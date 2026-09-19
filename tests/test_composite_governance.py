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
