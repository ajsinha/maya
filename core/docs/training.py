"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The training record: what one fit actually did.

Every other compiled document is about a model or a version. This one is about a
**parameter set** — one point of `P`, produced by one fit under one warrant — and
it exists because that moment had no document at all.

The case that makes it obvious is the calibrated model. Hull–White is solved
every morning; two hundred and fifty parameter sets a year, each one a governed
act with a warrant behind it and a reviewer's signature on it, and none of them
had a record anybody could read. The note explaining the one morning it went
wrong had nowhere to live, so it lived in an email.

**Compiled, not written.** Everything below is already in the register: the
warrant that authorised the fit, the featureset version it read, the window, the
`as_of`, the diagnostics the estimator returned, who recorded it and who
accepted it. Compiling it means two hundred and fifty records exist whether or
not anybody had time to write one, and the one that needs a human note has a
place to put it — as an attachment against the same subject.

**Pinned, like everything else.** The record names `sb_core@v1`, not `sb_core`.
A training record that referenced the featureset rather than the version would
describe something that has since moved, which is the failure the whole
platform is built to prevent, arriving in documentation's clothes.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from core.docs.common import DocumentError
from core.docs.subjects import PARAMETER_SET
from core.log import get_logger
from db.database import digest as canonical_digest

logger = get_logger(__name__)

TRAINING_RECORD = "training_record"
TITLE = "Training Record"
PURPOSE = ("what one fit read, what it produced, and under whose authority — "
           "the document a daily recalibration never had")


class TrainingRecordCompiler:
    """Compiles the record of one fit, from the register."""

    def __init__(self, documents, parameters, registry, evidence,
                 featuresets=None, warrants=None):
        self.documents = documents
        self.parameters = parameters
        self.registry = registry
        self.evidence = evidence
        self.featuresets = featuresets
        self.warrants = warrants

    # --------------------------------------------------------------- render
    def render(self, parameter_set_id: str) -> Dict[str, Any]:
        """What the record would say. Writes nothing.

        Separated from `compile` for the reason the other documents are: an
        export pack and a dossier want the content without performing the act.
        """
        row = self.parameters.get(parameter_set_id)
        if row is None:
            raise DocumentError("no_parameter_set",
                                f"no parameter set {parameter_set_id}",
                                "name a set the register holds")

        sections: List[Dict[str, Any]] = []
        missing: List[str] = []

        def section(key: str, heading: str, body: Optional[str],
                    required: bool = True) -> None:
            if body is None:
                if required:
                    missing.append(key)
                sections.append({
                    "key": key, "heading": heading, "filled": False,
                    "required": required,
                    "body": _gap(key, required)})
                return
            sections.append({"key": key, "heading": heading, "filled": True,
                             "required": required, "body": body})

        section("identity", "What this is", self._identity(row))
        section("authority", "Under what authority", self._authority(row))
        section("data", "What it read", self._data(row, self._binding(row)))
        section("result", "What it produced", self._result(row))
        section("diagnostics", "What the fit reported", self._diagnostics(row))
        section("acceptance", "Who accepted it", self._acceptance(row))

        return {
            "kind": TRAINING_RECORD,
            "title": f"{TITLE} — {row.get('name') or parameter_set_id}",
            "subject_type": PARAMETER_SET,
            "subject_id": parameter_set_id,
            "model_id": row.get("model_id"),
            "model_version_id": row.get("model_version_id"),
            "sections": sections,
            "citations": [],
            "coverage": {"sections": len(sections),
                         "filled": sum(1 for s in sections if s["filled"]),
                         "missing_required": missing,
                         "complete": not missing},
            "digest": canonical_digest({"kind": TRAINING_RECORD,
                                        "parameter_set": parameter_set_id,
                                        "sections": sections}),
            "subjects": [parameter_set_id],
        }

    def compile(self, parameter_set_id: str,
                actor: str = "system") -> Dict[str, Any]:
        """Render it, then author it."""
        row = self.render(parameter_set_id)
        head, _ = self.evidence.head()
        row.update({"evidence_head": head, "status": "compiled",
                    "compiled_at": time.time(), "compiled_by": actor})
        self.documents.add(row)
        self.evidence.append(
            "training_record_compiled", "parameter_set", parameter_set_id,
            {"document_id": row["id"], "complete": row["coverage"]["complete"]},
            actor=actor)
        logger.info("training record for %s: %d/%d sections",
                    parameter_set_id, row["coverage"]["filled"],
                    row["coverage"]["sections"])
        return self.documents.one(id=row["id"])

    # -------------------------------------------------------------- sections
    @staticmethod
    def _identity(row: Dict[str, Any]) -> Optional[str]:
        return (f"Parameter set **{row.get('name') or row['id']}**, kind "
                f"`{row.get('kind')}`, provenance `{row.get('provenance')}`. "
                f"State **{row.get('state')}**.\n\n"
                f"A parameter set is a point of `P`, not a model version: the "
                f"kernel did not change when this was recorded, which is what "
                f"lets a recalibration procedure be approved once rather than "
                f"pretending a committee meets every morning.")

    @staticmethod
    def _authority(row: Dict[str, Any]) -> Optional[str]:
        warrant = row.get("warrant_id")
        if not warrant:
            # Not a gap to paper over. A fitted set with no warrant is a set
            # whose data provenance has no answer, and the record says so.
            if row.get("provenance") == "declared":
                return ("Declared rather than fitted: these values were chosen "
                        "and recorded, not produced by reading data, so there "
                        "is no fit warrant behind them.")
            return None
        return (f"Fitted under warrant `{warrant}`.\n\n"
                f"A fitted set is accepted only against a warrant MAYA issued. "
                f"Without one, *which data produced these numbers* has no "
                f"answer — so the warrant is the record's spine rather than a "
                f"reference on it.")

    def _binding(self, row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """The featureset version this fit read, resolved from its id.

        The row stores the id rather than the name, which is right — a name
        would go stale — and means the record has to resolve it. Where the
        registry is not wired, the record says the section could not be filled
        rather than inventing a name.
        """
        version_id = row.get("featureset_version_id")
        if not version_id or self.featuresets is None:
            return None
        try:
            return self.featuresets.sets.version_by_id(version_id)
        except Exception as exc:
            logger.warning("could not resolve featureset version %s: %s",
                           version_id, exc)
            return None

    @staticmethod
    def _data(row: Dict[str, Any],
              binding: Optional[Dict[str, Any]]) -> Optional[str]:
        if binding is None:
            return None
        name, number = binding.get("featureset"), binding.get("version")
        window = {"from": row.get("window_from"), "to": row.get("window_to")}
        lines = [f"Featureset **{name} @ v{number}** — the *version*, pinned. "
                 f"A record naming the set rather than the version would "
                 f"describe something that has since moved."]
        if window.get("from") is not None:
            lines.append(f"\nWindow `{window.get('from')}` → `{window.get('to')}`, "
                         f"as of `{row.get('as_of')}`.")
        if row.get("snapshot_id"):
            lines.append(f"\nAssembled from snapshot `{row['snapshot_id']}`, read "
                         f"at its pinned Delta version rather than at the head — "
                         f"so running the same fit twice sees the same bytes.")
        return "\n".join(lines)

    @staticmethod
    def _result(row: Dict[str, Any]) -> Optional[str]:
        values = row.get("values_inline") or {}
        if not values:
            return (f"Held outside the register at `{row['values_uri']}`, "
                    f"digest `{row.get('digest', '')[:23]}`."
                    if row.get("values_uri") else None)
        shown = list(values.items())[:20]
        table = "\n".join(f"| `{k}` | {v} |" for k, v in shown)
        more = ("\n\n*(and "
                f"{len(values) - len(shown)} more)*" if len(values) > len(shown)
                else "")
        return (f"| Parameter | Value |\n|---|---|\n{table}{more}\n\n"
                f"Digest `{row.get('digest', '')[:23]}` — re-derived from the "
                f"values before any run, never compared against a stored copy "
                f"of itself.")

    @staticmethod
    def _diagnostics(row: Dict[str, Any]) -> Optional[str]:
        diagnostics = row.get("diagnostics") or {}
        if not diagnostics:
            return None
        table = "\n".join(f"| `{k}` | {v} |" for k, v in sorted(diagnostics.items()))
        return (f"| Diagnostic | Value |\n|---|---|\n{table}\n\n"
                f"These are what a reviewer reads. MAYA does not decide whether "
                f"a fit is any good; it puts the numbers in front of somebody "
                f"who can, and records that they looked.")

    @staticmethod
    def _acceptance(row: Dict[str, Any]) -> Optional[str]:
        if row.get("state") not in ("approved", "rejected"):
            return None
        verb = "accepted" if row["state"] == "approved" else "rejected"
        return (f"{verb.capitalize()} by **{row.get('approved_by')}**"
                + (f" — {row['review_note']}" if row.get("review_note") else "")
                + f"\n\nNot by whoever recorded it (`{row.get('created_by')}`): "
                  f"a number one person can both produce and bless is a "
                  f"preference, not an estimate.")


def _gap(key: str, required: bool) -> str:
    severity = ("**This section is required and could not be filled.**" if required
                else "*Not applicable to this fit.*")
    return (f"{severity}\n\nNothing in the register supports a `{key}` section "
            f"for this parameter set. That is a statement about the record of "
            f"this fit, not about this document.\n")
