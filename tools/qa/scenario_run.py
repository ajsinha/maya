"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Runs the hand-written cases, one at a time, against a live instance.

    python -m tools.qa.scenario_run                 # everything registered
    python -m tools.qa.scenario_run --only QA-DEL   # one prefix

Each case gets a **fresh subject** where it needs one, because these mutate:
they delete models, place holds and reclaim storage. Sharing state between
them is how a case comes to pass because of what the previous one left behind
— which already happened once in this run, when section B's malformed posts
made twenty-six of section C's cases look broken.

A scenario that raises is recorded as an error against its own case rather
than ending the pass. A run that stops at the first surprise reports nothing
about everything after it.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time
import traceback
from typing import Any, Dict, List

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.qa.scenarios import common
from tools.qa.scenarios.common import BLOCKED, FAIL, PASS, Ctx


def _load() -> None:
    """Import the section modules so their cases register."""
    import importlib
    import pkgutil
    package = ROOT / "tools" / "qa" / "scenarios"
    for info in pkgutil.iter_modules([str(package)]):
        if info.name not in ("common", "__init__"):
            importlib.import_module(f"tools.qa.scenarios.{info.name}")


def _run(fn, ctx):
    """One case, with its own failure contained.

    A case that raises is recorded against itself rather than ending the pass.
    A run that stops at the first surprise reports nothing about everything
    after it.
    """
    try:
        return fn(ctx)
    except AssertionError as setup:
        return BLOCKED, f"setup: {setup}"
    except SystemExit as exited:
        # A CLI tool refusing calls `sys.exit`, and `SystemExit` is a
        # BaseException — so it walked straight past the handler below and
        # ended the whole pass at the first tool that behaved correctly.
        return FAIL, (f"the case let a SystemExit({exited.code}) escape; a "
                      f"case that runs a CLI must read its exit code rather "
                      f"than let it terminate the run")
    except Exception as exc:
        return FAIL, (f"the case itself raised {type(exc).__name__}: {exc} | "
                      + traceback.format_exc(limit=2).replace("\n", " ")[:220])


def _isolated(case_id: str, fn):
    """Run one case against an application of its own.

    For cases that damage shared state — the evidence-chain tamper cases leave
    the chain broken, and everything after them would then detect damage it
    did not do.
    """
    from tools.qa.harness import PEOPLE, UNPRIVILEGED, live_client
    with live_client() as (ui, api, observer):
        app_ctx = getattr(getattr(ui, "app", None), "state", None)
        held = getattr(app_ctx, "ctx", {}) or {}
        ctx = Ctx(ui=ui, api=api, observer=observer,
                  people={"observer": UNPRIVILEGED,
                          **{w: (w, pw) for w, (_r, pw) in PEOPLE.items()}},
                  made={"db": held.get("db"), "evidence": held.get("evidence")})
        return _run(fn, ctx)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--only", default="",
                    help="run only case ids starting with this")
    # Per-prefix by default. One shared file meant each partial run erased
    # the last, and the coverage summary then reported whatever had been run
    # most recently as though it were everything.
    ap.add_argument("--out", default="")
    args = ap.parse_args(argv)

    _load()
    chosen = sorted(cid for cid in common.REGISTRY if cid.startswith(args.only))
    if not chosen:
        print(f"no cases match {args.only!r}")
        return 1

    from tools.qa.harness import PEOPLE, UNPRIVILEGED, live_client
    results: List[Dict[str, Any]] = []
    started = time.time()
    with live_client() as (ui, api, observer):
        # The application context, for the handful of cases that assert on a
        # service directly rather than through a route — the ones about a
        # declaration or a refusal that has no endpoint.
        app_ctx = getattr(getattr(ui, "app", None), "state", None)
        ctx = Ctx(ui=ui, api=api, observer=observer,
                  people={"observer": UNPRIVILEGED,
                          **{who: (who, password)
                             for who, (_roles, password) in PEOPLE.items()}},
                  made={"db": (getattr(app_ctx, "ctx", {}) or {}).get("db"),
                        "evidence": (getattr(app_ctx, "ctx", {}) or {}).get(
                            "evidence")})
        for case_id in chosen:
            title, fn = common.REGISTRY[case_id]
            if case_id in common.ISOLATED:
                verdict, evidence = _isolated(case_id, fn)
            else:
                verdict, evidence = _run(fn, ctx)
            results.append({"id": case_id, "title": title, "verdict": verdict,
                            "evidence": str(evidence)[:400]})
            print(f"  {verdict:8s} {case_id}  {title[:64]}", flush=True)

    took = time.time() - started
    summary = {"total": len(results),
               "pass": sum(1 for r in results if r["verdict"] == PASS),
               "fail": sum(1 for r in results if r["verdict"] == FAIL),
               "blocked": sum(1 for r in results if r["verdict"] == BLOCKED)}
    stem = (args.only or "all").replace("-", "_").lower()
    out = pathlib.Path(args.out or f"docs/QA/results/scenarios-{stem}.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"summary": summary, "seconds": round(took, 1),
                               "results": results}, indent=1), encoding="utf-8")
    print(f"\n{summary['total']} cases in {took:.0f}s — {summary['pass']} pass, "
          f"{summary['fail']} fail, {summary['blocked']} blocked")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
