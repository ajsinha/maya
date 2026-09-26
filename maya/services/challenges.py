"""
Champion and challenger: is the new model actually better, on the same data, by enough?

A challenger replaces a champion on evidence, and the evidence has to be a like-for-like
comparison. MAYA can make one honestly because both warrants' holdouts are escrowed and
sealed by content hash: when the two hashes are equal, the two models are scored on exactly
the same rows, in the same order, and nobody on either side has seen them.

So a challenge scores both -- each attempt counted on its warrant, like any other -- and
compares the *per-row* errors, which only MAYA holds:

* the difference in the chosen metric, challenger minus champion (negative is better for
  both RMSE and MAE);
* a paired bootstrap 95% interval for that difference, resampling rows with a fixed seed so
  the same challenge gives the same interval on any machine;
* the share of rows on which the challenger's absolute error is smaller.

The verdict it reports is ``challenger_better`` only when the whole interval lies below
zero, ``champion_better`` only when it lies above, and ``no_clear_difference`` otherwise:
a challenger that is better on average but whose interval straddles zero has not shown it.

The decision is a person's: promote or retain, with a written rationale, by somebody who
does not own the challenger's warrant. Promoting records the decision and nothing more --
the champion's execution warrants keep running until someone draws the challenger's and
retires the champion's, because a comparison on a holdout is evidence for that change and
not the change itself.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import builtins
from typing import Any

import numpy as np

from maya.core.clock import utcnow
from maya.core.errors import NotApproved, PermissionDenied, ValidationFailed
from maya.security.authz import Principal

METRICS = ("rmse", "mae")
BOOTSTRAP = 2000
SEED = 20260926


def _metric(err: np.ndarray, metric: str) -> float:
    return float(np.sqrt(np.mean(err**2))) if metric == "rmse" else float(np.mean(np.abs(err)))


def compare(
    champion: np.ndarray, challenger: np.ndarray, metric: str, *, draws: int = BOOTSTRAP
) -> dict[str, Any]:
    """Paired comparison of two error vectors over the same rows."""
    keep = ~(np.isnan(champion) | np.isnan(challenger))
    a, b = champion[keep], challenger[keep]
    if a.size < 2:
        raise ValidationFailed("A comparison needs at least two rows both models scored")
    diff = _metric(b, metric) - _metric(a, metric)
    rng = np.random.default_rng(SEED)
    idx = rng.integers(0, a.size, size=(draws, a.size))
    if metric == "rmse":
        boot = np.sqrt(np.mean(b[idx] ** 2, axis=1)) - np.sqrt(np.mean(a[idx] ** 2, axis=1))
    else:
        boot = np.mean(np.abs(b[idx]), axis=1) - np.mean(np.abs(a[idx]), axis=1)
    lo, hi = (float(q) for q in np.quantile(boot, [0.025, 0.975]))
    if hi < 0:
        verdict = "challenger_better"
    elif lo > 0:
        verdict = "champion_better"
    else:
        verdict = "no_clear_difference"
    return {
        "metric": metric,
        "champion": _metric(a, metric),
        "challenger": _metric(b, metric),
        "difference": diff,
        "interval": [lo, hi],
        "challenger_wins": float(np.mean(np.abs(b) < np.abs(a))),
        "rows": int(a.size),
        "bootstrap": {"draws": draws, "seed": SEED, "level": 0.95},
        "verdict": verdict,
    }


class ChallengeService:
    def __init__(self, platform: Any) -> None:
        self.p = platform

    def _describe(self, uow: Any, row: dict[str, Any]) -> dict[str, Any]:
        out = dict(row)
        for side in ("champion", "challenger"):
            w, ns = self.p.warrants._load(uow, row[f"{side}_warrant_id"])
            mv = uow.repo("model_versions").get(w["model_version_id"])
            model = uow.repo("models").get(mv["model_id"]) if mv else None
            out[side] = {
                "warrant": self.p.warrants.uri(w, ns),
                "warrant_id": w["id"],
                "model": f"{model['name']}@v{mv['version_no']}" if model and mv else None,
                "owner_id": w["owner_id"],
            }
        return out

    def create(
        self,
        p: Principal,
        champion: str,
        challenger: str,
        *,
        metric: str = "rmse",
        champion_parameter_set_id: str | None = None,
        challenger_parameter_set_id: str | None = None,
    ) -> dict[str, Any]:
        """Score both warrants on their shared escrowed holdout and compare them."""
        if metric not in METRICS:
            raise ValidationFailed(f"metric is one of {', '.join(METRICS)}")
        if champion == challenger:
            raise ValidationFailed("A model is not challenged by itself")
        with self.p.uow() as uow:
            warrants = {}
            for side, wid in (("champion", champion), ("challenger", challenger)):
                w, _ = self.p.warrants._load(uow, wid)
                self.p.access.require(uow, p, "read", "training_warrant", w)
                warrants[side] = w
        hashes = {side: w.get("holdout_hash") for side, w in warrants.items()}
        if not all(hashes.values()) or hashes["champion"] != hashes["challenger"]:
            raise ValidationFailed(
                "The two warrants were not drawn on the same escrowed holdout, so their scores "
                "are not comparable. Draw the challenger's warrant on the champion's feature "
                "set pin, with the same split and seed.",
                champion_holdout=hashes["champion"],
                challenger_holdout=hashes["challenger"],
            )
        if warrants["champion"]["spec"].get("target") != warrants["challenger"]["spec"].get(
            "target"
        ):
            raise ValidationFailed("The two warrants score different targets")
        errors = {}
        for side, wid, ps in (
            ("champion", champion, champion_parameter_set_id),
            ("challenger", challenger, challenger_parameter_set_id),
        ):
            err, _, _ = self.p.warrants.holdout_errors(
                p, wid, parameter_set_id=ps, purpose="champion-challenger"
            )
            errors[side] = np.asarray(err, dtype=float)
        if errors["champion"].shape != errors["challenger"].shape:
            raise ValidationFailed("The two scorings returned different numbers of rows")
        result = compare(errors["champion"], errors["challenger"], metric)
        with self.p.uow(p.username) as uow:
            row = uow.repo("challenges").add(
                {
                    "champion_warrant_id": champion,
                    "challenger_warrant_id": challenger,
                    "champion_parameter_set_id": champion_parameter_set_id,
                    "challenger_parameter_set_id": challenger_parameter_set_id,
                    "metric": metric,
                    "holdout_hash": hashes["champion"],
                    "result": result,
                    "state": "scored",
                    "raised_by": p.username,
                }
            )
            uow.audit(
                "challenge.scored",
                object_type="challenge",
                object_ref=row["id"],
                detail={k: result[k] for k in ("metric", "difference", "interval", "verdict")},
            )
            return self._describe(uow, row)

    def list(self, p: Principal) -> builtins.list[dict[str, Any]]:
        with self.p.uow() as uow:
            out = []
            for row in uow.repo("challenges").list(order_by=["-created_at"]):
                w = uow.repo("training_warrants").get(row["challenger_warrant_id"])
                if w and self.p.access.allowed(uow, p, "read", "training_warrant", w):
                    out.append(self._describe(uow, row))
            return out

    def get(self, p: Principal, challenge_id: str) -> dict[str, Any]:
        with self.p.uow() as uow:
            row = uow.repo("challenges").require(challenge_id)
            w = uow.repo("training_warrants").require(row["challenger_warrant_id"])
            self.p.access.require(uow, p, "read", "training_warrant", w)
            return self._describe(uow, row)

    def decide(
        self, p: Principal, challenge_id: str, decision: str, rationale: str
    ) -> dict[str, Any]:
        """Promote the challenger or retain the champion, with the reason in writing."""
        if decision not in ("promote", "retain"):
            raise ValidationFailed("decision is 'promote' or 'retain'")
        if not rationale.strip():
            raise ValidationFailed("A decision records why it was taken")
        with self.p.uow(p.username) as uow:
            row = uow.repo("challenges").require(challenge_id)
            w = uow.repo("training_warrants").require(row["challenger_warrant_id"])
            self.p.access.require(uow, p, "read", "training_warrant", w)
            if row["state"] != "scored":
                raise NotApproved(f"This challenge was already decided: {row['state']}")
            owner = uow.repo("users").get(w["owner_id"])
            if owner and owner["username"] == p.username:
                raise PermissionDenied(
                    "Whoever owns the challenger does not decide whether it replaces the champion"
                )
            state = "promoted" if decision == "promote" else "retained"
            out = uow.repo("challenges").update(
                challenge_id,
                {
                    "state": state,
                    "decided_by": p.username,
                    "decided_at": utcnow(),
                    "rationale": rationale.strip(),
                },
            )
            uow.audit(
                f"challenge.{state}",
                object_type="challenge",
                object_ref=challenge_id,
                detail={"verdict": row["result"].get("verdict"), "rationale": rationale.strip()},
            )
            return self._describe(uow, out)
