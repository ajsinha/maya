"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The inputs the caller brings, and the guarantees that do not apply to them.

Most of a model's inputs come from the feature platform: materialised, versioned,
bitemporal, replayable. Some do not. A loan amount typed into a form, a
transaction being scored as it happens, a quantity a trader just entered — these
arrive **in the request**, and the platform has never seen them before the call
and will never see them again.

That is fine, and it is also a hole in every assurance this platform otherwise
gives. The point of this module is to make the hole **declared and visible**
rather than discovered.

**The point-in-time guarantee does not apply.** MAYA cannot say what a
request-time value *was* as at a date, because it was never stored as at
anything. A replay over a cohort containing request-time inputs re-reads the
stored features and silently substitutes nothing for these, and a replay report
that did not say so would be claiming reproducibility it does not have.

**The skew check is blind to them, and its silence is the danger.**
`FR-FEA-016` compares the value a model was trained on against the value it was
served. For a request-time input there is no offline value to compare against, so
the check finds nothing — which reads on a screen exactly like a check that found
no skew. The gap is reported as its own number.

**And the collision is the real bug.** A name that is both a request-time input
*and* a catalogued feature is the sharpest failure in the feature platform: the
model was fitted on the stored value and is served the caller's, the two are
different by construction, and nothing anywhere distinguishes them. That is
refused when the declaration is made, because by the time it shows up in
production it looks like model degradation.

Validation at serve time is the operating contract's boundary check, which
already exists and already refuses — what this adds is the **declaration** the
check needs, so that a caller-supplied value gets the same treatment as a
materialised one instead of arriving unbounded.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Sequence

from core.features.common import FeatureError
from core.log import get_logger

logger = get_logger(__name__)

#: Guarantees the feature platform gives, and whether a request-time input has
#: them. Held as data so the gap is a table somebody can read rather than a
#: paragraph somebody wrote once.
GUARANTEES: Dict[str, Dict[str, Any]] = {
    "point_in_time": {
        "holds": False,
        "why": "the value was never stored as at anything, so there is no "
               "as-at read that returns it. A replay over a cohort containing "
               "request-time inputs re-reads the stored features and "
               "substitutes nothing for these"},
    "bitemporal": {
        "holds": False,
        "why": "there is no ingest time, because there was no ingest. The two "
               "clocks that separate a future value from a late arrival do not "
               "exist for a value that arrived with the question"},
    "replayable": {
        "holds": False,
        "why": "re-running the call would need the caller's payload, which the "
               "platform does not keep — the inference log holds a keyed "
               "digest of it and deliberately not the values"},
    "skew_checkable": {
        "holds": False,
        "why": "there is no offline value to compare the served one against, "
               "so the training/serving skew check finds nothing here — which "
               "reads exactly like finding no skew, and is the reason the gap "
               "is counted separately"},
    "bounded_at_serve": {
        "holds": True,
        "why": "the operating contract's boundary check applies to a "
               "caller-supplied value exactly as it does to a materialised "
               "one, once the input is declared. That is what this declaration "
               "is for"},
    "certifiable": {
        "holds": False,
        "why": "certification is a statement about a feature's definition and "
               "its lineage, and a request-time input has neither — what it "
               "has is a bound and a contract"},
}


class RequestTimeInputs:
    """Declares what the caller supplies, and what the platform cannot promise."""

    def __init__(self, registry, features, skew=None):
        self.registry, self.features = registry, features
        self.skew = skew

    # --------------------------------------------------------------- declare
    def declare(self, urn: str, semver: str) -> Dict[str, Any]:
        """Which of a version's declared inputs arrive in the request.

        Derived from the version's own `input_schema`: a field marked
        `at_request` there is one the caller brings. Declared in the contract
        rather than configured beside it, because an input list that can drift
        from the schema is one that will.
        """
        version = self.registry.version(urn, semver)
        if version is None:
            raise FeatureError(f"{urn} has no version {semver}")
        fields = [f for f in (version.get("input_schema") or [])
                  if isinstance(f, dict) and f.get("name")]
        at_request = [f for f in fields if f.get("at_request")]
        collisions = self._collisions(at_request)
        if collisions:
            raise FeatureError(
                "these inputs are declared at request time AND exist in the "
                "feature catalogue: " + ", ".join(collisions) + ". The model "
                "was fitted on the stored value and would be served the "
                "caller's, the two are different by construction, and nothing "
                "anywhere distinguishes them — by the time it shows up in "
                "production it looks like model degradation. Rename the "
                "request-time input, or bind the slot to the catalogued "
                "feature and stop asking the caller for it")
        return self.posture(urn, semver)

    def _collisions(self, at_request: Sequence[Dict[str, Any]]) -> List[str]:
        """Names that are both caller-supplied and catalogued."""
        out = []
        for field in at_request:
            if self.features.catalogue.get(field["name"]):
                out.append(field["name"])
        return sorted(out)

    # --------------------------------------------------------------- posture
    def posture(self, urn: str, semver: str) -> Dict[str, Any]:
        """What arrives in the request, and what cannot be promised about it."""
        version = self.registry.version(urn, semver)
        if version is None:
            raise FeatureError(f"{urn} has no version {semver}")
        fields = [f for f in (version.get("input_schema") or [])
                  if isinstance(f, dict) and f.get("name")]
        at_request = [f for f in fields if f.get("at_request")]
        unbounded = [f["name"] for f in at_request
                     if f.get("minimum") is None and f.get("maximum") is None
                     and not f.get("enum")]
        return {
            "urn": urn, "semver": semver,
            "inputs": len(fields),
            "at_request": [{"name": f["name"], "dtype": f.get("dtype") or "",
                            "minimum": f.get("minimum"),
                            "maximum": f.get("maximum"),
                            "enum": list(f.get("enum") or []),
                            "bounded": not (f.get("minimum") is None
                                            and f.get("maximum") is None
                                            and not f.get("enum"))}
                           for f in at_request],
            "count": len(at_request),
            "share": (round(len(at_request) / len(fields), 3) if fields
                      else 0.0),
            "unbounded": unbounded,
            "guarantees": {k: dict(v) for k, v in GUARANTEES.items()},
            "detail": self._posture_detail(fields, at_request, unbounded),
        }

    @staticmethod
    def _posture_detail(fields, at_request, unbounded) -> str:
        if not at_request:
            return ("every input this version declares comes from the feature "
                    "platform, so every guarantee it gives applies: "
                    "point-in-time, bitemporal, replayable, skew-checkable")
        out = (f"{len(at_request)} of {len(fields)} input(s) arrive in the "
               f"request. **The point-in-time guarantee does not apply to "
               f"them**, they carry no ingest time, a replay cannot reproduce "
               f"them, and the training/serving skew check is blind to them — "
               f"which reads on a screen exactly like finding no skew, and is "
               f"why the gap is counted rather than left to be inferred")
        if unbounded:
            out += (f". {len(unbounded)} of them — {', '.join(unbounded)} — "
                    f"declare no bound at all, so the operating contract's "
                    f"boundary check has nothing to refuse against and a "
                    f"caller may send anything")
        return out

    # ---------------------------------------------------------------- verify
    def check(self, urn: str, semver: str,
              payload: Dict[str, Any]) -> Dict[str, Any]:
        """Judge one request's caller-supplied values against the declaration.

        Every violation is reported rather than the first: a caller told about
        one bad field fixes it, retries, and is told about the next.
        """
        posture = self.posture(urn, semver)
        declared = {f["name"]: f for f in posture["at_request"]}
        violations, absent, unexpected = [], [], []
        for name, field in declared.items():
            if name not in payload:
                absent.append(name)
                continue
            violations += _violations(name, payload[name], field)
        for name in payload:
            if name not in declared:
                unexpected.append(name)
        return {
            "urn": urn, "semver": semver,
            "checked": len(declared), "violations": violations,
            "absent": sorted(absent), "unexpected": sorted(unexpected),
            "admissible": not violations and not absent,
            "detail": self._check_detail(declared, violations, absent,
                                         unexpected),
        }

    @staticmethod
    def _check_detail(declared, violations, absent, unexpected) -> str:
        if not declared:
            return ("this version declares no request-time input, so a payload "
                    "supplies nothing the contract knows about")
        if not violations and not absent and not unexpected:
            return (f"all {len(declared)} caller-supplied value(s) are inside "
                    f"the declared bounds")
        out = ""
        if absent:
            out += (f"{len(absent)} declared input(s) are missing from the "
                    f"payload: {', '.join(absent)}. A missing request-time "
                    f"value is not a null — nothing stored it, so there is "
                    f"nothing to fall back to")
        if violations:
            out += ((". " if out else "")
                    + f"{len(violations)} value(s) fall outside the contract: "
                    + "; ".join(v["why"] for v in violations)
                    + ". Every one is named rather than the first, because a "
                      "caller told about one fixes it, retries and is told "
                      "about the next")
        if unexpected:
            out += ((". " if out else "")
                    + f"{len(unexpected)} field(s) in the payload are not "
                    f"declared: {', '.join(unexpected)}. Reported and not "
                    f"refused — an undeclared field is ignored by the model, "
                    f"and refusing it would break a caller who sends a "
                    f"superset for two models")
        return out

    # ----------------------------------------------------------------- estate
    def across_the_estate(self, now: Optional[float] = None) -> Dict[str, Any]:
        """Every version with a caller-supplied input, most exposed first."""
        moment = now if now is not None else time.time()
        rows = []
        for model in self.registry.list():
            for version in self.registry.versions(model["urn"]):
                out = self.posture(model["urn"], version["semver"])
                if out["count"]:
                    rows.append(out)
        rows.sort(key=lambda r: (-r["share"], -len(r["unbounded"])))
        unbounded = [r for r in rows if r["unbounded"]]
        return {
            "versions": rows, "count": len(rows),
            "with_unbounded_inputs": [f"{r['urn']}@{r['semver']}"
                                      for r in unbounded],
            "checked_at": moment,
            "detail": (
                f"{len(rows)} version(s) read at least one value the caller "
                f"brings, and no point-in-time, bitemporal, replay or skew "
                f"guarantee reaches those values"
                + (f". {len(unbounded)} carry an input with no declared bound, "
                   f"so the contract's boundary check has nothing to refuse "
                   f"against" if unbounded else "")
                if rows else
                "every input of every version comes from the feature platform, "
                "which is unusual and worth checking rather than assuming: an "
                "input nobody marked `at_request` is treated as materialised"),
        }

    @staticmethod
    def guarantees() -> Dict[str, Any]:
        """What the platform promises about a stored value and not a sent one."""
        return {
            "guarantees": [{"guarantee": k, **v} for k, v in GUARANTEES.items()],
            "detail": ("a request-time input is fine and is also a hole in "
                       "every assurance this platform otherwise gives. The "
                       "point of declaring one is that the hole is visible "
                       "rather than discovered"),
        }


def _violations(name: str, value: Any, field: Dict[str, Any]) -> List[Dict]:
    out = []
    if field["enum"]:
        if value not in field["enum"]:
            out.append({"field": name, "value": value,
                        "why": f"{name}={value!r} is not one of "
                               f"{', '.join(str(v) for v in field['enum'])}"})
        return out
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        if field["minimum"] is not None or field["maximum"] is not None:
            out.append({"field": name, "value": value,
                        "why": f"{name}={value!r} is not a number, and this "
                               f"input carries a numeric bound"})
        return out
    if field["minimum"] is not None and value < field["minimum"]:
        out.append({"field": name, "value": value,
                    "why": f"{name}={value} is below the declared minimum "
                           f"{field['minimum']}"})
    if field["maximum"] is not None and value > field["maximum"]:
        out.append({"field": name, "value": value,
                    "why": f"{name}={value} is above the declared maximum "
                           f"{field['maximum']}"})
    return out
