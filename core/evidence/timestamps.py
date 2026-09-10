"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

A time somebody who is not us will attest to, and the half of it that is a lie.

The evidence chain is hash-linked, so a rewritten node is detectable. The anchors
put heads outside the database, so a rewritten *chain* is detectable. Neither
says **when**. Every timestamp in the register is a clock the firm controls, and
a firm arguing with a supervisor about the order of events is arguing from its
own clock.

RFC 3161 closes that: a Time Stamp Authority signs a hash and returns a token
saying *this data existed at this instant*, and the signature is not the firm's.

**MAYA is not the authority, and does not verify the token either.** Both halves
matter and the second is the one people skip. Verifying an RFC 3161 token means
holding the authority's certificate chain and deciding which roots to trust ---
which is a decision a bank's security function has already made, differently,
and shipping one here would be shipping that decision. This is exactly the
position taken on artifact signing (`FR-VER-007`), and it produces the same
three states rather than a boolean:

  * **`verified`** --- a verifier this firm wired accepted the token.
  * **`unverified`** --- a token is held and nothing here can check it.
  * **`absent`** --- there is no token. Reported as absent, never as untimed.

Collapsing `unverified` into `absent` would let a token nobody could check read
as no token at all. Collapsing it into `verified` is worse and is the mistake
this arrangement exists to make impossible.

**And a timestamp bounds the head from above, not below.** A token proves the
chain head existed *no later than* T. That is what stops a firm reconstructing a
record after the fact and claiming it is old --- which is the thing a supervisor
is actually worried about. It does **not** prove the head existed no *earlier*
than T, it says nothing about a record deleted before any token was taken, and
it cannot see behind the first one. The report says all three, because a control
whose limits are unstated is one somebody will lean on past them.

**Nothing is timestamped by default.** With no authority wired, `stamp()`
refuses rather than recording an untimestamped anchor as though it had been
timed, and the estate view reports how much of the chain is covered. A firm that
believes its chain is externally timestamped when it is not is worse off than one
that knows, because the first has stopped asking.
"""
from __future__ import annotations

import json
import time
from typing import Any, Dict, Optional, Protocol, runtime_checkable

from core.log import get_logger

logger = get_logger(__name__)

VERIFIED, UNVERIFIED, ABSENT = "verified", "unverified", "absent"
STATES = (VERIFIED, UNVERIFIED, ABSENT)

#: The hash a token covers. SHA-256 because the chain is SHA-256 and a token
#: over a different digest would be a token over a different thing.
ALGORITHM = "sha256"


@runtime_checkable
class TimestampAuthority(Protocol):
    """Something that will attest to a time. Deliberately tiny.

    Two methods, and neither of them is *verify*. An authority that both issued
    and checked its own tokens would be the arrangement this exists to replace.
    """

    name: str

    def stamp(self, digest: str) -> Dict[str, Any]:
        """Return a token over this digest, or raise. MAYA does not mint one."""
        ...


@runtime_checkable
class TimestampVerifier(Protocol):
    """Something that will check a token against a trust root MAYA does not hold."""

    def verify(self, token: Dict[str, Any], digest: str) -> Dict[str, Any]:
        """Return `{"valid": bool, "at": float, "authority": str, "why": str}`."""
        ...


class TimestampError(RuntimeError):
    """A timestamping operation was refused. The message always says why."""

    def __init__(self, code: str, detail: str, remediation: str = ""):
        super().__init__(detail)
        self.code, self.detail, self.remediation = code, detail, remediation

    def as_problem(self) -> Dict[str, str]:
        return {"error": self.code, "detail": self.detail,
                "remediation": self.remediation}


class ChainTimestamps:
    """Holds tokens over anchored chain heads, and never mints or trusts one."""

    #: Where a token lives, beside the anchor it covers, in the same WORM store.
    NAME = "timestamp-{seq:012d}.json"

    def __init__(self, anchor, authority=None, verifier=None, evidence=None):
        self.anchor = anchor
        # Both optional and both reported. Without an authority nothing is
        # stamped; without a verifier everything held reads `unverified`, which
        # is a weaker claim than `verified` and a much stronger one than
        # `absent`.
        self.authority, self.verifier = authority, verifier
        self.evidence = evidence

    # ------------------------------------------------------------------ stamp
    def stamp(self, seq: Optional[int] = None,
              now: Optional[float] = None,
              actor: str = "system") -> Dict[str, Any]:
        """Ask the authority to attest to an anchored head.

        Only an **anchored** head is stamped. A token over a head that was never
        written outside the database would attest to a hash nothing can be
        compared against later, which is a receipt rather than a control.
        """
        if self.authority is None:
            raise TimestampError(
                "no_timestamp_authority",
                "no time stamp authority is wired, so nothing here can attest "
                "to when this chain head existed",
                "configure one under `evidence.timestamps` — and until then "
                "the chain's timestamps are the firm's own clock, which is "
                "reported rather than assumed")
        anchored = self.anchor.latest() if seq is None \
            else next((a for a in self.anchor.anchors() if a["seq"] == seq),
                      None)
        if not anchored:
            raise TimestampError(
                "nothing_anchored",
                "there is no anchored head to timestamp"
                + (f" at sequence {seq}" if seq is not None else ""),
                "anchor the chain first: a token over a head nobody wrote "
                "outside the database attests to a hash nothing can later be "
                "compared against")
        held = self._held(anchored["seq"])
        if held:
            logger.info("chain head at seq %d is already timestamped",
                        anchored["seq"])
            return {**self.read(anchored["seq"]), "written": 0}

        digest = anchored["chain_hash"]
        token = self.authority.stamp(digest)
        moment = now if now is not None else time.time()
        record = {
            "seq": anchored["seq"], "chain_hash": digest,
            "algorithm": ALGORITHM,
            "authority": getattr(self.authority, "name", "unnamed"),
            "token": token,
            # When MAYA asked, which is NOT when the authority attests. The two
            # are kept apart because the gap between them is the only thing a
            # reader can use to notice a token that was issued somewhere else.
            "requested_at": moment, "requested_by": actor,
        }
        self.anchor.store.put(
            self.NAME.format(seq=anchored["seq"]),
            json.dumps(record, sort_keys=True).encode("utf-8"))
        if self.evidence is not None:
            self.evidence.append(
                "chain_head_timestamped", "evidence_chain", digest,
                {"seq": anchored["seq"], "authority": record["authority"],
                 "requested_at": moment}, actor=actor)
        logger.info("chain head at seq %d timestamped by %s", anchored["seq"],
                    record["authority"])
        return {**self.read(anchored["seq"]), "written": 1}

    # ------------------------------------------------------------------- read
    def read(self, seq: int) -> Dict[str, Any]:
        """One token, and what can honestly be said about it."""
        held = self._held(seq)
        if not held:
            return {"seq": seq, "state": ABSENT, "token": None,
                    "detail": ("no token covers this head. Reported as absent "
                               "rather than as untimed: the head exists and "
                               "its time is the firm's own clock")}
        checked = self._verify(held)
        return {**held, **checked, "detail": self._detail(held, checked)}

    def _held(self, seq: int) -> Optional[Dict[str, Any]]:
        name = self.NAME.format(seq=seq)
        if not self.anchor.store.exists(name):
            return None
        return json.loads(self.anchor.store.get(name).decode("utf-8"))

    def _verify(self, held: Dict[str, Any]) -> Dict[str, Any]:
        if self.verifier is None:
            return {"state": UNVERIFIED, "attested_at": None,
                    "why": ("a token is held and no verifier is wired. "
                            "Checking an RFC 3161 token means holding the "
                            "authority's certificate chain and deciding which "
                            "roots to trust — a decision this firm's security "
                            "function has already made, and one MAYA will not "
                            "make on its behalf")}
        answer = self.verifier.verify(held["token"], held["chain_hash"])
        return {
            "state": VERIFIED if answer.get("valid") else UNVERIFIED,
            "attested_at": answer.get("at"),
            "why": answer.get("why") or "",
        }

    @staticmethod
    def _detail(held: Dict[str, Any], checked: Dict[str, Any]) -> str:
        out = (f"a token over chain head {held['chain_hash'][:19]} from "
               f"{held['authority']}, {checked['state']}")
        if checked["state"] == VERIFIED and checked.get("attested_at"):
            out += (f". It attests that this head existed no later than "
                    f"{_when(checked['attested_at'])} — which is the bound that "
                    f"stops a record being reconstructed after the fact and "
                    f"called old. It does **not** say the head existed no "
                    f"earlier, it says nothing about a record deleted before "
                    f"any token was taken, and it cannot see behind the first "
                    f"one")
        elif checked["state"] == UNVERIFIED:
            out += f". {checked['why']}"
        return out

    # ----------------------------------------------------------------- estate
    def coverage(self, now: Optional[float] = None) -> Dict[str, Any]:
        """How much of the chain has a time somebody else will stand behind."""
        moment = now if now is not None else time.time()
        anchors = self.anchor.anchors()
        rows = [self.read(a["seq"]) for a in anchors]
        by_state: Dict[str, int] = {}
        for row in rows:
            by_state[row["state"]] = by_state.get(row["state"], 0) + 1
        stamped = [r for r in rows if r["state"] != ABSENT]
        earliest = min((r["seq"] for r in stamped), default=None)
        return {
            "anchors": len(anchors), "timestamps": rows,
            "by_state": by_state,
            "covered": len(stamped),
            "share": round(len(stamped) / len(anchors), 3) if anchors else 0.0,
            "earliest_timestamped_seq": earliest,
            "authority_wired": self.authority is not None,
            "verifier_wired": self.verifier is not None,
            "is_the_authority": False,
            "checked_at": moment,
            "detail": self._coverage_detail(anchors, rows, stamped, earliest),
        }

    def _coverage_detail(self, anchors, rows, stamped, earliest) -> str:
        if not anchors:
            return ("nothing is anchored, so there is nothing to timestamp. "
                    "The chain's times are the firm's own clock, which is the "
                    "honest resting state and not a failure")
        if self.authority is None:
            return (f"{len(anchors)} anchored head(s) and no time stamp "
                    f"authority wired. Every timestamp in this register is a "
                    f"clock the firm controls, and a firm arguing with a "
                    f"supervisor about the order of events is arguing from its "
                    f"own clock. That is reported rather than assumed")
        out = (f"{len(stamped)} of {len(anchors)} anchored head(s) carry a "
               f"token")
        unverified = sum(1 for r in rows if r["state"] == UNVERIFIED)
        if unverified:
            out += (f", {unverified} of them unverified because no verifier is "
                    f"wired — which is a weaker claim than verified and a much "
                    f"stronger one than absent, and collapsing the three states "
                    f"into a boolean is how a token nobody could check comes to "
                    f"read as no token at all")
        if earliest is not None:
            out += (f". Nothing before sequence {earliest} is covered: a "
                    f"timestamp cannot see behind the first one, and tampering "
                    f"that happened before it leaves nothing to disagree with")
        return out

    @staticmethod
    def posture() -> Dict[str, Any]:
        """What a timestamp proves, and the two halves that are not proof."""
        return {
            "states": list(STATES),
            "algorithm": ALGORITHM,
            "is_the_authority": False, "verifies_by_default": False,
            "bounds": {
                "above": "the head existed NO LATER than the attested time. "
                         "This is the bound that stops a record being "
                         "reconstructed after the fact and called old",
                "below": "nothing. A token does not say the head existed no "
                         "earlier, so it cannot establish that a record is as "
                         "recent as somebody claims",
                "before_the_first": "nothing. Tampering before the first token "
                                    "leaves nothing to disagree with, exactly "
                                    "as with anchoring",
                "deletion": "nothing. A record destroyed before any token was "
                            "taken is invisible to this and to every other "
                            "control here",
            },
            "detail": ("MAYA is not the authority and does not verify the "
                       "token. Verifying one means holding a certificate chain "
                       "and deciding which roots to trust — a decision this "
                       "firm's security function has already made differently, "
                       "and shipping one here would be shipping that decision"),
        }


def _when(stamp: Optional[float]) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(stamp)) \
        if stamp else "unknown"
