"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Comparing the runs, and saying whether any of them could be repeated.

**A parameter set under one version is an experiment.** Nothing new has to be
stored to compare experiments: a fit already records the warrant it ran under,
the snapshot it read, the featureset version that shaped it, the window, the
cardinality and the diagnostics. Putting them side by side is arithmetic over
what the register holds.

**"Promote a run to a version" is a category error, and saying so is the
answer.** A parameter set is a point in `P`; a version is a kernel — `f : P ⊗ X →
D(Y)`. Promoting one to the other would mean the kernel changed because somebody
re-fitted, which is exactly the confusion the parameter/version split exists to
prevent: it is what lets a recalibration procedure be approved once instead of
pretending a committee meets every morning. What promotion *means* here is
**approving the parameter set**, which is a real act with a real signature, and
this module points at it rather than building a wrong thing next to it.

**And "reproducible" is a property of a claim, not of a wish.** Most platforms
show a reproducibility badge meaning *we stored some metadata*. This enumerates
what a re-run would actually need, says which of it is present, and **refuses to
call a fit reproducible when the answer is unknown** — because the missing items
are nearly always the environment and the seed, and a badge that hides that is
worse than no badge.

**MAYA cannot reconstruct an environment it never had.** It did not run the
training; four of the facts a bundle needs are the fitter's to supply. So the
bundle states them, checks them, and ranks what is missing by how much it
actually threatens the reproduction — because re-running on a different
population is not a reproduction, while re-running on a patch-level library
difference usually agrees to more decimal places than anybody uses.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from core.parameters.common import ParameterError

#: What a re-run needs, what supplies it, and how badly its absence hurts.
#: Ranked, because "seven fields missing" is not a finding and "you cannot
#: reproduce this because you do not know which rows it read" is.
BUNDLE: Dict[str, Dict[str, Any]] = {
    "snapshot": {
        "from": "the register",
        "threat": "fatal",
        "means": "which rows the fit actually read, pinned by digest",
        "why": "re-running on a different population is not a reproduction, it "
               "is a different experiment. This is the one MAYA can guarantee "
               "and the one that matters most",
    },
    "featureset_version": {
        "from": "the register",
        "threat": "fatal",
        "means": "which schema shaped the columns",
        "why": "the same rows read through a different featureset are "
               "different inputs",
    },
    "warrant": {
        "from": "the register",
        "threat": "fatal",
        "means": "the authority the fit ran under",
        "why": "without it, *which data produced these numbers* has no answer "
               "at all",
    },
    "window": {
        "from": "the register",
        "threat": "fatal",
        "means": "the period the fit was over",
        "why": "a bitemporal store will happily answer a different question if "
               "you ask it at a different as-of",
    },
    "seed": {
        "from": "the fitter",
        "threat": "serious",
        "means": "the random seed the procedure used",
        "why": "without it a stochastic fit is reproducible only in "
               "distribution, which is a weaker claim than the one people make "
               "when they say reproducible",
    },
    "environment": {
        "from": "the fitter",
        "threat": "moderate",
        "means": "a lockfile digest, or a container digest",
        "why": "a patch-level library difference usually agrees to more decimal "
               "places than anybody uses — but *usually* is not a control, and "
               "the cases where it does not are the ones somebody will argue "
               "about",
    },
    "commit": {
        "from": "the fitter",
        "threat": "moderate",
        "means": "the revision of the fitting code",
        "why": "the procedure is not in this register, so its version is "
               "somebody else's fact to state",
    },
}

#: Where each fact should be found on a parameter set.
COLUMNS: Dict[str, str] = {
    "snapshot": "snapshot_id",
    "featureset_version": "featureset_version_id",
    "warrant": "warrant_id",
}

#: Diagnostics keys the fitter is expected to have put the fitter's own facts
#: under. Looked for under several names because nobody agrees, and looking
#: under one is how a check quietly passes everything.
DIAGNOSTIC_KEYS: Dict[str, tuple] = {
    "seed": ("seed", "random_seed", "rng_seed"),
    "environment": ("environment", "lockfile", "lockfile_digest",
                    "container", "container_digest", "image_digest"),
    "commit": ("commit", "git_commit", "revision", "sha"),
}


class Experiments:
    """Compares the runs under one version, and grades their reproducibility."""

    def __init__(self, parameters, registry):
        self.parameters, self.registry = parameters, registry

    # ------------------------------------------------------------- compare
    def compare(self, urn: str, semver: str,
                name: Optional[str] = None) -> Dict[str, Any]:
        """Every run under this version, side by side."""
        version = self.registry.version_service.require(urn, semver)
        rows = [r for r in self.parameters.parameters.many(
            model_version_id=version["id"])
            if name is None or r.get("name") == name]
        rows.sort(key=lambda r: (r.get("created_at") or 0))
        if not rows:
            return {"urn": urn, "semver": semver, "runs": [], "count": 0,
                    "metrics": [], "approved": [],
                    "differ_only_in_parameters": True,
                    # Carried even here: a reader who arrives at an empty
                    # version is exactly the reader about to look for a
                    # "promote" button, and the answer to that is the same.
                    "promotion": self.promotion(),
                    "detail": ("no parameters have been recorded against this "
                               "version, so there is nothing to compare — "
                               "which is what a version nobody has fitted "
                               "looks like")}

        metrics = sorted({k for r in rows
                          for k, v in (r.get("diagnostics") or {}).items()
                          if isinstance(v, (int, float))
                          and not isinstance(v, bool)})
        runs = []
        for row in rows:
            diagnostics = row.get("diagnostics") or {}
            runs.append({
                "parameter_set_id": row["id"], "name": row.get("name"),
                "version": row.get("version"), "state": row.get("state"),
                "provenance": row.get("provenance"),
                "cardinality": row.get("cardinality"),
                "digest": row.get("digest"),
                "warrant_id": row.get("warrant_id"),
                "snapshot_id": row.get("snapshot_id"),
                "window_from": row.get("window_from"),
                "window_to": row.get("window_to"),
                "metrics": {m: diagnostics.get(m) for m in metrics},
                "reproducible": self.bundle(row)["reproducible"],
            })
        approved = [r for r in runs if r["state"] == "approved"]
        return {
            "urn": urn, "semver": semver, "runs": runs, "count": len(runs),
            "metrics": metrics,
            "approved": [r["parameter_set_id"] for r in approved],
            "differ_only_in_parameters": self._same_inputs(rows),
            "promotion": self.promotion(),
            "detail": self._compare_detail(runs, metrics, rows),
        }

    @staticmethod
    def _same_inputs(rows: List[Dict[str, Any]]) -> bool:
        """Whether every run read the same data through the same schema.

        The question that decides what a comparison means. Runs over the same
        inputs differ because of the procedure; runs over different inputs
        differ for reasons nobody has separated, and a metric table across them
        is a table of unlike things.
        """
        keys = {(r.get("snapshot_id"), r.get("featureset_version_id"),
                 r.get("window_from"), r.get("window_to")) for r in rows}
        return len(keys) == 1

    @staticmethod
    def _compare_detail(runs, metrics, rows) -> str:
        out = f"{len(runs)} run(s)"
        if metrics:
            out += f", comparable on {', '.join(metrics)}"
        else:
            out += (", and none of them recorded a numeric diagnostic — so "
                    "there is nothing to rank them by, which is a fact about "
                    "the fitter rather than about the runs")
        if not Experiments._same_inputs(rows):
            out += (". They did NOT all read the same data through the same "
                    "schema, so a metric table across them is a table of "
                    "unlike things: runs over the same inputs differ because "
                    "of the procedure, and runs over different inputs differ "
                    "for reasons nobody has separated")
        irreproducible = [r for r in runs if not r["reproducible"]]
        if irreproducible:
            out += (f". {len(irreproducible)} of them could not be re-run from "
                    f"what the register holds")
        return out

    # -------------------------------------------------------------- bundle
    def bundle(self, row: Dict[str, Any]) -> Dict[str, Any]:
        """What a re-run of this fit would need, and what is missing.

        Ranked by threat rather than counted, because *seven fields missing* is
        not a finding and *you cannot reproduce this because you do not know
        which rows it read* is.
        """
        diagnostics = row.get("diagnostics") or {}
        present, missing = {}, []
        for fact, spec in BUNDLE.items():
            value = self._value(fact, row, diagnostics)
            if value:
                present[fact] = value
            else:
                missing.append({"fact": fact, **spec})
        fatal = [m for m in missing if m["threat"] == "fatal"]
        return {
            "parameter_set_id": row.get("id"),
            "present": present, "missing": missing,
            "fatal": [m["fact"] for m in fatal],
            # Reproducible means the claim holds, not that some metadata was
            # stored. A fatal gap is a re-run that would answer a different
            # question, and calling that reproducible would be the badge this
            # module exists to refuse.
            "reproducible": not fatal,
            "detail": self._bundle_detail(present, missing, fatal),
        }

    @staticmethod
    def _value(fact: str, row: Dict[str, Any],
               diagnostics: Dict[str, Any]) -> Optional[Any]:
        if fact == "window":
            return (row.get("window_from") is not None
                    and row.get("window_to") is not None) or None
        column = COLUMNS.get(fact)
        if column:
            return row.get(column)
        for key in DIAGNOSTIC_KEYS.get(fact, ()):
            if diagnostics.get(key):
                return diagnostics[key]
        return None

    @staticmethod
    def _bundle_detail(present, missing, fatal) -> str:
        if not missing:
            return ("everything a re-run needs is recorded, including the four "
                    "facts only the fitter could supply")
        if fatal:
            worst = fatal[0]
            return (f"this fit cannot be reproduced: {worst['fact']} is "
                    f"missing, and {worst['why']}. "
                    f"{len(missing) - len(fatal)} other fact(s) are also "
                    f"absent, but they are not what stops it")
        names = ", ".join(m["fact"] for m in missing)
        return (f"the register can say which data this fit read and under what "
                f"authority, which is the part it can guarantee. {names} "
                f"came from the fitter and were not supplied — MAYA did not "
                f"run the training and cannot reconstruct an environment it "
                f"never had, so this is stated rather than assumed away")

    def bundle_for(self, parameter_set_id: str) -> Dict[str, Any]:
        row = self.parameters.parameters.one(id=parameter_set_id)
        if not row:
            raise ParameterError(
                "no_parameter_set", f"no parameter set '{parameter_set_id}'",
                "the id comes from the run list on a version")
        return self.bundle(row)

    # ----------------------------------------------------------- promotion
    @staticmethod
    def promotion() -> Dict[str, Any]:
        """Why a run is not promoted to a version, and what to do instead."""
        return {
            "supported": False,
            "why_not": (
                "a parameter set is a point in `P` and a version is a kernel, "
                "`f : P ⊗ X → D(Y)`. Promoting one to the other would mean the "
                "kernel changed because somebody re-fitted — which is exactly "
                "the confusion the parameter/version split exists to prevent, "
                "and the thing that lets a recalibration procedure be approved "
                "once instead of pretending a committee meets every morning"),
            "what_to_do_instead": (
                "approve the parameter set. That is a real act with a real "
                "signature and its own segregation rule, and it is what "
                "'promoting a run' actually means here — the model that runs "
                "changes because the approved point of `P` changed, and the "
                "kernel it changed under is unaffected"),
            "if_the_kernel_really_changed": (
                "then it is a new VERSION, and it goes through refinement "
                "(`L-7`) and variance (`L-12`) like any other — which is the "
                "check a promotion button would have skipped"),
        }

    # ---------------------------------------------------------------- estate
    def across_the_estate(self) -> Dict[str, Any]:
        """Every fitted run, and how many could actually be re-run."""
        rows = list(self.parameters.parameters.many())
        fitted = [r for r in rows if r.get("provenance") == "fitted"]
        bundles = [self.bundle(r) for r in fitted]
        reproducible = [b for b in bundles if b["reproducible"]]
        by_missing: Dict[str, int] = {}
        for bundle in bundles:
            for gap in bundle["missing"]:
                by_missing[gap["fact"]] = by_missing.get(gap["fact"], 0) + 1
        return {
            "fitted_runs": len(fitted), "reproducible": len(reproducible),
            "missing_by_fact": by_missing,
            "bundle": [{"fact": k, **v} for k, v in BUNDLE.items()],
            "detail": (
                f"{len(reproducible)} of {len(fitted)} fitted run(s) could be "
                f"re-run from what the register holds"
                + (f". The commonest gap is "
                   f"{max(by_missing, key=lambda k: by_missing[k])}, which is "
                   f"a fact the fitter supplies — MAYA did not run the "
                   f"training and cannot reconstruct an environment it never "
                   f"had" if by_missing else "")
                if fitted else
                "nothing on this estate has been fitted, so there is no run to "
                "reproduce"),
        }
