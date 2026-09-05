"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The `rules` runtime: a T8 model, run at the point of `P` that was approved.

The grammar has named this runtime since the first milestone and no engine
implemented it, so a rule set could be registered, versioned, approved and
attested — and never actually run by anything. It could still be *scored*, by
whatever stored procedure the bank was already using, which is the arrangement
this platform exists to end: the governed artefact and the executing artefact
were two documents that nobody compared.

## Why the rule set arrives in the parameters and not in the artifact

For a T8 model the rule set **is** `P`. It reaches the engine the way every
register-held parameter object does — `CaptiveEngine._with_parameters` resolves the
approved set, re-derives its digest, and puts the values in
`inputs["parameters"]`. So running a rule set at an unapproved point of `P` is
refused by the same mechanism that refuses running a scorecard at unapproved
coefficients, rather than by anything written here.

That is also why this runtime is absent from `UNVERIFIABLE_DETERMINISM`
(`L-W5`): MAYA holds the rule set, reads it, and can therefore verify the
determinism a warrant claims by executing it — which is stronger evidence than a
seed, and the same reason the captive estimator is exempt.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from core.execution.errors import WarrantError
from core.execution.runtimes.base import Invocation
from core.log import get_logger
from core.rules.common import RuleError
from core.rules.ruleset import RuleSet

logger = get_logger(__name__)


class RulesRuntime:
    """Evaluates an approved rule set, first match wins."""

    key = "rules"

    def available(self) -> Optional[str]:
        """Always usable. The rule language is this repository's own, with no
        third-party dependency to be missing — which is most of the argument for
        keeping it as small as it is."""
        return None

    def invoke(self, call: Invocation) -> Any:
        verb = (call.warrant.get("operation") or {}).get("verb")
        if verb != "score":
            raise WarrantError(
                "wrong_verb",
                f"a rule set is authored rather than fitted, and the warrant's "
                f"verb is '{verb}'",
                "issue a warrant whose verb is 'score'; a change to the rules is "
                "a new parameter set somebody approves, not a fit")

        document = (call.inputs or {}).get("parameters")
        if not document:
            raise WarrantError(
                "no_ruleset",
                "the warrant binds no parameter set, so there are no rules to "
                "run and nothing that was approved",
                "record the rule set as a parameter set and have somebody other "
                "than its author approve it")

        try:
            ruleset = RuleSet.parse(document)
        except RuleError as exc:
            # Not swallowed and not recovered from: a stored rule set that no
            # longer parses means the register holds something the register's
            # own checks would refuse, and running the rules it *can* read would
            # be answering with part of a policy.
            logger.error("an approved rule set failed to parse at execution: %s",
                         exc.detail)
            raise WarrantError(
                "ruleset_malformed",
                f"the approved rule set does not parse: {exc.detail}",
                "do not run it; the register holds a document its own checks "
                "would refuse, and that is a platform defect rather than a bad "
                "request") from exc

        row = {k: v for k, v in (call.inputs or {}).items() if k != "parameters"}
        outcome = ruleset.decide(row)
        logger.info("rule set decided %s for version %s",
                    outcome.get("matched_rule") or "(otherwise)", call.version_id)
        return self._project(outcome, call)

    @staticmethod
    def _project(outcome: Dict[str, Any], call: Invocation) -> Dict[str, Any]:
        """The declared outputs, plus the attribution.

        `matched_rule` and `because` travel even when the output schema does not
        declare them. A decision a bank cannot attribute to a rule is one it
        cannot explain to the person it refused, and under most consumer-credit
        regimes the explanation is the obligation — not the decision.
        """
        declared = call.output_names
        projected = ({k: v for k, v in outcome.items() if k in declared}
                     if declared else
                     {k: v for k, v in outcome.items()
                      if k not in ("matched_rule", "because")})
        return {**projected,
                "matched_rule": outcome.get("matched_rule"),
                "because": outcome.get("because")}
