"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

What refers to what — asked once, answered for two different questions.

**"Where is this feature used?"** and **"may I delete this?"** are the same
question with different consequences, and building them separately is how they
come to disagree. A screen that lists three usages while a delete check knows
about four is a screen that says a thing is safe to remove and then refuses.

Both read this.

## Why a delete needed it

`DELETE /models/{name}` checked that the caller was an administrator and that
they had given a reason, and then removed the row. Nineteen tables carry a
`model_id`. Deleting a model with a live warrant, an open finding, a monitor and
three parameter sets left every one of those rows pointing at an identifier that
no longer resolves — and the evidence chain, which survives the deletion by
design, then described acts against a model nobody could look up.

Feature and featureset deletion refused a **durable** one, which is the right
rule and not the whole rule: an *ephemeral* feature sitting in a materialised
view or a published featureset version is exactly as load-bearing while it is
there.

## The distinction that matters

A reference is **blocking** or it is **historical**, and conflating them makes
the check useless in one direction or the other.

*Blocking*: something that would be left broken. A warrant naming this model, a
featureset version pinning this feature, a version this alias points at.

*Historical*: something that records what happened and reads correctly
afterwards. An evidence node, a closed finding, an amendment. Those are not
reasons to refuse — a register in which nothing may ever be deleted because
something once happened is a register that grows without bound — but they are
worth *seeing* before deleting, which is why they are returned rather than
filtered out.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

#: The things this index can be asked about.
KINDS: Tuple[str, ...] = ("model", "model_version", "feature", "feature_view",
                          "featureset", "featureset_version")


@dataclass(frozen=True)
class Reference:
    """One thing that refers to the subject."""
    kind: str            #: what the referrer is — "warrant", "featureset_version"
    identifier: str      #: how to find it
    label: str           #: how to say it to a person
    why: str             #: what the reference IS, in one clause
    blocking: bool       #: would deleting the subject leave this broken

    def as_dict(self) -> Dict[str, Any]:
        return {"kind": self.kind, "id": self.identifier, "label": self.label,
                "why": self.why, "blocking": int(self.blocking)}


class NoSuchSubject(LookupError):
    """The thing being asked about does not exist.

    Held apart from "nothing refers to it", because conflating the two is how
    the dependency screen told somebody a name they had mistyped was safe to
    delete.
    """

    def __init__(self, kind: str, identifier: str):
        super().__init__(identifier)
        self.kind, self.identifier = kind, identifier
        self.code = "no_such_subject"
        self.detail = (f"there is no {kind.replace('_', ' ')} called "
                       f"'{identifier}'")
        self.remediation = ("check the name; this is not the same answer as "
                            "'nothing refers to it', and treating it as one is "
                            "how something gets deleted that was never there")

    def as_problem(self) -> Dict[str, Any]:
        return {"error": self.code, "detail": self.detail,
                "remediation": self.remediation}


class ReferenceIndex:
    """Answers what refers to a model, a version, a feature or a featureset."""

    def __init__(self, db, registry, features):
        self.db, self.registry, self.features = db, registry, features

    # ------------------------------------------------------------------ query
    def to(self, kind: str, identifier: str) -> Dict[str, Any]:
        """Everything that refers to one thing, with the blocking ones marked."""
        if kind not in KINDS:
            raise ValueError(
                f"'{kind}' is not something this index knows about; it answers "
                f"for {', '.join(KINDS)}")
        # Does the subject EXIST? Nothing asked, so a mistyped name answered
        # "nothing refers to this. It can be deleted, and deleting it will
        # leave nothing broken" — identical to the answer for a real,
        # unreferenced thing. The screen's own docstring calls a blank result
        # the most dangerous wrong answer it can give, and this was how it gave
        # it: reassurance about something that was never there.
        if not self._exists(kind, identifier):
            raise NoSuchSubject(kind, identifier)
        found = getattr(self, f"_to_{kind}")(identifier)
        blocking = [r for r in found if r.blocking]
        return {
            "kind": kind, "id": identifier,
            "references": [r.as_dict() for r in found],
            "blocking": len(blocking),
            "historical": len(found) - len(blocking),
            "deletable": not blocking,
            "detail": self._detail(len(blocking), len(found) - len(blocking)),
        }

    def _exists(self, kind: str, identifier: str) -> bool:
        """Whether the thing being asked about is there at all."""
        if kind == "model":
            return self.registry.get(identifier) is not None
        if kind == "model_version":
            return self.registry.version_by_id(identifier) is not None
        if kind == "feature":
            return self.features.feature(identifier) is not None
        if kind == "featureset":
            return self.features.featureset(identifier) is not None
        if kind == "feature_view":
            return bool(self.features.views.views.one(name=identifier))
        if kind == "featureset_version":
            return bool(self.db.query(
                "SELECT id FROM featureset_version WHERE id = :i LIMIT 1",
                {"i": identifier}))
        return True

    @staticmethod
    def _detail(blocking: int, historical: int) -> str:
        if not blocking and not historical:
            return "nothing refers to this"
        parts = []
        if blocking:
            parts.append(f"{blocking} reference(s) would be left broken by a "
                         f"deletion")
        if historical:
            parts.append(f"{historical} historical reference(s), which read "
                         f"correctly afterwards and do not block one")
        return "; ".join(parts)

    # ------------------------------------------------------------- the models
    def _to_model(self, urn: str) -> List[Reference]:
        model = self.registry.get(urn)
        if not model:
            return []
        model_id = model["id"]
        found: List[Reference] = []

        for row in self.db.query(
                "SELECT semver, status FROM model_version WHERE model_id = :m",
                {"m": model_id}):
            found.append(Reference(
                "model_version", row["semver"], f"version {row['semver']}",
                f"an immutable version of this model, {row['status']}", True))

        for row in self.db.query(
                "SELECT id, principal, environment, declared_use, revoked "
                "FROM warrant WHERE model_id = :m", {"m": model_id}):
            live = not row["revoked"]
            found.append(Reference(
                "warrant", row["id"],
                f"{row['principal']} in {row['environment']}",
                ("a live grant to run this model" if live
                 else "a revoked grant, kept as a record"),
                live))

        for row in self.db.query(
                "SELECT id, environment, name FROM alias WHERE model_id = :m",
                {"m": model_id}):
            found.append(Reference(
                "alias", row["id"], f"{row['environment']}/{row['name']}",
                "an alias consumers bind to instead of a semver", True))

        for row in self.db.query(
                "SELECT id, name, state FROM parameter_set WHERE model_id = :m",
                {"m": model_id}):
            found.append(Reference(
                "parameter_set", row["id"], row["name"],
                f"a point of P this model runs at, {row['state']}",
                row["state"] == "approved"))

        for row in self.db.query(
                "SELECT id, title, status FROM finding WHERE model_id = :m",
                {"m": model_id}):
            open_ = row["status"] not in ("closed", "withdrawn")
            found.append(Reference(
                "finding", row["id"], row["title"],
                ("an open finding against this model" if open_
                 else "a closed finding, which is the record that it was"),
                open_))

        for row in self.db.query(
                "SELECT id, name, status FROM monitor WHERE model_id = :m",
                {"m": model_id}):
            found.append(Reference(
                "monitor", row["id"], row["name"],
                f"a monitor on this model, {row['status']}",
                row["status"] == "active"))

        for row in self.db.query(
                "SELECT id, reference, name, status, effective_to "
                "FROM model_use WHERE model_id = :m", {"m": model_id}):
            live = row["status"] == "active"
            found.append(Reference(
                "model_use", row["id"], row["reference"],
                (f"a declared use of this model: {row['name']}" if live
                 else f"a retired use, {row['name']} — the record that it was "
                      f"used for this once"),
                live))

        for row in self.db.query(
                "SELECT id, inherited_at FROM monitoring_plan "
                "WHERE model_id = :m", {"m": model_id}):
            inherited = bool(row.get("inherited_at"))
            found.append(Reference(
                "monitoring_plan", row["id"], "monitoring plan",
                ("the plan this model's monitors were created from" if inherited
                 else "a monitoring plan that has NOT been inherited — this "
                      "model is planned for and not monitored"),
                not inherited))

        for row in self.db.query(
                "SELECT COUNT(*) AS n, MAX(at) AS last FROM warrant_invocation "
                "WHERE model_id = :m", {"m": model_id}):
            if row.get("n"):
                found.append(Reference(
                    "warrant_invocation", model_id,
                    f"{row['n']} invocation(s)",
                    "a record of this model actually being run — not a "
                    "dependency, but the thing that says deleting it would "
                    "lose the history of who called it",
                    False))

        for row in self.db.query(
                "SELECT id, reference, kind, regulator, scope, state "
                "FROM regulatory_approval WHERE model_id = :m",
                {"m": model_id}):
            live = row["state"] == "in_force"
            found.append(Reference(
                "regulatory_approval", row["id"], row["reference"],
                (f"a {row['kind'].upper()} permission from {row['regulator']} "
                 f"over {row['scope']} — deleting the model would remove the "
                 f"record of a permission somebody else granted, which is not "
                 f"this firm's to delete"
                 if live else
                 f"a {row['kind'].upper()} permission that is {row['state']}, "
                 f"and the record that it was once held"),
                live))

        for row in self.db.query(
                "SELECT id, urn, amount, currency, source "
                "FROM estate_cost WHERE model_id = :m", {"m": model_id}):
            found.append(Reference(
                "estate_cost", row["id"],
                f"{row['amount']:,.2f} {row['currency']} from {row['source']}",
                ("an attested cost attributed to this model. The ownership on "
                 "it was copied from the register at record time so that a "
                 "report for last quarter says who owned it last quarter — "
                 "deleting the model leaves the figure with an owner nothing "
                 "can any longer explain"),
                # Not live-blocking: a historical cost line is evidence about a
                # period already closed, and a deletion that waited for it
                # would be a deletion nobody can perform.
                False))

        for row in self.db.query(
                "SELECT id, replacement, retention_class, decommissioned_by "
                "FROM model_decommission WHERE model_id = :m", {"m": model_id}):
            found.append(Reference(
                "model_decommission", row["id"],
                f"decommissioned by {row['decommissioned_by']}, kept under "
                f"'{row['retention_class']}'",
                ("the record of why this model was taken out of service, what "
                 "does its job now and how long it is kept. It exists BECAUSE "
                 "those questions get asked years later by somebody who cannot "
                 "ask anybody — and deleting the model deletes the answer "
                 "along with the retention obligation that was the reason for "
                 "keeping it"),
                # Live-blocking, and the only one of these that is. Everything
                # else here is evidence about a period already closed; this is
                # an undischarged retention obligation, and deleting the row it
                # attaches to is the specific act it exists to prevent.
                True))

        for row in self.db.query(
                "SELECT id, fact, source, reference "
                "FROM tiering_fact_source WHERE model_id = :m",
                {"m": model_id}):
            found.append(Reference(
                "tiering_fact_source", row["id"],
                f"{row['fact']} from {row['source']}",
                ("the attestation that this model's "
                 f"{row['fact']} came from {row['source']} "
                 f"({row['reference']}) rather than from somebody's estimate. "
                 "Deleting the model deletes the only record distinguishing "
                 "its tier from a number typed into a form"),
                # Never live-blocking. A source record is evidence about a
                # decision already made, and a deletion that had to wait for
                # somebody to un-source a fact would be a deletion nobody can
                # perform — which is how orphan rows get left behind instead.
                False))

        for row in self.db.query(
                "SELECT id, reference, recipient, status, expires_at "
                "FROM export_share WHERE model_id = :m", {"m": model_id}):
            live = row["status"] == "open"
            found.append(Reference(
                "export_share", row["id"], row["recipient"],
                ("a live share of this model's export pack with somebody "
                 "outside the firm — deleting the model would leave a link "
                 "serving an archive nothing here can any longer explain"
                 if live else
                 "a closed share, and the record of what left the building "
                 "and who it went to"),
                live))

        for row in self.db.query(
                "SELECT id, reference, question, state FROM elicitation "
                "WHERE model_id = :m", {"m": model_id}):
            live = row["state"] == "open"
            found.append(Reference(
                "elicitation", row["id"], row["reference"],
                (f"an open panel answering '{row['question'][:60]}' about this "
                 f"model — deleting it would end an elicitation mid-round and "
                 f"lose the responses already given"
                 if live else
                 "a concluded elicitation, and the record of how much the "
                 "panel disagreed on the way to the number"),
                live))

        for row in self.db.query(
                "SELECT id, reference, verb, state FROM run WHERE model_id = :m",
                {"m": model_id}):
            live = row["state"] == "open"
            found.append(Reference(
                "run", row["id"], row["reference"],
                (f"an OPEN {row['verb']} run against this model — it has "
                 f"consumed a warrant and read whatever its inputs named, and "
                 f"deleting the model now would leave a run nothing can be "
                 f"reconciled to"
                 if live else
                 f"a {row['verb']} run that {row['state']}, and the lineage of "
                 f"whatever it produced"),
                live))

        for row in self.db.query(
                "SELECT id, auto_accept, status FROM retrain_policy "
                "WHERE model_id = :m", {"m": model_id}):
            live = row["status"] == "active"
            found.append(Reference(
                "retrain_policy", row["id"],
                "automatic" if row["auto_accept"] else "triggers only",
                ("a standing approval in force — somebody delegated a "
                 "judgement over this model's future re-fits, and deleting it "
                 "would erase the delegation rather than end it"
                 if live else
                 "a standing approval that is no longer in force, kept as the "
                 "record that one existed"),
                live))

        for row in self.db.query(
                "SELECT i.id, i.state, c.reference, c.kind, c.status "
                "FROM campaign_item i JOIN campaign c "
                "ON c.id = i.campaign_id WHERE i.model_id = :m",
                {"m": model_id}):
            live = row["status"] == "open" and row["state"] == "outstanding"
            found.append(Reference(
                "campaign_item", row["id"], row["reference"],
                (f"an outstanding item in the open {row['kind']} round — "
                 f"deleting the model would shrink a population that was "
                 f"deliberately frozen, and the round's completion figure "
                 f"would rise without anybody having answered anything"
                 if live else
                 f"this model's place in the {row['kind']} round "
                 f"{row['reference']}, and the answer given in it"),
                live))

        for row in self.db.query(
                "SELECT id, reference, vendor, product, state "
                "FROM vendor_assessment WHERE model_id = :m",
                {"m": model_id}):
            open_still = row["state"] == "open"
            found.append(Reference(
                "vendor_assessment", row["id"], row["reference"],
                (f"an open due-diligence assessment of {row['vendor']} "
                 f"{row['product']} — deleting the model would end it with no "
                 f"conclusion, and the questions answered so far would answer "
                 f"nothing"
                 if open_still else
                 f"a concluded assessment of {row['vendor']} "
                 f"{row['product']}, and the record of what this firm "
                 f"established about a model it did not build"),
                open_still))

        for row in self.db.query(
                "SELECT id, reference, state, champion_semver, "
                "challenger_semver FROM parallel_run WHERE model_id = :m",
                {"m": model_id}):
            running = row["state"] == "running"
            found.append(Reference(
                "parallel_run", row["id"], row["reference"],
                (f"a parallel run of {row['challenger_semver']} against "
                 f"{row['champion_semver']} that is still open — deleting the "
                 f"model would end it with no verdict, and the observations "
                 f"gathered so far would answer nothing"
                 if running else
                 f"a concluded parallel run, and the record of how "
                 f"{row['challenger_semver']} compared before somebody decided "
                 f"about it"),
                running))

        for row in self.db.query(
                "SELECT id, reference, kind, enforcement, state "
                "FROM approval_condition WHERE model_id = :m",
                {"m": model_id}):
            active = row["state"] == "active"
            found.append(Reference(
                "approval_condition", row["id"], row["reference"],
                (f"a {row['enforcement']} condition on this model's approval "
                 f"({row['kind']}) — deleting the model would remove the "
                 f"control without anybody deciding to"
                 if active else
                 f"a discharged {row['kind']} condition, and the record that "
                 f"this model was once approved only on terms"),
                active))

        for row in self.db.query(
                "SELECT COUNT(*) AS n, SUM(CASE WHEN features IS NOT NULL "
                "THEN 1 ELSE 0 END) AS held FROM inference "
                "WHERE model_id = :m", {"m": model_id}):
            if row.get("n"):
                held = row.get("held") or 0
                found.append(Reference(
                    "inference", model_id, f"{row['n']} inference record(s)",
                    (f"what this model was asked and answered. {held} of them "
                     f"hold the feature values themselves, so deleting the "
                     f"model would strand personal data behind an identifier "
                     f"nothing resolves — which is worse than losing it, "
                     f"because nothing would then be watching its retention"
                     if held else
                     "what this model was asked and answered, as keyed "
                     "digests. Not a dependency, but the record that would "
                     "answer whether a past decision came from this model"),
                    bool(held)))

        for row in self.db.query(
                "SELECT id, reference, control, status FROM control_waiver "
                "WHERE model_id = :m", {"m": model_id}):
            active = row["status"] == "active"
            found.append(Reference(
                "control_waiver", row["id"], row["reference"],
                (f"a control this model is deliberately not meeting "
                 f"({row['control']})" if active
                 else f"a waiver of {row['control']}, {row['status']} — the "
                      f"record that the control was relaxed once"),
                active))

        for row in self.db.query(
                "SELECT id, name, status FROM overlay WHERE model_id = :m",
                {"m": model_id}):
            found.append(Reference(
                "overlay", row["id"], row["name"],
                f"an adjustment on this model's output, {row['status']}",
                row["status"] not in ("closed", "expired")))

        for row in self.db.query(
                "SELECT id, from_model, to_model, kind FROM model_edge "
                "WHERE from_model = :u OR to_model = :u", {"u": urn}):
            other = (row["to_model"] if row["from_model"] == urn
                     else row["from_model"])
            found.append(Reference(
                "model_edge", row["id"], f"{row['kind']} {other}",
                "a relation to another model, which would point at nothing",
                True))

        for row in self.db.query(
                "SELECT id, title FROM attachment WHERE model_id = :m",
                {"m": model_id}):
            found.append(Reference(
                "attachment", row["id"], row["title"],
                "a document filed against this model", True))

        for row in self.db.query(
                "SELECT id, kind FROM document WHERE model_id = :m",
                {"m": model_id}):
            found.append(Reference(
                "document", row["id"], row["kind"],
                "a compiled document about this model", True))

        # The seven tables this index did not read. Nineteen tables carry a
        # `model_id` and twelve were checked, so a delete could orphan the rest
        # while the dependency screen -- whose own docstring calls a blank
        # result "the most dangerous wrong answer this screen can give" --
        # reported that nothing referred to the model.
        #
        # Two of the seven are reachable with no version at all, which is
        # exactly the case the delete permits:
        #
        #   `risk_assessment` holds the TIER, which decides every control
        #   requirement and every quorum size on the model.
        #
        #   `compliance_debt` is raised per gap by a baseline import, and
        #   `DebtRegister.reconcile` is per-model — so debt orphaned by a
        #   deleted model can never close, and the programme's burn-down is
        #   pinned below 100% forever with no row anyone can act on.
        #
        # The rest are history rather than live commitments, so they are
        # reported and do not block: refusing to delete a model because it once
        # had an amendment would make the control unusable.
        for table, columns, kind, label, why, blocking in (
                ("risk_assessment", "id, tier", "risk_assessment", "tier",
                 "the tier assessment that decides this model's controls", True),
                ("compliance_debt", "id, gap_key, status", "compliance_debt",
                 "gap_key",
                 "an open baseline gap that can only be closed against this "
                 "model", True),
                ("attestation", "id, kind, status", "attestation", "kind",
                 "an attestation of this model", True),
                ("amendment", "id, status", "amendment", "status",
                 "an amendment raised against this model", True),
                ("breach", "id, severity", "breach", "severity",
                 "a recorded breach of appetite by this model", False),
                ("alias_history", "id, name", "alias_history", "name",
                 "a past alias move on this model", False),
                ("finding_action", "id, finding_id", "finding_action",
                 "finding_id",
                 "an action recorded against a finding on this model", False)):
            for row in self.db.query(
                    f"SELECT {columns} FROM {table} WHERE model_id = :m",
                    {"m": model_id}):
                found.append(Reference(
                    kind, str(row["id"]), str(row.get(label) or row["id"]),
                    why, blocking))

        return found

    def _to_model_version(self, version_id: str) -> List[Reference]:
        found: List[Reference] = []
        for table, columns, kind, why, blocking in (
                ("parameter_set", "id, name, state", "parameter_set",
                 "a point of P against this version", None),
                ("validation", "id, status", "validation",
                 "an effective-challenge episode about this version", None),
                ("version_approval", "id, status", "version_approval",
                 "the quorum that approved this version", False),
                ("feature_contract", "id", "feature_contract",
                 "the featureset this version's contract pins", True),
                ("serving_attestation", "id", "serving_attestation",
                 "an engine's statement of what it served", False),
                ("model_limitation", "id, reference", "limitation",
                 "a stated limitation of this version", True),
                ("model_assumption", "id, reference", "assumption",
                 "a stated assumption of this version", True)):
            for row in self.db.query(
                    f"SELECT {columns} FROM {table} WHERE model_version_id = :v",
                    {"v": version_id}):
                blocks = (blocking if blocking is not None
                          else (row.get("state") or row.get("status"))
                          in ("approved", "open", "in_progress"))
                found.append(Reference(
                    kind, row["id"],
                    str(row.get("name") or row.get("reference")
                        or row.get("state") or row.get("status")
                        or row["id"][:12]),
                    why, bool(blocks)))
        return found

    # ----------------------------------------------------------- the features
    def _to_feature(self, name: str) -> List[Reference]:
        found: List[Reference] = []

        # A view carries feature names in a JSON column, so this is read in
        # Python rather than as SQL — `LIKE '%name%'` would match `ltv` inside
        # `ltv_band`, which is the kind of near-miss that makes a delete check
        # untrustworthy in the direction that matters.
        for view in self.features.views.views.many():
            for pin in self.features.views.versions_of(view["name"]):
                if name in (pin.get("features") or []):
                    found.append(Reference(
                        "feature_view_version", pin["id"],
                        f"{view['name']} v{pin['version']}",
                        "a materialised view carrying this feature's values",
                        True))

        for derived in self.features.derived.list():
            if name in (derived.get("inputs") or []):
                found.append(Reference(
                    "derived_feature", derived["id"], derived["name"],
                    "a derived feature computed from this one", True))

        for row in self.features.sets.sets.many():
            plan = row.get("slots") or {}
            if name in plan:
                found.append(Reference(
                    "featureset", row["id"], row["name"],
                    "a featureset declaring a slot of this name", True))

        for version in self.features.sets.versions.many():
            bindings = version.get("bindings") or {}
            bound = [slot for slot, b in bindings.items()
                     if (b.get("feature") if isinstance(b, dict) else b) == name]
            if bound:
                found.append(Reference(
                    "featureset_version", version["id"],
                    f"version {version['version']} · {', '.join(sorted(bound))}",
                    "a published featureset version pinning this feature",
                    True))
        return found

    def _to_feature_view(self, name: str) -> List[Reference]:
        found: List[Reference] = []
        view = self.features.views.views.one(name=name)
        if not view:
            return []
        for version in self.features.sets.versions.many():
            for slot, binding in (version.get("bindings") or {}).items():
                if isinstance(binding, dict) and binding.get("view") == name:
                    found.append(Reference(
                        "featureset_version", version["id"],
                        f"version {version['version']} · slot {slot}",
                        "a featureset version pinned to this view", True))
                    break
        return found

    def _to_featureset(self, name: str) -> List[Reference]:
        row = self.features.sets.get(name)
        if not row:
            return []
        found: List[Reference] = []
        for version in self.features.sets.versions.many(featureset_id=row["id"]):
            found += self._to_featureset_version(version["id"])
            found.append(Reference(
                "featureset_version", version["id"],
                f"version {version['version']}",
                "a published version of this set, digested and pinnable", True))
        for other in self.features.sets.sets.many():
            composes = [c.get("name") if isinstance(c, dict) else c
                        for c in (other.get("composes") or [])]
            if name in composes:
                found.append(Reference(
                    "featureset", other["id"], other["name"],
                    "a featureset composed from this one", True))
        return found

    def _to_featureset_version(self, version_id: str) -> List[Reference]:
        found: List[Reference] = []
        for row in self.db.query(
                "SELECT id, name, state FROM parameter_set "
                "WHERE featureset_version_id = :v", {"v": version_id}):
            found.append(Reference(
                "parameter_set", row["id"], row["name"],
                "coefficients fitted from this exact set", True))

        # `dataset_snapshot` names the set and its number rather than the
        # version's id, so this looks it up by those.
        version = self.features.sets.versions.one(id=version_id)
        if version:
            owner = self.features.sets.sets.one(id=version["featureset_id"])
            for row in self.db.query(
                    "SELECT id, name FROM dataset_snapshot WHERE featureset = :f "
                    "AND featureset_version = :n",
                    {"f": (owner or {}).get("name"), "n": version["version"]}):
                found.append(Reference(
                    "dataset_snapshot", row["id"], row["name"],
                    "a training set assembled from this version", True))
        return found

    # ----------------------------------------------------------------- refuse
    def refuse_if_referenced(self, kind: str, identifier: str,
                             label: Optional[str] = None) -> None:
        """Raise unless nothing would be left broken.

        The message names what refers to it rather than saying no: somebody who
        is told *why* can go and deal with it, and somebody who is told *no*
        finds another way.
        """
        report = self.to(kind, identifier)
        blocking = [r for r in report["references"] if r["blocking"]]
        if not blocking:
            return
        shown = blocking[:6]
        listed = "; ".join(f"{r['kind']} {r['label']} — {r['why']}"
                           for r in shown)
        more = (f" and {len(blocking) - len(shown)} more"
                if len(blocking) > len(shown) else "")
        raise ReferencedError(
            "still_referenced",
            f"{label or identifier} cannot be deleted: {len(blocking)} thing(s) "
            f"refer to it and would be left pointing at nothing — {listed}"
            f"{more}",
            "remove or retire what refers to it first, or retire this instead "
            "of deleting it — retiring withdraws it from use and keeps every "
            "reference readable")


class ReferencedError(RuntimeError):
    """Something refers to this, so it may not be deleted.

    The code is the first argument, like every other coded refusal here — the
    discipline test walks `core/` for exactly that shape, and a class attribute
    would have left this status documented and, as far as the walker could see,
    raised by nothing.
    """

    def __init__(self, code: str, detail: str, remediation: str = ""):
        super().__init__(detail)
        self.code, self.detail, self.remediation = code, detail, remediation

    def as_problem(self) -> Dict[str, Any]:
        return {"error": self.code, "detail": self.detail,
                "remediation": self.remediation}
