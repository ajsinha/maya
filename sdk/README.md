# MAYA SDKs

One folder per language. Each is a **client and nothing more**.

```
sdk/
  python/     maya_sdk — built, tested against the real application
  java/       not built; the contract it must honour is written down
```

## The rule every SDK here keeps

**An SDK never decides anything.**

It carries requests and translates refusals. It holds no rule about who may act,
no local view of whether a version is approved, no copy of the tiering bands, no
idea which verbs a trainability class admits. Every one of those would be a
second implementation of a governance rule — and a second implementation is a
thing that can disagree with the first, quietly, in the direction of permitting
more, because that is the direction in which nobody files a bug.

What an SDK is *for* is the other half of the same principle: **the compliant
path has to be the fast path.** If registering a model properly takes forty lines
of HTTP plumbing and getting it wrong takes four, the register fills with models
nobody registered properly, and the inventory rots while every control reports
success.

## What that means concretely

| | |
|---|---|
| **Refusals are raised, never returned** | A caller who forgets to check a returned verdict has continued past a governance decision while their code reads as though it succeeded |
| **The remediation survives the crossing** | It is the half that makes a refusal usable, and the half a naive client throws away |
| **`Refused` and `Unreachable` are different** | "MAYA said no" and "MAYA did not answer" call for opposite responses; collapsing them treats an outage as a verdict |
| **`POST` is never retried** | A create that timed out may well have succeeded, and retrying it registers the model twice |
| **Datasets stream to a file** | Feature values are not small; an SDK that returned a list of dictionaries would be convenient until the first real dataset |
| **Credentials are presented, never ambient** | HTTP Basic, so no CSRF token applies — a property of the design rather than an exemption from it |
| **The request id is carried** | It is in every exception, so a traceback quotes the identifier the server logged |

## Adding a language

Read [`java/README.md`](java/README.md). It states the contract rather than
sketching an implementation, because the contract is the part that is the same
in every language and the part an implementation gets wrong.
