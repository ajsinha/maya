"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

PMML scorecards and regression models, evaluated natively.

The obvious way to run PMML is to embed a JVM, and every mature PMML library
does. That is a heavy dependency for a governance platform to carry, and it puts
a second runtime between the digest we verified and the number we return.

So the two element types that cover most of a bank's PMML estate are evaluated
here directly: `RegressionModel` — the logistic and linear scorecards that credit
risk has run for forty years — and `Scorecard`, the points-based form. Both are
arithmetic over coefficients held in the XML, and the coefficients are the
deliverable: a scorecard's whole appeal is that you can read it.

Anything else is refused **by name**. A partial implementation that silently
mis-evaluates a tree ensemble would be far worse than one that says it only does
regressions.
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Dict, Optional

from core.execution.errors import WarrantError
from core.execution.runtimes.base import Invocation, resolve_path, verify_artifact
import logging

from core.log import get_logger, swallowed

logger = get_logger(__name__)

SUPPORTED = ("RegressionModel", "Scorecard")

# PMML normalisation methods this evaluator implements.
NORMALISATION = {
    "none": lambda y: y,
    "softmax": lambda y: 1.0 / (1.0 + math.exp(-y)),   # binary logistic
    "logit": lambda y: 1.0 / (1.0 + math.exp(-y)),
    "exp": math.exp,
}


class PmmlRuntime:
    """Evaluates the regression and scorecard subset of PMML, without a JVM."""

    key = "pmml"

    def __init__(self, artifact_dir: Optional[Path] = None):
        self.artifact_dir = Path(artifact_dir) if artifact_dir else None
        self._parsed: Dict[str, Dict[str, Any]] = {}

    def available(self) -> Optional[str]:
        try:
            from lxml import etree
        except ImportError as exc:
            swallowed(logger, exc, "the pmml runtime is not usable here",
                      detail="warrants naming it will be refused with the reason",
                      level=logging.DEBUG)
            return f"lxml is not installed ({exc}); pip install lxml"
        return None

    def invoke(self, call: Invocation) -> Any:
        if (why := self.available()):
            raise WarrantError("runtime_unavailable", why, "install the package")
        path = resolve_path(call, self.artifact_dir)
        digest = call.artifact.get("digest")
        verify_artifact(path, digest)
        model = self._parse(path, digest)
        return self._evaluate(model, call)

    # ------------------------------------------------------------------ parse
    def _parse(self, path: Path, digest: str) -> Dict[str, Any]:
        if digest in self._parsed:
            return self._parsed[digest]
        from lxml import etree

        tree = etree.parse(str(path))
        root = tree.getroot()
        ns = {"p": root.nsmap.get(None, "http://www.dmg.org/PMML-4_4")}

        for kind in SUPPORTED:
            found = root.find(f".//p:{kind}", ns)
            if found is not None:
                parsed = (self._regression(found, ns) if kind == "RegressionModel"
                          else self._scorecard(found, ns))
                parsed["kind"] = kind
                self._parsed[digest] = parsed
                logger.info("parsed PMML %s from %s", kind, path.name)
                return parsed

        present = {etree.QName(e).localname for e in root} - {"Header", "DataDictionary"}
        raise WarrantError(
            "pmml_unsupported",
            f"this evaluator implements {' and '.join(SUPPORTED)}; the document "
            f"contains {', '.join(sorted(present)) or 'no recognised model'}",
            "use an engine with a full PMML implementation for this model, or "
            "export it as ONNX")

    @staticmethod
    def _regression(node, ns) -> Dict[str, Any]:
        table = node.find("p:RegressionTable", ns)
        if table is None:
            raise WarrantError("pmml_malformed",
                               "the RegressionModel has no RegressionTable", "")
        return {
            "intercept": float(table.get("intercept", "0")),
            "coefficients": {p.get("name"): float(p.get("coefficient"))
                             for p in table.findall("p:NumericPredictor", ns)},
            "categorical": [(p.get("name"), p.get("value"),
                             float(p.get("coefficient")))
                            for p in table.findall("p:CategoricalPredictor", ns)],
            "normalisation": node.get("normalizationMethod", "none"),
        }

    @staticmethod
    def _scorecard(node, ns) -> Dict[str, Any]:
        characteristics = []
        for ch in node.findall(".//p:Characteristic", ns):
            attributes = []
            for attr in ch.findall("p:Attribute", ns):
                points = float(attr.get("partialScore", "0"))
                predicate = attr.find("p:SimplePredicate", ns)
                attributes.append({
                    "points": points,
                    "field": predicate.get("field") if predicate is not None else None,
                    "operator": predicate.get("operator") if predicate is not None else None,
                    "value": predicate.get("value") if predicate is not None else None,
                })
            characteristics.append({"name": ch.get("name"), "attributes": attributes})
        return {"initial_score": float(node.get("initialScore", "0")),
                "characteristics": characteristics}

    # --------------------------------------------------------------- evaluate
    def _evaluate(self, model: Dict[str, Any], call: Invocation) -> Any:
        value = (self._eval_regression(model, call.inputs)
                 if model["kind"] == "RegressionModel"
                 else self._eval_scorecard(model, call.inputs))
        names = call.output_names
        return {names[0]: value} if names else value

    @staticmethod
    def _eval_regression(model: Dict[str, Any], inputs: Dict[str, Any]) -> float:
        missing = [f for f in model["coefficients"] if f not in inputs]
        if missing:
            raise WarrantError(
                "missing_inputs",
                f"the scorecard needs {', '.join(missing)}",
                "supply every field the regression table names")
        total = model["intercept"]
        for field, coefficient in model["coefficients"].items():
            total += coefficient * float(inputs[field])
        for field, expected, coefficient in model["categorical"]:
            if str(inputs.get(field)) == expected:
                total += coefficient
        method = model["normalisation"]
        if method not in NORMALISATION:
            raise WarrantError(
                "pmml_unsupported",
                f"normalisation method '{method}' is not implemented",
                f"implemented methods are {', '.join(NORMALISATION)}")
        return NORMALISATION[method](total)

    @staticmethod
    def _eval_scorecard(model: Dict[str, Any], inputs: Dict[str, Any]) -> float:
        score = model["initial_score"]
        for characteristic in model["characteristics"]:
            for attribute in characteristic["attributes"]:
                if _matches(attribute, inputs):
                    score += attribute["points"]
                    break              # first matching band wins, as PMML says
        return score


_OPERATORS = {
    "lessThan": lambda a, b: a < b,
    "lessOrEqual": lambda a, b: a <= b,
    "greaterThan": lambda a, b: a > b,
    "greaterOrEqual": lambda a, b: a >= b,
    "equal": lambda a, b: a == b,
    "notEqual": lambda a, b: a != b,
}


def _matches(attribute: Dict[str, Any], inputs: Dict[str, Any]) -> bool:
    field, operator = attribute["field"], attribute["operator"]
    if field is None:
        return True                    # an unconditioned catch-all band
    if field not in inputs:
        raise WarrantError("missing_inputs", f"the scorecard needs {field}",
                           "supply every field the characteristics name")
    compare = _OPERATORS.get(operator)
    if compare is None:
        raise WarrantError(
            "pmml_unsupported", f"predicate operator '{operator}' is not implemented",
            f"implemented operators are {', '.join(_OPERATORS)}")
    try:
        return compare(float(inputs[field]), float(attribute["value"]))
    except (TypeError, ValueError) as exc:
        # A categorical band: PMML does not distinguish, so fall back to string
        # comparison rather than guessing the field's type from the schema.
        swallowed(logger, exc, f"predicate on '{field}' is not numeric",
                  detail="comparing as strings", level=logging.DEBUG)
        return compare(str(inputs[field]), str(attribute["value"]))
