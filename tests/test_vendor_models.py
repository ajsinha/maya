"""
Vendor models under the same wrapper (§29.10): a bought black box is registered as a
model of kind ``vendor`` with a declared input contract, the vendor's name, product,
version and documentation recorded; it passes the same review; its warrants behave
exactly as an internal model's — contract validation naming every missing input, the
leakage certificate, the download checksum, sealing — and what MAYA cannot verify is
*marked* unverifiable (the bundle says it cannot re-execute, scoring refuses by name)
rather than silently omitted.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import datetime as dt

import pytest

from maya.core.errors import ContractMismatch, NotApproved, ValidationFailed
from tests.conftest import PASSWORD
from tests.test_warrants import XY_DEF, complete_spec, xy_csv

VENDOR = {
    "name": "Acme Analytics",
    "product": "AcmeScore",
    "version": "7.2.1",
    "documentation": "AcmeScore 7.2 model card, section 4: inputs x and y, daily.",
}


def _black_box(*inputs: str, estimates: str = "a credit score from two ratios") -> dict:
    return {
        "inputs": [{"name": n, "type": "float64"} for n in inputs],
        "outputs": [{"name": "score"}],
        "black_box": {
            "estimates": estimates,
            "architecture": "closed gradient-boosted ensemble, vendor-hosted",
        },
    }


@pytest.fixture(scope="module")
def vendor_world(world):
    w = world
    w.p.access.create_namespace(w.admin, name="bought", preset="standard")
    w.p.features.create(w.dana, namespace="bought", name="xy", definition=XY_DEF)
    w.p.features.ingest(w.dana, "bought/xy", xy_csv(30), fmt="csv")
    w.p.features.transition(w.dana, "bought/xy", 1, "submit")
    w.p.features.transition(w.mick, "bought/xy", 1, "approve")
    fs_def = {
        "index": ["date", "symbol"],
        "members": [
            {"attr": "x", "ref": "maya://feature/bought/xy@v1", "source_attr": "x"},
            {"attr": "y", "ref": "maya://feature/bought/xy@v1", "source_attr": "y"},
        ],
    }
    w.p.featuresets.create(w.devi, namespace="bought", name="inputs", definition=fs_def)
    w.p.featuresets.transition(w.devi, "bought/inputs", 1, "submit")
    w.p.featuresets.transition(w.mick, "bought/inputs", 1, "approve")
    w.p.featuresets.pin(
        w.mick,
        "bought/inputs",
        version_no=1,
        pin_name="m1",
        as_of=dt.date(2026, 1, 30),
        cascade=True,
    )
    w.drain()
    w.p.models.create(
        w.mona,
        namespace="bought",
        name="acme",
        kind="vendor",
        ir=_black_box("x", "y"),
        vendor=VENDOR,
        description="AcmeScore as licensed",
    )
    w.p.models.update_draft(w.mona, "bought/acme", spec_latex=complete_spec("acme"))
    return w


def test_a_vendor_model_records_its_vendor_and_contract(vendor_world):
    w = vendor_world
    model = w.p.models.get(w.mona, "bought/acme")
    assert model["kind"] == "vendor" and model["vendor"] == VENDOR
    v = model["versions"][0]
    assert v["opaque"] is True
    assert [c["name"] for c in v["input_contract"]] == ["x", "y"]
    assert w.p.models.list(w.mona, q="acme")[0]["opaque"] is True
    with pytest.raises(ValidationFailed, match="kind must be one of"):
        w.p.models.create(w.mona, namespace="bought", name="nope", kind="vendr", ir=_black_box("x"))


def test_a_vendor_model_goes_through_the_same_review(vendor_world):
    w = vendor_world
    w.p.models.create(
        w.mona,
        namespace="bought",
        name="vague",
        kind="vendor",
        ir=_black_box("x", estimates=" "),
        vendor=VENDOR,
    )
    w.p.models.update_draft(w.mona, "bought/vague", spec_latex=complete_spec("vague"))
    with pytest.raises(NotApproved, match="estimates"):
        w.p.models.transition(w.mona, "bought/vague", 1, "submit")
    assert w.p.models.transition(w.mona, "bought/acme", 1, "submit")["state"] == "in_review"
    assert w.p.models.transition(w.mgr, "bought/acme", 1, "approve")["state"] == "approved"


def test_vendor_warrants_behave_as_internal_ones(vendor_world):
    w = vendor_world
    pin = "maya://featureset/bought/inputs#m1/2026-01-30"
    w.p.models.create(
        w.mona,
        namespace="bought",
        name="acme_z",
        kind="vendor",
        ir=_black_box("x", "z", "q"),
        vendor=VENDOR,
    )
    w.p.models.update_draft(w.mona, "bought/acme_z", spec_latex=complete_spec("acme_z"))
    w.p.models.transition(w.mona, "bought/acme_z", 1, "submit")
    w.p.models.transition(w.mgr, "bought/acme_z", 1, "approve")
    with pytest.raises(ContractMismatch) as exc:
        w.p.warrants.create(
            w.devi,
            namespace="bought",
            name="bad",
            model="bought/acme_z@v1",
            featureset=pin,
            spec={},
        )
    assert "'z'" in exc.value.message and "'q'" in exc.value.message

    tw = w.p.warrants.create(
        w.devi,
        namespace="bought",
        name="acme_run",
        model="bought/acme@v1",
        featureset=pin,
        spec={"seed": 3, "target": "y"},
    )
    assert tw["contract_report"]["ok"] and tw["leakage_certificate"]["status"] == "certified"
    data = w.p.warrants.data(w.devi, tw["id"])
    assert data["manifest"]["rows"] > 0 and len(data["manifest"]["checksum"]) == 64
    with pytest.raises(ValidationFailed, match="black box cannot be scored"):
        w.p.warrants.score_holdout(w.devi, tw["id"])
    w.p.warrants.transition(w.devi, tw["id"], "submit")
    w.p.warrants.transition(w.mgr, tw["id"], "approve")
    # nothing to train, so no parameter set is required to seal
    assert w.p.warrants.seal(w.mgr, tw["id"])["sealed_at"] is not None

    exported = w.p.bundles.export(w.devi, tw["id"])
    manifest = exported["manifest"]
    assert manifest["reexecutable"] is False and manifest["output_hash"] is None
    assert "declared black box" in manifest["not_reexecutable_reason"]
    report = w.p.bundles.verify(w.p.blobs.get(exported["blob"]))
    assert report["verified"] is True
    reexec = next(c for c in report["checks"] if c["check"] == "re-execution")
    assert reexec["ok"] is None and "black box" in reexec["detail"]


def test_a_vendor_model_over_the_sdk(vendor_world):
    from maya.api.app import create_api
    from maya.sdk import Client

    w = vendor_world
    app = create_api(w.p)
    token = Client(app=app).auth.login("mona", PASSWORD)["token"]
    sdk = Client(app=app, token=token)
    sdk.models.create(
        "bought",
        "acme_sdk",
        kind="vendor",
        ir=_black_box("x"),
        vendor={**VENDOR, "version": "8.0.0"},
    )
    shown = sdk.models.get("bought/acme_sdk")
    assert shown["kind"] == "vendor" and shown["vendor"]["version"] == "8.0.0"
    assert shown["versions"][0]["opaque"] is True
