"""
Execution warrants as live instruments (§9.2, §9.4, §28.5, §29.5).

An execution warrant answers *what can be run, on what inputs, by whom, until
when*. Once sealed it issues short-lived signed tokens; every SDK call checks
it and fails closed when it is expired, revoked or suspended, naming the
person to contact. Executions are reported back, covenants are evaluated on
each report, and a breach suspends the warrant immediately. Offline use is
possible and is labelled ``unattested``.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import base64
import datetime as dt
from typing import Any

from maya.core import djson
from maya.core.errors import (NotApproved, PermissionDenied, QuotaExceeded, ValidationFailed,
                              WarrantExpired, WarrantSuspended)
from maya.core.backends import Backends
from maya.formula import ir as irmod
from maya.core.clock import utcnow
from maya.security.authz import Principal
from maya.services import catalog, refs
from maya.workflow.engine import Subject

# Rate and volume limits (§9.2): they throttle, where a covenant breach suspends.
LIMIT_KEYS = ("max_calls_per_day", "max_rows_per_call", "max_rows_per_day")
COVENANT_KINDS = ("input_null_rate", "input_range", "output_range", "max_rows_per_day",
                  "staleness_days")
ENVIRONMENTS = ("dev", "uat", "prod")
TOKEN_MINUTES = 15


class ExecutionService:
    def __init__(self, platform: Any) -> None:
        self.p = platform

    def _load(self, uow: Any, ew_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
        ew = uow.repo("execution_warrants").require(ew_id)
        return ew, uow.repo("namespaces").require(ew["namespace_id"])

    @staticmethod
    def uri(ew: dict[str, Any], ns: dict[str, Any]) -> str:
        return f"maya://warrant/exec/{ns['name']}/{ew['name']}@v{ew['version_no']}"

    @staticmethod
    def status(ew: dict[str, Any]) -> str:
        now = utcnow()
        if ew.get("revoked_at"):
            return "revoked"
        if ew.get("suspended_at"):
            return "suspended"
        if ew.get("valid_to") and ew["valid_to"] < now:
            return "expired"
        if ew.get("sealed_at"):
            return "live"
        return ew["state"]

    def listing(self, uow: Any, p: Principal, *, q: str | None = None) -> Any:
        from maya.services.paging import Listing
        names = {n["id"]: n["name"] for n in uow.repo("namespaces").list()}
        return Listing(
            "execution_warrants", {"-created": "-created_at", "created": "created_at",
                                   "name": "name", "-name": "-name"},
            "-created", {}, (["name"], q or ""),
            keep=self.p.access.reader(uow, p, "execution_warrant"),
            enrich=lambda uow, ew: {**ew, "namespace": names.get(ew["namespace_id"]),
                                    "status": self.status(ew)})

    def list(self, p: Principal) -> list[dict[str, Any]]:
        with self.p.uow() as uow:
            return self.listing(uow, p).collect(uow)

    def page(self, p: Principal, *, q: str | None = None, page_size: int | None = None,
             cursor: str | None = None, sort: str | None = None, total: bool = False) -> dict[str, Any]:
        from maya.services.paging import run_page
        return run_page(self.p, lambda uow: self.listing(uow, p, q=q), page_size=page_size,
                        cursor=cursor, sort=sort, total=total)

    def get(self, p: Principal, ew_id: str) -> dict[str, Any]:
        with self.p.uow() as uow:
            ew, ns = self._load(uow, ew_id)
            self.p.access.require(uow, p, "read", "execution_warrant", ew)
            custody = uow.repo("custody_events").list(warrant_type="exec", warrant_id=ew_id,
                                                      order_by=["created_at"])
            offline = [c for c in custody if c["event"] == "offline_issued"]
            return {**ew, "namespace": ns["name"], "status": self.status(ew),
                    "uri": self.uri(ew, ns), "custody": custody,
                    "offline_use": {"label": "unattested" if offline else None,
                                    "copies_issued": len(offline),
                                    "last_issued_at": offline[-1]["created_at"]
                                    if offline else None},
                    "reports": uow.repo("execution_reports").list(
                        execution_warrant_id=ew_id, order_by=["-created_at"], limit=200),
                    "transitions": self.p.workflow.available(uow, self.subject(uow, ew, ns))}

    # -- creation -------------------------------------------------------------------
    def create(self, p: Principal, *, namespace: str, name: str,
               training_warrant_id: str | None = None, model: str | None = None,
               parameter_set_id: str | None = None, spec: dict[str, Any] | None = None
               ) -> dict[str, Any]:
        spec = self._spec(spec or {})
        with self.p.uow() as uow:
            ns = self.p.access.namespace(uow, namespace)
            self.p.access.require(uow, p, "create", "execution_warrant",
                                  {"id": "new", "namespace_id": ns["id"], "name": name})
            tw = uow.repo("training_warrants").require(training_warrant_id) \
                if training_warrant_id else None
            if tw is not None:
                mv = uow.repo("model_versions").require(tw["model_version_id"])
            elif model:
                r = refs.parse(model, "model")
                mobj, _ = catalog.find_object(uow, "models", "model", r)
                mv = catalog.version_of(uow, "model_versions", "model_id", mobj, r.version)
                if _trainable(mv):
                    raise ValidationFailed("A trainable model needs a training warrant and an "
                                           "approved parameter set")
            else:
                raise ValidationFailed("Name a training warrant, or a model for a "
                                       "non-trainable one")
            ps = uow.repo("parameter_sets").require(parameter_set_id) if parameter_set_id else None
            if _trainable(mv) and ps is None:
                raise ValidationFailed("The model declares parameters: name the approved "
                                       "parameter set this warrant runs")
            if ps is not None and tw is not None and ps["training_warrant_id"] != tw["id"]:
                raise ValidationFailed("The parameter set was not fitted under this training "
                                       "warrant")
            manifest = self._manifest(uow, mv, ps, tw, spec)
        with self.p.uow(p.username) as uow:
            prior = uow.repo("execution_warrants").list(namespace_id=ns["id"], name=name,
                                                        order_by=["-version_no"], limit=1)
            ew = uow.repo("execution_warrants").add({
                "namespace_id": ns["id"], "name": name,
                "version_no": prior[0]["version_no"] + 1 if prior else 1, "state": "draft",
                "owner_id": p.user_id, "training_warrant_id": training_warrant_id,
                "model_version_id": mv["id"], "parameter_set_id": parameter_set_id,
                "spec": spec, "manifest": manifest, "backends": Backends.provenance()})
            self.p.warrants._custody(uow, ew["id"], "created", p.username, warrant_type="exec")
            me = self.uri(ew, ns)
            if tw is not None:
                tns = uow.repo("namespaces").require(tw["namespace_id"])
                uow.repo("lineage_edges").link(self.p.warrants.uri(tw, tns), me, "executed_under")
            uow.audit("warrant.exec_created", object_type="execution_warrant", object_ref=me)
            return ew

    def _spec(self, spec: dict[str, Any]) -> dict[str, Any]:
        out: dict[str, Any] = {"valid_days": 90, "environments": ["dev"], "limits": {},
                               "contact": "", "covenants": []}
        out.update({k: v for k, v in spec.items() if v is not None})
        bad_env = set(out["environments"]) - set(ENVIRONMENTS)
        if bad_env:
            raise ValidationFailed(f"Unknown environment(s): {', '.join(bad_env)}")
        unknown = set(out["limits"]) - set(LIMIT_KEYS)
        if unknown:
            raise ValidationFailed(f"Unknown limit(s): {', '.join(sorted(unknown))}; limits are "
                                   f"{', '.join(LIMIT_KEYS)}")
        for key, value in out["limits"].items():
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValidationFailed(f"Limit '{key}' must be a positive whole number")
        for c in out["covenants"]:
            if c.get("kind") not in COVENANT_KINDS:
                raise ValidationFailed(f"Covenant kind must be one of {', '.join(COVENANT_KINDS)}")
        return out

    def _manifest(self, uow: Any, mv: dict[str, Any], ps: dict[str, Any] | None,
                  tw: dict[str, Any] | None, spec: dict[str, Any]) -> dict[str, Any]:
        model = uow.repo("models").require(mv["model_id"])
        ir = mv["formula_ir"] or {}
        return {"model": {"name": model["name"], "version_no": mv["version_no"],
                          "ir_hash": mv["ir_hash"], "artifact_hash": mv["artifact_hash"],
                          "opaque": mv["opaque"]},
                "parameters": {"id": ps["id"], "values_hash": ps["values_hash"],
                               "verified_data": ps["verified_data"]} if ps else None,
                "input_contract": mv["input_contract"],
                "bindings": (tw or {}).get("spec", {}).get("bindings", {}),
                "outputs": ir.get("outputs", []),
                "composite": ir.get("composite"),
                "environments": spec["environments"], "covenants": spec["covenants"],
                "limits": spec["limits"],
                "escalation_contact": spec["contact"]}

    # -- workflow ------------------------------------------------------------------------
    def subject(self, uow: Any, ew: dict[str, Any], ns: dict[str, Any]) -> Subject:
        owner = uow.repo("users").get(ew["owner_id"])
        return Subject("execution_warrant", "execution_warrants", ew["id"], self.uri(ew, ns),
                       "execution_warrant", ew, ns, ew["owner_id"],
                       owner["username"] if owner else None,
                       uow.repo("grants").list(object_type="execution_warrant", object_id=ew["id"]),
                       {"warrant": ew})

    def transition(self, p: Principal, ew_id: str, name: str, *, rationale: str | None = None,
                   force: bool = False) -> dict[str, Any]:
        with self.p.uow(p.username) as uow:
            ew, ns = self._load(uow, ew_id)
            out = self.p.workflow.transition(uow, p, self.subject(uow, ew, ns), name,
                                             rationale=rationale, force=force)
            if out.moved:
                self.p.warrants._custody(uow, ew_id, name, p.username, warrant_type="exec")
            return out.__dict__

    def check_params(self, uow: Any, ctx: dict[str, Any]) -> tuple[bool, str]:
        ew = ctx["row"]
        if not ew["parameter_set_id"]:
            if _trainable(uow.repo("model_versions").require(ew["model_version_id"])):
                return False, "the model declares parameters, but no parameter set is named"
            return True, "non-trainable model: no parameter set required"
        ps = uow.repo("parameter_sets").require(ew["parameter_set_id"])
        ok = ps["state"] in catalog.APPROVED_STATES
        return ok, f"parameter set is {ps['state']}"

    def seal(self, p: Principal, ew_id: str) -> dict[str, Any]:
        with self.p.uow(p.username) as uow:
            ew, ns = self._load(uow, ew_id)
            self.p.access.require(uow, p, "seal", "execution_warrant", ew)
            if ew["state"] not in catalog.APPROVED_STATES:
                raise NotApproved("Only an approved execution warrant can be sealed")
            now = utcnow()
            row = uow.repo("execution_warrants").update(ew_id, {
                "sealed_at": now, "valid_from": now,
                "valid_to": now + dt.timedelta(days=int(ew["spec"]["valid_days"]))})
            self.p.warrants._custody(uow, ew_id, "sealed", p.username, warrant_type="exec")
            uow.audit("warrant.exec_sealed", object_type="execution_warrant",
                      object_ref=self.uri(ew, ns))
            return row

    # -- live instrument ---------------------------------------------------------------
    def check(self, ew: dict[str, Any], environment: str | None = None) -> None:
        """Fail closed, naming whom to contact (§9.4)."""
        contact = ew["spec"].get("contact") or "the model owner"
        status = self.status(ew)
        if status == "revoked":
            raise NotApproved(f"Warrant revoked: {ew['revoke_reason']}. Contact {contact}.",
                              status=status)
        if status == "suspended":
            raise WarrantSuspended(f"Warrant suspended: {ew['suspend_reason']}. Contact {contact}.",
                                   status=status)
        if status == "expired":
            raise WarrantExpired(f"Warrant expired on {ew['valid_to']:%Y-%m-%d}. Contact {contact}.",
                                 status=status)
        if status != "live":
            raise NotApproved(f"Warrant is '{status}', not sealed and live", status=status)
        if environment and environment not in ew["spec"]["environments"]:
            raise PermissionDenied(f"Warrant is not valid in '{environment}'",
                                   environments=ew["spec"]["environments"])

    @staticmethod
    def usage_today(uow: Any, ew_id: str) -> dict[str, int]:
        midnight = utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        reports = uow.repo("execution_reports").list(execution_warrant_id=ew_id,
                                                     created_at__ge=midnight)
        return {"calls": len(reports), "rows": sum(r["rows"] for r in reports)}

    def check_allowance(self, uow: Any, ew: dict[str, Any]) -> None:
        """Refuse a new run once today's rate or volume allowance is spent (§9.2)."""
        limits = ew["spec"].get("limits") or {}
        if not limits:
            return
        used = self.usage_today(uow, ew["id"])
        contact = ew["spec"].get("contact") or "the model owner"
        if "max_calls_per_day" in limits and used["calls"] >= limits["max_calls_per_day"]:
            raise QuotaExceeded(f"Today's {limits['max_calls_per_day']} runs under this warrant "
                                f"are used. Contact {contact} to raise the limit.",
                                limit="max_calls_per_day", used=used["calls"])
        if "max_rows_per_day" in limits and used["rows"] >= limits["max_rows_per_day"]:
            raise QuotaExceeded(f"Today's {limits['max_rows_per_day']} rows under this warrant "
                                f"are used. Contact {contact} to raise the limit.",
                                limit="max_rows_per_day", used=used["rows"])

    def token(self, p: Principal, ew_id: str, environment: str) -> dict[str, Any]:
        with self.p.uow() as uow:
            ew, ns = self._load(uow, ew_id)
            self.p.access.require(uow, p, "read", "execution_warrant", ew)
            self.check(ew, environment)
            self.check_allowance(uow, ew)
        claims = {"warrant": self.uri(ew, ns), "id": ew_id, "env": environment,
                  "model_ir_hash": ew["manifest"]["model"]["ir_hash"],
                  "params_hash": (ew["manifest"].get("parameters") or {}).get("values_hash"),
                  "sub": p.username,
                  "exp": (utcnow() + dt.timedelta(minutes=TOKEN_MINUTES)).isoformat()}
        payload = djson.canonical(claims).encode()
        sig = self.p.signer.signature_block(payload)
        return {"token": base64.urlsafe_b64encode(payload).decode() + "." + sig["signature"],
                "claims": claims, "public_key": sig["public_key"]}

    def bundle(self, p: Principal, ew_id: str, environment: str, *,
               offline: bool = False) -> dict[str, Any]:
        """Everything the SDK needs to run the warrant in one call.

        ``offline`` asks for a copy to run without MAYA: no live token, nothing
        reported back, so no covenant or limit can be checked on its use. It is still
        issued — the requirement is that the weaker mode be visible, not forbidden —
        but it is recorded on the warrant's custody trail and audited, the bundle is
        labelled ``unattested``, and so is the warrant from then on (``offline_use``)."""
        with self.p.uow() as uow:
            ew, ns = self._load(uow, ew_id)
            self.p.access.require(uow, p, "read", "execution_warrant", ew)
            mv = uow.repo("model_versions").require(ew["model_version_id"])
            ps = uow.repo("parameter_sets").require(ew["parameter_set_id"]) \
                if ew["parameter_set_id"] else None
            members = self.p.models._member_irs(uow, mv["formula_ir"]) \
                if "composite" in (mv["formula_ir"] or {}) else {}
            self.check(ew, environment)
            self.check_allowance(uow, ew)
        out = {"warrant": self.uri(ew, ns), "id": ew_id, "manifest": ew["manifest"],
               "formula_ir": mv["formula_ir"], "member_irs": members,
               "parameters": ps["values"] if ps else {}, "status": self.status(ew)}
        if not offline:
            return {**out, "attestation": "attested",
                    "token": self.token(p, ew_id, environment)["token"]}
        with self.p.uow(p.username) as uow:
            self.p.warrants._custody(uow, ew_id, "offline_issued", p.username,
                                     detail={"environment": environment},
                                     warrant_type="exec")
            uow.audit("warrant.offline_issued", object_type="execution_warrant",
                      object_ref=out["warrant"], detail={"environment": environment})
        return {**out, "attestation": "unattested", "token": None,
                "notice": "Runs from this copy are not reported to MAYA: no covenant or "
                          "limit is checked on them, and the warrant shows it was issued "
                          "for offline use."}

    def report(self, p: Principal, ew_id: str, *, environment: str, rows: int,
               input_stats: dict[str, Any], output_stats: dict[str, Any] | None = None
               ) -> dict[str, Any]:
        """An execution reported back; covenants evaluated; breach suspends (§29.5)."""
        with self.p.uow(p.username) as uow:
            ew, ns = self._load(uow, ew_id)
            self.p.access.require(uow, p, "read", "execution_warrant", ew)
            self.check(ew, environment)
            used = self.usage_today(uow, ew_id)
            breaches = evaluate_covenants(ew["spec"]["covenants"], rows, input_stats,
                                          output_stats or {}, rows_today=used["rows"] + rows)
            over = over_limits(ew["spec"].get("limits") or {}, rows, used)
            uow.repo("execution_reports").add({
                "execution_warrant_id": ew_id, "environment": environment, "rows": rows,
                "input_stats": input_stats, "output_stats": output_stats or {},
                "breaches": breaches})
            uow.repo("execution_warrants").update(ew_id, {"executions": ew["executions"] + 1})
            me = self.uri(ew, ns)
            uow.repo("lineage_edges").link(me, f"maya://execution/{ew_id}/{environment}",
                                           "executed_under")
            if over:
                uow.audit("warrant.limit_exceeded", object_type="execution_warrant",
                          object_ref=me, detail={"limits": over, "environment": environment})
            if breaches:
                reason = "; ".join(b["detail"] for b in breaches)
                uow.repo("execution_warrants").update(ew_id, {"suspended_at": utcnow(),
                                                              "suspend_reason": reason})
                self.p.warrants._custody(uow, ew_id, "suspended", "covenant-monitor",
                                         detail={"breaches": breaches}, warrant_type="exec")
                uow.audit("warrant.suspended", object_type="execution_warrant", object_ref=me,
                          detail={"breaches": breaches}, principal_type="system")
                for uid in {ew["owner_id"]}:
                    uow.repo("notifications").add({"user_id": uid, "kind": "covenant_breach",
                                                   "message": f"{me} SUSPENDED: {reason}",
                                                   "object_ref": me})
            return {"accepted": True, "breaches": breaches, "limits_exceeded": over,
                    "status": "suspended" if breaches else "live"}

    def reinstate(self, p: Principal, ew_id: str, reason: str) -> dict[str, Any]:
        """Only an explicit, audited decision lifts a suspension (§29.5)."""
        if not reason.strip():
            raise ValidationFailed("Reinstatement requires a written reason")
        with self.p.uow(p.username) as uow:
            ew, ns = self._load(uow, ew_id)
            if not (p.is_admin or self.p.access.allowed(uow, p, "grant", "execution_warrant", ew)):
                raise PermissionDenied("Only the model owner or an administrator reinstates")
            if not ew["suspended_at"]:
                raise NotApproved("The warrant is not suspended; there is nothing to reinstate")
            row = uow.repo("execution_warrants").update(ew_id, {"suspended_at": None,
                                                                "suspend_reason": None})
            self.p.warrants._custody(uow, ew_id, "reinstated", p.username,
                                     detail={"reason": reason}, warrant_type="exec")
            uow.audit("warrant.reinstated", object_type="execution_warrant",
                      object_ref=self.uri(ew, ns), detail={"reason": reason})
            return row

    def revoke(self, p: Principal, ew_id: str, reason: str) -> dict[str, Any]:
        if not reason.strip():
            raise ValidationFailed("Revocation requires a reason")
        with self.p.uow(p.username) as uow:
            ew, ns = self._load(uow, ew_id)
            if not (p.is_admin or self.p.access.allowed(uow, p, "revoke", "execution_warrant", ew)):
                raise PermissionDenied("Only the model owner or an administrator revokes")
            row = uow.repo("execution_warrants").update(ew_id, {"revoked_at": utcnow(),
                                                                "revoke_reason": reason})
            self.p.warrants._custody(uow, ew_id, "revoked", p.username,
                                     detail={"reason": reason}, warrant_type="exec")
            uow.audit("warrant.exec_revoked", object_type="execution_warrant",
                      object_ref=self.uri(ew, ns), detail={"reason": reason})
            return row

    def expire_sweep(self) -> int:
        """Notify owners 30 days before expiry (§9.4). Run by the scheduler."""
        n = 0
        soon = utcnow() + dt.timedelta(days=30)
        with self.p.uow("system") as uow:
            for ew in uow.repo("execution_warrants").list(valid_to__le=soon, valid_to__gt=utcnow(),
                                                          revoked_at__isnull=True):
                if uow.repo("notifications").find_one(user_id=ew["owner_id"], kind="expiry",
                                                      object_ref=ew["id"]):
                    continue                    # one notice per warrant, not one per sweep
                uow.repo("notifications").add({"user_id": ew["owner_id"], "kind": "expiry",
                                               "message": f"{ew['name']} expires "
                                                          f"{ew['valid_to']:%Y-%m-%d}",
                                               "object_ref": ew["id"]})
                n += 1
        return n


def evaluate_covenants(covenants: list[dict[str, Any]], rows: int, inputs: dict[str, Any],
                       outputs: dict[str, Any], *, rows_today: int) -> list[dict[str, Any]]:
    """Every breached covenant, with what was observed."""
    out = []
    for c in covenants:
        kind, attr = c["kind"], c.get("attr")
        stats = (outputs if kind == "output_range" else inputs).get(attr or "", {})
        if kind == "input_null_rate" and stats.get("null_rate", 0) > c.get("max", 1):
            out.append({**c, "observed": stats["null_rate"],
                        "detail": f"null rate of '{attr}' {stats['null_rate']:.3f} > {c['max']}"})
        elif kind in ("input_range", "output_range"):
            lo, hi = c.get("min"), c.get("max")
            if lo is not None and stats.get("min") is not None and stats["min"] < lo:
                out.append({**c, "observed": stats["min"],
                            "detail": f"'{attr}' min {stats['min']} below {lo}"})
            if hi is not None and stats.get("max") is not None and stats["max"] > hi:
                out.append({**c, "observed": stats["max"],
                            "detail": f"'{attr}' max {stats['max']} above {hi}"})
        elif kind == "max_rows_per_day" and rows_today > c.get("max", 0):
            out.append({**c, "observed": rows_today,
                        "detail": f"{rows_today} rows today exceed the limit of {c['max']}"})
        elif kind == "staleness_days" and stats.get("age_days", 0) > c.get("max", 0):
            out.append({**c, "observed": stats["age_days"],
                        "detail": f"'{attr}' is {stats['age_days']} days stale"})
    return out


def over_limits(limits: dict[str, int], rows: int, used: dict[str, int]) -> list[dict[str, Any]]:
    """Limits this reported run went past, counting it: recorded as evidence, never hidden."""
    seen = {"max_rows_per_call": rows, "max_rows_per_day": used["rows"] + rows,
            "max_calls_per_day": used["calls"] + 1}
    return [{"limit": k, "max": v, "observed": seen[k]}
            for k, v in limits.items() if seen[k] > v]


def _trainable(mv: dict[str, Any]) -> bool:
    """Whether a model version declares parameters — closed-form or black box alike: a
    declared parameter is a value someone must fit and someone must approve."""
    return bool(irmod.parameter_inputs(mv["formula_ir"] or {}))
