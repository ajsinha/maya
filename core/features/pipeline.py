"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The data upstream of the models, watched as carefully as the models.

Most "model failures" are data failures. The model was fine; the feed stopped, or
arrived a tenth of its usual size, or lost a column, or filled one with nulls —
and the model went on producing plausible numbers from it, because that is what
models do. Every monitor in this platform points at a model's scores, which is
to say at the last place the problem shows up.

**Nothing here requires a declaration.** A freshness SLA is the obvious design
and the wrong one: an SLA somebody sets at onboarding is an SLA nobody revisits,
and it is either so loose that it never fires or so tight that it fires until
somebody switches it off. What is used instead is the view's **own history**. A
view that has loaded every twenty-four hours for its last ten versions has told
you what it does, and the honest question is not *is this within the SLA* but
*has this stopped behaving like itself*.

That has one real consequence worth stating: a view with two or three versions
cannot be judged this way, and this says so rather than inventing a baseline
from one observation. A new feed is unmonitorable for a while, and pretending
otherwise is how a monitor gets a reputation for crying wolf in its first week.

Four questions, and the fourth is the one nothing else in the platform can ask.

**Freshness** — how long since the last load, against how long this view
normally goes between loads.

**Volume** — how many rows arrived, against how many normally do. A load a tenth
of its usual size is the classic silent failure: it succeeds, it is recorded, and
every downstream number quietly becomes an average of less.

**Schema** — which features arrived. Gaining one is usually somebody's work;
LOSING one is what breaks the featureset pinned to this view, and the two are
reported separately for that reason.

**Null rate** — per feature, against its own recent typical rate. This is the
one `FR-FEA-011`'s assertions cannot reach: an assertion catches a null rate
crossing a line somebody drew in advance, and this catches a null rate that
tripled while staying inside it.
"""
from __future__ import annotations

import statistics
import time
from itertools import pairwise
from typing import Any, Dict, List, Optional

DAY = 86400.0

#: How many prior versions make a baseline. Below this the answer is "not yet",
#: because a baseline built from one observation is a number with a false air of
#: authority.
MIN_HISTORY = 4

#: How many times its usual interval a view may go without loading before the
#: gap is worth reporting. Two, because one missed load is a late batch and two
#: is a stopped one.
STALE_MULTIPLE = 2.0

#: How far a row count may fall from the recent median before it is reported.
#: Half, because a feed at half its usual size is either a real change somebody
#: should know about or a partial load, and both want the same phone call.
VOLUME_DROP = 0.5

#: How far above the recent median a load may be. Looser than the drop, because
#: a backfill is a common and usually benign reason to see three times the rows,
#: while a tenth of them is almost never benign.
VOLUME_SPIKE = 3.0

#: How many times its own baseline a feature's null rate may rise. Three, and
#: with a floor below, because a rate going from 0.1% to 0.4% is a quadrupling
#: and is not news.
NULL_MULTIPLE = 3.0
NULL_FLOOR = 0.02


class PipelineHealth:
    """What the feeds under a model are doing, judged against their own past."""

    def __init__(self, views, findings=None, registry=None,
                 models_using=None):
        self.views, self.findings, self.registry = views, findings, registry
        self.models_using = models_using

    # ------------------------------------------------------------------ read
    def for_view(self, view_name: str,
                 now: Optional[float] = None) -> Dict[str, Any]:
        """The four questions, for one view."""
        moment = now if now is not None else time.time()
        versions = sorted(self.views.versions_of(view_name),
                          key=lambda v: v.get("version") or 0)
        if not versions:
            return {"view": view_name, "judged": False,
                    "detail": "this view has never been materialised, so there "
                              "is nothing upstream of anything yet"}
        latest, history = versions[-1], versions[:-1]
        if len(history) < MIN_HISTORY:
            return {"view": view_name, "judged": False,
                    "versions": len(versions),
                    "detail": (f"{len(versions)} version(s): a baseline needs "
                               f"at least {MIN_HISTORY + 1}, and one built "
                               f"from fewer is a number with a false air of "
                               f"authority. This feed is not judgeable yet")}

        findings_ = [f for f in (self._freshness(latest, history, moment),
                                 self._volume(latest, history),
                                 *self._schema(latest, history),
                                 *self._nulls(latest, history)) if f]
        return {
            "view": view_name, "judged": True, "versions": len(versions),
            "latest_version": latest.get("version"),
            "materialised_at": latest.get("materialised_at"),
            "row_count": latest.get("row_count"),
            "problems": findings_,
            "healthy": not findings_,
            "detail": (f"{len(findings_)} problem(s) against this view's own "
                       f"history" if findings_ else
                       "this feed is behaving like itself"),
        }

    # ------------------------------------------------------------- questions
    @staticmethod
    def _freshness(latest, history, moment) -> Optional[Dict[str, Any]]:
        stamps = sorted(v.get("materialised_at") or 0 for v in history)
        gaps = [b - a for a, b in pairwise(stamps) if b > a]
        if not gaps:
            return None
        usual = statistics.median(gaps)
        since = moment - (latest.get("materialised_at") or 0)
        if usual <= 0 or since <= usual * STALE_MULTIPLE:
            return None
        return {
            "kind": "freshness", "observed_hours": round(since / 3600, 1),
            "usual_hours": round(usual / 3600, 1),
            "detail": (f"last loaded {since / 3600:.1f} hours ago; this view "
                       f"normally goes {usual / 3600:.1f} hours between loads. "
                       f"One missed load is a late batch and two is a stopped "
                       f"one"),
        }

    @staticmethod
    def _volume(latest, history) -> Optional[Dict[str, Any]]:
        counts = [v.get("row_count") or 0 for v in history]
        usual = statistics.median(counts)
        rows = latest.get("row_count") or 0
        if usual <= 0:
            return None
        if rows < usual * VOLUME_DROP:
            return {"kind": "volume_drop", "observed": rows,
                    "usual": usual,
                    "detail": (f"{rows} rows against a usual {usual:.0f}. A "
                               f"load at half its size succeeds, is recorded, "
                               f"and quietly makes every downstream number an "
                               f"average of less")}
        if rows > usual * VOLUME_SPIKE:
            return {"kind": "volume_spike", "observed": rows, "usual": usual,
                    "detail": (f"{rows} rows against a usual {usual:.0f}. "
                               f"Often a backfill, which is benign — but a "
                               f"backfill nobody mentioned changes what a "
                               f"point-in-time read returns")}
        return None

    @staticmethod
    def _schema(latest, history) -> List[Dict[str, Any]]:
        was = set(history[-1].get("features") or [])
        now_ = set(latest.get("features") or [])
        out = []
        # Reported separately and deliberately: gaining a column is usually
        # somebody's work landing, and losing one is what breaks the featureset
        # pinned to this view.
        if (lost := sorted(was - now_)):
            out.append({"kind": "schema_lost", "features": lost,
                        "detail": (f"{', '.join(lost)} stopped arriving. Any "
                                   f"featureset with a slot bound to one of "
                                   f"these can no longer be filled")})
        if (gained := sorted(now_ - was)):
            out.append({"kind": "schema_gained", "features": gained,
                        "detail": (f"{', '.join(gained)} started arriving. "
                                   f"Usually somebody's work landing, and "
                                   f"worth knowing it landed here")})
        return out

    @staticmethod
    def _nulls(latest, history) -> List[Dict[str, Any]]:
        def rates(version) -> Dict[str, float]:
            report = version.get("quality_report") or {}
            columns = report.get("columns") or report
            out = {}
            for name, stats in columns.items():
                if isinstance(stats, dict) and "null_rate" in stats:
                    out[name] = float(stats["null_rate"])
            return out

        now_ = rates(latest)
        past: Dict[str, List[float]] = {}
        for version in history:
            for name, rate in rates(version).items():
                past.setdefault(name, []).append(rate)

        out = []
        for name, rate in sorted(now_.items()):
            seen = past.get(name)
            if not seen:
                continue
            usual = statistics.median(seen)
            # The floor matters as much as the multiple: 0.1% to 0.4% is a
            # quadrupling and is not news, and a monitor that says so is one
            # people learn to skim.
            if rate >= NULL_FLOOR and rate > max(usual, NULL_FLOOR / NULL_MULTIPLE) * NULL_MULTIPLE:
                out.append({
                    "kind": "null_spike", "feature": name,
                    "observed": round(rate, 4), "usual": round(usual, 4),
                    "detail": (f"'{name}' is {rate:.1%} null against a usual "
                               f"{usual:.1%}. An assertion catches a null rate "
                               f"crossing a line somebody drew in advance; "
                               f"this is the one that tripled while staying "
                               f"inside it"),
                })
        return out

    # ------------------------------------------------------------------ sweep
    def sweep(self, now: Optional[float] = None,
              actor: str = "system") -> Dict[str, Any]:
        """Every view, and a finding for the two problems that break a model.

        Only `freshness` and `schema_lost` raise. A volume change is usually a
        real change in the business, and a null spike is usually worth a look
        rather than a ticket — raising all four would make this the loudest
        thing in the estate and therefore the first thing muted.
        """
        looked, raised = 0, []
        # `views.views` is the repository behind the manager. Reached this way
        # rather than adding a `list()` to the manager, because a sweep over
        # every view is this module's business and not something the manager
        # otherwise needs to offer.
        for view in self.views.views.many():
            looked += 1
            report = self.for_view(view["name"], now=now)
            if not report.get("judged"):
                continue
            for problem in report["problems"]:
                if problem["kind"] in ("freshness", "schema_lost") and \
                        self._raise(view, problem):
                    raised.append(f"{view['name']}: {problem['kind']}")
        return {"views": looked, "raised": raised, "count": len(raised),
                "detail": (f"{looked} view(s) checked against their own "
                           f"history; "
                           + (f"{len(raised)} raised" if raised
                              else "every feed is behaving like itself"))}

    def _raise(self, view: Dict[str, Any], problem: Dict[str, Any]) -> bool:
        """A finding against the view's owner. Idempotent by title."""
        if self.findings is None or self.registry is None:
            return False
        # A feature view is not a model, and findings hang off models — so this
        # raises against every model whose featureset pins this view, which is
        # also who actually needs to know.
        affected = self._models_using(view)
        if not affected:
            return False
        title = f"Upstream data: {problem['kind']} in '{view['name']}'"
        raised_any = False
        for model in affected:
            if any(f.get("title") == title
                   for f in self.findings.open_for(model["id"])):
                continue
            self.findings.raise_finding(
                model["id"], "High" if problem["kind"] == "schema_lost"
                else "Medium",
                title=title, owner=model.get("owner") or "person/unknown",
                description=(f"{problem['detail']}. Most model failures are "
                             f"data failures, and this one is upstream of the "
                             f"model rather than in it — the scores will go on "
                             f"looking plausible."),
                category="data_pipeline", source="monitoring", blocking=False)
            raised_any = True
        return raised_any

    def _models_using(self, view: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Every model whose featureset pins this view.

        A feature view is not a model and findings hang off models, so the
        finding goes to whoever actually has to act on it. Supplied as a lookup
        rather than reached for, so this module does not import the featureset
        machinery it is describing.
        """
        if self.models_using is None:
            return []
        return list(self.models_using(view["name"]))
