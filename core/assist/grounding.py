"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The grounding gate.

A Tier B output is a set of **claims**, each carrying the evidence it rests on.
The gate verifies every citation against the evidence graph and then does the
thing that makes it a gate rather than a warning: it **removes** the claims that
failed.

Flagging them in place was considered and rejected. A document where the
unsupported sentences are marked is a document where the marks are what gets
skimmed past — and the sentence still reads as though the platform said it. The
rejected claims are kept, separately, so a reviewer can see what the model tried
to assert and could not support. That is a much more useful artifact than an
annotated draft, because it is the list of places the model was making things up.

A claim citing nothing is not grounded. Uncited prose in a governance document is
exactly the thing this gate exists to stop, however true it happens to be.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Sequence, Set, Tuple

from core.log import get_logger

logger = get_logger(__name__)


def verify_claim(claim: Dict[str, Any], known: Set[str]) -> Dict[str, Any]:
    """One claim, against the evidence that exists."""
    cited = list(claim.get("citations") or ())
    dangling = [c for c in cited if c not in known]
    if not cited:
        return {**claim, "verified": False,
                "reason": "the claim cites nothing, so nothing supports it"}
    if dangling:
        return {**claim, "verified": False,
                "reason": f"{len(dangling)} citation(s) do not resolve: "
                          f"{', '.join(dangling)}"}
    return {**claim, "verified": True,
            "reason": f"supported by {len(cited)} evidence entr"
                      f"{'y' if len(cited) == 1 else 'ies'}"}


def gate(claims: Sequence[Dict[str, Any]],
         known_evidence: Iterable[str]) -> Tuple[List[Dict[str, Any]],
                                                 List[Dict[str, Any]]]:
    """(kept, rejected). Rejected claims never reach the output."""
    known = set(known_evidence)
    checked = [verify_claim(c, known) for c in claims]
    kept = [c for c in checked if c["verified"]]
    rejected = [c for c in checked if not c["verified"]]
    if rejected:
        logger.warning("grounding gate rejected %d of %d claims",
                       len(rejected), len(checked))
    return kept, rejected


def report(kept: Sequence[Dict[str, Any]],
           rejected: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    total = len(kept) + len(rejected)
    return {
        "claims": total, "grounded": len(kept), "rejected": len(rejected),
        "grounded_fraction": (len(kept) / total) if total else 0.0,
        "passed": bool(kept) and not rejected,
        "detail": (f"{len(kept)} of {total} claims were supported"
                   + (f"; {len(rejected)} were removed from the output"
                      if rejected else "")
                   if total else "the generation made no claims"),
    }


def assemble(kept: Sequence[Dict[str, Any]]) -> str:
    """The published text: the surviving claims, in order, and nothing else."""
    return "\n\n".join(c["text"] for c in kept if c.get("text"))
