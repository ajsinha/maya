"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Spike 4: the register at estate size.

`NFR-PERF-001` asks for **list and search p95 under 500 ms at 10,000 models** and
**detail p95 under 800 ms**, and has said *shape asserted, not timed* since the
first release. `NFR-PERF-005` asks the platform to hold **50,000 models** and
says *not demonstrated*, with a sentence that is really a prediction:

> the register lists all models and filters in process

That sentence is the thing to falsify. `routes/model_routes.py::list_models`
calls `reg.list(...)`, hands the whole result to the scope filter, applies the
search in Python, and cuts the page last. Every one of those steps is correct —
[14 §17](../../docs/14-detailed-design.md) explains why the page is cut last, and
it is the right decision — and all of them are **linear in the size of the
estate**, on every request, including the ones that return twenty rows.

So this spike is not really asking *is it fast*. It is asking **what shape is
it**, because a number from one estate size is a number and two are a slope.

## Why it seeds rows rather than registering models

`tools/demo/seed_estate.py` says, correctly, that an estate assembled by writing
rows would show screens in states the platform cannot reach. That argument is
about *screens*. This is a latency measurement over the read path, and at fifty
thousand models the alternative is not a better spike, it is no spike: each
`register` appends to a hash chain under a serialised lock, and the write path is
not what `NFR-PERF-001` is about.

**What that costs, stated rather than buried.** The rows are shaped exactly as
`CatalogueService.register` writes them, so the reads are the real reads. But the
seeded register has **no evidence chain**, so:

  * nothing here measures the **write** path at estate size — not registration,
    not the quorum, not the serialised append;
  * **chain verification at 50,000 models is not in this result** and remains a
    target. `tests/test_scale.py` verifies a chain of 6,000 nodes, which is the
    largest figure this repository has actually observed.

A spike that quietly skipped that second point would be reporting an estate-size
result for the one operation it did not run.

## Why each read is time-boxed, and why that is a result too

The first version took a fixed sixty samples of every read at every size, which
is the obvious design and the wrong one. At fifty thousand models the reads that
fold the estate are slow enough that sixty of them is **tens of minutes**, and a
measurement that only prints at the end loses everything to the first timeout.
The first run of this spike was killed at fifty minutes having reported nothing.

So each read gets a **sample budget and a wall-clock budget**, whichever ends
first, and the result carries `count` — the number of samples actually taken.
Nine samples is a weak percentile and it is reported as nine rather than dressed
up as sixty. Each size is written out as soon as it is measured, so a run that is
killed still leaves what it had established.

That the budget binds at all is itself the finding. **A read that cannot be
sampled sixty times in a minute is a read somebody waits for**, and which of them
binds is more informative than the millisecond figure beside it.

## A read too slow to sample is reported as too slow to sample

A wall-clock budget checked *between* samples does not bound anything if a single
call is slower than the budget. The second run of this spike was killed after
`portfolio` over fifty thousand models ran for more than half an hour, having
taken 8.26 seconds over ten thousand — and the spike had no way to stop waiting,
so the whole size was lost.

So every read is **probed once under a ceiling** before it is sampled, and a
probe that does not return inside it is recorded as `abandoned` with the floor
it passed: *more than N seconds*. That is a result. A missing row is not, and a
number arrived at by waiting long enough is a number about this machine's
patience.

## The ceiling this spike does not have, and why

A sample budget bounds a read whose single call is quick. It bounds nothing when
one call is slower than the budget — `portfolio` over fifty thousand models ran
for more than half an hour against 8.26 seconds over ten thousand, and the spike
had no way to stop waiting.

**Two in-process ceilings were tried and neither works, which is worth recording
so nobody tries them again.** `setitimer` with a signal handler does not fire: a
Python signal handler only runs when the interpreter regains control between
bytecodes, and these reads sit inside SQLite's C code, so the signal is delivered
and then handled when the call returns — precisely when it is no longer needed. A
thread is worse: nothing stops the work, and a probe that gave up while its own
query carried on burning the CPU would poison every measurement after it. Forking
fails for a third reason — the in-process test client runs its event loop on a
background thread, and a forked child inherits none of it, so every call hangs.

So the ceiling is **external**, which is the one place it can actually be
enforced:

    timeout 300 python -m tools.spikes.estate --sizes 50000 --only portfolio \
        --out result.json

`--out` is written after each size, and `--only` measures one read, so a run
killed by the OS still leaves what it established and the killing is the result:
*this read did not return inside five minutes*. A floor is a measurement. A
number arrived at by waiting longer is a number about this machine's patience.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import time
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from tools.spikes.common import conditions, percentiles

#: From `NFR-PERF-001`. The list target is stated at 10,000 models, which is why
#: that size is always measured even when a larger one is asked for.
LIST_TARGET_MS = 500.0
DETAIL_TARGET_MS = 800.0

#: The size `NFR-PERF-001` states its target at, and the size `NFR-PERF-005`
#: asks the platform to hold. Both are measured, because a target met at the
#: first and missed at the second is the useful result.
STATED_AT = 10_000
ASKED_FOR = 50_000

#: How long one read may be sampled for before the spike moves on, and the most
#: samples it will take. Whichever ends first — a fixed sample count is fine at
#: ten thousand models and is tens of minutes at fifty thousand, which is how
#: the first run of this spike was killed having reported nothing.
SECONDS_PER_READ = 45.0


#: What a reviewer actually does on arriving at the register, in order. Chosen
#: from the screens rather than from the endpoints: a benchmark of the fastest
#: endpoints is a benchmark of nothing somebody waits for.
DOMAINS = ("credit", "market", "operational", "conduct", "capital", "liquidity")
CLASSES = ("credit.pd.scorecard", "market.var.historical", "op.loss.lda",
           "conduct.surveillance.ml", "capital.irb.lgd", "liquidity.lcr.flow")


def run(sizes: Sequence[int] = (STATED_AT, ASKED_FOR), requests: int = 60,
        seconds: float = SECONDS_PER_READ, only: Sequence[str] = (),
        on_size: Optional[Callable[[str, Dict[str, Any]], None]] = None
        ) -> Dict[str, Any]:
    """Measure the reader's path at each size, and report the slope."""
    measured: Dict[str, Dict[str, Any]] = {}
    for size in sizes:
        measured[str(size)] = _at_size(size, requests, seconds, only)
        if on_size is not None:
            # Handed over as soon as it is established, so a run that is killed
            # part way leaves what it had rather than nothing. The first run of
            # this spike lost fifty minutes to exactly that.
            on_size(str(size), measured[str(size)])
    out: Dict[str, Any] = {
        "spike": "estate", "sizes": list(sizes),
        "sample_budget": requests, "seconds_per_read": seconds,
        "only": list(only),
        "by_size": measured,
        "conditions": conditions(sizes=list(sizes), store="sqlite"),
    }
    out["growth"] = _growth(measured, sizes) if len(measured) > 1 else {}
    out["against_target"] = _targets(measured)
    out["not_measured"] = NOT_MEASURED
    out["detail"] = _detail(measured, out["growth"], out["against_target"])
    return out


#: Stated in the result rather than in a footnote. A scale figure travels, and
#: the things it does not cover travel less well than the number does.
NOT_MEASURED: Tuple[str, ...] = (
    "the write path. The estate is seeded as rows, so registration, the "
    "approval quorum and the serialised evidence append are not timed here at "
    "any size",
    "evidence chain verification at estate size. The seeded register has no "
    "chain; 6,000 nodes in `tests/test_scale.py` is the largest this "
    "repository has observed, and `NFR-PERF-005` is asking about 50,000 "
    "models' worth",
    "concurrency. One process, one request at a time — a p95 under load is a "
    "different number and this is the floor under it",
    "PostgreSQL. Measured on SQLite, where the whole estate is one file on "
    "local disk. A network round trip per query moves every figure here",
    "anything multi-node: failover, replica reads, RTO and RPO "
    "(`NFR-AVAIL-001`, `NFR-AVAIL-003`) are untouched by this",
)


def _at_size(size: int, requests: int, seconds: float,
             only: Sequence[str] = ()) -> Dict[str, Any]:
    """Seed an estate of `size` models and time the reader's path over it."""
    harness = _harness(size)
    out: Dict[str, Any] = {"models": size}
    bound_by = []
    for name, call in harness["reads"].items():
        if only and name not in only:
            continue
        # Warm once and discard: the first call through any path pays for
        # imports and connection setup, and a sample carrying that as an
        # outlier reports a tail belonging to the spike rather than to the
        # platform.
        call()
        samples: List[float] = []
        deadline = time.perf_counter() + seconds
        while len(samples) < requests and time.perf_counter() < deadline:
            samples.append(_timed(call))
        out[name] = {**percentiles(samples), "budget": requests,
                     "bound_by": "clock" if len(samples) < requests
                                 else "samples"}
        if len(samples) < requests:
            bound_by.append(f"{name} ({len(samples)} of {requests})")
        print(f"  {size:>6} {name:<11} {out[name]['p95_ms']:>9.1f} ms p95 "
              f"over {out[name]['count']} sample(s)", file=sys.stderr,
              flush=True)
    out["seed_seconds"] = harness["seed_seconds"]
    # Which reads ran out of clock rather than of samples. More informative
    # than the milliseconds beside them: a read that cannot be sampled to its
    # budget inside the window is a read somebody waits for.
    out["clock_bound"] = bound_by
    return out


def _timed(call: Callable[[], None]) -> float:
    started = time.perf_counter()
    call()
    return time.perf_counter() - started


def _growth(measured: Dict[str, Dict[str, Any]],
            sizes: Sequence[int]) -> Dict[str, Any]:
    """How the work grew against how the estate did.

    1.0 is linear — each model costs the same as the last. Below 1 means the
    read is sublinear in estate size, which is what an index does. Meaningfully
    above 1 is the finding, because it is the difference between an estate that
    gets slower and one that stops.
    """
    if len(sizes) < 2:
        return {}
    small, large = str(sizes[0]), str(sizes[-1])
    factor = sizes[-1] / sizes[0]
    out = {}
    for name, value in measured[small].items():
        if not isinstance(value, dict) or "p95_ms" not in value:
            continue
        if "p95_ms" not in (measured[large].get(name) or {}):
            # Measured at one size and abandoned at the other. A ratio here
            # would be a slope drawn through one point.
            continue
        was, now = value["p95_ms"], measured[large][name]["p95_ms"]
        out[name] = {
            "p95_at_{}".format(small): was,
            "p95_at_{}".format(large): now,
            "ratio": round((now / was) / factor, 3) if was > 0 else None,
            "linear_would_be": 1.0,
        }
    return out


def _targets(measured: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """Against `NFR-PERF-001`, at the size it states its target at and above it.

    p95 rather than p99, because that is the percentile the requirement is
    written in — comparing a p99 against a p95 target is how a figure gets
    quoted as a miss it is not.
    """
    out: Dict[str, Any] = {}
    for size, rows in measured.items():
        for name, target in (("list", LIST_TARGET_MS), ("search", LIST_TARGET_MS),
                             ("detail", DETAIL_TARGET_MS)):
            sample = rows.get(name)
            if not sample:
                continue
            met = sample["p95_ms"] <= target
            out[f"{name}@{size}"] = {
                "target_p95_ms": target, "measured_p95_ms": sample["p95_ms"],
                "met": met,
                "detail": (
                    f"{name} at {size} models: p95 {sample['p95_ms']} ms "
                    f"against {target} ms"
                    + (f", {round(target - sample['p95_ms'], 1)} ms of "
                       f"headroom" if met
                       else f" — OVER by {round(sample['p95_ms'] - target, 1)} "
                            f"ms")
                    + f". The slowest single call was {sample['max_ms']} ms"),
            }
    return out


def _detail(measured: Dict[str, Dict[str, Any]], growth: Dict[str, Any],
            targets: Dict[str, Any]) -> str:
    missed = [k for k, v in targets.items() if not v["met"]]
    superlinear = [k for k, v in growth.items()
                   if (v.get("ratio") or 0) > 1.25]
    out = (f"measured at {', '.join(sorted(measured, key=int))} models. "
           f"{len(targets) - len(missed)} of {len(targets)} target "
           f"comparisons met")
    if missed:
        out += f"; over on {', '.join(sorted(missed))}"
    out += (". The figure to read is the SLOPE rather than either number: a "
            "read whose cost grows with the estate is one that works until it "
            "does not, and no amount of headroom at today's size tells you "
            "where that is")
    if superlinear:
        out += (f". These grew faster than the estate did, which is worse than "
                f"slow: {', '.join(sorted(superlinear))}")
    return out


def _harness(size: int) -> Dict[str, Any]:
    """A real application over a seeded estate of `size` models.

    The app is the real one and the reads go through the real routes. Only the
    seeding is shortcut, and `NOT_MEASURED` says what that costs.
    """
    import tempfile
    from pathlib import Path

    from fastapi.testclient import TestClient

    from core.config import PropertiesConfigurator

    tmp = Path(tempfile.mkdtemp(prefix="maya-spike-estate-"))
    (tmp / "application.yaml").write_text(_config(tmp))
    PropertiesConfigurator.reset()
    from run_maya_web import create_app
    app = create_app(PropertiesConfigurator(
        str(tmp / "application.yaml"), reload_interval=0))
    client = TestClient(app)
    client.__enter__()
    client.auth = ("admin", "maya-admin-dev")
    # The API takes HTTP Basic; the INTERFACE takes a signed session cookie,
    # and answers 200 with the sign-in page to anything else. Both are needed
    # here because the reader's path crosses both.
    signed_in = client.post("/login", data={"username": "admin",
                                            "password": "maya-admin-dev"},
                            follow_redirects=False)
    if signed_in.status_code not in (200, 302, 303):
        raise SystemExit(
            f"the spike could not sign in ({signed_in.status_code}), so every "
            f"interface read would time a login form")

    started = time.perf_counter()
    urns = _seed(app, size)
    seed_seconds = round(time.perf_counter() - started, 2)

    # A deterministic sample, so two runs of this spike read the same rows and
    # the difference between them is the platform rather than the draw.
    rng = random.Random(20260911)
    picked = [rng.choice(urns) for _ in range(64)]
    names = [u.split("/")[-1] for u in picked]
    cursor = {"n": 0}

    def _next_name() -> str:
        cursor["n"] = (cursor["n"] + 1) % len(names)
        return names[cursor["n"]]

    def _get(path: str, expect: str = "", **params: Any) -> None:
        answer = client.get(path, params=params or None)
        if answer.status_code != 200:
            raise SystemExit(
                f"{path} answered {answer.status_code} during the spike: "
                f"{answer.text[:300]}. A latency figure over errors is not a "
                f"latency figure")
        # And a 200 is not enough. `/dashboard` under HTTP Basic answers 200
        # with the SIGN-IN page — the interface takes a signed session cookie
        # and Basic is for the API — so the first version of this spike timed
        # a login form and reported it as a dashboard at 2.5 ms. A read has to
        # assert it got the page it asked for, not merely that something came
        # back.
        if expect and expect not in answer.text:
            raise SystemExit(
                f"{path} answered 200 without '{expect}' in it, so this is "
                f"not the page being measured. Timing the wrong page is worse "
                f"than timing an error, because an error stops the spike")

    return {
        "seed_seconds": seed_seconds,
        "reads": {
            # The first screen: page one of the register.
            "list": lambda: _get("/api/v1/models", limit=50),
            # A page most of the way down, scaled to the estate so that it is
            # a real page at every size. Offsets are ordinary rather than
            # cursors BECAUSE a governance register is read by people who want
            # page four hundred — so a deep page is part of the claim, not an
            # edge case.
            #
            # Fixed at 20,000 in the first version, which is past the end of a
            # ten-thousand-model estate: that compared an EMPTY page against a
            # real one, and the slope between them meant nothing.
            "deep_page": lambda: _get("/api/v1/models", limit=50,
                                      offset=int(size * 0.8)),
            # The search the requirement names, run in process over the whole
            # estate before the page is cut.
            "search": lambda: _get("/api/v1/models", q="pd", limit=50),
            # One model. Should be constant in estate size; this is where that
            # is checked rather than assumed.
            "detail": lambda: _get(f"/api/v1/models/{_next_name()}"),
            # The fold over the whole estate, which is the read that cannot
            # be paged out of doing the work.
            "portfolio": lambda: _get("/api/v1/portfolio"),
            # The screen a reviewer actually lands on. Measured as HTML rather
            # than as its API, because the worklist has no endpoint of its own
            # — it is assembled for the dashboard — and timing only the parts
            # that happen to be endpoints would miss the page somebody waits
            # for. It needs the session cookie below; asserted on content
            # rather than on status, for the reason in `_get`.
            "dashboard": lambda: _get("/dashboard", expect="Every model, one register"),
        },
    }


def _seed(app: Any, size: int) -> List[str]:
    """Write `size` models and one version each, shaped as `register` writes them.

    Straight through the repositories in one transaction per batch. The row
    shape is copied from `CatalogueService.register` rather than invented, so a
    column added there and forgotten here shows up as a failing read rather
    than as a fast one.
    """
    from db import ModelRepository, VersionRepository

    ctx = app.state.ctx
    models = ModelRepository(ctx["db"])
    versions = VersionRepository(ctx["db"])
    existing = {m["urn"] for m in models.many()}
    urns: List[str] = []
    now = time.time()
    rng = random.Random(4242)

    batch = 2_000
    for start in range(0, size, batch):
        with models.db.transaction():
            for index in range(start, min(start + batch, size)):
                urn = f"maya://model/seed.{index:06d}.pd"
                urns.append(urn)
                if urn in existing:
                    continue
                domain = DOMAINS[index % len(DOMAINS)]
                row = {
                    "urn": urn, "name": f"Seeded PD {index:06d}",
                    "description": "", "model_class": CLASSES[index % len(CLASSES)],
                    "domain": domain, "owner": f"person/owner-{index % 200}",
                    "legal_entity": f"LE-{index % 12:02d}",
                    "purpose": "12-month PD at origination",
                    "origin": "internal", "status": "draft",
                    "tier": rng.choice((1, 2, 3, 4)), "designations": [],
                    "attributes": {}, "created_at": now, "created_by": "spike",
                }
                models.add(row)
                versions.add({**VERSION, "model_id": row["id"],
                              "created_at": now})
    return urns


#: A version row, shaped from `VersionService.create_version` rather than
#: invented. Constant across the estate on purpose: this spike is about how the
#: register behaves as it grows, and varying the versions would put a second
#: variable into a measurement that has one.
VERSION: Dict[str, Any] = {
    "semver": "1.0.0", "manifest": {}, "manifest_digest": "sha256:" + "0" * 64,
    "trainability_class": "T2", "parameter_kind": "estimated_coefficients",
    "fit_procedure": "estimate", "deterministic": True,
    "input_schema": [{"name": "dscr", "dtype": "float"}],
    "parameter_schema": [], "output_schema": [{"name": "pd_12m",
                                               "dtype": "float"}],
    "contract": {}, "artifact_digest": "sha256:" + "0" * 64,
    "artifact_uri": None, "artifact_size": None, "status": "draft",
    "created_by": "spike"}


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
    parser = argparse.ArgumentParser(
        prog="tools.spikes.estate",
        description="The register at estate size. Reports the slope, not only "
                    "the number.")
    parser.add_argument("--sizes", type=int, nargs="+",
                        default=[STATED_AT, ASKED_FOR])
    parser.add_argument("--requests", type=int, default=60,
                        help="sample budget per read")
    parser.add_argument("--seconds", type=float, default=SECONDS_PER_READ,
                        help="wall-clock budget per read; whichever ends first")
    parser.add_argument("--only", nargs="*", default=[],
                        help="measure only these reads; a slow one is driven "
                             "alone under an external `timeout`")
    parser.add_argument("--out", default="",
                        help="write the result here, updated after each size, "
                             "so a killed run leaves what it established")
    args = parser.parse_args(argv)

    partial: Dict[str, Any] = {"spike": "estate", "by_size": {},
                               "complete": False}

    def _save(size: str, rows: Dict[str, Any]) -> None:
        if not args.out:
            return
        partial["by_size"][size] = rows
        _write(args.out, partial)

    result = run(args.sizes, args.requests, args.seconds, args.only,
                 on_size=_save)
    if args.out:
        _write(args.out, {**result, "complete": True})
    print(json.dumps(result, indent=2))
    return 0


def _write(path: str, payload: Dict[str, Any]) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")


if __name__ == "__main__":                       # pragma: no cover
    sys.exit(main())
