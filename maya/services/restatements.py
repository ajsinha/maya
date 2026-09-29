"""
Restatement alerts: when data is corrected underneath a live model (§29.1, §29.4).

A restatement never touches a pin. That is the point of two clocks, and it has a cost: a
model fitted on a pin keeps running on the story the pin tells, even after the source has
said that story was wrong. MAYA already records every restatement; this acts on it.

After a restatement is ingested, a job looks at every live execution warrant. It takes the
feature set pin its training warrant was drawn on and resolves the same definition again --
the same member feature versions, the same as-of date -- once with what was known when the
pin was sealed (the control) and once with what is known now. If the two hash the same,
nothing under that model moved and nothing is said. If they differ, MAYA measures the
difference without showing anyone a row:

- how many rows changed, were added or were dropped, in training and in the holdout;
- the live parameters scored blind on the holdout both ways (RMSE and MAE), a formula from
  its IR and a black box in the sandbox, exactly as blind scoring does -- and, being MAYA's
  own check with the approved parameters, not counted as a holdout attempt;
- how far the model's predictions moved over every row: the mean and largest absolute
  change and the share of rows that moved at all.

The difference is stored as an *impact* on the warrant, the warrant's owner, the model's
owner and every model manager are notified, and the owner acknowledges it with a note --
refitting, or saying why the change does not matter. Nothing is suspended: whether a
correction invalidates a model is a judgement, and the evidence for it is what this gives.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import builtins
import datetime as dt
from types import SimpleNamespace
from typing import Any

import numpy as np
import pandas as pd

from maya.core.clock import utcnow
from maya.core.errors import PermissionDenied, ValidationFailed
from maya.formula import ir as irmod
from maya.security.authz import Principal
from maya.services import refs

JOB = "restatement.assess"
SPLIT = "_split"
MOVED = 1e-9  # an absolute change in a prediction smaller than this is rounding


class RestatementService:
    def __init__(self, platform: Any) -> None:
        self.p = platform

    # -- triggering ---------------------------------------------------------------------
    def queue(self, uow: Any, *, trigger: str, knowledge_time: dt.datetime, actor: str) -> None:
        """Queue an assessment in the ingest's own transaction (so only if it commits)."""
        if not self.p.settings.bool("restatements.alerts", True):
            return
        self.p.jobs.submit(
            uow,
            JOB,
            {"trigger": trigger, "knowledge_time": knowledge_time.isoformat()},
            owner=actor,
        )

    def run_job(self, ctx: Any, params: dict[str, Any]) -> dict[str, Any]:
        with self.p.uow() as uow:
            live = [
                ew
                for ew in uow.repo("execution_warrants").list(revoked_at__isnull=True)
                if self.p.execution.status(ew) in ("live", "suspended")
                and ew.get("training_warrant_id")
            ]
        known = params.get("knowledge_time")
        found = []
        for i, ew in enumerate(live):
            ctx.progress(5 + int(90 * i / max(len(live), 1)), f"checking {ew['name']}")
            impact = self.assess(
                ew["id"],
                trigger=params.get("trigger"),
                knowledge_time=dt.datetime.fromisoformat(known) if known else None,
            )
            if impact:
                found.append(impact["id"])
        return {"checked": len(live), "impacts": found}

    def check(self, p: Principal, ew_id: str) -> dict[str, Any]:
        """Queue an assessment of one warrant now (its owner, or an administrator)."""
        with self.p.uow(p.username) as uow:
            ew, _ = self.p.execution._load(uow, ew_id)
            self._may_act(p, ew)
            return self.p.jobs.submit(
                uow,
                JOB + ".one",
                {"ew_id": ew_id, "trigger": f"checked by {p.username}"},
                owner=p.username,
            )

    def run_one(self, ctx: Any, params: dict[str, Any]) -> dict[str, Any]:
        ctx.progress(10, "resolving the training pin with what is known now")
        impact = self.assess(params["ew_id"], trigger=params.get("trigger"))
        return {"impact": impact["id"] if impact else None, "moved": bool(impact)}

    # -- the assessment -----------------------------------------------------------------
    def assess(
        self,
        ew_id: str,
        *,
        trigger: str | None = None,
        knowledge_time: dt.datetime | None = None,
    ) -> dict[str, Any] | None:
        """Compare a live warrant's training pin with the same data known now. Returns the
        impact recorded, or None when nothing under the pin moved (or it was already told)."""
        ctx = self._context(ew_id)
        if ctx is None:
            return None
        corrected = self._resolve(ctx)
        if corrected["hash"] == ctx["pin"]["content_hash"]:
            return None
        control = self._sealed(ctx)
        with self.p.uow() as uow:
            if uow.repo("restatement_impacts").find_one(
                execution_warrant_id=ew_id, corrected_hash=corrected["hash"]
            ):
                return None
        comparison = self._compare(ctx, control["frame"], corrected["frame"])
        return self._record(ctx, trigger, knowledge_time, control, corrected, comparison)

    def _context(self, ew_id: str) -> dict[str, Any] | None:
        with self.p.uow() as uow:
            ew, ns = self.p.execution._load(uow, ew_id)
            tw = uow.repo("training_warrants").get(ew.get("training_warrant_id") or "")
            if tw is None or not tw.get("feature_set_pin_id"):
                return None
            pin = uow.repo("feature_set_pins").get(tw["feature_set_pin_id"])
            if pin is None or pin["state"] != "sealed":
                return None
            version = uow.repo("feature_set_versions").require(pin["feature_set_version_id"])
            eff, inherited = self.p.featuresets.effective(uow, version["definition"])
            mv = uow.repo("model_versions").require(ew["model_version_id"])
            model = uow.repo("models").require(mv["model_id"])
            values = (
                uow.repo("parameter_sets").require(ew["parameter_set_id"])["values"]
                if ew.get("parameter_set_id")
                else {}
            )
            members = self._member_versions(uow, pin)
        return {
            "ew": ew,
            "ns": ns,
            "tw": tw,
            "pin": pin,
            "eff": eff,
            "inherited": inherited,
            "mv": mv,
            "model": model,
            "values": values,
            "members": members,
        }

    @staticmethod
    def _member_versions(uow: Any, pin: dict[str, Any]) -> dict[str, str]:
        """Each member as the feature *version* its member pin holds, so the comparison is
        about data and never about a definition approved since."""
        out = {}
        for ref, pin_id in ((pin.get("manifest") or {}).get("member_pins") or {}).items():
            member = uow.repo("feature_pins").get(pin_id)
            if member is None:
                continue  # a nested feature set is resolved as its definition names it
            feature = uow.repo("features").require(member["feature_id"])
            ns = uow.repo("namespaces").require(feature["namespace_id"])
            version = uow.repo("feature_versions").require(member["feature_version_id"])
            out[ref] = refs.version_ref(
                "feature", ns["name"], feature["name"], version["version_no"]
            )
        return out

    def _resolve(self, ctx: dict[str, Any]) -> dict[str, Any]:
        """The pin's definition over its member versions, with everything known now."""
        res = self.p.featuresets.resolve_definition(
            None,
            ctx["eff"],
            ctx["inherited"],
            end=ctx["pin"]["as_of_date"],
            member_override=ctx["members"],
        )
        table = self.p.feature_data.to_table(res)
        return {
            "hash": self.p.lake.describe_pin(table).content_hash,
            "frame": self._split(ctx, table.to_pandas(), res.meta),
        }

    def _sealed(self, ctx: dict[str, Any]) -> dict[str, Any]:
        """The pin as sealed: what the model was fitted and escrowed on."""
        pin = ctx["pin"]
        with self.p.uow() as uow:
            fs = uow.repo("feature_sets").require(pin["feature_set_id"])
            ns = uow.repo("namespaces").require(fs["namespace_id"])
        table = self.p.featuresets.pin_table(pin, fs, ns, ctx["eff"], ctx["inherited"])
        meta = (pin.get("manifest") or {}).get("meta") or {}
        return {"hash": pin["content_hash"], "frame": self._split(ctx, table.to_pandas(), meta)}

    def _split(self, ctx: dict[str, Any], df: pd.DataFrame, meta: dict[str, Any]) -> pd.DataFrame:
        return self.p.warrants._split_frame(SimpleNamespace(df=df, meta=meta), ctx["tw"]["spec"])

    def _predict(self, ctx: dict[str, Any], frame: pd.DataFrame) -> np.ndarray:
        mv, spec = ctx["mv"], ctx["tw"]["spec"]
        bindings = spec.get("bindings", {})
        if irmod.is_opaque(mv["formula_ir"] or {}):
            pred, _ = self.p.warrants._predict_blind(
                mv, frame, bindings, ctx["values"], spec.get("target")
            )
            return np.asarray(pred, dtype=float)
        return np.asarray(self.p.warrants.predict(mv, frame, bindings, ctx["values"]), dtype=float)

    def _compare(
        self, ctx: dict[str, Any], before: pd.DataFrame, after: pd.DataFrame
    ) -> dict[str, Any]:
        index = [c for c in ctx["pin"]["manifest"].get("meta", {}).get("index", []) or []]
        index = [c for c in index if c in before.columns and c in after.columns] or [
            c for c in after.columns if c != SPLIT
        ][:1]
        before = before.assign(_pred=self._predict(ctx, before))
        after = after.assign(_pred=self._predict(ctx, after))
        keys = [before[index].astype(str), after[index].astype(str)]
        b, a = (
            f.assign(_key=k.agg("|".join, axis=1)).set_index("_key")
            for f, k in zip((before, after), keys, strict=True)
        )
        both = b.index.intersection(a.index)
        inputs = [c for c in b.columns if c in a.columns and c not in (SPLIT, "_pred", *index)]
        changed = [k for k in both if any(not _same(b.at[k, c], a.at[k, c]) for c in inputs)]
        split = a[SPLIT]
        delta = np.abs(a.loc[both, "_pred"].to_numpy() - b.loc[both, "_pred"].to_numpy())
        delta = delta[~np.isnan(delta)]
        return {
            "rows": {
                "compared": int(len(both)),
                "changed": len(changed),
                "changed_in_holdout": int(sum(split.get(k) == "test" for k in changed)),
                "added": int(len(a.index.difference(b.index))),
                "dropped": int(len(b.index.difference(a.index))),
            },
            "metrics_sealed": self._metrics(ctx, before),
            "metrics_corrected": self._metrics(ctx, after),
            "shift": {
                "mean_abs": float(delta.mean()) if len(delta) else 0.0,
                "max_abs": float(delta.max()) if len(delta) else 0.0,
                "share_moved": float((delta > MOVED).mean()) if len(delta) else 0.0,
            },
        }

    @staticmethod
    def _metrics(ctx: dict[str, Any], frame: pd.DataFrame) -> dict[str, Any]:
        target = ctx["tw"]["spec"].get("target")
        test = frame[frame[SPLIT] == "test"]
        if not target or target not in test.columns or test.empty:
            return {}
        err = test["_pred"].to_numpy() - test[target].astype(float).to_numpy()
        return {
            "rmse": float(np.sqrt(np.nanmean(err**2))),
            "mae": float(np.nanmean(np.abs(err))),
            "rows": int(len(test)),
        }

    def _record(
        self,
        ctx: dict[str, Any],
        trigger: str | None,
        knowledge_time: dt.datetime | None,
        control: dict[str, Any],
        corrected: dict[str, Any],
        comparison: dict[str, Any],
    ) -> dict[str, Any]:
        ew, ns, pin = ctx["ew"], ctx["ns"], ctx["pin"]
        uri = self.p.execution.uri(ew, ns)
        with self.p.uow("system") as uow:
            row = uow.repo("restatement_impacts").add(
                {
                    "execution_warrant_id": ew["id"],
                    "training_warrant_id": ctx["tw"]["id"],
                    "feature_set_pin_id": pin["id"],
                    "trigger": (trigger or "")[:500] or None,
                    "knowledge_time": knowledge_time,
                    "sealed_hash": control["hash"],
                    "corrected_hash": corrected["hash"],
                    **comparison,
                }
            )
            message = _message(uri, pin, comparison)
            from maya.services.subscriptions import MANAGER_ROLE, SubscriptionService as Subs

            users = {ew["owner_id"], ctx["model"]["owner_id"]} | Subs._role_holders(
                uow, MANAGER_ROLE
            )
            for user_id in sorted(u for u in users if u):
                Subs._notify(uow, user_id, "restatement", uri, message)
            from maya.observability.metrics import METRICS

            METRICS.inc("maya_restatement_impacts_total")
            uow.audit(
                "restatement.impact",
                object_type="execution_warrant",
                object_ref=uri,
                principal_type="system",
                detail={
                    "impact": row["id"],
                    "trigger": trigger,
                    "rows": comparison["rows"],
                    "shift": comparison["shift"],
                },
            )
        return row

    # -- reading and acknowledging ---------------------------------------------------------
    def list(self, p: Principal, ew_id: str) -> builtins.list[dict[str, Any]]:
        with self.p.uow() as uow:
            ew, _ = self.p.execution._load(uow, ew_id)
            self.p.access.require(uow, p, "read", "execution_warrant", ew)
            return uow.repo("restatement_impacts").list(
                execution_warrant_id=ew_id, order_by=["-created_at"]
            )

    def acknowledge(self, p: Principal, impact_id: str, note: str) -> dict[str, Any]:
        """The owner says what they did about it: refitted, or why it does not matter."""
        if not (note or "").strip():
            raise ValidationFailed("Say what was done about it, or why it does not matter")
        with self.p.uow(p.username) as uow:
            impact = uow.repo("restatement_impacts").require(impact_id)
            ew, ns = self.p.execution._load(uow, impact["execution_warrant_id"])
            self._may_act(p, ew)
            if impact["state"] != "open":
                raise ValidationFailed("This impact was already acknowledged")
            row = uow.repo("restatement_impacts").update(
                impact_id,
                {
                    "state": "acknowledged",
                    "acknowledged_by": p.username,
                    "acknowledged_at": utcnow(),
                    "note": note.strip(),
                },
            )
            uow.audit(
                "restatement.acknowledged",
                object_type="execution_warrant",
                object_ref=self.p.execution.uri(ew, ns),
                detail={"impact": impact_id, "note": note.strip()[:500]},
            )
            return row

    @staticmethod
    def _may_act(p: Principal, ew: dict[str, Any]) -> None:
        if not (p.is_admin or p.user_id == ew["owner_id"] or "model_manager" in p.roles):
            raise PermissionDenied(
                "Only the warrant's owner, a model manager or an administrator may do this"
            )


def _same(x: Any, y: Any) -> bool:
    if x is None or y is None or (isinstance(x, float) and np.isnan(x)):
        return (x is None or (isinstance(x, float) and np.isnan(x))) and (
            y is None or (isinstance(y, float) and np.isnan(y))
        )
    try:
        return bool(np.isclose(float(x), float(y), rtol=1e-12, atol=0.0))
    except (TypeError, ValueError):
        return str(x) == str(y)


def _message(uri: str, pin: dict[str, Any], c: dict[str, Any]) -> str:
    rows, shift = c["rows"], c["shift"]
    text = (
        f"{uri}: data under its training pin ({pin['pin_name']} as of {pin['as_of_date']}) "
        f"was restated — {rows['changed']} row(s) changed, {rows['added']} added, "
        f"{rows['dropped']} dropped; predictions moved by {shift['mean_abs']:.4g} on average "
        f"(largest {shift['max_abs']:.4g})"
    )
    before, after = c["metrics_sealed"], c["metrics_corrected"]
    if before and after:
        text += f"; holdout RMSE {before['rmse']:.4g} → {after['rmse']:.4g}"
    return text
