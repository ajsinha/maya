"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The runtime where the JSON **is** the model.

Every other runtime here names something else — a graph, an image, a script, a
document — and MAYA governs the naming. This one does not: the kernel's
`entry.expression` is the whole of `f`, written in the expression language the
platform already parses for derived features, and there is no artifact to
locate, no digest to trust and no engine to ask.

That closes a gap the taxonomy had. A scorecard, a logistic link, a
loss-given-default haircut, a Basel risk weight — the small closed-form models a
bank has hundreds of — had to be registered as `descriptor_only` (governed and
unrunnable) or wrapped in a container to be executed at all, which turns four
lines of arithmetic into an artifact somebody has to build, sign and store.

**What this deliberately is not.** The language has no window, no lag, no
recursion and no library. A moving average is not expressible; neither is
anything needing state. That boundary is the same one `core/features/expressions`
draws and for the same reason: MAYA transforms values it holds, and the moment
it would need to run somebody's code the answer is a different runtime.

`P` is inhabited the ordinary way. An expression naming only its inputs is `T0`
— terminal parameter object, nothing to fit. One naming coefficients is `T2` and
the coefficients arrive as an approved parameter set, exactly as they do for
`estimator`; the expression says how they are combined and the parameter set
says what they are.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from core.execution.errors import WarrantError
from core.execution.runtimes.base import Invocation
from core.features.common import FeatureError
from core.features.expressions import Expression
from core.log import get_logger

logger = get_logger(__name__)


class FormulaRuntime:
    """Evaluates a closed-form expression carried by the version itself."""

    key = "formula"

    def available(self) -> Optional[str]:
        """Always. The parser is this repository's own and has no dependency to
        be missing, which is most of the argument for a runtime like this one:
        it cannot fail to be installed."""
        return None

    def invoke(self, call: Invocation) -> Any:
        entry = (call.warrant.get("operation") or {}).get("entry") or {}
        source = entry.get("expression")
        if not source:
            raise WarrantError(
                "no_expression",
                "a formula warrant carries no expression, so there is nothing "
                "to evaluate",
                "declare `entry: {\"expression\": \"…\"}` on the version's "
                "kernel")

        row: Dict[str, Any] = dict((call.inputs or {}).get("features") or {})
        # Coefficients enter by the same door as features and are named in the
        # same expression. Ordering is deliberate: a parameter may not be
        # overwritten by an input of the same name, or a caller could supply
        # their own coefficient and the warrant would still say the model ran
        # at its approved point of `P`.
        parameters = (call.inputs or {}).get("parameters") or {}
        values = parameters.get("values") if isinstance(parameters, dict) else None
        overridden = sorted(set(row) & set(values or {}))
        if overridden:
            raise WarrantError(
                "parameter_overridden",
                f"the inputs supply {', '.join(overridden)}, which this "
                f"version's approved parameter set also supplies",
                "a caller who can set a coefficient is choosing the model; "
                "rename the input, or record a parameter set that does not "
                "name it")
        row.update(values or {})

        try:
            expression = Expression(source)
        except FeatureError as exc:
            # Not recovered from. A stored expression that no longer parses
            # means the register holds a version its own checks would refuse,
            # and evaluating the part that still parses would be answering with
            # half a model.
            logger.error("an approved formula failed to parse at execution: %s",
                         exc)
            raise WarrantError(
                "malformed_expression",
                f"this version's expression does not parse: {exc}",
                "the version is immutable, so this is a defect in what was "
                "registered; create a corrected version") from exc

        missing = sorted(set(expression.feature_names()) - set(row))
        if missing:
            raise WarrantError(
                "missing_inputs",
                f"the expression reads {', '.join(missing)}, and the call "
                f"supplied neither an input nor a parameter of that name",
                "supply every field the version's input_schema declares")

        target = entry.get("target") or "value"
        return {"family": "formula", "target": target,
                "prediction": expression.evaluate(row)}
