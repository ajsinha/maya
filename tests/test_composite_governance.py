"""
The composite controls §8.7 and §9.5 describe, which existed as helpers nothing called:
structure checked when the composite is written (cycles, nesting depth), read access to
every member, a seed per member, and — before a warrant seals — an approved parameter set
covering every trainable member, not just the first one anyone fitted.

Copyright (c) 2026 Ashutosh Sinha.  All rights reserved.
"""

from __future__ import annotations

import pytest

from maya.core.errors import NotApproved, PermissionDenied, ValidationFailed
from maya.formula import composite as comp
from tests.conftest import PASSWORD
from tests.test_warrants import complete_spec, journey  # noqa: F401 - the fixture, reused


def _member(w, name: str, formula: str, roles: dict[str, str]) -> str:
    w.p.models.create(w.mona, namespace="quant", name=name, formula=formula, roles=roles)
    w.p.models.update_draft(w.mona, f"quant/{name}", spec_latex=complete_spec(name))
    w.p.models.transition(w.mona, f"quant/{name}", 1, "submit")
    w.p.models.transition(w.mgr, f"quant/{name}", 1, "approve")
    return f"maya://model/quant/{name}@v1"


def _composite_ir(members: dict[str, str]) -> dict:
    aliases = sorted(members)
    return {
        "outputs": [{"name": "yhat", "type": "float64"}],
        "inputs": [],
        "composite": {
            "kind": "ensemble",
            "members": [{"alias": a, "ref": members[a]} for a in aliases],
            "combine": {"op": "add", "args": [{"ref": f"{a}.yhat"} for a in aliases]},
        },
    }


@pytest.fixture(scope="module")
def blend(journey):  # noqa: F811
    w = journey
    refs = {
        "one": _member(w, "cg_one", "yhat = a*x", {"a": "parameter"}),
        "two": _member(w, "cg_two", "yhat = b*x", {"b": "parameter"}),
    }
    w.p.models.create(w.mona, namespace="quant", name="cg_blend", kind="composite")
    w.p.models.update_draft(
        w.mona, "quant/cg_blend", ir=_composite_ir(refs), spec_latex=complete_spec("cg_blend")
    )
    w.p.models.transition(w.mona, "quant/cg_blend", 1, "submit")
    w.p.models.transition(w.mgr, "quant/cg_blend", 1, "approve")
    return w, refs


def test_a_warrant_seals_only_when_every_trainable_member_is_fitted(blend):
    w, _ = blend
    tw = w.p.warrants.create(
        w.devi,
        namespace="quant",
        name="cg_calib",
        model="quant/cg_blend@v1",
        featureset="maya://featureset/quant/panel#q1/2026-02-28",
        spec={"target": "y", "seed": 11},
    )
    checksum = w.p.warrants.data(w.devi, tw["id"])["manifest"]["checksum"]
    first = w.p.warrants.upload_parameters(
        w.devi, tw["id"], values={"a": 2.0}, data_checksum=checksum, member_alias="one"
    )
    w.p.warrants.parameter_transition(w.devi, first["id"], "submit")
    w.p.warrants.parameter_transition(w.mgr, first["id"], "approve")
    w.p.warrants.transition(w.devi, tw["id"], "submit")
    w.p.warrants.transition(w.mgr, tw["id"], "approve")
    with pytest.raises(NotApproved, match="still to fit: two"):
        w.p.warrants.seal(w.mgr, tw["id"])
    second = w.p.warrants.upload_parameters(
        w.devi, tw["id"], values={"b": 0.5}, data_checksum=checksum, member_alias="two"
    )
    w.p.warrants.parameter_transition(w.devi, second["id"], "submit")
    w.p.warrants.parameter_transition(w.mgr, second["id"], "approve")
    assert w.p.warrants.seal(w.mgr, tw["id"])["sealed_at"] is not None


def test_one_combined_parameter_set_also_covers_every_member(blend):
    w, _ = blend
    tw = w.p.warrants.create(
        w.devi,
        namespace="quant",
        name="cg_combined",
        model="quant/cg_blend@v1",
        featureset="maya://featureset/quant/panel#q1/2026-02-28",
        spec={"target": "y", "seed": 12},
    )
    checksum = w.p.warrants.data(w.devi, tw["id"])["manifest"]["checksum"]
    ps = w.p.warrants.upload_parameters(
        w.devi, tw["id"], values={"one.a": 2.0, "two.b": 0.5}, data_checksum=checksum
    )
    w.p.warrants.parameter_transition(w.devi, ps["id"], "submit")
    w.p.warrants.parameter_transition(w.mgr, ps["id"], "approve")
    w.p.warrants.transition(w.devi, tw["id"], "submit")
    w.p.warrants.transition(w.mgr, tw["id"], "approve")
    assert w.p.warrants.seal(w.mgr, tw["id"])["sealed_at"] is not None


def test_each_member_gets_its_own_seed_derived_from_the_warrant_seed(blend):
    w, _ = blend
    tw = w.p.warrants.create(
        w.devi,
        namespace="quant",
        name="cg_seeds",
        model="quant/cg_blend@v1",
        featureset="maya://featureset/quant/panel#q1/2026-02-28",
        spec={"target": "y", "seed": 7},
    )
    seeds = tw["spec"]["member_seeds"]
    assert set(seeds) == {"one", "two"} and seeds["one"] != seeds["two"]
    assert seeds == comp.member_seeds(7, ["one", "two"]), "derived, not random"


def test_a_composite_that_refers_to_itself_is_refused_while_it_is_a_draft(blend):
    w, refs = blend
    w.p.models.create(w.mona, namespace="quant", name="cg_loop", kind="composite")
    ir = _composite_ir({"one": refs["one"], "self": "maya://model/quant/cg_loop@v1"})
    with pytest.raises(ValidationFailed, match="cycle"):
        w.p.models.update_draft(w.mona, "quant/cg_loop", ir=ir)


def test_a_composite_needs_read_on_every_member(blend):
    """A composite exposes its members' contract and behaviour, so writing one requires
    read on each. Before this, a member you could not open could be wrapped and used."""
    w, refs = blend
    w.p.access.create_user(
        w.admin, username="cg_outsider", password=PASSWORD, roles=["model_designer"]
    )
    w.p.access.create_namespace(
        w.admin, name="cg_shut", preset="small_team", default_visibility="private"
    )
    w.p.models.create(
        w.mona,
        namespace="cg_shut",
        name="cg_hidden",
        formula="yhat = d*x",
        roles={"d": "parameter"},
    )
    hidden = _composite_ir({"one": refs["one"], "hidden": "maya://model/cg_shut/cg_hidden@v1"})
    outsider = w.principal("cg_outsider")
    w.p.models.create(outsider, namespace="quant", name="cg_peek", kind="composite")
    with pytest.raises(PermissionDenied, match="read model"):
        w.p.models.update_draft(outsider, "quant/cg_peek", ir=hidden)
    w.p.models.create(w.mona, namespace="quant", name="cg_peek_owner", kind="composite")
    assert w.p.models.update_draft(w.mona, "quant/cg_peek_owner", ir=hidden), (
        "the member's owner may wrap it"
    )


def test_the_escrowed_holdout_is_fixed_when_the_warrant_is_drawn(journey):  # noqa: F811
    """`holdout: escrowed` (§29.4) recomputed the test partition on every score and never
    hashed it, so the numbers a score was compared against could move. The hash is now
    taken when the warrant is drawn, and scoring refuses if it no longer matches."""
    w = journey
    w.p.models.create(w.mona, namespace="quant", name="cg_score", formula="y = 2*x")
    w.p.models.update_draft(w.mona, "quant/cg_score", spec_latex=complete_spec("cg_score"))
    w.p.models.transition(w.mona, "quant/cg_score", 1, "submit")
    w.p.models.transition(w.mgr, "quant/cg_score", 1, "approve")
    tw = w.p.warrants.create(
        w.devi,
        namespace="quant",
        name="cg_escrow",
        model="quant/cg_score@v1",
        featureset="maya://featureset/quant/panel#q1/2026-02-28",
        spec={"target": "y", "seed": 5},
    )
    assert tw["holdout_hash"] and tw["holdout_rows"] > 0, "escrowed at the moment it was drawn"
    first = w.p.warrants.score_holdout(w.devi, tw["id"])
    assert first["metrics"]["rows"] == tw["holdout_rows"]
    with w.p.uow("admin") as uow:  # the escrowed data moves under the warrant
        uow.repo("training_warrants").update(tw["id"], {"holdout_hash": "0" * 64})
    with pytest.raises(ValidationFailed, match="not the one this warrant was drawn on"):
        w.p.warrants.score_holdout(w.devi, tw["id"])


def test_a_bundle_carries_the_artifact_the_set_definition_and_the_member_pins(journey):  # noqa: F811
    """§18.4: the bundle omitted the uploaded code artifact, the feature-set definition and
    the member pins behind it, so a reader could not say which bytes the frame came from."""
    import io
    import json
    import zipfile

    w = journey
    w.p.models.create(w.mona, namespace="quant", name="cg_bundle", formula="y = 2*x")
    w.p.models.update_draft(w.mona, "quant/cg_bundle", spec_latex=complete_spec("cg_bundle"))
    artifact = (
        "import numpy as np\n\nclass Model:\n    def fit(self, X, y, ctx):\n        return {}\n\n"
        "    def predict(self, X, params, ctx):\n        return [2.0 * v for v in X['x']]\n"
    )
    w.p.models.upload_artifact(w.mona, "quant/cg_bundle", artifact)
    w.drain()
    w.p.models.transition(w.mona, "quant/cg_bundle", 1, "submit")
    w.p.models.transition(w.mgr, "quant/cg_bundle", 1, "approve")
    tw = w.p.warrants.create(
        w.devi,
        namespace="quant",
        name="cg_bundle_tw",
        model="quant/cg_bundle@v1",
        featureset="maya://featureset/quant/panel#q1/2026-02-28",
        spec={"target": "y"},
    )
    exported = w.p.bundles.export(w.devi, tw["id"])
    data = w.p.blobs.get(exported["blob"])
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        names = set(z.namelist())
        assert {"model/artifact.py", "model/artifact_report.json"} <= names
        assert b"class Model" in z.read("model/artifact.py")
        definition = json.loads(z.read("featureset/definition.json"))
        assert definition["name"] == "panel" and definition["effective"]["members"]
        members = json.loads(z.read("featureset/member_pins.json"))
        assert members and all(m["content_hash"] and m["member"] for m in members)
        assert json.loads(z.read("featureset/pin.json"))["pin_name"] == "q1"
    manifest = exported["manifest"]
    for name in ("model/artifact.py", "featureset/definition.json", "featureset/member_pins.json"):
        assert name in manifest["files"], "every added file is hashed in the manifest"


def test_an_execution_warrant_renders_the_manifest_a_person_reads(journey):  # noqa: F811
    """§9.2 asks for the manifest as PDF *and* JSON; only the JSON existed. The PDF is
    rendered from the sealed manifest, and says when it came from the draft renderer."""
    w = journey
    from tests.test_warrants import complete_spec as spec_for

    w.p.models.create(w.mona, namespace="quant", name="mf_model", formula="y = 3*x")
    w.p.models.update_draft(w.mona, "quant/mf_model", spec_latex=spec_for("mf_model"))
    w.p.models.transition(w.mona, "quant/mf_model", 1, "submit")
    w.p.models.transition(w.mgr, "quant/mf_model", 1, "approve")
    ew = w.p.execution.create(
        w.mgr,
        namespace="quant",
        name="mf_live",
        model="quant/mf_model@v1",
        spec={"environments": ["prod"], "limits": {"max_rows_per_day": 1000}, "contact": "desk@x"},
    )
    pdf = w.p.execution.manifest_pdf(w.mgr, ew["id"])
    assert pdf[:4] == b"%PDF", "a real PDF, whichever renderer made it"
    assert len(pdf) > 1000
    with w.p.uow() as uow:
        rendered = uow.repo("audit_events").list(action="warrant.manifest_rendered")
    assert rendered and "draft_render" in rendered[-1]["detail"]
    from maya.services.execution import manifest_latex

    latex = manifest_latex(
        ew, {"name": "quant"}, "maya://warrant/exec/quant/mf_live@v1", "draft", None
    )
    for expected in (
        "Execution manifest",
        "mf\\_model",
        "prod",
        "max\\_rows\\_per\\_day",
        "desk@x",
    ):
        assert expected in latex, expected


def test_the_combiners_own_features_are_part_of_the_contract(journey):  # noqa: F811
    """A combiner is not limited to member outputs (§8.7).

    ``evaluate_composite`` gives the combine expression the same inputs the members got, so
    a router like ``drawn + where(inDraw, a.leq, b.leq) * (commitment - drawn)`` reads three
    features no member mentions. Leaving them out of the composite's declared contract would
    let a warrant be drawn on a feature set that cannot supply them, and the failure would
    surface during evaluation rather than at the contract check — which is the one place §8.2
    promises to catch it."""
    w = journey
    one = _member(w, "cc_one", "yhat = a*x", {"a": "parameter"})
    two = _member(w, "cc_two", "yhat = b*x", {"b": "parameter"})
    ir = {
        "outputs": [{"name": "yhat", "type": "float64"}],
        "inputs": [],
        "composite": {
            "kind": "router",
            "members": [{"alias": "one", "ref": one}, {"alias": "two", "ref": two}],
            "combine": {
                "op": "add",
                "args": [
                    {"ref": "gate"},
                    {
                        "op": "where",
                        "args": [{"ref": "gate"}, {"ref": "one.yhat"}, {"ref": "two.yhat"}],
                    },
                ],
            },
        },
    }
    w.p.models.create(w.mona, namespace="quant", name="cc_router", kind="composite")
    w.p.models.update_draft(w.mona, "quant/cc_router", ir=ir, spec_latex=complete_spec("cc_router"))
    contract = w.p.models.get(w.mona, "quant/cc_router")["versions"][0]["input_contract"]
    by_name = {c["name"]: c for c in contract}
    assert set(by_name) == {"x", "gate"}, "the members want x; only the combiner wants gate"
    assert by_name["gate"]["needed_by"] == ["combine"]
    assert by_name["x"]["needed_by"] == ["one", "two"]
    # a member output is produced, not supplied, so it is not an input
    assert "one.yhat" not in by_name
    assert comp.combiner_features(ir["composite"]["combine"]) == {"gate"}


def test_the_combiners_own_parameters_are_declared_and_owed(journey):  # noqa: F811
    """A composite can be more than a product of its members.

    The weight in a blend, the threshold in a router, the horizon multiple in an impairment
    model: those are numbers somebody has to decide, they belong to no member, and undeclared
    they were checked by nothing — the bounds check had nothing to look for and the warrant
    sealed with the most argued-over figures in the model unapproved. They are part of the
    composite's contract now, and the seal waits for them.
    """
    w = journey
    one = _member(w, "cp_one", "yhat = a*x", {"a": "parameter"})
    two = _member(w, "cp_two", "yhat = b*x", {"b": "parameter"})
    ir = {
        "outputs": [{"name": "yhat", "type": "float64"}],
        "inputs": [],
        "composite": {
            "kind": "ensemble",
            "members": [{"alias": "one", "ref": one}, {"alias": "two", "ref": two}],
            "combine": {
                "op": "add",
                "args": [
                    {"op": "mul", "args": [{"param": "weight"}, {"ref": "one.yhat"}]},
                    {"ref": "two.yhat"},
                ],
            },
        },
    }
    w.p.models.create(w.mona, namespace="quant", name="cp_blend", kind="composite")
    w.p.models.update_draft(w.mona, "quant/cp_blend", ir=ir, spec_latex=complete_spec("cp_blend"))
    contract = w.p.models.get(w.mona, "quant/cp_blend")["versions"][0]["input_contract"]
    by_name = {c["name"]: c for c in contract}
    assert by_name["weight"]["role"] == "parameter" and by_name["weight"]["needed_by"] == [
        "combine"
    ]
    assert by_name["x"]["role"] == "feature", "the members' inputs are still features"
    assert comp.combiner_parameters(ir["composite"]["combine"]) == {"weight"}

    w.p.models.transition(w.mona, "quant/cp_blend", 1, "submit")
    w.p.models.transition(w.mgr, "quant/cp_blend", 1, "approve")
    tw = w.p.warrants.create(
        w.devi,
        namespace="quant",
        name="cp_calib",
        model="quant/cp_blend@v1",
        featureset="maya://featureset/quant/panel#q1/2026-02-28",
        spec={"target": "y", "seed": 3},
    )
    checksum = w.p.warrants.data(w.devi, tw["id"])["manifest"]["checksum"]
    for alias, values in (("one", {"a": 2.0}), ("two", {"b": 0.5})):
        ps = w.p.warrants.upload_parameters(
            w.devi, tw["id"], values=values, data_checksum=checksum, member_alias=alias
        )
        w.p.warrants.parameter_transition(w.devi, ps["id"], "submit")
        w.p.warrants.parameter_transition(w.mgr, ps["id"], "approve")
    w.p.warrants.transition(w.devi, tw["id"], "submit")
    w.p.warrants.transition(w.mgr, tw["id"], "approve")
    with pytest.raises(NotApproved, match="the combiner's own parameters"):
        w.p.warrants.seal(w.mgr, tw["id"])
    own = w.p.warrants.upload_parameters(
        w.devi, tw["id"], values={"weight": 0.4}, data_checksum=checksum
    )
    assert own["member_alias"] is None, "the combiner's set belongs to no member"
    w.p.warrants.parameter_transition(w.devi, own["id"], "submit")
    w.p.warrants.parameter_transition(w.mgr, own["id"], "approve")
    assert w.p.warrants.seal(w.mgr, tw["id"])["sealed_at"] is not None


def test_deprecating_a_version_moves_its_maturity_down_the_ladder(journey):  # noqa: F811
    """§8.6's maturity ladder ends in `deprecated` and `retired`, and nothing reached them.

    `maturity` is only settable through `update_draft`, which requires an editable draft, so
    an approved version could never be moved down the ladder at all: the `deprecate` and
    `retire` transitions moved the workflow *state* and left the maturity at `candidate`. A
    deprecated version went on advertising itself as a candidate, and — because §8.7's cap
    reads a member's maturity rather than its state — a composite went on treating a
    deprecated member as a usable one, which is the opposite of "deprecating a member warns
    every composite that contains it"."""
    w = journey
    stale = _member(w, "cg_stale", "yhat = e*x", {"e": "parameter"})
    fresh = _member(w, "cg_fresh", "yhat = f*x", {"f": "parameter"})
    w.p.models.create(w.mona, namespace="quant", name="cg_over_stale", kind="composite")
    w.p.models.update_draft(
        w.mona,
        "quant/cg_over_stale",
        ir=_composite_ir({"stale": stale, "fresh": fresh}),
        spec_latex=complete_spec("cg_over_stale"),
    )

    def maturity(name: str) -> str:
        return str(w.p.models.get(w.mona, f"quant/{name}")["versions"][0]["maturity"])

    assert maturity("cg_stale") == "candidate", "approval promotes experimental to candidate"
    w.p.models.transition(
        w.mgr, "quant/cg_stale", 1, "deprecate", successor="maya://model/quant/cg_stale@v2"
    )
    assert maturity("cg_stale") == "deprecated"
    with w.p.uow("admin") as uow:
        ir = w.p.models.get(w.mona, "quant/cg_over_stale")["versions"][0]["formula_ir"]
        cap = comp.capped_maturity(w.p.models._member_maturities(uow, ir))
    assert cap == "deprecated", "a composite cannot claim more maturity than a deprecated member"
    with pytest.raises(ValidationFailed, match=r"capped at its lowest member's \('deprecated'\)"):
        w.p.models.update_draft(w.mona, "quant/cg_over_stale", maturity="candidate")
    w.p.models.transition(w.admin, "quant/cg_stale", 1, "retire")
    assert maturity("cg_stale") == "retired"


def test_a_version_still_serving_production_cannot_be_retired(journey):  # noqa: F811
    """Retirement is an administrative end of life, not an outage (§8.6, §9.4).

    Unguarded it was neither: a version could be retired while a sealed execution warrant went
    on serving it, so production ran a retired model and nothing said so. Taking a model out of
    service *now* is revocation, a different and deliberate act, and the order matters. A
    training warrant does not block — it is a record, its seal exists to keep the fit
    reproducible, and withdrawing that would destroy the thing the seal is for — so its owner is
    warned instead.
    """
    w = journey
    w.p.models.create(
        w.mona,
        namespace="quant",
        name="rt_model",
        formula="yhat = g*x",
        roles={"g": "parameter"},
    )
    w.p.models.update_draft(w.mona, "quant/rt_model", spec_latex=complete_spec("rt_model"))
    w.p.models.transition(w.mona, "quant/rt_model", 1, "submit")
    w.p.models.transition(w.mgr, "quant/rt_model", 1, "approve")
    tw = w.p.warrants.create(
        w.devi,
        namespace="quant",
        name="rt_fit",
        model="quant/rt_model@v1",
        featureset="maya://featureset/quant/panel#q1/2026-02-28",
        spec={"target": "y", "seed": 2},
    )
    data = w.p.warrants.data(w.devi, tw["id"])
    ps = w.p.warrants.upload_parameters(
        w.devi, tw["id"], values={"g": 1.5}, data_checksum=data["manifest"]["checksum"]
    )
    w.p.warrants.parameter_transition(w.devi, ps["id"], "submit")
    w.p.warrants.parameter_transition(w.mgr, ps["id"], "approve")
    ew = w.p.execution.create(
        w.mgr,
        namespace="quant",
        name="rt_live",
        training_warrant_id=tw["id"],
        parameter_set_id=ps["id"],
        spec={"environments": ["dev"], "contact": "risk@example.com"},
    )
    w.p.execution.transition(w.mgr, ew["id"], "submit")
    w.p.execution.transition(w.principal("mgr2"), ew["id"], "approve")
    w.p.execution.seal(w.mgr, ew["id"])
    assert w.p.execution.bundle(w.devi, ew["id"], "dev")["status"] == "live"

    w.p.models.transition(
        w.mgr, "quant/rt_model", 1, "deprecate", successor="none: the book was sold"
    )
    with pytest.raises(NotApproved, match="quant/rt_live.*revoke the warrant first"):
        w.p.models.transition(w.admin, "quant/rt_model", 1, "retire")

    w.p.execution.revoke(w.admin, ew["id"], "the book was sold; the model is out of service")
    assert w.p.models.transition(w.admin, "quant/rt_model", 1, "retire")["state"] == "retired"
    # and the training warrant's owner was told, both times, without losing the warrant
    told = [n for n in w.p.access.inbox(w.devi) if "rt_model@v1" in (n["object_ref"] or "")]
    assert {n["kind"] for n in told} == {"deprecation", "retirement"}
    assert w.p.warrants.get(w.devi, tw["id"])["sealed_at"] is None, "sealing was never claimed"
    assert (
        w.p.warrants.data(w.devi, tw["id"])["manifest"]["checksum"]
        == (data["manifest"]["checksum"])
    ), "a retired version's warrant is still reproducible"
