"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The parameter register: inhabitants of P.

A model is ``f : P × X → D(Y)``. Fitting does not change ``f`` — it picks a point
in ``P``. So a fit produces a **parameter set**, not a model version: the kernel
did not change, and minting a version for every retrain would make "the model
changed" mean two different things.

But a parameter set does change behaviour, so it is immutable, versioned, and an
alias cannot point at it until somebody other than its author has approved it.
That is the same gate that governs model versions, applied to the other half of
the pair.

**A fitted parameter set is accepted only against a warrant MAYA issued.** There
is no back door. Without that, "which data produced these numbers" has no answer,
and the lineage that the featureset, the pinned view versions and the bitemporal
clocks exist to establish stops one step short of the thing it was for.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from core.evidence import EvidenceEngine
from core.authz.common import same_person
from core.log import get_logger
from core.parameters.common import (APPROVED, CALIBRATED, DECLARED, FITTED,
                                    MAX_INLINE_VALUES, NEEDS_WARRANT, PROPOSED,
                                    PROVENANCE, REJECTED, SUPERSEDED,
                                    ParameterError)
from db import ParameterSetRepository
from db.database import digest as canonical_digest

logger = get_logger(__name__)


def _cardinality(values: Dict[str, Any], kind: str) -> int:
    """How big this parameter object is, in whatever unit means something for it.

    Top-level keys for anything whose `P` is a record of numbers; **rules** for a
    rule set, whose document always has three keys however large the policy is.
    """
    if not values:
        return 0
    if kind == "rule_set":
        rules = values.get("rules")
        return len(rules) if isinstance(rules, list) else 0
    return len(values)


class ParameterRegister:
    """Records, approves and resolves the parameters a model version runs with."""

    def __init__(self, parameters: ParameterSetRepository, registry,
                 evidence: EvidenceEngine, warrants=None, featuresets=None,
                 snapshots=None):
        self.parameters, self.registry = parameters, registry
        self.evidence, self.warrants = evidence, warrants
        self.featuresets = featuresets
        # Optional, and its absence is why this gap existed. Without a way to
        # resolve `snapshot_id`, this service stored it as an opaque string and
        # could not have refused an unverified assembly if it wanted to.
        self.snapshots = snapshots

    # ----------------------------------------------------------------- record
    def record(self, urn: str, semver: str, name: str, kind: str,
               values: Dict[str, Any], provenance: str = FITTED,
               diagnostics: Optional[Dict[str, Any]] = None,
               featureset: Optional[str] = None,
               featureset_version: Optional[int] = None,
               window: Optional[Dict[str, float]] = None,
               as_of: Optional[float] = None, snapshot_id: Optional[str] = None,
               warrant_id: Optional[str] = None, values_uri: Optional[str] = None,
               note: str = "", actor: str = "system") -> Dict[str, Any]:
        """Take delivery of an inhabitant of P."""
        if provenance not in PROVENANCE:
            raise ParameterError("unknown_provenance",
                                 f"unknown provenance '{provenance}'",
                                 f"expected one of {', '.join(PROVENANCE)}")
        version = self._version_of(urn, semver)
        self._refuse_if_not_fittable(version, provenance)
        self._check_warrant(provenance, warrant_id, version)
        self._refuse_unverified_snapshot(snapshot_id, provenance)
        values, uri, cardinality = self._store(values, values_uri, provenance, kind)
        binding = self._binding(provenance, featureset, featureset_version)

        row = {
            "model_id": version["model_id"], "model_version_id": version["id"],
            "name": name, "version": self.parameters.next_version(version["id"], name),
            "kind": kind, "provenance": provenance,
            "values_inline": values, "values_uri": uri, "cardinality": cardinality,
            "diagnostics": diagnostics or {},
            "featureset_version_id": binding.get("id"),
            "window_from": (window or {}).get("from"),
            "window_to": (window or {}).get("to"),
            "as_of": as_of, "snapshot_id": snapshot_id, "warrant_id": warrant_id,
            "digest": canonical_digest({"values": values, "uri": uri,
                                        "kind": kind, "model_version": version["id"]}),
            "state": PROPOSED, "note": note,
            "created_by": actor, "created_at": time.time(),
        }
        self.parameters.add(row)
        self.evidence.append("parameter_set_recorded", "version", version["id"],
                             {"name": name, "provenance": provenance, "kind": kind,
                              "digest": row["digest"], "cardinality": cardinality,
                              "featureset": binding.get("label"),
                              "warrant": warrant_id, "as_of": as_of}, actor=actor)
        logger.info("recorded %s parameter set %s v%d for %s@%s",
                    provenance, name, row["version"], urn, semver)
        return self.parameters.one(id=row["id"])

    def _version_of(self, urn: str, semver: str) -> Dict[str, Any]:
        version = self.registry.version(urn, semver)
        if version is None:
            raise ParameterError("no_such_version",
                                 f"{urn} has no version {semver}",
                                 "record parameters against a version that exists")
        return version

    def _refuse_if_not_fittable(self, version: Dict[str, Any],
                                provenance: str) -> None:
        """T0 has no parameters to fit and T6's are not ours to see. Both may
        still hold *declared* parameters — a closed form arrives with them — so
        the refusal is of the route, not of the parameter set."""
        # Read from the row's own column, not from `version["kernel"]`, which
        # does not exist — the kernel spec lives under `manifest.kernel` and the
        # field is a top-level column. So `kind` was **always None** and neither
        # refusal below could ever fire: fitted coefficients could be recorded
        # against a T0 version whose parameter object is terminal, and against a
        # T6 version whose parameters are inside somebody else's black box.
        #
        # The fit *warrant* path refuses both correctly (`L-W1`), so the type
        # error was enforced on one route and not the other — the pattern this
        # module's own docstring warns about, in the module that warns about it.
        kind = self._parameter_kind(version)
        if provenance == FITTED and kind == "none":
            raise ParameterError(
                "nothing_to_fit",
                "this version's parameter object is terminal: its parameters "
                "come from theory, not from data, so there is nothing a fit "
                "could have produced",
                "record them with provenance 'declared', which is what a closed "
                "form actually has")
        if provenance == FITTED and kind == "opaque":
            raise ParameterError(
                "parameters_not_reachable",
                "this version's parameters are inside a vendor black box and "
                "cannot be reached, so MAYA cannot take delivery of them",
                "record what the vendor states with provenance 'declared'")

    @staticmethod
    def _parameter_kind(version: Dict[str, Any]) -> Optional[str]:
        """How `P` is inhabited, from wherever the row keeps it.

        `create` writes it as a top-level column and also inside the manifest.
        Both are read, column first, so this keeps working if a caller hands
        over a manifest-shaped dict rather than a row.
        """
        if version.get("parameter_kind"):
            return version["parameter_kind"]
        kernel = (version.get("manifest") or {}).get("kernel") or {}
        return kernel.get("parameter_kind")

    def _check_warrant(self, provenance: str, warrant_id: Optional[str],
                       version: Dict[str, Any]) -> None:
        """A fitted set is accepted only against a warrant MAYA issued."""
        if provenance not in NEEDS_WARRANT:
            return
        if not warrant_id:
            raise ParameterError(
                "warrant_required",
                "a fitted parameter set must name the warrant it was produced "
                "under; without it, which data produced these numbers has no answer",
                "issue a fit warrant and quote its id, or record this with "
                "provenance 'declared' if nobody fitted it")
        if self.warrants is None:
            return
        grant = self.warrants.get(warrant_id)
        if grant is None:
            raise ParameterError(
                "unknown_warrant",
                f"MAYA did not issue warrant {warrant_id}",
                "parameters are accepted only against a warrant from this register")
        if grant.get("revoked"):
            raise ParameterError(
                "warrant_revoked",
                "that warrant has been revoked, so nothing produced under it may "
                "be taken into the register",
                "issue a fresh fit warrant and run again")
        if grant.get("model_id") != version["model_id"]:
            raise ParameterError(
                "warrant_names_another_model",
                "that warrant was issued for a different model",
                "record the parameters against the model the warrant names")
        if grant.get("version_id") not in (None, version["id"]):
            raise ParameterError(
                "warrant_names_another_version",
                "that warrant was pinned to a different version of this model",
                "record the parameters against the version the warrant names")

    @staticmethod
    def _store(values: Dict[str, Any], uri: Optional[str],
               provenance: str, kind: str = "") -> tuple:
        """Small parameter objects live in the register; large ones are located.

        A coefficient vector is a record — a reviewer should be able to read it.
        A hundred million weights are an artifact, and putting them in a row
        would make every read of the register carry them.

        ## Why `kind` is here

        `cardinality` answers *how big is this parameter object*, and the
        register shows it — "12 values" on the model page and the parameter
        page. For a coefficient vector the top-level key count is that number.

        For a **rule set** it is not. A rule-set document has three top-level
        keys (`rules`, `otherwise`, `note`) whatever it contains, so a
        forty-rule lending policy and a one-rule one both reported **3 values**.
        Not a refusal and not a wrong digest — just a number displayed beside a
        governed object that measured nothing, which is worse than showing no
        number at all, because a reader has no way to tell.
        """
        if not values and not uri:
            raise ParameterError(
                "no_parameters",
                "the parameter set is empty",
                "supply the values, or a uri if they are large enough to be an "
                "artifact rather than a record")
        counted = _cardinality(values, kind)
        if values and len(values) > MAX_INLINE_VALUES:
            if not uri:
                raise ParameterError(
                    "parameters_too_large",
                    f"{len(values)} parameters is an artifact rather than a "
                    f"record; the register holds up to {MAX_INLINE_VALUES} inline",
                    "store them in the artifact store and supply values_uri with "
                    "their digest")
            return {}, uri, counted
        return values, uri, counted

    def _refuse_unverified_snapshot(self, snapshot_id: Optional[str],
                                    provenance: str) -> None:
        """Parameters fitted on an assembly MAYA declared unverified.

        `FittingService` refuses this already, and has since somebody noticed
        that `pit_verified` was "computed, stored, displayed, and gated
        nothing". That fix went on **one** call site — the captive engine, which
        `docs/06` calls optional and which the architecture explicitly steers
        away from.

        This is the other one, and it is the path the platform's own refusal
        message recommends: *"enable execution.captive, or POST the parameters
        to /parameters under the warrant that produced them."* The warrant,
        model and version checks all bit on that route. The leakage check did
        not, so coefficients fitted on a snapshot MAYA had flagged as leaking
        could be recorded, approved by a second person, bound into a warrant and
        served — with the flag sitting `False` on the snapshot the whole time.

        A control fixed at one call site and not the others is the sixth of the
        ways a control reports success while doing nothing, and it is the one
        that recurs most, because the fix looks complete from where it was made.
        """
        if not snapshot_id or provenance != FITTED:
            return
        if self.snapshots is None:
            # Not wired: no opinion rather than a wrong one, and said out loud
            # so that a deployment missing it is visible rather than silently
            # ungated.
            logger.warning("parameter set names snapshot %s but no snapshot "
                           "repository is wired, so point-in-time verification "
                           "was not checked on this path", snapshot_id)
            return
        snapshot = self.snapshots.one(id=snapshot_id)
        if snapshot is None:
            raise ParameterError(
                "unknown_snapshot",
                f"no snapshot '{snapshot_id}' — these parameters name a "
                f"training set that is not in the register",
                "record the snapshot the fit read, or omit snapshot_id if the "
                "fit did not read one")
        if snapshot.get("pit_verified"):
            return
        report = snapshot.get("pit_report") or {}
        leakage = report.get("leakage") or []
        raise ParameterError(
            "snapshot_not_pit_verified",
            f"snapshot '{snapshot.get('name')}' did not pass point-in-time "
            f"verification"
            + (f"; suspected leakage in {', '.join(leakage)}" if leakage else "")
            + (f": {report.get('detail')}" if report.get("detail") else ""),
            "assemble it again from a featureset version whose slots cannot see "
            "the label, or fix the leak the report names; a model fitted on "
            "leaked data scores well and then does not")

    def _binding(self, provenance: str, featureset: Optional[str],
                 version: Optional[int]) -> Dict[str, Any]:
        """A fitted set says which featureset version produced it."""
        if provenance != FITTED:
            return {}
        if not featureset:
            raise ParameterError(
                "featureset_required",
                "a fitted parameter set must name the featureset version it was "
                "fitted from; the coefficients mean nothing without the columns "
                "they belong to",
                "quote the featureset and version the fit warrant named")
        if self.featuresets is None:
            return {"label": f"{featureset}@v{version}"}
        row = self.featuresets.version(featureset, int(version or 0))
        return {"id": row["id"], "label": f"{featureset}@v{row['version']}"}

    # ----------------------------------------------------------------- review
    def approve(self, parameter_set_id: str, actor: str,
                note: str = "") -> Dict[str, Any]:
        """A parameter set changes behaviour, so it is approved like a version."""
        row = self.require(parameter_set_id)
        self._refuse_second_review(row)
        if same_person(actor, row["created_by"]):
            raise ParameterError(
                "self_approval",
                f"{actor} recorded these parameters and cannot also approve them",
                "a parameter set changes what the model does; approval is by "
                "somebody other than whoever produced it")
        self.parameters.set({"state": APPROVED, "approved_by": actor,
                             "approved_at": time.time(), "review_note": note},
                            id=parameter_set_id)
        self.evidence.append("parameter_set_approved", "version",
                             row["model_version_id"],
                             {"name": row["name"], "version": row["version"],
                              "digest": row["digest"], "note": note}, actor=actor)
        return self.parameters.one(id=parameter_set_id)

    def reject(self, parameter_set_id: str, actor: str,
               note: str) -> Dict[str, Any]:
        row = self.require(parameter_set_id)
        self._refuse_second_review(row)
        if not note.strip():
            raise ParameterError(
                "reason_required",
                "rejecting a parameter set requires a reason",
                "say what is wrong with it; the rejection stays in the register")
        self.parameters.set({"state": REJECTED, "approved_by": actor,
                             "approved_at": time.time(), "review_note": note},
                            id=parameter_set_id)
        self.evidence.append("parameter_set_rejected", "version",
                             row["model_version_id"],
                             {"name": row["name"], "note": note}, actor=actor)
        return self.parameters.one(id=parameter_set_id)

    @staticmethod
    def _refuse_second_review(row: Dict[str, Any]) -> None:
        if row["state"] != PROPOSED:
            raise ParameterError(
                "already_reviewed",
                f"this parameter set is already '{row['state']}'",
                "record a new one; an approved parameter set is immutable, "
                "because a run cited it")

    def supersede(self, parameter_set_id: str, by: str,
                  actor: str = "system") -> Dict[str, Any]:
        """Retire a set in favour of a newer one, without deleting the record."""
        row, replacement = self.require(parameter_set_id), self.require(by)
        if replacement["model_version_id"] != row["model_version_id"]:
            raise ParameterError(
                "different_version",
                "a parameter set can only be superseded by one for the same "
                "model version", "")
        self.parameters.set({"state": SUPERSEDED, "superseded_by": by},
                            id=parameter_set_id)
        self.evidence.append("parameter_set_superseded", "version",
                             row["model_version_id"],
                             {"name": row["name"], "superseded_by": by}, actor=actor)
        return self.parameters.one(id=parameter_set_id)

    # ------------------------------------------------------------------ query
    @staticmethod
    def digest_of(row: Dict[str, Any]) -> str:
        """Re-derive a parameter set's digest from what it currently holds.

        Recomputed rather than read back. A check that compares the stored
        digest against the warrant's compares two copies of the same claim and
        would pass over values somebody had edited underneath it -- which is
        precisely the defect the scale suite found in the evidence chain, where
        verify_chain re-linked the stored hash instead of re-deriving it.
        """
        return canonical_digest({"values": row.get("values_inline") or {},
                                 "uri": row.get("values_uri"),
                                 "kind": row.get("kind"),
                                 "model_version": row.get("model_version_id")})

    def get(self, parameter_set_id: str) -> Optional[Dict[str, Any]]:
        return self.parameters.one(id=parameter_set_id)

    def require(self, parameter_set_id: str) -> Dict[str, Any]:
        row = self.get(parameter_set_id)
        if row is None:
            raise ParameterError("no_parameter_set",
                                 f"no parameter set {parameter_set_id}", "")
        return row

    def for_version(self, urn: str, semver: str) -> List[Dict[str, Any]]:
        return self.parameters.for_version(self._version_of(urn, semver)["id"])

    def resolve(self, urn: str, semver: str,
                name: Optional[str] = None) -> Dict[str, Any]:
        """The parameters a run warrant should carry: approved, newest, named.

        Refusing when there is more than one candidate and no name is deliberate.
        Choosing for the caller is how a model quietly runs on last quarter's
        coefficients.
        """
        version = self._version_of(urn, semver)
        approved = [p for p in self.parameters.approved_for(version["id"])
                    if name is None or p["name"] == name]
        if not approved:
            raise ParameterError(
                "no_approved_parameters",
                f"{urn}@{semver} has no approved parameter set"
                + (f" named '{name}'" if name else ""),
                "fit or declare one, and have somebody else approve it")
        names = {p["name"] for p in approved}
        if name is None and len(names) > 1:
            raise ParameterError(
                "ambiguous_parameters",
                f"{urn}@{semver} has approved parameter sets called "
                f"{', '.join(sorted(names))}; naming one is the caller's job",
                "name the parameter set the warrant should carry")
        return max(approved, key=lambda p: (p["version"], p["created_at"]))

    def status(self, urn: str, semver: str) -> Dict[str, Any]:
        """Whether this version's kernel is ready to be used, and by what route."""
        version = self._version_of(urn, semver)
        rows = self.parameters.for_version(version["id"])
        kind = self._parameter_kind(version)
        terminal = (kind == "none")
        approved = [p for p in rows if p["state"] == APPROVED]
        return {
            "model_version": f"{urn}@{semver}",
            "parameter_kind": kind,
            "recorded": len(rows), "approved": len(approved),
            "awaiting_approval": sum(1 for p in rows if p["state"] == PROPOSED),
            "by_provenance": {p: sum(1 for r in rows if r["provenance"] == p)
                              for p in PROVENANCE
                              if any(r["provenance"] == p for r in rows)},
            "ready": bool(approved) or terminal,
            "detail": self._detail(terminal, approved, rows),
        }

    @staticmethod
    def _detail(terminal: bool, approved: List[Dict[str, Any]],
                rows: List[Dict[str, Any]]) -> str:
        if terminal and not rows:
            return ("the parameter object is terminal — there is nothing to fit, "
                    "and the kernel is ready as it stands")
        if approved:
            newest = max(approved, key=lambda p: p["created_at"])
            return (f"running on '{newest['name']}' v{newest['version']}, "
                    f"{newest['provenance']}")
        if rows:
            return "parameters recorded but none approved, so nothing may run yet"
        return "no parameters recorded; this kernel cannot be run until it has some"
