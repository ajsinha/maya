"""
Workspaces and shadow replay (§28.3, §29.2).

A workspace is a copy-on-write branch of the catalog. Staging a change stores a
proposed definition for an existing feature or feature set and copies nothing
else. Inside the workspace every resolution — direct, through a derived
feature, through a feature set's members — uses the proposal in place of the
version it would replace (``catalog.overlay``), so downstream effects are real
resolutions rather than a list of names.

Shadow replay answers the question reviewers actually have: *how much does it
move?* Every training and execution warrant downstream of a change is replayed
on a sampled window, once on the current definitions and once on the proposed
ones, with the warrant's own model and parameters. The report gives per-model
median and 95th-percentile shift, the worst row, and how many rows cross the
materiality threshold that model declares — with the sample size, the share of
the population it covered, and the replay basis stated, because sampled
agreement is not proof.

Three numbers can each be the materiality threshold, and the report says which
was used: the model version's own declaration first, since only the model knows
whether its output is a price, a rate in basis points or a probability; then the
namespace's; then the configured default. Replaying costs compute, so it is
gated by a per-namespace budget in row comparisons per day, charged against what
the audit log says previous replays spent.

Submitting a workspace is the merge request: each change becomes a new draft
version and is submitted through the ordinary workflow, with the replay report
attached for the reviewer. Nothing production-facing changes until those
versions are approved; a base approved over in the meantime is a conflict.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import builtins
import datetime as dt
from typing import Any

import numpy as np
import pandas as pd

from maya.core.errors import ConflictError, NotApproved, PermissionDenied, ValidationFailed
from maya.core.clock import utcnow
from maya.security.authz import Principal
from maya.services import catalog, refs

KINDS = {
    "feature": ("features", "feature_versions", "feature_id"),
    "featureset": ("feature_sets", "feature_set_versions", "feature_set_id"),
}


class WorkspaceService:
    def __init__(self, platform: Any) -> None:
        self.p = platform
        s = platform.settings
        self.sample_rows = s.int("workspaces.shadow.sample_rows", 5000)
        self.materiality = float(s.get("workspaces.shadow.materiality", "0.0001") or 0.0001)
        self.budget_rows = s.int("workspaces.shadow.budget_rows", 2000000)

    # -- workspaces -------------------------------------------------------------------
    def create(self, p: Principal, name: str, description: str = "") -> dict[str, Any]:
        if not name.strip():
            raise ValidationFailed("A workspace needs a name")
        with self.p.uow(p.username) as uow:
            row = uow.repo("workspaces").add(
                {
                    "name": name.strip(),
                    "owner_id": p.user_id,
                    "description": description,
                    "state": "open",
                }
            )
            uow.audit(
                "workspace.created",
                object_type="workspace",
                object_ref=row["id"],
                detail={"name": name},
            )
            return row

    def list(self, p: Principal) -> list[dict[str, Any]]:
        with self.p.uow() as uow:
            rows = uow.repo("workspaces").list(order_by=["-created_at"])
            users = {u["id"]: u["username"] for u in uow.repo("users").list()}
            for r in rows:
                r["owner"] = users.get(r["owner_id"])
                r["changes"] = uow.repo("workspace_changes").count(workspace_id=r["id"])
        return [r for r in rows if r["owner_id"] == p.user_id or p.is_admin or r["state"] != "open"]

    def get(self, p: Principal, ws_id: str) -> dict[str, Any]:
        self._refresh_merge_state(ws_id)
        with self.p.uow() as uow:
            ws = uow.repo("workspaces").require(ws_id)
            changes = uow.repo("workspace_changes").list(
                workspace_id=ws_id, order_by=["created_at"]
            )
            owner = uow.repo("users").get(ws["owner_id"])
        for c in changes:
            c["diff"] = self._diff(c)
        return {
            **ws,
            "owner": owner["username"] if owner else None,
            "changes": changes,
            "mine": ws["owner_id"] == p.user_id,
        }

    def _owned_open(self, uow: Any, p: Principal, ws_id: str) -> dict[str, Any]:
        ws = uow.repo("workspaces").require(ws_id)
        if ws["owner_id"] != p.user_id and not p.is_admin:
            raise PermissionDenied("Only the workspace's owner changes it")
        if ws["state"] != "open":
            raise NotApproved(f"The workspace is {ws['state']}; open a new one")
        return ws

    # -- staging ------------------------------------------------------------------------
    def stage(
        self,
        p: Principal,
        ws_id: str,
        *,
        kind: str,
        ref: str,
        definition: dict[str, Any],
        note: str = "",
    ) -> dict[str, Any]:
        """Stage a proposed definition. Rehearsal needs read; submitting needs update."""
        if kind not in KINDS:
            raise ValidationFailed("Workspaces stage features and feature sets")
        table, vtable, fk = KINDS[kind]
        errors = self._validate(kind, definition)
        if errors:
            raise ValidationFailed(
                "The proposed definition is not valid: " + "; ".join(errors), errors=errors
            )
        with self.p.uow(p.username) as uow:
            self._owned_open(uow, p, ws_id)
            obj, ns = catalog.find_object(uow, table, kind, refs.parse(ref, kind))
            self.p.access.require(uow, p, "read", kind, obj)
            base = catalog.version_of(uow, vtable, fk, obj, None)
            existing = uow.repo("workspace_changes").find_one(
                workspace_id=ws_id, object_kind=kind, object_id=obj["id"]
            )
            values = {
                "definition": definition,
                "note": note,
                "base_version_id": base["id"],
                "base_version_no": base["version_no"],
            }
            if existing:
                row = uow.repo("workspace_changes").update(existing["id"], values)
            else:
                row = uow.repo("workspace_changes").add(
                    {
                        "workspace_id": ws_id,
                        "object_kind": kind,
                        "object_id": obj["id"],
                        "object_ref": refs.object_ref(kind, ns["name"], obj["name"]),
                        **values,
                    }
                )
            uow.repo("workspaces").update(ws_id, {"replay": {}})  # a stale report is no report
            uow.audit(
                "workspace.staged",
                object_type="workspace",
                object_ref=ws_id,
                detail={"object": row["object_ref"], "base": base["version_no"]},
            )
            return row

    def _validate(self, kind: str, definition: dict[str, Any]) -> builtins.list[str]:
        if kind == "featureset":
            return self.p.featuresets.validate(definition)
        return catalog.blocking_errors(catalog.validate_feature_definition(definition))

    def unstage(self, p: Principal, ws_id: str, change_id: str) -> None:
        with self.p.uow(p.username) as uow:
            self._owned_open(uow, p, ws_id)
            uow.repo("workspace_changes").delete(change_id)
            uow.repo("workspaces").update(ws_id, {"replay": {}})

    def _overlay(self, ws_id: str) -> dict[tuple[str, str], dict[str, Any]]:
        with self.p.uow() as uow:
            return {
                (c["object_kind"], c["object_id"]): c
                for c in uow.repo("workspace_changes").list(workspace_id=ws_id)
            }

    def _diff(self, change: dict[str, Any]) -> builtins.list[dict[str, Any]]:
        from maya.services.features import diff_definitions

        with self.p.uow() as uow:
            base = uow.repo(KINDS[change["object_kind"]][1]).get(change["base_version_id"])
        return diff_definitions((base or {}).get("definition") or {}, change["definition"])

    # -- inside the workspace -------------------------------------------------------------
    def preview(self, p: Principal, ws_id: str, ref: str, limit: int = 200) -> dict[str, Any]:
        """Resolve any feature or feature set as it would be if the workspace merged."""
        r = refs.parse(ref, "feature")
        with catalog.overlay(self._overlay(ws_id)):
            if r.kind == "featureset":
                return self.p.featuresets.preview(p, ref) | {"workspace": ws_id}
            return self.p.features.preview(p, ref, limit=limit) | {"workspace": ws_id}

    def impact(self, p: Principal, ws_id: str) -> dict[str, Any]:
        """Everything downstream of a staged change, with its owner (§19)."""
        with self.p.uow() as uow:
            uow.repo("workspaces").require(ws_id)
            changes = uow.repo("workspace_changes").list(workspace_id=ws_id)
        nodes: dict[str, set[str]] = {}
        for c in changes:
            base_ref = f"{c['object_ref']}@v{c['base_version_no']}"
            for root in (base_ref, c["object_ref"]):
                graph = self.p.ops.lineage(root, direction="downstream", depth=8)
                for n in graph["nodes"]:
                    if n["id"] not in (base_ref, c["object_ref"]):
                        nodes.setdefault(n["id"], set()).add(c["object_ref"])
        return {
            "downstream": [
                {"ref": ref, "via": sorted(via), "kind": _kind(ref)}
                for ref, via in sorted(nodes.items())
            ],
            "warrants": sorted(ref for ref in nodes if ref.startswith("maya://warrant/")),
        }

    # -- shadow replay (§29.2) -------------------------------------------------------------
    def request_replay(self, p: Principal, ws_id: str) -> dict[str, Any]:
        with self.p.uow(p.username) as uow:
            uow.repo("workspaces").require(ws_id)
            return self.p.jobs.submit(
                uow, "workspace.shadow_replay", {"workspace_id": ws_id}, owner=p.username
            )

    def run_replay_job(self, ctx: Any, params: dict[str, Any]) -> dict[str, Any]:
        ws_id = params["workspace_id"]
        with self.p.uow() as uow:
            user = uow.repo("users").find_one(username=ctx.actor)
            principal = self.p.auth.build_principal(uow, user["id"])
        impacted = self.impact(principal, ws_id)["warrants"]
        overlay = self._overlay(ws_id)
        opening = self._opening_spend()
        spend = dict(opening)
        results = []
        for i, uri in enumerate(impacted):
            ctx.progress(10 + int(80 * i / max(len(impacted), 1)), f"replaying {uri}")
            results.append(self._replay_one(uri, overlay, spend))
        charged = {k: v - opening.get(k, 0) for k, v in spend.items() if v > opening.get(k, 0)}
        moved = [r for r in results if r.get("rows_over_materiality")]
        report = {
            "generated_at": utcnow().isoformat(),
            "sample_rows": self.sample_rows,
            "materiality": self.materiality,
            "warrants": results,
            "coverage": _coverage(results),
            "budget": {"rows_per_day": self.budget_rows, "spent": self._named(charged)},
            "summary": _summary(results, moved),
            "basis": "Each warrant's feature set version is resolved live twice — "
            "current definitions, then the workspace's — and scored with the "
            "warrant's own model and parameters. Sealed pins never change, so "
            "the replay shows what the warrant would see if drawn today. The "
            "sample is the most recent rows of each warrant's index, which is a "
            "recency bias and not a random draw, and the share of the matched "
            "rows it covers is stated per warrant. Sampled agreement is not proof.",
        }
        with self.p.uow(ctx.actor) as uow:
            uow.repo("workspaces").update(ws_id, {"replay": report})
            uow.audit(
                "workspace.replayed",
                object_type="workspace",
                object_ref=ws_id,
                detail={"warrants": len(results), "moved": len(moved), "spent": charged},
            )
        return {"warrants": len(results), "moved": len(moved)}

    def _replay_one(
        self, uri: str, overlay: dict[tuple[str, str], Any], spend: dict[str, int]
    ) -> dict[str, Any]:
        """One warrant's before-and-after, and the row comparisons it charged to ``spend``."""
        with self.p.uow() as uow:
            w, why = self._target(uow, uri)
            if w is None:
                return {"warrant": uri, "replayed": False, "reason": why}
            mv = uow.repo("model_versions").require(w["model_version_id"])
            params = w["values"] if "values" in w else self._params(uow, w)
            ns = uow.repo("namespaces").get(w.get("namespace_id") or "")
        if params is None:
            return {
                "warrant": uri,
                "replayed": False,
                "reason": "no parameter set to score with yet",
            }
        ns_id = (ns or {}).get("id") or ""
        refused = self._over_budget(uri, ns, spend.get(ns_id, 0))
        if refused is not None:
            return refused
        fs_ref = self._version_ref(w["featureset_ref"])
        bindings = w["spec"].get("bindings", {})
        try:
            base = self.p.featuresets.resolve_ref(None, fs_ref)
            with catalog.overlay(overlay):
                proposed = self.p.featuresets.resolve_ref(None, fs_ref)
            index = base.meta["index"]
            joined = base.df.merge(
                proposed.df, on=index, how="outer", suffixes=("", "__new"), indicator=True
            )
            matched = joined[joined["_merge"] == "both"]
            both = matched.sort_values(index).tail(self.sample_rows)
            old = self.p.warrants.predict(mv, both, bindings, params)
            new_frame = both[[c for c in both.columns if not c.endswith("__new")]].copy()
            for c in both.columns:
                if c.endswith("__new"):
                    new_frame[c[:-5]] = both[c].to_numpy()
            new = self.p.warrants.predict(mv, new_frame, bindings, params)
        except Exception as exc:  # noqa: BLE001 - one warrant's failure is reported, not fatal
            return {"warrant": uri, "replayed": False, "reason": str(getattr(exc, "message", exc))}
        threshold, source = self._materiality(mv, ns)
        stats = self._stats(np.asarray(new) - np.asarray(old), both, index, threshold, source)
        spend[ns_id] = spend.get(ns_id, 0) + int(stats["rows_compared"])
        return {
            "warrant": uri,
            "replayed": True,
            "featureset": fs_ref,
            "rows_added": int((joined["_merge"] == "right_only").sum()),
            "rows_removed": int((joined["_merge"] == "left_only").sum()),
            "rows_available": int(len(matched)),
            "coverage": (len(both) / len(matched)) if len(matched) else 1.0,
            **stats,
        }

    def _stats(
        self,
        delta: np.ndarray,
        rows: pd.DataFrame,
        index: builtins.list[str],
        materiality: float | None = None,
        materiality_from: str = "default",
    ) -> dict[str, Any]:
        budget = self.materiality if materiality is None else materiality
        where = {"materiality": budget, "materiality_from": materiality_from}
        finite = np.abs(delta[np.isfinite(delta)])
        if not len(finite):
            return {"rows_compared": int(len(delta)), "median_abs_shift": None, **where}
        worst = int(np.nanargmax(np.where(np.isfinite(delta), np.abs(delta), -1)))
        over = int((finite > budget).sum())
        return {
            "rows_compared": int(len(delta)),
            "median_abs_shift": float(np.median(finite)),
            "p95_abs_shift": float(np.percentile(finite, 95)),
            "max_abs_shift": float(finite.max()),
            "worst_row": {c: str(rows.iloc[worst][c]) for c in index},
            "rows_over_materiality": over,
            "share_over_materiality": over / len(delta),
            **where,
        }

    def _materiality(self, mv: dict[str, Any], ns: dict[str, Any] | None) -> tuple[float, str]:
        """The threshold a shift is measured against, and where it came from (§29.2).

        The model version's declaration wins, because only the model knows its output's
        units: a rate in basis points, a price and a probability are material at three
        different numbers. Failing that, the namespace's figure is the desk's default, and
        the configured value is the last resort. A report that used the wrong one of the
        three reads as "nothing moved", which is why the report says which it used.
        """
        if mv.get("shadow_materiality"):
            return float(mv["shadow_materiality"]), "model"
        if ns and ns.get("shadow_materiality"):
            return float(ns["shadow_materiality"]), "namespace"
        return self.materiality, "default"

    # -- the cost gate (§29.2) --------------------------------------------------------------
    def _over_budget(
        self, uri: str, ns: dict[str, Any] | None, spent: int
    ) -> dict[str, Any] | None:
        """Nothing, or the entry that says this warrant was not replayed because its
        namespace has spent its day's compute. The check is before the work and the charge
        is after it, so the first warrant of a day always runs however small the budget —
        a ceiling that could refuse everything would be a way to make a replay silently
        say "nothing moved"."""
        ceiling = self._ceiling(ns)
        if not ceiling or spent < ceiling:
            return None
        return {
            "warrant": uri,
            "replayed": False,
            "budget_rows": ceiling,
            "spent_rows": spent,
            "reason": (
                f"{(ns or {}).get('name') or 'this namespace'} has spent its shadow-replay "
                f"budget for the day: {spent} of {ceiling} row comparisons. It frees as the "
                "day rolls, or raise the namespace's shadow_budget_rows."
            ),
        }

    def _ceiling(self, ns: dict[str, Any] | None) -> int:
        declared = (ns or {}).get("shadow_budget_rows")
        return int(self.budget_rows if declared is None else declared)

    def _opening_spend(self) -> dict[str, int]:
        """What each namespace's replays have already cost in the last day.

        Read from the audit log, because that is where MAYA records the spend and it is the
        one ledger nothing can quietly adjust: a replay that was not audited was not
        charged, which is the right way round.
        """
        since = utcnow() - dt.timedelta(days=1)
        spend: dict[str, int] = {}
        with self.p.uow() as uow:
            rows = uow.repo("audit_events").list(action="workspace.replayed", at__ge=since)
        for row in rows:
            for ns_id, count in ((row["detail"] or {}).get("spent") or {}).items():
                spend[ns_id] = spend.get(ns_id, 0) + int(count)
        return spend

    def _named(self, charged: dict[str, int]) -> dict[str, int]:
        """The spend by namespace name, since an id on a report tells a reader nothing."""
        with self.p.uow() as uow:
            names = {n["id"]: n["name"] for n in uow.repo("namespaces").list()}
        return {names.get(ns_id, ns_id): rows for ns_id, rows in sorted(charged.items())}

    def _target(self, uow: Any, uri: str) -> tuple[dict[str, Any] | None, str]:
        """What to replay for a warrant URI: a training warrant as it is; an execution
        warrant as the training warrant it was issued from — its feature set and bindings —
        scored with the execution warrant's own model version and sealed parameters."""
        kind = "exec" if uri.startswith("maya://warrant/exec/") else "train"
        w = self._warrant(uow, uri, kind)
        if w is None:
            return None, "warrant not found"
        if kind == "train":
            return w, ""
        if not w.get("training_warrant_id"):
            return None, (
                "execution warrant has no training warrant: its inputs come from "
                "callers, so there is no feature set to replay"
            )
        tw = uow.repo("training_warrants").require(w["training_warrant_id"])
        target = {**tw, "model_version_id": w["model_version_id"]}
        if w.get("parameter_set_id"):
            target["values"] = uow.repo("parameter_sets").require(w["parameter_set_id"])["values"]
        return target, ""

    def _warrant(self, uow: Any, uri: str, kind: str = "train") -> dict[str, Any] | None:
        body = uri.split(f"maya://warrant/{kind}/", 1)[-1]
        path, _, version = body.partition("@v")
        ns_name, _, name = path.partition("/")
        ns = uow.repo("namespaces").find_one(name=ns_name)
        if ns is None or not version.isdigit():
            return None
        table = "execution_warrants" if kind == "exec" else "training_warrants"
        return uow.repo(table).find_one(namespace_id=ns["id"], name=name, version_no=int(version))

    @staticmethod
    def _params(uow: Any, w: dict[str, Any]) -> dict[str, Any] | None:
        sets = uow.repo("parameter_sets").list(
            training_warrant_id=w["id"], order_by=["-created_at"]
        )
        approved = [s for s in sets if s["state"] in catalog.APPROVED_STATES]
        chosen = (approved or sets or [None])[0]
        return chosen["values"] if chosen else None

    def _version_ref(self, fs_ref: str) -> str:
        """A pin's live counterpart: the feature set version behind it."""
        r = refs.parse(fs_ref, "featureset")
        if not r.is_pin:
            return fs_ref
        fs, ns, v, _, _, _ = self.p.featuresets.load(fs_ref)
        return refs.version_ref("featureset", ns["name"], fs["name"], v["version_no"])

    # -- merge ------------------------------------------------------------------------------
    def submit(self, p: Principal, ws_id: str) -> dict[str, Any]:
        """The merge request: each change becomes a submitted draft; reviewers approve."""
        with self.p.uow() as uow:
            ws = self._owned_open(uow, p, ws_id)
            changes = uow.repo("workspace_changes").list(workspace_id=ws_id)
        if not changes:
            raise ValidationFailed("The workspace has no staged change")
        self._check_bases(changes)
        submitted = []
        for c in changes:
            svc = self.p.features if c["object_kind"] == "feature" else self.p.featuresets
            draft = svc.new_draft(p, c["object_ref"])
            if draft["version_no"] <= c["base_version_no"]:
                raise ConflictError("Unexpected draft numbering; reload the workspace")
            svc.update_draft(p, c["object_ref"], c["definition"])
            out = svc.transition(
                p,
                c["object_ref"],
                draft["version_no"],
                "submit",
                rationale=f"Rehearsed in workspace '{ws['name']}'",
            )
            submitted.append(
                {
                    "kind": c["object_kind"],
                    "ref": c["object_ref"],
                    "version_no": draft["version_no"],
                    "version_id": draft["id"],
                    "state": out["state"],
                }
            )
            self.p.workflow_svc.comment(
                p,
                f"{c['object_kind']}_version"
                if c["object_kind"] == "feature"
                else "featureset_version",
                draft["id"],
                f"Rehearsed in workspace '{ws['name']}' ({ws_id}). Shadow replay: "
                f"{(ws['replay'] or {}).get('summary', 'not run')}",
            )
        with self.p.uow(p.username) as uow:
            uow.repo("workspaces").update(
                ws_id,
                {"state": "in_review", "submitted_at": utcnow(), "submitted_versions": submitted},
            )
            uow.audit(
                "workspace.submitted",
                object_type="workspace",
                object_ref=ws_id,
                detail={"versions": submitted},
            )
        return {"submitted": submitted}

    def _check_bases(self, changes: builtins.list[dict[str, Any]]) -> None:
        with self.p.uow() as uow:
            for c in changes:
                table, vtable, fk = KINDS[c["object_kind"]]
                obj = uow.repo(table).require(c["object_id"])
                latest_approved = catalog.version_of(uow, vtable, fk, obj, None)
                if latest_approved["id"] != c["base_version_id"]:
                    raise ConflictError(
                        f"{c['object_ref']} moved on: v{latest_approved['version_no']} was "
                        f"approved after this workspace staged against "
                        f"v{c['base_version_no']}. Re-stage the change (rebase) and replay."
                    )
                editable = uow.repo(vtable).list(
                    **{fk: obj["id"], "state__in": ("draft", "changes_requested")}
                )
                if editable:
                    raise ConflictError(
                        f"{c['object_ref']} already has an open draft "
                        f"(v{editable[0]['version_no']}); finish or withdraw it"
                    )

    def abandon(self, p: Principal, ws_id: str) -> dict[str, Any]:
        with self.p.uow(p.username) as uow:
            self._owned_open(uow, p, ws_id)
            row = uow.repo("workspaces").update(ws_id, {"state": "abandoned"})
            uow.audit("workspace.abandoned", object_type="workspace", object_ref=ws_id)
            return row

    def _refresh_merge_state(self, ws_id: str) -> None:
        """A submitted workspace is merged once every version it submitted is approved."""
        with self.p.uow("system") as uow:
            ws = uow.repo("workspaces").require(ws_id)
            if ws["state"] != "in_review":
                return
            states = []
            for v in ws["submitted_versions"]:
                table = KINDS[v["kind"]][1]
                states.append((uow.repo(table).get(v["version_id"]) or {}).get("state"))
            if states and all(s in catalog.APPROVED_STATES for s in states):
                uow.repo("workspaces").update(ws_id, {"state": "merged", "merged_at": utcnow()})
                uow.audit(
                    "workspace.merged",
                    object_type="workspace",
                    object_ref=ws_id,
                    principal_type="system",
                )


def _kind(ref: str) -> str:
    return ref[7:].split("/")[0] if ref.startswith("maya://") else "other"


def _coverage(results: list[dict[str, Any]]) -> dict[str, Any]:
    """How much of the population the sample actually covered (§29.2's honest sampling).

    Stated as rows and as a share, because "5,000 rows" means one thing on a panel of six
    thousand and quite another on a panel of six million, and a reader deciding whether to
    trust the numbers needs the second figure.
    """
    compared = sum(int(r.get("rows_compared") or 0) for r in results)
    available = sum(int(r.get("rows_available") or 0) for r in results)
    return {
        "rows_compared": compared,
        "rows_available": available,
        "share": (compared / available) if available else None,
        "sampling": "the most recent rows of each warrant's index",
    }


def _summary(results: list[dict[str, Any]], moved: list[dict[str, Any]]) -> str:
    replayed = [r for r in results if r.get("replayed")]
    if not results:
        return "No training warrant depends on the staged changes."
    parts = [f"moves {len(moved)} of {len(replayed)} replayed dependent model(s)"]
    for r in moved:
        parts.append(
            f"{r['warrant']}: median |Δ| {r['median_abs_shift']:.4g}, p95 "
            f"{r['p95_abs_shift']:.4g}, {r['share_over_materiality']:.1%} of rows over "
            f"materiality ({r['materiality']:.4g}, {r['materiality_from']})"
        )
    cover = _coverage(results)
    if cover["share"] is not None and cover["share"] < 1:
        parts.append(
            f"on {cover['rows_compared']} of {cover['rows_available']} matched rows "
            f"({cover['share']:.1%})"
        )
    skipped = len(results) - len(replayed)
    if skipped:
        parts.append(f"{skipped} could not be replayed (see each entry)")
    return "; ".join(parts)
