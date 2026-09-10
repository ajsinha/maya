"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Where a fit on sensitive data is allowed to happen.

GDPR asks two things of a run over personal data — that it stay where it is
permitted to be, and that it be for the purpose it was collected for — and both
are questions about *where the compute is*, which a register does not see.

**So the honest position is stated before the code.** MAYA does not run the
training. It cannot observe which machine read the rows, and a platform claiming
to enforce residency by watching would be claiming something it has no way to
check. What it *can* do is refuse to issue the authority in the first place: a
fit happens under a warrant, the warrant names a zone, and a warrant for
restricted data into an unapproved zone is **never issued**. That is a real
control at the only moment MAYA controls, and it is the same shape as everything
else here — the platform gates the *authorisation*, not the execution.

**Whether the run then honoured its warrant is an attestation, not an
observation**, and it is labelled as one. The executor states the zone it ran
in; that statement is evidence the executor said something, exactly as a vendor's
validation report is (`core/validation/vendor.py`), and a mismatch between the
zone authorised and the zone attested is a finding rather than a refusal —
because by the time it is known, the run has happened.

**The classification decides which data is sensitive, and it is derived.** A zone
policy keyed on somebody's opinion of a featureset would be a second answer to a
question `core/classification/` already answers from the features themselves.
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Sequence

from core.execution.errors import WarrantError
from core.log import get_logger

logger = get_logger(__name__)

#: What a zone declares about itself. The residency is a place; the purposes are
#: what the data in it may be used for. Both are the firm's own words, because a
#: closed list here would be this platform having an opinion about how a bank
#: divides the world up.
#:
#: `handles` is the highest data classification the zone may process, read
#: against `core/classification/` — so *which data is sensitive* is derived from
#: the features rather than from anybody's memory.
ZONE_FIELDS = ("name", "residency", "handles", "purposes")

#: Where a fit may run when nobody has said. Deliberately the weakest: an
#: unlisted zone handles nothing above `internal`, so a restricted fit into an
#: unconfigured estate is refused rather than allowed by omission.
DEFAULT_HANDLES = "internal"

RANK = {"public": 0, "internal": 1, "confidential": 2, "restricted": 3}


class ComputeZones:
    """Refuses a fit warrant into a zone that may not hold the data."""

    def __init__(self, zones: Optional[Sequence[Dict[str, Any]]] = None,
                 classification=None, evidence=None):
        self.zones = {z["name"]: z for z in (zones or ())}
        # Which data is sensitive, derived from the features a model reads. A
        # policy keyed on somebody's opinion would be a second answer to a
        # question the classification lattice already settles.
        self.classification, self.evidence = classification, evidence

    # ------------------------------------------------------------- describe
    def describe(self) -> Dict[str, Any]:
        """The zones this estate has, and what each may process."""
        rows = [{**z, "handles": z.get("handles", DEFAULT_HANDLES)}
                for z in self.zones.values()]
        rows.sort(key=lambda z: -RANK.get(z["handles"], 0))
        return {
            "zones": rows, "count": len(rows),
            "default_handles": DEFAULT_HANDLES,
            "enforced_at": "warrant issue",
            "detail": (
                f"{len(rows)} compute zone(s) configured. A fit warrant naming "
                f"an unlisted zone is treated as handling no more than "
                f"'{DEFAULT_HANDLES}', so a restricted fit into an "
                f"unconfigured estate is refused rather than allowed by "
                f"omission. Enforcement is at warrant ISSUE, because MAYA does "
                f"not run the training and cannot observe which machine read "
                f"the rows — what it can do is decline to authorise the run"
                if rows else
                "no compute zone is configured, so every zone handles no more "
                "than 'internal' and a fit over confidential or restricted "
                "data is refused. That is the resting state rather than a "
                "gap: allowing it by omission is what a zone policy exists to "
                "prevent"),
        }

    # ---------------------------------------------------------------- check
    def check(self, urn: str, zone: str,
              purpose: str = "") -> Dict[str, Any]:
        """Whether a fit on this model's data may run in this zone.

        Called at warrant issue. Refuses rather than warns, because this is the
        only moment MAYA holds anything: after the warrant is signed the run is
        somebody else's to make.
        """
        classification = self._classification(urn)
        declared = self.zones.get(zone)
        handles = (declared or {}).get("handles", DEFAULT_HANDLES)

        if RANK.get(classification, 1) > RANK.get(handles, 1):
            raise WarrantError(
                "zone_may_not_hold_this_data",
                f"this model reads {classification} data and zone '{zone}' "
                f"handles no more than {handles}"
                + ("" if declared else
                   f" — '{zone}' is not a configured zone at all, and an "
                   f"unlisted zone is treated as the weakest rather than "
                   f"trusted"),
                "fit in a zone cleared for this data, or reclassify the "
                "features — which is a decision about the data rather than "
                "about this run")

        purposes = (declared or {}).get("purposes") or ()
        if purpose and purposes and purpose not in purposes:
            raise WarrantError(
                "purpose_not_permitted_in_zone",
                f"zone '{zone}' holds data collected for "
                f"{', '.join(purposes)}, and this fit is for '{purpose}'. "
                f"Purpose limitation is not about where the data is, it is "
                f"about what it was gathered to do",
                "fit for a permitted purpose, or in a zone whose data was "
                "collected for this one")
        return {
            "urn": urn, "zone": zone, "classification": classification,
            "zone_handles": handles, "configured": declared is not None,
            "purposes": list(purposes), "permitted": True,
            "detail": (f"a {classification} fit may run in '{zone}', which "
                       f"handles up to {handles}"),
        }

    def _classification(self, urn: str) -> str:
        if self.classification is None:
            # Nothing to derive from, so the strictest assumption. Guessing
            # `internal` here would let a restricted fit through on an instance
            # where nobody wired the lattice in.
            return "restricted"
        try:
            return self.classification.of_model(urn)["classification"]
        except Exception:
            logger.warning("could not derive a classification for %s; the zone "
                           "check assumes the strictest", urn, exc_info=True)
            return "restricted"

    # ----------------------------------------------------------- attestation
    def attest(self, warrant_id: str, *, ran_in: str, authorised: str,
               actor: str = "system") -> Dict[str, Any]:
        """The executor states where it actually ran.

        **An attestation, not an observation**, and labelled as one. MAYA did
        not run the training and cannot see the machine; this is evidence that
        the executor said something, exactly as a vendor's validation report is.
        A mismatch is a **finding rather than a refusal**, because by the time
        it is known the run has already happened — refusing here would be
        theatre.
        """
        matched = ran_in == authorised
        if self.evidence is not None:
            with self.evidence.recording():
                self.evidence.append(
                    "compute_zone_attested", "warrant", warrant_id,
                    {"authorised": authorised, "ran_in": ran_in,
                     "matched": matched}, actor=actor)
        if not matched:
            logger.warning("warrant %s authorised a fit in %s and the executor "
                           "attests it ran in %s", warrant_id, authorised,
                           ran_in)
        return {
            "warrant_id": warrant_id, "authorised": authorised,
            "ran_in": ran_in, "matched": matched,
            "kind": "attestation",
            "detail": (
                f"the executor states the fit ran in '{ran_in}', which is "
                f"where it was authorised" if matched else
                f"the fit was authorised for '{authorised}' and the executor "
                f"states it ran in '{ran_in}'. That is a finding and not a "
                f"refusal: by the time this is known the run has happened, and "
                f"refusing here would be theatre. What it tells you is that "
                f"the authorisation and the execution have come apart, which "
                f"is worth knowing whichever of them was wrong")
            + ". This is what the executor SAID. MAYA did not run the training "
              "and cannot see the machine, so it is an attestation and is "
              "labelled as one",
        }
