"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The platform's own configuration, exported and applied — and the boundary that
says what is configurable at all.

"Configuration as code" usually means: put everything in YAML, put the YAML in
git, let CI apply it. Done that way to a governance platform it is the single
most effective way to defeat one, because **the gates and the git repository
then have the same approval process**, and that process is a pull request
reviewed by whoever is on shift.

So two things are true here at once and neither is negotiable.

**What is configuration and what is code is published, and the line does not
move.** A firm may configure its policies, its warrant profiles, its monitoring
defaults, its appetite limits and its remediation costs — the places where a
bank's own judgement belongs. It may not configure the lifecycle state graph,
the tier lattice, the trainability fibration or the refusal taxonomy. A firm
that could add a transition could add one that skips approval; a firm that could
edit the lattice could make tier 1 owe what tier 4 owes. Those are not settings
that happen to be hardcoded — they are the argument, and the argument is what
the platform is.

**Applying a configuration is a governance act, with a diff and an author.** Not
a deployment step. `plan` renders exactly what would change, `apply` records what
did, and both go on the evidence chain. A configuration that applied silently
would let somebody change every gate in the estate with a git push and no
approval — which is the failure this module is arranged to prevent rather than
to enable.

**And a plan that loosens is separated from a plan that tightens.** The policy
register already computes drift when a gate is republished; the same reading
applies to a whole configuration. *Three rules changed* is not a reviewable
sentence. *Two of these three let something through that is refused today* is —
and a loosening plan needs a named approver, because the whole risk of
configuration-as-code is that a tightening and a loosening travel in the same
pull request.
"""
from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional, Sequence

from core.log import get_logger

logger = get_logger(__name__)

FORMAT = "maya.configuration/v1"

#: What a firm may configure, and what reads it.
CONFIGURABLE: Dict[str, str] = {
    "policies": "the gates: what each one refuses and on which facts",
    "warrant_profiles": "the named defaults a warrant request is templated from",
    "monitoring_defaults": "which monitors a class and tier should have",
    "appetite": "the declared limits over metrics the platform derives",
    "retraining": "the standing policies that may accept a re-fit",
    "remediation_costs": "what each remediation act costs this firm",
}

#: What is code, and why each one is. Published beside the configurable list,
#: because "why can I not configure X" is a question with an answer, and the
#: answer is more useful than the absence.
NOT_CONFIGURABLE: Dict[str, str] = {
    "lifecycle_states": "a firm that could add a transition could add one that "
                        "skips approval, and the state graph is the only thing "
                        "making 'approved' mean the same in two institutions",
    "tier_lattice": "the adjunction between a tier and the controls it owes is "
                    "the argument, not a setting. A configurable lattice can "
                    "be made to say tier 1 owes what tier 4 owes",
    "trainability_fibration": "a class is DERIVED from what a version declares "
                              "and never asserted; configuring the derivation "
                              "would make it an assertion with extra steps",
    "refusal_taxonomy": "a refusal code is an interface. Renaming one in "
                        "configuration would break every caller that handles "
                        "it, silently, at the moment it fires",
    "evidence_chain": "append-only and hash-linked is what makes the record "
                      "evidence rather than a table",
    "segregation_of_duties": "the incompatible-role pairs are the three lines "
                             "of defence. A firm that could configure them "
                             "away would have configured away the reason the "
                             "platform exists",
}

LOOSENS, TIGHTENS, NEUTRAL = "loosens", "tightens", "neutral"


class ConfigurationError(RuntimeError):
    """A configuration was refused. The message always says which part."""

    def __init__(self, code: str, detail: str, remediation: str = ""):
        super().__init__(detail)
        self.code, self.detail, self.remediation = code, detail, remediation

    def as_problem(self) -> Dict[str, str]:
        return {"error": self.code, "detail": self.detail,
                "remediation": self.remediation}


class Configuration:
    """Exports what a firm may configure, plans a change, records applying it."""

    def __init__(self, evidence, policies=None, profiles=None,
                 monitoring_defaults=None, appetite=None, retraining=None,
                 registry=None, config=None):
        self.evidence = evidence
        self.policies, self.profiles = policies, profiles
        self.monitoring_defaults = monitoring_defaults
        self.appetite, self.retraining = appetite, retraining
        self.registry, self.config = registry, config

    # ---------------------------------------------------------------- export
    def export(self, sections: Optional[Sequence[str]] = None,
               now: Optional[float] = None) -> Dict[str, Any]:
        """What is in force, as a document. Read from the registers, not a file.

        Exporting from the registers rather than from whatever YAML was last
        applied is the difference between a description of the platform and a
        description of somebody's intentions.
        """
        wanted = list(sections or CONFIGURABLE)
        unknown = [s for s in wanted if s not in CONFIGURABLE]
        if unknown:
            raise ConfigurationError(
                "not_configurable",
                f"{', '.join(unknown)} is not something a firm configures",
                self._why_not(unknown))
        moment = now if now is not None else time.time()
        body = {s: self._read(s) for s in wanted}
        return {
            "format": FORMAT, "exported_at": moment,
            "sections": wanted, "configuration": body,
            "not_configurable": list(NOT_CONFIGURABLE),
            "read_from": "the registers in force, never a file",
            "detail": (
                f"{sum(len(v) for v in body.values())} object(s) across "
                f"{len(wanted)} section(s), read from the registers rather than "
                f"from whatever was last applied — which is the difference "
                f"between a description of the platform and a description of "
                f"somebody's intentions"),
        }

    @staticmethod
    def _why_not(names: Sequence[str]) -> str:
        reasons = [f"{n}: {NOT_CONFIGURABLE[n]}" for n in names
                   if n in NOT_CONFIGURABLE]
        if reasons:
            return ("; ".join(reasons)
                    + ". These are not settings that happen to be hardcoded — "
                      "they are the argument, and the argument is what the "
                      "platform is")
        return (f"the configurable sections are {', '.join(CONFIGURABLE)}; "
                f"everything else is code")

    def _read(self, section: str) -> List[Dict[str, Any]]:
        return getattr(self, f"_read_{section}")()

    def _read_policies(self) -> List[Dict[str, Any]]:
        if self.policies is None:
            return []
        out = []
        for gate in sorted({p["gate"] for p in self.policies.policies.many()}):
            row = self.policies.in_force(gate)
            if row:
                out.append({"gate": gate, "rule": row.get("rule"),
                            "reason": row.get("reason"),
                            "version": row.get("version")})
        return out

    def _read_warrant_profiles(self) -> List[Dict[str, Any]]:
        if self.profiles is None:
            return []
        return [{"name": p["name"], "when": p.get("when"),
                 "defaults": p.get("defaults"), "version": p.get("version")}
                for p in self.profiles.repo.many() if not p.get("retired_at")]

    def _read_monitoring_defaults(self) -> List[Dict[str, Any]]:
        if self.monitoring_defaults is None:
            return []
        described = getattr(self.monitoring_defaults, "describe", None)
        return list(described().get("defaults", [])) if described else []

    def _read_appetite(self) -> List[Dict[str, Any]]:
        if self.appetite is None:
            return []
        # `limit_value` and `amber_value` are the register's own column names.
        # Renamed here to `limit`/`amber` so the exported document reads like
        # the thing a person declares rather than like the table it lives in —
        # a configuration format that mirrors a schema is one that breaks every
        # time the schema is tidied.
        return [{"metric": row.get("metric"), "limit": row.get("limit_value"),
                 "amber": row.get("amber_value"), "scope": row.get("scope"),
                 "rationale": row.get("rationale")}
                for row in self.appetite.in_force()]

    def _read_retraining(self) -> List[Dict[str, Any]]:
        if self.retraining is None or self.registry is None:
            return []
        out = []
        for model in self.registry.list():
            state = self.retraining.policy(model["urn"])
            if state["policy"]:
                out.append({"urn": model["urn"],
                            "triggers": state["policy"]["triggers"],
                            "tolerance": state["policy"]["tolerance"],
                            "auto_accept": state["policy"]["auto_accept"]})
        return out

    def _read_remediation_costs(self) -> List[Dict[str, Any]]:
        if self.config is None:
            return []
        costs = self.config.get("remediation.costs", {}) or {}
        return [{"act": k, "cost": v} for k, v in sorted(costs.items())]

    # ------------------------------------------------------------------ plan
    def plan(self, document: Dict[str, Any],
             now: Optional[float] = None) -> Dict[str, Any]:
        """Exactly what would change, and which way each change points."""
        self._validate(document)
        moment = now if now is not None else time.time()
        wanted = list(document.get("configuration") or {})
        current = self.export(sections=wanted, now=moment)["configuration"]
        changes: List[Dict[str, Any]] = []
        for section in wanted:
            changes += _diff(section, current.get(section) or [],
                             document["configuration"][section] or [])
        loosening = [c for c in changes if c["direction"] == LOOSENS]
        return {
            "format": FORMAT, "planned_at": moment,
            "sections": wanted, "changes": changes, "count": len(changes),
            "loosens": loosening,
            "tightens": [c for c in changes if c["direction"] == TIGHTENS],
            "applied": False,
            "detail": self._plan_detail(changes, loosening),
        }

    @staticmethod
    def _plan_detail(changes, loosening) -> str:
        if not changes:
            return ("this configuration matches what is in force, so applying "
                    "it changes nothing. Worth running before every apply: a "
                    "no-op plan is the only proof that a repository and a "
                    "platform agree")
        out = f"{len(changes)} change(s)"
        if loosening:
            out += (f", **{len(loosening)} of which loosen something** — they "
                    f"let through what is refused today: "
                    + "; ".join(c["what"] for c in loosening[:4])
                    + (f" and {len(loosening) - 4} more"
                       if len(loosening) > 4 else "")
                    + ". *Three rules changed* is not a reviewable sentence; "
                      "*two of these three let something through that is "
                      "refused today* is")
        else:
            out += (", none of which loosen anything. That is computed from "
                    "the shape of each change rather than asserted by whoever "
                    "wrote it")
        return out

    def _validate(self, document: Dict[str, Any]) -> None:
        if document.get("format") != FORMAT:
            raise ConfigurationError(
                "unknown_format",
                f"this document declares format "
                f"{document.get('format') or 'nothing'}, not {FORMAT}",
                "a configuration with no format is one nothing can check the "
                "shape of; export a current one and edit that")
        body = document.get("configuration")
        if not isinstance(body, dict) or not body:
            raise ConfigurationError(
                "empty_configuration",
                "this document configures nothing",
                "an empty configuration applied would look like a successful "
                "no-op and would be a document nobody wrote")
        unknown = [s for s in body if s not in CONFIGURABLE]
        if unknown:
            raise ConfigurationError(
                "not_configurable",
                f"{', '.join(unknown)} is not something a firm configures",
                self._why_not(unknown))

    # ----------------------------------------------------------------- apply
    def apply(self, document: Dict[str, Any], rationale: str,
              actor: str = "system", now: Optional[float] = None,
              approved_by: str = "") -> Dict[str, Any]:
        """Record that a configuration was applied, with its diff.

        A governance act and not a deployment step. This records the intent and
        the diff on the evidence chain; each section is applied through its own
        register, which keeps its own approval — a method here that wrote
        policies directly would be a second way to publish a gate, and the
        second way is always the one without the signature.
        """
        planned = self.plan(document, now=now)
        if not planned["changes"]:
            raise ConfigurationError(
                "nothing_to_apply",
                "this configuration matches what is in force",
                "a no-op recorded as a change is an entry on the evidence "
                "chain that says something happened when nothing did")
        if not (rationale or "").strip():
            raise ConfigurationError(
                "rationale_required",
                "applying a configuration needs a reason. It changes what the "
                "platform refuses, and a year later the diff says what changed "
                "while only the rationale says why",
                "say what this is for")
        if planned["loosens"] and not (approved_by or "").strip():
            raise ConfigurationError(
                "loosening_needs_an_approver",
                f"{len(planned['loosens'])} change(s) let through what is "
                f"refused today, and nobody is named as approving that",
                "name the approver. A configuration that tightens can be a "
                "deployment; one that loosens is a decision, and the whole "
                "risk of configuration-as-code is that the two travel in the "
                "same pull request")
        moment = now if now is not None else time.time()
        self.evidence.append(
            "configuration_applied", "platform", "configuration",
            {"sections": planned["sections"], "changes": planned["count"],
             "loosens": len(planned["loosens"]),
             "tightens": len(planned["tightens"]),
             "rationale": rationale.strip(),
             "approved_by": approved_by or None,
             "digest": _digest(document)}, actor=actor)
        logger.info("%s applied a configuration over %d section(s): %d "
                    "change(s), %d loosening", actor, len(planned["sections"]),
                    planned["count"], len(planned["loosens"]))
        return {**planned, "applied": True, "applied_at": moment,
                "applied_by": actor, "approved_by": approved_by or None,
                "rationale": rationale.strip(),
                "detail": (planned["detail"] + ". Recorded on the evidence "
                           "chain as a governance act: a configuration that "
                           "applied silently would let somebody change every "
                           "gate in the estate with a git push and no "
                           "approval")}

    # ------------------------------------------------------------------ what
    @staticmethod
    def boundary() -> Dict[str, Any]:
        """What is configuration, what is code, and why the line is where it is."""
        return {
            "configurable": [{"section": k, "is": v}
                             for k, v in CONFIGURABLE.items()],
            "not_configurable": [{"section": k, "why": v}
                                 for k, v in NOT_CONFIGURABLE.items()],
            "format": FORMAT,
            "detail": ("configuration-as-code done naively to a governance "
                       "platform is the most effective way to defeat one: the "
                       "gates and the git repository end up with the same "
                       "approval process, and that process is a pull request "
                       "reviewed by whoever is on shift. So the line is "
                       "published and it does not move"),
        }


# --------------------------------------------------------------------- diff
def _key_of(section: str, row: Dict[str, Any]) -> str:
    for candidate in ("gate", "name", "metric", "urn", "act", "kind"):
        if row.get(candidate):
            return str(row[candidate])
    return json.dumps(row, sort_keys=True)[:64]


def _diff(section: str, current: Sequence[Dict[str, Any]],
          wanted: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """What would change in one section, and which way each change points."""
    held = {_key_of(section, r): r for r in current}
    asked = {_key_of(section, r): r for r in wanted}
    out = []
    for key in sorted(set(held) | set(asked)):
        before, after = held.get(key), asked.get(key)
        if before == after:
            continue
        direction = _direction(section, before, after)
        out.append({
            "section": section, "key": key,
            "before": before, "after": after,
            "change": ("added" if before is None else
                       "removed" if after is None else "changed"),
            "direction": direction,
            "what": _describe(section, key, before, after, direction),
        })
    return out


def _direction(section: str, before, after) -> str:
    """Whether a change lets more through. Computed, never asserted.

    Removing a gate loosens; adding one tightens. Raising an appetite limit
    loosens; lowering it tightens. Where the shape gives no reading the answer
    is `neutral` and it is not guessed — a wrong direction on a review screen is
    worse than none, because somebody stops reading the diff.
    """
    gating = ("policies", "warrant_profiles", "monitoring_defaults")
    if before is None:
        return TIGHTENS if section in gating else NEUTRAL
    if after is None:
        return LOOSENS if section in gating else NEUTRAL
    old, new = before.get("limit"), after.get("limit")
    if isinstance(old, (int, float)) and isinstance(new, (int, float)):
        if new > old:
            return LOOSENS
        if new < old:
            return TIGHTENS
    if section == "retraining":
        if after.get("auto_accept") and not before.get("auto_accept"):
            return LOOSENS
        if before.get("auto_accept") and not after.get("auto_accept"):
            return TIGHTENS
    return NEUTRAL


def _describe(section, key, before, after, direction) -> str:
    if before is None:
        return f"{section}/{key} added"
    if after is None:
        return (f"{section}/{key} removed"
                + (" — whatever it refused is no longer refused"
                   if direction == LOOSENS else ""))
    return (f"{section}/{key} changed"
            + (" and lets through more than it does today"
               if direction == LOOSENS else
               " and refuses more than it does today"
               if direction == TIGHTENS else ""))


def _digest(document: Dict[str, Any]) -> str:
    from db.database import digest
    return digest(document)
