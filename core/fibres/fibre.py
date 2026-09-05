"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

One fibre: everything that varies with the trainability class, in one place.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

from core.fibres.common import FACETS


@dataclass(frozen=True)
class Fibre:
    """The fibre over one trainability class.

    Frozen, because a fibre that can be edited at run time is a governance rule
    that can be edited at run time.

    The three prose fields are not decoration. `soundness`, `outcomes` and
    `answers` are what a validator is *entitled to ask for* in this class, and
    asking a T0 pricer for out-of-sample discrimination is not rigour — it is a
    category error that wastes a review cycle and teaches everybody that the
    checklist is noise. They are carried here so the document compiler and the
    validation scoper read one source rather than each carrying an opinion.
    """

    trainability_class: str
    label: str

    # --- the four facets L-15 names -----------------------------------------
    #: Attachment kinds this class must hold before its evidence is complete.
    evidence: Tuple[str, ...]
    #: Lifecycle states a model of this class may occupy.
    lifecycle: Tuple[str, ...]
    #: Monitor kinds that can answer a question about this class.
    metrics: Tuple[str, ...]
    #: Document kinds that compile for this class.
    templates: Tuple[str, ...]

    # --- what the facets are *for*, per `docs/02 §5` -------------------------
    soundness: str
    outcomes: str
    answers: str

    def missing_facets(self) -> Tuple[str, ...]:
        """Which of the four are empty. The totality check, for one fibre."""
        return tuple(f for f in FACETS if not getattr(self, f))

    @property
    def is_total(self) -> bool:
        return not self.missing_facets()

    def admits_monitor(self, kind: str) -> bool:
        return kind in self.metrics

    def admits_document(self, kind: str) -> bool:
        return kind in self.templates

    def requires_evidence(self, kind: str) -> bool:
        return kind in self.evidence
