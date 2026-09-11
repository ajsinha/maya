# maya-sdk

The Python client for MAYA. Standard library only.

```bash
pip install -e sdk/python
```

```python
from maya_sdk import Maya, Refused, Blocked

maya = Maya("https://maya.internal", "d.raman", "…")

maya.models.register(urn="maya://model/credit.pd.smallbiz", name="SB PD",
                     model_class="credit.pd.scorecard", domain="credit",
                     owner="person/j.okafor", legal_entity="LE-US-01",
                     purpose="12-month PD at origination")

try:
    maya.versions.promote("maya://model/credit.pd.smallbiz",
                          semver="3.3.0", environment="prod")
except Blocked as refusal:
    print(refusal.detail)        # an open blocking finding stands against it
    print(refusal.remediation)   # close it, or ask the validator to downgrade it
    print(refusal.request_id)    # quote this in the ticket
```

## What is here

Twenty-five subjects. This table listed seven of them for a long time, which is
worse than listing none: a reader concludes the SDK cannot do the other
eighteen and writes raw calls for things it already had — the same way a
tutorial once fell back to `client.call()` for methods that existed. A test
asserts every subject on the client appears here, so the list cannot quietly
fall behind again.

**The model, and what may be said about it**

| | |
|---|---|
| `maya.models` | register, read, assess a tier, submit, approve, attest, relate, blast radius, shared dependencies |
| `maya.versions` | create, approve, open and sign a quorum, promote an alias |
| `maya.approvals` | the quorum a tier needs, what is still outstanding, withdraw |
| `maya.lifecycle` | the state machine, submit, approve, send back, attest, amend, retire, **decommission** (why, what replaced it, who was told, how long it is kept), delete |
| `maya.authority` | who may approve this by tier, **amount** and legal entity, in what order, and the delegations behind it |
| `maya.relations` | what a model derives from and what it feeds, and removing an edge |
| `maya.artifacts` | put, get, verify a digest, where each is used |
| `maya.parameters` | fit, record a fitted set, review it, provenance |
| `maya.limitations` | what a version **cannot do**, and which of those a contract clause enforces rather than a person remembering |
| `maya.waivers` | controls a model is **not** meeting, with a mandatory bounded window, a required compensating control, and an approval quorum that scales with the tier. There are no indefinite waivers |
| `maya.assumptions` | what a version **relies on being true**, and which of those a monitor tests rather than the platform simply believing. The sibling of the above, and the difference is that an assumption can stop being true while the model runs |
| `maya.assist` | register an AI capability, record or draft a generation, attest one — and a reviewer's automation-bias record. Tier C is refused, and self-attestation is refused |
| `maya.rules` | the expression vocabulary, check, trial, publish a rule set, explain one |

**Features, and the data under them**

| | |
|---|---|
| `maya.features` | define, derive, create a view, upload values from a file |
| `maya.catalogue` | read one resolved, amend, certify, seal and break a seal, transfer, retire, check a definition for free |
| `maya.views` | materialise rows, list versions, read as-of, stream data, ask what is retirable |
| `maya.featuresets` | define, preview a composition, fill, seal, assemble a training set, stream data |
| `maya.featureset_algebra` | the plan, restatements, roll forward, retrieval policy, transfer |
| `maya.contracts` | bind a version's inputs, and the namespaces serving must read |
| `maya.training_sets` | build one from a spine |

**Running, and watching**

| | |
|---|---|
| `maya.warrants` | grant, resolve, fit-warrant, execute, the grammar, profiles |
| `maya.validations` | open, record a test, conclude, replay |
| `maya.findings` | raise, assign, acknowledge, plan, extend, close, ageing, escalation |
| `maya.monitors` | define, evaluate, evaluate from telemetry, observations |
| `maya.distributed_monitoring` | an estate that will not fit in one process. A job computes **sufficient statistics** where the data is; MAYA computes the metric from them and compares it. Unlike an external observation, the result **can be replayed** |
| `maya.reports` | query the semantic layer, save and run views, export, regulatory returns |
| `maya.validation_aid` | vendor document coverage, challenge questions, untested assumptions |
| `maya.regime_encoding` | propose an encoding from regulatory text; never activates |
| `maya.probes` | derive a probe set from a declared domain, grade one |
| `maya.remediation` | the cheapest route to a model being in force, computed |
| `maya.migrations` | judge an equivalence claim about two artifacts |
| `maya.supervisory` | matters a regulator raised, their scope and the committed date |
| `maya.backlog` | validator workload, declared capacity, forecast, queue |
| `maya.campaigns` | open a round over a frozen population, respond, close |
| `maya.intake` | record a proposal, read the assessment, triage, register |
| `maya.runs` | declare a run before it happens, close it, read a search |
| `maya.retraining` | when a re-fit is due, and the standing approval for one |
| `maya.composites` | resolve a chain of models as one unit, or refuse it as one |
| `maya.shadow` | authorise an advisory grant for mirrored traffic |
| `maya.elicitations` | convene a panel, record responses per round, conclude with dissent |
| `maya.overlay_disclosure` | the judgement component of the number, by period |
| `maya.configuration` | export, plan and apply the platform's own configuration |
| `maya.document_review` | comment on a compiled document; never edit one |
| `maya.request_time` | the inputs the caller brings, and what cannot be promised |
| `maya.concentration` | what several models depend on at once; never a score |
| `maya.feature_impact` | who is downstream of a feature, to the declared use |
| `maya.fibres` | what each trainability class must carry |

**Documents, and the platform itself**

| | |
|---|---|
| `maya.attachments` | attach a file, list, download, review |
| `maya.documents` | compile, read, the dossier, a training record |
| `maya.packages` | cut an evidence package, its manifest |
| `maya.principals` | people, services, roles, permissions, suspend and reinstate |
| `maya.api_keys` | issue, list, revoke — how a service authenticates |
| `maya.whoami()` | who you are and what you may do — from the platform, never derived here |
| `maya.health()`, `maya.verify_evidence()` | is it up, and does the chain still verify |
| `maya.call(...)` | the escape hatch, for anything the SDK does not name |

**The register's edges** — where MAYA touches something it does not control, and
says so in narrower words than the name suggests

| | |
|---|---|
| `maya.timestamps` | a time an RFC 3161 authority attests to. Bounds a head from **above only** — it stops backdating, and says nothing about deletion or about anything before the first token |
| `maya.plugins` | what a firm's own package declares. Discovery imports nothing; enabling needs configuration to name it, because a control that switched on with a dependency bump is one nobody turned on |
| `maya.connectors` | MLflow, Unity Catalog, a git tree — read from an export, never an API, and producing candidates for triage rather than registrations |
| `maya.scanner_contract` | what somebody else's discovery scanner has to send. Precision is computable; **recall is not**, and the grade says so |
| `maya.shares` | a time-boxed link to a **content digest**, for a reader with no login. Not a portal, and it establishes no identity |
| `maya.rendering` | a compiled document as typesetting source with its citations intact. MAYA runs no typesetter, and coverage gaps are written *into* the output |
| `maya.rule_import` | a CSV decision table or a DMN file, read into a rule set **candidate**. Read `untranslated` first — a document with any entry there is refused whole, because a parser finds the judgement calls hard and the judgement calls are what a rulebook exists for |
| `maya.warrant_signing` | what a signature proves, and the key an engine verifies its **own** warrants with. `posture()` says plainly that it does not prove authorship to a third party; `key()` is the only call here that returns a secret |

## Three things worth knowing before you use it

**A refusal is an exception.** `Refused` carries `code`, `detail`, `remediation`,
`status` and `request_id`. `NotAuthenticated`, `NotPermitted`, `NotFound` and
`Blocked` are subclasses, so the refusal a first-line tool wants to handle — the
user may not do this, hide the button — is catchable on its own. `Unreachable` is
**not** a subclass of `Refused`: MAYA saying no and MAYA not answering call for
opposite responses.

**Datasets go to a file.** `featuresets.data(...)` writes and returns a `Path`.
Feature values are not small, and an SDK that materialised them to be convenient
would be convenient until the first real dataset.

**The SDK decides nothing.** No tier arithmetic, no local approval check, no copy
of the vocabularies. Ask `maya.warrants.grammar()` rather than hard-coding verbs;
ask `maya.whoami()` rather than reasoning about permissions. A second
implementation of a governance rule disagrees with the first eventually, and it
disagrees in the direction of permitting more.

## Testing

The suite lives with the platform (`tests/test_sdk.py`) and drives the real
application in-process through the transport seam — a mock of the thing under
test proves only that the mock agrees with itself.

```bash
.venv/bin/python -m pytest tests/test_sdk.py -q
```
