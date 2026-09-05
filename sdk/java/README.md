# MAYA — Java SDK

**Not built.** This file says what it has to do, so that when it is built it is a
client rather than a second implementation of the platform.

Stated rather than sketched, deliberately: a stub that compiles and does the
wrong thing is worse than an empty folder, because the folder is honest about
where the work is.

## The contract

Everything below is a property of *this* platform's API, not of HTTP in general.
A client that gets these wrong will look like it works.

### 1. A refusal is a decision, and it has three parts

Every refusal answers in one shape:

```json
{"error": "blocked",
 "detail": "an open blocking finding stands against credit.pd.smallbiz",
 "remediation": "close the finding, or ask the validator to downgrade it"}
```

Throw, do not return. Carry all three parts. The **remediation** is the half that
makes a refusal usable and the half a naive client discards.

Separate the classes a caller wants to catch on purpose:

| HTTP | Meaning | Suggested type |
|---|---|---|
| 401 | no credentials, or they did not verify | `NotAuthenticatedException` |
| 403 | authenticated, not allowed | `NotPermittedException` |
| 404 | no such thing | `NotFoundException` |
| 409 / 410 / 423 | a governance condition stands in the way | `BlockedException` |
| anything else | a refusal with nothing more specific to say | `RefusedException` |

And keep **"MAYA said no"** apart from **"MAYA did not answer"**. They call for
opposite responses, and a client that collapses them will eventually treat an
outage as a governance verdict.

### 2. Never retry a `POST`

`GET`, `HEAD`, `OPTIONS`, `PUT` and `DELETE` may be retried. `POST` may not: a
create that timed out may well have succeeded, and retrying it registers the
model twice or records two parameter sets. An SDK that quietly duplicates a
governance act is worse than one that fails loudly.

### 3. Authenticate with a credential, never a cookie

HTTP Basic against the principal register. A session cookie is *ambient* — a
browser sends it whether or not the page that triggered the request came from us
— which is why a mutating call under one needs a CSRF token. A credential the
caller presents is not ambient, so no token applies. Do not implement the cookie
flow; there is nothing for a service client to gain from it and a token to get
wrong.

### 4. Send a request id, and keep the one that comes back

Send `X-Request-ID` on every call and read it off the response — the server may
answer with a different one, and the one it answers with is the one it wrote
down. Put it on every exception. Without it, *"it failed"* and *"which of the
four thousand log lines was mine"* are two separate investigations.

### 5. Compute the artifact digest client-side

`POST /api/v1/artifacts?format=…&digest=sha256:…`. Hash the file **before**
uploading and send the digest. The platform checks what arrived against what was
meant, so a truncated upload is refused rather than stored under the address of
whatever turned up. Letting the server hash whatever it received makes the check
tautological.

### 6. Stream datasets; never materialise them

`GET /api/v1/featuresets/{name}/versions/{v}/data` returns Arrow, Parquet, NDJSON
or CSV, and it returns as much of it as exists. Write to a sink. A method that
returns a list of records is convenient until the first real dataset, at which
point it is an out-of-memory error inside somebody else's job.

### 7. Decide nothing

No local tier arithmetic. No client-side check of whether a version is approved.
No enumeration of trainability classes, verbs, runtimes or bindings — fetch
`GET /api/v1/grammar` and `GET /api/v1/grammar/schema` instead, so a vocabulary
that grows does not leave every client stale and confidently wrong.

The Python SDK's test suite asserts this by walking its own source for a
trainability class appearing in code rather than in prose. Whatever the
equivalent is in Java, write it: this is the rule most likely to be broken by
somebody being helpful.

## Reference

`sdk/python/maya_sdk` is the worked example, and its docstrings carry the
reasoning rather than a description of the syntax.
