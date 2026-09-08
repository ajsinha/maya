"""
MAYA — what must be true at every instant, whatever has happened.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.

A scenario that passes says a path works. An invariant that still holds after
six hours says the platform is still the thing it claims to be — and those are
different claims, which come apart in ways only time reveals.

Each of these is checked directly against the running server and against its
database, over and over, between batches of work. They are deliberately cheap,
because something checked once an hour catches a problem an hour late.
"""
from __future__ import annotations

import json
import pathlib
import sqlite3
from typing import Any, Dict


def evidence_chain_verifies(client, journal, state: Dict[str, Any]) -> None:
    """The chain, recomputed rather than trusted.

    MAYA's product is evidence. A chain that verifies after ten appends and
    not after ten thousand from concurrent writers is the failure this whole
    run exists to look for — and it would never appear in a unit test, because
    a unit test's chain is four nodes long.
    """
    status, body = client.get("/evidence/verify", auth=("soak.audit",
                                                        "soak-audit-password-long"))
    if status == 404:
        status, body = client.get("/evidence/chain?verify=true",
                                  auth=("soak.audit", "soak-audit-password-long"))
    intact = status == 200 and not _says_broken(body)
    journal.check("invariant", "the evidence chain still verifies", intact,
                  "intact", f"{status} {json.dumps(body)[:300]}")


def _says_broken(body: Any) -> bool:
    if not isinstance(body, dict):
        return False
    for key in ("intact", "verified", "ok", "valid"):
        if key in body:
            return not bool(body[key])
    return bool(body.get("broken") or body.get("breaks") or body.get("mismatches"))


def evidence_sequence_is_dense(database: pathlib.Path, journal,
                               state: Dict[str, Any]) -> None:
    """No gaps, no duplicates, and never going backwards.

    Read straight from the database rather than through the API, because the
    question is about what was WRITTEN. A sequence with a hole is an append
    that was lost; a sequence with a repeat is two writers that both believed
    they had the lock. The evidence engine takes an advisory lock to make
    exactly this impossible, and this is the assertion that the lock is really
    being taken — under hours of contention rather than in one test.
    """
    try:
        with sqlite3.connect(f"file:{database}?mode=ro", uri=True) as conn:
            rows = conn.execute(
                "SELECT COUNT(*), MIN(seq), MAX(seq), COUNT(DISTINCT seq) "
                "FROM evidence_node").fetchone()
    except Exception as exc:
        journal.check("invariant", "the evidence sequence is readable", False,
                      "readable", f"{type(exc).__name__}: {exc}")
        return
    count, lowest, highest, distinct = rows
    if not count:
        return
    journal.check("invariant", "no two evidence nodes share a sequence number",
                  count == distinct, f"{count} distinct", distinct)
    journal.check("invariant", "the evidence sequence has no gaps",
                  highest - lowest + 1 == count,
                  f"{lowest}..{highest} is {highest - lowest + 1} nodes", count)
    previous = state.get("evidence_high", 0)
    journal.check("invariant", "the evidence sequence never goes backwards",
                  highest >= previous, f">= {previous}", highest)
    state["evidence_high"] = highest
    state["evidence_count"] = count


def schema_has_not_drifted(client, journal) -> None:
    """Nothing the platform does at runtime may change its own shape."""
    status, _ = client.get("/health/schema",
                           auth=("soak.ops", "soak-ops-password-long"))
    if status == 404:
        return          # no endpoint; the database check below covers it
    journal.check("invariant", "the schema has not drifted", status == 200,
                  200, status)


def schema_matches_the_declaration(database: pathlib.Path, journal) -> None:
    """Asked of the database directly, with MAYA's own drift check."""
    import sys
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
    from db.database import Database

    try:
        db = Database(f"sqlite:///{database}")
        gaps = db.drift()
    except Exception as exc:
        journal.check("invariant", "the schema is inspectable", False,
                      "inspectable", f"{type(exc).__name__}: {exc}")
        return
    real = {t: [w for w in why if "no effect on SQLite" not in w]
            for t, why in gaps.items()}
    real = {t: why for t, why in real.items() if why}
    journal.check("invariant", "no table has drifted from the declaration",
                  not real, "no drift", json.dumps(real)[:400])


def nothing_returned_a_500(client, journal, state: Dict[str, Any]) -> None:
    """A 500 is the absence of an answer.

    Every refusal on this platform carries a code, a sentence and a
    remediation. An unhandled exception carries none of those, and design rule
    DR-6 says no failure may be unmapped. So the count must stay at zero for
    the whole run, and the check names the newest one when it does not.
    """
    seen = len(client.server_errors)
    fresh = client.server_errors[state.get("errors_reported", 0):]
    journal.check("invariant", "no request has produced a 500",
                  not fresh, "none",
                  json.dumps(fresh[:3])[:400] if fresh else "none")
    state["errors_reported"] = seen


def resources_are_bounded(server, journal, state: Dict[str, Any]) -> None:
    """Memory, file handles and threads, over hours.

    The reason a soak exists at all. A leak is invisible to a unit suite by
    construction — the process exits before it matters — and the live log
    viewer added a bounded in-memory ring, which is exactly the kind of thing
    that is bounded until it isn't.

    The thresholds are generous and the SHAPE is what matters: growth that
    tracks work done and then flattens is a cache; growth that tracks time is
    a leak.
    """
    health = server.health()
    if not health:
        return
    journal.sample(**health)
    first = state.setdefault("first_health", dict(health))

    rss = health.get("rss_kb")
    if rss and first.get("rss_kb"):
        # Four times the starting resident set, after any amount of work, is
        # not a cache. Stated as a ratio because the absolute number depends
        # on the machine.
        journal.check("invariant", "resident memory is bounded",
                      rss <= max(first["rss_kb"] * 4, first["rss_kb"] + 600_000),
                      f"<= 4x the {first['rss_kb']} kB it started at", f"{rss} kB")
    fds = health.get("fds")
    if fds and first.get("fds"):
        journal.check("invariant", "open file handles are bounded",
                      fds <= first["fds"] + 200,
                      f"<= {first['fds'] + 200}", fds)
    threads = health.get("threads")
    if threads and first.get("threads"):
        journal.check("invariant", "the thread count is bounded",
                      threads <= first["threads"] + 100,
                      f"<= {first['threads'] + 100}", threads)


def the_log_ring_stays_bounded(client, journal) -> None:
    """The viewer added an in-memory ring. Bounded by construction, said the
    commit message; this is the part that watches it be so for six hours."""
    status, body = client.get("/logs?limit=1",
                              auth=("soak.ops", "soak-ops-password-long"))
    if status != 200 or not isinstance(body, dict):
        journal.check("invariant", "the log window is readable", False,
                      200, status)
        return
    held, capacity = body.get("held"), body.get("capacity")
    journal.check("invariant", "the log ring never exceeds its capacity",
                  held is not None and capacity and held <= capacity,
                  f"held <= {capacity}", held)


def no_credential_is_visible(client, journal) -> None:
    """Redaction, checked against the real stream rather than against a unit.

    A live log viewer renders whatever the process wrote. Anything that names
    itself a credential is blanked on the way into the buffer; this asks the
    running server, repeatedly, whether that is still so.
    """
    status, body = client.get("/logs?limit=200&quiet=false",
                              auth=("soak.ops", "soak-ops-password-long"))
    if status != 200 or not isinstance(body, dict):
        return
    text = json.dumps(body.get("lines", []))
    leaked = [needle for needle in
              ("soak-mrm-password-long", "soak-dev-password-long",
               "maya-admin-dev", "soak-owner-password-long")
              if needle in text]
    journal.check("invariant", "no credential appears in the log window",
                  not leaked, "none", leaked)


def the_warrant_epoch_only_rises(client, journal, state: Dict[str, Any]) -> None:
    """Every revocation bumps it, and a descriptor carries the epoch it was
    minted under. An epoch that went backwards would make a revoked credential
    look current again."""
    status, body = client.get("/warrants?live=true",
                              auth=("soak.audit", "soak-audit-password-long"))
    if status != 200 or not isinstance(body, dict):
        return
    epoch = body.get("epoch")
    if epoch is None:
        return
    previous = state.get("epoch", 0)
    journal.check("invariant", "the warrant epoch never goes backwards",
                  epoch >= previous, f">= {previous}", epoch)
    state["epoch"] = epoch


def the_register_only_grows(client, journal, state: Dict[str, Any]) -> None:
    """Nothing in this run retires a model, so the count may only rise.

    A register that quietly loses a row is the failure a governance platform
    cannot have, and it is precisely the sort of thing a long run with
    concurrent writers finds.
    """
    status, body = client.get("/models",
                              auth=("soak.audit", "soak-audit-password-long"))
    if status != 200:
        return
    models = body.get("models", body) if isinstance(body, dict) else body
    if not isinstance(models, list):
        return
    count = len(models)
    previous = state.get("models", 0)
    journal.check("invariant", "the model register never loses a row",
                  count >= previous, f">= {previous}", count)
    state["models"] = count


def latency_has_not_collapsed(client, journal, state: Dict[str, Any]) -> None:
    """Slowing down over hours is a finding even when nothing fails.

    Compared against the first two hundred calls rather than an absolute
    number, because the machine is whatever it is. A tenfold median is not
    load; it is something that grows with the data.
    """
    if len(client.latencies) < 400:
        return
    baseline = state.setdefault(
        "baseline_latency", sorted(client.latencies[:200])[100])
    recent = sorted(client.latencies[-200:])[100]
    state["recent_latency"] = recent
    journal.check("invariant", "median latency has not collapsed",
                  recent <= max(baseline * 10, baseline + 2.0),
                  f"<= 10x the {baseline * 1000:.0f} ms it began at",
                  f"{recent * 1000:.0f} ms")


def the_delta_backend_has_not_changed(client, journal, state) -> None:
    """Which Delta implementation is underneath, asserted every cycle.

    A soak that silently switched implementations partway through would be a
    soak proving nothing about either, and it is one import away from doing so.
    Asked of the RUNNING server rather than of this process, because they are
    different processes and only one of them is the subject.
    """
    # The ROOT path, not one under /api/v1 — which the client prefixes by
    # default, so the first version of this asked for /api/v1/health, got a
    # 404, and returned without recording a check. An invariant that silently
    # checks nothing is the exact defect this file exists to look for, written
    # into the file that looks for it.
    from tools.soak import harness

    status, body = client.get(harness.BASE + "/health", auth=None)
    backend = (body or {}).get("delta", {}).get("backend") \
        if isinstance(body, dict) else None
    if not journal.check("invariant", "the running server reports its Delta backend",
                         status == 200 and backend is not None,
                         "200 naming a backend", f"{status} {backend}"):
        return
    previous = state.get("delta_backend")
    journal.check("invariant", "the Delta backend has not changed mid-run",
                  previous is None or backend == previous,
                  previous or backend, backend)
    state["delta_backend"] = backend


def the_server_is_still_up(server, journal) -> bool:
    alive = server.alive()
    journal.check("invariant", "the server process is still running", alive,
                  "running", "running" if alive else "EXITED")
    return alive
