"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

How long each kind of thing is kept, and where it has to live.

**Retention is per artifact class because the obligations are.** AI Act Art. 19
asks for logs over the system's lifetime; SOX asks seven years of what supported
a financial statement; data protection asks that personal data be held for *less*
time, not more. A single estate-wide number satisfies whichever of those is
loudest and quietly breaks the others, so the classes are separate and each one
names the obligation it comes from.

**A WORM option is a claim about where something is stored, not a flag on a
row.** `core/evidence/worm.py` says so about itself in its own docstring: a
directory with the permission bit cleared is an honest limit, not immutable
storage, because whoever can clear it can set it again. So a class declares the
backing it **requires**, the platform reports the backing it **has**, and where
those differ it says so rather than showing a tick. A register that reports
compliance with a WORM requirement because somebody selected WORM from a dropdown
is worse than one with no such field, because the tick is what stops anybody
asking.

**Retention is a floor, never a ceiling.** Nothing here deletes on the day a
period ends; a period says how long something must be kept, and deleting is a
separate act with its own control (`core/execution/inference.py` is the one place
that does it, because its content is somebody else's personal data). Confusing
*may now be deleted* with *must now be deleted* is how a register loses the
record that was about to be asked for.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

YEAR = 365.25 * 86400.0

#: Storage backings, weakest first. `filesystem` is where most of this actually
#: lives and it is not WORM — saying so is the point.
FILESYSTEM, OBJECT_LOCK, EXTERNAL = "filesystem", "object_lock", "external_worm"

#: Each class of thing this register keeps: how long, why that long, and what
#: the obligation requires it be stored on. `requires_worm` is a requirement,
#: not a description of what is in place.
CLASSES: Dict[str, Dict[str, Any]] = {
    "evidence_chain": {
        "years": 10.0,
        "because": "AI Act Art. 19 asks for logs over the system's lifetime, "
                   "and the chain is what makes every other record verifiable. "
                   "It is append-only, so a retention period here is a floor "
                   "and nothing has a mechanism to reach it",
        "requires_worm": True,
    },
    "model_record": {
        "years": 10.0,
        "because": "a model's record outlives the model. The question asked "
                   "after a decision is challenged is what the register said "
                   "at the time, which is answerable for as long as the record "
                   "and the chain are both there",
        "requires_worm": False,
    },
    "artifact": {
        "years": 7.0,
        "because": "SOX, for anything that supported a financial statement — "
                   "and an artifact whose bytes are gone cannot be re-run "
                   "against the claim somebody made about it",
        "requires_worm": True,
    },
    "validation": {
        "years": 7.0,
        "because": "the report and the measurements behind it are what a "
                   "supervisor asks for, and asking is not usually prompt",
        "requires_worm": False,
    },
    "attachment": {
        "years": 7.0,
        "because": "documents filed against a model are the firm's own account "
                   "of it, and the account has to outlast the people who wrote "
                   "it",
        "requires_worm": False,
    },
    "inference": {
        "years": 1.0,
        "because": "the SHORTEST period here, because this is the only class "
                   "whose content is somebody else's personal data — and it is "
                   "the one class where the period is enforced by deletion "
                   "rather than by keeping. Its per-classification schedule is "
                   "in core/execution/inference.py and is tighter still",
        "requires_worm": False,
    },
    "telemetry": {
        "years": 2.0,
        "because": "enough to show a trend across two annual reviews, and not "
                   "so much that a volume problem becomes a retention problem",
        "requires_worm": False,
    },
}


def retention_of(artifact_class: str) -> float:
    """How long this class is kept, in seconds."""
    spec = CLASSES.get(artifact_class)
    return (spec["years"] if spec else 7.0) * YEAR


def backing_of(artifact_class: str) -> bool:
    """Whether this class's obligation requires immutable storage."""
    spec = CLASSES.get(artifact_class)
    return bool(spec and spec["requires_worm"])


class RetentionSchedule:
    """States the schedule, and says where the backing does not meet it."""

    def __init__(self, worm=None, holds=None):
        # The WORM port, if one is configured. `None` means nothing immutable
        # is wired in, which is reported rather than treated as compliance.
        self.worm, self.holds = worm, holds

    def describe(self, now: Optional[float] = None) -> Dict[str, Any]:
        """Every class, its period, and whether the backing meets it."""
        actual = self.backing()
        rows = []
        for name, spec in CLASSES.items():
            met = (not spec["requires_worm"]) or actual == EXTERNAL
            rows.append({
                "artifact_class": name, "years": spec["years"],
                "because": spec["because"],
                "requires_worm": spec["requires_worm"],
                "backing": actual, "requirement_met": met,
            })
        unmet = [r for r in rows if not r["requirement_met"]]
        held = self.holds.active() if self.holds is not None else []
        return {
            "classes": rows, "backing": actual,
            "requirements_not_met": [r["artifact_class"] for r in unmet],
            "active_holds": len(held),
            "detail": self._detail(rows, unmet, actual, held),
        }

    def backing(self) -> str:
        """What this instance's immutable storage actually is.

        A directory with the permission bit cleared is not immutable storage —
        `core/evidence/worm.py` says so about itself — because whoever can clear
        the bit can set it again. Reporting that as WORM because somebody chose
        WORM from a dropdown is worse than having no such field, since the tick
        is what stops anybody asking.
        """
        if self.worm is None:
            return FILESYSTEM
        return getattr(self.worm, "backing", FILESYSTEM)

    @staticmethod
    def _detail(rows, unmet, actual, held) -> str:
        out = f"{len(rows)} artifact class(es) with a stated retention period"
        if unmet:
            out += (f". {len(unmet)} require immutable storage and this "
                    f"instance's backing is '{actual}', which is not — a "
                    f"directory with the permission bit cleared is an honest "
                    f"limit and not WORM, because whoever can clear the bit "
                    f"can set it again. Reporting compliance here because "
                    f"somebody chose it from a dropdown is worse than having "
                    f"no field at all")
        else:
            out += f". The backing is '{actual}', which meets every requirement"
        if held:
            out += (f". {len(held)} legal hold(s) are in force and override "
                    f"every period above, which is the one direction this "
                    f"platform lets a control be overridden")
        out += (". A period is a FLOOR: it says how long something must be "
                "kept, not when it must go. Confusing *may now be deleted* "
                "with *must now be deleted* is how a register loses the record "
                "that was about to be asked for")
        return out

    def periods(self) -> Dict[str, float]:
        """The schedule as a plain mapping, for anything that enforces it."""
        return {name: spec["years"] * YEAR for name, spec in CLASSES.items()}
