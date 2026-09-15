"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section I — asking the document subsystem about something that is not there.

Both cases here are about the same failure shape and it is the one this
platform names as its worst: an answer that looks like a real answer. A
compilation of a model nobody registered has every ingredient absent, and a
document compiler is built to tolerate absent ingredients — so the natural
outcome is an empty document about a model that does not exist, which reads on
a screen exactly like a model with nothing recorded against it.
"""
from __future__ import annotations

from qa.regression_suite.scenarios.common import (BLOCKED, DENIAL, FAIL, PASS,
                                                  Ctx, Result, case, code_of)

D = "/api/v1/documents"


def _kind(ctx: Ctx) -> str:
    got = ctx.api.get("/api/v1/document-kinds")
    if got.status_code >= 400:
        return ""
    kinds = (got.json() or {}).get("kinds") or []
    first = kinds[0] if kinds else ""
    return first.get("kind", "") if isinstance(first, dict) else str(first)


@case("QA-PLT-505", "Compile against a model that does not exist")
def plt_505(ctx: Ctx) -> Result:
    """A REAL kind against a URN nobody registered — QA-PLT-127 asks the
    question with both halves unknown, which any dictionary lookup refuses.

    This half is the harder one. Every section the compiler assembles is
    allowed to be empty, because a freshly registered model legitimately has
    nothing recorded yet. So the difference between *a model with nothing in
    it* and *no model* has to be asked before the sections are gathered, and
    if it is not, the compiler's tolerance produces a confident empty document
    about something that was never registered.
    """
    kind = _kind(ctx)
    if not kind:
        return BLOCKED, "no document kind is published"
    absent = f"maya://model/{ctx.unique('never-registered')}"
    # urn and kind are QUERY parameters here, not a body.
    got = ctx.api.post(D, params={"kind": kind, "urn": absent})
    if got.status_code >= 500:
        return FAIL, f"{got.status_code} {got.text[:150]}"
    if code_of(got) in DENIAL:
        return BLOCKED, f"answered '{code_of(got)}' — the caller never reached it"
    if got.status_code >= 400:
        return PASS, f"refused '{code_of(got)}' ({got.status_code})"
    body = got.json() or {}
    return FAIL, (
        f"a '{kind}' document was compiled against {absent}, which is not in "
        f"the register, and the answer is a document rather than a refusal "
        f"(id {body.get('id') or body.get('document_id')}). Every section is "
        f"empty because every section is ALLOWED to be empty, so this is "
        f"indistinguishable on screen from a registered model with nothing "
        f"recorded against it yet")


@case("QA-PLT-506", "Read a document that does not exist")
def plt_506(ctx: Ctx) -> Result:
    """404 on both representations, and the markdown one is the one worth
    asking: it renders rather than returning JSON, so a miss there has a
    second way to come back as an empty page with a 200."""
    missing = ctx.unique("no-such-document")
    answers = []
    for path in (f"{D}/{missing}", f"{D}/{missing}/markdown"):
        got = ctx.api.get(path)
        if got.status_code >= 500:
            return FAIL, f"{path} answered {got.status_code}"
        if code_of(got) in DENIAL:
            return BLOCKED, f"{path} answered '{code_of(got)}' — not reached"
        if got.status_code < 400:
            return FAIL, (f"GET {path} answered {got.status_code} for a "
                          f"document that does not exist, so a mistyped id "
                          f"returns something a reader will take for a "
                          f"document: {got.text[:110]}")
        answers.append(f"{path.rsplit('/', 1)[-1]}={got.status_code}")
    return PASS, f"both refused ({', '.join(answers)})"
