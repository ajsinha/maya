"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Warrant profiles: templating the REQUEST, never the warrant.

The recurring ask is "warrants should be templated by kind of model", and it is
half right in a way worth being precise about, because the wrong half is
expensive.

**The document must not fork.** If a T4 warrant has a different *shape* from a
T3 warrant, every engine, replay path and audit query has to branch on model
type before it can read anything, and the branch grows a case per model family
forever. One grammar over seven families with no special case is the property
the design is built on; a per-category schema throws it away.

**The content already differs, and differs derivably.** The parameter kind, the
admissible verbs, the artifact block, the determinism, the required data
bindings — each is computed from a fact, not declared. Nothing needs a template
for any of it.

What is genuinely tedious is the *request*: the same verb, the same resource
ceiling and the same binding shape retyped for every warrant of a given kind. So
that is what a profile fills in, and it comes with three constraints that keep
it from becoming a taxonomy:

  1. **Selected by a predicate over derived facts**, never by a category
     somebody attached to a model. A declared taxonomy sitting beside a derived
     one is two answers to one question, and they will eventually disagree —
     `neural_network` labelled on a model whose `parameter_kind` says
     `calibration_set`, and no rule for which one wins. Selecting by the derived
     facts means a profile *cannot* disagree with the truth, because the truth
     is what chose it.

  2. **Defaults only, and only for keys a caller could have typed.** Everything
     that decides who may act, for what, in which environment and until when is
     refused at creation. A profile that could widen authority would be an
     authority mechanism wearing a convenience mechanism's clothes.

  3. **It never overrides a caller.** A profile fills holes. A value the caller
     supplied is theirs, including a value identical to the default, because
     "the caller asked for this" and "nobody said, so we chose" are different
     facts and only one of them is the caller's responsibility.

Several profiles may match. They compose by the same fold featuresets use —
left to right, rightmost wins, `{}` as the identity — ordered by **specificity**
so the most specific speaks last. That is a monoid, and saying so is what makes
`(A ∘ B) ∘ C` and `A ∘ (B ∘ C)` the same set rather than a question about the
order somebody happened to declare them in.

**Obligations do not live here.** "A T4 warrant in prod must carry a digest" is
not a default — a default is something you can drop. It is a law (L-W12) or a
policy gate, and both refuse rather than suggest. A profile that tries to carry
an obligation is refused, pointing at the two places that can hold one.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Tuple

from core.evidence import EvidenceEngine
from core.log import get_logger
from db import WarrantProfileRepository
from db.database import digest as canonical_digest

logger = get_logger(__name__)


class ProfileError(RuntimeError):
    """A profile operation was refused. The message always says why."""

    def __init__(self, code: str, detail: str, remediation: str = ""):
        super().__init__(detail)
        self.code, self.detail, self.remediation = code, detail, remediation

    def as_problem(self) -> Dict[str, str]:
        return {"error": self.code, "detail": self.detail,
                "remediation": self.remediation}


# The facts a predicate may test. Closed, and every one of them is DERIVED by
# the platform from the version's kernel or the model's record — there is no
# entry here that somebody types as free text on the model.
SELECTABLE_FACTS: Dict[str, str] = {
    "trainability_class": "T0-T8, derived from how the parameter object is inhabited",
    "parameter_kind": "what inhabits P: coefficients, weights, a calibration set",
    "fit_procedure": "how P is filled: estimate, calibrate, train, configure",
    "runtime": "how the kernel becomes something an engine can invoke",
    "artifact_format": "the serialised form, where there is one",
    "environment": "prod, uat, dev — selecting by it is not widening authority",
    "tier": "the model's risk tier, as assessed",
    "domain": "credit, markets, operations",
    "model_class": "the fibre the model belongs to",
}

# What a profile may fill in. Each is something the caller could have typed on
# the request, and each is re-validated by the grammar afterwards exactly as if
# they had.
DEFAULTABLE: Dict[str, str] = {
    "verb": "the operation, when the caller did not name one",
    "max_seconds": "the resource ceiling for a run",
    "mode": "batch or streaming",
    "inputs": "the data bindings a run of this shape usually reads",
    "outputs": "where the results usually go",
}

# What a profile may NEVER fill in, because filling it in would decide who may
# act rather than save them typing. Refused at creation: a check performed when
# the profile is written is a check nobody can forget to perform at use.
AUTHORITY_KEYS: Tuple[str, ...] = (
    "principal", "declared_use", "environment", "urn", "semver", "model_urn",
    "ttl_seconds", "grace_seconds", "binding_kind", "warrant_id", "signature",
    "governance", "authority", "subject", "trainability_class",
)

MAX_NAME = 64


class WarrantProfileRegister:
    """Named, versioned request defaults, selected by derived facts."""

    def __init__(self, repo: WarrantProfileRepository, evidence: EvidenceEngine):
        self.repo, self.evidence = repo, evidence

    # ---------------------------------------------------------------- create
    def create(self, name: str, when: Optional[Dict[str, Any]] = None,
               defaults: Optional[Dict[str, Any]] = None, note: str = "",
               actor: str = "system") -> Dict[str, Any]:
        """Register a profile version. Versions are immutable, like everything else."""
        name = (name or "").strip()
        if not name or len(name) > MAX_NAME:
            raise ProfileError(
                "profile_name_required",
                f"a profile needs a name of 1 to {MAX_NAME} characters",
                "name it for the shape it serves, not for the model that "
                "prompted it — a profile called 'fraud_nn' will be wrong the "
                "day the second network arrives")
        when = self._check_predicate(when or {})
        defaults = self._check_defaults(defaults or {})

        row = {"name": name, "version": self.repo.next_version(name),
               "when_facts": when, "defaults": defaults, "note": note,
               # The fold orders by how many facts a profile tests, so the most
               # specific speaks last and wins. Storing it means the ordering is
               # a column rather than a sort somebody has to remember to apply.
               "specificity": len(when),
               "retired": 0,
               "digest": canonical_digest({"when": when, "defaults": defaults}),
               "created_by": actor, "created_at": time.time()}
        self.repo.add(row)
        self.evidence.append("warrant_profile_created", "warrant_profile", row["id"],
                             {"name": name, "version": row["version"],
                              "when": when, "defaults": sorted(defaults),
                              "digest": row["digest"]}, actor=actor)
        logger.info("warrant profile %s v%s registered over %s facts",
                    name, row["version"], len(when))
        return row

    def retire(self, name: str, actor: str = "system") -> Dict[str, Any]:
        """Stop a profile applying. The version stays; warrants it shaped stand."""
        row = self.current(name)
        if row is None:
            raise ProfileError("no_such_profile", f"no profile named '{name}'",
                               "list the profiles to see what is registered")
        self.repo.set({"retired": 1, "retired_at": time.time(),
                       "retired_by": actor}, id=row["id"])
        self.evidence.append("warrant_profile_retired", "warrant_profile",
                             row["id"], {"name": name, "version": row["version"]},
                             actor=actor)
        return self.repo.one(id=row["id"])

    # ------------------------------------------------------------------ read
    def current(self, name: str) -> Optional[Dict[str, Any]]:
        """The live version of one profile, or None."""
        rows = [r for r in self.repo.many(name=name) if not r["retired"]]
        return max(rows, key=lambda r: r["version"]) if rows else None

    def list(self) -> List[Dict[str, Any]]:
        live: Dict[str, Dict[str, Any]] = {}
        for row in self.repo.many():
            if row["retired"]:
                continue
            held = live.get(row["name"])
            if held is None or row["version"] > held["version"]:
                live[row["name"]] = row
        return sorted(live.values(), key=lambda r: (r["specificity"], r["name"]))

    # --------------------------------------------------------------- resolve
    def matching(self, facts: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Every live profile whose predicate the facts satisfy, least specific first.

        A profile with an empty predicate matches everything — that is the
        identity of the fold, and it is the right way to write "this applies
        unless something more specific says otherwise".
        """
        return [p for p in self.list() if self._matches(p["when_facts"], facts)]

    def apply(self, facts: Dict[str, Any],
              request: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Fold the matching profiles into the request, without overriding it.

        Returns the filled request together with the derivation: which profiles
        matched, in which order, and which key each value came from. A default
        whose origin cannot be named is a value nobody can argue with later.
        """
        request = dict(request or {})
        matched = self.matching(facts)
        folded: Dict[str, Any] = {}
        origin: Dict[str, str] = {}
        for profile in matched:                       # left to right, rightmost wins
            for key, value in (profile["defaults"] or {}).items():
                folded[key] = value
                origin[key] = f"{profile['name']}@{profile['version']}"

        applied: Dict[str, str] = {}
        for key, value in folded.items():
            if request.get(key) is None:
                request[key] = value
                applied[key] = origin[key]

        return {"request": request,
                "profiles": [{"name": p["name"], "version": p["version"],
                              "when": p["when_facts"],
                              "specificity": p["specificity"]} for p in matched],
                "applied": applied,
                "detail": (f"{len(applied)} value(s) filled from "
                           f"{len(matched)} profile(s)" if matched
                           else "no profile matches these facts; "
                                "the request stands as the caller wrote it")}

    # ------------------------------------------------------------------ parts
    @staticmethod
    def _matches(when: Dict[str, Any], facts: Dict[str, Any]) -> bool:
        for fact, allowed in (when or {}).items():
            value = facts.get(fact)
            if value is None or value not in allowed:
                return False
        return True

    @staticmethod
    def _check_predicate(when: Dict[str, Any]) -> Dict[str, List[Any]]:
        """Every key a derived fact, every value a non-empty list of allowed values."""
        out: Dict[str, List[Any]] = {}
        for fact, allowed in when.items():
            if fact not in SELECTABLE_FACTS:
                raise ProfileError(
                    "unknown_profile_fact",
                    f"'{fact}' is not a fact a profile may select on",
                    "select on facts the platform DERIVES — "
                    + ", ".join(sorted(SELECTABLE_FACTS))
                    + " — never on a category attached to the model, which "
                      "would be a second taxonomy able to disagree with the first")
            values = allowed if isinstance(allowed, (list, tuple)) else [allowed]
            if not values:
                raise ProfileError(
                    "empty_predicate",
                    f"the predicate on '{fact}' allows nothing, so this profile "
                    f"can never match",
                    "list the values it applies to, or drop the key entirely — "
                    "an absent key matches everything")
            out[fact] = list(values)
        return out

    @staticmethod
    def _check_defaults(defaults: Dict[str, Any]) -> Dict[str, Any]:
        for key in defaults:
            if key in AUTHORITY_KEYS:
                raise ProfileError(
                    "authority_not_defaultable",
                    f"'{key}' decides who may act, for what, or until when, so a "
                    f"profile may not supply it",
                    "authority is granted per principal and per use, never "
                    "inherited from a template; if this is an obligation rather "
                    "than a convenience, write it as a policy on the "
                    "'warrant:resolve' gate, which refuses instead of suggesting")
            if key not in DEFAULTABLE:
                raise ProfileError(
                    "not_defaultable",
                    f"'{key}' is not something a profile may fill in",
                    "a profile fills in what a caller could have typed: "
                    + ", ".join(sorted(DEFAULTABLE)))
        if not defaults:
            raise ProfileError(
                "empty_profile",
                "this profile supplies no defaults, so it would do nothing",
                "give it at least one default, or delete it — a profile that "
                "matches and changes nothing reads as a control that ran")
        return dict(defaults)


def facts_for(model: Dict[str, Any], version: Dict[str, Any],
              environment: str) -> Dict[str, Any]:
    """The facts a predicate is evaluated against, all of them derived.

    Assembled here rather than at each call site so there is one answer to "what
    can a profile see", and so adding a fact is a change to this function rather
    than to every caller.
    """
    kernel = ((version.get("manifest") or {}).get("kernel") or {})
    return {
        "trainability_class": version.get("trainability_class"),
        "parameter_kind": version.get("parameter_kind"),
        "fit_procedure": version.get("fit_procedure"),
        "runtime": kernel.get("runtime") or "descriptor_only",
        "artifact_format": kernel.get("artifact_format"),
        "environment": environment,
        "tier": model.get("tier"),
        "domain": model.get("domain"),
        "model_class": model.get("model_class"),
    }
