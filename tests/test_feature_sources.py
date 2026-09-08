"""
MAYA — where a feature view's values come from, when they are not uploaded.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

A source is **pulled, never read through**, and that is the whole design.

MAYA fetches from the SQL query, the file or the object store and writes what
it got into its own Delta as a new version — with the same two clocks, the same
quality measurement and the same immutability as an upload. Reading through
would give away everything this platform exists to guarantee:

  * a warehouse table overwritten since March cannot say what was knowable in
    March, and will answer something rather than refuse;
  * a training set built from a live query is a description of one, not one;
  * "where did this number come from" has to survive the source being dropped.

So these hold three things: that a pull produces an ordinary, immutable,
pinnable version; that a source may only READ, refused before it is stored
rather than before it is run; and that no credential is ever written down.
"""
from __future__ import annotations

import json
import sqlite3
import time

import pytest

from core.features.sources import SourceError, SourceRegistry

API = "/api/v1"



@pytest.fixture
def a_view(client):
    for name in ("dscr", "ltv"):
        client.post(f"{API}/features", json={
            "name": name, "entity": "borrower", "dtype": "numeric",
            "description": name, "owner": "person/admin"})
    assert client.post(f"{API}/feature-views", json={
        "name": "risk", "entity": "borrower", "owner": "person/admin",
        "features": ["dscr", "ltv"]}).status_code == 201
    return "risk"


@pytest.fixture
def a_csv(tmp_path):
    """A file shaped the way somebody's export actually is: their column names,
    not MAYA's."""
    now = time.time()
    path = tmp_path / "rows.csv"
    path.write_text(
        "customer_number,asof,loaded_at,dscr,ltv\n" + "\n".join(
            f"b{i},{now - 86400 * i},{now},{1.1 + i / 10:.2f},{0.5 + i / 100:.2f}"
            for i in range(5)))
    return path


@pytest.fixture
def a_warehouse(tmp_path):
    """A real external database, not a mock. The point of a connector is that
    it talks to something."""
    path = tmp_path / "warehouse.db"
    now = time.time()
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE risk (cust TEXT, asof REAL, seen REAL, "
                 "dscr REAL, ltv REAL)")
    conn.executemany("INSERT INTO risk VALUES (?,?,?,?,?)",
                     [(f"b{i}", now - 86400 * i, now, 1.0 + i / 10, 0.4 + i / 50)
                      for i in range(7)])
    conn.commit()
    conn.close()
    return path


MAPPING = {"columns": {"customer_number": "entity_id", "asof": "event_ts",
                       "loaded_at": "ingest_ts"}}
SQL_MAPPING = {"columns": {"cust": "entity_id", "asof": "event_ts",
                           "seen": "ingest_ts"}}


class TestAPullProducesAnOrdinaryVersion:
    def test_a_csv_on_disk_becomes_a_feature_view_version(self, client, a_view, a_csv):
        assert client.put(f"{API}/feature-views/{a_view}/source", json={
            "kind": "file", "locator": str(a_csv), "options": MAPPING
        }).status_code == 201
        pulled = client.post(f"{API}/feature-views/{a_view}/source/pull")
        assert pulled.status_code == 201, pulled.text
        assert pulled.json()["rows"] == 5
        assert pulled.json()["version"] == 1

        versions = client.get(f"{API}/feature-views/{a_view}/versions").json()
        rows = versions.get("versions", versions)
        assert [(v["version"], v["row_count"]) for v in rows] == [(1, 5)]

    def test_a_sql_query_does_too(self, client, a_view, a_warehouse):
        client.put(f"{API}/feature-views/{a_view}/source", json={
            "kind": "sql", "locator": f"sqlite:///{a_warehouse}",
            "statement": "SELECT cust, asof, seen, dscr, ltv FROM risk",
            "options": SQL_MAPPING})
        assert client.post(f"{API}/feature-views/{a_view}/source/pull"
                           ).json()["rows"] == 7

    def test_a_second_pull_is_a_second_version_and_not_an_update(
            self, client, a_view, a_csv):
        """The previous version keeps serving exactly what it served, because
        it is a different Delta path — so a warrant pinned to it does not
        change meaning because somebody refreshed the source. That is the
        entire reason MAYA pulls rather than reads through."""
        client.put(f"{API}/feature-views/{a_view}/source", json={
            "kind": "file", "locator": str(a_csv), "options": MAPPING})
        first = client.post(f"{API}/feature-views/{a_view}/source/pull").json()
        second = client.post(f"{API}/feature-views/{a_view}/source/pull").json()
        assert (first["version"], second["version"]) == (1, 2)
        assert first["digest"] == second["digest"]

    def test_and_says_when_the_bytes_were_the_same(self, client, a_view, a_csv):
        """"We refreshed and nothing changed" is a fact a reviewer wants. A
        silent no-op is not."""
        client.put(f"{API}/feature-views/{a_view}/source", json={
            "kind": "file", "locator": str(a_csv), "options": MAPPING})
        assert client.post(f"{API}/feature-views/{a_view}/source/pull"
                           ).json()["unchanged"] is False
        again = client.post(f"{API}/feature-views/{a_view}/source/pull").json()
        assert again["unchanged"] is True
        assert "the same bytes" in client.get(
            f"{API}/feature-views/{a_view}/source").json()["source"]["last_pull_detail"]

    def test_the_pull_is_on_the_evidence_chain(self, client, a_view, a_csv):
        """What was read, from where, how many rows and with what digest —
        because "where did this number come from" has to have an answer that
        survives the source being dropped."""
        client.put(f"{API}/feature-views/{a_view}/source", json={
            "kind": "file", "locator": str(a_csv), "options": MAPPING})
        client.post(f"{API}/feature-views/{a_view}/source/pull")
        # Read from the chain itself. `/evidence/chain` VERIFIES the chain and
        # returns a verdict rather than the nodes, which is the right shape for
        # that endpoint and the wrong one for this question.
        nodes = client.app.state.ctx["evidence"].repo.many()
        kinds = [n["kind"] for n in nodes]
        assert "feature_source_pulled" in kinds
        assert "feature_source_declared" in kinds

        pulled = next(n for n in nodes if n["kind"] == "feature_source_pulled")
        payload = json.loads(pulled["payload"]) if isinstance(
            pulled["payload"], str) else pulled["payload"]
        # What was read, from where, how many rows and with what digest.
        assert payload["rows"] == 5
        assert payload["view"] == a_view
        assert payload["digest"].startswith("sha256:")
        assert "locator" in payload

    def test_the_source_is_mapped_to_mayas_column_names(self, client, a_view, a_csv):
        """A warehouse calls the entity `customer_number` and the clock `asof`.
        Renaming here rather than making somebody rewrite their query is the
        difference between a source people declare and one people export a CSV
        to avoid."""
        client.put(f"{API}/feature-views/{a_view}/source", json={
            "kind": "file", "locator": str(a_csv), "options": MAPPING})
        preview = client.get(f"{API}/feature-views/{a_view}/source/preview").json()
        assert "entity_id" in preview["columns"]
        assert "customer_number" not in preview["columns"]
        assert preview["usable"] is True


class TestPreviewWritesNothing:
    """The only way to find out that the source calls the clock `asof` without
    first producing a version that says so."""

    def test_it_reads_without_producing_a_version(self, client, a_view, a_csv):
        client.put(f"{API}/feature-views/{a_view}/source", json={
            "kind": "file", "locator": str(a_csv), "options": MAPPING})
        assert client.get(f"{API}/feature-views/{a_view}/source/preview"
                          ).json()["row_count"] == 5
        versions = client.get(f"{API}/feature-views/{a_view}/versions").json()
        assert not versions.get("versions", versions)

    def test_it_names_the_columns_that_are_missing(self, client, a_view, a_csv):
        """A row without both clocks is refused at load. Saying so at preview
        means it is refused before a version exists rather than after."""
        client.put(f"{API}/feature-views/{a_view}/source", json={
            "kind": "file", "locator": str(a_csv)})       # no mapping
        preview = client.get(f"{API}/feature-views/{a_view}/source/preview").json()
        assert preview["usable"] is False
        assert set(preview["missing_required"]) == {"entity_id", "event_ts",
                                                    "ingest_ts"}
        assert "refused at load" in preview["detail"]

    def test_a_sql_preview_does_not_drag_the_whole_table_across(
            self, client, a_view, a_warehouse):
        """Preview is what somebody does BEFORE they are sure the query is
        right, so it must not be the expensive call. Fetched with `fetchmany`
        rather than read whole and sliced — driver-agnostic, because wrapping
        the statement in a LIMIT would mean knowing every dialect's spelling
        of one."""
        import inspect

        from core.features.sources import SourceRegistry

        source = inspect.getsource(SourceRegistry._read_sql)
        assert "fetchmany(limit)" in source
        assert "rows[:limit]" not in source, \
            "reading everything and slicing is what this replaced"

        client.put(f"{API}/feature-views/{a_view}/source", json={
            "kind": "sql", "locator": f"sqlite:///{a_warehouse}",
            "statement": "SELECT cust, asof, seen, dscr, ltv FROM risk",
            "options": SQL_MAPPING})
        assert client.get(f"{API}/feature-views/{a_view}/source/preview?limit=2"
                          ).json()["row_count"] == 2

    def test_it_honours_its_limit(self, client, a_view, a_csv):
        client.put(f"{API}/feature-views/{a_view}/source", json={
            "kind": "file", "locator": str(a_csv), "options": MAPPING})
        assert client.get(f"{API}/feature-views/{a_view}/source/preview?limit=2"
                          ).json()["row_count"] == 2


class TestASourceMayOnlyRead:
    """Refused before it is STORED, not before it is run. A statement nobody
    may run is a statement nobody should be able to save — the moment it is
    saved, somebody will schedule it."""

    @pytest.mark.parametrize("statement,word", [
        ("UPDATE risk SET dscr = 0", "UPDATE"),
        ("DELETE FROM risk", "DELETE"),
        ("DROP TABLE risk", "DROP"),
        ("TRUNCATE TABLE risk", "TRUNCATE"),
        ("INSERT INTO risk VALUES (1)", "INSERT"),
        ("CREATE TABLE x (a INT)", "CREATE"),
        ("GRANT ALL ON risk TO PUBLIC", "GRANT"),
    ])
    def test_a_write_is_refused(self, client, a_view, a_warehouse, statement, word):
        r = client.put(f"{API}/feature-views/{a_view}/source", json={
            "kind": "sql", "locator": f"sqlite:///{a_warehouse}",
            "statement": statement})
        assert r.status_code == 409
        assert word in r.json()["detail"]

    def test_a_second_statement_is_refused(self, client, a_view, a_warehouse):
        r = client.put(f"{API}/feature-views/{a_view}/source", json={
            "kind": "sql", "locator": f"sqlite:///{a_warehouse}",
            "statement": "SELECT 1; DROP TABLE risk"})
        assert r.status_code == 409
        assert "one statement" in r.json()["detail"]

    def test_a_select_that_merely_mentions_one_is_allowed(
            self, client, a_view, a_warehouse):
        """"SELECT ... FROM updates" is a perfectly good query, and a control
        that refuses correct work is one people route around."""
        assert client.put(f"{API}/feature-views/{a_view}/source", json={
            "kind": "sql", "locator": f"sqlite:///{a_warehouse}",
            "statement": "SELECT cust FROM risk WHERE cust NOT IN "
                         "(SELECT cust FROM risk WHERE dscr > 99)",
        }).status_code == 201

    def test_the_external_table_is_never_written_to(self, client, a_view,
                                                    a_warehouse):
        client.put(f"{API}/feature-views/{a_view}/source", json={
            "kind": "sql", "locator": f"sqlite:///{a_warehouse}",
            "statement": "SELECT cust, asof, seen, dscr, ltv FROM risk",
            "options": SQL_MAPPING})
        for _ in range(3):
            client.post(f"{API}/feature-views/{a_view}/source/pull")
        rows = sqlite3.connect(a_warehouse).execute(
            "SELECT COUNT(*), ROUND(SUM(dscr), 2) FROM risk").fetchone()
        assert rows == (7, 9.1)


class TestWhatCannotBeDeclared:
    def test_a_kind_maya_cannot_read(self, client, a_view):
        r = client.put(f"{API}/feature-views/{a_view}/source",
                       json={"kind": "ftp", "locator": "ftp://x/y"})
        assert r.status_code == 409
        assert "sql, file, s3, gcs" in r.json()["detail"]

    def test_a_file_whose_format_nothing_states(self, client, a_view):
        r = client.put(f"{API}/feature-views/{a_view}/source",
                       json={"kind": "file", "locator": "/tmp/mystery"})
        assert r.status_code == 409
        assert "csv, jsonl, parquet, arrow" in r.json()["detail"]

    def test_a_format_inferred_from_the_suffix(self, client, a_view, a_csv):
        """Somebody giving a path should not also have to say what it is."""
        client.put(f"{API}/feature-views/{a_view}/source",
                   json={"kind": "file", "locator": str(a_csv)})
        assert client.get(f"{API}/feature-views/{a_view}/source"
                          ).json()["source"]["format"] == "csv"

    def test_no_locator(self, client, a_view):
        r = client.put(f"{API}/feature-views/{a_view}/source",
                       json={"kind": "file", "locator": "   "})
        assert r.status_code == 409
        assert "locator" in r.json()["detail"]

    def test_a_view_reads_from_one_place(self, client, a_view, a_csv):
        """A view filled from two places at once has a provenance nobody can
        state."""
        client.put(f"{API}/feature-views/{a_view}/source", json={
            "kind": "file", "locator": str(a_csv), "options": MAPPING})
        r = client.put(f"{API}/feature-views/{a_view}/source", json={
            "kind": "file", "locator": str(a_csv), "options": MAPPING})
        assert r.status_code == 409
        assert "already reads from" in r.json()["detail"]

    def test_a_source_on_a_view_that_does_not_exist(self, client):
        r = client.put(f"{API}/feature-views/nothing-here/source",
                       json={"kind": "file", "locator": "/tmp/x.csv"})
        assert r.status_code >= 400

    def test_a_pull_of_nothing_is_not_a_version(self, client, a_view, tmp_path):
        """A version of nothing is not a version, and half a pull is worse than
        no pull."""
        empty = tmp_path / "empty.csv"
        empty.write_text("entity_id,event_ts,ingest_ts,dscr\n")
        client.put(f"{API}/feature-views/{a_view}/source",
                   json={"kind": "file", "locator": str(empty)})
        r = client.post(f"{API}/feature-views/{a_view}/source/pull")
        assert r.status_code == 409
        assert "no rows" in r.json()["detail"]
        versions = client.get(f"{API}/feature-views/{a_view}/versions").json()
        assert not versions.get("versions", versions)


class TestNoCredentialIsWrittenDown:
    """A register holding a warehouse password is a register nobody can hand to
    an auditor, and handing it to an auditor is this platform's whole point."""

    def test_the_row_holds_a_NAME_and_not_a_secret(self, client, a_view, a_csv):
        client.put(f"{API}/feature-views/{a_view}/source", json={
            "kind": "file", "locator": str(a_csv), "options": MAPPING,
            "credential_ref": "warehouse-reader"})
        source = client.get(f"{API}/feature-views/{a_view}/source").json()["source"]
        assert source["credential_ref"] == "warehouse-reader"
        assert "password" not in json.dumps(source).lower()

    def test_the_schema_has_nowhere_to_put_one(self):
        from db.schema.tables import METADATA

        columns = {c.name for c in METADATA.tables["feature_source"].columns}
        assert not columns & {"password", "secret", "token", "key",
                              "access_key", "credential"}
        assert "credential_ref" in columns

    def test_an_unknown_credential_name_falls_back_rather_than_failing(self, cfg_free):
        """An instance running with an instance profile or a local `~/.aws` is
        the common case, and refusing it would make the explicit-credential
        path the only path."""
        assert cfg_free("nothing-defines-this") is None


@pytest.fixture
def cfg_free(tmp_path):
    from run_maya_web import PropertiesConfigurator, _credential_resolver

    path = tmp_path / "c.yaml"
    path.write_text("app: {name: MAYA}\n")
    PropertiesConfigurator.reset()
    return _credential_resolver(PropertiesConfigurator(str(path), reload_interval=0))


class TestARefusalIsNotACrash:
    """`SourceError` is a `FeatureError`, and `guard()` looked its exception up
    by EXACT type — so every source refusal raised KeyError inside the handler
    that maps refusals, and arrived as a 500.

    A refusal reported as a crash is the unmapped failure DR-6 forbids,
    produced by the code written to prevent it.
    """

    def test_a_subclass_of_a_mapped_error_is_still_mapped(self, client, a_view,
                                                          a_warehouse):
        r = client.put(f"{API}/feature-views/{a_view}/source", json={
            "kind": "sql", "locator": f"sqlite:///{a_warehouse}",
            "statement": "DROP TABLE risk"})
        assert r.status_code == 409, "a refusal, not a 500"
        assert r.json()["error"] == "feature_refused"
        assert r.json()["remediation"], "and it says what to do instead"

    def test_the_mapping_walks_the_mro(self):
        from core.features.common import FeatureError

        class Deeper(SourceError):
            pass

        assert issubclass(Deeper, FeatureError)
        assert FeatureError in Deeper.__mro__


class TestSourcesCanBeSwitchedOff:
    """A deployment that forbids outbound connections leaves them off rather
    than configuring them into uselessness — and every route then says the same
    thing instead of five of them raising AttributeError."""

    def test_a_registry_without_a_repository_is_absent(self, db, evidence):
        from core.features.registry import FeatureRegistry
        from db import (ContractRepository, DerivedFeatureRepository,
                        FeatureRepository, FeatureViewRepository,
                        FeatureViewVersionRepository, SnapshotRepository)
        from db.delta_store import DeltaStore

        registry = FeatureRegistry(
            FeatureRepository(db), FeatureViewRepository(db),
            FeatureViewVersionRepository(db), ContractRepository(db),
            SnapshotRepository(db), DeltaStore("/tmp/maya-soak-unused"), evidence,
            DerivedFeatureRepository(db))
        assert registry.sources is None


class TestTheScreenOffersIt:
    """A source existed only as an API, which on a platform whose stated rule
    is that a screen is a client of the same API is the wrong way round."""

    def test_a_view_with_no_source_offers_the_form(self, client, a_view):
        from tests.api_helpers import login

        login(client)
        page = client.get(f"/feature-views/{a_view}").text
        assert "Where the values come from" in page
        assert 'id="src-locator"' in page
        assert 'id="src-statement"' in page
        assert 'id="src-mapping"' in page
        for kind in ("sql", "file", "s3", "gcs"):
            assert f'value="{kind}"' in page

    def test_it_says_why_maya_pulls_rather_than_reads_through(self, client, a_view):
        """The single most important thing on the panel: somebody about to
        point this at a warehouse needs to know it takes a copy."""
        from tests.api_helpers import login

        login(client)
        page = client.get(f"/feature-views/{a_view}").text
        assert "never serving a model off the source" in page
        assert "overwritten" in page

    def test_a_declared_source_is_shown_with_its_last_pull(self, client, a_view,
                                                           a_csv):
        from tests.api_helpers import login

        client.put(f"{API}/feature-views/{a_view}/source", json={
            "kind": "file", "locator": str(a_csv), "options": MAPPING,
            "credential_ref": "warehouse-reader"})
        client.post(f"{API}/feature-views/{a_view}/source/pull")
        login(client)
        page = client.get(f"/feature-views/{a_view}").text
        assert str(a_csv) in page
        assert "Last pull" in page
        assert "into v1" in page
        assert "Pull now" in page

    def test_the_credential_name_is_shown_and_labelled_as_a_name(
            self, client, a_view, a_csv):
        from tests.api_helpers import login

        client.put(f"{API}/feature-views/{a_view}/source", json={
            "kind": "file", "locator": str(a_csv), "options": MAPPING,
            "credential_ref": "warehouse-reader"})
        login(client)
        page = client.get(f"/feature-views/{a_view}").text
        assert "warehouse-reader" in page
        assert "NAME of one this deployment configures" in page

    def test_a_reader_is_not_offered_the_controls(self, client, people, a_view):
        """`feature:define` declares one and `feature:materialise` pulls it. A
        screen that offers a control it will then refuse teaches people that
        refusals are noise."""
        from tests.api_helpers import login

        login(client, *people["a.mehta"])
        page = client.get(f"/feature-views/{a_view}").text
        assert 'id="declare-source"' not in page
        assert "Declaring a source needs" in page


class TestTheRegistryIsUsableWithoutTheWeb:
    """Every act here is one a script can perform, because the screen is a
    client of the same thing."""

    def test_declare_and_pull_directly(self, db, evidence, tmp_path, a_csv):
        from core.features.registry import FeatureRegistry
        from db import (ContractRepository, DerivedFeatureRepository,
                        FeatureRepository, FeatureSourceRepository,
                        FeatureViewRepository, FeatureViewVersionRepository,
                        SnapshotRepository)
        from db.delta_store import DeltaStore

        features = FeatureRegistry(
            FeatureRepository(db), FeatureViewRepository(db),
            FeatureViewVersionRepository(db), ContractRepository(db),
            SnapshotRepository(db), DeltaStore(str(tmp_path / "delta")), evidence,
            DerivedFeatureRepository(db), sources=FeatureSourceRepository(db))
        features.define("dscr", "borrower", "numeric", "d", "person/admin")
        features.create_view("v", "borrower", "person/admin", ["dscr"])
        assert isinstance(features.sources, SourceRegistry)
        features.sources.declare("v", "file", str(a_csv), options=MAPPING)
        assert features.sources.pull("v")["rows"] == 5
