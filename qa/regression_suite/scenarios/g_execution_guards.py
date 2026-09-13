"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section G — the checks the captive engine makes before it loads anything.

The captive engine is convenience only: it is reached through the same
contract an external engine uses, and disabling it changes nothing else. What
makes it worth testing is the ORDER — everything above the artifact is checked
without touching a file, so a refusal is cheap and an artifact never loads on
an authorisation that was never valid.

Two of the checks are about a warrant being a document from ELSEWHERE.
Treating a path inside it as trustworthy is how a governance system becomes a
file-read primitive, and a warrant naming a digest over an engine that does
not check it is a chain of custody with its last link missing — the only link
that touches what actually executes.
"""
from __future__ import annotations

from typing import ClassVar

from qa.regression_suite.scenarios.common import (BLOCKED, FAIL, PASS, Ctx,
                                                  Result, case)
from qa.regression_suite.scenarios.g_execution import governed

X = "/api/v1/execute"
W = "/api/v1/warrants"


def _engine(ctx: Ctx):
    return ctx.ui.app.state.ctx.get("engine") or \
        ctx.ui.app.state.ctx.get("execution")


def _entitled(ctx: Ctx) -> str:
    """A governed model with a warrant issued to `svc-pricing`."""
    made = governed(ctx)
    urn = made["urn"]
    ctx.api.post(W, json={"urn": urn, "principal": "svc-pricing",
                          "environment": "prod",
                          "declared_use": "credit_decision"})
    return urn


def _run(ctx: Ctx, urn: str, **over):
    body = {"urn": urn, "principal": "svc-pricing", "environment": "prod",
            "declared_use": "credit_decision", "inputs": {"x": 1.0}}
    body.update(over)
    return ctx.api.post(X, json=body, auth=ctx.people["owner"])


@case("QA-FX-441", "The order of the six pre-artifact checks")
def fx_441(ctx: Ctx) -> Result:
    """The property that makes a refusal cheap. A warrant failing on
    authorisation must be refused BEFORE anything opens an artifact — an
    engine that loaded first and checked second would read a file on behalf
    of a caller who was never entitled to it."""
    import inspect
    engine = _engine(ctx)
    if engine is None:
        return BLOCKED, "no captive engine is wired"
    source = inspect.getsource(type(engine).execute)
    order = []
    for marker, label in (("self.warrants.resolve", "resolve"),
                          ("self.warrants.verify", "signature"),
                          ("_revoked_locally", "revocation"),
                          ("_refuse_stale_epoch", "epoch"),
                          ("is_expired", "expiry"),
                          ("check_inputs", "boundary")):
        at = source.find(marker)
        if at < 0:
            return FAIL, f"the engine does not check '{label}' at all"
        order.append((at, label))
    loads = max(source.find("self.sandbox.run"),
                source.find("self.runtimes.invoke"))
    if loads < 0:
        return FAIL, "the engine never dispatches to a runtime"
    late = [label for at, label in order if at > loads]
    if late:
        return FAIL, (f"{late} are checked AFTER the artifact is dispatched, "
                      f"so a file is read on an authorisation that may never "
                      f"have been valid")
    return PASS, (f"six checks, all before dispatch: "
                  f"{', '.join(l for _a, l in sorted(order))}")


@case("QA-FX-438", "A tampered signature")
def fx_438(ctx: Ctx) -> Result:
    """The warrant is a document from elsewhere and the seal is the only
    thing that makes it this register's. An engine that ran an unsealed
    warrant would be running whatever the caller wrote."""
    engine = _engine(ctx)
    if engine is None:
        return BLOCKED, "no captive engine is wired"
    urn = _entitled(ctx)
    got = ctx.api.post("/api/v1/resolve",
                       json={"urn": urn, "principal": "svc-pricing",
                             "environment": "prod",
                             "declared_use": "credit_decision"})
    if got.status_code >= 400:
        return BLOCKED, f"no warrant could be resolved: {got.text[:140]}"
    body = got.json() or {}
    # The resolve response IS the warrant document; `maya_warrant` is the
    # version marker at its top level, not a nested envelope.
    warrant = body
    if not engine.warrants.verify(warrant):
        return BLOCKED, "the freshly issued warrant does not verify"
    broke = []
    for field, value in (("warrant_id", "forged"),
                         ("subject", {"model_urn": "maya://model/theirs",
                                      "version": "9.9.9"})):
        if field not in warrant:
            continue
        if engine.warrants.verify({**warrant, field: value}):
            return FAIL, (f"a warrant with '{field}' rewritten still verifies, "
                          f"so the seal does not cover it")
        broke.append(field)
    signature = dict(warrant.get("signature") or {})
    if signature.get("value"):
        signature["value"] = "0" * len(signature["value"])
        if engine.warrants.verify({**warrant, "signature": signature}):
            return FAIL, "a zeroed signature still verifies"
        broke.append("signature")
    if not broke:
        return BLOCKED, "the warrant carries none of the fields to tamper with"
    return PASS, f"rewriting {', '.join(broke)} breaks the seal"


@case("QA-FX-439", "The signing key rotated between issue and execution")
def fx_439(ctx: Ctx) -> Result:
    """A warrant sealed under a key the engine no longer holds is not this
    register's warrant any more. Accepting it would mean a rotation does not
    rotate anything."""
    engine = _engine(ctx)
    if engine is None:
        return BLOCKED, "no captive engine is wired"
    urn = _entitled(ctx)
    got = ctx.api.post("/api/v1/resolve",
                       json={"urn": urn, "principal": "svc-pricing",
                             "environment": "prod",
                             "declared_use": "credit_decision"})
    if got.status_code >= 400:
        return BLOCKED, f"no warrant could be resolved: {got.text[:140]}"
    warrant = got.json() or {}
    signer = getattr(engine.warrants, "signer", None)
    if signer is None or not hasattr(signer, "_key"):
        return BLOCKED, "the signer's key is not reachable to rotate"
    was = signer._key
    try:
        signer._key = b"a-rotated-signing-secret"
        if engine.warrants.verify(warrant):
            return FAIL, ("a warrant sealed under the old key still verifies "
                          "after rotation, so rotating the key rotates "
                          "nothing")
    finally:
        signer._key = was
    if not engine.warrants.verify(warrant):
        return FAIL, "the warrant stopped verifying under its own key"
    return PASS, "refused under the rotated key, accepted under its own"


@case("QA-FX-416", "An artifact path resolving outside the configured root")
def fx_416(ctx: Ctx) -> Result:
    """`is_relative_to`, not a string prefix: `/srv/artifacts-backup/x`
    begins with `/srv/artifacts` and is a different directory. A path inside
    a warrant is the least trustworthy thing in it."""
    from pathlib import Path

    from core.execution.errors import WarrantError
    from core.execution.runtimes.base import resolve_path
    root = Path("/srv/artifacts")

    class Call:
        # `uri.split("://", 1)[-1]` is what is joined to the root, so the
        # traversal has to be in THAT part. `artifact/../artifacts-backup`
        # lands back inside the root and proves nothing.
        artifact: ClassVar[dict] = {
            "uri": "maya://../artifacts-backup/x.onnx"}

    try:
        resolve_path(Call(), root)
    except WarrantError as exc:
        if getattr(exc, "code", "") != "artifact_outside_root":
            return FAIL, f"refused '{getattr(exc, 'code', exc)}'"
    else:
        return FAIL, "a traversing path resolved inside the root"

    class Sibling:
        """A path INSIDE the root that simply is not there. It must refuse
        `artifact_missing` rather than `artifact_outside_root`, or the two
        situations — somebody attacking the path and somebody forgetting to
        publish — read the same."""

        artifact: ClassVar[dict] = {"uri": "maya://artifact/x"}

    try:
        resolve_path(Sibling(), root)
    except WarrantError as exc:
        code = getattr(exc, "code", "")
        if code != "artifact_missing":
            return FAIL, (f"a legitimate path inside the root refused "
                          f"'{code}' rather than being reported missing")
        return PASS, ("traversal refused 'artifact_outside_root'; a real path "
                      "inside the root refused 'artifact_missing'")
    return FAIL, "a path that is not there resolved anyway"


@case("QA-FX-418", "No artifact root configured at all")
def fx_418(ctx: Ctx) -> Result:
    """An engine with nowhere to read from must say so rather than resolving
    against the process's working directory, which is how a governance
    system becomes a file-read primitive."""
    from core.execution.errors import WarrantError
    from core.execution.runtimes.base import resolve_path

    class Call:
        artifact: ClassVar[dict] = {"uri": "maya://artifact/x.onnx"}

    try:
        resolve_path(Call(), None)
    except WarrantError as exc:
        if getattr(exc, "code", "") != "no_artifact_root":
            return FAIL, f"refused '{getattr(exc, 'code', exc)}'"
        if "artifact_dir" not in getattr(exc, "remediation", ""):
            return FAIL, "the refusal does not name the setting to configure"
        return PASS, "refused 'no_artifact_root', naming the setting"
    return FAIL, ("an engine with no artifact root resolved a path anyway, so "
                  "it reads relative to whatever the process's directory is")


@case("QA-FX-414", "An artifact whose digest does not match the warrant")
def fx_414(ctx: Ctx) -> Result:
    """The last link in the chain of custody, and the only one that touches
    what actually executes. Refused BEFORE the bytes are handed to a
    runtime."""
    import tempfile
    from pathlib import Path

    from core.execution.errors import WarrantError
    from core.execution.runtimes.base import verify_artifact
    with tempfile.TemporaryDirectory() as tmp:
        artifact = Path(tmp) / "model.onnx"
        artifact.write_bytes(b"the bytes that are actually here")
        wrong = "sha256:" + "0" * 64
        try:
            verify_artifact(artifact, wrong)
        except WarrantError as exc:
            if getattr(exc, "code", "") != "artifact_mismatch":
                return FAIL, f"refused '{getattr(exc, 'code', exc)}'"
            if "security incident" not in getattr(exc, "remediation", ""):
                return FAIL, ("the refusal does not say this is a security "
                              "incident, so it reads as a configuration slip")
        else:
            return FAIL, ("an artifact whose digest does not match the warrant "
                          "was accepted")
        try:
            verify_artifact(artifact, "")
        except WarrantError as exc:
            if getattr(exc, "code", "") != "artifact_unverifiable":
                return FAIL, (f"an artifact with NO digest refused "
                              f"'{getattr(exc, 'code', exc)}'")
        else:
            return FAIL, ("an artifact carrying no digest in the warrant was "
                          "accepted, so what runs is never checked against "
                          "what was approved")
    return PASS, "mismatch and absence refused apart, both before the load"


@case("QA-FX-412", "A runtime the captive engine never implemented")
def fx_412(ctx: Ctx) -> Result:
    """501 and not 500. A runtime this build does not have is a statement
    about the deployment, and the refusal has to name what it DOES
    implement — otherwise a caller cannot tell an unsupported runtime from a
    broken one."""
    engine = _engine(ctx)
    if engine is None:
        return BLOCKED, "no captive engine is wired"
    described = engine.implements()
    if not described:
        return BLOCKED, "the engine implements nothing"
    # `implements()` answers a list of DICTS describing each runtime, not a
    # list of names — testing membership against it as strings raises.
    implemented = [r.get("runtime") or r.get("name") or ""
                   if isinstance(r, dict) else str(r) for r in described]
    from core.execution.errors import WarrantError
    from core.execution.runtimes.base import Invocation
    # The dispatcher reads `realisation.runtime`. Putting it under
    # `realisation.entry.runtime` falls through to the callables runtime,
    # which refuses "no callable is bound" — a different control.
    warrant = {"warrant_id": "w", "subject": self_subject(),
               "realisation": {"runtime": "a-runtime-nobody-wrote",
                               "entry": {}, "artifact": {}}}
    try:
        engine.runtimes.invoke(Invocation(warrant, {}))
    except WarrantError as exc:
        code = getattr(exc, "code", "")
        if code != "no_runtime":
            return FAIL, f"refused '{code}' rather than 'no_runtime'"
        said = f"{exc} {getattr(exc, 'remediation', '')}"
        named = [r for r in implemented if r and r in said]
        if "a-runtime-nobody-wrote" not in said:
            return FAIL, "the refusal does not name the runtime that was asked for"
        if not named:
            return FAIL, (f"the refusal does not name what the engine does "
                          f"implement ({implemented}), so an unsupported "
                          f"runtime reads like a broken one")
        return PASS, f"refused 'no_runtime', naming {len(named)} it has"
    except Exception as exc:
        return FAIL, (f"an unknown runtime raised {type(exc).__name__} rather "
                      f"than a named refusal: {exc}")
    return FAIL, "an unknown runtime was dispatched"


def self_subject() -> dict:
    return {"model_urn": "maya://model/x", "version": "1.0.0"}


@case("QA-FX-427",
      "The engine holds no reference to the registry or the feature store")
def fx_427(ctx: Ctx) -> Result:
    """Asserted by construction. An execution engine that could read the
    register would be able to decide its own authorisation, and one that
    could read the feature store would be choosing the values it ran on —
    which is the decision the approval exists to make."""
    engine = _engine(ctx)
    if engine is None:
        return BLOCKED, "no captive engine is wired"
    held = {name: type(value).__name__ for name, value in vars(engine).items()
            if value is not None}
    # `sandbox` is not a register read — it is where an artifact runs. What
    # must not be here is anything that lets the engine look up its own
    # authorisation or choose the values it runs on.
    forbidden = [name for name in held
                 if any(word in name.lower()
                        for word in ("registry", "catalogue", "featurestore",
                                     "feature_store", "features", "database"))
                 or name.lower() in ("db",)]
    if forbidden:
        return FAIL, (f"the engine holds {forbidden}: it can read what it is "
                      f"supposed to be told, so it could decide its own "
                      f"authorisation or choose the values it runs on")
    return PASS, f"holds {sorted(held)} and nothing that reads the register"
