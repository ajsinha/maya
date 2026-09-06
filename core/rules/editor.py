"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The rule-set editor: the one place MAYA authors a model, and the reasons it is
allowed to.

`docs/10 §7` says MAYA does not train models and does not run them, and an
authoring surface looks like a straight breach of that. It is not, and the
distinction is worth being precise about because it is what keeps the rest of
the boundary intact.

**MAYA does not become the authoring tool. It becomes an editor for a parameter
set it already held.** A T8 rule set was always `P` in the register —
`parameter_kind: rule_set`, `provenance: declared`, versioned, digested,
approved by somebody other than its author. What existed was the governed
object; what did not exist was any way to type into it except a raw JSON body,
and no way for the platform to say a single thing about what the rules meant.

So the line is: **the editor edits the governed object, and never mints one.**
Everything that made a parameter set trustworthy still applies unchanged —
`approve` still refuses `self_approval`, the digest is still taken over the
content, the second reviewer is still a different person. Publishing here is the
same act as `POST /parameters`, reached through a door that checks the document
first.

Three things follow that are worth naming:

* **This is not a model editor for ONNX or PMML.** Those serialize a fitted map;
  authoring one by hand would let MAYA mint an artifact that has never been
  trained or validated and is indistinguishable in the register from one that
  was. A rule set has no training run to be indistinguishable from — authorship
  *is* its provenance, which is exactly what `declared` means.
* **Rendering is separate from authoring.** `explain()` produces the English
  form and `canonical()` the bytes; neither carries authority, and both can be
  re-run over an approved set without authoring anything. This is the same
  `render`/`compile` split the export pack forced.
* **`trial()` runs a draft and records nothing.** An author needs to try an
  input against rules nobody has approved yet, and that is not scoring a model —
  there is no warrant, no entitlement and no decision. Calling it through
  `/execute` would have required inventing an authority for it.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from core.evidence import EvidenceEngine
from core.log import get_logger
from core.rules.common import RuleError
from core.rules.ruleset import RuleSet

logger = get_logger(__name__)

RULE_SET = "rule_set"
DECLARED = "declared"


class RuleSetEditor:
    """Validates, explains, trials and publishes rule sets."""

    def __init__(self, registry, parameters, evidence: EvidenceEngine):
        self.registry, self.parameters, self.evidence = registry, parameters, evidence

    # ------------------------------------------------------------------ check
    def check(self, urn: str, semver: str, document: Any) -> Dict[str, Any]:
        """Parse and validate against the version's declared schemas.

        The whole report, not the first problem: somebody fixing a forty-rule
        set wants the list. The refusals that make a set unusable still raise —
        this returns what passed.
        """
        version = self._version(urn, semver)
        ruleset = RuleSet.parse(document)
        report = ruleset.validate(_schema_of(version.get("input_schema")),
                                  _schema_of(version.get("output_schema")))
        return {**report,
                "urn": urn, "semver": semver,
                "reads": sorted(ruleset.fields()),
                "explanation": ruleset.describe(),
                "canonical": ruleset.canonical()}

    # ------------------------------------------------------------------ trial
    def trial(self, urn: str, semver: str, document: Any,
              rows: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Run a draft against sample inputs. Records nothing, decides nothing.

        Deliberately not routed through `/execute`. There is no warrant here and
        no entitlement, because nothing is being scored: an author is reading
        their own draft back. Giving this an authority would have meant
        inventing one, and an authority invented for a convenience is the kind
        that turns up later attached to something else.

        It also earns its keep as a **coverage report**. A rule that fires on
        none of the sample rows is not necessarily wrong — but a rule set where
        most rules never fire on any realistic input is one somebody should look
        at before it is approved.
        """
        version = self._version(urn, semver)
        ruleset = RuleSet.parse(document)
        ruleset.validate(_schema_of(version.get("input_schema")),
                         _schema_of(version.get("output_schema")))

        outcomes, fired = [], {r.id: 0 for r in ruleset.rules}
        for index, row in enumerate(rows):
            try:
                decision = ruleset.decide(row)
            except RuleError as exc:
                # Reported against the row, not raised: one bad sample must not
                # hide what the other nineteen would have shown.
                logger.info("trial row %d could not be decided: %s", index, exc.detail)
                outcomes.append({"row": index, "refused": exc.code,
                                 "detail": exc.detail})
                continue
            if decision.get("matched_rule"):
                fired[decision["matched_rule"]] += 1
            outcomes.append({"row": index, **decision})
        return {"outcomes": outcomes,
                "fired": fired,
                "never_fired": sorted(k for k, n in fired.items() if not n),
                "fell_through": sum(1 for o in outcomes
                                    if o.get("matched_rule") is None
                                    and "refused" not in o)}

    # ---------------------------------------------------------------- publish
    def publish(self, urn: str, semver: str, name: str, document: Any,
                note: str = "", actor: str = "system") -> Dict[str, Any]:
        """Record the rule set as a parameter set, checked first.

        No new authority: this is `ParameterRegister.record` with a validated
        document, so the set lands `proposed` and somebody other than the author
        approves it, exactly as a fitted coefficient set does.
        """
        report = self.check(urn, semver, document)
        ruleset = RuleSet.parse(document)
        row = self.parameters.record(
            urn, semver, name, RULE_SET, ruleset.canonical(),
            provenance=DECLARED,
            diagnostics={"rules": len(ruleset.rules),
                         "reads": sorted(ruleset.fields()),
                         "shadowed": report["shadowed"],
                         "contradictions": report["contradictions"]},
            note=note, actor=actor)
        logger.info("published rule set '%s' for %s@%s: %d rules over %d fields",
                    name, urn, semver, len(ruleset.rules), len(ruleset.fields()))
        return row

    # ---------------------------------------------------------------- explain
    def explain(self, parameter_set_id: str) -> Dict[str, Any]:
        """An approved rule set in English. Carries no authority and records
        nothing, so a model card, a committee paper and an export pack all read
        the same rendering rather than each writing their own."""
        row = self.parameters.require(parameter_set_id)
        if row.get("kind") != RULE_SET:
            raise RuleError(
                "not_a_ruleset",
                f"parameter set '{row.get('name')}' is a '{row.get('kind')}', "
                f"not a rule set",
                "this reads rule sets; a fitted parameter set is read on the "
                "model page")
        ruleset = RuleSet.parse(row.get("values_inline") or {})
        return {"parameter_set": parameter_set_id,
                "name": row.get("name"), "state": row.get("state"),
                "rules": len(ruleset.rules),
                "reads": sorted(ruleset.fields()),
                "explanation": ruleset.describe()}

    # ------------------------------------------------------------------ util
    def _version(self, urn: str, semver: str) -> Dict[str, Any]:
        version = self.registry.version(urn, semver)
        if version is None:
            raise RuleError("not_found", f"{urn}@{semver} is not registered",
                            "register the version before authoring its rules")
        if version.get("parameter_kind") != RULE_SET:
            raise RuleError(
                "not_a_ruleset_model",
                f"{urn}@{semver} declares parameter_kind "
                f"'{version.get('parameter_kind')}', so its parameter object is "
                f"not a rule set",
                "register a version with parameter_kind 'rule_set' and "
                "fit_procedure 'author'")
        return version


def _schema_of(declared: Any) -> Dict[str, str]:
    """`[{name, dtype}, ...]` as `{name: dtype}`, which is what the condition
    checker needs. An absent schema becomes an empty map, and every field read
    is then refused by name — which is the right outcome: a rule set over a
    model that declares no inputs is reading something nobody wrote down."""
    if not isinstance(declared, list):
        return {}
    return {f["name"]: str(f.get("dtype", "numeric"))
            for f in declared if isinstance(f, dict) and f.get("name")}
