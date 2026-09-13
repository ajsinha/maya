"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Properties, swept across every endpoint that has them.

    python -m qa.regression_suite.sweep --out qa/results/sweep.json

## Why this exists

Ten of the defects this pass has found are one property: **a field the
platform declares required, guarded by a truthiness check, accepting `"   "`**.
They were found one field at a time, in six subsystems, over several hours —
a warrant's declared use, a revocation reason, a finding title, a monitor
owner, and six at once in the feature registry.

Writing a case per field does not scale and never finishes. A property does.
There are around 240 mutating endpoints and each has a handful of required
fields; sweeping the product takes seconds and asks the same question
everywhere, which is the only way to find out whether the answer is
consistent.

## What a sweep is not

It is not the hand-written half of the case list. A sweep asks *is this
property true everywhere*; a case asks *does this control fire in this
situation*, and no sweep will ever ask whether acknowledging a finding
orphans a review comment.

It also cannot tell a refusal from a refusal for the wrong reason. Every
result here is a **candidate**, and the ones that matter are read by a person
before they are called defects.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
import time
from typing import Any, Dict, List

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

#: Paths a sweep must not call: they end the run or never return.
AVOID = ("/admin/shutdown", "/admin/restart", "/api/v1/logs/stream",
         "/logout", "/login")

#: Values that are not values, and what each one asks.
#:
#: Chosen so that every one has an obviously correct answer. A field that
#: accepts a negative count, a NaN, or a value outside its own enumeration is
#: wrong whatever the endpoint does with it afterwards.
STRING_PROBES = {
    "blank": ("   ", "a stated ground accepted blank"),
    "empty": ("", "a required string accepted empty"),
}
NUMBER_PROBES = {
    "negative": (-1, "a count or duration accepted as negative"),
    "huge": (10 ** 15, "a magnitude accepted with no ceiling"),
}
ENUM_PROBE = ("qa-not-a-member", "a closed vocabulary accepted a non-member")

#: Fields whose blankness is a caller's business, not a control.
#:
#: A note, a comment or a description on an act that already carries its
#: reason elsewhere is allowed to be empty; refusing those would be
#: ceremony. The stated GROUNDS are the ones that matter.
NOT_GROUNDS = {"note", "statement", "comment", "quote", "description",
               "justification", "detail", "instruction", "label"}


def _plausible(name: str) -> str:
    return {"semver": "9.9.9", "version": "9.9.9"}.get(name, "qa-sweep")


def _fill(path: str) -> str:
    return re.sub(r"\{([a-z_]+)(?::[a-z]+)?\}",
                  lambda m: _plausible(m.group(1)), path)


def run(client, spec: Dict[str, Any]) -> List[Dict[str, Any]]:
    from qa.regression_suite.shapes import body_for, fields_of
    out: List[Dict[str, Any]] = []
    paths = spec.get("paths", {})
    for path, item in sorted(paths.items()):
        if any(path.startswith(a) for a in AVOID):
            continue
        for method, operation in sorted(item.items()):
            if method.upper() not in ("POST", "PUT", "PATCH"):
                continue
            schema = (operation.get("requestBody", {})
                      .get("content", {}).get("application/json", {})
                      .get("schema"))
            if not schema:
                continue
            body = body_for(method, path, client)
            declared = fields_of(method, path, client)

            def probe(field: str, value: Any, label: str, asks: str,
                      body=body, method=method, path=path) -> None:
                # The loop variables are bound as defaults. Closing over them
                # would make every probe use whatever endpoint the loop
                # happened to end on, and the results would name the wrong
                # path — a report that is confidently about the wrong thing.
                attempt = dict(body)
                attempt[field] = value
                answer = client.request(method.upper(), _fill(path),
                                        json=attempt)
                # A 404 means the sweep never reached the check: the subject
                # in the path does not exist. Not evidence either way, and
                # counting it as a pass would be the loudest false comfort
                # available here.
                if answer.status_code == 404:
                    verdict = "UNREACHED"
                elif answer.status_code >= 500:
                    verdict = "CRASHED"
                elif answer.status_code < 400:
                    verdict = "ACCEPTED"
                else:
                    verdict = "REFUSED"
                out.append({
                    "id": f"SWEEP-{method.upper()}-{path}-{field}-{label}",
                    "method": method.upper(), "path": path, "field": field,
                    "probe": label, "asks": asks,
                    "status": answer.status_code, "verdict": verdict,
                    "evidence": answer.text[:150]})

            for field, child in declared.items():
                if field in NOT_GROUNDS:
                    continue
                kind = child.get("type")
                if child.get("enum"):
                    probe(field, ENUM_PROBE[0], "not-a-member", ENUM_PROBE[1])
                elif kind == "string" or isinstance(body.get(field), str):
                    for label, (value, asks) in STRING_PROBES.items():
                        probe(field, value, label, asks)
                elif kind in ("integer", "number"):
                    for label, (value, asks) in NUMBER_PROBES.items():
                        probe(field, value, label, asks)
    return out


def authorisation(client, observer, spec: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Every mutating endpoint, called by somebody who should not be able to.

    A separate property from the value probes above, and a stronger one: the
    value probes ask whether a field is checked, this asks whether the door
    is. There are around 240 mutating endpoints and a permission check is one
    line each, which is exactly the kind of line that gets left out of the
    one endpoint nobody thought about.

    The observer is an `operator` — authenticated, and holding almost
    nothing. Deliberately not an anonymous caller: that tests the
    authentication layer, which is a different control, and would report
    every endpoint as protected while never reaching an authorisation check.
    """
    from qa.regression_suite.shapes import body_for
    out: List[Dict[str, Any]] = []
    for path, item in sorted(spec.get("paths", {}).items()):
        if any(path.startswith(a) for a in AVOID):
            continue
        for method, operation in sorted(item.items()):
            if method.upper() not in ("POST", "PUT", "PATCH", "DELETE"):
                continue
            body = body_for(method, path, client) if operation.get(
                "requestBody") else None
            answer = observer.request(method.upper(), _fill(path),
                                      json=body if body else None)
            if answer.status_code in (401, 403):
                verdict = "REFUSED"
            elif answer.status_code == 404:
                verdict = "UNREACHED"
            elif answer.status_code >= 500:
                verdict = "CRASHED"
            elif answer.status_code < 400:
                verdict = "ACCEPTED"
            else:
                # A 409/422 means the request got PAST the permission check
                # and was refused on its content. For a caller who should not
                # be here at all, that is the door being open.
                verdict = "PAST-THE-DOOR"
            out.append({
                "id": f"SWEEP-AUTHZ-{method.upper()}-{path}",
                "method": method.upper(), "path": path, "field": "-",
                "probe": "unprivileged", "asks": "the door is checked",
                "status": answer.status_code, "verdict": verdict,
                "evidence": answer.text[:150]})
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="qa/results/sweep.json")
    args = ap.parse_args(argv)
    from qa.regression_suite.harness import live_client
    from qa.regression_suite.shapes import document
    started = time.time()
    with live_client() as (_ui, api, observer):
        spec = document(api)
        results = run(api, spec)
        results.extend(authorisation(api, observer, spec))
    took = time.time() - started
    counts: Dict[str, int] = {}
    for row in results:
        counts[row["verdict"]] = counts.get(row["verdict"], 0) + 1
    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"summary": counts, "seconds": round(took, 1),
                               "results": results}, indent=1),
                   encoding="utf-8")
    print(f"{len(results)} probes in {took:.0f}s — {counts}")
    # Only ACCEPTED is reported, and even that needs reading.
    #
    # `PAST-THE-DOOR` — a 409 or 422 for an unprivileged caller — is
    # AMBIGUOUS and is deliberately not listed as a finding. FastAPI validates
    # the body before the handler runs the permission check, so a malformed
    # request is refused on its content by an endpoint whose door is
    # perfectly well guarded. Reporting 117 of those as defects would have
    # been the loudest wrong answer this sweep could give.
    #
    # And two of the ACCEPTED are correct: an operator holds `scheduler:run`,
    # and break-glass is open to any authenticated principal on purpose —
    # "ask for elevation, nothing is granted by asking". Requiring a
    # permission to request emergency access defeats emergency access.
    door = [r for r in results
            if r["probe"] == "unprivileged"
            and r["verdict"] in ("ACCEPTED", "CRASHED")]
    if door:
        print(f"\n{len(door)} mutating endpoint(s) an unprivileged caller "
              f"got through — read each one against the role's permissions "
              f"before calling it a defect:")
        for row in door[:30]:
            print(f"   {row['verdict']:9s} {row['method']:6s} {row['path']}")

    accepted = [r for r in results
                if r["verdict"] == "ACCEPTED" and r["probe"] != "unprivileged"]
    print(f"\n{len(accepted)} field(s) accepted a value that is not one:")
    for row in accepted[:40]:
        print(f"   {row['method']:6s} {row['path']:52s} {row['field']} "
              f"({row['probe']})")
    if len(accepted) > 40:
        print(f"   … and {len(accepted) - 40} more")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
