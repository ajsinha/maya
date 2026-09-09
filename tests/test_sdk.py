"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The SDK, against the real application rather than against a mock of it.

A mock of the thing under test proves only that the mock agrees with itself, and
an SDK is precisely the code whose value is that it agrees with a *server*. So
the transport seam takes the FastAPI test client, and every call below travels
the whole stack — routes, authorisation, the CSRF boundary, the domain, the
evidence chain — and comes back.

Two properties matter more than coverage of the methods.

**The SDK decides nothing.** There is no local rule here about who may act, no
copy of the tiering bands, no view of which verbs a class admits. A second
implementation of a governance rule can disagree with the first, and it will
disagree in the direction of permitting more, because that is the direction in
which nobody files a bug.

**A refusal is raised, never returned.** A caller who forgets to check a returned
verdict has continued past a governance decision while their code reads as though
it succeeded.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "sdk" / "python"))

from maya_sdk import (Blocked, Maya, NotAuthenticated, NotFound, NotPermitted,
                      Refused, Unreachable)
from maya_sdk.artifacts import digest_of
from maya_sdk.models import short
from maya_sdk.transport import IDEMPOTENT

URN = "maya://model/credit.pd.smallbiz"

KERNEL = {"parameter_kind": "estimated_coefficients", "fit_procedure": "estimate",
          "input_schema": [{"name": "dscr", "dtype": "float",
                            "minimum": -5, "maximum": 20}],
          "output_schema": [{"name": "pd_12m", "dtype": "float"}]}


class _TestClientTransport:
    """Speaks the transport interface, drives the app in-process.

    This is the seam the SDK was designed around: the client takes a transport
    rather than building one, so the tests exercise the real routes.
    """

    def __init__(self, client, auth=None):
        self.client, self.auth = client, auth

    def request(self, method, path, *, json=None, content=None, params=None,
                headers=None):
        clean = {k: v for k, v in (params or {}).items() if v is not None}
        return self.client.request(method, path, json=json, content=content,
                                   params=clean or None, headers=headers,
                                   auth=self.auth or self.client.auth)


@pytest.fixture
def maya(client):
    return Maya(transport=_TestClientTransport(client))


@pytest.fixture
def as_person(client):
    def _as(credentials):
        return Maya(transport=_TestClientTransport(client, auth=credentials))
    return _as


class TestTheUrnIsAcceptedInBothSpellings:
    """A caller reads the full URN off a warrant and the short name off a URL.
    Making them convert produces a 404 whose cause is a string format."""

    @pytest.mark.parametrize("given,expected", [
        ("maya://model/credit.pd.smallbiz", "credit.pd.smallbiz"),
        ("credit.pd.smallbiz", "credit.pd.smallbiz"),
        ("maya://model/a.b#champion", "a.b#champion"),
    ])
    def test_both_reach_the_same_place(self, given, expected):
        assert short(given) == expected


class TestRegisteringAModel:
    def test_a_model_is_registered_and_read_back(self, maya):
        out = maya.models.register(
            urn=URN, name="SB PD", model_class="credit.pd.scorecard",
            domain="credit", owner="person/admin", legal_entity="LE-US-01",
            purpose="12-month PD at origination")
        assert out["urn"] == URN and out["status"] == "draft"
        assert maya.models.get(URN)["model"]["name"] == "SB PD"

    def test_the_inventory_comes_back_paged(self, maya):
        maya.models.register(urn=URN, name="SB PD",
                             model_class="c", domain="credit",
                             owner="person/admin", legal_entity="LE-1",
                             purpose="p")
        listing = maya.models.list(domain="credit")
        assert listing["total"] == 1 and listing["limit"]

    def test_a_duplicate_is_refused_rather_than_returned(self, maya):
        args = dict(urn=URN, name="SB PD", model_class="c", domain="credit",
                    owner="person/admin", legal_entity="LE-1", purpose="p")
        maya.models.register(**args)
        with pytest.raises(Refused) as exc:
            maya.models.register(**args)
        assert exc.value.status == 409
        assert exc.value.remediation, "a refusal without a remediation is a wall"

    def test_the_tier_comes_back_with_its_derivation(self, maya):
        maya.models.register(urn=URN, name="SB PD", model_class="c",
                             domain="credit", owner="person/admin",
                             legal_entity="LE-1", purpose="p")
        # A version first: the tier reads the trainability class off the latest
        # one, and assessing without a version is refused rather than read as
        # T0.
        maya.versions.create(URN, semver="1.0.0", kernel=KERNEL)
        out = maya.models.assess(URN, exposure=2_000_000_000,
                                 purpose_class="regulatory_capital",
                                 feature_count=12, uses_alternative_data=False,
                                 interpretable=True)
        assert out["tier"] in (1, 2, 3, 4)
        assert out.get("derivation") or out.get("rationale"), \
            "a tier without its derivation is an opinion"


class TestARefusalIsRaisedAndCarriesItsRemediation:
    def test_an_unknown_model_raises_not_found(self, maya):
        with pytest.raises(NotFound) as exc:
            maya.models.get("maya://model/nothing.here")
        assert exc.value.status == 404

    def test_bad_credentials_raise_not_authenticated(self, as_person):
        with pytest.raises(NotAuthenticated):
            as_person(("nobody", "wrong")).whoami()

    def test_a_permission_refusal_has_its_own_class(self, as_person, people):
        """The one a first-line tool wants to catch on purpose: it should hide a
        button, not crash."""
        with pytest.raises(NotPermitted):
            as_person(people["d.raman"]).models.register(
                urn="maya://model/x.y", name="X", model_class="c",
                domain="credit", owner="person/x", legal_entity="LE-1",
                purpose="p")

    def test_a_governance_refusal_is_told_apart_from_an_error(self, maya):
        """`Blocked` is the refusal the platform exists to produce, so a caller
        can report it as governance rather than as a fault."""
        maya.models.register(urn=URN, name="SB PD", model_class="c",
                             domain="credit", owner="person/admin",
                             legal_entity="LE-1", purpose="p")
        maya.versions.create(URN, semver="1.0.0", kernel=KERNEL)
        with pytest.raises(Blocked):
            maya.versions.create(URN, semver="1.0.0", kernel=KERNEL)

    def test_the_request_id_reaches_the_exception(self, maya):
        with pytest.raises(Refused) as exc:
            maya.models.get("maya://model/nothing.here")
        assert exc.value.request_id, \
            "without it, 'it failed' and 'which line was mine' are two searches"
        assert exc.value.request_id == maya.last_request_id

    def test_the_message_carries_all_three_parts(self, maya):
        with pytest.raises(Refused) as exc:
            maya.models.get("maya://model/nothing.here")
        assert "not_found" in str(exc.value)
        assert "[request " in str(exc.value)

    def test_a_body_that_is_not_the_problem_shape_still_raises_usefully(self):
        from maya_sdk.errors import refusal
        exc = refusal(502, "<html>Bad Gateway</html>", "req-1")
        assert exc.code == "http_502" and "Bad Gateway" in exc.detail


class TestVersionsAndPromotion:
    def test_a_version_is_created_and_its_class_derived(self, maya):
        maya.models.register(urn=URN, name="SB PD", model_class="c",
                             domain="credit", owner="person/admin",
                             legal_entity="LE-1", purpose="p")
        out = maya.versions.create(URN, semver="1.0.0", kernel=KERNEL)
        assert out["semver"] == "1.0.0"
        assert out["trainability_class"].startswith("T"), \
            "derived by the platform from how P is inhabited, never declared here"
        assert "trainability_class" not in KERNEL, \
            "the caller never declares it; it falls out of parameter_kind and "\
            "fit_procedure"

    def test_the_sdk_holds_no_opinion_about_the_class(self):
        """Asserted on the source, because the temptation to 'help' by
        computing it locally is exactly what would create a second rule."""
        import re
        root = Path(__file__).resolve().parents[1] / "sdk" / "python" / "maya_sdk"
        classes = re.compile(r"\bT[0-8]\b")
        offenders = []
        for path in sorted(root.glob("*.py")):
            body = path.read_text()
            # Strip docstrings and comments: explaining a class in prose is the
            # point of the documentation, and enumerating one in code is the
            # second rule this test exists to prevent.
            code = re.sub(r'"""(?:.|\n)*?"""', "", body)
            code = "\n".join(line.split("#")[0] for line in code.split("\n"))
            if classes.search(code):
                offenders.append(path.name)
        assert not offenders, (
            f"{offenders} enumerate a trainability class in code. The platform "
            "derives the class from how P is inhabited; a copy here is a second "
            "rule that can disagree with the first")


class TestArtifacts:
    def test_the_digest_is_computed_here_and_checked_there(self, maya, tmp_path):
        """The one thing a thin wrapper would not do. Letting the server hash
        whatever it received would make the check tautological."""
        weights = tmp_path / "model.onnx"
        weights.write_bytes(b"\x08\x01onnx-ish" + b"\x00\xff" * 4000)
        out = maya.artifacts.put(weights, format="onnx")
        assert out["digest"] == digest_of(weights)
        assert out["stored"] is True

    def test_storing_it_twice_stores_it_once(self, maya, tmp_path):
        weights = tmp_path / "model.onnx"
        weights.write_bytes(b"same bytes" * 500)
        first = maya.artifacts.put(weights, format="onnx")
        second = maya.artifacts.put(weights, format="onnx")
        assert second["digest"] == first["digest"] and second["stored"] is False

    def test_the_bytes_come_back_exactly(self, maya, tmp_path):
        weights = tmp_path / "model.onnx"
        weights.write_bytes(b"\x01\x02\x03" * 900)
        digest = maya.artifacts.put(weights, format="onnx")["digest"]
        back = maya.artifacts.get(digest, tmp_path / "back.onnx")
        assert back.read_bytes() == weights.read_bytes()

    def test_an_unknown_format_is_refused_by_the_platform(self, maya, tmp_path):
        f = tmp_path / "m.pkl"
        f.write_bytes(b"nope")
        with pytest.raises(Refused) as exc:
            maya.artifacts.put(f, format="pickle")
        assert exc.value.code == "unknown_format"

    def test_which_formats_run_code_is_asked_rather_than_assumed(self, maya):
        by = {f["format"]: f for f in maya.artifacts.formats()["formats"]}
        assert by["torchscript"]["executes_on_load"] is True
        assert by["safetensors"]["executes_on_load"] is False


class TestFeaturesAndFeaturesets:
    def test_a_feature_and_a_featureset_are_defined_and_filled(self, maya):
        maya.features.define(name="dscr", entity="borrower_id", dtype="numeric",
                             description="Debt service coverage",
                             owner="person/admin")
        maya.featuresets.define(name="sb_core", entity="borrower_id",
                                slots={"dscr": "numeric"})
        assert maya.featuresets.get("sb_core")["name"] == "sb_core"

    def test_a_derived_feature_can_actually_be_declared(self, maya):
        """`derive()` shipped unable to make a single successful call.

        It sent an `owner` field. The endpoint sets the owner from the
        authenticated principal and forbids extra fields, so every call it could
        make returned 422 — and nothing in the repository called it and no test
        covered it, so nothing said so. Found by writing a case study against
        the SDK, which is the first time the method was used.

        This asserts the round trip rather than the payload: a test that checked
        the body would have passed against the broken version just as happily.
        """
        maya.features.define(name="spot_px", entity="contract", dtype="numeric",
                             description="underlying price", owner="person/admin")
        maya.features.define(name="strike_px", entity="contract", dtype="numeric",
                             description="contract strike", owner="person/admin")
        made = maya.features.derive(
            name="moneyness_sdk", expression="strike_px / spot_px",
            dtype="numeric", description="strike over spot")
        assert made["name"] == "moneyness_sdk"
        assert maya.features.lineage("moneyness_sdk")["rests_on"]

    def test_a_bad_upload_names_the_file_rather_than_guessing(self, maya, tmp_path):
        odd = tmp_path / "values.dat"
        odd.write_bytes(b"x")
        with pytest.raises(ValueError, match="media_type"):
            maya.features.load("any_view", odd)

    def test_a_bulk_read_asks_for_a_known_format(self, maya):
        with pytest.raises(ValueError, match="format must be one of"):
            maya.featuresets.data("sb_core", version=1, into="/tmp/x",
                                  format="excel")


class TestWarrantsAndTheGrammar:
    def test_the_grammar_is_asked_for_rather_than_carried(self, maya):
        """A vocabulary copied into a client is a vocabulary that goes stale."""
        grammar = maya.warrants.grammar()
        assert grammar["operations"] and grammar["runtimes"] and grammar["bindings"]

    def test_a_document_is_validated_by_the_platform(self, maya):
        report = maya.warrants.validate({"maya_warrant": "nonsense"})
        assert report["valid"] is False and report["problems"]

    def test_the_profiles_can_be_read(self, maya):
        assert "profiles" in maya.warrants.profiles()


class TestTheTransport:
    def test_post_is_never_retried(self):
        """A create that timed out may well have succeeded, and retrying it
        registers the model twice. An SDK that quietly duplicates a governance
        act is worse than one that fails loudly."""
        assert "POST" not in IDEMPOTENT
        assert {"GET", "PUT", "DELETE"} <= IDEMPOTENT

    def test_an_unreachable_platform_is_not_a_refusal(self):
        """"MAYA said no" and "MAYA did not answer" call for opposite responses,
        and a client that collapses them treats an outage as a verdict."""
        from maya_sdk.transport import HttpTransport
        transport = HttpTransport("http://127.0.0.1:1", "u", "p",
                                  timeout=0.05, retries=1)
        maya = Maya(transport=transport)
        with pytest.raises(Unreachable):
            maya.whoami()
        assert not issubclass(Unreachable, Refused)

    def test_basic_credentials_need_no_csrf_token(self, maya):
        """The SDK authenticates with a credential it has to present, which is
        not ambient — so the CSRF boundary does not apply to it, and that is a
        property of the design rather than an exemption from it."""
        maya.models.register(urn=URN, name="SB PD", model_class="c",
                             domain="credit", owner="person/admin",
                             legal_entity="LE-1", purpose="p")

    def test_it_depends_on_nothing_outside_the_standard_library(self):
        """A governance platform that cannot be deployed air-gapped is one
        somebody works around; an SDK with a dependency tree moves that problem
        into the client's build pipeline rather than solving it."""
        import ast
        root = Path(__file__).resolve().parents[1] / "sdk" / "python" / "maya_sdk"
        allowed = set(sys.stdlib_module_names) | {"maya_sdk"}
        for path in sorted(root.glob("*.py")):
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names = [a.name.split(".")[0] for a in node.names]
                elif isinstance(node, ast.ImportFrom) and node.level == 0:
                    names = [(node.module or "").split(".")[0]]
                else:
                    continue
                for name in names:
                    assert name in allowed, f"{path.name} imports {name}"


class TestWhoAmI:
    def test_the_permissions_come_from_the_platform(self, maya):
        """So a tool can hide an action the caller may not take without ever
        deciding that for itself."""
        me = maya.whoami()
        assert me["username"] == "admin" and me["permissions"]

    def test_readiness_is_outside_the_versioned_api(self, maya):
        assert "status" in maya.health()
