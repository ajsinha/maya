"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Sealing, ephemerality and ownership.

Three states a feature or featureset can be in, and they are not independent.

**Sealed.** Somebody with the right to has declared it final. It cannot be
modified — not renamed, not redefined, not given another version — and it *can*
still be composed from. That combination is the point: sealing is what makes a
parent safe to build on, because a sealed parent is a parent that cannot move.
Evolution does not stop; it moves to a child, where it is visible.

**Ephemeral.** Created for one purpose, read, and destroyed — with a TTL, or on
request. Two rules follow, and both are refusals rather than warnings:

  - Nothing governed may depend on one. A feature contract, a warrant or a
    composition that pinned an ephemeral thing would resolve today and dangle
    tomorrow, and a dangling pin is worse than no pin because it looks like one.
  - It cannot be sealed. "Permanent" and "temporary" are not two flags that
    happen to be set; one of them is wrong.

Destruction is **recorded**. The rows go, the evidence stays: a throwaway
featureset that somebody pulled a million rows through is exactly the thing an
examiner asks about, and "it was ephemeral" is not an answer.

**Owned.** Two different facts, kept apart. The **creator** is history and never
changes. The **owner** is a responsibility and can be transferred — to somebody
who exists, by somebody entitled to, with the handover in the chain. An owner
field that quietly becomes a leaver's username is how a model ends up
accountable to nobody.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from core.evidence import EvidenceEngine
from core.features.common import FeatureError
from core.log import get_logger

logger = get_logger(__name__)

DAY = 86400.0
DEFAULT_TTL_DAYS = 1.0
MAX_TTL_DAYS = 30.0


class Lifecycle:
    """Seals, expires and transfers ownership of a catalogue object."""

    def __init__(self, evidence: EvidenceEngine, noun: str = "feature"):
        self.evidence, self.noun = evidence, noun

    # ------------------------------------------------------------------ seal
    def refuse_if_sealed(self, row: Dict[str, Any], act: str = "change") -> None:
        """A sealed object is final. The way forward is a child, not an edit."""
        if row.get("sealed_at"):
            raise FeatureError(
                f"'{row.get('name')}' was sealed by {row.get('sealed_by')} and "
                f"cannot {act}. compose a new {self.noun} from it instead — that "
                f"is what sealing is for: a parent that cannot move is a parent "
                f"worth building on, and the change stays visible in the child")

    def seal(self, row: Dict[str, Any], actor: str,
             note: str = "") -> Dict[str, Any]:
        """Declare it final. Not reversible except by an administrator."""
        if row.get("sealed_at"):
            raise FeatureError(f"'{row.get('name')}' is already sealed")
        if row.get("ephemeral"):
            raise FeatureError(
                f"'{row.get('name')}' is ephemeral, so it cannot be sealed. "
                f"permanent and temporary are not two flags that happen to be "
                f"set — one of them is wrong")
        patch = {"sealed_at": time.time(), "sealed_by": actor,
                 "seal_note": note}
        self.evidence.append(f"{self.noun}_sealed", self.noun, row["id"],
                             {"name": row.get("name"), "note": note}, actor=actor)
        logger.info("%s %s sealed by %s", self.noun, row.get("name"), actor)
        return patch

    def break_seal(self, row: Dict[str, Any], actor: str,
                   reason: str) -> Dict[str, Any]:
        """Administrators only, and never quietly.

        A seal that anybody could lift would not be a seal. One that nobody
        could lift makes a typo permanent, and the platform already accepts an
        administrator escape for deleting a model. Both facts stay in the chain,
        so the object carries its own history of having been unsealed.
        """
        if not row.get("sealed_at"):
            raise FeatureError(f"'{row.get('name')}' is not sealed")
        if not reason.strip():
            raise FeatureError(
                "breaking a seal requires a reason; it stays in the record, and "
                "the next person to read this object will want to know why")
        self.evidence.append(f"{self.noun}_seal_broken", self.noun, row["id"],
                             {"name": row.get("name"),
                              "sealed_by": row.get("sealed_by"),
                              "reason": reason}, actor=actor)
        logger.warning("%s %s: seal broken by %s — %s",
                       self.noun, row.get("name"), actor, reason)
        return {"sealed_at": None, "sealed_by": None,
                "seal_note": f"unsealed by {actor}: {reason}"}

    # ------------------------------------------------------------- ephemeral
    @staticmethod
    def expiry(ttl_days: Optional[float], now: Optional[float] = None) -> float:
        """When an ephemeral object stops existing."""
        moment = now if now is not None else time.time()
        days = DEFAULT_TTL_DAYS if ttl_days is None else float(ttl_days)
        if days <= 0:
            raise FeatureError(
                "a time to live of zero or less is not a lifetime; leave it out "
                "for the default, or say how long this is actually needed for")
        if days > MAX_TTL_DAYS:
            raise FeatureError(
                f"{days:g} days is longer than the {MAX_TTL_DAYS:g} an ephemeral "
                f"object may live. something needed for longer than that is not "
                f"ephemeral, and declaring it so is a way of avoiding the "
                f"governance a durable one owes")
        return moment + days * DAY

    def refuse_if_ephemeral(self, row: Dict[str, Any], act: str) -> None:
        """Nothing governed may depend on something that will be destroyed."""
        if row.get("ephemeral"):
            raise FeatureError(
                f"'{row.get('name')}' is ephemeral and cannot {act}. a pin to "
                f"something that will be destroyed resolves today and dangles "
                f"tomorrow, which is worse than no pin because it looks like one")

    @staticmethod
    def expired(row: Dict[str, Any], now: Optional[float] = None) -> bool:
        moment = now if now is not None else time.time()
        return bool(row.get("ephemeral") and row.get("expires_at")
                    and row["expires_at"] <= moment)

    def record_destruction(self, row: Dict[str, Any], why: str,
                           detail: Optional[Dict[str, Any]] = None,
                           actor: str = "system") -> None:
        """The rows go; the record that they existed does not.

        A throwaway featureset somebody pulled a million rows through is exactly
        what an examiner asks about, and "it was ephemeral" is not an answer.
        """
        self.evidence.append(f"{self.noun}_destroyed", self.noun, row["id"],
                             {"name": row.get("name"), "why": why,
                              "created_by": row.get("created_by"),
                              "expires_at": row.get("expires_at"),
                              **(detail or {})}, actor=actor)
        logger.info("%s %s destroyed (%s)", self.noun, row.get("name"), why)

    @staticmethod
    def remaining(row: Dict[str, Any], now: Optional[float] = None) -> Dict[str, Any]:
        """How long is left, for a page and for a caller deciding whether to hurry."""
        if not row.get("ephemeral"):
            return {"ephemeral": False, "detail": "durable"}
        moment = now if now is not None else time.time()
        left = (row.get("expires_at") or moment) - moment
        return {
            "ephemeral": True, "expires_at": row.get("expires_at"),
            "seconds_left": max(left, 0.0),
            "expired": left <= 0,
            "detail": (f"expired {abs(left) / 3600:.1f} hours ago and is waiting "
                       f"to be reaped" if left <= 0 else
                       f"{left / 3600:.1f} hours left"),
        }

    # ------------------------------------------------------------- ownership
    def transfer(self, row: Dict[str, Any], to: str, actor: str,
                 reason: str = "") -> Dict[str, Any]:
        """Hand the responsibility on. The creator is history and does not move.

        Two different facts. Whoever made a thing made it, permanently. Whoever
        answers for it can change, and when it changes somebody should be able to
        see when and why — an owner field that quietly becomes a leaver's
        username is how a model ends up accountable to nobody.
        """
        if not to or not to.strip():
            raise FeatureError(
                f"a {self.noun} with no owner is a {self.noun} nobody answers "
                f"for; name who takes it on")
        if to == row.get("owner"):
            raise FeatureError(f"'{to}' already owns '{row.get('name')}'")
        self.refuse_if_sealed(row, "change owner")
        self.evidence.append(f"{self.noun}_ownership_transferred", self.noun,
                             row["id"],
                             {"name": row.get("name"), "from": row.get("owner"),
                              "to": to, "reason": reason}, actor=actor)
        return {"owner": to}

    @staticmethod
    def provenance(row: Dict[str, Any]) -> Dict[str, Any]:
        """Who made it and who answers for it, said separately."""
        creator, owner = row.get("created_by"), row.get("owner")
        return {
            "created_by": creator, "created_at": row.get("created_at"),
            "owner": owner,
            "transferred": bool(creator and owner and creator != owner),
            "detail": (f"created by {creator}, now owned by {owner}"
                       if creator and owner and creator != owner
                       else f"created and owned by {owner or creator or 'nobody'}"),
        }


def reap(rows: List[Dict[str, Any]], now: Optional[float] = None
         ) -> List[Dict[str, Any]]:
    """Which ephemeral objects have outlived their declared lifetime."""
    moment = now if now is not None else time.time()
    return [r for r in rows
            if r.get("ephemeral") and (r.get("expires_at") or moment) <= moment]
