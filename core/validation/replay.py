"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Reproducibility replay.

A validation result is a claim about a computation. Replay is the only thing
that turns it back into one: given the same data, the same test, and the same
parameters, does the same number come out?

The comparison is on the recorded digest, which covers the test key, the value,
the threshold, the parameters and the slice. So a replay catches more than a
changed number — it catches a threshold that moved after the fact, and a slice
definition that drifted, both of which leave the value intact and the conclusion
wrong.

A test whose data cannot be supplied is reported as **skipped**, never as
reproduced. The difference matters: "we checked and it matched" and "we could
not check" are opposite findings, and a replay report that blurs them is worse
than no replay at all.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from core.validation.catalogue import TestCatalogue
from core.validation.service import ValidationService

# Given (test_key, slice) return the two aligned series, or None if unavailable.
DataProvider = Callable[[str, Dict[str, Any]], Optional[Tuple[Sequence, Sequence]]]


class Replayer:
    """Recomputes a validation's tests and compares them against what was stored."""

    def __init__(self, validations: ValidationService, catalogue: TestCatalogue):
        self.validations, self.catalogue = validations, catalogue

    def replay(self, validation_id: str, provider: DataProvider) -> Dict[str, Any]:
        stored = self.validations.results_for(validation_id)
        reproduced: List[Dict[str, Any]] = []
        mismatched: List[Dict[str, Any]] = []
        skipped: List[Dict[str, Any]] = []

        for row in stored:
            data = provider(row["test_key"], row["slice"])
            if data is None:
                skipped.append({"test_key": row["test_key"], "slice": row["slice"],
                                "reason": "no data supplied for this test and slice"})
                continue
            left, right = data
            again = self.catalogue.run(row["test_key"], left, right, row["threshold"],
                                       row["parameters"], row["slice"])
            record = {"test_key": row["test_key"], "slice": row["slice"],
                      "stored_value": row["value"], "replayed_value": again.value,
                      "stored_digest": row["digest"], "replayed_digest": again.digest()}
            (reproduced if again.digest() == row["digest"] else mismatched).append(record)

        return self.report(validation_id, len(stored), reproduced, mismatched, skipped)

    @staticmethod
    def report(validation_id: str, total: int, reproduced: List, mismatched: List,
               skipped: List) -> Dict[str, Any]:
        """A replay is reproducible only if everything was checked and matched."""
        ok = not mismatched and not skipped and total > 0
        if total == 0:
            detail = "no results to replay"
        elif ok:
            detail = f"all {total} result(s) reproduced exactly"
        else:
            parts = []
            if mismatched:
                parts.append(f"{len(mismatched)} differed "
                             f"({', '.join(sorted({m['test_key'] for m in mismatched}))})")
            if skipped:
                parts.append(f"{len(skipped)} could not be checked")
            detail = "; ".join(parts)
        return {"validation_id": validation_id, "reproducible": ok, "total": total,
                "reproduced": len(reproduced), "mismatched": mismatched,
                "skipped": skipped, "detail": detail}
