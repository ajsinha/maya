"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

What this model was approved for, against what it is actually used for.

Every individual call is already legitimate. A declared use is checked at
resolution against the grant that carries it, and a call for a use nobody holds
is refused on the spot — so there is no single invocation anywhere in the log
that anybody should object to. Off-label use is not a bad call. It is a
**pattern of good ones**, and nothing was looking at the pattern.

Four shapes, and the interesting thing about them is that three are invisible
per-call by construction:

**A use nobody grants, tried repeatedly.** These are all refused, so a
control-effectiveness report shows the platform working perfectly. What it does
not show is that somebody has attempted the same off-label use four hundred
times this quarter, which is not a control success — it is a team that believes
this model answers a question it was not approved for, and they will eventually
find a way to ask it that nobody is watching.

**A grant nobody exercises.** Least privilege in the other direction, and it is
the warrant catalogue's business rather than this one's.

**A purpose the traffic does not match.** The model's registered purpose says
one thing; ninety per cent of its calls arrive under a use that does not appear
in it. Both the purpose and the grants were approved, separately, by people who
never saw them side by side.

**A use that lives in a lower environment and appears in production.** Not
itself wrong — that is what promotion looks like — but it is the moment when
somebody should have re-read the purpose, and it usually is not.

This raises a finding on the first shape only. The others are reported and left
to a person, because a register that raised a finding every time a model's
traffic was uneven would be a register whose findings nobody reads.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

DAY = 86400.0

#: How many refused attempts at one unheld use, in the window, before this
#: stops being somebody's mistake and starts being a team's intention.
DEFAULT_ATTEMPT_THRESHOLD = 20

#: How far back to look. A quarter, because that is the period over which a
#: pattern is a pattern rather than a bad week.
DEFAULT_WINDOW_DAYS = 90

#: What share of traffic makes one use *the* use of a model.
DOMINANT_SHARE = 0.6


class UseReconciliation:
    """Compares what a model is approved for against what it is used for."""

    def __init__(self, invocations, warrants, registry, findings=None,
                 attempt_threshold: int = DEFAULT_ATTEMPT_THRESHOLD,
                 window_days: int = DEFAULT_WINDOW_DAYS):
        self.invocations, self.warrants = invocations, warrants
        self.registry, self.findings = registry, findings
        self.attempt_threshold = attempt_threshold
        self.window_days = window_days

    # ------------------------------------------------------------- reconcile
    def for_model(self, urn: str, now: Optional[float] = None) -> Dict[str, Any]:
        model = self.registry.require(urn)
        moment = now if now is not None else time.time()
        since = moment - self.window_days * DAY

        granted = {g.get("declared_use") for g in self.warrants.grants_for(urn)
                   if g.get("declared_use")}
        rows = [r for r in
                self.invocations.for_model(model["id"])["invocations"]
                if (r.get("at") or 0) >= since]

        exercised: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            use = row.get("declared_use") or "(none)"
            entry = exercised.setdefault(
                use, {"use": use, "calls": 0, "refused": 0, "granted": False,
                      "principals": set(), "environments": set()})
            entry["calls"] += 1
            if row["outcome"] == "refused":
                entry["refused"] += 1
            entry["principals"].add(row.get("principal") or "")
            entry["environments"].add(row.get("environment") or "")

        for use, entry in exercised.items():
            entry["granted"] = use in granted
            entry["principals"] = sorted(entry["principals"])
            entry["environments"] = sorted(entry["environments"])
            entry["share"] = round(entry["calls"] / len(rows), 4) if rows else 0.0

        off_label = sorted(
            (e for e in exercised.values()
             if not e["granted"] and e["refused"] >= self.attempt_threshold),
            key=lambda e: -e["refused"])
        attempted = sorted((e for e in exercised.values() if not e["granted"]),
                           key=lambda e: -e["calls"])
        unexercised = sorted(granted - set(exercised))
        promoted = sorted(e["use"] for e in exercised.values()
                          if e["granted"] and len(e["environments"]) > 1)

        return {
            "urn": urn, "purpose": model.get("purpose"),
            "window_days": self.window_days, "invocations": len(rows),
            "granted_uses": sorted(granted),
            "exercised": sorted(exercised.values(), key=lambda e: -e["calls"]),
            "off_label": off_label,
            "attempted_without_a_grant": attempted,
            "granted_but_never_exercised": unexercised,
            "crossed_environments": promoted,
            "purpose_mismatch": self._purpose_mismatch(model, exercised),
            "detail": self._detail(rows, off_label, attempted, unexercised),
        }

    def _purpose_mismatch(self, model: Dict[str, Any],
                          exercised: Dict[str, Dict[str, Any]]
                          ) -> Optional[Dict[str, Any]]:
        """The dominant use, where the registered purpose does not mention it.

        A deliberately crude check — substring against the purpose text — and
        crude is the right shape here. It cannot be made precise without the
        purpose being structured, which is `FR-INV-005`'s job, and a precise
        answer to the wrong question would be worse than an approximate one to
        the right question. What it is looking for is the case where a model's
        prose says one thing and nine calls in ten say another, and both were
        approved by people who never saw them side by side.
        """
        if not exercised:
            return None
        dominant = max(exercised.values(), key=lambda e: e["calls"])
        # Strictly more than three calls in five, so an evenly split model is
        # not flagged. A model used for two approved things is not a model
        # being misused, and flagging it would be how this report stops being
        # read — which costs more than the case it would have caught.
        if dominant["share"] <= DOMINANT_SHARE or not dominant["granted"]:
            return None
        purpose = (model.get("purpose") or "").lower()
        words = [w for w in dominant["use"].replace("_", " ").split() if len(w) > 3]
        if any(w in purpose for w in words):
            return None
        return {
            "dominant_use": dominant["use"], "share": dominant["share"],
            "purpose": model.get("purpose"),
            "detail": (f"{dominant['share']:.0%} of calls arrive under "
                       f"'{dominant['use']}', and the registered purpose does "
                       f"not mention it. Both were approved — separately, by "
                       f"people who did not see them side by side — so this is "
                       f"a question for a person rather than a defect"),
        }

    # ----------------------------------------------------------- raise it
    def sweep(self, now: Optional[float] = None,
              actor: str = "system") -> Dict[str, Any]:
        """Reconcile every model, and raise a finding where it is warranted.

        Only the first shape raises. A register that raised a finding every
        time a model's traffic was uneven is a register whose findings nobody
        reads, and the other three shapes are questions for a person rather
        than defects.
        """
        raised, looked = [], 0
        for model in self.registry.list():
            looked += 1
            report = self.for_model(model["urn"], now=now)
            for entry in report["off_label"]:
                if self._raise_off_label(model, entry, report):
                    raised.append(f"{model['urn']}: {entry['use']}")
        return {"models": looked, "raised": raised, "count": len(raised),
                "detail": (f"{looked} model(s) reconciled; "
                           + (f"{len(raised)} off-label pattern(s) raised"
                              if raised else "no off-label pattern found"))}

    def _raise_off_label(self, model: Dict[str, Any], entry: Dict[str, Any],
                         report: Dict[str, Any]) -> bool:
        if self.findings is None:
            return False
        title = f"Off-label use attempted: {entry['use']}"
        # Idempotence: the same condition must not raise the same finding
        # twice, or a quarterly sweep produces a quarterly duplicate.
        for existing in self.findings.open_for(model["id"]):
            if existing.get("title") == title:
                return False
        self.findings.raise_finding(
            model["id"], "Medium", title=title,
            owner=model.get("owner") or "person/unknown",
            description=(
                f"{entry['refused']} attempt(s) to use this model under "
                f"'{entry['use']}' were refused in the last "
                f"{report['window_days']} days, by "
                f"{', '.join(entry['principals'][:5])}. Every one of those "
                f"refusals is the control working — which is exactly why "
                f"nothing was looking at them. A team attempting the same "
                f"unapproved use this persistently believes this model answers "
                f"a question it was not approved for, and will eventually find "
                f"a way to ask it that nobody is watching. Either grant the "
                f"use, having assessed it, or tell them why not."),
            category="use", source="self_identified", blocking=False)
        return True

    @staticmethod
    def _detail(rows: List[Dict[str, Any]], off_label: List[Dict[str, Any]],
                attempted: List[Dict[str, Any]],
                unexercised: List[str]) -> str:
        if not rows:
            return ("no invocations in the window, so nothing can be said "
                    "about actual use — which is itself worth knowing about a "
                    "model somebody is maintaining")
        out = f"{len(rows)} invocation(s) in the window"
        if off_label:
            out += (f"; {len(off_label)} use(s) attempted persistently without "
                    f"a grant, which is a pattern of refusals rather than a "
                    f"bad call")
        elif attempted:
            out += f"; {len(attempted)} use(s) attempted without a grant"
        if unexercised:
            out += f"; {len(unexercised)} granted use(s) nobody exercised"
        return out
