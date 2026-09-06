"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The fibre registry and the totality gate.

`L-15`: *every class has a total evidence schema, lifecycle, metric set and
template set; no fibre is empty.* The gate runs at start-up, because a partial
fibre discovered at run time is discovered by whoever was relying on it.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from core.fibres.common import BASE, FACETS, FibreError
from core.fibres.fibre import Fibre
from core.fibres.library import library
from core.log import get_logger

logger = get_logger(__name__)


class FibreRegistry:
    """Fibres indexed by trainability class, and the law that keeps them total.

    Extension is `register()`, which is the whole point of a fibration: a new
    kind of model supplies a fibre and nothing else changes. It is also why the
    gate has to exist — an extension point with no completeness check is an
    invitation to supply half of one.
    """

    def __init__(self, fibres: Optional[Dict[str, Fibre]] = None,
                 base: tuple = BASE):
        self._fibres: Dict[str, Fibre] = dict(fibres if fibres is not None
                                              else library())
        self._base = tuple(base)

    # ------------------------------------------------------------------ read
    def of(self, trainability_class: str) -> Fibre:
        fibre = self._fibres.get(trainability_class)
        if fibre is None:
            raise FibreError(
                "no_fibre",
                f"'{trainability_class}' has no fibre, so there is nothing that "
                f"says what evidence it needs, what may be monitored on it or "
                f"what compiles for it",
                "register a fibre for the class, or use a class that has one")
        return fibre

    def get(self, trainability_class: str) -> Optional[Fibre]:
        """The lookup that does not refuse, for callers reporting rather than
        deciding."""
        return self._fibres.get(trainability_class)

    def classes(self) -> List[str]:
        return sorted(self._fibres)

    # --------------------------------------------------------------- extend
    def register(self, fibre: Fibre) -> Fibre:
        """Add a fibre. Refused if it is partial, so the registry cannot hold
        one — the gate would then only be catching what registration let in."""
        if missing := fibre.missing_facets():
            raise FibreError(
                "partial_fibre",
                f"the fibre for '{fibre.trainability_class}' is missing "
                f"{', '.join(missing)}",
                f"every fibre needs all of {', '.join(FACETS)}; a class with an "
                f"empty facet is a class the platform cannot say anything about")
        if fibre.trainability_class in self._fibres:
            raise FibreError(
                "fibre_exists",
                f"'{fibre.trainability_class}' already has a fibre",
                "fibres are replaced deliberately, not shadowed; remove it first")
        self._fibres[fibre.trainability_class] = fibre
        logger.info("registered fibre for %s (%s)",
                    fibre.trainability_class, fibre.label)
        return fibre

    # --------------------------------------------------------------- the law
    def totality(self) -> Dict[str, List[str]]:
        """Every gap, as a report rather than an exception.

        Two kinds of gap, and they are different failures: a class in the base
        with **no fibre at all**, and a fibre that exists and is **partial**.
        The first is an extension nobody finished; the second is one somebody
        started.
        """
        gaps: Dict[str, List[str]] = {}
        for name in self._base:
            fibre = self._fibres.get(name)
            if fibre is None:
                gaps[name] = ["no fibre"]
            elif missing := fibre.missing_facets():
                gaps[name] = list(missing)
        return gaps

    def verify(self) -> Dict[str, object]:
        """`L-15`, executed. Raises rather than reports, because this runs at
        start-up and a platform that boots with a partial fibre will answer
        questions about that class by omitting them."""
        gaps = self.totality()
        if gaps:
            detail = "; ".join(f"{name}: {', '.join(why)}"
                               for name, why in sorted(gaps.items()))
            logger.error("L-15 violated — the fibration is not total: %s", detail)
            raise FibreError(
                "fibration_incomplete",
                f"the fibration is not total, so L-15 does not hold: {detail}",
                "supply the missing fibres or facets before starting; a class "
                "the platform cannot describe is one it will silently skip")
        logger.info("L-15 holds: %d fibres, all total", len(self._base))
        return {"law": "L-15", "classes": len(self._base), "total": True}
