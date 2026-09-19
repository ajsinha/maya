"""
What a change does to the things bound to it (§5.8, §6.7, §8.7).

A reference is either *pinned* — it names a version and nothing can move under
it — or *tracking*, which means "the latest approved one". Tracking is
convenient and dangerous in equal measure, so the platform's side of the
bargain is that a tracking dependant is never quietly changed: when the parent
takes a breaking or behavioural bump, every dependant that tracks it is marked
for re-approval and its owner is told, naming the parent, the version and the
class of the change. Deprecating a member warns every feature set and composite
that holds it, and revoking a member model's warrant flags the composite
execution warrants that embed it.

The bindings are read from the lineage edges the catalog already writes on
approval (``extends``, ``member_of``, ``composite_member``): an edge whose
source is a bare reference *is* a tracking binding, so there is one record of
the relationship rather than two that can disagree.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

from typing import Any

from maya.services import refs

# The edge types that carry a dependency, and how each reads in a sentence.
TRACKING_EDGES = {
    "extends": "inherits from",
    "member_of": "is a member of",
    "composite_member": "is a member model of",
}
# dependant kind -> (its version table, the object table, the foreign key)
DEPENDANTS = {
    "feature": ("feature_versions", "features", "feature_id"),
    "featureset": ("feature_set_versions", "feature_sets", "feature_set_id"),
    "model": ("model_versions", "models", "model_id"),
}
MOVING_CLASSES = ("breaking", "behavioral")


def bare(ref: str) -> str:
    """The reference with any version or pin suffix removed."""
    return ref.split("@")[0].split("#")[0]


class TrackingService:
    """Propagation: re-approval marks, member warnings, warrant flags."""

    def __init__(self, platform: Any) -> None:
        self.p = platform

    # -- the workflow listener -------------------------------------------------
    def on_move(self, uow: Any, subject: Any, transition: str, to_state: str) -> None:
        """Called inside the transition's own transaction, after it has moved.

        A listener never blocks a transition: propagation is a consequence of the
        change, not a condition of it.
        """
        _ = transition
        if to_state in ("approved", "published"):
            self.mark_tracking_dependants(uow, subject)
        elif to_state == "deprecated":
            self.warn_dependants(uow, subject)

    # -- a parent or member bumped (§5.8, §8.7) --------------------------------
    def mark_tracking_dependants(self, uow: Any, subject: Any) -> int:
        """Mark every dependant that tracks this object for re-approval.

        Only a breaking or behavioural bump moves anybody: an additive version adds
        an attribute nobody downstream is yet reading, so re-approving for it would
        be ceremony without a question to answer.
        """
        change_class = subject.row.get("change_class")
        if change_class is not None and change_class not in MOVING_CLASSES:
            return 0
        parent = bare(subject.ref)
        version_no = subject.row.get("version_no")
        note = (
            f"{parent}@v{version_no} was approved and this object tracks it "
            f"({change_class or 'a new version'}): re-approve it, or pin the reference "
            "to the version you reviewed"
        )
        marked = 0
        for edge in self._edges_from(uow, parent):
            marked += self._mark(uow, edge["dst_ref"], note, parent)
        if marked:
            uow.audit(
                "tracking.dependants_marked",
                object_type=subject.object_type,
                object_ref=subject.ref,
                detail={"marked": marked, "change_class": change_class},
            )
        return marked

    def warn_dependants(self, uow: Any, subject: Any) -> int:
        """Tell every feature set and composite holding this object that it is deprecated."""
        parent = bare(subject.ref)
        told = 0
        for edge in self._edges_from(uow, parent):
            resolved = self._resolve(uow, edge["dst_ref"])
            if resolved is None:
                continue
            _, obj, version = resolved
            told += self._notify_owner(
                uow,
                obj,
                "member_deprecated",
                edge["dst_ref"],
                f"{parent} has been deprecated and {TRACKING_EDGES[edge['edge_type']]} "
                f"this object (v{version['version_no']}): name a successor before it retires",
            )
        if told:
            uow.audit(
                "tracking.deprecation_warned",
                object_type=subject.object_type,
                object_ref=subject.ref,
                detail={"warned": told},
            )
        return told

    @staticmethod
    def _edges_from(uow: Any, parent: str) -> list[dict[str, Any]]:
        """Dependency edges whose source is the *bare* parent reference — which is what
        a tracking binding writes; a pinned binding names a version and is not here."""
        out = []
        for edge_type in TRACKING_EDGES:
            out += uow.repo("lineage_edges").list(src_ref=parent, edge_type=edge_type)
        return out

    def _mark(self, uow: Any, dependant_ref: str, note: str, parent: str) -> int:
        resolved = self._resolve(uow, dependant_ref)
        if resolved is None:
            return 0
        kind, obj, version = resolved
        table = DEPENDANTS[kind][0]
        if version["needs_reapproval"] == note:
            return 0  # already marked for this same bump
        uow.repo(table).update(version["id"], {"needs_reapproval": note})
        self._notify_owner(uow, obj, "tracking_bump", dependant_ref, f"{dependant_ref}: {note}")
        _ = parent
        return 1

    def _resolve(self, uow: Any, ref: str) -> tuple[str, dict[str, Any], dict[str, Any]] | None:
        """(kind, the object, the version) a dependency edge's target names."""
        from maya.core.errors import MayaError
        from maya.services import catalog

        try:
            parsed = refs.parse(ref)
        except MayaError:
            return None
        if parsed.kind not in DEPENDANTS or parsed.version is None:
            return None
        vtable, table, fk = DEPENDANTS[parsed.kind]
        try:
            obj, _ = catalog.find_object(uow, table, parsed.kind, parsed)
            version = catalog.version_of(uow, vtable, fk, obj, parsed.version)
        except MayaError:
            return None
        return parsed.kind, obj, version

    @staticmethod
    def _notify_owner(
        uow: Any, obj: dict[str, Any], kind: str, object_ref: str, message: str
    ) -> int:
        owner = obj.get("owner_id")
        if not owner:
            return 0
        if uow.repo("notifications").find_one(
            user_id=owner, kind=kind, object_ref=object_ref, message=message
        ):
            return 0
        uow.repo("notifications").add(
            {"user_id": owner, "kind": kind, "message": message, "object_ref": object_ref}
        )
        return 1

    # -- a member model's warrant was revoked (§9.5) ----------------------------
    def sweep_revoked_members(self) -> int:
        """Flag the composites whose member warrants have been revoked. Run hourly.

        A sweep rather than a hook on revocation: ``warrants.revoke`` cascades to the
        execution warrants issued from the same training warrant, which is a different
        relationship, and the composite that merely *contains* that model is a separate
        instrument with a separate owner. Flagging is idempotent on (owner, warrant,
        message), so a warrant revoked once is reported once however often this runs.
        """
        flagged = 0
        with self.p.uow() as uow:
            revoked = [
                (w["id"], w["revoke_reason"])
                for table in ("training_warrants", "execution_warrants")
                for w in uow.repo(table).list(revoked_at__isnull=False)
            ]
        for warrant_id, reason in revoked:
            flagged += len(self.flag_composites_of(warrant_id, reason or "the warrant was revoked"))
        return flagged

    def flag_composites_of(self, warrant_id: str, reason: str) -> list[dict[str, Any]]:
        """Every composite execution warrant embedding the revoked warrant's model, with
        the member named. Revocation cascades to the warrants issued from the same
        training warrant already; a composite that merely *contains* that model is a
        different instrument with a different owner, and has to be told, not revoked."""
        flagged: list[dict[str, Any]] = []
        with self.p.uow("system") as uow:
            warrant = uow.repo("training_warrants").get(warrant_id) or uow.repo(
                "execution_warrants"
            ).get(warrant_id)
            if warrant is None:
                return flagged
            member_version = warrant["model_version_id"]
            composite_ids = {
                m["composite_version_id"]
                for m in uow.repo("composite_members").list()
                if self._names_version(uow, m["member_ref"], member_version)
            }
            for ew in uow.repo("execution_warrants").list(revoked_at__isnull=True):
                if ew["model_version_id"] not in composite_ids:
                    continue
                member = self._member_name(uow, member_version)
                message = (
                    f"a warrant on member model {member} was revoked ({reason}): this "
                    "composite execution warrant embeds it and needs review"
                )
                self._notify_owner(uow, ew, "member_warrant_revoked", ew["id"], message)
                uow.audit(
                    "tracking.composite_flagged",
                    object_type="execution_warrant",
                    object_ref=ew["id"],
                    detail={"member": member, "reason": reason},
                )
                flagged.append({"execution_warrant_id": ew["id"], "member": member})
        return flagged

    @staticmethod
    def _names_version(uow: Any, member_ref: str, model_version_id: str) -> bool:
        from maya.core.errors import MayaError
        from maya.services import catalog

        try:
            parsed = refs.parse(member_ref, "model")
            model, _ = catalog.find_object(uow, "models", "model", parsed)
            version = catalog.version_of(uow, "model_versions", "model_id", model, parsed.version)
        except MayaError:
            return False
        return bool(version["id"] == model_version_id)

    @staticmethod
    def _member_name(uow: Any, model_version_id: str) -> str:
        version = uow.repo("model_versions").get(model_version_id)
        model = uow.repo("models").get((version or {}).get("model_id"))
        return str((model or {}).get("name") or model_version_id)
