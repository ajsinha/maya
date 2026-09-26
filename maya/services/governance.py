"""
Model governance: findings, materiality and periodic review.

Three things a model risk function does that MAYA did not record:

* **Findings.** A validator finds a defect; the model owner remediates it; somebody other
  than the person who did the remediation closes it, or the risk is knowingly accepted with
  a written reason. Each finding carries a severity, an owner and a due date, and every
  move is kept in its own history as well as in the audit chain. Nobody closes their own
  fix, for the same reason nobody approves their own model.
* **Materiality.** A tier from 1 (most material) to 3, *derived* from what MAYA can see --
  how many live execution warrants the model runs under and how often it has run, whether
  it is a black box -- and from the two things only the owner can declare: what the model
  is used for and the exposure it sits over. An override is allowed and needs a reason;
  one that makes a model *less* material than the evidence says is flagged as such, since
  that is the direction in which an override needs explaining.
* **Periodic review.** The tier sets how often the model has to be looked at again. When a
  review falls overdue, the sweep suspends every live execution warrant the model runs
  under, through the same suspension a covenant breach uses, so the live instrument fails
  closed and says why. Recording the review lifts exactly those suspensions and no others:
  a warrant suspended for a breach stays suspended until someone decides otherwise.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import builtins
import datetime as dt
from typing import Any

from maya.core.clock import utcnow
from maya.core.errors import NotApproved, PermissionDenied, ValidationFailed
from maya.security.authz import Principal
from maya.services import catalog, refs

SEVERITIES = ("low", "medium", "high", "critical")
SOURCES = ("validation", "audit", "monitoring", "review", "self-identified")
STATES = ("open", "remediating", "remediated", "closed", "accepted")
# days to remediate by default, by severity; the raiser can set an earlier date
DUE_DAYS = {"critical": 30, "high": 90, "medium": 180, "low": 365}
# action: (states it may be taken from, state it leads to)
MOVES = {
    "start": (("open",), "remediating"),
    "remediated": (("open", "remediating"), "remediated"),
    "close": (("remediated",), "closed"),
    "reject": (("remediated",), "remediating"),
    "accept": (("open", "remediating", "remediated"), "accepted"),
    "reopen": (("closed", "accepted"), "open"),
}
USES = {
    "regulatory": 3,
    "financial_reporting": 3,
    "business_decision": 2,
    "internal": 1,
}
OUTCOMES = ("satisfactory", "needs_improvement", "unsatisfactory")
REVIEW_DAYS = {1: 365, 2: 730, 3: 1095}
REVIEW_REASON = "Periodic review overdue"


def _date(value: Any) -> dt.date | None:
    if value in (None, ""):
        return None
    if isinstance(value, dt.date):
        return value
    try:
        return dt.date.fromisoformat(str(value))
    except ValueError as exc:
        raise ValidationFailed(f"'{value}' is not a date (YYYY-MM-DD)") from exc


class GovernanceService:
    def __init__(self, platform: Any) -> None:
        self.p = platform

    # -- shared ---------------------------------------------------------------------
    def _model(self, uow: Any, p: Principal, ref: str, action: str = "read") -> tuple[Any, Any]:
        model, ns = catalog.find_object(uow, "models", "model", refs.parse(ref, "model"))
        self.p.access.require(uow, p, action, "model", model)
        return model, ns

    @staticmethod
    def _ref(model: dict[str, Any], ns: dict[str, Any]) -> str:
        return refs.object_ref("model", ns["name"], model["name"])

    def _owner(self, uow: Any, model: dict[str, Any]) -> str | None:
        user = uow.repo("users").get(model["owner_id"])
        return user["username"] if user else None

    def _warrants(self, uow: Any, model_id: str) -> builtins.list[dict[str, Any]]:
        versions = [v["id"] for v in uow.repo("model_versions").list(model_id=model_id)]
        if not versions:
            return []
        return uow.repo("execution_warrants").list(model_version_id__in=versions)

    # -- findings -------------------------------------------------------------------
    def findings(
        self, p: Principal, model: str | None = None, state: str | None = None
    ) -> builtins.list[dict[str, Any]]:
        """The register: every finding on a model the caller may read, most urgent first."""
        with self.p.uow() as uow:
            filters: dict[str, Any] = {}
            if model:
                filters["model_id"] = self._model(uow, p, model)[0]["id"]
            if state == "active":
                filters["state__in"] = ["open", "remediating", "remediated"]
            elif state:
                filters["state"] = state
            rows = uow.repo("findings").list(**filters)
            return self._decorate(uow, p, rows)

    def _decorate(
        self, uow: Any, p: Principal, rows: builtins.list[dict[str, Any]]
    ) -> builtins.list[dict[str, Any]]:
        out, seen = [], {}
        today = utcnow().date()
        for row in rows:
            mid = row["model_id"]
            if mid not in seen:
                model = uow.repo("models").get(mid)
                ns = uow.repo("namespaces").get(model["namespace_id"])
                ok = self.p.access.allowed(uow, p, "read", "model", model)
                seen[mid] = self._ref(model, ns) if ok else None
            if seen[mid] is None:
                continue
            live = row["state"] in ("open", "remediating", "remediated")
            out.append(
                {
                    **row,
                    "model_ref": seen[mid],
                    "overdue": bool(live and row["due_date"] and row["due_date"] < today),
                }
            )
        rank = {s: i for i, s in enumerate(reversed(SEVERITIES))}
        return sorted(
            out,
            key=lambda r: (
                r["state"] not in ("open", "remediating", "remediated"),
                rank[r["severity"]],
                r["due_date"] or dt.date.max,
            ),
        )

    def finding(self, p: Principal, finding_id: str) -> dict[str, Any]:
        with self.p.uow() as uow:
            row = uow.repo("findings").require(finding_id)
            model = uow.repo("models").require(row["model_id"])
            self.p.access.require(uow, p, "read", "model", model)
            return self._decorate(uow, p, [row])[0]

    def raise_finding(
        self,
        p: Principal,
        model: str,
        title: str,
        severity: str,
        *,
        detail: str | None = None,
        source: str = "validation",
        owner: str | None = None,
        due_date: Any = None,
        version_no: int | None = None,
    ) -> dict[str, Any]:
        """Record a defect. The owner defaults to the model's owner, the due date to the
        severity's remediation window."""
        if not title.strip():
            raise ValidationFailed("A finding needs a title that says what is wrong")
        if severity not in SEVERITIES:
            raise ValidationFailed(f"severity is one of {', '.join(SEVERITIES)}")
        if source not in SOURCES:
            raise ValidationFailed(f"source is one of {', '.join(SOURCES)}")
        due = _date(due_date) or utcnow().date() + dt.timedelta(days=DUE_DAYS[severity])
        with self.p.uow(p.username) as uow:
            m, ns = self._model(uow, p, model)
            if version_no is not None and not uow.repo("model_versions").find_one(
                model_id=m["id"], version_no=version_no
            ):
                raise ValidationFailed(f"{self._ref(m, ns)} has no version {version_no}")
            row = uow.repo("findings").add(
                {
                    "model_id": m["id"],
                    "version_no": version_no,
                    "title": title.strip(),
                    "detail": detail,
                    "severity": severity,
                    "source": source,
                    "state": "open",
                    "raised_by": p.username,
                    "owner": owner or self._owner(uow, m),
                    "due_date": due,
                    "history": [self._event(p, "raised", None, "open", detail)],
                }
            )
            uow.audit(
                "finding.raised",
                object_type="model",
                object_ref=self._ref(m, ns),
                detail={"finding": row["id"], "severity": severity, "title": row["title"]},
            )
            return self._decorate(uow, p, [row])[0]

    @staticmethod
    def _event(p: Principal, action: str, old: str | None, new: str, note: str | None) -> Any:
        return {
            "at": utcnow().isoformat(),
            "by": p.username,
            "action": action,
            "from": old,
            "to": new,
            "note": note,
        }

    def move_finding(
        self, p: Principal, finding_id: str, action: str, note: str | None = None
    ) -> dict[str, Any]:
        """Take one step in a finding's life. Closing, rejecting a fix and accepting the
        risk need a written note; nobody closes a fix they made themselves."""
        if action not in MOVES:
            raise ValidationFailed(f"action is one of {', '.join(MOVES)}")
        sources, target = MOVES[action]
        note = (note or "").strip() or None
        with self.p.uow(p.username) as uow:
            row = uow.repo("findings").require(finding_id)
            model = uow.repo("models").require(row["model_id"])
            ns = uow.repo("namespaces").require(model["namespace_id"])
            self.p.access.require(uow, p, "read", "model", model)
            if row["state"] not in sources:
                raise NotApproved(
                    f"A finding that is '{row['state']}' cannot be moved by '{action}'",
                    state=row["state"],
                )
            if action in ("close", "reject", "accept", "reopen") and not note:
                raise ValidationFailed(f"'{action}' needs a written note saying why")
            if action in ("close", "reject") and p.username == row["remediated_by"]:
                raise PermissionDenied(
                    "Whoever remediated a finding does not close it; an independent "
                    "reviewer confirms the fix"
                )
            if action == "accept" and not (p.is_admin or p.username != self._owner(uow, model)):
                raise PermissionDenied("A model owner does not accept the risk in their own model")
            changes: dict[str, Any] = {
                "state": target,
                "history": [*row["history"], self._event(p, action, row["state"], target, note)],
            }
            if action == "remediated":
                changes["remediated_by"] = p.username
            if target in ("closed", "accepted"):
                changes.update(closed_by=p.username, closed_at=utcnow(), resolution=note)
            if action == "reopen":
                changes.update(closed_by=None, closed_at=None, remediated_by=None)
            out = uow.repo("findings").update(finding_id, changes)
            uow.audit(
                f"finding.{action}",
                object_type="model",
                object_ref=self._ref(model, ns),
                detail={"finding": finding_id, "from": row["state"], "to": target, "note": note},
            )
            return self._decorate(uow, p, [out])[0]

    # -- materiality ----------------------------------------------------------------
    def questionnaire(self) -> dict[str, Any]:
        """The materiality questionnaire from ``governance.tiering_questionnaire``.

        A firm's own policy, in a file it edits: questions, the answers each allows, and
        the score (1 to 3) of each answer. Blank means none: the measured drivers alone."""
        path = self.p.settings.get("governance.tiering_questionnaire") or ""
        if not path:
            return {"rule": "max", "thresholds": {}, "questions": []}
        from pathlib import Path

        import yaml

        file = Path(path)
        try:
            stamp = file.stat().st_mtime
        except OSError as exc:
            raise ValidationFailed(
                f"The tiering questionnaire '{path}' (governance.tiering_questionnaire) "
                "cannot be read"
            ) from exc
        cached = getattr(self, "_questionnaire", None)
        if cached and cached[0] == (path, stamp):
            return cached[1]
        doc = yaml.safe_load(file.read_text(encoding="utf-8")) or {}
        rule = doc.get("rule", "max")
        if rule not in ("max", "points"):
            raise ValidationFailed(f"{path}: rule is 'max' or 'points'")
        questions = []
        for q in doc.get("questions") or []:
            answers = {str(k): int(v) for k, v in (q.get("answers") or {}).items()}
            if not q.get("id") or not answers or not all(1 <= v <= 3 for v in answers.values()):
                raise ValidationFailed(
                    f"{path}: each question has an id and answers scored 1 to 3", question=q
                )
            questions.append(
                {"id": str(q["id"]), "text": q.get("text", q["id"]), "answers": answers}
            )
        out = {
            "rule": rule,
            "thresholds": {int(k): int(v) for k, v in (doc.get("thresholds") or {}).items()},
            "questions": questions,
        }
        self._questionnaire = ((path, stamp), out)
        return out

    def _answers_score(self, answers: dict[str, str]) -> tuple[int, builtins.list[Any], bool]:
        """(score, drivers, complete) from the owner's answers under the questionnaire."""
        q = self.questionnaire()
        drivers, scores = [], []
        for question in q["questions"]:
            answer = answers.get(question["id"])
            if answer is None:
                continue
            score = question["answers"][answer]
            scores.append(score)
            if q["rule"] == "max":
                drivers.append(
                    {
                        "driver": f"questionnaire: {question['id']}",
                        "value": answer.replace("_", " "),
                        "score": score,
                        "why": question["text"],
                    }
                )
        complete = all(question["id"] in answers for question in q["questions"])
        if q["rule"] == "points" and scores:
            total = sum(scores)
            score = next(
                (k for k, v in sorted(q["thresholds"].items(), reverse=True) if total >= v), 1
            )
            drivers.append(
                {
                    "driver": "questionnaire",
                    "value": f"{total} points over {len(scores)} answer(s)",
                    "score": score,
                    "why": "the firm's questionnaire, summed and placed by its thresholds",
                }
            )
            return score, drivers, complete
        return (max(scores) if scores else 1), drivers, complete

    def _profile_row(self, uow: Any, model_id: str) -> dict[str, Any]:
        return uow.repo("model_governance").find_one(model_id=model_id) or {}

    def derive(self, uow: Any, model: dict[str, Any], prof: dict[str, Any]) -> dict[str, Any]:
        """The tier the evidence supports, and each driver that went into it."""
        drivers = []
        use = prof.get("use")
        drivers.append(
            {
                "driver": "use",
                "value": use or "not declared",
                "score": USES.get(use or "", 1),
                "why": "what the model is used for, declared by its owner",
            }
        )
        exposure = prof.get("exposure")
        e_score = 1 if exposure is None else 3 if exposure >= 1e9 else 2 if exposure >= 1e7 else 1
        drivers.append(
            {
                "driver": "exposure",
                "value": exposure if exposure is not None else "not declared",
                "score": e_score,
                "why": "the amount the model's output sits over: 10m and 1bn are the steps",
            }
        )
        warrants = self._warrants(uow, model["id"])
        live = [w for w in warrants if self.p.execution.status(w) in ("live", "suspended")]
        runs = sum(int(w.get("executions") or 0) for w in warrants)
        reach = 3 if len(live) >= 3 or runs >= 10_000 else 2 if live else 1
        drivers.append(
            {
                "driver": "reach",
                "value": f"{len(live)} live warrant(s), {runs} execution(s)",
                "score": reach,
                "why": "measured by MAYA: where the model is licensed to run and how often it has",
            }
        )
        versions = uow.repo("model_versions").list(model_id=model["id"])
        opaque = model["kind"] != "formula" or any(v.get("opaque") for v in versions)
        drivers.append(
            {
                "driver": "transparency",
                "value": "black box" if opaque else "closed form",
                "score": 1,
                "bump": opaque,
                "why": "a model nobody can read is one tier more material than its reach",
            }
        )
        q_score, q_drivers, complete = self._answers_score(prof.get("answers") or {})
        drivers.extend(q_drivers)
        score = max(USES.get(use or "", 1), e_score, reach, q_score) + (1 if opaque else 0)
        tier = 4 - min(score, 3)
        return {
            "tier": tier,
            "drivers": drivers,
            "declared": bool(use and exposure is not None and complete),
        }

    def _review_days(self, tier: int, prof: dict[str, Any]) -> int:
        if prof.get("review_days"):
            return int(prof["review_days"])
        return self.p.settings.int(f"governance.review_days_tier{tier}", REVIEW_DAYS[tier])

    def _profile(self, uow: Any, model: dict[str, Any]) -> dict[str, Any]:
        prof = self._profile_row(uow, model["id"])
        derived = self.derive(uow, model, prof)
        tier = prof.get("tier_override") or derived["tier"]
        days = self._review_days(tier, prof)
        approved = [
            v["approved_at"]
            for v in uow.repo("model_versions").list(model_id=model["id"])
            if v.get("approved_at")
        ]
        anchor = prof.get("last_reviewed_at") or (min(approved) if approved else None)
        due = (anchor + dt.timedelta(days=days)).date() if anchor else None
        return {
            "use": prof.get("use"),
            "exposure": prof.get("exposure"),
            "answers": prof.get("answers") or {},
            "derived_tier": derived["tier"],
            "drivers": derived["drivers"],
            "declared": derived["declared"],
            "tier_override": prof.get("tier_override"),
            "override_reason": prof.get("override_reason"),
            "override_lowers": bool(
                prof.get("tier_override") and prof["tier_override"] > derived["tier"]
            ),
            "tier": tier,
            "review_days": days,
            "last_reviewed_at": prof.get("last_reviewed_at"),
            "last_reviewed_by": prof.get("last_reviewed_by"),
            "next_review_due": due,
            "review_overdue": bool(due and due < utcnow().date()),
        }

    def profile(self, p: Principal, model: str) -> dict[str, Any]:
        """Everything governance knows about one model."""
        with self.p.uow() as uow:
            m, ns = self._model(uow, p, model)
            findings = self._decorate(uow, p, uow.repo("findings").list(model_id=m["id"]))
            reviews = uow.repo("model_reviews").list(model_id=m["id"], order_by=["-created_at"])
            return {
                "model_ref": self._ref(m, ns),
                "owner": self._owner(uow, m),
                **self._profile(uow, m),
                "findings": findings,
                "reviews": reviews,
                "questionnaire": self.questionnaire()["questions"],
                "can_edit": self.p.access.allowed(uow, p, "update", "model", m),
            }

    def set_profile(
        self,
        p: Principal,
        model: str,
        *,
        use: str | None = None,
        exposure: float | None = None,
        tier_override: int | None = None,
        override_reason: str | None = None,
        review_days: int | None = None,
        answers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Declare what only the owner knows, and override the derived tier with a reason.
        ``answers`` replaces the questionnaire answers; ``None`` leaves them as they were."""
        if answers is not None:
            allowed = {q["id"]: q["answers"] for q in self.questionnaire()["questions"]}
            for qid, answer in answers.items():
                if qid not in allowed:
                    raise ValidationFailed(f"'{qid}' is not a question in the questionnaire")
                if answer not in allowed[qid]:
                    raise ValidationFailed(
                        f"'{answer}' is not an answer to '{qid}'", allowed=sorted(allowed[qid])
                    )
        if use is not None and use not in USES:
            raise ValidationFailed(f"use is one of {', '.join(USES)}")
        if exposure is not None and exposure < 0:
            raise ValidationFailed("exposure is an amount, not negative")
        if tier_override is not None and tier_override not in (1, 2, 3):
            raise ValidationFailed("a tier is 1, 2 or 3")
        if tier_override is not None and not (override_reason or "").strip():
            raise ValidationFailed("overriding the derived tier needs a written reason")
        if review_days is not None and not 30 <= review_days <= 1825:
            raise ValidationFailed("a review interval is between 30 days and five years")
        with self.p.uow(p.username) as uow:
            m, ns = self._model(uow, p, model, "update")
            values: dict[str, Any] = {
                "use": use,
                "exposure": exposure,
                "tier_override": tier_override,
                "override_reason": (override_reason or "").strip() or None,
                "review_days": review_days,
            }
            if answers is not None:
                values["answers"] = dict(answers)
            prof = self._profile_row(uow, m["id"])
            if prof:
                uow.repo("model_governance").update(prof["id"], values)
            else:
                uow.repo("model_governance").add({"model_id": m["id"], **values})
            out = self._profile(uow, m)
            uow.audit(
                "governance.profile_set",
                object_type="model",
                object_ref=self._ref(m, ns),
                detail={**values, "tier": out["tier"], "derived_tier": out["derived_tier"]},
            )
            return out

    # -- periodic review ------------------------------------------------------------
    def record_review(self, p: Principal, model: str, outcome: str, note: str) -> dict[str, Any]:
        """The dated act of looking at a model again. Its owner does not review it."""
        if outcome not in OUTCOMES:
            raise ValidationFailed(f"outcome is one of {', '.join(OUTCOMES)}")
        if not note.strip():
            raise ValidationFailed("A review records what was looked at and what was concluded")
        with self.p.uow(p.username) as uow:
            m, ns = self._model(uow, p, model)
            if p.username == self._owner(uow, m):
                raise PermissionDenied("A model's owner does not review their own model")
            now = utcnow()
            prof = self._profile_row(uow, m["id"])
            values = {"last_reviewed_at": now, "last_reviewed_by": p.username}
            if prof:
                uow.repo("model_governance").update(prof["id"], values)
            else:
                uow.repo("model_governance").add({"model_id": m["id"], **values})
            out = self._profile(uow, m)
            uow.repo("model_reviews").add(
                {
                    "model_id": m["id"],
                    "reviewer": p.username,
                    "outcome": outcome,
                    "note": note.strip(),
                    "tier": out["tier"],
                    "next_due": out["next_review_due"],
                }
            )
            lifted = self._lift(uow, p, m)
            uow.audit(
                "governance.reviewed",
                object_type="model",
                object_ref=self._ref(m, ns),
                detail={"outcome": outcome, "next_due": str(out["next_review_due"])},
            )
            return {**out, "reinstated": lifted}

    def _lift(self, uow: Any, p: Principal, model: dict[str, Any]) -> builtins.list[str]:
        """Reinstate the warrants this module suspended, and only those."""
        lifted = []
        for w in self._warrants(uow, model["id"]):
            if w.get("suspended_at") and (w.get("suspend_reason") or "").startswith(REVIEW_REASON):
                uow.repo("execution_warrants").update(
                    w["id"], {"suspended_at": None, "suspend_reason": None}
                )
                self.p.warrants._custody(
                    uow,
                    w["id"],
                    "reinstated",
                    p.username,
                    detail={"reason": "periodic review recorded"},
                    warrant_type="exec",
                )
                lifted.append(w["id"])
        return lifted

    def sweep(self, p: Principal | None = None) -> dict[str, Any]:
        """Suspend every live execution warrant of a model whose review is overdue."""
        if p is not None and not p.is_admin:
            raise PermissionDenied("Running the review sweep is for administrators")
        suspended = []
        with self.p.uow("governance-sweep") as uow:
            for model in uow.repo("models").list():
                prof = self._profile(uow, model)
                if not prof["review_overdue"]:
                    continue
                reason = f"{REVIEW_REASON} since {prof['next_review_due']:%Y-%m-%d}"
                for w in self._warrants(uow, model["id"]):
                    if self.p.execution.status(w) != "live":
                        continue
                    uow.repo("execution_warrants").update(
                        w["id"], {"suspended_at": utcnow(), "suspend_reason": reason}
                    )
                    self.p.warrants._custody(
                        uow,
                        w["id"],
                        "suspended",
                        "governance-sweep",
                        detail={"reason": reason},
                        warrant_type="exec",
                    )
                    ns = uow.repo("namespaces").get(w["namespace_id"])
                    uow.audit(
                        "warrant.suspended",
                        object_type="execution_warrant",
                        object_ref=self.p.execution.uri(w, ns),
                        detail={"reason": reason},
                        principal_type="system",
                    )
                    suspended.append(w["id"])
        return {"suspended": suspended}

    def overview(self, p: Principal) -> dict[str, Any]:
        """One row per model the caller may read: tier, review date and open findings."""
        rows = []
        with self.p.uow() as uow:
            open_by_model: dict[str, dict[str, int]] = {}
            for f in uow.repo("findings").list(state__in=["open", "remediating", "remediated"]):
                counts = open_by_model.setdefault(f["model_id"], dict.fromkeys(SEVERITIES, 0))
                counts[f["severity"]] += 1
            for model in uow.repo("models").list(order_by=["name"]):
                if not self.p.access.allowed(uow, p, "read", "model", model):
                    continue
                ns = uow.repo("namespaces").get(model["namespace_id"])
                prof = self._profile(uow, model)
                counts = open_by_model.get(model["id"], dict.fromkeys(SEVERITIES, 0))
                rows.append(
                    {
                        "model_ref": self._ref(model, ns),
                        "namespace": ns["name"],
                        "name": model["name"],
                        "tier": prof["tier"],
                        "derived_tier": prof["derived_tier"],
                        "declared": prof["declared"],
                        "next_review_due": prof["next_review_due"],
                        "review_overdue": prof["review_overdue"],
                        "open_findings": sum(counts.values()),
                        "by_severity": counts,
                    }
                )
        return {
            "models": rows,
            "overdue_reviews": sum(r["review_overdue"] for r in rows),
            "open_findings": sum(r["open_findings"] for r in rows),
            "critical_open": sum(r["by_severity"]["critical"] for r in rows),
        }
