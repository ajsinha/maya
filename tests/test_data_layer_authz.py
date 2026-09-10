"""The same authorisation, twice, from one definition.

Scope already decides which models a principal may act on and every route
applies it. The requirement asks for the same rule in the data layer as well —
and the reason a firm asks is not distrust of the application: it is that a
read-only credential, a reporting tool, a restored backup and a support engineer
running a query are four ways to read rows the API would have refused.
"""
from __future__ import annotations


from core.authz.datalayer import (REDACTED, SCOPED_TABLES, SENSITIVE_FIELDS,
                                  encryption_posture, policies, redact,
                                  redactions)


class TestFieldLevelIsRedactionNotOmission:
    def test_a_field_a_reader_may_not_see_is_marked(self):
        out = redact({"name": "SB PD", "exposure": 2e9}, ["model:read"])
        assert out["name"] == "SB PD"
        assert out["exposure"] == REDACTED

    def test_the_permission_reveals_it(self):
        out = redact({"exposure": 2e9}, ["model:read", "report:read"])
        assert out["exposure"] == 2e9

    def test_a_field_that_is_absent_stays_absent(self):
        assert "exposure" not in redact({"name": "x"}, [])

    def test_a_null_field_is_not_marked(self):
        """Marking a null would tell a reader something is there when nothing
        is, which is the same misleading silence in the other direction."""
        assert redact({"exposure": None}, [])["exposure"] is None

    def test_the_reader_is_told_what_would_reveal_it(self):
        """Silence would let somebody conclude a model has no exposure recorded
        when what they lack is a permission."""
        out = redactions(["model:read"])
        assert "exposure" in out["redacted_fields"]
        assert out["detail"][0]["needs"] == "report:read"
        assert "cannot tell from a response where the field is empty" in (
            out["why_marked"])

    def test_a_reader_who_sees_everything_is_told_nothing_is_hidden(self):
        granted = [spec["permission"] for spec in SENSITIVE_FIELDS.values()]
        assert redactions(granted)["redacted_fields"] == []

    def test_the_list_is_short_on_purpose(self):
        """Field-level authorisation over a hundred fields is a policy nobody
        can reason about."""
        assert len(SENSITIVE_FIELDS) <= 5
        assert all(v["why"] and v["permission"] for v in SENSITIVE_FIELDS.values())


class TestRowLevelIsGeneratedNotWritten:
    def test_it_enables_row_level_security_on_the_scoped_tables(self):
        out = policies()
        assert any("ENABLE ROW LEVEL SECURITY" in s for s in out["statements"])
        assert out["tables"] == sorted(SCOPED_TABLES)

    def test_the_policy_covers_every_scope_dimension(self):
        """Two enforcement points written twice will disagree, and the one that
        disagrees permissively is the one nobody notices."""
        sql = "\n".join(policies()["statements"])
        for column in SCOPED_TABLES["model"]:
            assert column in sql

    def test_an_empty_setting_is_unrestricted_like_the_scope(self):
        """`Scope.unrestricted` is *no entities and no domains*, and the SQL
        has to mean the same thing."""
        sql = "\n".join(policies()["statements"])
        assert "IS NULL" in sql and "= ''" in sql

    def test_it_says_where_it_came_from(self):
        out = policies()
        assert out["generated_from"] == "core.authz.scope.Scope"
        assert "one rule expressed twice" in out["detail"]

    def test_it_is_emitted_and_not_executed(self):
        """A platform that turned on row-level security against a running
        database would be making an availability decision for somebody else."""
        assert "Emitted rather than executed" in policies()["detail"]

    def test_only_tables_carrying_the_scope_directly_are_policied(self):
        """A join inside a security policy is a performance cliff that gets the
        policy disabled."""
        assert set(SCOPED_TABLES) == {"model"}


class TestEncryptionIsReportedNotClaimed:
    def test_a_sound_instance_says_so(self):
        out = encryption_posture(https=True, cookie_secure=True,
                                 database_url="postgres://h/db?sslmode=require")
        assert out["sound"] is True
        assert "nothing about the transport is misconfigured" in out["detail"]

    def test_plain_http_is_named(self):
        out = encryption_posture(https=False, cookie_secure=True)
        assert any(f["state"] == "not encrypted" for f in out["findings"])

    def test_an_insecure_cookie_is_named(self):
        out = encryption_posture(https=True, cookie_secure=False)
        assert any("session cookie" in f["what"] for f in out["findings"])
        assert any("one plain-HTTP request hands over a signed session"
                   in f["why"] for f in out["findings"])

    def test_a_database_url_without_tls_is_named(self):
        out = encryption_posture(https=True, cookie_secure=True,
                                 database_url="postgres://h/db")
        assert out["database_tls"] is False
        assert any("database" in f["what"] for f in out["findings"])

    def test_the_published_secret_is_named(self):
        out = encryption_posture(https=True, cookie_secure=True,
                                 session_secret_is_default=True)
        assert any("forge a signed session" in f["why"]
                   for f in out["findings"])

    def test_at_rest_is_delegated_and_says_so(self):
        """A platform shipping its own would be shipping a key-management
        decision nobody asked it to make."""
        out = encryption_posture(https=True, cookie_secure=True)
        assert "not this platform's" in out["at_rest"]
        assert "the inference log's retention" in out["at_rest"]

    def test_field_level_encryption_says_why_half_is_worse_than_none(self):
        out = encryption_posture(https=True, cookie_secure=True)
        assert "worse than none, because it reads as solved" in (
            out["field_level"])

    def test_findings_are_reported_rather_than_refused_at_boot(self):
        """An instance somebody is trying out on a laptop is a legitimate
        thing, and refusing it would teach people to set the flags without
        meaning them."""
        out = encryption_posture(https=False, cookie_secure=False)
        assert "reported rather than refused at boot" in out["detail"]


class TestOverHttp:
    def test_the_policies_and_this_readers_redactions_are_served(self, client,
                                                                 people):
        r = client.get("/api/v1/data-layer-authorisation",
                       auth=people["a.mehta"])
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["generated_from"] == "core.authz.scope.Scope"
        assert "redacted_fields" in body

    def test_the_encryption_posture_is_served(self, client):
        r = client.get("/health/encryption")
        assert r.status_code == 200, r.text
        body = r.json()
        assert "at_rest" in body and "findings" in body
        assert "not this platform's" in body["at_rest"]

    def test_a_development_instance_is_told_what_is_wrong(self, client):
        """An instance reachable by anybody else with these findings is one
        whose assurances do not hold."""
        body = client.get("/health/encryption").json()
        assert body["sound"] is False
        assert body["findings"]
