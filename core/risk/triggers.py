"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

When a tier stopped being the answer to the question it was answering.

## The gap this closes

`FR-TIER-005` asks for seven re-tiering triggers — exposure change, a new use,
a methodology change, a data-source change, a monitoring breach, a regulatory
change, and elapsed time. **Only the last one was watched**, as
`next_review_due`.

That is the largest remaining hole in the spine of this platform, because the
tier is not a label. It decides the size of the approval quorum, the review
cadence, the monitoring depth and the warrant's time to live. A model assessed
once at Tier 3 stays Tier 3 until its review date falls due, however much the
world has moved underneath it — and the review date for a Tier 3 is two years.

**The facts are all here already.** An assessment stores the facts it was made
from, and every one of the six unwatched triggers is a comparison between those
facts and what the register holds now. Nothing has to be observed, ingested or
inferred; it has to be *looked at*.

## What this does, and the one thing it will not do

**It detects and reports. It never re-tiers.**

An automatic re-tier would be the platform changing a governance decision that
nobody made — and changing it in the direction the arithmetic happened to point,
at a moment nobody chose. The tier is somebody's assessment. What a trigger says
is *the assessment was made against facts that have changed, and here is which
ones*, and a person assesses again.

That is weaker than it first sounds and it is the right weakness. The failure
this is really against is not an under-tiered model; it is an under-tiered model
**nobody knows is under-tiered**, because the assessment looks as current as the
day it was made.

## Why a trigger is not automatically a finding

A regulatory change fires on every in-scope model at once. Fifty findings with
fifty owners, each seeing a problem they cannot fix, is the exact shape of
`M-8` — and `core/validation/correlation.py` exists because of it.

So a sweep raises findings **under one named root per shared cause**. A tier
stale because *this* model's exposure tripled is that model's problem. Fifty
tiers stale because a regime activated is one problem, and the board pack should
be able to say so.

## The two things a trigger cannot tell you

**Whether the tier would actually change.** Re-running `tau` over the new facts
would answer that, and this deliberately does not: the complexity facts are
declared, and re-deriving them from stale declarations would produce a confident
number over inputs nobody re-stated. What a trigger reports is that the
*assessment* is out of date — which is the fact somebody can act on.

**Whether the change matters.** An exposure that moved 3% and one that tripled
both fire, unless a threshold is set — and `MATERIAL_MOVE` is a threshold with a
number in it, which means it is a judgement this platform is making on a firm's
behalf. It is configurable, it is stated, and it defaults deliberately high,
because a trigger that fires on every rounding is one somebody switches off.
"""
from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple

from core.log import get_logger

logger = get_logger(__name__)

#: The seven `FR-TIER-005` names, what each compares, and where the fact lives.
#: Published, because a trigger a reader cannot see the derivation of is one
#: they cannot argue with — and the first question anybody asks a re-tiering
#: alert is *why*.
TRIGGERS: Tuple[Tuple[str, str, str], ...] = (
    ("exposure_change",
     "the exposure the assessment was made against has moved materially",
     "`facts.exposure` on the assessment, against the latest **sourced** "
     "exposure. This trigger is answerable ONLY where the exposure has been "
     "attested (`H-8`), because the register holds no standing exposure "
     "column — outside an assessment, the only figure MAYA has is the one the "
     "assessment itself was made from, and comparing that against itself is "
     "vacuous"),
    ("new_use",
     "the model is approved for a use it was not assessed for",
     "`model_use` rows created after the assessment. Purpose class drives "
     "materiality directly, so a use added later can move the tier without "
     "anything else changing"),
    ("methodology_change",
     "a version arrived whose trainability class differs from the assessed one",
     "`model_version.trainability_class`, which is DERIVED from how the "
     "parameter object is inhabited and therefore cannot be gamed by "
     "re-declaring it"),
    ("data_source_change",
     "the featureset a version binds is not the one that was assessed",
     "the version's feature contract. A model refitted on a different "
     "population is a different model to anybody reading its tier"),
    ("monitoring_breach",
     "a monitor has breached since the assessment",
     "the breach register. A breach is evidence about the model's behaviour "
     "that the assessment did not have"),
    ("regulatory_change",
     "a regime activated or changed since the assessment",
     "the active regimes and when each was activated. This is the trigger that "
     "fires across the whole estate at once, which is why a sweep correlates"),
    ("elapsed_time",
     "the assessment is past its review date",
     "`next_review_due`. The only one that was watched before this module"),
)

#: How far exposure has to move before it counts. A threshold with a number in
#: it is a judgement this platform makes on a firm's behalf, so it is stated
#: and configurable, and it defaults high: a trigger that fires on every
#: rounding is a trigger somebody switches off, taking the real ones with it.
MATERIAL_MOVE = 0.25

#: A breach below this severity does not fire. `Low` breaches are common on a
#: busy estate and a tier is not the instrument for them.
BREACH_SEVERITIES = ("High", "Critical")


class RetierTriggers:
    """Reports which assessments stopped matching the facts they were made from."""

    def __init__(self, risk, registry, *, uses=None, breaches=None,
                 regimes=None, sourcing=None, findings=None, roots=None,
                 evidence=None, material_move: float = MATERIAL_MOVE):
        self.risk, self.registry = risk, registry
        self.uses, self.breaches, self.regimes = uses, breaches, regimes
        self.sourcing, self.findings = sourcing, findings
        self.roots, self.evidence = roots, evidence
        self.material_move = material_move

    # --------------------------------------------------------------- posture
    def posture(self) -> Dict[str, Any]:
        """What a trigger is, and the one thing it will not do."""
        return {
            "re_tiers_anything": False,
            "triggers": [{"trigger": t, "means": m, "derived_from": d}
                         for t, m, d in TRIGGERS],
            "material_move": self.material_move,
            "breach_severities": list(BREACH_SEVERITIES),
            "why_not_re_tier": (
                "an automatic re-tier would be the platform changing a "
                "governance decision nobody made, in the direction the "
                "arithmetic happened to point, at a moment nobody chose. The "
                "tier is somebody's assessment. A trigger says the assessment "
                "was made against facts that have changed and names which"),
            "what_it_cannot_tell_you": [
                "whether the tier would actually change. Re-running tau over "
                "the new facts would answer that, and this does not: the "
                "complexity facts are DECLARED, and re-deriving a tier from "
                "stale declarations produces a confident number over inputs "
                "nobody re-stated",
                "whether the change matters. That is what the threshold is "
                "for, and a threshold with a number in it is a judgement made "
                "on a firm's behalf — so it is stated rather than buried",
            ],
            "detail": (
                "the tier decides the approval quorum, the review cadence, the "
                "monitoring depth and the warrant's time to live. The failure "
                "this is against is not an under-tiered model; it is an "
                "under-tiered model NOBODY KNOWS is under-tiered, because the "
                "assessment looks as current as the day it was made"),
        }

    # ---------------------------------------------------------------- one model
    def of(self, urn: str, now: Optional[float] = None) -> Dict[str, Any]:
        """Which triggers have fired for one model since its last assessment."""
        model = self.registry.require(urn)
        moment = now if now is not None else time.time()
        assessment = self._latest(model["id"])
        if assessment is None:
            return {
                "urn": model["urn"], "assessed": False, "fired": [],
                "detail": ("this model has never been assessed, so there is no "
                           "tier for a trigger to be about. That is a "
                           "different and larger problem, and the register "
                           "already refuses to approve a version without one"),
            }
        facts = self._facts(assessment)
        answers = [a for a in (
            self._exposure(model, facts, assessment),
            self._new_use(model, assessment),
            self._methodology(model, facts),
            self._data_source(model, facts, assessment),
            self._breach(model, assessment),
            self._regulatory(assessment),
            self._elapsed(assessment, moment),
        ) if a is not None]
        # A trigger the register cannot answer is kept OUT of `fired`, so it
        # never inflates a stale count — and reported beside it, so it is never
        # mistaken for one that ran and found nothing.
        fired = [a for a in answers if a.get("state") != "cannot_check"]
        cannot = [a for a in answers if a.get("state") == "cannot_check"]
        return {
            "urn": model["urn"], "assessed": True,
            "tier": assessment["tier"],
            "assessed_at": assessment["assessed_at"],
            "fired": fired, "count": len(fired),
            "cannot_check": cannot,
            "re_tiers_anything": False,
            "detail": self._detail(model, assessment, fired, cannot, moment),
        }

    def _detail(self, model: Dict[str, Any], assessment: Dict[str, Any],
                fired: Sequence[Dict[str, Any]],
                cannot: Sequence[Dict[str, Any]], now: float) -> str:
        age = (now - (assessment.get("assessed_at") or now)) / 86400.0
        if fired:
            out = (f"{len(fired)} trigger(s) fired against this Tier "
                   f"{assessment['tier']} assessment, made {age:.0f} day(s) "
                   f"ago: {', '.join(f['trigger'] for f in fired)}. **Nothing "
                   f"has been re-tiered and nothing will be** — the tier is "
                   f"somebody's assessment, and what this says is that it was "
                   f"made against facts that have since changed")
        else:
            out = (f"nothing has changed under this Tier {assessment['tier']} "
                   f"assessment in {age:.0f} day(s). That is the ordinary "
                   f"answer and it is worth having: an assessment nobody has "
                   f"checked against the facts is indistinguishable from one "
                   f"that has been")
        if cannot:
            out += (f". **{len(cannot)} trigger(s) could not be checked at "
                    f"all** — {', '.join(c['trigger'] for c in cannot)}. That "
                    f"is reported rather than passed over, because a control "
                    f"that quietly cannot run looks exactly like one that ran "
                    f"and found nothing")
        return out

    # ------------------------------------------------------------ the triggers
    def _exposure(self, model: Dict[str, Any], facts: Dict[str, Any],
                  assessment: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Has the exposure moved since the assessment was made?

        **This turned out to be answerable only where the exposure has been
        sourced**, and finding that out is worth more than the trigger.

        The register holds no standing exposure column. An exposure is a fact
        supplied *at assessment time* and stored in that assessment's facts —
        so outside the assessment, the only figure MAYA has is the one the
        assessment was made from, and comparing it against itself answers
        nothing. The `H-8` fact-sourcing table is the first place a *current*
        exposure exists at all.

        So `FR-TIER-005`'s first trigger depends on `H-8` having been done for
        that model, and where it has not been, this reports **cannot check**
        rather than not firing. Silently not firing is how a control becomes
        green and inert.
        """
        was = _as_float(facts.get("exposure"))
        current = self._sourced_exposure(model)
        if was is None or was <= 0:
            return None
        if current is None:
            return self._cannot_check(
                "exposure_change",
                {"assessed_at_exposure": was},
                ("MAYA holds no exposure for this model other than the one "
                 "the assessment was made from, so there is nothing to "
                 "compare it against. **This is not the same as nothing "
                 "having changed.** Source the exposure "
                 "(`POST /fact-sourcing/model`) and the trigger becomes "
                 "answerable"))
        move = abs(current["value"] - was) / was
        if move < self.material_move:
            return None
        return self._fired("exposure_change", {
            "assessed_at_exposure": was, "current_exposure": current["value"],
            "move": round(move, 4), "threshold": self.material_move,
            "source": current["source"], "reference": current["reference"],
            "as_at": current["as_at"],
        }, (f"exposure moved {move:.0%} since the assessment, from "
            f"{was:,.0f} to {current['value']:,.0f} — attested to "
            f"{current['source']} ({current['reference']})"))

    def _sourced_exposure(self, model: Dict[str, Any]
                          ) -> Optional[Dict[str, Any]]:
        """The latest exposure somebody attested to a system of record.

        Nothing else will do. A figure typed into a form is the same kind of
        thing as the figure the assessment was made from, and a move between
        two of those is not evidence that anything happened.
        """
        if self.sourcing is None:
            return None
        try:
            rows = [r for r in self.sourcing.repo.many(model_id=model["id"])
                    if r.get("fact") == "exposure"]
        except Exception as exc:                 # pragma: no cover - defensive
            logger.warning("could not read fact sourcing for %s: %s",
                           model.get("urn"), exc)
            return None
        if not rows:
            return None
        latest = max(rows, key=lambda r: r.get("as_at") or 0)
        value = _as_float(latest.get("value"))
        return None if value is None else {
            "value": value, "source": latest.get("source"),
            "reference": latest.get("reference"), "as_at": latest.get("as_at")}

    @staticmethod
    def _cannot_check(trigger: str, evidence: Dict[str, Any],
                      detail: str) -> Dict[str, Any]:
        """A trigger the register cannot currently answer.

        Reported rather than skipped, and kept out of `fired` so it never
        inflates a stale count. A control that quietly cannot run looks exactly
        like one that ran and found nothing, which is the failure this whole
        codebase is arranged against.
        """
        return {"trigger": trigger, "state": "cannot_check",
                "evidence": evidence, "detail": detail}

    def _new_use(self, model: Dict[str, Any],
                 assessment: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if self.uses is None:
            return None
        since = assessment.get("assessed_at") or 0
        added = [u for u in self.uses.many(model_id=model["id"])
                 if (u.get("created_at") or 0) > since]
        if not added:
            return None
        return self._fired("new_use", {
            "uses": [u.get("declared_use") or u.get("name") for u in added],
        }, (f"{len(added)} approved use(s) were added after the assessment: "
            f"{', '.join(str(u.get('declared_use') or u.get('name')) for u in added[:4])}"
            f". Purpose class drives materiality directly, so a use added "
            f"later can move the tier without anything else changing"))

    def _methodology(self, model: Dict[str, Any],
                     facts: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        was = facts.get("trainability_class")
        versions = self.registry.versions(model["urn"])
        current = (_latest_version(versions) or {}).get("trainability_class")
        if not was or not current or was == current:
            return None
        return self._fired("methodology_change", {
            "assessed_class": was, "current_class": current,
        }, (f"the latest version is {current} and the assessment was made "
            f"against {was}. The class is DERIVED from how the parameter "
            f"object is inhabited, so this is a real change of method rather "
            f"than a re-declaration"))

    def _data_source(self, model: Dict[str, Any], facts: Dict[str, Any],
                     assessment: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        versions = self.registry.versions(model["urn"])
        since = assessment.get("assessed_at") or 0
        refitted = [v for v in versions
                    if (v.get("created_at") or 0) > since
                    and v.get("featureset")
                    and v.get("featureset") != facts.get("featureset")]
        if not refitted:
            return None
        return self._fired("data_source_change", {
            "featuresets": sorted({str(v.get("featureset")) for v in refitted}),
            "assessed_featureset": facts.get("featureset"),
        }, ("a version created after the assessment binds a different "
            "featureset. A model refitted on a different population is a "
            "different model to anybody reading its tier"))

    def _breach(self, model: Dict[str, Any],
                assessment: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if self.breaches is None:
            return None
        since = assessment.get("assessed_at") or 0
        hits = [b for b in self.breaches.many(model_id=model["id"])
                if (b.get("opened_at") or 0) > since
                and b.get("severity") in BREACH_SEVERITIES]
        if not hits:
            return None
        return self._fired("monitoring_breach", {
            "breaches": len(hits),
            "severities": sorted({b["severity"] for b in hits}),
        }, (f"{len(hits)} {'/'.join(sorted({b['severity'] for b in hits}))} "
            f"breach(es) opened after the assessment. A breach is evidence "
            f"about the model's behaviour that the assessment did not have"))

    def _regulatory(self, assessment: Dict[str, Any]
                    ) -> Optional[Dict[str, Any]]:
        if self.regimes is None:
            return None
        since = assessment.get("assessed_at") or 0
        try:
            active = self.regimes.active()
        except Exception as exc:                 # pragma: no cover - defensive
            logger.warning("could not read the active regimes: %s", exc)
            return None
        # `(activated or 0) > since`, with the parenthesis that was missing.
        #
        # It read `_as_float(_activated_at(...)) or since < 0`, which Python
        # parses as `_as_float(...) or (since < 0)` — so ANY regime carrying a
        # non-null activation timestamp matched, the assessment date was never
        # compared against anything, and `since` was used only in a test that
        # is false whenever a clock is sane. The trigger fired for regimes
        # activated years BEFORE the assessment while its own message said
        # "activated after the assessment", and because this is the trigger
        # that correlates across the estate it inflated every sweep and every
        # board-pack staleness figure.
        later = [r for r in active
                 if (_as_float(_activated_at(self.regimes, r)) or 0) > since]
        if not later:
            return None
        return self._fired("regulatory_change", {"regimes": later},
                           (f"{len(later)} regime(s) activated after the "
                            f"assessment: {', '.join(later)}. **This is the "
                            f"trigger that fires across the whole estate at "
                            f"once**, which is why a sweep correlates its "
                            f"findings under one cause"))

    @staticmethod
    def _elapsed(assessment: Dict[str, Any],
                 now: float) -> Optional[Dict[str, Any]]:
        due = assessment.get("next_review_due")
        if not due or now <= due:
            return None
        return {"trigger": "elapsed_time",
                "evidence": {"due_at": due,
                             "overdue_days": round((now - due) / 86400.0, 1)},
                "detail": (f"the assessment is {round((now - due) / 86400.0)} "
                           f"day(s) past its review date. The only trigger "
                           f"that was watched before this module")}

    @staticmethod
    def _fired(trigger: str, evidence: Dict[str, Any],
               detail: str) -> Dict[str, Any]:
        return {"trigger": trigger, "evidence": evidence, "detail": detail}

    # ------------------------------------------------------ across the estate
    def across_the_estate(self, now: Optional[float] = None) -> Dict[str, Any]:
        """How much of this estate's tiering is out of date, and why.

        The number this exists to produce, and it is a fact about the *tiering
        programme* rather than about any one model. An estate where a third of
        the assessments were made against facts that have since changed is one
        whose tier column means less than it looks like it means.
        """
        moment = now if now is not None else time.time()
        rows: List[Dict[str, Any]] = []
        by_trigger: Dict[str, int] = {}
        unanswerable: Dict[str, int] = {}
        never: List[str] = []
        models = self.registry.list()
        for model in models:
            answer = self.of(model["urn"], moment)
            if not answer["assessed"]:
                never.append(model["urn"])
                continue
            for blocked in answer.get("cannot_check") or []:
                unanswerable[blocked["trigger"]] = \
                    unanswerable.get(blocked["trigger"], 0) + 1
            if not answer["fired"]:
                continue
            rows.append({"urn": answer["urn"], "tier": answer["tier"],
                         "triggers": [f["trigger"] for f in answer["fired"]],
                         "count": answer["count"]})
            for fired in answer["fired"]:
                by_trigger[fired["trigger"]] = \
                    by_trigger.get(fired["trigger"], 0) + 1
        rows.sort(key=lambda r: -r["count"])
        total = len(models)
        return {
            "models": total, "stale": len(rows), "never_assessed": never,
            "by_trigger": by_trigger,
            # The coverage figure. A sweep reporting *nothing fired* over an
            # estate where half the triggers cannot be evaluated is reporting
            # its own blindness as an all-clear.
            "cannot_check": unanswerable,
            "rows": rows, "re_tiers_anything": False,
            "detail": (
                f"{len(rows)} of {total} assessment(s) were made against facts "
                f"that have since changed"
                + (f", most often {max(by_trigger, key=lambda k: by_trigger[k])}"
                   if by_trigger else "")
                + (f". {len(never)} model(s) have never been assessed at all"
                   if never else "")
                + (f". **{unanswerable.get('exposure_change', 0)} model(s) "
                   f"have no sourced exposure**, so the first trigger cannot "
                   f"be evaluated for them at all — not that nothing changed"
                   if unanswerable.get("exposure_change") else "")
                + ". This is a fact about the tiering PROGRAMME rather than "
                  "about any one model: an estate where a third of the "
                  "assessments are out of date is one whose tier column means "
                  "less than it looks like it means"),
        }

    # ------------------------------------------------------------- the sweep
    def sweep(self, *, actor: str = "system",
              now: Optional[float] = None) -> Dict[str, Any]:
        """Raise a finding per stale assessment, correlated by shared cause.

        A regulatory change fires on every in-scope model at once. Fifty
        findings with fifty owners, each seeing a problem they cannot fix, is
        the exact shape of `M-8` — so findings from a shared cause are raised
        under **one named root**, and the board pack can say they are one
        problem.
        """
        moment = now if now is not None else time.time()
        estate = self.across_the_estate(moment)
        if self.findings is None:
            return {**estate, "raised": [], "roots": [],
                    "detail": estate["detail"] + ". No finding register is "
                                                 "wired, so nothing was raised"}
        shared = self._shared_causes(estate["rows"])
        raised, roots = [], []
        for row in estate["rows"]:
            finding_id = self._raise(row, actor, moment)
            if finding_id:
                raised.append(finding_id)
        for trigger, urns in shared.items():
            root_id = self._correlate(trigger, urns, raised, actor)
            if root_id:
                roots.append({"trigger": trigger, "root_id": root_id,
                              "models": len(urns)})
        return {
            **estate, "raised": raised, "roots": roots,
            "detail": (estate["detail"]
                       + f". {len(raised)} finding(s) raised"
                       + (f", correlated under {len(roots)} named cause(s) — "
                          f"a regime activation is one problem across many "
                          f"models, not many problems" if roots else "")),
        }

    @staticmethod
    def _shared_causes(rows: Sequence[Dict[str, Any]]) -> Dict[str, List[str]]:
        """Triggers that fired across more than one model.

        Only `regulatory_change` does so by construction; the others are facts
        about one model. Computing it rather than hard-coding it means a
        trigger added later is correlated without anybody remembering to.
        """
        by_trigger: Dict[str, List[str]] = {}
        for row in rows:
            for trigger in row["triggers"]:
                by_trigger.setdefault(trigger, []).append(row["urn"])
        return {t: u for t, u in by_trigger.items() if len(u) > 1}

    def _raise(self, row: Dict[str, Any], actor: str,
               now: float) -> Optional[str]:
        try:
            model = self.registry.require(row["urn"])
            finding = self.findings.raise_finding(
                model_id=model["id"],
                title=f"tier {row['tier']} assessment is out of date",
                severity="Medium", source="tiering",
                detail=("fired: " + ", ".join(row["triggers"])
                        + ". The tier has NOT been changed — re-assess"),
                actor=actor)
            return finding.get("id")
        except Exception as exc:
            # A sweep that failed because one finding could not be raised
            # would lose the rest of the sweep as well.
            logger.warning("could not raise a re-tiering finding for %s: %s",
                           row["urn"], exc)
            return None

    def _correlate(self, trigger: str, urns: Sequence[str],
                   raised: Sequence[str], actor: str) -> Optional[str]:
        if self.roots is None or not raised:
            return None
        try:
            root = self.roots.open_root(
                title=f"{trigger} left {len(urns)} tier assessment(s) out of "
                      f"date",
                kind=("control_gap" if trigger == "regulatory_change"
                      else "population_shift"),
                detail=("one cause, many models. Each finding keeps its own "
                        "owner and due date — nothing was merged — and the "
                        "estate can now be read by cause as well as by symptom"),
                findings=list(raised), actor=actor)
            return root.get("id")
        except Exception as exc:
            logger.warning("could not correlate re-tiering findings: %s", exc)
            return None

    # ---------------------------------------------------------------- reading
    def _latest(self, model_id: str) -> Optional[Dict[str, Any]]:
        rows = self.risk.many(model_id=model_id)
        return max(rows, key=lambda r: r.get("assessed_at") or 0) \
            if rows else None

    @staticmethod
    def _facts(assessment: Dict[str, Any]) -> Dict[str, Any]:
        facts = assessment.get("facts")
        if isinstance(facts, dict):
            return facts
        try:
            return json.loads(facts or "{}")
        except (TypeError, ValueError) as exc:
            logger.warning("an assessment's facts are not readable: %s", exc)
            return {}


def _as_float(value: Any) -> Optional[float]:
    """A number, or None.

    Logged at debug rather than passed over: an exposure that is not a number
    is a fact the register holds and cannot compare, and the trigger then
    silently does not fire. That is the one outcome this module is arranged
    against, so the line exists to be found when somebody asks why a model
    never triggers.
    """
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        logger.debug("a tiering fact is not a number (%r): %s", value, exc)
        return None


def _activated_at(regimes: Any, name: str) -> Any:
    getter = getattr(regimes, "activated_at", None)
    return getter(name) if callable(getter) else 0


def _latest_version(versions: Sequence[Dict[str, Any]]
                    ) -> Optional[Dict[str, Any]]:
    return max(versions, key=lambda v: v.get("created_at") or 0) \
        if versions else None
