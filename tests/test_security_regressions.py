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

EVIL = "import pathlib\npathlib.Path('{marker}').write_text('pwned')\n"


@pytest.fixture(scope="module")
def platform():
    p = build_platform()
    yield p
    p.shutdown()


def _bundle(signer, files: dict[str, bytes], *, tamper: str | None = None,
            extra: dict[str, bytes] | None = None, bad_sig: bool = False) -> bytes:
    listing = {k: hashlib.sha256(v).hexdigest() for k, v in sorted(files.items())}
    body = json.dumps(listing, sort_keys=True, separators=(",", ":")).encode()
    sig = signer.signature_block(body)
    if bad_sig:
        sig = {**sig, "signature": sig["signature"][::-1]}
    manifest = {"files": listing, "signature": sig, "data_content_hash": "x",
                "reexecutable": False}
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        z.writestr("manifest.json", json.dumps(manifest))
        for name, data in {**files, **(extra or {})}.items():
            if name == tamper:
                data = data + b"# changed\n"
            z.writestr(name, data)
    return out.getvalue()


@pytest.mark.parametrize("case", ["foreign key", "bad signature", "altered file",
                                  "missing file", "extra file"])
def test_the_server_never_executes_an_untrusted_bundle(platform, tmp_path, case):
    marker = tmp_path / "pwned.txt"
    files = {"verify.py": EVIL.format(marker=marker).encode(),
             "lib/canonical.py": EVIL.format(marker=marker).encode()}
    signer = Signer(tmp_path / "other-keys") if case == "foreign key" else platform.signer
    kwargs = {"bad signature": {"bad_sig": True}, "altered file": {"tamper": "verify.py"},
              "extra file": {"extra": {"lib/extra.py": EVIL.format(marker=marker).encode()}}
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
@pytest.mark.parametrize("covenant,rows,inputs,outputs,today,breached", [
    ({"kind": "input_null_rate", "attr": "x", "max": 0.1}, 10, {"x": {"null_rate": 0.05}}, {}, 10,
     False),
    ({"kind": "input_null_rate", "attr": "x", "max": 0.1}, 10, {"x": {"null_rate": 0.2}}, {}, 10,
     True),
    ({"kind": "input_range", "attr": "x", "min": 0, "max": 5}, 1, {"x": {"min": 1, "max": 4}},
     {}, 1, False),
    ({"kind": "input_range", "attr": "x", "min": 0}, 1, {"x": {"min": -1, "max": 4}}, {}, 1,
     True),
    ({"kind": "input_range", "attr": "x", "max": 5}, 1, {"x": {"min": 1, "max": 6}}, {}, 1, True),
    ({"kind": "output_range", "attr": "y", "max": 1}, 1, {}, {"y": {"min": 0, "max": 1}}, 1,
     False),
    ({"kind": "output_range", "attr": "y", "max": 1}, 1, {}, {"y": {"min": 0, "max": 2}}, 1,
     True),
    ({"kind": "max_rows_per_day", "max": 100}, 10, {}, {}, 100, False),
    ({"kind": "max_rows_per_day", "max": 100}, 10, {}, {}, 101, True),
    ({"kind": "staleness_days", "attr": "x", "max": 3}, 1, {"x": {"age_days": 3}}, {}, 1, False),
    ({"kind": "staleness_days", "attr": "x", "max": 3}, 1, {"x": {"age_days": 4}}, {}, 1, True),
    ({"kind": "input_null_rate", "attr": "x", "max": 0.1}, 10, {}, {}, 10, False),
])
def test_each_covenant(covenant, rows, inputs, outputs, today, breached):
    out = evaluate_covenants([covenant], rows, inputs, outputs, rows_today=today)
    assert bool(out) is breached, out
    if breached:
        assert out[0]["kind"] == covenant["kind"] and out[0]["detail"]


@pytest.mark.parametrize("limits,rows,used,exceeded", [
    ({}, 10**9, {"calls": 10**6, "rows": 10**12}, []),
    ({"max_rows_per_call": 100}, 100, {"calls": 0, "rows": 0}, []),
    ({"max_rows_per_call": 100}, 101, {"calls": 0, "rows": 0}, ["max_rows_per_call"]),
    ({"max_rows_per_day": 1000}, 10, {"calls": 3, "rows": 990}, []),
    ({"max_rows_per_day": 1000}, 11, {"calls": 3, "rows": 990}, ["max_rows_per_day"]),
    ({"max_calls_per_day": 3}, 1, {"calls": 2, "rows": 0}, []),
    ({"max_calls_per_day": 3}, 1, {"calls": 3, "rows": 0}, ["max_calls_per_day"]),
    ({"max_calls_per_day": 1, "max_rows_per_call": 1}, 5, {"calls": 1, "rows": 0},
     ["max_calls_per_day", "max_rows_per_call"]),
])
def test_execution_limits(limits, rows, used, exceeded):
    assert sorted(x["limit"] for x in over_limits(limits, rows, used)) == sorted(exceeded)
