"""The gate ladder's single entry point (plan §7). Never a remembered list.

    python tools/ci/gates.py              # the fast static gates
    python tools/ci/gates.py --tests      # … then the full suite, failing under 90% coverage
    python tools/ci/gates.py --fallback   # … then the suite with every seam on its fallback
    python tools/ci/gates.py --security   # … then the dependency scan and sandbox escapes
    python tools/ci/gates.py --bench      # … then no benchmark regression over 10%

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
GATES = [
    "lint.py",
    "typecheck.py",
    "file_size.py",
    "import_boundaries.py",
    "cycle_check.py",
    "module_symbols.py",
    "seam_imports.py",
    "public_symbols.py",
    "version_single_source.py",
    "no_secrets.py",
    "table_contract.py",
    "contrast.py",
    "sdk_parity.py",
    "ui_parity.py",
    "api_snapshot.py",
    "protocol_literals.py",
    "sast.py",
]

# Gate 11b, the fallback matrix: every Type A seam pinned to its fallback, so each
# fallback is exercised by the whole suite, not just by the preferred backend's absence.
# (pg_driver's fallback, pg8000, applies to PostgreSQL runs only.)
FALLBACKS = {
    "lake": "pure",
    "json": "stdlib",
    "frames": "pandas",
    "pushdown": "maya",
    "compress": "zlib",
    "tzdb": "tzdata",
    "procstat": "os",
    "kdf": "scrypt",
    "typeset": "draft",
    "event_loop": "asyncio",
    "tracing": "ids",
}


ROOT = HERE.parents[1]


def _run(cmd: list[str], env: dict[str, str] | None = None) -> bool:
    import os

    return subprocess.call(cmd, cwd=ROOT, env={**os.environ, **(env or {})}) == 0


def _suite() -> list[tuple[str, list[str], dict[str, str]]]:
    # the full suite, under a coverage floor: a change that drops below it fails here
    return [
        (
            "pytest",
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "--cov=maya",
                "--cov=maya_delta",
                "--cov-report=term:skip-covered",
                "--cov-fail-under=90",
            ],
            # the full stage also runs every case study end to end (tests/test_case_studies)
            {"MAYA_TEST_CASE_STUDIES": "1"},
        )
    ]


def _fallback() -> list[tuple[str, list[str], dict[str, str]]]:
    pins = " ".join(f"--seams.{k}={v}" for k, v in FALLBACKS.items()) + " --lake.backend=pure"
    return [
        (
            "pytest (fallback matrix)",
            [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"],
            {"MAYA_TEST_EXTRA_ARGV": pins},
        )
    ]


def _security() -> list[tuple[str, list[str], dict[str, str]]]:
    # gate 25: known-vulnerable dependencies (needs the network), and the jail's escape
    # attempts (Linux strong tier; skipped where bubblewrap is absent)
    return [
        (
            "pip-audit",
            [
                sys.executable,
                "-m",
                "pip_audit",
                "-r",
                "requirements.txt",
                "--progress-spinner",
                "off",
            ],
            {},
        ),
        (
            "sandbox escapes",
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "-p",
                "no:cacheprovider",
                "tests/test_sandbox_linux.py",
                "tests/test_sandbox.py",
            ],
            {},
        ),
    ]


def _bench() -> list[tuple[str, list[str], dict[str, str]]]:
    return [
        ("benchmark regression", [sys.executable, str(ROOT / "tools" / "bench" / "regress.py")], {})
    ]


STAGES = {"--tests": _suite, "--fallback": _fallback, "--security": _security, "--bench": _bench}


def main(argv: list[str]) -> int:
    failed = [gate for gate in GATES if not _run([sys.executable, str(HERE / gate)])]
    if not _run([sys.executable, str(HERE / "gen_schema.py"), "--check"]):
        failed.append("gen_schema.py --check")
    for flag, stage in STAGES.items():  # each only on a green static ladder
        if flag in argv and not failed:
            failed += [name for name, cmd, env in stage() if not _run(cmd, env)]
    print("\n" + ("ALL GATES GREEN" if not failed else "RED: " + ", ".join(failed)))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
