"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section I — a time somebody else will stand behind, and bytes that are their
own address.

A timestamp is the bound that stops a record being reconstructed after the fact
and called old. It does **not** say the head existed no earlier, it says
nothing about a record deleted before any token was taken, and it cannot see
behind the first one. MAYA does not act as the authority and does not verify
the token either — checking an RFC 3161 token means holding a certificate chain
and deciding which roots to trust, and that is a decision the firm's security
function has already made differently. So there are three states and
`unverified` never collapses into either neighbour, because a token nobody
could check reading as no token at all is the failure the three states exist
against.

Artifacts are the other half: content addressing makes tampering hard rather
than impossible, because the filesystem is still a filesystem. Re-hashing is
how you find out, and it is deliberately a separate call — which makes *who
calls it* the question worth asking.
"""
from __future__ import annotations

import hashlib
import pathlib
import time

from qa.regression_suite.scenarios.common import (BLOCKED, FAIL, PASS, Ctx,
                                                  Result, case, code_of)

M = "/api/v1/models"
ART = "/api/v1/artifacts"
TS = "/api/v1/evidence/timestamps"
SHAPE = {"model_class": "logistic", "domain": "credit",
         "legal_entity": "LE-US-01", "purpose": "credit_decision"}


def _evidence(ctx: Ctx):
    return ctx.ui.app.state.ctx.get("evidence")


def _stamps(ctx: Ctx):
    return ctx.ui.app.state.ctx.get("chain_timestamps")


def _acts(ctx: Ctx, how_many: int = 3) -> None:
    for _ in range(how_many):
        name = ctx.unique("ts")
        ctx.api.post(M, json={"urn": f"maya://model/{name}", "name": name,
                              "owner": "owner", **SHAPE},
                     auth=ctx.people["owner"])


class _Authority:
    """A stub authority. Returns whatever token the case needs to see stored."""

    name = "qa-authority"

    def __init__(self, token):
        self.token = token
        self.asked = 0

    def stamp(self, digest):
        self.asked += 1
        return dict(self.token, digest=digest)


# ------------------------------------------------------------------ timestamps
@case("QA-PLT-112", "Time-stamping a head that was never anchored",
      isolated=True)
def plt_112(ctx: Ctx) -> Result:
    """A token over a head nobody wrote outside the database attests to a
    hash nothing can later be compared against — a receipt rather than a
    control."""
    stamps = _stamps(ctx)
    if stamps is None:
        return BLOCKED, "no chain timestamps are wired"
    _acts(ctx, 2)
    stamps.authority = _Authority({"genTime": time.time()})
    try:
        stamps.stamp(actor="qa")
    except Exception as exc:
        code = getattr(exc, "code", None)
        if code != "nothing_anchored":
            return FAIL, f"refused '{code}': {str(exc)[:130]}"
        if "compared against" not in str(exc) + str(getattr(exc, "remediation", "")):
            return FAIL, "the refusal does not say why an unanchored head is useless"
        return PASS, f"refused 'nothing_anchored': {str(exc)[:110]}"
    finally:
        stamps.authority = None
    return FAIL, "a head nobody anchored was timestamped"


@case("QA-PLT-113", "The same head stamped twice", isolated=True)
def plt_113(ctx: Ctx) -> Result:
    """`written: 0` and no second object. A second token at one head is
    either a duplicate to suppress or an overwrite to refuse, and the
    write-once store would refuse the second — so this has to be caught
    before it gets there."""
    evidence, stamps = _evidence(ctx), _stamps(ctx)
    if evidence is None or stamps is None:
        return BLOCKED, "no evidence chain or timestamps are wired"
    _acts(ctx, 3)
    evidence.anchor_head(actor="qa")
    authority = _Authority({"genTime": time.time(), "serial": "A1"})
    stamps.authority = authority
    try:
        first = stamps.stamp(actor="qa")
        second = stamps.stamp(actor="qa")
    except Exception as exc:
        return FAIL, (f"the second stamp raised "
                      f"{getattr(exc, 'code', type(exc).__name__)}: "
                      f"{str(exc)[:120]}")
    finally:
        stamps.authority = None
    if first.get("written") != 1:
        return BLOCKED, f"the first stamp wrote nothing: {first}"
    if second.get("written") != 0:
        return FAIL, f"the second stamp reports written={second.get('written')}"
    if authority.asked != 1:
        return FAIL, (f"the authority was asked {authority.asked} times for one "
                      f"head — a second request costs money and produces a "
                      f"token nothing will store")
    held = list(pathlib.Path(evidence.anchors.root).glob("timestamp-*.json"))
    if len(held) != 1:
        return FAIL, f"{len(held)} timestamp object(s) in the store"
    return PASS, "one object, one request to the authority, written=0 on the second"


@case("QA-PLT-033", "A token is held and nothing here can check it",
      isolated=True)
def plt_033(ctx: Ctx) -> Result:
    """`unverified` — a weaker claim than verified and a much stronger one
    than absent. Collapsing the three into a boolean is how a token nobody
    could check comes to read as no token at all."""
    from core.evidence.timestamps import ABSENT, UNVERIFIED, VERIFIED
    evidence, stamps = _evidence(ctx), _stamps(ctx)
    if evidence is None or stamps is None:
        return BLOCKED, "no evidence chain or timestamps are wired"
    _acts(ctx, 3)
    anchored = evidence.anchor_head(actor="qa")
    at = anchored.get("seq")
    if not at:
        return BLOCKED, f"nothing was anchored: {anchored}"
    absent = stamps.read(at)
    if absent["state"] != ABSENT:
        return BLOCKED, f"the head already carries a token: {absent['state']}"
    stamps.authority = _Authority({"genTime": time.time()})
    try:
        stamps.stamp(actor="qa")
    finally:
        stamps.authority = None
    held = stamps.read(at)
    if held["state"] != UNVERIFIED:
        return FAIL, (f"a held token with no verifier reads "
                      f"'{held['state']}' rather than '{UNVERIFIED}'")
    if held["state"] == absent["state"]:
        return FAIL, "a held token and no token read the same"
    if not held.get("token"):
        return FAIL, "the state is unverified and no token is carried"
    if "no verifier is wired" not in (held.get("why") or ""):
        return FAIL, f"the answer does not say why it is unverified: {held}"
    if f", {VERIFIED}" in (held.get("detail") or ""):
        return FAIL, "an unverified token's detail claims it is verified"
    return PASS, (f"three distinct states; this one is '{held['state']}' "
                  f"carrying the token, and says why")


@case("QA-PLT-034", "A token dated after the moment it was requested",
      isolated=True)
def plt_034(ctx: Ctx) -> Result:
    """`requested_at` is recorded, and the module says why: *the gap between
    them is the only thing a reader can use to notice a token that was
    issued somewhere else.* This is whether anything computes that gap."""
    evidence, stamps = _evidence(ctx), _stamps(ctx)
    if evidence is None or stamps is None:
        return BLOCKED, "no evidence chain or timestamps are wired"
    _acts(ctx, 3)
    anchored = evidence.anchor_head(actor="qa")
    at = anchored.get("seq")
    if not at:
        return BLOCKED, f"nothing was anchored: {anchored}"
    ahead = time.time() + 365 * 86400
    stamps.authority = _Authority({"genTime": ahead, "serial": "A9"})
    try:
        stamps.stamp(actor="qa")
    except Exception as exc:
        code = getattr(exc, "code", None)
        return PASS, f"refused '{code}': {str(exc)[:120]}"
    finally:
        stamps.authority = None
    held = stamps.read(at)
    # Read the platform's OWN words, not the token — a stub whose serial says
    # "FUTURE" would otherwise satisfy this by echoing the fixture back.
    said = f"{held.get('why') or ''} {held.get('detail') or ''}".lower()
    if "future" in said or "ahead" in said:
        return PASS, f"the token is reported as future-dated: {said[:120]}"
    return FAIL, (
        f"an authority returned a token dated a year ahead of the request and "
        f"it was stored and read back with state '{held.get('state')}' and no "
        f"remark. `stamp` records `requested_at` alongside the token and the "
        f"module says exactly why — *the gap between them is the only thing a "
        f"reader can use to notice a token that was issued somewhere else* — "
        f"and nothing computes that gap. Not verifying an RFC 3161 token is a "
        f"stated decision; comparing two numbers MAYA wrote itself is not the "
        f"same decision, and the field is recorded for a purpose nothing "
        f"serves. `token_from_the_future` exists as a refusal code and is "
        f"raised only by the OIDC layer")


@case("QA-PLT-036", "A token over a head that is no longer the head",
      isolated=True)
def plt_036(ctx: Ctx) -> Result:
    """The token still bounds the head it names, and says nothing about
    later ones. That is the correct answer and the coverage detail has to
    carry it, because a reader who takes one token as covering the chain has
    the wrong idea of what was proved."""
    evidence, stamps = _evidence(ctx), _stamps(ctx)
    if evidence is None or stamps is None:
        return BLOCKED, "no evidence chain or timestamps are wired"
    _acts(ctx, 3)
    early = evidence.anchor_head(actor="qa")
    at = early.get("seq")
    if not at:
        return BLOCKED, f"nothing was anchored: {early}"
    stamps.authority = _Authority({"genTime": time.time(), "serial": "A1"})
    stamps.stamp(actor="qa")
    _acts(ctx, 3)
    later = evidence.anchor_head(actor="qa")
    if later.get("seq") == at:
        return BLOCKED, "the head did not move"
    still = stamps.read(at)
    fresh = stamps.read(later["seq"])
    if still.get("state") == "absent":
        return FAIL, "the earlier token stopped being readable when the head moved"
    if fresh.get("state") != "absent":
        return FAIL, "the new head reports a token nobody took"
    figure = stamps.coverage()
    stamps.authority = None
    if figure["covered"] >= figure["anchors"]:
        return FAIL, (f"{figure['covered']} of {figure['anchors']} anchored "
                      f"heads report covered after one token")
    if f"before sequence {at}" not in (figure.get("detail") or ""):
        return FAIL, (f"the coverage detail does not say what is NOT covered: "
                      f"{figure.get('detail')[:150]}")
    return PASS, (f"the token still names seq {at}; the new head at "
                  f"{later['seq']} reads absent; coverage "
                  f"{figure['covered']}/{figure['anchors']} and the detail "
                  f"names the uncovered span")


@case("QA-PLT-114", "Timestamp coverage on an estate with no anchors",
      isolated=True)
def plt_114(ctx: Ctx) -> Result:
    """`share: 0.0`, and a detail distinguishing *no anchors* from *no
    tokens*. Both are zero and they are different facts: one is nothing to
    attest to, the other is nothing attesting."""
    stamps = _stamps(ctx)
    evidence = _evidence(ctx)
    if stamps is None or evidence is None:
        return BLOCKED, "no chain timestamps are wired"
    bare = stamps.coverage()
    if bare["anchors"]:
        return BLOCKED, f"{bare['anchors']} anchor(s) already exist"
    if bare["share"] != 0.0 or bare["covered"]:
        return FAIL, f"an unanchored estate reports coverage: {bare}"
    if "nothing to timestamp" not in (bare.get("detail") or ""):
        return FAIL, (f"the zero does not say there is nothing to attest to: "
                      f"{bare.get('detail')[:150]}")
    _acts(ctx, 3)
    evidence.anchor_head(actor="qa")
    anchored = stamps.coverage()
    if anchored["share"] != 0.0:
        return FAIL, f"an untimestamped anchor reports share {anchored['share']}"
    if anchored.get("detail") == bare.get("detail"):
        return FAIL, ("an estate with nothing anchored and one with anchors "
                      "and no tokens give the same answer")
    if "authority" not in (anchored.get("detail") or ""):
        return FAIL, (f"the second zero does not say why nothing is stamped: "
                      f"{anchored.get('detail')[:150]}")
    if anchored.get("is_the_authority") is not False:
        return FAIL, "the platform reports itself as the timestamp authority"
    return PASS, (f"share 0.0 twice, two different sentences: "
                  f"{bare['detail'][:50]!r} then {anchored['detail'][:50]!r}")


@case("QA-PLT-111", "Time-stamping with the authority unconfigured")
def plt_111(ctx: Ctx) -> Result:
    """The refusal is right. The remediation names a configuration key, and
    a remediation is an instruction — one naming a key nothing reads sends
    the reader to set something that will not take effect."""
    import inspect

    import run_maya_web
    stamps = _stamps(ctx)
    if stamps is None:
        return BLOCKED, "no chain timestamps are wired"
    if stamps.authority is not None:
        return BLOCKED, "an authority is wired in this instance"
    try:
        stamps.stamp(actor="qa")
    except Exception as exc:
        code = getattr(exc, "code", None)
        if code != "no_timestamp_authority":
            return FAIL, f"refused '{code}' rather than naming the gap"
        remediation = str(getattr(exc, "remediation", ""))
    else:
        return FAIL, "a chain with no authority produced a timestamp"
    key = "evidence.timestamps"
    if key not in remediation:
        return BLOCKED, f"the remediation names no key: {remediation[:130]}"
    source = inspect.getsource(run_maya_web)
    reads = [ln.strip() for ln in source.splitlines()
             if "cfg.get(" in ln and "timestamp" in ln.lower()]
    wiring = [ln.strip() for ln in source.splitlines()
              if "ChainTimestamps(" in ln]
    if reads:
        return PASS, f"the key is read: {reads[0][:110]}"
    return FAIL, (
        f"the refusal is correct and its remediation says *configure one under "
        f"`{key}`* — and nothing reads that key. `ChainTimestamps` is "
        f"constructed with `authority=None, verifier=None` as literals "
        f"({wiring[0][:60] if wiring else 'not found'}…), and "
        f"`cfg.get('{key}...')` appears nowhere in the application. A "
        f"deployer following the remediation sets a key the platform never "
        f"looks at and gets the same refusal, having been told what to do by "
        f"the thing refusing")


# ------------------------------------------------------------------- artifacts
@case("QA-PLT-038", "An artifact digest in the register that resolves to nothing")
def plt_038(ctx: Ctx) -> Result:
    """A version can name an artifact that is not there. Reading it must be
    a refusal that names what is missing, not an empty stream."""
    store = ctx.ui.app.state.ctx.get("artifacts")
    if store is None:
        return BLOCKED, "no artifact store is wired"
    body = b"a model artifact that will be deleted"
    digest = "sha256:" + hashlib.sha256(body).hexdigest()
    uploaded = ctx.api.post(f"{ART}?format=onnx", content=body,
                            auth=ctx.people["developer"])
    if uploaded.status_code >= 400:
        return BLOCKED, f"the artifact could not be stored: {uploaded.text[:150]}"
    stored = (uploaded.json() or {}).get("digest") or digest
    path = store._path(stored)
    if not path.exists():
        return BLOCKED, "the artifact was not written to disk"
    path.unlink()
    got = ctx.api.get(f"{ART}/{stored}", auth=ctx.people["developer"])
    if got.status_code < 400:
        return FAIL, (f"an artifact whose bytes are gone was served "
                      f"{got.status_code} with {len(got.content)} byte(s)")
    if code_of(got) != "artifact_not_stored":
        return FAIL, f"refused '{code_of(got)}' at {got.status_code}"
    if stored[:23] not in got.text:
        return FAIL, "the refusal does not name what is missing"
    return PASS, f"refused 'artifact_not_stored' at {got.status_code}"


@case("QA-PLT-039", "An artifact whose bytes changed under a stable digest")
def plt_039(ctx: Ctx) -> Result:
    """Content addressing makes tampering hard rather than impossible — the
    filesystem is still a filesystem. Re-hashing is a separate call by
    design, so the question is what reads the artifact WITHOUT making it."""
    store = ctx.ui.app.state.ctx.get("artifacts")
    if store is None:
        return BLOCKED, "no artifact store is wired"
    body = b"the approved model artifact"
    uploaded = ctx.api.post(f"{ART}?format=onnx", content=body,
                            auth=ctx.people["developer"])
    if uploaded.status_code >= 400:
        return BLOCKED, f"the artifact could not be stored: {uploaded.text[:150]}"
    stored = (uploaded.json() or {})["digest"]
    path = store._path(stored)
    path.chmod(0o600)
    path.write_bytes(b"a DIFFERENT model artifact entirely")
    checked = ctx.api.get(f"{ART}/{stored}/verify", auth=ctx.people["developer"])
    served = ctx.api.get(f"{ART}/{stored}", auth=ctx.people["developer"])
    report = checked.json() or {}
    if report.get("intact"):
        return FAIL, f"re-hashing does not notice the change: {report}"
    if served.status_code >= 400:
        return PASS, (f"a read refuses too: '{code_of(served)}', and verify "
                      f"reports intact={report.get('intact')}")
    if served.content == body:
        return BLOCKED, "the read did not serve the changed bytes"
    return FAIL, (
        f"the bytes under {stored[:23]}… were replaced. `GET "
        f"{ART}/{{digest}}/verify` re-hashes and reports intact=False with "
        f"recomputed {str(report.get('recomputed'))[:23]}…, and `GET "
        f"{ART}/{{digest}}` serves the substituted bytes with "
        f"{served.status_code}. That separation is deliberate and documented — "
        f"re-hashing a multi-gigabyte file on every read is not free — so the "
        f"control rests entirely on somebody CALLING verify. The execution "
        f"path does call it (`verify_artifact` in the runtimes, before every "
        f"load), and nothing else does: no scheduled job re-hashes the store, "
        f"so an artifact that is never executed is never checked again after "
        f"the upload")


@case("QA-PLT-040", "An artifact path pointed outside the artifact root")
def plt_040(ctx: Ctx) -> Result:
    """A store that serves anything on the filesystem is a store that serves
    the configuration file. The address is validated as an address rather
    than resolved and then compared, so nothing depends on a path
    comparison."""
    store = ctx.ui.app.state.ctx.get("artifacts")
    if store is None:
        return BLOCKED, "no artifact store is wired"
    from core.artifacts.common import ArtifactError
    attempts = {
        "traversal": "sha256:../../../../etc/passwd",
        "separator": "sha256:aa/bb/cc",
        "short": "sha256:abc",
        "not hex": "sha256:" + "z" * 64,
        "no scheme": "../" * 8 + "etc/passwd",
    }
    for what, digest in attempts.items():
        try:
            resolved = store._path(digest)
        except ArtifactError as exc:
            if exc.code != "malformed_digest":
                return FAIL, f"{what} refused '{exc.code}'"
            continue
        root = pathlib.Path(store.root).resolve()
        if root not in resolved.resolve().parents:
            return FAIL, (f"{what} resolved to {resolved} which is outside "
                          f"{root}")
        return FAIL, f"{what} was accepted and resolved inside the root"
    over_http = ctx.api.get(f"{ART}/{attempts['traversal']}",
                            auth=ctx.people["developer"])
    if over_http.status_code < 400:
        return FAIL, (f"a traversal in the digest position was served "
                      f"{over_http.status_code} over HTTP")
    return PASS, (f"{len(attempts)} malformed addresses refused "
                  f"'malformed_digest' at the store, and "
                  f"{over_http.status_code} over HTTP")


@case("QA-PLT-035", "A token past its validity", isolated=True)
def plt_035(ctx: Ctx) -> Result:
    """The other side of QA-PLT-034. An expired token accepted and then
    rendered as coverage is worse than no token: the coverage figure is the
    one number a supervisor is shown about the chain's age."""
    evidence, stamps = _evidence(ctx), _stamps(ctx)
    if evidence is None or stamps is None:
        return BLOCKED, "no evidence chain or timestamps are wired"
    _acts(ctx, 3)
    anchored = evidence.anchor_head(actor="qa")
    at = anchored.get("seq")
    if not at:
        return BLOCKED, f"nothing was anchored: {anchored}"
    long_ago = time.time() - 10 * 365 * 86400
    stamps.authority = _Authority({"genTime": long_ago,
                                   "notAfter": long_ago + 86400,
                                   "serial": "B2"})
    try:
        stamps.stamp(actor="qa")
    except Exception as exc:
        code = getattr(exc, "code", None)
        return PASS, f"refused '{code}': {str(exc)[:120]}"
    figure = stamps.coverage()
    said = f"{figure.get('detail') or ''}".lower()
    stamps.authority = None
    if "expire" in said:
        return PASS, f"the expiry is reported in coverage: {said[:120]}"
    if figure["covered"] < 1:
        return PASS, "an expired token is not counted as coverage"
    return FAIL, (
        f"a token whose validity ended nine years ago was stored and is "
        f"counted in coverage: {figure['covered']} of {figure['anchors']} "
        f"anchored head(s) 'carry a token'. Nothing in `stamp` looks at the "
        f"token at all — not `genTime`, not `notAfter` — because verification "
        f"is delegated to a verifier that is not wired, and coverage counts "
        f"`state != absent`. So the number a supervisor is shown about the "
        f"chain's age counts an attestation nobody would accept. The three "
        f"states are honest about what was CHECKED; the coverage figure "
        f"summarises them as though holding a token were the thing that "
        f"mattered")
