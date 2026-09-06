"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The policy register.

A gate that cannot be changed without a release is a gate people work around. A
gate that *can* be changed without a release is a gate that can be **weakened**
without a release, which is worse. Everything here is about making the first
possible without making the second silent.

**A policy ships with its own tests, and cannot be published until they pass.**
Not tests somebody wrote elsewhere — cases carried by the policy itself, each a
set of facts and the verdict the author says those facts deserve. At least one
must be a case the policy *refuses*: a policy nobody has shown to refuse anything
is a policy nobody has shown to be a gate.

**A published version is immutable**, and superseding one keeps it. "Which rule
was in force in March" is a question somebody will ask.

**Weakening is allowed and is never quiet.** Publishing a version that permits
something its predecessor refused is a legitimate act — rules do change — but the
register replays the outgoing version's cases against the incoming one and
reports every verdict that flipped. A change that loosens a gate should be a
thing somebody decided, not a thing somebody discovered.

**An instance that publishes nothing runs exactly what it ran before.** The
built-in rules are the default for every gate, expressed in the same language, so
adopting the engine changes no behaviour at all.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Sequence, Tuple

from core.evidence import EvidenceEngine
from core.log import get_logger
from core.policy.common import (ALLOW, DRAFT, GATES, GATE_MEANING, MIN_CASES,
                                PUBLISHED, REFUSE, SUPERSEDED, PolicyError)
from core.policy.facts import BUILT_IN, complete, describe as describe_facts
from core.policy.facts import vocabulary
from core.policy.language import Rule
from db.database import digest as canonical_digest

logger = get_logger(__name__)


class PolicyRegister:
    """Holds the rule in force for each gate, and how it got there."""

    def __init__(self, policies, evidence: EvidenceEngine):
        self.policies, self.evidence = policies, evidence
        self._compiled: Dict[str, Tuple[str, Rule]] = {}

    # ----------------------------------------------------------------- write
    def draft(self, gate: str, rule: str, reason: str,
              cases: Sequence[Dict[str, Any]], actor: str = "system",
              note: str = "") -> Dict[str, Any]:
        """Write a policy and its cases. Nothing is in force until it passes."""
        if gate not in GATES:
            raise PolicyError("unknown_gate", f"'{gate}' is not a gate",
                              f"expected one of {', '.join(GATES)}")
        if not reason.strip():
            raise PolicyError(
                "reason_required",
                "a policy needs a sentence saying what it is for",
                "the refusal a person sees quotes it, and 'policy violation' "
                "tells them nothing they can act on")
        compiled = Rule(rule, vocabulary(gate))         # refuses an unknown fact
        report = self.check(gate, compiled, cases)
        row = {
            "gate": gate, "rule": compiled.source, "reason": reason.strip(),
            "cases": list(cases), "facts_read": compiled.facts_read(),
            "version": self._next_version(gate), "state": DRAFT,
            "note": note, "digest": canonical_digest(
                {"gate": gate, "rule": compiled.source, "cases": list(cases)}),
            "created_by": actor, "created_at": time.time(),
            "published_at": None, "published_by": None,
            "test_report": report,
        }
        self.policies.add(row)
        self.evidence.append("policy_drafted", "policy", row["id"],
                             {"gate": gate, "version": row["version"],
                              "rule": compiled.source,
                              "cases": len(cases),
                              "passing": report["passed"]}, actor=actor)
        return self.policies.one(id=row["id"])

    def check(self, gate: str, rule: Rule,
              cases: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
        """Run the policy's own cases. Reported, never assumed."""
        if len(cases) < MIN_CASES:
            raise PolicyError(
                "too_few_cases",
                f"a policy carries at least {MIN_CASES} cases and this one "
                f"carries {len(cases)}",
                "one that allows and one that refuses, at least; a policy "
                "nobody has shown to refuse anything is a policy nobody has "
                "shown to be a gate")
        results, failures = [], []
        for index, case in enumerate(cases):
            expected = case.get("expect")
            if expected not in (ALLOW, REFUSE):
                raise PolicyError(
                    "case_without_a_verdict",
                    f"case {index} does not say whether it expects "
                    f"'{ALLOW}' or '{REFUSE}'",
                    "a case with no expected verdict tests nothing")
            got = ALLOW if rule.evaluate(
                complete(gate, case.get("facts") or {})) else REFUSE
            row = {"case": index, "name": case.get("name", f"case {index}"),
                   "expected": expected, "got": got, "ok": got == expected}
            results.append(row)
            if not row["ok"]:
                failures.append(row)
        refusing = [r for r in results if r["expected"] == REFUSE]
        if not refusing:
            raise PolicyError(
                "no_refusing_case",
                "none of the cases expects this policy to refuse anything",
                "a policy nobody has shown to refuse is a policy nobody has "
                "shown to be a gate; add a case it must turn down")
        return {"cases": len(results), "passed": not failures,
                "results": results, "failures": failures,
                "detail": (f"all {len(results)} case(s) behave as declared"
                           if not failures else
                           f"{len(failures)} of {len(results)} case(s) do not: "
                           + "; ".join(f"{f['name']} expected {f['expected']}, "
                                       f"got {f['got']}" for f in failures))}

    def publish(self, policy_id: str, actor: str = "system") -> Dict[str, Any]:
        """Put a policy in force, if its own cases pass."""
        row = self.require(policy_id)
        if row["state"] != DRAFT:
            raise PolicyError("already_decided",
                              f"this policy is already '{row['state']}'",
                              "draft a new version")
        rule = Rule(row["rule"], vocabulary(row["gate"]))
        report = self.check(row["gate"], rule, row["cases"])
        if not report["passed"]:
            raise PolicyError(
                "cases_do_not_pass",
                f"this policy does not behave as its own cases declare: "
                f"{report['detail']}",
                "a gate that can be changed without a release is a gate that "
                "can be weakened without one; the cases are what stops that "
                "being silent")

        outgoing = self.in_force(row["gate"])
        drift = self.compare(row["gate"], outgoing, rule) if outgoing else {}
        if outgoing:
            self.policies.set({"state": SUPERSEDED}, id=outgoing["id"])
        self.policies.set({"state": PUBLISHED, "published_at": time.time(),
                           "published_by": actor, "test_report": report},
                          id=policy_id)
        self._compiled.pop(row["gate"], None)
        self.evidence.append("policy_published", "policy", policy_id,
                             {"gate": row["gate"], "version": row["version"],
                              "rule": row["rule"],
                              "supersedes": outgoing["version"] if outgoing else None,
                              "loosened": drift.get("loosened", []),
                              "tightened": drift.get("tightened", [])},
                             actor=actor)
        if drift.get("loosened"):
            logger.warning("policy %s v%d permits %d case(s) its predecessor "
                           "refused", row["gate"], row["version"],
                           len(drift["loosened"]))
        return {**self.policies.one(id=policy_id), "drift": drift}

    def compare(self, gate: str, outgoing: Dict[str, Any],
                incoming: Rule) -> Dict[str, Any]:
        """Replay the outgoing policy's cases against the incoming one.

        Weakening a gate is legitimate; doing it without anybody noticing is
        not. This is what turns the second into the first.
        """
        loosened, tightened = [], []
        for case in outgoing.get("cases") or []:
            facts = complete(gate, case.get("facts") or {})
            before = case.get("expect")
            after = ALLOW if incoming.evaluate(facts) else REFUSE
            if before == after:
                continue
            row = {"name": case.get("name", "a case"), "was": before, "now": after}
            (loosened if after == ALLOW else tightened).append(row)
        return {"loosened": loosened, "tightened": tightened,
                "detail": self._drift_detail(loosened, tightened)}

    @staticmethod
    def _drift_detail(loosened: Sequence[Dict[str, Any]],
                      tightened: Sequence[Dict[str, Any]]) -> str:
        if not loosened and not tightened:
            return "nothing the previous policy decided has changed"
        return "; ".join(
            ([f"{len(loosened)} case(s) the previous policy refused are now "
              f"permitted"] if loosened else [])
            + ([f"{len(tightened)} case(s) it permitted are now refused"]
               if tightened else []))

    def drift_of(self, policy_id: str) -> Dict[str, Any]:
        """What changed when this version went in force, read from the record.

        The comparison is made once, at publication, and returned to whoever
        published. A report that existed only in that response would be a
        governance fact nobody could revisit — and the question "when did this
        gate get looser" is asked long afterwards, by somebody who was not there.
        So it is read back off the evidence chain rather than recomputed against
        a rule that has since moved on.
        """
        for row in self.evidence.for_subject(policy_id):
            if row.get("kind") != "policy_published":
                continue
            payload = row.get("payload") or {}
            loosened = payload.get("loosened") or []
            tightened = payload.get("tightened") or []
            return {
                "loosened": loosened, "tightened": tightened,
                "supersedes": payload.get("supersedes"),
                "detail": (self._drift_detail(loosened, tightened)
                           if payload.get("supersedes") is not None else
                           "nothing was in force on this gate before, so there "
                           "was nothing to compare it with"),
            }
        return {}

    # ------------------------------------------------------------------ read
    def in_force(self, gate: str) -> Optional[Dict[str, Any]]:
        return self.policies.one(gate=gate, state=PUBLISHED)

    def rule_for(self, gate: str) -> Tuple[Rule, Dict[str, Any]]:
        """The rule in force, and where it came from. Built-in when none is."""
        published = self.in_force(gate)
        if published is None:
            source, reason = BUILT_IN[gate]
            cached = self._compiled.get(f"built-in:{gate}")
            rule = cached[1] if cached else Rule(source, vocabulary(gate))
            self._compiled[f"built-in:{gate}"] = (source, rule)
            return rule, {"gate": gate, "version": 0, "rule": source,
                          "reason": reason, "source": "built-in"}
        cached = self._compiled.get(gate)
        if cached is None or cached[0] != published["rule"]:
            cached = (published["rule"], Rule(published["rule"],
                                              vocabulary(gate)))
            self._compiled[gate] = cached
        return cached[1], {**published, "source": "published"}

    def decide(self, gate: str, facts: Dict[str, Any],
               strict: bool = True) -> Dict[str, Any]:
        """The verdict, and which policy version reached it.

        The version is part of the answer. 'Why was this refused in March' is a
        question about a rule that may since have changed.
        """
        if gate not in GATES:
            raise PolicyError("unknown_gate", f"'{gate}' is not a gate", "")
        rule, provenance = self.rule_for(gate)

        # A fact the RULE reads must be supplied. Anything else may default.
        #
        # `complete()` filled in every fact the gate declares, so by the time
        # the rule ran nothing was ever missing and `Rule.evaluate`'s
        # `fact_not_supplied` refusal could never fire. Fourteen of the
        # thirty-six advertised facts were never passed by any call site, and
        # three of them — `blocking_findings`, `open_findings`, `actor_roles` —
        # default to the PERMISSIVE value. The built-in `version:approve` rule
        # is `blocking_findings == 0 and tier is not None`, published as in
        # force with the reason "a version is not approved over an open blocking
        # finding", and that half of it had never been able to fire.
        #
        # Refusing here is loud in the right direction: a gate wired without a
        # fact it judges on stops working visibly rather than passing everything.
        # `strict=False` is the EXPLORATION path — `/policies/try`, where
        # somebody is asking what a rule would decide about facts they typed.
        # Defaulting there is what they expect; defaulting on the live path is
        # the defect.
        missing = sorted(set(rule.facts_read()) - set(facts)) if strict else []
        if missing:
            raise PolicyError(
                "fact_not_supplied",
                f"the '{gate}' policy reads {', '.join(missing)} and the call "
                f"site did not supply it",
                "this is a defect in the gate's wiring rather than in the rule: "
                "a fact the rule judges on cannot be defaulted, because the "
                "default would decide the answer")

        supplied = complete(gate, facts)
        allowed = rule.evaluate(supplied)
        return {
            "gate": gate, "decision": ALLOW if allowed else REFUSE,
            "allowed": allowed,
            "policy_version": provenance["version"],
            "policy_source": provenance["source"],
            "rule": provenance["rule"], "reason": provenance["reason"],
            "facts_read": {f: supplied.get(f) for f in rule.facts_read()},
            "detail": (f"permitted by {provenance['source']} policy v"
                       f"{provenance['version']}" if allowed else
                       f"refused by {provenance['source']} policy v"
                       f"{provenance['version']}: {provenance['reason']}"),
        }

    def get(self, policy_id: str) -> Optional[Dict[str, Any]]:
        return self.policies.one(id=policy_id)

    def require(self, policy_id: str) -> Dict[str, Any]:
        row = self.get(policy_id)
        if row is None:
            raise PolicyError("no_policy", f"no policy {policy_id}", "")
        return row

    def history(self, gate: str) -> List[Dict[str, Any]]:
        """Every version, superseded ones included. Somebody will ask."""
        return sorted(self.policies.many(gate=gate),
                      key=lambda p: p["version"])

    def _next_version(self, gate: str) -> int:
        existing = self.policies.many(gate=gate)
        return max((p["version"] for p in existing), default=0) + 1

    # -------------------------------------------------------------- describe
    def describe(self) -> List[Dict[str, Any]]:
        """Every gate: what is in force, where it came from, what it may read."""
        out = []
        for gate in GATES:
            _, provenance = self.rule_for(gate)
            out.append({
                "gate": gate, "governs": GATE_MEANING[gate],
                "in_force": provenance["rule"],
                "reason": provenance["reason"],
                "version": provenance["version"],
                "source": provenance["source"],
                "facts": describe_facts(gate),
                "versions": len(self.policies.many(gate=gate)),
            })
        return out


class PolicyGate:
    """Applies the register's verdict at a call site, and only ever to refuse.

    **Policy tightens; the code's invariants are the floor.** The checks written
    in the registry stay exactly where they are and a policy runs in addition to
    them, so a rule can add a condition and cannot remove one.

    That is a smaller promise than "the gates are the policy", and it is the
    honest one. Replacing an invariant with a line of configuration means a
    mistyped rule can weaken the platform, and the failure would look like a
    successful deployment. Tightening without a release is the half of the
    problem worth solving; loosening a gate should cost a release, and does.
    """

    def __init__(self, register: PolicyRegister, error=None):
        self.register = register
        # A call site supplies its own error type so the refusal reads like the
        # rest of that surface. Without one the gate raises its own, which is
        # what an engine or a script embedding it should see.
        self.error = error

    def check(self, gate: str, facts: Dict[str, Any],
              subject: str = "") -> Dict[str, Any]:
        """Raise the caller's own error type when the policy refuses."""
        verdict = self.register.decide(gate, facts)
        if not verdict["allowed"]:
            logger.info("policy v%s refused %s for %s",
                        verdict["policy_version"], gate, subject or "a subject")
            message = (f"{subject or gate} was refused by policy v"
                       f"{verdict['policy_version']}: {verdict['reason']}")
            if self.error is None:
                raise PolicyError(
                    "policy_refused", message,
                    "the rule in force is published at /api/v1/policies, "
                    "alongside the facts it read to reach this")
            raise self.error(message)
        return verdict

    def describe(self) -> Dict[str, Any]:
        return {
            "applies": "in addition to the checks written in the registry, "
                       "never instead of them",
            "can": "add a condition, so a gate can be tightened without a release",
            "cannot": "remove one; the code's invariants are the floor, because "
                      "a mistyped rule that weakened the platform would look "
                      "like a successful deployment",
            "gates": self.register.describe(),
        }
