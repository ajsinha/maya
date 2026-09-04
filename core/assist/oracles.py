"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Oracles: the checks that make Tier A possible.

An oracle is a predicate that decides whether a generated artifact is correct,
mechanically, without asking the thing that generated it. That is a strong
requirement and very few tasks have one — which is the point. The list below is
short because the honest list is short.

Every oracle here is backed by machinery that already exists for another reason,
and that is not a coincidence. A platform whose properties are formal enough to
check a human's work is a platform that can check a machine's, and the same
check serves both. An oracle written specially to bless AI output would be an
oracle nobody had reason to trust.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from core.log import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class Verdict:
    passed: bool
    detail: str

    def as_dict(self) -> Dict[str, Any]:
        return {"passed": self.passed, "detail": self.detail}


@dataclass(frozen=True)
class Oracle:
    """A mechanical check on a generated artifact."""
    key: str
    what: str
    rests_on: str
    check: Callable[[Dict[str, Any]], Verdict]


# --------------------------------------------------------------------- checks
def _warrant_conforms(payload: Dict[str, Any]) -> Verdict:
    from core.execution.grammar import validate
    report = validate(payload.get("warrant") or {})
    return Verdict(report.valid, report.as_dict()["detail"])


def _contract_refines(payload: Dict[str, Any]) -> Verdict:
    from core.registry.specs import contract_of
    proposed = contract_of(payload.get("proposed") or {})
    incumbent = contract_of(payload.get("incumbent") or {})
    result = proposed.refines(incumbent)
    return Verdict(result.holds, result.reason())


def _schemas_substitutable(payload: Dict[str, Any]) -> Verdict:
    from core.domain import substitutable
    from core.registry.specs import schema_of
    result = substitutable(schema_of(payload.get("new_input")),
                           schema_of(payload.get("new_output")),
                           schema_of(payload.get("old_input")),
                           schema_of(payload.get("old_output")))
    return Verdict(result.ok, result.reason())


def _test_is_registered(payload: Dict[str, Any]) -> Verdict:
    """A generated validation test either exists in the catalogue or does not."""
    from core.validation import TestCatalogue
    catalogue = TestCatalogue()
    key = payload.get("test_key")
    if key in catalogue.keys():
        return Verdict(True, f"'{key}' is a registered test")
    return Verdict(False, f"'{key}' is not in the test catalogue")


def _citations_resolve(payload: Dict[str, Any]) -> Verdict:
    """Boolean-semiring citation soundness: every cited node exists."""
    known = set(payload.get("known_evidence") or ())
    cited = list(payload.get("citations") or ())
    dangling = [c for c in cited if c not in known]
    if not cited:
        return Verdict(False, "nothing was cited, so nothing is supported")
    return Verdict(not dangling,
                   "every citation resolves" if not dangling
                   else f"{len(dangling)} citation(s) do not resolve")


ORACLES: Dict[str, Oracle] = {
    o.key: o for o in (
        Oracle("warrant.conforms",
               "a generated warrant validates against the grammar",
               "core.execution.grammar", _warrant_conforms),
        Oracle("contract.refines",
               "a proposed contract refines the incumbent (L-7)",
               "core.domain.contracts", _contract_refines),
        Oracle("schemas.substitutable",
               "proposed schemas satisfy variance (L-12)",
               "core.domain.schemas", _schemas_substitutable),
        Oracle("test.registered",
               "a proposed validation test exists in the catalogue",
               "core.validation.catalogue", _test_is_registered),
        Oracle("citations.resolve",
               "every cited evidence node exists",
               "core.evidence", _citations_resolve),
    )
}


def get(key: str) -> Optional[Oracle]:
    return ORACLES.get(key)


def describe() -> List[Dict[str, str]]:
    """The oracles, and what each rests on. Short on purpose."""
    return [{"key": o.key, "checks": o.what, "rests_on": o.rests_on}
            for o in sorted(ORACLES.values(), key=lambda o: o.key)]
