"""
MAYA — the soak runner.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.

    python tools/soak/run.py --hours 6 --max-checks 3000

Starts a MAYA server on a scratch database, drives real work through its HTTP
API and its screens for the stated duration, and asserts the invariants between
batches. Writes a JSONL journal as it goes; `report.py` renders it.

**Paced, not raced.** The check budget is spread across the whole duration on
purpose. A run that spends three thousand checks in ten minutes has measured
throughput; the question here is whether the platform still tells the truth
after six hours, and that requires six hours to have passed. Between batches
the runner sleeps, and while it sleeps the server is idle — which is itself a
condition worth being in, because a scheduler loop, a cache expiry or a
connection recycled by a pool all happen in the quiet.

**Concurrency, deliberately.** One phase in each cycle drives several writers
at the evidence chain at once. The advisory lock that serialises the sequence
is the thing under test, and it cannot be tested by one caller.
"""
from __future__ import annotations

import argparse
import pathlib
import shutil
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.soak import invariants, scenarios                    
from tools.soak.harness import Client, Journal, Server          


def parse() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="MAYA soak run")
    p.add_argument("--hours", type=float, default=6.0)
    p.add_argument("--max-checks", type=int, default=3000)
    p.add_argument("--port", type=int, default=5099)
    p.add_argument("--workdir", default=None)
    p.add_argument("--journal", default=None)
    p.add_argument("--writers", type=int, default=4)
    return p.parse_args()


def concurrent_evidence(client, journal, cycle: int, writers: int) -> None:
    """Several principals writing at once, on purpose.

    The evidence engine takes an advisory lock so that the sequence is dense
    and unique. One caller can never show that the lock is really being taken;
    `invariants.evidence_sequence_is_dense` checks the result, and this is what
    makes the result mean something.
    """
    # All four act as the OWNER. The point of this phase is simultaneous
    # writes to the evidence chain, not authorisation — and picking principals
    # who may not register turned "the lock serialises writers" into "two of
    # the four were refused", which measures the wrong thing.
    people = ["soak.owner"] * max(1, writers)
    results = []
    lock = threading.Lock()

    def one(index: int, who: str):
        name = f"soak.race.{cycle:05d}.{index}"
        status, _ = client.post("/models", {
            "urn": f"maya://model/{name}", "name": f"race {index}",
            "model_class": "credit.pd.scorecard", "domain": "credit",
            "owner": "person/soak.owner", "legal_entity": "LE-UK-01",
            "purpose": "written at the same moment as its siblings"},
            auth=scenarios.creds(who))
        with lock:
            results.append(status)

    with ThreadPoolExecutor(max_workers=len(people)) as pool:
        for index, who in enumerate(people):
            pool.submit(one, index, who)

    made = sum(1 for s in results if s == 201)
    journal.check("concurrency",
                  f"{len(people)} simultaneous writers all succeed",
                  made == len(people), f"{len(people)} created", made)


def main() -> int:
    args = parse()
    work = pathlib.Path(args.workdir or (ROOT / ".soak" / "run"))
    if work.exists():
        shutil.rmtree(work)
    journal_path = pathlib.Path(
        args.journal or (ROOT / "docs" / "soak" / "soak-journal.jsonl"))
    journal = Journal(journal_path)

    base = f"http://127.0.0.1:{args.port}"
    import tools.soak.harness as harness
    harness.BASE = base
    harness.API = base + "/api/v1"

    server = Server(work, args.port, journal)
    client = Client(journal)

    journal.event("run_started", hours=args.hours, max_checks=args.max_checks,
                  writers=args.writers, base=base,
                  commit=_commit(), python=sys.version.split()[0])

    server.start()
    if not server.wait_until_ready():
        journal.check("startup", "the server accepts connections", False,
                      "ready within 90s", "never came up")
        journal.event("run_aborted", why="server never became ready")
        server.stop()
        journal.close()
        return 1
    journal.check("startup", "the server accepts connections", True,
                  "ready", "ready")

    scenarios.bootstrap(client, journal)
    state: dict = {}
    deadline = time.time() + args.hours * 3600.0
    cycle = 0
    # Every cycle costs roughly this many checks; the budget divided by it is
    # how many cycles there is room for, and the duration divided by THAT is
    # how long to rest between them. Recomputed each cycle from what has
    # actually been spent, so an early scenario that fails and returns short
    # does not leave the run idle for hours.
    try:
        while time.time() < deadline and journal.checks < args.max_checks:
            cycle += 1
            began = time.time()
            journal.event("cycle_started", cycle=cycle,
                          checks_so_far=journal.checks)

            if not invariants.the_server_is_still_up(server, journal):
                journal.event("run_aborted", why="the server exited", cycle=cycle)
                break

            model = scenarios.governed_lifecycle(client, journal, cycle)
            scenarios.refusals_that_must_hold(client, journal, cycle, model)
            scenarios.features_and_shapes(client, journal, cycle)
            concurrent_evidence(client, journal, cycle, args.writers)
            scenarios.platform_surfaces(client, journal)
            scenarios.ui_pages(client, journal, base)
            if cycle % 3 == 1:
                scenarios.api_keys(client, journal, cycle)
            if cycle % 5 == 1:
                scenarios.scheduler_batch(client, journal)
            scenarios.evidence_and_chain(client, journal)

            # The invariants, every cycle without exception. Something checked
            # once an hour catches a problem an hour late.
            invariants.evidence_chain_verifies(client, journal, state)
            invariants.evidence_sequence_is_dense(work / "maya.db", journal, state)
            invariants.schema_matches_the_declaration(work / "maya.db", journal)
            invariants.nothing_returned_a_500(client, journal, state)
            invariants.resources_are_bounded(server, journal, state)
            invariants.the_log_ring_stays_bounded(client, journal)
            invariants.no_credential_is_visible(client, journal)
            invariants.the_warrant_epoch_only_rises(client, journal, state)
            invariants.the_register_only_grows(client, journal, state)
            invariants.latency_has_not_collapsed(client, journal, state)

            spent = journal.checks
            cost = max(1, spent / cycle)
            remaining_checks = max(0, args.max_checks - spent)
            remaining_time = max(0.0, deadline - time.time())
            cycles_left = max(1.0, remaining_checks / cost)
            rest = max(0.0, remaining_time / cycles_left - (time.time() - began))
            journal.event("cycle_finished", cycle=cycle, checks=spent,
                          failures=journal.failures,
                          took=round(time.time() - began, 2),
                          resting=round(rest, 1),
                          cycles_left=round(cycles_left, 1))
            if remaining_checks <= 0:
                break
            # Slept in slices so the run can still notice the clock and a dead
            # server rather than committing to a long sleep it cannot leave.
            end_of_rest = time.time() + rest
            while time.time() < min(end_of_rest, deadline):
                time.sleep(min(15.0, max(0.5, end_of_rest - time.time())))
                if not server.alive():
                    break
    except KeyboardInterrupt:
        journal.event("run_interrupted")
    except Exception as exc:                       # the run itself failing
        import traceback
        journal.event("harness_error", error=f"{type(exc).__name__}: {exc}",
                      traceback=traceback.format_exc()[:4000])
        journal.check("harness", "the soak harness itself did not fail", False,
                      "no harness error", f"{type(exc).__name__}: {exc}")

    journal.event("run_finished", cycles=cycle, checks=journal.checks,
                  failures=journal.failures, calls=client.calls,
                  server_errors=len(client.server_errors),
                  elapsed=round(time.time() - journal.started, 1))
    server.stop()
    journal.close()
    print(f"cycles {cycle}  checks {journal.checks}  failures {journal.failures}")
    return 1 if journal.failures else 0


def _commit() -> str:
    import subprocess
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                              cwd=ROOT, capture_output=True, text=True,
                              check=True).stdout.strip()
    except Exception:
        return "unknown"


if __name__ == "__main__":
    raise SystemExit(main())
