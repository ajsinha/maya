#!/usr/bin/env python3
"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

CASE STUDY 7 — An LLM drafting model documentation, governed as a model.

    A language model drafts the "model description" section of a validation
    pack from the evidence MAYA already holds. It is a capability, it is
    registered, and every claim it makes has to cite something.

**An AI capability IS a model under this platform's definition.** `P` is a
prompt and a configuration, `X` is the context it is given, `D(Y)` is a
distribution over text. Nothing in `f : P (x) X -> D(Y)` needed changing to
accommodate it, which is the argument for having had a definition rather than a
list.

**MAYA does not call the language model.** Ask it which providers are usable
and it answers, of Anthropic and OpenAI: *"MAYA does not call the API. Nothing
here is wired to an egress path, a credential, or a confidentiality decision
about what may leave the institution."* That is the same boundary as "MAYA does
not train models" — the bank's own inference runs wherever the bank runs it,
and MAYA records what came back and refuses what should be refused.

So the "model" in this script is a deterministic stand-in, and it is a stand-in
for the bank's egress path rather than for the platform's.

**The three controls this case study exists to show.**

    TIER C IS REFUSED     a capability that can be neither checked nor grounded
                          is advisory, and advisory AI is a chat window
    GROUNDING REMOVES     unsupported claims are taken OUT, not flagged — and
                          kept, separately, for the reviewer
    ATTESTATION IS A      nothing is evidence until a person signs for it, and
    DIFFERENT ACT         never the person who asked
"""
from __future__ import annotations

import hashlib
import pathlib
import sys
from typing import Any, Dict, List

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from _common.casekit import (Say, attempt, connect, document,
                             ensure_cast, expect_refusal, latex_escape, parse,
                             save_json, table)

HERE = pathlib.Path(__file__).resolve().parent

#: The capability being registered. Tier B: every claim cites evidence.
CAPABILITY = "doc.model_description"
TIER_B, TIER_C = "B", "C"

#: The subject. A model already in the register — case study 4's, so this one
#: documents something a previous case study built rather than inventing a
#: subject nobody can look at.
SUBJECT_TYPE, SUBJECT_URN = "model", "maya://model/wholesale.credit.merton_dd"

#: The prompt is the parameter object. What is registered is its DIGEST: a copy
#: of the text would be a copy somebody can edit, and "this generation came
#: from that prompt" is exactly what a digest answers and a copy does not.
PROMPT = (
    "You are drafting the model description section of a validation pack.\n"
    "Use ONLY the evidence provided. Every sentence must cite an evidence id.\n"
    "State what the model is, how its parameters are inhabited, and what its\n"
    "stated limitations are. Do not speculate about performance.\n"
)
PROMPT_DIGEST = "sha256:" + hashlib.sha256(PROMPT.encode()).hexdigest()


# ==================================== the bank's own model, standing in here
def draft_description(evidence: Dict[str, str]) -> List[Dict[str, Any]]:
    """What the bank's LLM returned. Deterministic, so the demo is checkable.

    Five claims. Four of them cite evidence MAYA holds. The fifth is the point
    of the whole case study: a fluent, plausible, entirely unsupported sentence
    of the kind these systems produce constantly — and it cites an evidence id
    that does not exist.
    """
    return [
        {"id": "c1",
         "text": "The model is a Merton structural default probability for "
                 "large corporate obligors.",
         "citations": ["ev-registration"]},
        {"id": "c2",
         "text": "Its parameter object is terminal: the class is T0 and there "
                 "is nothing to fit.",
         "citations": ["ev-version"]},
        {"id": "c3",
         "text": "The version was approved by two signatories in two roles "
                 "before any warrant was issued.",
         "citations": ["ev-approval", "ev-quorum"]},
        {"id": "c4",
         "text": "Asset value and asset volatility are not observable and are "
                 "inferred, which is recorded as a stated limitation.",
         "citations": ["ev-limitation"]},
        # The hallucination. Fluent, specific, plausible, and citing an
        # evidence node that was never created.
        {"id": "c5",
         "text": "Backtesting over the 2019-2024 period showed an area under "
                 "the ROC curve of 0.87, comfortably above the 0.75 threshold "
                 "in the model risk policy.",
         "citations": ["ev-backtest-2024"]},
    ]


#: What MAYA actually holds. `ev-backtest-2024` is deliberately absent.
KNOWN_EVIDENCE = ["ev-registration", "ev-version", "ev-approval", "ev-quorum",
                  "ev-limitation"]


# ================================================================== the build
def main() -> int:
    args = parse("Case study 7 — an LLM capability, governed")
    out = pathlib.Path(args.out) if args.out else HERE
    say = Say("CASE STUDY 7 — an LLM drafting documentation (AI Tier B)")

    maya = connect(args)
    say.step("Make sure the people exist")
    people = ensure_cast(maya, args.url)

    # --------------------------------------------------- 1. the boundary
    say.step("Ask MAYA which providers it can reach")
    providers = maya.assist.providers().get("providers", [])
    for p in providers:
        mark = "usable" if p.get("usable") else "NOT usable"
        print(f"    {p.get('provider'):12} {mark}")
        if p.get("why_not"):
            print(f"                 {p['why_not'][:96]}")
    say.note("this is the same boundary as 'MAYA does not train models'. The "
             "inference runs wherever the bank runs it; MAYA records what came "
             "back")

    # ------------------------------------------------------ 2. the tiers
    say.step("The three tiers, and why one of them is not registrable")
    tiers = maya.assist.tiers()
    for row in (tiers.get("tiers") or []):
        print(f"    Tier {row.get('tier')}: {str(row.get('means'))[:98]}")

    say.step("Try to register a Tier C capability")
    say.did("neither mechanically checkable nor groundable in evidence")
    expect_refusal(
        "a Tier C capability — advisory AI, in a register",
        lambda: maya.assist.register(
            capability_key="doc.freeform_commentary",
            description="writes general commentary on a model",
            tier=TIER_C, base_model="claude-opus-5",
            prompt_digest=PROMPT_DIGEST, owner="person/a.mehta"))
    say.did("a Tier C capability in a registry is a Tier C capability that "
            "will one day be wired into a decision")

    # ------------------------------------------------- 3. register Tier B
    say.step("Register the capability — Tier B, every claim cites evidence")
    attempt(CAPABILITY, lambda: maya.assist.register(
        capability_key=CAPABILITY,
        description="Drafts the model description section of a validation "
                    "pack from the evidence MAYA holds",
        tier=TIER_B, base_model="claude-opus-5",
        prompt_digest=PROMPT_DIGEST, owner="person/a.mehta",
        autonomy="human_approved_automation",
        # Every generation reviewed, for a first deployment. The rate is
        # deterministic on the capability's own draw count, so a drafter
        # cannot infer it by watching a clock.
        review_sample=1.0))
    say.maya(f"prompt registered by DIGEST: {PROMPT_DIGEST[:26]}…")
    say.did("the prompt is the parameter object; a copy of its text would be a "
            "copy somebody can edit")

    # ------------------------------------------------ 4. the generation
    say.step("Record what the bank's model produced")
    claims = draft_description({})
    say.engine(f"{len(claims)} claims drafted, outside MAYA")
    for c in claims:
        cited = ", ".join(c["citations"])
        known = all(x in KNOWN_EVIDENCE for x in c["citations"])
        print(f"      {c['id']}  cites {cited:<28} "
              f"{'' if known else '<- cites nothing MAYA holds'}")

    generation = attempt("the generation", lambda: maya.assist.record(
        capability_key=CAPABILITY, subject_type=SUBJECT_TYPE,
        subject_id=SUBJECT_URN, claims=claims,
        known_evidence=KNOWN_EVIDENCE,
        output={"section": "model description"}))
    generation_id = (generation or {}).get("id") or \
        (generation or {}).get("generation_id")

    # ------------------------------------------------ 5. what grounding did
    say.step("What the grounding gate did to it")
    if generation_id:
        record = maya.assist.get(str(generation_id))
        kept = record.get("claims") or []
        removed = record.get("rejected_claims") or []
        grounding = (record.get("output") or {}).get("grounding") or {}
        say.maya(f"{len(kept)} claim(s) kept, {len(removed)} REMOVED — "
                 f"{grounding.get('detail', '')}")
        for r in removed:
            print(f"      removed  {r.get('id')}: {str(r.get('text'))[:70]}…")
            print(f"      because  {r.get('reason')}")
        say.maya(f"pulled for independent review: {record.get('sampled')} "
                 f"— this capability's review_sample is 1.0, so every "
                 f"generation is")
        verdict = record.get("oracle_verdict") or {}
        say.did(f"oracle: {verdict.get('detail')}")
        say.did("removed, not flagged. A flag leaves the unsupported sentence "
                "in the document with a marker somebody has to notice; removal "
                "leaves a document whose remaining sentences are all supported "
                "— and a list of what was taken out, for the reviewer")
        save_json(out / "generation.json", record, what="the generation record")

    # ------------------------------------------- 6. attestation, by another
    say.step("Nothing is evidence until a person signs for it")
    if generation_id:
        expect_refusal(
            "the principal who asked for the draft attesting their own draft",
            lambda: maya.assist.attest(str(generation_id), accept=True,
                                       note="looks right to me"))
        attempt("attested by s.iqbal (model risk)",
                lambda: people["s.iqbal"].assist.attest(
                    str(generation_id), accept=True,
                    final_text="The model is a Merton structural default "
                               "probability for large corporate obligors. Its "
                               "parameter object is terminal: the class is T0 "
                               "and there is nothing to fit.",
                    note="Accepted with edits; the unsupported backtest claim "
                         "was removed by the platform before I saw it."),
                already="already attested")
        say.did("the person who ASKED and the person who SIGNS are different, "
                "and the platform refuses the alternative rather than "
                "recommending against it")

    # --------------------------------------------- 7. automation bias
    say.step("Measuring automation bias, rather than warning about it")
    try:
        # The bare username, not the `person/…` actor the generation records
        # as `attested_by` — the path parameter is a username and the slash in
        # the actor form would split it. Worth knowing if you wire this up.
        reviewer = people["s.iqbal"].assist.reviewer("s.iqbal")
        print(f"      reviewer {reviewer.get('reviewer')}: "
              f"{reviewer.get('attested')} attestation(s), "
              f"trend known: {reviewer.get('known')}")
        print(f"      {reviewer.get('detail')}")
    except Exception as exc:
        say.note(f"reviewer record unavailable: {exc}")
    say.did("somebody who has approved forty correct drafts is not reading the "
            "forty-first, and no amount of telling them to will change that. "
            "Edit distance is what makes it visible: accepting everything "
            "unchanged and reading carefully produce the same approval count "
            "and very different distributions")

    say.step("Write the LaTeX specification")
    path = write_document(out, claims, PROMPT_DIGEST, providers)
    print(f"\n    LaTeX written to {path}")

    print(f"\n{'=' * 78}")
    print("Done. An AI capability registered like a model, its unsupported")
    print("claim removed rather than flagged, and signed for by a second person.")
    print(f"{'=' * 78}")
    return 0


def write_document(out, claims, digest, providers):
    claim_rows = [[latex_escape(c["id"]),
                   latex_escape(c["text"][:74] + ("…" if len(c["text"]) > 74 else "")),
                   latex_escape(", ".join(c["citations"])),
                   "kept" if all(x in KNOWN_EVIDENCE for x in c["citations"])
                   else "REMOVED"]
                  for c in claims]
    blocks = [
        r"\section{What this capability is}",
        "A language model drafting the model description section of a "
        "validation pack. MAYA registers it the way it registers any other "
        r"model, because under \(f : P \otimes X \to D(Y)\) it is one: $P$ is a "
        "prompt and a configuration, $X$ is the context it is given, and $D(Y)$ "
        "is a distribution over text. Nothing in the definition needed changing "
        "to accommodate it.",
        r"\textbf{Tier B} --- every claim it makes must cite evidence the "
        r"platform holds. Tier A is for output a named oracle can mechanically "
        r"check; \textbf{Tier C --- neither checkable nor groundable --- is "
        r"deliberately not registrable}, because a Tier C capability in a "
        r"register is one that will be wired into a decision one day.",

        r"\section{MAYA does not call the model}",
        "Asked which providers it can reach, the platform answers of the "
        "commercial APIs: \\emph{MAYA does not call the API. Nothing here is "
        "wired to an egress path, a credential, or a confidentiality decision "
        "about what may leave the institution.} The inference runs wherever the "
        "bank runs it. This is the same boundary as \\emph{MAYA does not train "
        "models}, and it is the reason adopting the platform does not require a "
        "conversation about data leaving the building.",

        r"\section{The draft, and what grounding did to it}",
        # The claim text is a sentence, so its column has to be a `p{}` like
        # the citations column. As `l` it was unbounded, and the table ran
        # 247pt past the margin — reported as an overfull hbox in a build that
        # succeeded, and visible in the PDF as text off the edge of the page.
        table(claim_rows, header=["Claim", "Text", "Cites", "Outcome"],
              spec=r"lp{62mm}p{32mm}l"),
        r"Claim \texttt{c5} is the one that matters. It is fluent, specific, "
        r"quantified, and cites an evidence node that does not exist --- the "
        r"exact shape of output these systems produce constantly. The grounding "
        r"gate \textbf{removes} it rather than flagging it, and keeps it "
        r"separately for the reviewer: a flag leaves an unsupported sentence in "
        r"the document with a marker somebody has to notice, while removal "
        r"leaves a document whose remaining sentences are all supported.",

        r"\section{Governance}",
        table([["Capability", latex_escape(CAPABILITY)],
               ["Tier", "B --- claims grounded in evidence"],
               ["Prompt", latex_escape(digest[:34]) + "…"],
               ["Review sample", "1.0 --- every generation reviewed"],
               ["Autonomy", latex_escape("human_approved_automation")],
               ["Providers usable",
                latex_escape(", ".join(p["provider"] for p in providers
                                       if p.get("usable")) or "none")]],
              header=["Field", "Value"], spec="ll"),
        r"\textbf{Nothing is evidence until a person attests it, and never the "
        r"person who asked.} The platform refuses self-attestation in the "
        r"mechanism rather than recommending against it in a policy --- and a "
        r"rejected generation stays on the record with its reason, because a "
        r"capability whose rejections are deleted has no measurable quality.",
    ]
    return document(path=out / "llm-capability-specification.tex",
                    title="AI Capability --- Model Documentation Drafting",
                    subtitle=latex_escape("Registered in MAYA · " + CAPABILITY),
                    blocks=blocks)


if __name__ == "__main__":
    raise SystemExit(main())
