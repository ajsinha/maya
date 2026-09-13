"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section I — discovery: finding the models nobody registered.

"The hard part of discovery is not finding spreadsheets. It is not finding all
of them." A scanner returning forty thousand candidates has produced a queue
nobody triages, and an untriaged queue is worse than no scan — the estate now
believes it has a discovery programme, and what it has is a table filling up.
The contract exists to stop that, and these cases test it.
"""
from __future__ import annotations

from core.discovery.contract import (CERTAINTY, POOR_PRECISION, REQUIRED,
                                     SWEEP_REQUIRED)
from core.discovery.register import MIN_FOR_PRECISION
from qa.regression_suite.scenarios.common import (BLOCKED, DENIAL, FAIL, PASS,
                                                  Ctx, Result, case, code_of)

#: Two surfaces, and they are not the same door. `/discovery` takes delivery
#: of a sweep (scanner + candidates, idempotent on the fingerprint);
#: `/scanner-contract` is where a sweep is measured against the contract and
#: is the only one that accepts `scope` and `recall_known`.
D = "/api/v1/discovery"
C = "/api/v1/scanner-contract"


def _candidate(ctx: Ctx, **over) -> dict:
    body = {"fingerprint": f"sha256:{ctx.unique('f').replace('-', '')}",
            "location": "//share/models/pricing.xlsx",
            "source": "fileshare", "confidence": 0.6,
            # A DICT, not prose: the matched pattern, the surrounding text,
            # the sheet name. "A triage decision made without it is a guess
            # with a reference number", and a sentence is not those things.
            "evidence": {"pattern": "LINEST(", "sheet": "Pricing",
                         "context": "=LINEST(B2:B400, A2:A400)"},
            "scanner": "qa-scanner-1"}
    body.update(over)
    return body


def _sweep(ctx: Ctx, candidates=None, **over):
    body = {"scanner": "qa-scanner-1", "scope": "two of four drives",
            "recall_known": False,
            "candidates": candidates if candidates is not None
            else [_candidate(ctx)]}
    body.update(over)
    return ctx.api.post(f"{C}/check", json=body, auth=ctx.people["risk"])


def _reached(got) -> bool:
    return code_of(got) not in DENIAL + ("not_found",)


@case("QA-PLT-267", "A sweep reporting confidence 1.0")
def plt_267(ctx: Ctx) -> Result:
    """"A scanner found a file with a regression in it. That is evidence
    somebody built something, not evidence that it is a model." Certainty is
    triage's determination, not the scanner's."""
    got = _sweep(ctx, [_candidate(ctx, confidence=CERTAINTY)])
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if not _reached(got):
        return BLOCKED, f"answered '{code_of(got)}' — not reached"
    if got.status_code < 400 and (got.json() or {}).get("admissible"):
        return FAIL, (f"a candidate at confidence {CERTAINTY} was admitted; "
                      f"the scanner made triage's determination")
    problems = str((got.json() if got.status_code < 500 else {}) or {})
    if "confidence" not in problems and "confidence" not in got.text:
        return FAIL, f"the refusal does not name confidence: {got.text[:130]}"
    return PASS, f"refused at {CERTAINTY}"


@case("QA-PLT-268", "A sweep with recall unknown, stated")
def plt_268(ctx: Ctx) -> Result:
    """"A scanner that says *I swept these four drives and not the other two*
    is worth ten that say nothing." Admitting recall is unknown is the
    ADMISSIBLE case; saying nothing is not."""
    stated = _sweep(ctx, recall_known=False)
    if stated.status_code >= 400:
        return BLOCKED, stated.text[:170]
    if not (stated.json() or {}).get("admissible"):
        return FAIL, (f"a sweep admitting recall is unknown was rejected: "
                      f"{str(stated.json())[:140]}")
    silent = ctx.api.post(f"{C}/check",
                          json={"scanner": "qa-scanner-1",
                                "scope": "two of four drives",
                                "candidates": [_candidate(ctx)]},
                          auth=ctx.people["risk"])
    if silent.status_code >= 400:
        return PASS, f"a silent sweep refused '{code_of(silent)}'"
    if not (silent.json() or {}).get("admissible"):
        return PASS, "stated-unknown admissible, silent not"
    # Establish the mechanism. The contract tests for the key's ABSENCE, and
    # the route's model declares `recall_known: Optional[bool] = None`, so
    # `model_dump()` always supplies it.
    contract = ctx.ui.app.state.ctx.get("scanner_contract")
    reachable = ""
    if contract is not None:
        direct = contract.check({"scanner": "qa-scanner-1",
                                 "scope": "two of four drives",
                                 "candidates": [_candidate(ctx)]})
        if not direct.get("admissible"):
            reachable = (" — the check fires when the key is genuinely "
                         "absent, so it is the route that defeats it")
    return FAIL, (
        "a sweep saying nothing about recall was admitted. The contract tests "
        "`\"recall_known\" not in sweep`, and the route model declares it "
        "`Optional[bool] = None`, so `model_dump()` always supplies the key "
        "and the absence can never be observed over HTTP" + reachable)


@case("QA-PLT-271", "A candidate with no fingerprint")
def plt_271(ctx: Ctx) -> Result:
    """A path is not an identity. A spreadsheet that changes folder arrives
    as a new candidate and the dismissal somebody recorded is lost — which is
    how a monthly sweep re-raises four thousand rows nobody has time to look
    at twice."""
    got = _sweep(ctx, [_candidate(ctx, fingerprint="")])
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400 and (got.json() or {}).get("admissible"):
        return FAIL, "a candidate with no fingerprint was admitted"
    if "fingerprint" not in got.text:
        return FAIL, f"the problem does not name the field: {got.text[:130]}"
    return PASS, "refused, naming the fingerprint"


@case("QA-PLT-266", "One bad row among ninety-nine good ones")
def plt_266(ctx: Ctx) -> Result:
    """The bad row must be named by index. Refusing "a sweep" without saying
    which of a hundred rows is wrong makes a scanner author guess."""
    candidates = [_candidate(ctx) for _ in range(99)]
    candidates.insert(40, _candidate(ctx, confidence=None))
    got = _sweep(ctx, candidates)
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    body = got.json() if got.status_code < 500 else {}
    if got.status_code < 400 and (body or {}).get("admissible"):
        return FAIL, "a sweep with a malformed candidate was admitted whole"
    problems = str((body or {}).get("problems") or got.text)
    if "40" not in problems:
        return FAIL, (f"the bad row is not identified by index, so a scanner "
                      f"author reads a hundred rows to find it: "
                      f"{problems[:140]}")
    return PASS, "the offending row is named by index"


@case("QA-PLT-269", "A sweep with several problems")
def plt_269(ctx: Ctx) -> Result:
    """Reported together. One per round trip makes a scanner author fix a
    contract by binary search."""
    got = _sweep(ctx, [_candidate(ctx, fingerprint="", confidence=CERTAINTY,
                                  evidence={})], scope="")
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    body = got.json() if got.status_code < 500 else {}
    problems = (body or {}).get("problems") or []
    if not problems and got.status_code < 400:
        return FAIL, "a sweep with four problems was admitted"
    if len(problems) < 3:
        return FAIL, (f"four problems produced {len(problems)} report(s), so "
                      f"fixing a sweep takes several attempts")
    return PASS, f"{len(problems)} problems reported together"


@case("QA-PLT-270", "The same candidate ingested twice")
def plt_270(ctx: Ctx) -> Result:
    """Deduplicated on the fingerprint, or a monthly sweep re-raises
    everything somebody already dismissed."""
    candidate = _candidate(ctx)
    deliver = {"scanner": "qa-scanner-1", "candidates": [candidate]}
    first = ctx.api.post(D, json=deliver)
    if first.status_code >= 400:
        return BLOCKED, first.text[:170]
    second = ctx.api.post(D, json=deliver)
    if second.status_code >= 400:
        return BLOCKED, second.text[:170]
    queue = ctx.api.get(f"{D}/candidates", auth=ctx.people["risk"])
    if queue.status_code >= 400:
        return BLOCKED, queue.text[:170]
    # The queue answers `rows`, with a cursor beside it.
    rows = (queue.json() or {}).get("rows") or []
    same = [r for r in rows
            if r.get("fingerprint") == candidate["fingerprint"]]
    if len(same) > 1:
        return FAIL, (f"one artifact appears {len(same)} times in the queue; "
                      f"a monthly sweep re-raises what was dismissed")
    return PASS, "deduplicated on the fingerprint"


@case("QA-PLT-273", "Precision on a scanner with too few triaged candidates")
def plt_273(ctx: Ctx) -> Result:
    """A precision computed from three dismissals is a number somebody will
    scale a programme on. Below the floor it must not be quoted."""
    got = ctx.api.get(D, auth=ctx.people["risk"])
    if got.status_code >= 400:
        return BLOCKED, got.text[:170]
    body = got.json() or {}
    # The estate view answers one `precision` block, not a list per scanner.
    precision = body.get("precision") or {}
    if not precision:
        return BLOCKED, f"no precision block came back: {sorted(body)}"
    # With nothing triaged there is no per-scanner figure at all, and the
    # block says so — the honest answer, since the point of the floor is that
    # a number from three dismissals must not be quoted.
    if precision.get("minimum_judged") != MIN_FOR_PRECISION:
        return FAIL, (f"the published floor is "
                      f"{precision.get('minimum_judged')}, not "
                      f"{MIN_FOR_PRECISION}")
    scanners = precision.get("scanners") or []
    thin = [row for row in scanners
            if (row.get("judged") or 0) < MIN_FOR_PRECISION
            and row.get("precision") is not None
            and row.get("enough_to_read") is not False]
    if thin:
        return FAIL, (f"precision is quoted for {len(thin)} scanner(s) below "
                      f"the floor with nothing saying the number is thin")
    if not scanners and not (precision.get("detail") or "").strip():
        return FAIL, ("no scanner has a precision and the block says nothing, "
                      "so an ungraded programme looks like a graded one")
    return PASS, (f"floor {MIN_FOR_PRECISION} published; "
                  f"{str(precision.get('detail'))[:80]}")


@case("QA-PLT-274", "Recall on any scanner")
def plt_274(ctx: Ctx) -> Result:
    """"Precision the register computes for itself from the dismissals.
    Recall it cannot: it has no idea what the scanner did not look at." A
    computed recall would be the register inventing the one number it has no
    basis for."""
    got = ctx.api.get(D, auth=ctx.people["risk"])
    if got.status_code >= 400:
        return BLOCKED, got.text[:170]
    body = got.json() or {}
    if isinstance((body.get("precision") or {}).get("recall"),
                  (int, float)):
        return FAIL, ("a recall was computed; the register has no idea what "
                      "the scanner did not look at")
    if isinstance(body.get("recall"), (int, float)):
        return FAIL, "a recall was computed at the estate level"
    return PASS, "no recall is computed anywhere"


@case("QA-PLT-4100", "The poor-precision threshold is published")
def plt_4100(ctx: Ctx) -> Result:
    """"Below this precision, scaling a scanner up costs more triage than the
    risk it surfaces. Published so the judgement is arguable rather than
    implicit." """
    got = ctx.api.get(f"{C}", auth=ctx.people["risk"])
    if got.status_code >= 400:
        got = ctx.api.get(D, auth=ctx.people["risk"])
    if got.status_code >= 400:
        return BLOCKED, got.text[:170]
    text = got.text
    if str(POOR_PRECISION) not in text and str(int(POOR_PRECISION * 100)) \
            not in text:
        return FAIL, (f"the {POOR_PRECISION} precision floor is not published, "
                      f"so the judgement to stop scaling a scanner is implicit")
    return PASS, f"the {POOR_PRECISION} floor is published"


@case("QA-PLT-4101", "Every contract field says why it is required")
def plt_4101(ctx: Ctx) -> Result:
    """A scanner author outside this firm reads the contract and nothing
    else. A required field with no reason is one they will send badly."""
    # Two lists: what a CANDIDATE must carry and what a SWEEP must carry.
    both = tuple(REQUIRED) + tuple(SWEEP_REQUIRED)
    mute = [field for field, why in both if not (why or "").strip()]
    if mute:
        return FAIL, f"required with no reason: {mute}"
    if len(both) < 6:
        return FAIL, f"only {len(both)} fields are required in total"
    return PASS, (f"{len(REQUIRED)} candidate and {len(SWEEP_REQUIRED)} sweep "
                  f"fields, each explaining itself")


@case("QA-PLT-272", "Triage the same candidate twice")
def plt_272(ctx: Ctx) -> Result:
    """A second determination on one candidate is two answers, and the
    precision figure is computed from them."""
    candidate = _candidate(ctx)
    made = ctx.api.post(D, json={"scanner": "qa-scanner-1",
                                 "candidates": [candidate]})
    if made.status_code >= 400:
        return BLOCKED, made.text[:170]
    queue = ctx.api.get(f"{D}/candidates", auth=ctx.people["risk"])
    rows = [r for r in ((queue.json() or {}).get("rows") or [])
            if r.get("fingerprint") == candidate["fingerprint"]]
    if not rows:
        return BLOCKED, "the candidate is not in the queue"
    reference = rows[0].get("reference") or rows[0].get("id")
    # `outcome` and `note`, not is_a_model/rationale.
    # Triage needs `model:register`, which the risk manager does not hold.
    first = ctx.api.post(f"{D}/{reference}/triage",
                         json={"outcome": "euc",
                               "note": "a reporting spreadsheet"})
    if first.status_code >= 400:
        return BLOCKED, first.text[:170]
    again = ctx.api.post(f"{D}/{reference}/triage",
                         json={"outcome": "registered",
                               "note": "changed my mind"})
    if again.status_code >= 500:
        return FAIL, f"{again.status_code}"
    if again.status_code < 400:
        return FAIL, ("a candidate was triaged twice with opposite answers; "
                      "the precision figure is computed from these")
    return PASS, f"refused '{code_of(again)}'"
