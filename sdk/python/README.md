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

| | |
|---|---|
| `maya.models` | register, read, assess, submit, attest, relate, blast radius |
| `maya.versions` | create, approve, quorum, promote an alias |
| `maya.features` | define, derive, create a view, upload values |
| `maya.featuresets` | define, preview a composition, fill, seal, assemble a training set, stream data |
| `maya.warrants` | grant, resolve, fit-warrant, execute, grammar, profiles |
| `maya.artifacts` | put, get, verify, usage |
| `maya.parameters` | fit, record, review, provenance |
| `maya.whoami()` | who you are and what you may do — from the platform, never derived here |

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
