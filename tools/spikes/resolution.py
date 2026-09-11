"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Spike 1: warrant resolution latency.

`NFR-PERF-002` asks for **p99 under 50 ms cached and 200 ms cold**, and the
requirements table has said *not measured* since the first release. It is the
figure that matters most in this platform: resolution sits on the critical path
of production scoring, so every millisecond here is a millisecond added to
somebody else's decision.

## Why it measures in-process rather than over HTTP

Over HTTP the number would include uvicorn, the socket, the JSON encode and
whatever the loopback does that day, and none of that is the thing being
questioned. What `NFR-PERF-002` is really asking is *how expensive is a
governance decision* — the entitlement check, the blocking-findings read, the
version status, the grammar validation and the signature. That is what this
times. A deployment's own figure will be larger and this is the floor under it.

## The two numbers, and why the second is the honest one

**Warm** is the repeated case: the same grant, resolved again. It is what a
scoring fleet actually does and it is the one to compare against the 50 ms
target.

**Cold** is a grant resolved for the first time. It is measured separately
rather than averaged in, because averaging a small number of cold calls into a
large number of warm ones produces a figure that flatters the design — and the
cold path is the one that runs after a deployment, which is exactly when a fleet
is re-resolving everything at once.

There is **no cache in this platform**, which the design document says plainly,
so the two should be close. If they are, that is the finding: the target
distinguishes cached from cold and the implementation does not, so the *cold*
target is the only one that means anything here.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from typing import Any, Dict, List

from tools.spikes.common import against, conditions, percentiles

#: From `NFR-PERF-002`.
WARM_TARGET_MS = 50.0
COLD_TARGET_MS = 200.0


def run(requests: int = 2000, grants: int = 50) -> Dict[str, Any]:
    """Resolve repeatedly and report the distribution.

    `grants` is deliberately more than one. Resolving the same grant ten
    thousand times measures a SQLite page cache as much as it measures MAYA,
    and a fleet has many grants live at once.
    """
    from tests.conftest import URN
    harness = _harness(grants)
    warm: List[float] = []
    cold: List[float] = []

    for grant in harness["grants"]:
        start = time.perf_counter()
        harness["resolve"](grant)
        cold.append(time.perf_counter() - start)

    for index in range(requests):
        grant = harness["grants"][index % len(harness["grants"])]
        start = time.perf_counter()
        harness["resolve"](grant)
        warm.append(time.perf_counter() - start)

    warm_stats, cold_stats = percentiles(warm), percentiles(cold)
    return {
        "spike": "warrant-resolution-latency",
        "requirement": "NFR-PERF-002",
        "conditions": conditions(requests=requests, grants=grants,
                                 store="sqlite", transport="in-process",
                                 urn=URN),
        "cold": cold_stats,
        "warm": warm_stats,
        "against_target": {
            "warm": against(warm_stats, WARM_TARGET_MS,
                            "warm resolution (the repeated case)"),
            "cold": against(cold_stats, COLD_TARGET_MS,
                            "cold resolution (the first time)"),
        },
        "detail": _detail(warm_stats, cold_stats),
    }


def _detail(warm: Dict[str, float], cold: Dict[str, float]) -> str:
    if not warm or not cold:
        return "nothing was measured"
    ratio = cold["p99_ms"] / warm["p99_ms"] if warm["p99_ms"] else 0
    out = (f"warm p99 {warm['p99_ms']} ms, cold p99 {cold['p99_ms']} ms, "
           f"measured in-process over {warm['count']} warm calls")
    if ratio < 1.5:
        out += (". The two are close, and that IS the finding rather than a "
                "good result: `NFR-PERF-002` distinguishes cached from cold "
                "and this platform has no descriptor cache, so there is no "
                "warm path to be fast. The 200 ms cold target is the only one "
                "of the two that means anything here")
    else:
        out += (f". Cold is {ratio:.1f}x warm, which is the database and not a "
                f"cache — there is no descriptor cache in this platform")
    if cold["count"] < 100:
        out += (f". **The cold p99 is over {cold['count']} samples and should "
                f"not be read as a p99 at all** — there is one cold call per "
                f"grant by construction, so a run with few grants measures a "
                f"maximum and labels it a percentile. Raise --grants to make "
                f"the cold figure mean something. Reported rather than "
                f"quietly printed, because a small-sample percentile is the "
                f"easiest number in a benchmark to quote out of context")
    if cold["p99_ms"] < warm["p99_ms"]:
        out += (". Cold measured FASTER than warm here, which is not a result "
                "about caching: the cold calls ran first, against a database "
                "holding almost nothing, and the warm sample includes whatever "
                "the store did as it grew. It is the kind of inversion that "
                "means the measurement rather than the system is being "
                "observed")
    out += (". Measured in-process: a deployment's figure includes uvicorn, "
            "the socket and the JSON encode, and will be larger. This is the "
            "floor under it, not a prediction of it")
    return out


def _harness(grants: int) -> Dict[str, Any]:
    """A real application, a real model, and `grants` live warrants.

    The test fixtures rather than a mock, because a mock of warrant resolution
    would be measuring a mock. This is the same path the API takes, minus the
    HTTP.
    """
    from fastapi.testclient import TestClient

    from core.config import PropertiesConfigurator
    from tests.api_helpers import approve_record, quorum_approve
    from tests.conftest import PEOPLE, URN

    import tempfile
    from pathlib import Path
    tmp = Path(tempfile.mkdtemp(prefix="maya-spike-"))
    (tmp / "application.yaml").write_text(_config(tmp))
    PropertiesConfigurator.reset()
    from run_maya_web import create_app
    app = create_app(PropertiesConfigurator(
        str(tmp / "application.yaml"), reload_interval=0))
    client = TestClient(app)
    client.__enter__()
    client.auth = ("admin", "maya-admin-dev")

    people = {}
    for username, (roles, password) in PEOPLE.items():
        client.post("/api/v1/principals", json={
            "username": username, "display_name": username, "roles": roles,
            "password": password})
        people[username] = (username, password)
    owner, dev, mrm = (people["j.okafor"], people["d.raman"],
                       people["s.iqbal"])
    client.post("/api/v1/models", auth=owner, json={
        "urn": URN, "name": "SB PD", "model_class": "credit.pd.scorecard",
        "domain": "credit", "owner": "person/j.okafor",
        "legal_entity": "LE-US-01", "purpose": "12-month PD at origination"})
    client.post(f"/api/v1/models/{URN.split('/')[-1]}/versions", auth=dev,
                json={"semver": "3.2.1", "kernel": _kernel(),
                      "artifact_digest": "sha256:" + "a" * 64})
    client.post(f"/api/v1/models/{URN.split('/')[-1]}/assess", auth=owner,
                json={"exposure": 2e9, "purpose_class": "regulatory_capital",
                      "feature_count": 12, "uses_alternative_data": False,
                      "interpretable": True})
    quorum_approve(client, people)
    approve_record(client, people)
    client.put(f"/api/v1/models/{URN.split('/')[-1]}/aliases", auth=mrm,
               json={"environment": "prod", "alias": "champion",
                     "semver": "3.2.1"})

    live = []
    for index in range(grants):
        principal = f"svc/spike-{index}"
        made = client.post("/api/v1/warrants", auth=owner, json={
            "urn": f"{URN}#champion", "principal": principal,
            "declared_use": "origination_decision", "environment": "prod"})
        if made.status_code == 201:
            live.append(principal)
    if not live:
        raise SystemExit(
            "the harness could not issue a warrant, so there is nothing to "
            "resolve. This is a defect in the spike rather than a result")

    def resolve(principal: str) -> None:
        answer = client.post("/api/v1/resolve", json={
            "urn": f"{URN}#champion", "environment": "prod",
            "principal": principal, "declared_use": "origination_decision"})
        if answer.status_code != 200:
            raise SystemExit(
                f"resolution refused during the spike ({answer.status_code}): "
                f"{answer.text[:300]}. A latency figure over refusals is not a "
                f"latency figure")

    return {"grants": live, "resolve": resolve}


def _kernel() -> Dict[str, Any]:
    return {"parameter_kind": "estimated_coefficients",
            "fit_procedure": "estimate",
            "input_schema": [{"name": "dscr", "dtype": "float",
                              "minimum": -5, "maximum": 20}],
            "output_schema": [{"name": "pd_12m", "dtype": "float"}]}


def _config(tmp: Any) -> str:
    return f"""
app: {{name: MAYA, version: "0.1.0", tagline: "t", slogan: "s", principle: "p"}}
server: {{host: 127.0.0.1, port: 5006}}
database: {{url: "sqlite:///{tmp}/data/sqlite/maya.db"}}
data: {{dir: "{tmp}/data", artifacts: "{tmp}/data/artifacts",
        attachments: "{tmp}/data/attachments",
        delta: {{dir: "{tmp}/data/delta", features: "{tmp}/data/delta/features",
                snapshots: "{tmp}/data/delta/snapshots",
                telemetry: "{tmp}/data/delta/telemetry",
                monitoring: "{tmp}/data/delta/monitoring"}}}}
risk:
  exposure_bands: {{negligible: 0, low: 1000000, moderate: 50000000,
                   material: 500000000, critical: 5000000000}}
  purpose_ranks: {{commercial: 1, valuation: 2, risk_management: 2,
                  customer_facing: 3, credit_decision: 3,
                  financial_reporting: 3, policy_decision: 4,
                  clinical_decision: 4, regulatory_capital: 4}}
  review_months: {{1: 12, 2: 18, 3: 24, 4: 36}}
warrants: {{jitter_pct: 0, signing_key: spike-signing-secret,
         ttl_seconds: {{1: 3600, 2: 3600, 3: 3600, 4: 3600}},
         grace_seconds: {{1: 900, 2: 900, 3: 900, 4: 900}}}}
execution: {{captive: {{enabled: false}}}}
logging: {{level: ERROR}}
"""


def main(argv: Any = None) -> int:
    parser = argparse.ArgumentParser(prog="tools.spikes.resolution")
    parser.add_argument("--requests", type=int, default=2000)
    parser.add_argument("--grants", type=int, default=50)
    args = parser.parse_args(argv)
    result = run(args.requests, args.grants)
    print(json.dumps(result, indent=2))
    print("\n" + result["detail"], file=sys.stderr)
    return 0


if __name__ == "__main__":                       # pragma: no cover
    raise SystemExit(main())
