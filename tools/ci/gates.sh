#!/bin/bash
#
# MAYA — the preflight gates, run together and failing loudly.
#
# Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
# Proprietary and confidential. See LICENSE and NOTICE at the repository root.
#
# Run before every commit:
#
#     bash tools/ci/gates.sh
#
# There are five, and none of them is the test suite — the suite is slow enough
# that it is run separately, and these are the checks that catch the things a
# passing suite does not:
#
#   ruff          style and the obvious mistakes
#   typecheck     mypy over everything not in the declared backlog
#   scan_secrets  a credential about to enter the history
#   spec_lock     the OpenAPI lock, so a route cannot change unnoticed
#                 (run `--update` yourself when you MEANT to change one)
#   qa verify     the published case list re-derived from source, plus the two
#                 guards that check it against the scenario registry in BOTH
#                 directions — every scenario answers a published case, and
#                 every published case claiming a scenario has one
#
# The last is the one worth having here rather than only in the suite: it is
# cheap, and the case list going stale is silent.
set -e
cd "$(dirname "$0")/../.."

PY=.venv/bin/python
RUFF=.venv/bin/ruff

fail() { echo "GATE FAILED — DO NOT COMMIT: $1"; exit 1; }

$RUFF check . >/dev/null || fail "ruff"
$PY tools/ci/typecheck.py >/dev/null 2>&1 || fail "typecheck"
$PY tools/ci/scan_secrets.py >/dev/null 2>&1 || fail "scan_secrets"
$PY tools/ci/spec_lock.py >/dev/null 2>&1 || fail \
    "spec_lock — run 'python tools/ci/spec_lock.py --update' if you changed a route on purpose"
$PY -m qa.regression_suite.verify >/dev/null 2>&1 || fail "qa verify"

guard=$(mktemp)
if ! $PY -m pytest tests/test_qa_scenarios.py tests/test_qa_cases.py \
        -q -p no:randomly > "$guard" 2>&1; then
  echo "GATE FAILED — DO NOT COMMIT: the QA guards"
  grep -E "^E  " "$guard" | head -12
  rm -f "$guard"
  exit 1
fi
rm -f "$guard"
echo "ALL GATES PASS"
