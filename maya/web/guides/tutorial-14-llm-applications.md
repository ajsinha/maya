# Tutorial 14 · LLM applications: evaluation sets and guardrails

A bank that drafts complaint replies with a large language model is running a
model, and it should be governed like one. In MAYA an **LLM application** has
versions, and each version seals everything that decides its behaviour: the
provider, the model, the prompts, the parameters and the guardrails, under one
hash. An **evaluation set** plays the part of the holdout: cases with
deterministic checks. A version is approved only on a passing evaluation, by a
model manager who neither owns the application nor submitted it. In this
tutorial you build a complaints assistant, catch it leaking a card number, fix
it, and take it through approval.

## Time to complete

20 minutes.

## Before you start

- [Tutorial 5 · Write a model](/help/guides/tutorial-05-write-a-model):
  **mona** (model designer) and **mgr** (model manager).
  [Tutorial 4](/help/guides/tutorial-04-feature-sets-and-pins) created **devi**
  (model developer), who appears once to be refused.
- The admin password, to add a namespace.
- No API key for any model provider. The tutorial uses recorded answers and
  MAYA's offline `mock` provider, so it costs nothing and gives the same result
  every time.

## What you will learn

- What an LLM application version seals, and why any change is a new
  definition.
- How to write an evaluation set with deterministic checks.
- What the guardrails check on every answer: personal data and blocked terms.
- The difference between a **recorded** run, with answers you collected where
  the application runs, and a **live** run, where MAYA calls the provider.
- Why old evidence stops counting when the draft changes.
- Who may submit and who may approve.

## Step 1 · Reconnect, and add a namespace

```python
# reconnect; the admin adds the support namespace
import os

import maya.sdk as maya

URL = os.environ.get("MAYA_URL", "http://127.0.0.1:8600")
PW = "Tutorial-pass-1"


def connect_as(user, password=PW):
    """Sign in, create an API key, and return a client acting as that person."""
    token = maya.Client(URL).auth.login(user, password)["token"]
    key = maya.Client(URL, token=token).auth.create_api_key("tutorial")["api_key"]
    return maya.connect(base_url=URL, api_key=key)


admin = connect_as("admin", "maya-dev-admin")  # your admin password, if you changed it
ns = admin.namespaces.create("support", preset="standard")
mona, mgr, devi = connect_as("mona"), connect_as("mgr"), connect_as("devi")
print(ns["name"], ns["preset"])
```

You should see the new namespace:

```text
support standard
```

## Step 2 · The application and its first version

mona registers the application with its use case, then saves a version. The
version names the provider and model, the system prompt, a prompt template with
one `{placeholder}` per input, the call parameters and the guardrails. Here the
provider is `mock`, MAYA's offline stand-in; in production it would be
`anthropic`, `openai`, `bedrock` or any other provider MAYA lists.

```python
# mona creates the application and saves version 1
APP = "support/complaints"
mona.llm.create_app(
    "support",
    "complaints",
    use_case="draft replies to retail complaints",
    description="First drafts for the complaints team; a person sends every reply",
)
v = mona.llm.save_version(
    APP,
    provider="mock",
    model="mock-1",
    system_prompt="You are a careful complaints handler for a retail bank.",
    prompt_template="Reply to this complaint: {complaint}",
    parameters={"max_tokens": 300},
    guardrails={"blocked_terms": ["guarantee"]},
)
first_hash = v["definition_hash"]
print("v" + str(v["version_no"]), v["state"], v["provider"], v["model"])
print(v["guardrails"])
print(len(first_hash), "character definition hash")
```

You should see version 1 as a draft, the guardrails with MAYA's two defaults
added, and the hash that seals the definition:

```text
v1 draft mock mock-1
{'pii': True, 'min_pass_rate': 1.0, 'blocked_terms': ['guarantee']}
64 character definition hash
```

`pii: True` checks every answer for personal data: card numbers (with a valid
Luhn digit), email addresses, phone numbers. `min_pass_rate: 1.0` means every
evaluation case must pass before the version can be submitted. `blocked_terms`
are words the bank never wants in a reply: no adviser may *guarantee* an
outcome. The hash covers all of it, so changing a single word of the prompt
changes the definition.

## Step 3 · An evaluation set

An evaluation set is a list of cases. Each case supplies the template's inputs
and lists **checks** on the answer: `contains`, `not_contains`, `equals`,
`regex`, `max_chars`, or `json` (the answer parses as JSON with the named keys).
Every check is deterministic, so the same answer always gets the same verdict.

```python
# the core cases: a refund reply, and a classification the routing system parses
CASES = [
    {
        "id": "refund",
        "vars": {"complaint": "I was charged twice for my card fee."},
        "checks": [
            {"kind": "contains", "value": "refund"},
            {"kind": "max_chars", "value": 400},
        ],
    },
    {
        "id": "statement",
        "vars": {"complaint": "Where is my statement? Please answer as JSON."},
        "checks": [{"kind": "json", "value": ["category"]}],
    },
]
es = mona.llm.save_eval_set(APP, "core", CASES, description="Cases every version must pass")
print(es["name"], len(es["cases"]), "cases")

try:
    mona.llm.submit(APP, 1)
except maya.NotApproved as exc:
    print(type(exc).__name__, exc)
```

You should see the set saved, and a submission refused for want of evidence:

```text
core 2 cases
NotApproved Submission needs an evaluation run on this exact definition, against an evaluation set as it now stands, passing at least 100% of cases with no guardrail violation
```

Note the two conditions: "this exact definition" and "an evaluation set as it
now stands". Evidence is tied to both hashes. Edit either, and the old runs stop
counting.

## Step 4 · A recorded run that breaks a guardrail

The application runs in the bank's own service, which collected these answers
from version 1. A **recorded run** submits them, one per case, and MAYA scores
them:

```python
# answers collected where the application runs, scored by MAYA
answers_v1 = {
    "refund": "We are sorry. We guarantee a refund of the duplicate fee to card "
    "4111 1111 1111 1111 within five days.",
    "statement": '{"category": "statements", "urgency": "low"}',
}
run = mona.llm.run_eval(APP, 1, "core", responses=answers_v1)
print(
    run["mode"],
    run["passed"],
    "of",
    run["cases"],
    "passed;",
    run["guardrail_violations"],
    "guardrail violation",
)
for r in run["results"]:
    print(
        " ",
        r["case"],
        r["passed"],
        [c["check"] for c in r["checks"] if not c["passed"]],
        r["guardrails"],
    )
```

You should see the refund answer pass its own checks but fail on two
guardrails, and the statement answer pass:

```text
recorded 1 of 2 passed; 1 guardrail violation
  refund False [] ["blocked term 'guarantee'", 'personal data: card number', 'personal data: phone number']
  statement True [] []
```

The refund reply contains "refund" and is under 400 characters, so both case
checks pass. But it promises a guarantee, and it repeats a full card number,
which a reply must never do. The sixteen digits also match the pattern for a
phone number, so the personal-data check names both; either alone would fail
the case. The guardrails run on every answer of every case,
whatever the case's own checks say.

## Step 5 · A live run

A **live run** has MAYA call the provider itself, exactly as the version
declares: this provider, this model, these prompts. No administrator's choice of
default profile can change what is called, because the pairing is what was
reviewed.

```python
# MAYA calls the declared provider for every case
live = mona.llm.run_eval(APP, 1, "core")
print(live["mode"], live["passed"], "of", live["cases"], "passed")
for r in live["results"]:
    print(" ", r["case"], r["provider"], r["model"], "->", r["answer"])
```

You should see a live run, each case answered by `mock-1`, and both failing:

```text
live 0 of 2 passed
  refund mock mock-1 -> The mock model has no rule for this prompt.
  statement mock mock-1 -> The mock model has no rule for this prompt.
```

The mock provider answers from a rules file named in the server's configuration
(`llm.mock.rules_file`), and this server has none, so every answer is its
default sentence. That is the point of the example: a live run scores what the
provider really says, and a provider that says nothing useful fails. With a
real provider and its key configured on the server, the same call asks the real
model. MAYA records the run either way, with the tokens each case used.

Use a live run when MAYA can reach the provider. Use a recorded run when the
application runs somewhere MAYA cannot call, such as a provider MAYA does not
integrate or a model hosted inside another system; MAYA then scores the answers
you collected, and the run says `recorded`.

## Step 6 · Fix the draft, and evaluate again

The card number came from the model echoing details back. mona tightens the
system prompt. Version 1 is still a draft, so saving edits it in place, and the
definition hash changes:

```python
# fix the system prompt: version 1 is still a draft, so it is edited in place
v = mona.llm.save_version(
    APP,
    provider="mock",
    model="mock-1",
    system_prompt="You are a careful complaints handler for a retail bank. Never repeat "
    "a card number, account number or other personal detail; say 'your card'. Never "
    "promise or guarantee an outcome.",
    prompt_template="Reply to this complaint: {complaint}",
    parameters={"max_tokens": 300},
    guardrails={"blocked_terms": ["guarantee"]},
)
print("v" + str(v["version_no"]), v["state"], "hash changed:", v["definition_hash"] != first_hash)

# the bank's service, rerun with the fixed prompt, gives these answers
answers_fixed = {
    "refund": "We are sorry. A refund of the duplicate fee is on its way to your card "
    "and should arrive within five working days.",
    "statement": '{"category": "statements", "urgency": "low"}',
}
run = mona.llm.run_eval(APP, 1, "core", responses=answers_fixed)
print(run["mode"], run["pass_rate"], run["guardrail_violations"])
```

You should see the same version number with a new hash, and a clean run:

```text
v1 draft hash changed: True
recorded 1.0 0
```

The failed runs from steps 4 and 5 were recorded against the old hash. They
remain in the history, but they no longer describe this definition, so they no
longer count, for or against.

## Step 7 · Submit and approve

```python
# mona submits; devi and mona may not decide; mgr approves with a note
r = mona.llm.submit(APP, 1)
print(r["state"], "submitted by", r["submitted_by"])

for who, client in (("devi", devi), ("mona", mona)):
    try:
        client.llm.decide(APP, 1, "approve", "looks fine")
    except maya.PermissionDenied as exc:
        print(who, type(exc).__name__, exc)

r = mgr.llm.decide(APP, 1, "approve", "Every core case passes; no guardrail violation")
print(r["state"], "decided by", r["decided_by"], "-", r["decision_note"])
```

You should see the version in review, both refusals, and mgr's approval with
his reason:

```text
in_review submitted by mona
devi PermissionDenied An LLM application is approved by a model manager
mona PermissionDenied An LLM application is approved by a model manager
approved decided by mgr - Every core case passes; no guardrail violation
```

A decision always records why: an empty note is refused. Had mgr owned the
application or submitted the version, he would have been refused too:
"Whoever owns the application or submitted the version does not approve it".

## Step 8 · Read the application back

```python
# the application as the catalogue sees it
row = next(a for a in mona.llm.apps() if a["name"] == "complaints")
print(row["approved"]["version_no"], row["latest"]["version_no"])
detail = mona.llm.app(APP)
print([(x["version_no"], x["state"]) for x in detail["versions"]])
print([(x["mode"], x["passed"], x["cases"]) for x in detail["runs"]])
```

You should see version 1 approved and latest, and every run kept, newest
first:

```text
1 1
[(1, 'approved')]
[('recorded', 2, 2), ('live', 0, 2), ('recorded', 1, 2)]
```

Any later change, even one word of the prompt, opens version 2 as a new draft,
which needs its own evaluation and its own approval. Approving it retires
version 1, so one version is approved at a time. LLM applications also appear
in the model inventory beside the models, with their evaluation evidence.

## Next steps

- [LLM applications](/help/llm-apps) covers every check, guardrail and
  provider, and how MAYA registers its own AI features as applications.
- [Workflow](/help/workflow) explains who decides what, across every kind of
  object.

## If something goes wrong

| What you see | Why | What to do |
|---|---|---|
| `The prompt template reads no {placeholder}` | Every case would ask the same thing | Add a placeholder for each input, such as `{complaint}` |
| `A recorded run answers every case; missing [...]` | The responses do not cover every case id | Supply an answer for every case in the set |
| `Submission needs an evaluation run on this exact definition` | No passing run on the current hash and set | Run the evaluation again after any edit |
| `MAYA does not call ... itself` | The version names a provider MAYA does not integrate | Run where the application runs, and submit a recorded run |
| `Whoever owns the application or submitted the version does not approve it` | Separation of duties | Ask another model manager |
