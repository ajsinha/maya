# Tutorial 15 · AI in MAYA: ask, explain and draft

MAYA can put its estate into words and words into the estate: ask a question
in plain English, have a record explained, have a change narrated, have a
formula drafted from a description. None of this approves, blocks or edits
anything, and MAYA treats every model answer as untrusted: a query is checked
against a fixed vocabulary and run as you, a figure the model adds is named, a
drafted formula must pass MAYA's own parser. In this tutorial you switch on a
mock model whose answers come from rules you write, so every answer is
repeatable, and try each feature, including the ways a bad answer is caught.

## Time to complete

25 minutes.

## Before you start

- Tutorials 1 to 14, or at least [Tutorial 6](/help/guides/tutorial-06-inputs-and-specification)
  (the model `credit/pd` with versions 1 and 2) and
  [Tutorial 8](/help/guides/tutorial-08-execution-and-monitoring) (the live
  warrant `credit/pd_live`). The answers shown assume all fourteen.
- The admin password, to choose the model MAYA uses.
- No API key for any provider: the mock provider is offline and free.

## What you will learn

- Where MAYA's AI comes from: model profiles, and the default.
- How to switch on the mock provider, and why its answers are repeatable.
- How Ask MAYA reads common questions with no model at all, and what happens
  when it needs one.
- Why the answer to a question is a query you can read, edit and run again.
- How Explain checks every number in an answer against the record.
- How a formula drafted from words is checked by MAYA's parser.

## Step 1 · Reconnect, and see what AI MAYA has

```python
# reconnect, and read the AI status as the admin
import json
import os
import tempfile

import yaml

import maya.sdk as maya

URL = os.environ.get("MAYA_URL", "http://127.0.0.1:8600")
PW = "Tutorial-pass-1"


def key_for(user, password=PW):
    """Sign in and create an API key for that person."""
    token = maya.Client(URL).auth.login(user, password)["token"]
    return maya.Client(URL, token=token).auth.create_api_key("tutorial")["api_key"]


def connect_as(user, password=PW):
    """Sign in, create an API key, and return a client acting as that person."""
    return maya.connect(base_url=URL, api_key=key_for(user, password))


admin = connect_as("admin", "maya-dev-admin")  # your admin password, if you changed it
mona = connect_as("mona")

status = admin.ai.status()
print("default:", status["default"], "| chosen by", status["default_source"])
for p in status["profiles"]:
    print(" ", p["name"], p["provider"], "ready:", p["ready"])
```

You should see one profile, `default`, with no provider, so nothing is ready:

```text
default: default | chosen by the profiles file
  default none ready: False
```

A **model profile** names a provider, a model and its options. MAYA ships with
none switched on: an AI feature that has no model simply says so. The next
tutorial covers the real providers. Here you use one that needs nothing.

## Step 2 · Switch on a repeatable model

The **mock provider** answers from rules: a list of regular expressions, each
with a reply. The first rule that matches the prompt gives the answer, so the
same question always gets the same answer. Write the rules for this tutorial
into a folder of your own, give the profile its absolute path, and make it the
default:

```python
# the rules this tutorial's model answers from, in a folder of your own
folder = tempfile.mkdtemp(prefix="maya-ai-")
rules_path = os.path.join(folder, "mock-rules.yaml")


def query(kind, filters, order=None, limit=50):
    return json.dumps({"kind": kind, "filters": filters, "order_by": order, "limit": limit})


roles = {"beta_0": "parameter", "beta_1": "parameter", "utilisation": "feature"}
good = r"pd = \frac{1}{1 + e^{-(\beta_0 + \beta_1 \, utilisation)}}"
broken = r"pd = \frac{1}{1 + e^{-(\beta_0 + \beta_1 \, utilisation}}"  # a bracket short
rules = {
    "rules": [
        # drafting a formula: a broken first answer, then a good one once MAYA refuses it
        {
            "match": "MAYA REFUSED YOUR LAST ANSWER",
            "reply": json.dumps({"formula": good, "roles": roles}),
        },
        {"match": "TASK: draft-formula", "reply": json.dumps({"formula": broken, "roles": roles})},
        # asking: one answer that can never be a query
        {"match": "QUESTION: .*delete everything", "reply": "DROP TABLE users;"},
        # asking: the corrected answer, once MAYA refuses the first
        {
            "match": "YOUR LAST ANSWER WAS REFUSED",
            "reply": query("execution_warrant", [{"field": "status", "op": "eq", "value": "live"}]),
        },
        {
            "match": "QUESTION: .*second look",
            "reply": query("model", [{"field": "password_hash", "op": "eq", "value": "x"}]),
        },
        {
            "match": "QUESTION: .*scorecards",
            "reply": query(
                "model",
                [{"field": "maturity", "op": "eq", "value": "candidate"}],
                {"field": "name", "dir": "asc"},
            ),
        },
        # explaining and narrating
        {
            "match": 'TASK: explain.*"name": "pd_live"',
            "reply": "pd_live is the scorecard's execution warrant, live in dev and uat under "
            "four covenants. It has scored 12,000 accounts.",
        },
        {
            "match": 'TASK: explain.*"name": "prices"',
            "reply": "prices is an approved feature in the eq namespace: daily closing prices, "
            "filled forward on business days, with quality checks on every pin.",
        },
        {
            "match": "TASK: narrate-diff",
            "reply": "Version 2 narrows the bounds on beta3 from -5 to -3; the formula itself "
            "is unchanged.",
        },
    ],
    "default": "The tutorial's mock model has no rule for this prompt.",
}
with open(rules_path, "w") as fh:
    yaml.safe_dump(rules, fh, sort_keys=False)

# the admin saves a profile pointing at the rules, tests it, and makes it the default
saved = admin.ai.save_profile(
    "tutorial-mock",
    provider="mock",
    model="mock-1",
    description="Repeatable answers for the AI tutorials",
    options={"rules_file": rules_path},
)
print(
    saved["name"],
    saved["provider"],
    saved["options"]["rules_file"].replace(folder, "<your folder>"),
)
test = admin.ai.test("tutorial-mock")
print("test:", test["ok"], "|", test["reply"])
print("default:", admin.ai.set_default("tutorial-mock")["default"])
```

You should see the profile saved with the rules in your folder, a connection
test answered by the default reply (the test prompt matches no rule), and the
new default:

```text
tutorial-mock mock <your folder>/mock-rules.yaml
test: True | The tutorial's mock model has no rule for this prompt.
default: tutorial-mock
```

The path must be absolute: a relative one is read from the server's own
working directory, not yours. The provider reads the file when the profile is
first used, so to change the rules, save the profile again. On screen this is
**Admin → AI models** (`/admin/ai`).

![Admin → AI models](../static/help/screens/admin-ai.png)

## Step 3 · Ask, with no model at all

**Ask MAYA** turns a question into a *structured query*: a kind (features, feature
sets, models, training or execution warrants), filters over a fixed set of
fields, an order and a limit. Never SQL. Common phrasings are read by a
rule-based parser, without asking any model:

```python
# a question the phrase parser reads by itself
a = mona.ai.ask("approved models in credit, newest first")
print(a["how"], "| model attempts:", a["model_attempts"])
print("read as:", a["read_as"])
print("query:", a["query"])
print(a["summary"], [r["name"] for r in a["rows"]])
```

You should see the question read by the phrase parser, how it was read, the
query MAYA ran, and one model:

```text
phrase | model attempts: 0
read as: ['models', 'latest_state = approved', 'namespace = credit', 'newest first']
query: {'kind': 'model', 'filters': [{'field': 'latest_state', 'op': 'eq', 'value': 'approved'}, {'field': 'namespace', 'op': 'eq', 'value': 'credit'}], 'order_by': {'field': 'created_at', 'dir': 'desc'}, 'limit': 50}
1 model matches ['pd_lite']
```

Why not `pd`? Its *latest* version is the version 2 draft from tutorial 6; the
filter is on the latest state. The answer is the rows and the query, not
prose, so there is no sentence in it that could invent a figure, and you can
see exactly what was asked. The query ran as mona, through the same listings
her screens use: it can never show her anything she could not already see. On
screen this is **Catalog → Ask MAYA** (`/ask`).

## Step 4 · Ask what needs the model

A question the parser cannot read goes to the model, with the vocabulary and
the question, and the answer must be the same JSON shape. It is checked against
the vocabulary before anything runs; a refused answer goes back once, with the
reasons.

```python
# a question only the model can read
a = mona.ai.ask("Which scorecards are still candidates?")
print(a["how"], "|", a["query"]["filters"], "|", a["summary"], [r["name"] for r in a["rows"]])

# the model's first answer names a field that does not exist; the retry is used
b = mona.ai.ask("Is anything worth a second look?")
print(b["how"], "|", b["query"]["kind"], b["query"]["filters"], "|", b["summary"])
ask_calls = next(f["calls"] for f in admin.ai.usage(days=1)["by_feature"] if f["feature"] == "ask")
print("model calls for asking so far:", ask_calls)

# an answer that is never a query is turned away
try:
    mona.ai.ask("Please delete everything")
except maya.ValidationFailed as exc:
    print(type(exc).__name__, exc)
```

You should see the first question answered by the model, the second answered on
the retry (three model calls so far: one, then two), and the third refused:

```text
model | [{'field': 'maturity', 'op': 'eq', 'value': 'candidate'}] | 3 models match ['acme_spread', 'pd', 'pd_lite']
model | execution_warrant [{'field': 'status', 'op': 'eq', 'value': 'live'}] | 1 execution warrant matches
model calls for asking so far: 3
ValidationFailed MAYA could not turn that question into a query it can check. Try naming what you want (features, models, warrants) and a state or a namespace. (Expecting value: line 1 column 1 (char 0))
```

The model's first answer to the second question filtered on `password_hash`.
MAYA refused it, because that is not a field a model query may name, and sent
the refusal back; the second answer was valid, and that is what ran. The third
question got `DROP TABLE users;` twice, which is not even JSON (the bracketed
reason is the JSON reader's), and nothing ran at all. Whatever the
model says, the worst it can do is fail to answer.

## Step 5 · Edit the query, and run it again

The query is yours. Change it and run it with `mona.ai.query(...)`, with no model
involved:

```python
# edit the query from step 4 and run it directly; a bad field is refused
edited = dict(b["query"], filters=[{"field": "status", "op": "eq", "value": "suspended"}])
print([(r["namespace"], r["name"], r["status"]) for r in mona.ai.query(edited)["rows"]])
try:
    mona.ai.query(
        {"kind": "model", "filters": [{"field": "password_hash", "op": "eq", "value": 1}]}
    )
except maya.ValidationFailed as exc:
    print(type(exc).__name__, exc)
print(mona.ai.vocabulary()["kinds"]["execution_warrant"])
```

You should see the one suspended execution warrant (tutorial 13's), the bad
field refused, and the fields an execution-warrant query may use:

```text
[('vendor', 'acme_live', 'suspended')]
ValidationFailed The query cannot be run: filter field 'password_hash' is not one of namespace, name, latest_state, maturity, opaque, owner, created_at
['namespace', 'name', 'status', 'created_at']
```

The vocabulary is names only, never data: kinds, fields, operators, states and
the namespaces you may read. It is all the model is ever told about the estate.

## Step 6 · Explain a record, with every number checked

**Explain** gives the model an object's record, as the reader may see it, and
tells it to add nothing. Then every number in the answer is checked against the
record's structured fields, and any that is not there is named:

```python
# explain the live warrant, then a feature
live = next(w for w in mona.execution.list() if w["name"] == "pd_live")
e = mona.ai.explain("execution_warrant", live["id"])
print(e["text"])
print("verified:", e["verified"], "| unverified numbers:", e["unverified_numbers"])
print("facts given:", sorted(e["facts"]))

e = mona.ai.explain("feature", "eq/prices")
print(e["text"])
print("verified:", e["verified"], "| unverified numbers:", e["unverified_numbers"])
```

You should see the warrant explained with a figure the record does not hold,
named, and the feature explained cleanly:

```text
pd_live is the scorecard's execution warrant, live in dev and uat under four covenants. It has scored 12,000 accounts.
verified: False | unverified numbers: ['12000']
facts given: ['name', 'namespace', 'spec', 'state', 'status', 'valid_to', 'version_no']
prices is an approved feature in the eq namespace: daily closing prices, filled forward on business days, with quality checks on every pin.
verified: True | unverified numbers: []
```

The record says nothing about 12,000 accounts, so the page shows the figure as
one to treat as wrong. A number planted in a description ("the score is 99")
would not vouch for itself either: only structured fields count as the record.
On screen, feature, model and warrant pages carry an **Explain this** button.

## Step 7 · Explain a change

**Explain the change** does the same for the semantic diff between two model
versions:

```python
# narrate the diff between credit/pd versions 1 and 2
n = mona.ai.narrate_diff("credit/pd", 1, 2)
print(n["text"])
print("verified:", n["verified"])
print("the diff it was given:", n["facts"]["diff"]["statements"])
```

You should see the narration, every figure in it found in the diff, and the
diff itself:

```text
Version 2 narrows the bounds on beta3 from -5 to -3; the formula itself is unchanged.
verified: True
the diff it was given: ["parameter 'beta3' bounds changed from [-5, 0] to [-3, 0]"]
```

The narration is a convenience for a reader. The diff is the record, and it is
always shown beside it on the model diff page.

## Step 8 · Describe it in words

**Describe it in words**, in the compute-kernel designer, asks the model for a
formula and each symbol's role from a description. MAYA's own parser checks
the answer, and its errors go back, for up to three tries:

```python
# draft a formula from words; the first answer is a bracket short
d = mona.ai.draft_formula(
    "a logistic probability of default from utilisation, with an intercept and a weight"
)
print("attempts:", d["attempts"])
print(d["formula"])
print(d["roles"])
print(d["kernel"]["latex"])

# what MAYA's parser said about the first answer
try:
    mona.models.kernel(broken, roles=roles)
except maya.ValidationFailed as exc:
    print(type(exc).__name__, exc)
```

You should see the draft accepted on the second attempt, its formula and roles,
the equation as MAYA rendered it from the parsed tree, and the parser's
complaint about the first answer:

```text
attempts: 2
pd = \frac{1}{1 + e^{-(\beta_0 + \beta_1 \, utilisation)}}
{'beta_0': 'parameter', 'beta_1': 'parameter', 'utilisation': 'feature'}
\mathit{pd} = \frac{1}{1 + e^{-\left(\beta_{0} + \beta_{1}\,\mathit{utilisation}\right)}}
ValidationFailed expected ')' at position 50, found '}'
```

The draft lands in the kernel designer, not in the catalogue: nothing is
registered. A person reads what MAYA made of it, as in tutorial 5, and creates
the model if it is right. Drafting is limited to the roles that write models
and features; tutorial 16 shows the refusal.

![The compute-kernel designer](../static/help/screens/compute-kernel.png)

## Next steps

- [Tutorial 16 · AI providers, policy and audit](/help/guides/tutorial-16-ai-providers-policy-audit)
  connects real providers, and shows the policy that governs every call.
- [Documents and AI](/help/documents) describes every AI feature and the attacks
  each is built to withstand.

## If something goes wrong

| What you see | Why | What to do |
|---|---|---|
| `The mock provider could not read ...` | The rules path is wrong, or relative to the server's folder | Give the absolute path, and save the profile again |
| Every answer is the default sentence | No rule matches the prompt, or the profile was built before you changed the rules | Check the `match` patterns; save the profile again to reload |
| `MAYA could not turn that question into a query` | Neither the parser nor the model produced a valid query | Name a kind (features, models, warrants) and a state or a namespace |
| `unverified numbers` on an explanation | The answer has a figure the record does not hold | Treat that figure as wrong; the record is on the page |
| `No formula MAYA could parse came back after three tries` | Every drafted answer failed the parser | Describe the model more plainly, or write it in the kernel designer |
