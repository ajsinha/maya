"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Probes over a declared domain, and the coverage figure that is worth having.

A probe set is the fixed list of inputs a model is asked when somebody needs to
know whether two things behave alike — a version against its predecessor, an
artifact against the one it was converted from, a challenger against a champion.
Almost every probe set in the wild was written by whoever built the model, from
rows that were lying around, and it therefore samples the **interior** of the
input domain: the ordinary cases, the ones that worked.

That is precisely the wrong sample. **The interior is where two implementations
agree.** They differ at the boundary — the value one clamps and the other
rejects, the missing field one treats as zero, the category neither was fitted
on. A probe set of ten thousand ordinary rows and no boundary case will show two
artifacts agreeing to six decimal places and tell you nothing about the case that
will break.

So probes here are **derived from the declared domain, never sampled from data**.
The operating contract already states each input's bounds; a probe set is then a
mechanical consequence of them: at each bound, one step inside, one step outside,
the missing value, the wrong type. Nothing is invented, nothing is generated, and
what a probe *is* can be read off the declaration it came from.

**MAYA proposes probes and does not run them.** Running them means running the
model, and the register does not run models — the probes go to whoever does, and
what comes back is a claim about equivalence that the register holds to a
standard. A platform that both generated the test and produced the result would
be the only witness to its own model's behaviour.

**Coverage is over the declaration, not over the data.** The question is not how
many probes there are but which declared constraints have one that exercises
them — and a declared bound with no probe at it is the finding. A thin probe set
is reported as a **deficiency in the probe set** rather than as a passing
comparison, because the two look identical in every equivalence report ever
written.
"""
from __future__ import annotations

from typing import Any, Dict, List, Sequence, Tuple

from core.assist.common import AssistError
from core.log import get_logger

logger = get_logger(__name__)

# What a probe is for. Each kind exercises a different way two implementations
# come apart, and a set missing a kind is blind to that way.
AT_BOUND, INSIDE, OUTSIDE = "at_bound", "just_inside", "just_outside"
MISSING, WRONG_TYPE, INTERIOR = "missing", "wrong_type", "interior"
KINDS: Tuple[str, ...] = (AT_BOUND, INSIDE, OUTSIDE, MISSING, WRONG_TYPE,
                          INTERIOR)

WHY: Dict[str, str] = {
    AT_BOUND: "the declared limit itself, where an inclusive and an exclusive "
              "reading of the same contract diverge",
    INSIDE: "one step inside the limit, which must be accepted by any correct "
            "implementation",
    OUTSIDE: "one step outside, where the contract's stated behaviour on "
             "violation is the thing being tested",
    MISSING: "the field absent, which one implementation reads as zero and "
             "another refuses — the commonest silent divergence there is",
    WRONG_TYPE: "a value of the wrong type, where coercion rules differ "
                "between runtimes far more than anybody expects",
    INTERIOR: "an ordinary value. Necessary, and the only kind a hand-written "
              "probe set usually has",
}

#: A step small enough to be inside the bound and large enough to survive a
#: float round trip through JSON and back. Declared rather than computed,
#: because a step derived from the range would be different in every probe set
#: and nothing downstream could compare two of them.
STEP = 1e-6

#: Below this share of the declared constraints exercised, the probe set is
#: reported as a deficiency rather than as a comparison.
THIN_BELOW = 0.8


class ProbeSets:
    """Derives probes from a version's declared domain, and grades a set."""

    def __init__(self, registry):
        self.registry = registry

    # ---------------------------------------------------------------- propose
    def propose(self, urn: str, semver: str) -> Dict[str, Any]:
        """The probe set a version's own declaration implies."""
        version = self.registry.version(urn, semver)
        if version is None:
            raise AssistError("unknown_version", f"{urn} has no version {semver}",
                              "check the semver")
        fields = _declared(version)
        if not fields:
            raise AssistError(
                "no_declared_domain",
                f"{urn}@{semver} declares no input schema and no contract "
                f"assumptions, so there is no domain to probe over",
                "declare the inputs and their bounds; a probe set sampled from "
                "data instead would exercise the interior, which is exactly "
                "where two implementations agree")
        probes: List[Dict[str, Any]] = []
        for field in fields:
            probes.extend(_probes_for(field))
        constraints = _constraints(fields)
        return {
            "urn": urn, "semver": semver,
            "fields": [f["name"] for f in fields],
            "probes": probes, "count": len(probes),
            "constraints": constraints,
            "by_kind": {k: sum(1 for p in probes if p["kind"] == k)
                        for k in KINDS if any(p["kind"] == k for p in probes)},
            "runs_them": False,
            "detail": (
                f"{len(probes)} probe(s) over {len(fields)} declared field(s), "
                f"derived from the contract and not sampled from data — the "
                f"interior is where two implementations agree, and a probe set "
                f"drawn from rows that were lying around is an interior sample "
                f"by construction. MAYA proposes these and does not run them: "
                f"running a probe means running the model, and a platform that "
                f"produced both the test and the result would be the only "
                f"witness to its own model's behaviour"),
        }

    # ----------------------------------------------------------------- grade
    def grade(self, urn: str, semver: str,
              probes: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
        """Which declared constraints a probe set exercises, and which it does not.

        Coverage is over the **declaration**, never over the probes. "We have
        four thousand probes" is not an answer to "does anything test what
        happens at the lower bound of `dscr`", and the two are routinely
        confused because only the first is easy to count.
        """
        version = self.registry.version(urn, semver)
        if version is None:
            raise AssistError("unknown_version", f"{urn} has no version {semver}",
                              "check the semver")
        fields = _declared(version)
        constraints = _constraints(fields)
        exercised = []
        for constraint in constraints:
            hits = [p for p in probes if _exercises(p, constraint, fields)]
            exercised.append({**constraint, "probes": len(hits),
                              "exercised": bool(hits)})
        covered = [c for c in exercised if c["exercised"]]
        coverage = len(covered) / len(constraints) if constraints else 0.0
        thin = coverage < THIN_BELOW
        return {
            "urn": urn, "semver": semver,
            "probes": len(probes),
            "constraints": exercised,
            "covered": len(covered), "of": len(constraints),
            "coverage": round(coverage, 3),
            "unexercised": [c["constraint"] for c in exercised
                            if not c["exercised"]],
            "thin": thin,
            "deficiency": (self._deficiency(exercised, coverage, len(probes))
                           if thin else None),
            "detail": self._grade_detail(exercised, coverage, len(probes), thin),
        }

    @staticmethod
    def _deficiency(exercised, coverage, count) -> Dict[str, Any]:
        unexercised = [c for c in exercised if not c["exercised"]]
        return {
            "kind": "thin_probe_set",
            "coverage": round(coverage, 3),
            "unexercised": [c["constraint"] for c in unexercised],
            "statement": (
                f"{len(unexercised)} declared constraint(s) have no probe "
                f"exercising them, so an equivalence result computed over this "
                f"set is silent about them. It is a deficiency in the probe "
                f"set and not a result about the model — and the two are "
                f"indistinguishable in every equivalence report ever written, "
                f"which is why this is stated rather than left to be noticed"),
        }

    @staticmethod
    def _grade_detail(exercised, coverage, count, thin) -> str:
        out = (f"{count} probe(s) exercise "
               f"{sum(1 for c in exercised if c['exercised'])} of "
               f"{len(exercised)} declared constraint(s), which is "
               f"{coverage:.0%}")
        if thin:
            out += (f" — below the {THIN_BELOW:.0%} at which a probe set stops "
                    f"being evidence. Coverage here is over the DECLARATION and "
                    f"never over the probes: 'we have four thousand probes' is "
                    f"not an answer to 'does anything test the lower bound of "
                    f"this input', and the two get confused because only the "
                    f"first is easy to count")
        else:
            out += (". Every declared constraint has something exercising it, "
                    "which is what makes an equivalence result over this set "
                    "mean anything")
        return out

    # ------------------------------------------------------------------ what
    @staticmethod
    def describe() -> Dict[str, Any]:
        return {
            "kinds": [{"kind": k, "why": WHY[k]} for k in KINDS],
            "thin_below": THIN_BELOW,
            "runs_them": False,
            "detail": ("probes are derived from the declared domain and never "
                       "sampled from data. The interior is where two "
                       "implementations agree; they come apart at the boundary "
                       "— the value one clamps and the other rejects, the "
                       "missing field one reads as zero"),
        }


# --------------------------------------------------------------- derivation
def _declared(version: Dict[str, Any]) -> List[Dict[str, Any]]:
    """One list of fields with their bounds, from the schema and the contract.

    Both, merged. The input schema says what a field *is* and the contract says
    what the model *promises about* it, and a probe set built from one of them
    misses whichever constraints live in the other.
    """
    fields: Dict[str, Dict[str, Any]] = {}
    for entry in version.get("input_schema") or []:
        if not isinstance(entry, dict) or not entry.get("name"):
            continue
        fields[entry["name"]] = {
            "name": entry["name"], "dtype": entry.get("dtype") or "",
            "minimum": entry.get("minimum"), "maximum": entry.get("maximum"),
            "enum": list(entry.get("enum") or []),
            "nullable": bool(entry.get("nullable")),
            "from": ["input_schema"]}
    contract = version.get("contract") or {}
    for entry in contract.get("assumptions") or []:
        if not isinstance(entry, dict) or not entry.get("key"):
            continue
        name = entry["key"]
        held = fields.setdefault(name, {"name": name, "dtype": "",
                                        "minimum": None, "maximum": None,
                                        "enum": [], "nullable": False,
                                        "from": []})
        for bound in ("minimum", "maximum"):
            if entry.get(bound) is not None:
                held[bound] = entry[bound]
        held["from"] = sorted(set(held["from"]) | {"contract"})
    return [fields[name] for name in sorted(fields)]


def _constraints(fields: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Every declared thing a probe could exercise, named."""
    out = []
    for field in fields:
        for bound in ("minimum", "maximum"):
            if field.get(bound) is not None:
                out.append({"constraint": f"{field['name']}.{bound}",
                            "field": field["name"], "aspect": bound,
                            "value": field[bound],
                            "declared_in": field["from"]})
        if field.get("enum"):
            out.append({"constraint": f"{field['name']}.enum",
                        "field": field["name"], "aspect": "enum",
                        "value": field["enum"],
                        "declared_in": field["from"]})
        out.append({"constraint": f"{field['name']}.presence",
                    "field": field["name"], "aspect": "presence",
                    "value": None, "declared_in": field["from"]})
        if field.get("dtype"):
            out.append({"constraint": f"{field['name']}.dtype",
                        "field": field["name"], "aspect": "dtype",
                        "value": field["dtype"],
                        "declared_in": field["from"]})
    return out


def _probes_for(field: Dict[str, Any]) -> List[Dict[str, Any]]:
    """The probes one field's declaration implies. Nothing invented."""
    name = field["name"]
    out: List[Dict[str, Any]] = []
    low, high = field.get("minimum"), field.get("maximum")

    for bound, value in (("minimum", low), ("maximum", high)):
        if value is None:
            continue
        step = STEP if bound == "minimum" else -STEP
        out.append(_probe(name, AT_BOUND, value, f"{name}.{bound}"))
        out.append(_probe(name, INSIDE, _numeric(value) + step,
                          f"{name}.{bound}"))
        out.append(_probe(name, OUTSIDE, _numeric(value) - step,
                          f"{name}.{bound}"))
    for value in field.get("enum") or []:
        out.append(_probe(name, AT_BOUND, value, f"{name}.enum"))
    if field.get("enum"):
        out.append(_probe(name, OUTSIDE, "__not_a_declared_category__",
                          f"{name}.enum"))
    out.append(_probe(name, MISSING, None, f"{name}.presence"))
    if field.get("dtype"):
        out.append(_probe(name, WRONG_TYPE, _wrong_for(field["dtype"]),
                          f"{name}.dtype"))
    if low is not None and high is not None:
        out.append(_probe(name, INTERIOR,
                          (_numeric(low) + _numeric(high)) / 2.0,
                          f"{name}.presence"))
    return out


def _probe(field: str, kind: str, value: Any, exercises: str) -> Dict[str, Any]:
    return {"field": field, "kind": kind, "value": value,
            "exercises": exercises, "why": WHY[kind]}


def _numeric(value: Any) -> float:
    text = str(value).strip()
    digits = text[1:] if text.startswith("-") else text
    return float(text) if digits.replace(".", "", 1).isdigit() else 0.0


def _wrong_for(dtype: str) -> Any:
    """A value of the wrong type for this one. Coercion rules differ between
    runtimes far more than anybody expects, which is what this is for."""
    return "not-a-number" if dtype in ("float", "int", "double", "number") \
        else 0


def _exercises(probe: Dict[str, Any], constraint: Dict[str, Any],
               fields: Sequence[Dict[str, Any]]) -> bool:
    """Whether a supplied probe touches a declared constraint.

    A probe supplied by somebody else carries no `exercises` label, so this
    decides from the value — which is the point: a caller who could assert what
    their probe covered would assert it covered everything.
    """
    field = constraint["field"]
    if probe.get("field") != field and field not in (probe.get("inputs") or {}):
        return False
    value = probe.get("value", (probe.get("inputs") or {}).get(field))
    aspect = constraint["aspect"]
    if aspect == "presence":
        return value is None or probe.get("kind") == MISSING
    if aspect == "dtype":
        declared = next((f["dtype"] for f in fields if f["name"] == field), "")
        return _is_wrong_type(value, declared)
    if aspect == "enum":
        return value is not None and not _is_number(value)
    if value is None or not _is_number(value):
        return False
    return abs(float(value) - _numeric(constraint["value"])) <= 2 * STEP


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_wrong_type(value: Any, dtype: str) -> bool:
    if not dtype:
        return False
    if dtype in ("float", "int", "double", "number"):
        return value is not None and not _is_number(value)
    return _is_number(value)
