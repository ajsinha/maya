"""
Write the study's inputs: an evaluation set of complaints, and the answers two versions of
the triage application gave to it, as recorded by the harness the application runs in.

    .venv/bin/python case_studies/49-llm-complaint-triage/make_data.py

* ``eval_cases.json`` — twenty-four complaints, each with the team it belongs to and the
  checks an answer must pass: it is JSON with a ``category`` and a ``reply``, the category is
  the right one, the reply stays under 600 characters.
* ``answers_v1.json`` — the answers version 1 gave. Two of them repeat the customer's card
  number back to them, and one promises a refund it cannot promise.
* ``answers_v2.json`` — the answers after the system prompt was changed to forbid both.
* ``extra_case.json`` — a case the validator adds later: a complaint written in Welsh.

The answers are written here rather than produced by a model, on purpose: MAYA scores
recorded answers from whatever harness the application runs in, and a case study whose
numbers changed every time a provider updated its model would demonstrate nothing
reproducible. Everything is synthetic; no customer is real.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent

COMPLAINTS = [
    ("billing", "I was charged the annual card fee twice this month."),
    ("billing", "An overdraft charge appeared even though I was never overdrawn."),
    ("billing", "My statement shows interest on a balance I cleared in full."),
    ("billing", "You took my direct debit two days early and it bounced my rent."),
    ("billing", "The foreign transaction fee was higher than your price list says."),
    ("fraud", "There are three payments to a shop in Lisbon I have never visited."),
    ("fraud", "Someone called pretending to be your bank and I gave them a code."),
    ("fraud", "My card 4111 1111 1111 1111 was used online after I reported it stolen."),
    ("fraud", "I received a text asking me to confirm a payee I never added."),
    ("fraud", "A new device was added to my online banking last night, not by me."),
    ("mortgage", "My mortgage payment went up and nobody told me why."),
    ("mortgage", "I asked for a payment holiday three weeks ago and heard nothing."),
    ("mortgage", "The redemption figure you sent does not match my own calculation."),
    ("mortgage", "You have not applied my overpayment to the capital."),
    ("mortgage", "My fixed rate ended and I was moved to the standard rate without notice."),
    ("access", "I have been locked out of the app for four days."),
    ("access", "The branch refused to let my carer help me at the counter."),
    ("access", "Your phone line kept me on hold for ninety minutes."),
    ("access", "I cannot read your letters; I asked for large print twice."),
    ("access", "The website rejects my password reset every time."),
    ("other", "Your adviser was rude to me on the phone."),
    ("other", "I want to close my account and nobody will tell me how."),
    ("other", "The cash machine outside your branch has been broken for a month."),
    ("other", "I was promised a call back that never came."),
]

REPLIES = {
    "billing": "Thank you for telling us. We have passed this to our billing team, who will "
    "review the charge and write to you within five working days.",
    "fraud": "We are sorry. Our fraud team will contact you today. Please do not share any "
    "codes with anyone who calls you, even if they say they are from the bank.",
    "mortgage": "Thank you. Our mortgage servicing team will look into this and reply within "
    "five working days with a full explanation.",
    "access": "We are sorry this has been difficult. Our accessibility team will contact you "
    "by the method you prefer to put this right.",
    "other": "Thank you for your feedback. We have passed it to the right team, who will be "
    "in touch within five working days.",
}


def main() -> None:
    cases, v1, v2 = [], {}, {}
    for i, (category, text) in enumerate(COMPLAINTS, start=1):
        cid = f"c{i:02d}"
        cases.append(
            {
                "id": cid,
                "vars": {"complaint": text},
                "checks": [
                    {"kind": "json", "value": ["category", "reply"]},
                    {"kind": "regex", "value": f'"category"\\s*:\\s*"{category}"'},
                    {"kind": "max_chars", "value": 600},
                ],
            }
        )
        reply = REPLIES[category]
        v2[cid] = json.dumps({"category": category, "reply": reply})
        if "4111" in text:  # version 1 repeats the card number back
            v1[cid] = json.dumps(
                {
                    "category": category,
                    "reply": f"We have blocked card 4111 1111 1111 1111. {reply}",
                }
            )
        elif i == 7:  # and repeats a phone number from its own context
            v1[cid] = json.dumps(
                {"category": category, "reply": f"{reply} Call us on +44 20 7946 0958 now."}
            )
        elif i == 1:  # and promises what it cannot
            v1[cid] = json.dumps(
                {"category": category, "reply": "We guarantee a full refund today. " + reply}
            )
        else:
            v1[cid] = v2[cid]
    extra = {
        "id": "c25",
        "vars": {"complaint": "Codwyd ffi flynyddol y cerdyn ddwywaith y mis hwn."},
        "checks": [
            {"kind": "json", "value": ["category", "reply"]},
            {"kind": "regex", "value": '"category"\\s*:\\s*"billing"'},
            {"kind": "max_chars", "value": 600},
        ],
    }
    v2_with_extra = {**v2, "c25": json.dumps({"category": "billing", "reply": REPLIES["billing"]})}
    (HERE / "data").mkdir(exist_ok=True)
    for name, doc in (
        ("eval_cases", cases),
        ("answers_v1", v1),
        ("answers_v2", v2),
        ("extra_case", extra),
        ("answers_v2_with_extra", v2_with_extra),
    ):
        (HERE / "data" / f"{name}.json").write_text(json.dumps(doc, indent=2) + "\n")
    print(f"wrote {len(cases)} cases and two versions' answers to data/")


if __name__ == "__main__":
    main()
