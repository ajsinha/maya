"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Executing the generated half of the case list, one case at a time.

    python -m tools.qa.run --section A          # one section
    python -m tools.qa.run                      # A, B, C, E
    python -m tools.qa.run --out docs/QA/results/pass1.json

## What this runs and what it cannot

Sections **A, B, C and E** are derived from `openapi.lock.json` and the navbar,
so each one names a method, a path and an expectation, and can be *called*.
This calls them against a real application against a throwaway database, and
records the status, the refusal code and the verdict for every single case.

Section **D** — every mapped refusal code, provoked — is not runnable this way
and this file does not pretend otherwise. Provoking `segregation_of_duties`
means building two principals, an approval and a conflict; there are 591 of
them and no generic driver constructs 591 different states. They are verified
by a different method in `tools/qa/refusals.py`, and the log says which method
answered which case, because a reader who cannot tell "called it" from
"reasoned about it" has been given one number for two different claims.

## The verdicts

`PASS`      the expectation held
`FAIL`      the expectation did not hold — a defect **or** a bad case
`BLOCKED`   could not be reached; the reason is recorded per case

A `FAIL` is not a defect until somebody has read it. Pass 1 of the earlier,
smaller list produced 33 bad cases against 22 real defects, and recording them
as defects would have made the platform look worse than it is while burying
the ones that mattered.

## Why a throwaway database

Every mutating operation in section A is actually performed. The runner
registers, approves, deletes and revokes; against a register anybody cares
about that is destruction, not testing.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.qa.enumerate import (_path_params, _required, operations, screens)

#: Path parameters get a value that is syntactically plausible for their name.
#: A `{semver}` filled with "does-not-exist" is refused by *validation* before
#: the lookup, which answers 422 and tests nothing about the lookup.
PLAUSIBLE: Dict[str, str] = {
    "semver": "9.9.9", "version": "9.9.9", "epoch": "1", "seq": "1",
    "year": "2026", "month": "1", "day": "1", "at": "1",
    "port": "1", "limit": "1", "offset": "0", "n": "1",
}

#: The value used when a path parameter names something that should not exist.
ABSENT = "qa-does-not-exist"

SKIP_PATHS = (
    # Shutting the server down mid-run ends the run, and the case is a
    # statement about operations rather than about the register.
    "/admin/shutdown", "/admin/restart",
    # A long-lived `text/event-stream`. A plain call never returns, and this
    # blocked the first attempt at this run for eighteen minutes with nothing
    # written — which is why the runner now traces as it goes.
    #
    # Recorded BLOCKED rather than skipped silently: the endpoint is real and
    # needs a case, it just needs one that reads a few events and disconnects
    # rather than one that waits for the response to end. That case belongs in
    # the hand-written sections, and saying so is the difference between a gap
    # somebody can close and a gap nobody can see.
    "/api/v1/logs/stream",
)

#: Operations that end the caller's session. Called, then signed back in.
SESSION_ENDING = ("/logout", "/login")


class Case(dict):
    """One case, its expectation, and what happened."""


def _fill(path: str, value_for) -> str:
    def sub(m):
        name = m.group(1)
        return value_for(name)
    return re.sub(r"\{([a-z_]+)(?::[a-z]+)?\}", sub, path)


def _expected_status(expect: str) -> Optional[int]:
    m = re.search(r"\((\d{3})", expect)
    return int(m.group(1)) if m else None


def _body_for(spec: Dict[str, Any], omit: Tuple[str, ...] = ()) -> Dict[str, Any]:
    """A body carrying every declared field, minus the ones being omitted.

    Values are deliberately generic. This section asks whether an operation
    *answers*, not whether it accepts good data — a case that failed because
    the runner guessed a domain value wrongly would be a bad case, and 603 of
    those would drown the run.
    """
    out: Dict[str, Any] = {}
    for field in (spec.get("body") or []):
        name = field.rstrip("!")
        if name in omit:
            continue
        out[name] = f"qa-{name}"
    return out


class Runner:
    """Executes cases and writes each result the moment it has one.

    Incremental, not batched at the end. The first attempt at this run buffered
    everything and blocked on some endpoint eighteen minutes in — and because
    nothing had been written, there was no way to tell *which* endpoint from
    outside the process. A runner whose progress is invisible is a runner you
    have to restart to learn anything from.
    """

    def __init__(self, client, verbose: bool = False, trace=None, api=None):
        self.client, self.verbose = client, verbose
        # `/api/v1/...` goes to the API client — Basic credentials, no session
        # cookie, no CSRF, which is what an API caller is. Everything else is a
        # page and goes to the browser-shaped client.
        self.api = api or client
        self.results: List[Case] = []
        self.trace = trace

    # ------------------------------------------------------------------ call
    def _call(self, method: str, path: str,
              body: Optional[Dict[str, Any]] = None,
              auth: Optional[Tuple[str, str]] = None):
        if self.trace:
            self.trace.write(f"CALL {method} {path}\n")
            self.trace.flush()
        client = self.api if path.startswith("/api/") else self.client
        if path in SESSION_ENDING:
            # Called, then undone. `/logout` is a real operation and deserves
            # its case; it must not silently sign the rest of the run out.
            from tools.qa.harness import sign_in
            response = client.request(method, path)
            sign_in(self.client)
            from tools.qa.harness import carry_csrf
            carry_csrf(self.client)
            return response
        kwargs: Dict[str, Any] = {}
        if body is not None and method in ("POST", "PUT", "PATCH"):
            kwargs["json"] = body
        if auth is not None:
            kwargs["auth"] = auth
        return client.request(method, path, **kwargs)

    def _record(self, case_id: str, section: str, area: str, title: str,
                expect: str, status: Optional[int], verdict: str,
                evidence: str, method_used: str = "called") -> None:
        self.results.append(Case(
            id=case_id, section=section, area=area, title=title,
            expect=expect, status=status, verdict=verdict,
            evidence=evidence[:400], method=method_used))
        if self.trace:
            self.trace.write(f"  {verdict:8s} {case_id} {title[:80]}\n")
            self.trace.flush()
        if self.verbose:
            print(f"  {verdict:8s} {case_id}  {title[:70]}")

    # --------------------------------------------------------------- section
    def _cases(self, section_prefix: str):
        """The published cases for one section, in published order.

        Taken from `tools.qa.enumerate.build()` — the same function that
        writes the case list — rather than re-derived here. The first version
        of this minted its own ids (`QA-APIKEYS-B001`) and 359 results then
        matched nothing in the published list, so the run could report a
        coverage percentage of a numbering only it used.
        """
        from tools.qa.enumerate import build
        for name, cases in build().items():
            if name.startswith(section_prefix):
                yield from cases

    @staticmethod
    def _target(steps: str) -> Tuple[str, str]:
        """`METHOD /path` out of a case's steps line."""
        head = steps.split(" — ")[0].split(" omitting")[0].split(" with ")[0]
        parts = head.strip().split(" ", 1)
        return (parts[0], parts[1].strip()) if len(parts) == 2 else ("GET", "/")

    def section_a(self) -> None:
        """Every operation answers on the happy path."""
        specs = {(m, p): s for m, p, s in operations()}
        for entry in self._cases("A."):
            method, path = self._target(entry["steps"])
            spec = specs.get((method, path), {})
            if any(path.startswith(skip) for skip in SKIP_PATHS):
                self._record(entry["id"], "A", entry["area"], entry["title"],
                             entry["expect"], None, "BLOCKED",
                             "not callable by a generic driver: it either "
                             "stops the server or streams without ending. "
                             "Needs a hand-written case")
                continue
            called = _fill(path, lambda n: PLAUSIBLE.get(n, ABSENT))
            r = self._call(method, called, _body_for(spec))
            ok = r.status_code < 500 or (
                r.status_code == 501 and '"error"' in r.text)
            self._record(entry["id"], "A", entry["area"], entry["title"],
                         entry["expect"], r.status_code,
                         "PASS" if ok else "FAIL",
                         f"{method} {called} -> {r.status_code} {r.text[:160]}")

    def section_b(self) -> None:
        """A required field, omitted."""
        specs = {(m, p): s for m, p, s in operations()}
        for entry in self._cases("B."):
            method, path = self._target(entry["steps"])
            spec = specs.get((method, path), {})
            required = tuple(_required(spec))
            called = _fill(path, lambda n: PLAUSIBLE.get(n, ABSENT))
            r = self._call(method, called, _body_for(spec, omit=required))
            # 422 is the expectation. An earlier refusal — the subject in the
            # path does not exist either — is a different correct answer to a
            # request that is wrong twice.
            verdict = ("PASS" if r.status_code in (401, 403, 404, 409, 422, 423)
                       else "FAIL")
            self._record(entry["id"], "B", entry["area"], entry["title"],
                         entry["expect"], r.status_code, verdict,
                         f"{method} {called} omitting {list(required)} -> "
                         f"{r.status_code} {r.text[:150]}")

    def section_c(self) -> None:
        """An identifier that does not exist."""
        specs = {(m, p): s for m, p, s in operations()}
        for entry in self._cases("C."):
            method, path = self._target(entry["steps"])
            spec = specs.get((method, path), {})
            names = _path_params(path)
            if not names:
                continue
            if any(path.startswith(skip) for skip in SKIP_PATHS):
                self._record(entry["id"], "C", entry["area"], entry["title"],
                             entry["expect"], None, "BLOCKED", "stops the server")
                continue
            called = _fill(path, lambda n, first=names[0]:
                           ABSENT if n == first else PLAUSIBLE.get(n, ABSENT))
            r = self._call(method, called, _body_for(spec))
            # The narrow claim: an unknown id must not produce a 500. Which
            # 4xx is a judgement the hand-written sections make case by case.
            verdict = ("PASS"
                       if r.status_code in (400, 401, 403, 404, 409, 410, 422, 423)
                       else "FAIL")
            self._record(entry["id"], "C", entry["area"], entry["title"],
                         entry["expect"], r.status_code, verdict,
                         f"{method} {called} -> {r.status_code} {r.text[:150]}")

    def section_e(self, observer=None) -> None:
        """Every screen, for somebody who may see it and somebody who may not."""
        entries = list(self._cases("E."))
        pairs = list(screens())
        for index, (path, _title, _permission) in enumerate(pairs):
            allowed = entries[index * 2] if index * 2 < len(entries) else None
            refused_case = (entries[index * 2 + 1]
                            if index * 2 + 1 < len(entries) else None)
            r = self._call("GET", path)
            if allowed:
                self._record(allowed["id"], "E", "screen", allowed["title"],
                             allowed["expect"], r.status_code,
                             "PASS" if r.status_code == 200 else "FAIL",
                             f"GET {path} as admin -> {r.status_code}")
            if refused_case is None:
                continue
            if observer is None:
                self._record(refused_case["id"], "E", "screen",
                             refused_case["title"], refused_case["expect"],
                             None, "BLOCKED",
                             "no unprivileged principal was provided")
                continue
            if self.trace:
                self.trace.write(f"CALL(observer) GET {path}\n")
                self.trace.flush()
            got = observer.get(path)
            # A UI route answers 200 with the sign-in form when the caller
            # cannot see the page, so the assertion is on CONTENT.
            refused = (got.status_code in (401, 403)
                       or "sign in" in got.text.lower()
                       or "not permitted" in got.text.lower())
            self._record(refused_case["id"], "E", "screen",
                         refused_case["title"], refused_case["expect"],
                         got.status_code, "PASS" if refused else "FAIL",
                         f"GET {path} unprivileged -> {got.status_code}")


def summarise(results: List[Case]) -> Dict[str, Any]:
    by_section: Dict[str, Dict[str, int]] = {}
    for r in results:
        bucket = by_section.setdefault(r["section"], {})
        bucket[r["verdict"]] = bucket.get(r["verdict"], 0) + 1
    return {
        "total": len(results),
        "pass": sum(1 for r in results if r["verdict"] == "PASS"),
        "fail": sum(1 for r in results if r["verdict"] == "FAIL"),
        "blocked": sum(1 for r in results if r["verdict"] == "BLOCKED"),
        "by_section": by_section,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--section", action="append",
                    choices=["A", "B", "C", "E"], default=None)
    ap.add_argument("--out", default="docs/QA/results/generated.json")
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--trace", default="docs/QA/results/.trace.log",
                    help="where to write progress as it happens, so a run "
                         "that blocks says what it blocked on")
    args = ap.parse_args(argv)
    sections = args.section or ["A", "B", "C", "E"]

    from tools.qa.harness import live_client
    started = time.time()
    trace_path = pathlib.Path(args.trace)
    trace_path.parent.mkdir(parents=True, exist_ok=True)
    runner = None
    with (trace_path.open("w", encoding="utf-8") as trace,
          live_client() as (client, api, observer)):
            runner = Runner(client, verbose=args.verbose, trace=trace, api=api)
            for name in sections:
                print(f"running section {name} ...", flush=True)
                trace.write(f"== section {name} ==\n")
                trace.flush()
                if name == "E":
                    runner.section_e(observer)
                else:
                    getattr(runner, f"section_{name.lower()}")()
    took = time.time() - started

    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    summary = summarise(runner.results)
    out.write_text(json.dumps(
        {"summary": summary, "seconds": round(took, 1),
         "results": runner.results}, indent=1), encoding="utf-8")
    print(f"\n{summary['total']} cases in {took:.0f}s — "
          f"{summary['pass']} pass, {summary['fail']} fail, "
          f"{summary['blocked']} blocked")
    for section, counts in sorted(summary["by_section"].items()):
        print(f"  {section}: {counts}")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
