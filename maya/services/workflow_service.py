"""
Workflow as seen by people (§10.3–§10.6): the review queue, comments,
instance history, the live population per state, campaigns, the break-glass
report, and the policy editor — where a policy is itself governed: drafted,
validated as it is edited, previewed against the live population, activated
by a second administrator, and retained so the policy behind any past
decision is recoverable.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from maya.core.errors import MayaError, NotApproved, PermissionDenied, ValidationFailed
from maya.core.clock import utcnow
from maya.security.authz import Principal, can
from maya.workflow import policy as pol


# policy object type -> (table, how to transition an object of it)
def _namespace_of(ref: str) -> str | None:
    """The namespace in a maya:// reference (warrants carry an extra path segment)."""
    body = ref.split("maya://", 1)[-1].split("@")[0].split("#")[0].split("/")
    if body[:1] == ["warrant"]:
        body = body[1:]
    return body[1] if len(body) >= 3 else None


def _admin_ids(uow: Any) -> set[str]:
    role = uow.repo("roles").find_one(name="admin")
    return {r["user_id"] for r in uow.repo("user_roles").list(role_id=role["id"])}


TABLES = {
    "feature_version": "feature_versions",
    "featureset_version": "feature_set_versions",
    "model_version": "model_versions",
    "parameter_set": "parameter_sets",
    "training_warrant": "training_warrants",
    "execution_warrant": "execution_warrants",
}


# object type -> (its table, key of the governing object, that object's table, access kind)
GOVERNING = {
    "feature_version": ("feature_versions", "feature_id", "features", "feature"),
    "featureset_version": ("feature_set_versions", "feature_set_id", "feature_sets", "featureset"),
    "model_version": ("model_versions", "model_id", "models", "model"),
    "parameter_set": (
        "parameter_sets",
        "training_warrant_id",
        "training_warrants",
        "training_warrant",
    ),
    "training_warrant": ("training_warrants", None, None, "training_warrant"),
    "execution_warrant": ("execution_warrants", None, None, "execution_warrant"),
}


class WorkflowService:
    def __init__(self, platform: Any) -> None:
        self.p = platform

    # -- policies ------------------------------------------------------------------
    def policies(self) -> list[dict[str, Any]]:
        with self.p.uow() as uow:
            return uow.repo("workflow_policies").list(order_by=["object_type", "-version_no"])

    def policy(self, policy_id: str) -> dict[str, Any]:
        with self.p.uow() as uow:
            row = uow.repo("workflow_policies").require(policy_id)
        row["yaml"] = pol.to_yaml(row["policy"])
        row["errors"] = self.validate(row["policy"])
        row["population"] = self.population(row["object_type"])
        return row

    def validate(self, policy: dict[str, Any]) -> list[str]:
        with self.p.uow() as uow:
            roles = [r["name"] for r in uow.repo("roles").list()]
        return pol.validate(policy, checks=self.p.workflow.checks.keys(), roles=roles)

    def draft_policy(
        self,
        p: Principal,
        object_type: str,
        policy: dict[str, Any],
        *,
        scope: str = "*",
        note: str = "",
    ) -> dict[str, Any]:
        """Save a policy draft — refused at edit time if it is invalid (§10.6)."""
        self._admin(p)
        if object_type not in TABLES:
            raise ValidationFailed(f"Unknown object type '{object_type}'")
        errors = self.validate(policy)
        if errors:
            raise ValidationFailed(
                "The policy cannot be saved: " + "; ".join(errors), errors=errors
            )
        impact = self.preview(object_type, policy)
        with self.p.uow(p.username) as uow:
            last = uow.repo("workflow_policies").list(
                object_type=object_type, scope=scope, order_by=["-version_no"], limit=1
            )
            row = uow.repo("workflow_policies").add(
                {
                    "object_type": object_type,
                    "scope": scope,
                    "version_no": last[0]["version_no"] + 1 if last else 1,
                    "state": "draft",
                    "policy": policy,
                    "note": note,
                }
            )
            uow.audit(
                "policy.drafted",
                object_type="workflow_policy",
                object_ref=f"{object_type}@{scope}#v{row['version_no']}",
                detail={"impact": impact},
            )
            return {**row, "impact": impact}

    def import_yaml(
        self,
        p: Principal,
        object_type: str,
        text: str,
        *,
        scope: str = "*",
        note: str = "imported from YAML",
    ) -> dict[str, Any]:
        return self.draft_policy(p, object_type, pol.from_yaml(text), scope=scope, note=note)

    def activate(self, p: Principal, policy_id: str) -> dict[str, Any]:
        """Activation is approval by a second administrator; the old version is retained."""
        self._admin(p)
        with self.p.uow(p.username) as uow:
            row = uow.repo("workflow_policies").require(policy_id)
            if row["state"] != "draft":
                raise NotApproved(f"Policy v{row['version_no']} is {row['state']}")
            if row["created_by"] == p.username and not self.p.workflow.allow_self_approval:
                raise PermissionDenied(
                    "A policy you drafted must be activated by another "
                    "administrator: the rules of governance are governed too"
                )
            for old in uow.repo("workflow_policies").list(
                object_type=row["object_type"], scope=row["scope"], state="active"
            ):
                uow.repo("workflow_policies").update(old["id"], {"state": "superseded"})
            out = uow.repo("workflow_policies").update(
                policy_id, {"state": "active", "approved_by": p.username, "activated_at": utcnow()}
            )
            uow.audit(
                "policy.activated",
                object_type="workflow_policy",
                object_ref=f"{row['object_type']}@{row['scope']}#v{row['version_no']}",
            )
            return out

    def preview(self, object_type: str, policy: dict[str, Any]) -> dict[str, Any]:
        """What this policy would do to the live population, before it is saved."""
        population = self.population(object_type)
        states = set(policy.get("states") or [])
        stranded = {s: n for s, n in population.items() if s not in states and n}
        exits = {s: pol.transitions_from(policy, s) for s in states}
        blocked = {
            s: n
            for s, n in population.items()
            if s in states and n and not exits.get(s) and s not in ("retired", "withdrawn")
        }
        messages = []
        if stranded:
            messages.append(
                "would strand " + ", ".join(f"{n} object(s) in '{s}'" for s, n in stranded.items())
            )
        if blocked:
            messages.append(
                "would block "
                + ", ".join(f"{n} object(s) in '{s}' (no way out)" for s, n in blocked.items())
            )
        return {
            "population": population,
            "stranded": stranded,
            "blocked": blocked,
            "messages": messages or ["no object currently in flight is affected"],
        }

    def population(self, object_type: str) -> dict[str, int]:
        if object_type not in TABLES:
            raise ValidationFailed(f"Unknown object type '{object_type}'", allowed=sorted(TABLES))
        with self.p.uow() as uow:
            counts: dict[str, int] = {}
            for row in uow.repo(TABLES[object_type]).list():
                counts[row["state"]] = counts.get(row["state"], 0) + 1
            return counts

    def export_yaml(self, policy_id: str) -> str:
        with self.p.uow() as uow:
            return pol.to_yaml(uow.repo("workflow_policies").require(policy_id)["policy"])

    @staticmethod
    def _admin(p: Principal) -> None:
        if not p.has_capability("workflow_policy", "U"):
            raise PermissionDenied("Workflow policy is administered by 'admin'")

    # -- the review screen (§10.3, §10.6) ------------------------------------------------
    def review(self, p: Principal, object_type: str, object_id: str) -> dict[str, Any]:
        """Everything a reviewer needs on one screen, and nothing they may not read.

        The semantic diff against the last approved version; the impact list — every
        dependent object and who owns it; the policy that actually governs *this* item,
        found by its own namespace rather than by object type alone; the separation of
        duties in force and whether it stops this reviewer; and which approvals are
        still outstanding and from whom.
        """
        with self.p.uow() as uow:
            self.require_read(uow, p, object_type, object_id)
            table, parent_key, parent_table, kind = GOVERNING[object_type]
            row = uow.repo(table).require(object_id)
            owner = uow.repo(parent_table).require(row[parent_key]) if parent_key else row
            ns = uow.repo("namespaces").require(self._namespace_id(uow, owner, row))
            record = self._policy_for(uow, object_type, ns["name"])
            ref = self._ref_of(uow, object_type, object_id, owner, ns)
            transitions = self._transition_views(uow, p, record, row, kind, owner, ns)
            outstanding = self._outstanding(uow, record, row, ns, object_type, object_id)
            return {
                "object_type": object_type,
                "object_id": object_id,
                "kind": kind,
                "ref": ref,
                "state": row["state"],
                "namespace": ns["name"],
                "owner": self._username(uow, owner.get("owner_id")),
                "policy": record,
                "policy_scope": (record or {}).get("scope"),
                "sod": self._sod_view(p, row, ns),
                "transitions": transitions,
                "outstanding": outstanding,
                "approvals": uow.repo("approvals").list(
                    object_type=object_type, object_id=object_id, order_by=["created_at"]
                ),
                "diff": self._review_diff(uow, object_type, row, owner),
                "impact": self.p.catalog.dependents_in(uow, p, self._impact_roots(ref)),
                "shadow": self._shadow(uow, object_type, object_id),
            }

    @staticmethod
    def _shadow(uow: Any, object_type: str, object_id: str) -> dict[str, Any] | None:
        """The numeric impact, where there is one (§29.2): *how much does it move*, not just
        what it touches. A version submitted from a workspace carries the shadow replay run
        there, so the approver reads "moves 3 of 11 dependent models" beside the list of
        names.

        Found by looking through the workspaces that have submitted something, rather than by
        hanging a workspace id on every version row: the link belongs to the workspace, there
        are few of them, and the great majority of versions never came from one and would
        carry an empty column for ever.
        """
        if object_type not in ("feature_version", "featureset_version"):
            return None
        for ws in uow.repo("workspaces").list(state__in=("in_review", "merged")):
            if not any((v or {}).get("version_id") == object_id for v in ws["submitted_versions"]):
                continue
            report = ws["replay"] or {}
            return {
                "workspace": ws["id"],
                "workspace_name": ws["name"],
                "summary": report.get("summary")
                or "No shadow replay was run in the workspace before this was submitted.",
                "generated_at": report.get("generated_at"),
                "coverage": report.get("coverage") or {},
                "warrants": report.get("warrants") or [],
            }
        return None

    @staticmethod
    def _namespace_id(uow: Any, owner: dict[str, Any], row: dict[str, Any]) -> str:
        """The namespace whose policy and SoD govern this item. A parameter set has none
        of its own: it is governed by its training warrant's."""
        if owner.get("namespace_id"):
            return str(owner["namespace_id"])
        warrant = uow.repo("training_warrants").get(row.get("training_warrant_id"))
        if warrant is None:
            raise ValidationFailed("This object belongs to no namespace", id=str(row.get("id")))
        return str(warrant["namespace_id"])

    def _policy_for(self, uow: Any, object_type: str, namespace: str) -> dict[str, Any] | None:
        """The policy record the engine will use on this item: the namespace's if it has
        one, else the global one. Showing the first active policy of the type regardless
        of scope would describe a different rule from the one that decides."""
        try:
            record: dict[str, Any] = self.p.workflow.active_policy(uow, object_type, namespace)
        except ValidationFailed:
            return None
        return record

    @staticmethod
    def _ref_of(
        uow: Any, object_type: str, object_id: str, owner: dict[str, Any], ns: dict[str, Any]
    ) -> str:
        events = uow.repo("workflow_events").list(
            object_type=object_type, object_id=object_id, order_by=["-created_at"]
        )
        for event in events:
            if event.get("object_ref"):
                return str(event["object_ref"])
        return f"{ns['name']}/{owner.get('name') or object_id}"

    @staticmethod
    def _impact_roots(ref: str) -> list[str]:
        """A lineage edge may name the version or the bare object; walk from both."""
        roots = [ref]
        bare = ref.split("@")[0]
        if bare != ref:
            roots.append(bare)
        return roots

    @staticmethod
    def _username(uow: Any, user_id: str | None) -> str | None:
        user = uow.repo("users").get(user_id) if user_id else None
        return str(user["username"]) if user else None

    SOD_STATEMENTS = {
        "strict": "nobody who created, submitted or last edited this object may approve it",
        "two_person": "whoever submitted this object may not approve it",
        "none": "no separation of duties is enforced in this namespace",
    }

    def _sod_view(self, p: Principal, row: dict[str, Any], ns: dict[str, Any]) -> dict[str, Any]:
        """The strictness in force and whether it disqualifies this reviewer (§28.9)."""
        level = ns.get("sod", "strict")
        involved = {row.get(k) for k in ("created_by", "submitted_by", "updated_by") if row.get(k)}
        if level == "two_person":
            involved = {row.get("submitted_by") or row.get("created_by")}
        blocks = level != "none" and p.username in involved
        return {
            "level": level,
            "statement": self.SOD_STATEMENTS.get(level, level),
            "blocks_you": blocks,
            "reason": (
                f"segregation of duties ({level}): you created, submitted or last "
                "modified this object, so you cannot approve it"
                if blocks
                else None
            ),
            "involved": sorted(x for x in involved if x),
        }

    CAPABILITY_ACTIONS = {"A": "approve", "U": "submit", "C": "create", "P": "seal"}

    def _transition_views(
        self,
        uow: Any,
        p: Principal,
        record: dict[str, Any] | None,
        row: dict[str, Any],
        kind: str,
        owner: dict[str, Any],
        ns: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Every transition out of this state, each either available or disabled with the
        reason — §16.4: a control nobody explains looks like a broken system.

        The reason is the engine's own: the same role test, the same ``can()`` decision
        and the same separation of duties it will apply if the button is pressed, so the
        screen cannot promise what the server will refuse, or refuse what it would allow.
        """
        if record is None:
            return []
        policy = record["policy"]
        described = self.p.access.describe(uow, kind, owner, state=row["state"])
        sod = self._sod_view(p, row, ns)
        out = []
        for name in pol.transitions_from(policy, row["state"]):
            t = (policy.get("transitions") or {})[name]
            reason = None
            roles = t.get("roles") or t.get("requires_role") or []
            letter = t.get("capability")
            if roles and not set(roles) & set(p.roles):
                reason = f"'{name}' requires one of the roles {', '.join(roles)}; yours are " + (
                    ", ".join(p.roles) or "none"
                )
            elif letter:
                action = self.CAPABILITY_ACTIONS.get(letter, "update")
                decision = can(p, action, described["obj"], described["grants"], ns)
                if not decision:
                    reason = f"you may not {name} this object: {decision.rule}"
            if reason is None and t.get("approvals") and sod["blocks_you"]:
                reason = sod["reason"]
            out.append(
                {
                    "name": name,
                    "to": t.get("to"),
                    "approvals": t.get("approvals") or [],
                    "checks": t.get("checks") or [],
                    "segregation": t.get("segregation"),
                    "available": reason is None,
                    "reason": reason,
                }
            )
        return out

    def _outstanding(
        self,
        uow: Any,
        record: dict[str, Any] | None,
        row: dict[str, Any],
        ns: dict[str, Any],
        object_type: str,
        object_id: str,
    ) -> list[dict[str, Any]]:
        """Which approvals are still missing, and from whom (§10.6)."""
        if record is None:
            return []
        approve = (record["policy"].get("transitions") or {}).get("approve") or {}
        round_no = max(
            uow.repo("workflow_events").count(
                object_type=object_type, object_id=object_id, transition="submit"
            ),
            1,
        )
        given = uow.repo("approvals").list(
            object_type=object_type, object_id=object_id, round_no=round_no, decision="approve"
        )
        out = []
        for requirement in approve.get("approvals") or []:
            when = requirement.get("when")
            if when == "prod" and not ns.get("production"):
                continue
            role = requirement["role"]
            count = int(requirement.get("count", 1))
            done = [a["approver"] for a in given if a["role"] == role]
            if len(done) >= count:
                continue
            out.append(
                {
                    "role": role,
                    "count": count,
                    "given": done,
                    "remaining": count - len(done),
                    "when": when,
                    "who": sorted(self._role_holders(uow, role) - set(done)),
                }
            )
        return out

    @staticmethod
    def _role_holders(uow: Any, role_name: str) -> set[str]:
        role = uow.repo("roles").find_one(name=role_name)
        if role is None:
            return set()
        ids = {ur["user_id"] for ur in uow.repo("user_roles").list(role_id=role["id"])}
        return {
            u["username"]
            for u in uow.repo("users").list(status="active")
            if u["id"] in ids and not u["is_service"]
        }

    def _review_diff(
        self, uow: Any, object_type: str, row: dict[str, Any], owner: dict[str, Any]
    ) -> dict[str, Any]:
        """The semantic diff against the last approved version before this one (§10.3)."""
        from maya.services import catalog

        if object_type == "model_version":
            return self._model_diff(uow, row, owner)
        kinds = {"feature_version": ("feature", "feature_versions", "feature_id")}
        kinds["featureset_version"] = ("featureset", "feature_set_versions", "feature_set_id")
        if object_type not in kinds:
            return {
                "kind": object_type,
                "entries": [],
                "note": f"a {object_type.replace('_', ' ')} carries no definition to diff",
            }
        kind, table, fk = kinds[object_type]
        prior = uow.repo(table).list(
            **{fk: row[fk], "state__in": catalog.APPROVED_STATES},
            version_no__lt=row["version_no"],
            order_by=["-version_no"],
            limit=1,
        )
        if not prior:
            return {
                "kind": kind,
                "entries": [],
                "note": "no approved version before this one: everything in it is new",
            }
        old, new = self._effective(uow, kind, prior[0]), self._effective(uow, kind, row)
        return {
            "kind": kind,
            "against": f"v{prior[0]['version_no']}",
            "entries": catalog.definition_diff(kind, old, new),
            "change_class": row.get("change_class"),
        }

    def _effective(self, uow: Any, kind: str, version: dict[str, Any]) -> dict[str, Any]:
        from maya.services import catalog

        if kind == "featureset":
            effective: dict[str, Any] = self.p.featuresets.effective(uow, version["definition"])[0]
            return effective
        return catalog.effective_feature_definition(uow, version["definition"])

    def _model_diff(self, uow: Any, row: dict[str, Any], owner: dict[str, Any]) -> dict[str, Any]:
        """A model's diff is over its formula, its artifact and its specification."""
        from maya.formula.diff import semantic_diff

        prior = uow.repo("model_versions").list(
            model_id=row["model_id"],
            state__in=("approved", "published"),
            version_no__lt=row["version_no"],
            order_by=["-version_no"],
            limit=1,
        )
        if not prior:
            return {
                "kind": "model",
                "entries": [],
                "note": "no approved version before this one: everything in it is new",
            }
        old = prior[0]
        entries = [
            {
                "section": "Formula",
                "what": "statement",
                "was": "",
                "now": statement,
                "change": "changed",
            }
            for statement in semantic_diff(old["formula_ir"] or {}, row["formula_ir"] or {})
        ]
        for section, key in (("Code", "artifact_hash"), ("Specification", "spec_latex")):
            if old.get(key) != row.get(key):
                entries.append(
                    {
                        "section": section,
                        "what": key.replace("_", " "),
                        "was": str(old.get(key) or "—")[:64],
                        "now": str(row.get(key) or "—")[:64],
                        "change": "changed",
                    }
                )
        _ = owner
        return {"kind": "model", "against": f"v{old['version_no']}", "entries": entries}

    # -- people-facing ------------------------------------------------------------------
    def queue(self, p: Principal, *, everything: bool = False) -> list[dict[str, Any]]:
        """Everything in review that this user may read (My queue, §16.2): an object
        they may not read is not so much as named. ``everything`` is for the system's
        own sweeps (SLA escalation), never for a caller."""
        out = []
        with self.p.uow() as uow:
            names = {n["id"]: n["name"] for n in uow.repo("namespaces").list()}
            for object_type, table in TABLES.items():
                _, parent_key, parent_table, kind = GOVERNING[object_type]
                keep = None if everything else self.p.access.reader(uow, p, kind)
                for row in uow.repo(table).list(state="in_review"):
                    owner = uow.repo(parent_table).get(row[parent_key]) if parent_key else row
                    if keep is not None and not (owner and keep(uow, owner)):
                        continue
                    ev = uow.repo("workflow_events").list(
                        object_type=object_type,
                        object_id=row["id"],
                        order_by=["-created_at"],
                        limit=1,
                    )
                    ref = ev[0]["object_ref"] if ev else row["id"]
                    since = ev[0]["created_at"] if ev else row["updated_at"]
                    out.append(
                        {
                            "object_type": object_type,
                            "id": row["id"],
                            "ref": ref,
                            "submitted_by": row.get("submitted_by") or row.get("created_by"),
                            "since": since,
                            "age_days": (utcnow() - since).days,
                            "namespace": names.get((owner or {}).get("namespace_id")),
                            "mine": (row.get("submitted_by") or row.get("created_by"))
                            == p.username,
                        }
                    )
        return sorted(out, key=lambda r: r["since"])

    def require_read(self, uow: Any, p: Principal, object_type: str, object_id: str) -> None:
        """Review history and comments belong to the object: reading or adding them needs
        read access to the object that governs it (a version's feature, model, …)."""
        if object_type not in GOVERNING:
            raise ValidationFailed(
                f"Unknown object type '{object_type}'", allowed=sorted(GOVERNING)
            )
        table, parent_key, parent_table, kind = GOVERNING[object_type]
        row = uow.repo(table).require(object_id)
        obj = uow.repo(parent_table).require(row[parent_key]) if parent_key else row
        self.p.access.require(uow, p, "read", kind, obj)

    def history(
        self, object_type: str, object_id: str, p: Principal | None = None
    ) -> list[dict[str, Any]]:
        with self.p.uow() as uow:
            if p is not None:
                self.require_read(uow, p, object_type, object_id)
            events = uow.repo("workflow_events").list(
                object_type=object_type, object_id=object_id, order_by=["created_at"]
            )
            approvals = uow.repo("approvals").list(
                object_type=object_type, object_id=object_id, order_by=["created_at"]
            )
        return events + [
            {
                **a,
                "transition": "approval",
                "from_state": "",
                "to_state": "",
                "actor": a["approver"],
            }
            for a in approvals
        ]

    def comment(
        self,
        p: Principal,
        object_type: str,
        object_id: str,
        body: str,
        *,
        blocking: bool = False,
        anchor: str | None = None,
    ) -> dict[str, Any]:
        if not body.strip():
            raise ValidationFailed("A comment needs a body")
        with self.p.uow(p.username) as uow:
            self.require_read(uow, p, object_type, object_id)
            row = uow.repo("comments").add(
                {
                    "object_type": object_type,
                    "object_id": object_id,
                    "author": p.username,
                    "body": body,
                    "blocking": blocking,
                    "anchor": anchor,
                }
            )
            uow.audit(
                "review.commented",
                object_type=object_type,
                object_ref=object_id,
                detail={"blocking": blocking},
            )
            return row

    def resolve_comment(self, p: Principal, comment_id: str) -> dict[str, Any]:
        with self.p.uow(p.username) as uow:
            row = uow.repo("comments").require(comment_id)
            if row["author"] != p.username and not p.is_admin:
                raise PermissionDenied("Only the comment's author resolves it")
            return uow.repo("comments").update(comment_id, {"resolved": True})

    def comments(
        self, object_type: str, object_id: str, p: Principal | None = None
    ) -> list[dict[str, Any]]:
        with self.p.uow() as uow:
            if p is not None:
                self.require_read(uow, p, object_type, object_id)
            return uow.repo("comments").list(
                object_type=object_type, object_id=object_id, order_by=["created_at"]
            )

    def check_no_blocking_comments(self, uow: Any, ctx: dict[str, Any]) -> tuple[bool, str]:
        subject = ctx["subject"]
        open_blocking = uow.repo("comments").count(
            object_type=subject.object_type, object_id=subject.id, blocking=True, resolved=False
        )
        return (
            open_blocking == 0,
            f"{open_blocking} open blocking comment(s)"
            if open_blocking
            else "no open blocking comments",
        )

    def break_glass_report(
        self, p: Principal | None = None, days: int = 31
    ) -> list[dict[str, Any]]:
        """Forced transitions in the last ``days``: all of them for an administrator, for
        anyone else those on objects they may read."""
        with self.p.uow() as uow:
            rows = uow.repo("workflow_events").list(
                forced=True,
                created_at__ge=utcnow() - dt.timedelta(days=days),
                order_by=["-created_at"],
            )
            if p is None or p.is_admin:
                return rows
            out = []
            for r in rows:
                try:
                    self.require_read(uow, p, r["object_type"], r["object_id"])
                except MayaError:
                    continue
                out.append(r)
            return out

    def aging(self, p: Principal | None = None) -> list[dict[str, Any]]:
        """Items past their SLA (§10.4): for ``p``, those they may read; else all."""
        out = []
        with self.p.uow() as uow:
            for item in self.queue(p) if p is not None else self.queue_all():
                # the policy that governs the item: its namespace's, else the global one
                try:
                    policy = self.p.workflow.active_policy(
                        uow, item["object_type"], item["namespace"] or "*"
                    )["policy"]
                except ValidationFailed:
                    continue
                sla = (policy.get("sla_days") or {}).get("in_review")
                if sla and item["age_days"] > int(sla):
                    out.append({**item, "sla_days": sla})
        return out

    def queue_all(self) -> list[dict[str, Any]]:
        from maya.security.authz import Principal as P

        return self.queue(P("", "", [], {}), everything=True)

    # -- delegation and escalation (§10.4) -----------------------------------------------
    def delegate(
        self,
        p: Principal,
        *,
        to: str,
        starts_on: dt.date,
        ends_on: dt.date,
        object_types: list[str] | None = None,
        reason: str = "",
    ) -> dict[str, Any]:
        """Name a stand-in for a date range. Only someone who can approve can delegate."""
        if not any("A" in letters for letters in p.capabilities.values()):
            raise PermissionDenied("Only an approver can delegate approvals")
        if ends_on < starts_on:
            raise ValidationFailed("The delegation ends before it starts")
        bad = set(object_types or []) - set(TABLES)
        if bad:
            raise ValidationFailed("Unknown object type(s): " + ", ".join(sorted(bad)))
        with self.p.uow(p.username) as uow:
            delegate = uow.repo("users").find_one(username=to)
            if delegate is None or delegate["status"] != "active":
                raise ValidationFailed(f"'{to}' is not an active user")
            if delegate["id"] == p.user_id:
                raise ValidationFailed("You cannot delegate to yourself")
            row = uow.repo("delegations").add(
                {
                    "delegator_id": p.user_id,
                    "delegate_id": delegate["id"],
                    "starts_on": starts_on,
                    "ends_on": ends_on,
                    "object_types": object_types or [],
                    "reason": reason,
                }
            )
            uow.repo("notifications").add(
                {
                    "user_id": delegate["id"],
                    "kind": "delegation",
                    "message": f"{p.username} delegated approvals to you from {starts_on} to "
                    f"{ends_on}" + (f" ({', '.join(object_types)})" if object_types else ""),
                    "object_ref": None,
                }
            )
            uow.audit(
                "workflow.delegated",
                object_ref=f"user:{to}",
                detail={
                    "from": p.username,
                    "starts_on": starts_on.isoformat(),
                    "ends_on": ends_on.isoformat(),
                    "object_types": object_types,
                    "reason": reason,
                },
            )
            return row

    def delegations(self, p: Principal) -> list[dict[str, Any]]:
        """Delegations given and received by this user (all, for an administrator)."""
        with self.p.uow() as uow:
            users = {u["id"]: u["username"] for u in uow.repo("users").list()}
            rows = uow.repo("delegations").list(order_by=["-starts_on"])
        out = []
        today = dt.date.today()
        for r in rows:
            if p.is_admin or p.user_id in (r["delegator_id"], r["delegate_id"]):
                active = not r["revoked_at"] and r["starts_on"] <= today <= r["ends_on"]
                out.append(
                    {
                        **r,
                        "delegator": users.get(r["delegator_id"]),
                        "delegate": users.get(r["delegate_id"]),
                        "active": active,
                    }
                )
        return out

    def revoke_delegation(self, p: Principal, delegation_id: str) -> None:
        with self.p.uow(p.username) as uow:
            row = uow.repo("delegations").require(delegation_id)
            if row["delegator_id"] != p.user_id and not p.is_admin:
                raise PermissionDenied("Only the delegator or an administrator revokes it")
            uow.repo("delegations").update(delegation_id, {"revoked_at": utcnow()})
            uow.audit("workflow.delegation_revoked", object_ref=f"delegation:{delegation_id}")

    def escalate_overdue(self) -> int:
        """Items past their SLA escalate to the namespace owner, once each (§10.4)."""
        sent = 0
        with self.p.uow("system") as uow:
            for item in self.aging():
                ns_name = _namespace_of(item["ref"])
                ns = uow.repo("namespaces").find_one(name=ns_name) if ns_name else None
                owners = {ns["owner_id"]} if ns and ns["owner_id"] else _admin_ids(uow)
                for owner in owners:
                    if uow.repo("notifications").find_one(
                        user_id=owner, kind="escalation", object_ref=item["ref"]
                    ):
                        continue
                    uow.repo("notifications").add(
                        {
                            "user_id": owner,
                            "kind": "escalation",
                            "object_ref": item["ref"],
                            "message": f"{item['ref']} has waited {item['age_days']} days in review "
                            f"(SLA {item['sla_days']} days)",
                        }
                    )
                    sent += 1
            if sent:
                uow.audit(
                    "workflow.escalated",
                    principal_type="system",
                    channel="scheduler",
                    detail={"notifications": sent},
                )
        return sent

    # -- campaigns ------------------------------------------------------------------------
    def run_campaign(
        self,
        p: Principal,
        name: str,
        transition: str,
        items: list[dict[str, Any]],
        rationale: str = "",
    ) -> dict[str, Any]:
        """One transition over many objects, per-item status, one audit record (§10.5)."""
        results = []
        for item in items:
            try:
                out = self.p.dispatch_transition(
                    p, item["object_type"], item["id"], transition, rationale=rationale
                )
                results.append(
                    {**item, "ok": True, "state": out["state"], "message": out["message"]}
                )
            except Exception as exc:  # noqa: BLE001 - partial failure is reported per item
                results.append({**item, "ok": False, "message": str(getattr(exc, "message", exc))})
        with self.p.uow(p.username) as uow:
            row = uow.repo("campaigns").add(
                {
                    "name": name,
                    "transition": transition,
                    "items": items,
                    "state": "done",
                    "results": results,
                    "rationale": rationale,
                }
            )
            uow.audit(
                "campaign.run",
                object_type="campaign",
                object_ref=name,
                detail={
                    "transition": transition,
                    "items": len(items),
                    "succeeded": sum(1 for r in results if r["ok"]),
                },
            )
            return row

    def campaigns(self) -> list[dict[str, Any]]:
        with self.p.uow() as uow:
            return uow.repo("campaigns").list(order_by=["-created_at"])
