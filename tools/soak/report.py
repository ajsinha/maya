"""
MAYA — render the soak journal as a document somebody can audit.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.

    python tools/soak/report.py [journal.jsonl] [-o report.md]

The journal is one JSON object per check, per event and per resource sample.
This turns it into prose, tables and a resource trace — and, deliberately, it
does NOT summarise the failures away. A soak report whose headline is "all
good" is a report nobody can check; every failed assertion appears in full,
with what was expected, what came back, and when.
"""
from __future__ import annotations

import argparse
import collections
import json
import pathlib
import statistics
from typing import Any, Dict, List

ROOT = pathlib.Path(__file__).resolve().parents[2]


def load(path: pathlib.Path) -> List[Dict[str, Any]]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except ValueError:
            # A run killed mid-write leaves a partial last line. Reporting the
            # truncation is better than refusing to render five hours of work.
            rows.append({"kind": "event", "what": "truncated_journal_line",
                         "detail": {"raw": line[:200]}})
    return rows


def clock(seconds: float) -> str:
    seconds = int(seconds)
    return f"{seconds // 3600}h {seconds % 3600 // 60:02d}m {seconds % 60:02d}s"


def sparkline(values: List[float], width: int = 60) -> str:
    """A trace in text, because the SHAPE is the finding.

    Growth that tracks work done and then flattens is a cache; growth that
    tracks time is a leak, and a single number at the end cannot tell you
    which.
    """
    if not values:
        return ""
    blocks = "▁▂▃▄▅▆▇█"
    step = max(1, len(values) // width)
    sampled = values[::step][:width]
    low, high = min(sampled), max(sampled)
    if high == low:
        return blocks[0] * len(sampled)
    return "".join(
        blocks[min(len(blocks) - 1,
                   int((v - low) / (high - low) * (len(blocks) - 1)))]
        for v in sampled)


FAMILY_NOTES = {
    "startup": "The server came up and answered. Everything below assumes it.",
    "bootstrap": "The six personas and one service principal the run acts as. "
                 "Duties are separated here because they are separated in the "
                 "platform — no single account can walk the whole path, and a "
                 "soak that ran as `admin` throughout would exercise none of "
                 "the segregation this system's argument rests on.",
    "lifecycle": "A model from registration to a signed, executable warrant: "
                 "register, tier, version, quorum, submit the record, approve "
                 "it, attest it with two roles, promote to prod, issue a "
                 "standing warrant, resolve a descriptor. Repeated every "
                 "cycle against a database that is filling up, because a "
                 "control that works on an empty register and not a full one "
                 "fails in production and nowhere else.",
    "refusals": "The controls, tried directly. A refusal nobody attempts is a "
                "claim rather than a control, and every one of these has a "
                "specific way it could silently start permitting: a use that "
                "was never approved, a principal with no entitlement, an "
                "environment nothing was promoted to, a duplicate semver, an "
                "auditor writing, a developer promoting, one person holding "
                "both halves of a separated duty, a password under the floor.",
    "features": "A scalar, a twelve-element array and a 3×3 matrix, defined "
                "and read back resolved. Shapes are here because they were "
                "once accepted at definition and unusable afterwards — a "
                "definition the platform took and could not honour.",
    "concurrency": "Four writers at the evidence chain at the same instant. "
                   "The engine takes an advisory lock so the sequence stays "
                   "dense and unique; one caller can never show the lock is "
                   "really taken, and the sequence invariant below is what "
                   "makes this phase mean something.",
    "surfaces": "The read endpoints a script actually calls. Cheap, and worth "
                "repeating: they are the most likely to be broken by something "
                "else changing, and a 500 in any of them is the one outcome "
                "this platform has no story for.",
    "screens": "Every screen a signed-in person can reach, still rendering. A "
               "screen nobody can click to is not built — and one that fails "
               "after six hours of use is worse than one that was never there.",
    "apikeys": "A key that works, a key that has been revoked, and the "
               "difference stated in the refusal rather than left to be "
               "inferred from a generic 401.",
    "batch": "The governance batch, run on demand. It is idempotent by design, "
             "so running it every fifth cycle tests that claim rather than "
             "costing anything.",
    "details": "The pages that answer *what is this thing*, asked about a "
               "feature and a model this cycle actually created. Here because "
               "two of them were unreachable and nothing noticed: a detail "
               "page that renders only when somebody types its URL is a page "
               "no test and no person ever opens.",
    "evidence": "The chain, read as an auditor would read it.",
    "invariant": "What must be true at every instant, whatever has happened. "
                 "These are the reason a soak is worth six hours rather than "
                 "six minutes: a chain verifies easily after ten appends, and "
                 "the question is whether it still verifies after thousands "
                 "from concurrent writers.",
    "harness": "The soak harness itself. A failure here invalidates the run "
               "rather than the platform, and saying so is the point.",
}


def render(rows: List[Dict[str, Any]]) -> str:
    checks = [r for r in rows if r.get("kind") == "check"]
    events = [r for r in rows if r.get("kind") == "event"]
    samples = [r for r in rows if r.get("kind") == "sample"]
    failures = [c for c in checks if not c["ok"]]

    started = next((e for e in events if e.get("what") == "run_started"), {})
    finished = next((e for e in events if e.get("what") == "run_finished"), {})
    aborted = [e for e in events if e.get("what") in
               ("run_aborted", "run_interrupted", "harness_error")]
    server_errors = [e for e in events if e.get("what") == "server_error"]
    cycles = [e for e in events if e.get("what") == "cycle_finished"]
    detail = started.get("detail", {})
    elapsed = finished.get("detail", {}).get("elapsed") or (
        rows[-1]["at"] if rows else 0)

    out: List[str] = []
    w = out.append

    w("# MAYA — six-hour soak run")
    w("")
    w("> **What this is.** A live MAYA server, driven through its HTTP API and "
      "its screens for six hours, with the platform's own invariants asserted "
      "between every batch of work. The unit suite answers *does each part "
      "behave*. This answers *does the platform still tell the truth after "
      "hours of use* — and those come apart in ways only time reveals.")
    w("")
    w("> **How to read it.** Every assertion made during the run is counted "
      "below and every failed one is reproduced in full, with what was "
      "expected and what came back. Nothing is summarised away. A soak report "
      "whose headline is *all good* is a report nobody can check.")
    w("")

    # ---------------------------------------------------------- the verdict
    passed = len(checks) - len(failures)
    verdict = "PASSED" if not failures and not aborted else "FAILED"
    w("## The result")
    w("")
    w("| | |")
    w("|---|---|")
    w(f"| **Verdict** | **{verdict}** |")
    w(f"| Duration | {clock(elapsed)} |")
    w(f"| Cycles completed | {len(cycles)} |")
    w(f"| Assertions made | {len(checks):,} of a 3,000 budget |")
    w(f"| Passed | {passed:,} |")
    w(f"| Failed | {len(failures):,} |")
    w(f"| HTTP calls | {finished.get('detail', {}).get('calls', '—'):,} |"
      if isinstance(finished.get("detail", {}).get("calls"), int)
      else "| HTTP calls | — |")
    background = finished.get("detail", {}).get("background_calls")
    if background is None:
        windows = [e for e in events if e.get("what") == "load_window"]
        background = windows[-1]["detail"]["background_calls"] if windows else 0
    w(f"| Background requests between cycles | {background:,} |")
    w(f"| Responses that were 500s | {len(server_errors)} |")
    w(f"| Commit under test | `{detail.get('commit', 'unknown')}` |")
    w(f"| Python | {detail.get('python', '—')} |")
    w("")
    if verdict == "PASSED":
        w(f"Every assertion held, across {clock(elapsed)} and a database that "
          "grew throughout. The invariants matter more than the scenarios "
          "here: a scenario passing says a path works, and an invariant still "
          "holding at the end says the platform is still the thing it claims "
          "to be.")
    else:
        w("**The run did not pass.** Every failure is reproduced below in "
          "full. A failing soak is more useful than a passing one and this "
          "section deliberately does not soften it.")
    w("")

    # ---------------------------------------------------------- the failures
    w("## Failures")
    w("")
    if not failures:
        w("None. Every one of the "
          f"{len(checks):,} assertions held.")
    else:
        w(f"{len(failures)} of {len(checks):,} assertions failed. Each is "
          "given with the time it happened, so it can be lined up against the "
          "resource trace and the cycle log below.")
        w("")
        w("| At | Family | Assertion | Expected | Got |")
        w("|---|---|---|---|---|")
        for f in failures:
            w(f"| {clock(f['at'])} | {f['family']} | {_cell(f['name'])} "
              f"| {_cell(f['expected'])} | {_cell(f['got'])} |")
    w("")
    if aborted:
        w("### The run did not finish cleanly")
        w("")
        for event in aborted:
            w(f"- `{event['what']}` at {clock(event['at'])}: "
              f"`{_cell(event.get('detail'))}`")
        w("")
    if server_errors:
        w("### Requests that produced a 500")
        w("")
        w("A refusal on this platform carries a code, a sentence and a "
          "remediation. A 500 carries none of those; design rule DR-6 says no "
          "failure may be unmapped.")
        w("")
        for e in server_errors[:40]:
            d = e.get("detail", {})
            w(f"- {clock(e['at'])} `{d.get('method')} {d.get('path')}` → "
              f"{d.get('status')} — `{_cell(d.get('body'))}`")
        w("")

    # ------------------------------------------------------- what was tested
    w("## What was tested, and why")
    w("")
    by_family = collections.Counter(c["family"] for c in checks)
    fails_by_family = collections.Counter(f["family"] for f in failures)
    for family, count in sorted(by_family.items(),
                                key=lambda kv: -kv[1]):
        bad = fails_by_family.get(family, 0)
        w(f"### {family} — {count:,} assertions"
          + (f", **{bad} failed**" if bad else ", all passed"))
        w("")
        w(FAMILY_NOTES.get(family, ""))
        w("")
        names = collections.Counter(c["name"] for c in checks
                                    if c["family"] == family)
        w("| Assertion | Times checked | Failed |")
        w("|---|---:|---:|")
        for name, n in sorted(names.items()):
            nfail = sum(1 for f in failures
                        if f["family"] == family and f["name"] == name)
            w(f"| {_cell(name)} | {n} | {nfail or ''} |")
        w("")

    # --------------------------------------------------------- the resources
    w("## Resources over the run")
    w("")
    w("A soak that does not measure these is a functional test that took six "
      "hours. A leak is invisible to a unit suite by construction — the "
      "process exits before it matters. The **shape** is the finding: growth "
      "that tracks work done and then flattens is a cache; growth that tracks "
      "time is a leak.")
    w("")
    if samples:
        w("| Metric | At the start | At the end | Peak | Trace |")
        w("|---|---:|---:|---:|---|")
        for key, label, scale, unit in (
                ("rss_kb", "Resident memory", 1 / 1024.0, "MB"),
                ("fds", "Open file handles", 1, ""),
                ("threads", "Threads", 1, ""),
                ("db_bytes", "Database size", 1 / 1048576.0, "MB")):
            series = [s[key] for s in samples if key in s]
            if not series:
                continue
            w(f"| {label} | {series[0] * scale:,.1f}{unit} "
              f"| {series[-1] * scale:,.1f}{unit} "
              f"| {max(series) * scale:,.1f}{unit} "
              f"| `{sparkline(series)}` |")
        w("")
    else:
        w("No resource samples were recorded.")
        w("")

    w("### Latency")
    w("")
    if cycles:
        took = [c["detail"]["took"] for c in cycles if "took" in c.get("detail", {})]
        if took:
            w(f"Each cycle of work took a median of **{statistics.median(took):.1f}s** "
              f"(fastest {min(took):.1f}s, slowest {max(took):.1f}s) across "
              f"{len(took)} cycles.")
            w("")
            w(f"`{sparkline(took)}`")
            w("")
            w("A cycle does the same work every time. A trace that climbs is "
              "the platform getting slower as its register fills, which is a "
              "finding even when nothing fails.")
            w("")

    # ------------------------------------------------------------ the cycles
    w("## Cycle log")
    w("")
    w("One line per cycle: the work done, the assertions made, and how long "
      "the runner then rested to spread the budget across the full duration.")
    w("")
    w("| Cycle | Finished at | Took | Assertions so far | Failures | Rested |")
    w("|---:|---|---:|---:|---:|---:|")
    for c in cycles:
        d = c["detail"]
        w(f"| {d.get('cycle')} | {clock(c['at'])} | {d.get('took', 0):.1f}s "
          f"| {d.get('checks', 0):,} | {d.get('failures', 0)} "
          f"| {d.get('resting', 0):.0f}s |")
    w("")

    # ------------------------------------------------------------- the notes
    w("## What a passing run does and does not prove")
    w("")
    w("**It proves** that the governed path works end to end, repeatedly, "
      "against a register that grows the whole time; that the controls refuse "
      "when they should, on the thousandth attempt as on the first; that the "
      "evidence chain stays verifiable and its sequence dense and unique under "
      "concurrent writers; that the schema does not drift at runtime; that no "
      "request produced an unmapped failure; and that memory, file handles and "
      "threads stay bounded over hours.")
    w("")
    w("**It does not prove** anything about PostgreSQL — this run is SQLite, "
      "which is the shipped default and not what a bank deploys. It does not "
      "prove behaviour under real concurrency at scale: four simultaneous "
      "writers is enough to make an advisory lock matter and is not a load "
      "test. It does not exercise a restart mid-transaction, a disk filling "
      "up, or a clock moving. And it cannot prove the absence of a control "
      "nobody thought to try — every refusal asserted here is one somebody "
      "chose to attempt.")
    w("")
    w("---")
    w("")
    w(f"*Rendered from `{len(rows):,}` journal records by "
      f"`tools/soak/report.py`. The journal is committed beside this file, so "
      f"every number here can be recomputed.*")
    return "\n".join(out) + "\n"


def _cell(value: Any) -> str:
    text = value if isinstance(value, str) else json.dumps(value, default=str)
    text = text.replace("|", "\\|").replace("\n", " ")
    return text[:300] + ("…" if len(text) > 300 else "")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("journal", nargs="?",
                   default=str(ROOT / "docs" / "soak" / "soak-journal.jsonl"))
    p.add_argument("-o", "--out",
                   default=str(ROOT / "docs" / "soak" / "SOAK-REPORT.md"))
    args = p.parse_args()
    path = pathlib.Path(args.journal)
    if not path.is_file():
        print(f"no journal at {path}")
        return 1
    body = render(load(path))
    pathlib.Path(args.out).write_text(body, encoding="utf-8")
    print(f"wrote {args.out} ({len(body.splitlines())} lines)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
