"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Extracts for supervisory returns, and the sentence that governs all of them.

**An extract is not a filing.** MAYA produces the fields it holds, from the
register, with each one traced to where it came from. It does not submit
anything, it does not sign anything, and it does not fill in a box it cannot
answer. That last part is the whole of the design.

Every model inventory return has fields a register genuinely does not know —
who the authorised representative is, which notified body assessed it, the
serial number of an EU declaration of conformity. A tool that emits a plausible
value in those boxes has produced the single most dangerous artefact in this
codebase, because unlike every other output here **it gets sent to a
supervisor**. So a field the register cannot answer is emitted as `not_held`,
named in the extract, counted in the header, and the header says the return is
incomplete. A firm that files it anyway is making a decision; a firm handed a
full-looking spreadsheet is not.

**The population is derived and published, and so is the exclusion.** Which
models are high-risk under Annex III is computed from the designations and
purpose classes the register already carries, not from a checkbox somebody
ticked at onboarding — because a checkbox is the field that is wrong, and a
return whose population was silently filtered is one nobody downstream can
check. Models *out* of scope are listed with the reason they are out. A
regulator's first question about a population of eleven is what happened to the
twelfth.

**No return is a legal opinion.** The scoping rules here encode a reading of
Annex III and of SS1/23; where the reading is contestable the extract says so
and names the fact it turned on, so the firm's counsel can disagree with a
specific derivation rather than with a number.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Sequence, Tuple

from core.log import get_logger
from core.validation.vendor import CHECKLIST

logger = get_logger(__name__)

HELD, DERIVED, NOT_HELD = "held", "derived", "not_held"

#: Purpose classes that put a model inside Annex III on their own. Credit
#: scoring of natural persons is named in the Annex; the others follow the same
#: reading — a decision taken about a person, at scale, by a machine.
ANNEX_III_PURPOSES: Tuple[str, ...] = ("credit_decision", "clinical_decision",
                                       "customer_facing", "policy_decision")

#: Designations that put a model inside Annex III whatever its purpose class.
ANNEX_III_DESIGNATIONS: Tuple[str, ...] = ("consumer_impacting",
                                           "safety_critical")


class ReturnError(RuntimeError):
    """A return could not be produced. The message says which return."""

    def __init__(self, code: str, detail: str, remediation: str = ""):
        super().__init__(detail)
        self.code, self.detail, self.remediation = code, detail, remediation

    def as_problem(self) -> Dict[str, str]:
        return {"error": self.code, "detail": self.detail,
                "remediation": self.remediation}


def _field(name: str, describes: str, source: str, cite: str = "") -> Dict[str, str]:
    return {"field": name, "describes": describes, "source": source,
            "reference": cite}


#: The returns this platform can extract for, what each field is, and — for the
#: fields it cannot answer — that it cannot. Held as data so the gaps are
#: inspectable before anybody runs one, rather than discovered in the output.
RETURNS: Dict[str, Dict[str, Any]] = {
    "ai_act_registration": {
        "title": "EU AI Act — high-risk system registration",
        "reference": "Regulation (EU) 2024/1689, Arts. 49 and 71, Annex VIII",
        "population": ("models the register's own designations and purpose "
                       "classes place inside Annex III"),
        "fields": [
            _field("provider", "the legal entity placing the system on the market",
                   HELD, "Annex VIII §1"),
            _field("system_name", "the trade name of the AI system", HELD),
            _field("urn", "the provider's internal identifier", HELD),
            _field("intended_purpose", "what the system is for", HELD,
                   "Annex VIII §5"),
            _field("annex_iii_ground", "which Annex III point it falls under",
                   DERIVED, "Annex III"),
            _field("status", "on the market, withdrawn, or not yet placed", DERIVED),
            _field("member_states", "where it is or will be made available",
                   NOT_HELD, "Annex VIII §4"),
            _field("authorised_representative",
                   "the representative where the provider is outside the Union",
                   NOT_HELD, "Annex VIII §2"),
            _field("conformity_assessment_body",
                   "the notified body, where one was involved", NOT_HELD,
                   "Annex VIII §7"),
            _field("declaration_of_conformity",
                   "the EU declaration and its identifier", NOT_HELD,
                   "Annex VIII §8"),
            _field("instructions_for_use",
                   "the electronic instructions accompanying the system",
                   NOT_HELD, "Annex VIII §9"),
        ],
    },
    "model_inventory": {
        "title": "Supervisory model inventory",
        "reference": "SS1/23 principle 2; SR 11-7 model inventory",
        "population": "every model in the register",
        "fields": [
            _field("urn", "the identifier", HELD),
            _field("name", "what it is called", HELD),
            _field("legal_entity", "which entity owns it", HELD),
            _field("domain", "the business area", HELD),
            _field("owner", "the accountable individual", HELD),
            _field("tier", "the firm's own risk tier", HELD),
            _field("purpose", "what it is used for", HELD),
            _field("origin", "developed, vendor or inherited", HELD),
            _field("status", "its lifecycle state", HELD),
            _field("in_force", "whether it may currently be resolved", DERIVED),
            _field("last_validated", "when the last validation concluded", DERIVED),
            _field("validation_outcome", "what it concluded", DERIVED),
            _field("open_findings", "findings not yet closed", DERIVED),
            _field("blocking_findings", "findings that refuse resolution", DERIVED),
            _field("monitored", "whether an active monitor exists", DERIVED),
            _field("materiality_amount",
                   "the exposure the model decides on, in currency", NOT_HELD),
        ],
    },
    "third_party_models": {
        "title": "Third-party and vendor model return",
        "reference": "SS1/23 principle 1.4; EBA outsourcing guidelines",
        "population": "models the register records as not built by this firm",
        "fields": [
            _field("urn", "the identifier", HELD),
            _field("name", "what it is called", HELD),
            _field("vendor", "who built it", DERIVED),
            _field("legal_entity", "which entity uses it", HELD),
            _field("tier", "the firm's own risk tier", HELD),
            _field("assessment_status",
                   "how far the vendor assessment has got", DERIVED),
            _field("items_discharged_by_vendor",
                   "checklist items only the vendor can answer", DERIVED),
            _field("contract_reference", "the agreement it is used under",
                   NOT_HELD),
            _field("exit_plan", "what happens if the vendor withdraws it",
                   NOT_HELD),
        ],
    },
}


class RegulatoryReturns:
    """Extracts for supervisory returns, with the gaps named inside them."""

    def __init__(self, registry, validation=None, findings=None,
                 monitoring=None, vendor=None):
        self.registry = registry
        self.validation, self.findings = validation, findings
        self.monitoring, self.vendor = monitoring, vendor

    # ------------------------------------------------------------- catalogue
    @staticmethod
    def catalogue() -> Dict[str, Any]:
        """Every return, and which of its fields the register cannot answer."""
        out = []
        for key, spec in RETURNS.items():
            gaps = [f for f in spec["fields"] if f["source"] == NOT_HELD]
            out.append({
                "return": key, "title": spec["title"],
                "reference": spec["reference"], "population": spec["population"],
                "fields": spec["fields"],
                "not_held": [f["field"] for f in gaps],
                "complete": not gaps,
                "detail": (f"{len(spec['fields'])} field(s), of which "
                           f"{len(gaps)} cannot be answered from the register"
                           if gaps else
                           "every field comes from the register")})
        return {"returns": out, "count": len(out),
                "detail": ("MAYA extracts and does not file. A field the "
                           "register cannot answer is emitted as not held and "
                           "counted in the header, because a plausible value "
                           "in a box nobody knew the answer to is the one "
                           "output here that gets sent to a supervisor")}

    # ----------------------------------------------------------------- extract
    def extract(self, name: str, now: Optional[float] = None,
                scope=None) -> Dict[str, Any]:
        """Produce one return over the population it applies to."""
        if name not in RETURNS:
            raise ReturnError(
                "unknown_return", f"there is no return called '{name}'",
                f"the platform extracts for {', '.join(sorted(RETURNS))}")
        spec = RETURNS[name]
        moment = now if now is not None else time.time()
        models = [m for m in self.registry.list()
                  if scope is None or scope.unrestricted or scope.permits(m)]
        included, excluded = self._population(name, models)
        rows = [getattr(self, f"_row_{name}")(m, moment) for m in included]
        gaps = [f["field"] for f in spec["fields"] if f["source"] == NOT_HELD]
        missing = self._missing(spec, rows)
        return {
            "return": name, "title": spec["title"],
            "reference": spec["reference"],
            "extracted_at": moment,
            "fields": [f["field"] for f in spec["fields"]],
            "field_sources": spec["fields"],
            "rows": rows, "count": len(rows),
            "excluded": excluded,
            "not_held": gaps,
            "empty_in_this_extract": missing,
            "complete": not gaps and not missing,
            "detail": self._detail(spec, rows, excluded, gaps, missing),
        }

    @staticmethod
    def _detail(spec, rows, excluded, gaps, missing) -> str:
        out = (f"{len(rows)} model(s) in scope for {spec['title']}; "
               f"{len(excluded)} out of scope and listed with the reason, "
               f"because a regulator's first question about a population of "
               f"{len(rows)} is what happened to the {len(rows) + 1}th")
        if gaps:
            out += (f". {len(gaps)} field(s) — {', '.join(gaps)} — are not held "
                    f"by the register at all and are emitted empty. **This "
                    f"extract is not a filing**: filling them in is a decision "
                    f"somebody has to take, and a tool that guessed at them "
                    f"would be guessing at something sent to a supervisor")
        if missing:
            out += (f". A further {len(missing)} field(s) are held in principle "
                    f"and empty for every row here: {', '.join(missing)}")
        return out

    @staticmethod
    def _missing(spec: Dict[str, Any],
                 rows: Sequence[Dict[str, Any]]) -> List[str]:
        """Fields the register could answer and did not, for any row.

        Different from `not_held` and worth separating: one is a limit of the
        platform and the other is a gap in this firm's data, and only the
        second is somebody's work.
        """
        if not rows:
            return []
        answerable = [f["field"] for f in spec["fields"]
                      if f["source"] != NOT_HELD]
        return [f for f in answerable
                if all(r.get(f) in (None, "", []) for r in rows)]

    # ---------------------------------------------------------- the population
    def _population(self, name: str,
                    models: Sequence[Dict[str, Any]]) -> Tuple[List, List]:
        included: List[Dict[str, Any]] = []
        excluded: List[Dict[str, Any]] = []
        for model in models:
            verdict = self._in_scope(name, model)
            (included if verdict["included"] else excluded).append(
                model if verdict["included"] else
                {"urn": model["urn"], "why": verdict["why"]})
        return included, excluded

    def _in_scope(self, name: str, model: Dict[str, Any]) -> Dict[str, Any]:
        if name == "model_inventory":
            return {"included": True, "why": "every registered model"}
        if name == "third_party_models":
            origin = (model.get("origin") or "").lower()
            if origin in ("vendor", "third_party", "acquired"):
                return {"included": True, "why": f"origin is {origin}"}
            return {"included": False,
                    "why": (f"origin is '{origin or 'unrecorded'}', so the "
                            f"register does not place this model with a third "
                            f"party. An unrecorded origin is a gap rather than "
                            f"a negative answer")}
        return self._annex_iii(model)

    @staticmethod
    def _annex_iii(model: Dict[str, Any]) -> Dict[str, Any]:
        """Whether Annex III reaches this model, and on what fact.

        Derived from the designations and purpose class the register already
        carries. A checkbox at onboarding would be the field that is wrong, and
        a population nobody can re-derive is one nobody downstream can check.
        """
        designations = list(model.get("designations") or [])
        hit = [d for d in designations if d in ANNEX_III_DESIGNATIONS]
        if hit:
            return {"included": True,
                    "why": f"designated {', '.join(hit)}",
                    "ground": hit[0]}
        purpose = (model.get("attributes") or {}).get("purpose_class") or ""
        if purpose in ANNEX_III_PURPOSES:
            return {"included": True,
                    "why": f"purpose class is {purpose}", "ground": purpose}
        return {"included": False,
                "why": (f"neither designated {' nor '.join(ANNEX_III_DESIGNATIONS)} "
                        f"nor of a purpose class Annex III names"
                        + (f" — its purpose class is '{purpose}'" if purpose else
                           ", and it carries no purpose class at all, which is "
                           "an absence rather than a negative answer"))}

    # ------------------------------------------------------------------- rows
    def _row_ai_act_registration(self, model: Dict[str, Any],
                                 now: float) -> Dict[str, Any]:
        ground = self._annex_iii(model)
        versions = self.registry.versions(model["urn"])
        approved = [v for v in versions if v.get("status") == "approved"]
        return {
            "provider": model.get("legal_entity") or "",
            "system_name": model.get("name") or "",
            "urn": model["urn"],
            "intended_purpose": model.get("purpose") or "",
            "annex_iii_ground": ground.get("ground", ""),
            "status": ("on the market" if approved else "not yet placed"),
            # Emitted, empty, and named in the header. Not guessed.
            "member_states": "",
            "authorised_representative": "",
            "conformity_assessment_body": "",
            "declaration_of_conformity": "",
            "instructions_for_use": "",
        }

    def _row_model_inventory(self, model: Dict[str, Any],
                             now: float) -> Dict[str, Any]:
        versions = self.registry.versions(model["urn"])
        opened = self.findings.open_for(model["id"]) if self.findings else []
        episodes = ([e for e in self.validation.for_model(model["urn"])
                     if e.get("completed_at")] if self.validation else [])
        last = max(episodes, key=lambda e: e["completed_at"]) if episodes else None
        monitors = (self.monitoring.registry.for_model(model["id"])
                    if self.monitoring else [])
        return {
            "urn": model["urn"], "name": model.get("name") or "",
            "legal_entity": model.get("legal_entity") or "",
            "domain": model.get("domain") or "",
            "owner": model.get("owner") or "",
            "tier": model.get("tier"),
            "purpose": model.get("purpose") or "",
            "origin": model.get("origin") or "",
            "status": model.get("status") or "",
            "in_force": (any(v.get("status") == "approved" for v in versions)
                         and not any(f["blocking"] for f in opened)),
            "last_validated": last["completed_at"] if last else None,
            "validation_outcome": (last.get("outcome") or "") if last else "",
            "open_findings": len(opened),
            "blocking_findings": sum(1 for f in opened if f["blocking"]),
            "monitored": any(m["status"] == "active" for m in monitors),
            # The register holds a tier and an exposure band, not a currency
            # figure per model. Emitted empty rather than approximated.
            "materiality_amount": "",
        }

    def _row_third_party_models(self, model: Dict[str, Any],
                                now: float) -> Dict[str, Any]:
        assessment = None
        if self.vendor is not None:
            episodes = self.vendor.for_model(model["urn"])
            assessment = episodes[-1] if episodes else None
        items = (self.vendor.items.many(assessment_id=assessment["id"])
                 if assessment and self.vendor else [])
        return {
            "urn": model["urn"], "name": model.get("name") or "",
            "vendor": (assessment or {}).get("vendor") or "",
            "legal_entity": model.get("legal_entity") or "",
            "tier": model.get("tier"),
            "assessment_status": (assessment.get("state") or "")
            if assessment else "never assessed",
            # From the checklist rather than from the row: which party can
            # discharge an item is a property of the QUESTION and not of the
            # answer somebody happened to give.
            "items_discharged_by_vendor": sum(
                1 for i in items
                if CHECKLIST.get(i.get("item") or "", {}).get(
                    "discharged_by") == "vendor"),
            "contract_reference": "",
            "exit_plan": "",
        }
