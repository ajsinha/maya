# MAYA — Java SDK

**Built.** `mvn -q test` — 17 tests, no runtime dependencies.

This file was the contract before there was an implementation, and it is kept in
that order deliberately: what follows is what a MAYA client *must* do, and the
implementation is held to it rather than described by it.

```java
Maya maya = Maya.withApiKey("https://maya.internal", System.getenv("MAYA_API_KEY"));

Map<String, Object> descriptor = maya.resolve(
    "maya://model/credit.pd.smallbiz#champion", "prod",
    "svc/origination", "origination_decision");

try (var sink = Files.newOutputStream(Path.of("training.parquet"))) {
    maya.streamFeaturesetData("credit.origination", 3, "parquet", sink);
}
```

## Building it

Requires a JDK with a compiler — JDK 21 or 17. A JRE-only install will fail at
`maven-compiler-plugin` with *release version 17 not supported*, which reads as
a Maven problem and is not one:

```
JAVA_HOME=/path/to/a/jdk mvn -q test
```

Compiled to **release 17**, because that is the LTS most banks are on, and not
because anything here wants to be old. `HttpClient.close()` is 21-only and is
therefore not used.

## No dependencies, and that is the design

`java.net.http` has been in the JDK since 11, and the JSON this client needs is
small enough to read and write by hand — `Json.java`, about two hundred lines.
That is a smaller cost than asking a bank's platform team to get Jackson through
an approval process so a service can call the register, and it is the same
reason every front-end asset in this repository is vendored: a governance
platform that cannot be deployed air-gapped is one somebody works around, and an
SDK with a dependency tree moves that problem into the client's build rather
than solving it.

JUnit is the exception and reaches only the test classpath.

## What a caller gets back

`Map<String, Object>`, with the platform's own field names — the names in its
documentation, its OpenAPI document and its error messages.

There is deliberately **no typed model class** and no generated client. A Java
object graph mirroring the platform's schemas is a second description of them,
and a second description goes stale in the permissive direction. The Python SDK
made the same choice for the same reason.

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
trainability class appearing in code rather than in prose. `MayaTest`
`DecidesNothing` is the Java equivalent: it walks `src/main/java`, strips the
comments — which argue about governance constantly and should — and fails on a
trainability class, a tier table or a local `isApproved` appearing in the
**code**. This is the rule most likely to be broken by somebody being helpful.

## What the tests assert, and what they cannot

The Python suite runs against the real application in-process, because a mock of
the thing under test proves only that the mock agrees with itself. Java cannot
reach that seam without standing a server up, so these tests take the other half
of the job: the properties that are **local to the client**, and that are the
ones a Java client gets wrong.

That a `POST` says *do not retry me* and a `GET` says it is safe. That an
outage is not a `Refused` and cannot be caught as one. That the remediation
survives into the exception message, including when FastAPI has nested the
problem document under `detail` — a client reading only the top level reports
every such refusal with no remediation at all. That a proxy's HTML is kept
rather than thrown over. That the digest is computed from the file and matches a
**constant**, not a second computation, because two implementations of the same
mistake agree.

What they do not assert is that any endpoint exists or behaves as expected. That
is what `sdk/python`'s suite is for, and duplicating it here would be a second
set of expectations about the platform — which is the same failure as a second
set of rules, one layer up.

## Reference

`sdk/python/maya_sdk` is the worked example, and its docstrings carry the
reasoning rather than a description of the syntax.
