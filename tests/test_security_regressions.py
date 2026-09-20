"""
Regression tests for the security faults the hardening pass found, plus tables
for covenants and execution limits.

* Server-side bundle verification used to run the ``verify.py`` inside the
  uploaded zip — and the code it carried — for any signed-in user. It now
  executes nothing unless the bundle is signed by this instance and every file
  matches its signed hash; each way of failing that is refused without running
  a line of the bundle's code.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import hashlib
import io
import json
import zipfile

import pytest

from maya.core.crypto import Signer
from maya.core.errors import ValidationFailed
from maya.services.execution import evaluate_covenants, over_limits
from tests.conftest import build_platform
from tests.test_warrants import complete_spec, journey  # noqa: F401 - the fixture, reused

EVIL = "import pathlib\npathlib.Path('{marker}').write_text('pwned')\n"


@pytest.fixture(scope="module")
def platform():
    p = build_platform()
    yield p
    p.shutdown()


def _bundle(
    signer,
    files: dict[str, bytes],
    *,
    tamper: str | None = None,
    extra: dict[str, bytes] | None = None,
    bad_sig: bool = False,
) -> bytes:
    listing = {k: hashlib.sha256(v).hexdigest() for k, v in sorted(files.items())}
    body = json.dumps(listing, sort_keys=True, separators=(",", ":")).encode()
    sig = signer.signature_block(body)
    if bad_sig:
        sig = {**sig, "signature": sig["signature"][::-1]}
    manifest = {"files": listing, "signature": sig, "data_content_hash": "x", "reexecutable": False}
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        z.writestr("manifest.json", json.dumps(manifest))
        for name, data in {**files, **(extra or {})}.items():
            if name == tamper:
                data = data + b"# changed\n"
            z.writestr(name, data)
    return out.getvalue()


@pytest.mark.parametrize(
    "case", ["foreign key", "bad signature", "altered file", "missing file", "extra file"]
)
def test_the_server_never_executes_an_untrusted_bundle(platform, tmp_path, case):
    marker = tmp_path / "pwned.txt"
    files = {
        "verify.py": EVIL.format(marker=marker).encode(),
        "lib/canonical.py": EVIL.format(marker=marker).encode(),
    }
    signer = Signer(tmp_path / "other-keys") if case == "foreign key" else platform.signer
    kwargs = {
        "bad signature": {"bad_sig": True},
        "altered file": {"tamper": "verify.py"},
        "extra file": {"extra": {"lib/extra.py": EVIL.format(marker=marker).encode()}},
    }.get(case, {})
    data = _bundle(signer, files, **kwargs)
    if case == "missing file":
        buf = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(data)) as src, zipfile.ZipFile(buf, "w") as dst:
            for item in src.infolist():
                if item.filename != "lib/canonical.py":
                    dst.writestr(item, src.read(item))
        data = buf.getvalue()
    report = platform.bundles.verify(data)
    assert report["verified"] is False and report["executed"] is False, report
    assert "not executed on the server" in report["checks"][0]["detail"]
    assert not marker.exists(), "the bundle's code ran on the server"


def test_a_trusted_bundle_runs_mayas_own_verifier_not_the_uploaded_one(platform, tmp_path):
    marker = tmp_path / "pwned.txt"
    files = {"verify.py": EVIL.format(marker=marker).encode()}
    report = platform.bundles.verify(_bundle(platform.signer, files))
    assert report["executed"] is True and not marker.exists()


@pytest.mark.parametrize("data", [b"not a zip", b"PK\x03\x04garbage"])
def test_a_non_bundle_is_refused_by_name(platform, data):
    with pytest.raises(ValidationFailed, match="Not a MAYA bundle"):
        platform.bundles.verify(data)


def test_a_zip_without_a_manifest_is_refused(platform):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("verify.py", "print('hi')")
    with pytest.raises(ValidationFailed, match="Not a MAYA bundle"):
        platform.bundles.verify(buf.getvalue())


def test_offline_verification_is_explicit_and_needs_a_verifier():
    from maya.services.bundle import BundleService

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("manifest.json", "{}")
    with pytest.raises(ValidationFailed, match="Not a MAYA bundle"):
        BundleService.verify_offline(buf.getvalue())


# --------------------------------------------------------------------- covenants
@pytest.mark.parametrize(
    "covenant,rows,inputs,outputs,today,breached",
    [
        (
            {"kind": "input_null_rate", "attr": "x", "max": 0.1},
            10,
            {"x": {"null_rate": 0.05}},
            {},
            10,
            False,
        ),
        (
            {"kind": "input_null_rate", "attr": "x", "max": 0.1},
            10,
            {"x": {"null_rate": 0.2}},
            {},
            10,
            True,
        ),
        (
            {"kind": "input_range", "attr": "x", "min": 0, "max": 5},
            1,
            {"x": {"min": 1, "max": 4}},
            {},
            1,
            False,
        ),
        (
            {"kind": "input_range", "attr": "x", "min": 0},
            1,
            {"x": {"min": -1, "max": 4}},
            {},
            1,
            True,
        ),
        (
            {"kind": "input_range", "attr": "x", "max": 5},
            1,
            {"x": {"min": 1, "max": 6}},
            {},
            1,
            True,
        ),
        (
            {"kind": "output_range", "attr": "y", "max": 1},
            1,
            {},
            {"y": {"min": 0, "max": 1}},
            1,
            False,
        ),
        (
            {"kind": "output_range", "attr": "y", "max": 1},
            1,
            {},
            {"y": {"min": 0, "max": 2}},
            1,
            True,
        ),
        ({"kind": "max_rows_per_day", "max": 100}, 10, {}, {}, 100, False),
        ({"kind": "max_rows_per_day", "max": 100}, 10, {}, {}, 101, True),
        (
            {"kind": "staleness_days", "attr": "x", "max": 3},
            1,
            {"x": {"age_days": 3}},
            {},
            1,
            False,
        ),
        ({"kind": "staleness_days", "attr": "x", "max": 3}, 1, {"x": {"age_days": 4}}, {}, 1, True),
        ({"kind": "input_null_rate", "attr": "x", "max": 0.1}, 10, {}, {}, 10, False),
    ],
)
def test_each_covenant(covenant, rows, inputs, outputs, today, breached):
    out = evaluate_covenants([covenant], rows, inputs, outputs, rows_today=today)
    assert bool(out) is breached, out
    if breached:
        assert out[0]["kind"] == covenant["kind"] and out[0]["detail"]


@pytest.mark.parametrize(
    "limits,rows,used,exceeded",
    [
        ({}, 10**9, {"calls": 10**6, "rows": 10**12}, []),
        ({"max_rows_per_call": 100}, 100, {"calls": 0, "rows": 0}, []),
        ({"max_rows_per_call": 100}, 101, {"calls": 0, "rows": 0}, ["max_rows_per_call"]),
        ({"max_rows_per_day": 1000}, 10, {"calls": 3, "rows": 990}, []),
        ({"max_rows_per_day": 1000}, 11, {"calls": 3, "rows": 990}, ["max_rows_per_day"]),
        ({"max_calls_per_day": 3}, 1, {"calls": 2, "rows": 0}, []),
        ({"max_calls_per_day": 3}, 1, {"calls": 3, "rows": 0}, ["max_calls_per_day"]),
        (
            {"max_calls_per_day": 1, "max_rows_per_call": 1},
            5,
            {"calls": 1, "rows": 0},
            ["max_calls_per_day", "max_rows_per_call"],
        ),
    ],
)
def test_execution_limits(limits, rows, used, exceeded):
    assert sorted(x["limit"] for x in over_limits(limits, rows, used)) == sorted(exceeded)


# -- the PSI covenant (§29.5), which the specification asked for and nothing built --------


def test_psi_is_zero_for_the_same_population_and_grows_as_it_moves():
    from maya.services.execution import psi

    same = [10, 20, 30, 20, 10]
    assert psi(same, same) == pytest.approx(0.0)
    shifted = [30, 25, 20, 15, 5]
    moved = psi(shifted, same)
    assert moved > 0
    gone = psi([0, 0, 0, 10, 80], same)
    assert gone > moved, "a population that has left its bins scores higher"
    assert psi([100, 0, 0, 0, 0], same) < 100, "an empty bin is smoothed, not infinite"
    with pytest.raises(ValidationFailed, match="same bins"):
        psi([1, 2], [1, 2, 3])


def test_a_psi_covenant_breaches_when_the_inputs_have_moved():
    from maya.services.execution import evaluate_covenants

    covenant = {"kind": "input_psi", "attr": "x", "max": 0.2, "baseline": [25, 25, 25, 25]}
    steady = {"x": {"histogram": [24, 26, 25, 25]}}
    assert evaluate_covenants([covenant], 10, steady, {}, rows_today=10) == []
    moved = {"x": {"histogram": [90, 5, 3, 2]}}
    breach = evaluate_covenants([covenant], 10, moved, {}, rows_today=10)
    assert breach and "population stability index" in breach[0]["detail"]
    nothing_reported = {"x": {"null_rate": 0.0}}
    assert evaluate_covenants([covenant], 10, nothing_reported, {}, rows_today=10) == []


def test_a_psi_baseline_is_taken_from_the_data_the_warrant_was_drawn_on(journey):  # noqa: F811
    """A covenant that declares no baseline gets the training population's, fixed at
    creation. Without a training warrant there is no baseline, and MAYA says so."""
    from maya.core.errors import ValidationFailed as VF

    w = journey
    w.p.models.create(w.mona, namespace="quant", name="psi_model", formula="yhat = 2*x")
    w.p.models.update_draft(w.mona, "quant/psi_model", spec_latex=complete_spec("psi_model"))
    w.p.models.transition(w.mona, "quant/psi_model", 1, "submit")
    w.p.models.transition(w.mgr, "quant/psi_model", 1, "approve")
    tw = w.p.warrants.create(
        w.devi,
        namespace="quant",
        name="psi_tw",
        model="quant/psi_model@v1",
        featureset="maya://featureset/quant/panel#q1/2026-02-28",
        spec={"target": "y"},
    )
    ew = w.p.execution.create(
        w.mgr,
        namespace="quant",
        name="psi_live",
        training_warrant_id=tw["id"],
        spec={"covenants": [{"kind": "input_psi", "attr": "x"}]},
    )
    covenant = ew["spec"]["covenants"][0]
    assert covenant["baseline"] and covenant["bin_edges"], covenant
    assert sum(covenant["baseline"]) > 0 and covenant["max"] == 0.25
    with pytest.raises(VF, match="needs a baseline"):
        w.p.execution.create(
            w.mgr,
            namespace="quant",
            name="psi_nobase",
            model="quant/psi_model@v1",
            spec={"covenants": [{"kind": "input_psi", "attr": "x"}]},
        )
    with pytest.raises(VF, match="names the attribute"):
        w.p.execution.create(
            w.mgr,
            namespace="quant",
            name="psi_noattr",
            training_warrant_id=tw["id"],
            spec={"covenants": [{"kind": "input_psi"}]},
        )


def test_a_covenant_that_names_no_attribute_is_filled_in_or_refused(journey):  # noqa: F811
    """A covenant is compared against the statistics reported for the attribute it names, so
    one that names nothing is compared against nothing and can never breach — which is worse
    than no covenant, because it appears on the warrant and in the manifest and controls
    nothing. A model with one output has one candidate and MAYA fills it in; an input
    covenant has no such default and is refused."""
    w = journey
    w.p.models.create(
        w.mona,
        namespace="quant",
        name="cov_model",
        formula="yhat = a*x + b",
        roles={"a": "parameter", "b": "parameter"},
    )
    w.p.models.update_draft(w.mona, "quant/cov_model", spec_latex=complete_spec("cov_model"))
    w.p.models.transition(w.mona, "quant/cov_model", 1, "submit")
    w.p.models.transition(w.mgr, "quant/cov_model", 1, "approve")
    tw = w.p.warrants.create(
        w.devi,
        namespace="quant",
        name="cov_named",
        model="quant/cov_model@v1",
        featureset="maya://featureset/quant/panel#q1/2026-02-28",
        spec={"target": "y", "seed": 5},
    )
    data = w.p.warrants.data(w.devi, tw["id"])
    good = w.p.warrants.upload_parameters(
        w.devi, tw["id"], values={"a": 2.0, "b": 0.5}, data_checksum=data["manifest"]["checksum"]
    )
    w.p.warrants.parameter_transition(w.devi, good["id"], "submit")
    w.p.warrants.parameter_transition(w.mgr, good["id"], "approve")
    ew = w.p.execution.create(
        w.mgr,
        namespace="quant",
        name="cov_live",
        training_warrant_id=tw["id"],
        parameter_set_id=good["id"],
        spec={
            "environments": ["dev"],
            "contact": "risk@example.com",
            "covenants": [{"kind": "output_range", "min": 0.0}],
        },
    )
    covenant = ew["spec"]["covenants"][0]
    assert covenant["attr"] == "yhat", "the model declares one output, so MAYA named it"
    w.p.execution.transition(w.mgr, ew["id"], "submit")
    w.p.execution.transition(w.principal("mgr2"), ew["id"], "approve")
    w.p.execution.seal(w.mgr, ew["id"])
    breached = w.p.execution.report(
        w.devi,
        ew["id"],
        environment="dev",
        rows=10,
        input_stats={},
        output_stats={"yhat": {"min": -3.0}},
    )
    assert breached["status"] == "suspended", "and having been named, it can actually breach"

    for kind in ("input_range", "input_null_rate"):
        with pytest.raises(ValidationFailed, match="names the attribute it watches"):
            w.p.execution.create(
                w.mgr,
                namespace="quant",
                name=f"cov_{kind}",
                training_warrant_id=tw["id"],
                parameter_set_id=good["id"],
                spec={"environments": ["dev"], "covenants": [{"kind": kind, "max": 1}]},
            )
