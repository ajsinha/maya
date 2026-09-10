"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Two versions of one model, side by side.

`L-7` and `L-12` already decide whether an alias *may* move: contracts refine,
inputs are contravariant, outputs covariant. That is a **yes with a reason**,
and it is the right thing to gate a promotion on. It is not what somebody
approving the change needs to read. *Is this legal* and *what changed* are
different questions, and a boolean cannot be turned back into the second one.

**The most useful output is what did NOT change.** A version whose contract,
schemas, parameters and measurements are all identical and whose artifact digest
moved is a **rebuild** — the same model compiled again — and that is a
completely different governance question from a re-fit on new data, which is
different again from a re-specification. Those three arrive at a reviewer
looking identical: a new semver, a new digest, an approval request. Naming which
one it is, from what the register already holds, is most of the value here.

**Direction matters on the contract, and a plain diff loses it.** A tightened
assumption and a loosened one are both *changed*, and they are opposite
governance facts: tightening narrows what the model claims to handle — safe in
itself, and liable to start refusing calls that used to work — while loosening
widens the claim and needs evidence behind it. `L-7` computes exactly this, so
the direction is read off the refinement result rather than re-derived, because
two implementations of one order eventually disagree in the direction of
permitting more.

**MAYA does not run either version.** The requirement asks for *output on a
common test set*, and what this can honestly give is the measurements each
version actually recorded, on the tests they have **in common**. Where they share
no test, the answer is that they share no test — which is itself a finding worth
having. Two versions of one model measured on different things cannot be
compared, and printing a metric delta across different test sets would be worse
than printing nothing, because it looks like an answer.
"""
from __future__ import annotations

from itertools import pairwise
from typing import Any, Dict, List, Optional, Tuple

from core.registry.common import RegistryError
from core.registry.specs import contract_of, schema_of

#: The kernel facts a reader compares first. Not everything on the row: a
#: `created_at` that differs tells nobody anything, and a diff that reports
#: every field is one nobody reads twice.
KERNEL_FIELDS: Tuple[str, ...] = (
    "trainability_class", "parameter_kind", "fit_procedure", "deterministic",
)

#: The shapes a version change can take, and what each one asks of a reviewer.
#: Named because "what kind of change is this" is the question a promotion
#: queue actually turns on, and it is answerable from what is already recorded.
SHAPES: Dict[str, str] = {
    "identical": "nothing recorded about these two versions differs, including "
                 "the artifact digest. Either the same version was registered "
                 "twice or something upstream is producing duplicates",
    "rebuild": "only the artifact digest moved. The same specification, "
               "compiled again — which needs a different question asked of it "
               "than a re-fit does: not *is the model still right* but *why "
               "did the bytes change*",
    "refit": "the parameters moved and the specification did not. The same "
             "model on different data, which is the ordinary case and the one "
             "outcomes analysis is for",
    "respecification": "the contract or the schemas moved. This is a different "
                       "model wearing the same name, and the refinement result "
                       "says whether it may take over the alias",
    "reclassification": "the trainability class changed, so what this model "
                        "IS has changed — every obligation derived from the "
                        "class moves with it",
}


class VersionComparison:
    """Diffs two versions of one model out of what the register already holds."""

    def __init__(self, registry, validation=None, parameters=None,
                 attachments=None):
        self.registry = registry
        self.validation, self.parameters = validation, parameters
        self.attachments = attachments

    # -------------------------------------------------------------- compare
    def compare(self, urn: str, left: str, right: str) -> Dict[str, Any]:
        """Everything the register knows about how these two differ."""
        if left == right:
            raise RegistryError(
                f"'{left}' compared with itself is not a comparison")
        a = self.registry.version_service.require(urn, left)
        b = self.registry.version_service.require(urn, right)

        kernel = self._kernel(a, b)
        contract = self._contract(a, b)
        schemas = self._schemas(a, b)
        artifact = self._artifact(a, b)
        parameters = self._parameters(a, b)
        measurements = self._measurements(a, b)
        documents = self._documents(a, b)

        shape = self._shape(kernel, contract, schemas, artifact, parameters)
        return {
            "urn": urn, "left": left, "right": right,
            "kernel": kernel, "contract": contract, "schemas": schemas,
            "artifact": artifact, "parameters": parameters,
            "measurements": measurements, "documents": documents,
            "shape": shape, "shape_means": SHAPES[shape],
            "detail": (f"{left} to {right}: {shape}. {SHAPES[shape]}"),
        }

    # --------------------------------------------------------------- kernel
    @staticmethod
    def _kernel(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
        changed = {field: {"left": a.get(field), "right": b.get(field)}
                   for field in KERNEL_FIELDS
                   if a.get(field) != b.get(field)}
        return {
            "changed": changed, "same": not changed,
            "reclassified": "trainability_class" in changed,
            "detail": ("the kernel facts are identical" if not changed else
                       "; ".join(f"{f}: {v['left']} → {v['right']}"
                                 for f, v in changed.items())),
        }

    # ------------------------------------------------------------- contract
    @staticmethod
    def _contract(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
        """Which way each clause moved, from `L-7` rather than from a text diff.

        The refinement is computed in both directions, and the pair of answers
        is what carries the direction: right refining left means the newer
        version is a safe substitute; left refining right means it is a
        widening, and something has to justify it.
        """
        left, right = contract_of(a["contract"]), contract_of(b["contract"])
        forward = right.refines(left)      # is the new one a safe substitute?
        backward = left.refines(right)     # or did it widen?

        keys_a = {clause.get("key") for clause in
                  (a["contract"].get("assumptions") or [])}
        keys_b = {clause.get("key") for clause in
                  (b["contract"].get("assumptions") or [])}
        g_a = {clause.get("key") for clause in
               (a["contract"].get("guarantees") or [])}
        g_b = {clause.get("key") for clause in
               (b["contract"].get("guarantees") or [])}

        direction = ("unchanged" if forward.holds and backward.holds
                     else "narrowed" if forward.holds
                     else "widened" if backward.holds
                     else "incomparable")
        return {
            "refines": forward.holds, "direction": direction,
            "assumptions_added": sorted(k for k in keys_b - keys_a if k),
            "assumptions_removed": sorted(k for k in keys_a - keys_b if k),
            "guarantees_added": sorted(k for k in g_b - g_a if k),
            "guarantees_removed": sorted(k for k in g_a - g_b if k),
            "assumptions_not_weakened": list(forward.assumption_failures),
            "guarantees_not_preserved": list(forward.guarantee_failures),
            "same": direction == "unchanged",
            "detail": {
                "unchanged": "the contract is the same operating envelope",
                "narrowed": "the newer contract is a safe substitute: it "
                            "assumes no more and promises no less. It may "
                            "start refusing calls the older one accepted, "
                            "which is a caller problem rather than a model one",
                "widened": "the newer contract claims MORE than the older one "
                           "— a wider operating envelope or a stronger "
                           "promise — and something has to stand behind the "
                           "extra claim. L-7 refuses the alias move",
                "incomparable": "each contract claims something the other does "
                                "not, so neither substitutes for the other. "
                                "This is a different model, and calling it a "
                                "new version of the same one is the part worth "
                                "arguing about",
            }[direction],
        }

    # -------------------------------------------------------------- schemas
    @staticmethod
    def _schemas(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        for field in ("input_schema", "output_schema", "parameter_schema"):
            left = {f.get("name"): f.get("dtype")
                    for f in (a.get(field) or []) if isinstance(f, dict)}
            right = {f.get("name"): f.get("dtype")
                     for f in (b.get(field) or []) if isinstance(f, dict)}
            retyped = {k: {"left": left[k], "right": right[k]}
                       for k in set(left) & set(right) if left[k] != right[k]}
            out[field] = {
                "added": sorted(set(right) - set(left)),
                "removed": sorted(set(left) - set(right)),
                "retyped": retyped,
                "same": left == right,
            }
        variance = substitutable_result(a, b)
        return {**out, "variance": variance,
                "same": all(v["same"] for v in out.values()),
                "detail": variance["detail"]}

    # ------------------------------------------------------------- artifact
    @staticmethod
    def _artifact(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
        same = a.get("artifact_digest") == b.get("artifact_digest")
        return {
            "left": a.get("artifact_digest"), "right": b.get("artifact_digest"),
            "same": same,
            "detail": ("the same bytes" if same else
                       "different bytes. Which says nothing on its own — a "
                       "rebuild of identical source changes a digest — and is "
                       "the reason the shape below is derived from everything "
                       "else rather than from this"),
        }

    # ------------------------------------------------------------ parameters
    def _parameters(self, a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
        if self.parameters is None:
            return {"available": False, "same": True,
                    "detail": "no parameter register is wired into this "
                              "instance, so whether the parameters moved is "
                              "not known — which is different from their not "
                              "having moved"}
        left = self._parameter_rows(a["id"])
        right = self._parameter_rows(b["id"])
        return {
            "available": True,
            "left": left, "right": right,
            "same": ({r["digest"] for r in left} == {r["digest"] for r in right}
                     and bool(left) == bool(right)),
            "detail": (f"{len(left)} parameter set(s) against the older "
                       f"version and {len(right)} against the newer"),
        }

    def _parameter_rows(self, version_id: str) -> List[Dict[str, Any]]:
        rows = self.parameters.parameters.many(model_version_id=version_id)
        return [{"name": r.get("name"), "version": r.get("version"),
                 "kind": r.get("kind"), "provenance": r.get("provenance"),
                 "cardinality": r.get("cardinality"), "digest": r.get("digest")}
                for r in rows]

    # ---------------------------------------------------- what was measured
    def _measurements(self, a: Dict[str, Any],
                      b: Dict[str, Any]) -> Dict[str, Any]:
        """The metrics each version actually recorded, on the tests in common.

        MAYA runs neither version. *Output on a common test set* is answered
        from what was measured, and where the two share no test the answer is
        that they share no test — printing a delta across different test sets
        would be worse than printing nothing, because it looks like an answer.
        """
        if self.validation is None:
            return {"available": False, "shared": [], "detail":
                    "no validation service is wired into this instance"}
        left = self._results_for(a["id"])
        right = self._results_for(b["id"])
        shared = sorted(set(left) & set(right))
        rows = []
        for key in shared:
            was, now = left[key], right[key]
            delta = (None if was is None or now is None else now - was)
            rows.append({"test_key": key, "left": was, "right": now,
                         "delta": delta,
                         "direction": ("same" if delta in (0, None)
                                       else "up" if delta > 0 else "down")})
        return {
            "available": True, "shared": rows,
            "only_left": sorted(set(left) - set(right)),
            "only_right": sorted(set(right) - set(left)),
            "detail": (
                f"{len(rows)} test(s) were run against both versions"
                if rows else
                "these two versions share no test at all, so their measured "
                "behaviour cannot be compared. That is a finding rather than "
                "an empty section: two versions of one model measured on "
                "different things are two things nobody can put side by side"),
        }

    def _results_for(self, version_id: str) -> Dict[str, Optional[float]]:
        out: Dict[str, Optional[float]] = {}
        episodes = self.validation.validations.many(
            model_version_id=version_id)
        for episode in episodes:
            for result in self.validation.results_for(episode["id"]):
                # The latest measurement of a given test wins: an episode that
                # re-ran a test after a fix recorded both, and the older one is
                # a measurement of something that has since been changed.
                out[result["test_key"]] = result.get("value")
        return out

    # ------------------------------------------------------------ documents
    def _documents(self, a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
        if self.attachments is None:
            return {"available": False, "detail":
                    "no attachment register is wired into this instance"}
        left = {r["kind"] for r in self.attachments.for_version(a["id"])}
        right = {r["kind"] for r in self.attachments.for_version(b["id"])}
        lost = sorted(left - right)
        return {
            "available": True,
            "left": sorted(left), "right": sorted(right),
            "added": sorted(right - left), "missing": lost,
            "same": left == right,
            "detail": (
                f"the newer version has no {', '.join(lost)} on file and the "
                f"older one did, which is the shape of a version that was "
                f"registered in a hurry"
                if lost else
                "the newer version holds every kind of document the older one "
                "did"),
        }

    # ---------------------------------------------------------------- shape
    @staticmethod
    def _shape(kernel, contract, schemas, artifact, parameters) -> str:
        """Which of the five kinds of change this is.

        Ordered most-significant first, because a re-specification that also
        re-fitted is a re-specification: the reviewer's question is set by the
        largest thing that moved, not the most recent.
        """
        if kernel["reclassified"]:
            return "reclassification"
        if not contract["same"] or not schemas["same"] or kernel["changed"]:
            return "respecification"
        if parameters.get("available") and not parameters["same"]:
            return "refit"
        if not artifact["same"]:
            return "rebuild"
        return "identical"

    # --------------------------------------------------------------- listing
    def history(self, urn: str) -> Dict[str, Any]:
        """Every consecutive pair, so a reader can see the shape of the series.

        A model whose last six versions were all rebuilds is telling a different
        story from one with six re-specifications, and neither is visible from a
        list of semvers.
        """
        versions = self.registry.versions(urn)
        if len(versions) < 2:
            return {"urn": urn, "steps": [], "count": 0,
                    "detail": "this model has fewer than two versions, so "
                              "there is nothing to compare"}
        steps = []
        for older, newer in pairwise(versions):
            out = self.compare(urn, older["semver"], newer["semver"])
            steps.append({"from": older["semver"], "to": newer["semver"],
                          "shape": out["shape"],
                          "contract": out["contract"]["direction"]})
        shapes: Dict[str, int] = {}
        for step in steps:
            shapes[step["shape"]] = shapes.get(step["shape"], 0) + 1
        return {
            "urn": urn, "steps": steps, "count": len(steps),
            "by_shape": shapes,
            "detail": (f"{len(steps)} step(s): "
                       + ", ".join(f"{n} {shape}"
                                   for shape, n in sorted(shapes.items()))),
        }


def substitutable_result(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
    """`L-12` between the two versions, phrased for a reader.

    Read off the law rather than re-derived. Two implementations of one order
    eventually disagree, and they disagree in the direction of permitting more.
    """
    from core.domain import substitutable

    result = substitutable(schema_of(b.get("input_schema") or []),
                           schema_of(b.get("output_schema") or []),
                           schema_of(a.get("input_schema") or []),
                           schema_of(a.get("output_schema") or []))
    return {
        "holds": result.ok,
        "input_regressions": list(result.input_regressions),
        "output_regressions": list(result.output_regressions),
        "detail": ("the newer version accepts everything the older one did and "
                   "produces everything it promised, so it substitutes for it"
                   if result.ok else
                   "the newer version is not a substitute: "
                   + "; ".join(filter(None, [
                       f"it no longer accepts {', '.join(result.input_regressions)}"
                       if result.input_regressions else "",
                       f"it no longer produces {', '.join(result.output_regressions)}"
                       if result.output_regressions else ""]))),
    }
