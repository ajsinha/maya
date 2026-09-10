"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

What a model was asked, and what it answered.

`core/execution/invocations.py` records the **shape** of every call — who, what
for, which version, how long, how it ended — and deliberately holds no content,
because content carries personal data and a table that quietly accumulated it
would be a retention problem nobody decided to take on. This is the other half,
and everything about it is arranged so that the retention problem is one
somebody *did* decide to take on.

**The digest is the default; the values are the exception.** Every logged
inference carries a digest of what went in and what came out. That is enough for
the question AI Act Art. 12 is actually about — *is this the call that produced
that decision* — and it holds neither the features nor the prediction. Retaining
the values is a separate decision, taken per model, with a reason and an end
date.

**The digest is keyed, and that is not decoration.** An unkeyed digest of a small
feature vector — an age, a postcode, a risk band — is a lookup table anybody with
the same hash function can enumerate, and a "digest instead of the data" that can
be reversed in an afternoon is worse than storing the data, because it is stored
under a name that stops anybody worrying about it. The key lives in
configuration and never in the row.

**Sampling is by tier, and the interesting calls are never sampled out.** A tier
1 model logs everything; a tier 4 logs a fraction. But a refusal, a boundary
violation and an error are kept **whatever the rate**, because the sample exists
to make the rare thing visible and sampling out the rare thing is exactly
backwards. Each row says which of those reasons put it there, since a sample
nobody can explain is a sample nobody trusts.

**Retention is by classification, and it runs the other way from what people
expect.** `restricted` data is kept for the *shortest* time, not the longest. The
instinct is that important data should be kept longer; the law is that data you
should not be holding should be held for less time. The classification comes from
`core/classification/`, so the retention of a model's inference log is derived
from the features it reads rather than from anybody's guess about them.
"""
from __future__ import annotations

import hashlib
import hmac
import random
import time
from typing import Any, Dict, List, Optional

from core.log import get_logger
from db.database import digest as canonical_digest

logger = get_logger(__name__)

DAY = 86400.0

#: Why a row exists. The interesting ones are kept for a different reason from
#: the ordinary ones, and saying which is the difference between a sample
#: somebody can reason about and a pile of rows.
REASONS: Dict[str, str] = {
    "sampled": "the tier's sampling rate selected it",
    "refused": "the call was refused, and a refusal is never sampled out",
    "boundary": "the call fell outside the version's operating contract",
    "error": "the call failed, and a failure is never sampled out",
    "always": "content retention is on for this model, so every call is kept",
}

#: What fraction of ordinary calls is kept, by tier. A tier 1 model's every call
#: is worth having; a tier 4's estate-wide log at the same rate would be a
#: storage bill nobody agreed to and a haystack nobody searches.
SAMPLE_BY_TIER: Dict[int, float] = {1: 1.0, 2: 0.25, 3: 0.05, 4: 0.01}
DEFAULT_SAMPLE = 0.01

#: How long a row is kept, by data classification — and note the direction. The
#: instinct is that important data should be kept longer; the obligation is that
#: data you should not be holding should be held for less time.
RETAIN_DAYS: Dict[str, float] = {
    "public": 3 * 365.0,
    "internal": 2 * 365.0,
    "confidential": 365.0,
    "restricted": 90.0,
}
DEFAULT_RETAIN_DAYS = 365.0

#: The outcomes that are always kept, whatever the sampling rate says.
ALWAYS = ("refused", "error")


class InferenceLog:
    """Records what a model was asked and answered, at a rate somebody chose."""

    def __init__(self, repo, registry, classification=None, key: str = "",
                 sampler=None):
        self.repo, self.registry = repo, registry
        # Where the retention comes from. Without it every row takes the
        # default, and the estate view says how many are doing so — a retention
        # period nobody chose is one nobody owns.
        self.classification = classification
        # The digest key. Empty is allowed and is REPORTED rather than
        # tolerated: an unkeyed digest of a small feature vector is a lookup
        # table, and a platform that pretended otherwise would be storing
        # personal data under a name that stops anybody worrying about it.
        self.key = key
        self._roll = sampler or random.random

    # ---------------------------------------------------------------- record
    def record(self, urn: str, *, principal: str,
               features: Optional[Dict[str, Any]] = None,
               prediction: Any = None,
               explanation: Optional[Dict[str, Any]] = None,
               outcome: str = "ok", semver: Optional[str] = None,
               latency_ms: Optional[float] = None,
               request_id: Optional[str] = None,
               invocation_id: Optional[str] = None,
               boundary_ok: bool = True,
               retain_content: bool = False,
               now: Optional[float] = None) -> Optional[Dict[str, Any]]:
        """Log one inference, or decline to and say why.

        Returns `None` when the sampler did not select the call — which is the
        ordinary case for a low-tier model and is not a failure. The digests are
        computed whether or not the row is kept, because computing them is the
        cheap part and skipping it would make the decision depend on the data.
        """
        model = self.registry.require(urn)
        moment = now if now is not None else time.time()
        reason = self._reason(model, outcome, boundary_ok, retain_content)
        if reason is None:
            return None

        classification = self._classification(urn)
        retain = RETAIN_DAYS.get(classification, DEFAULT_RETAIN_DAYS)
        version = self._version(urn, semver)
        row = {
            "invocation_id": invocation_id, "model_id": model["id"],
            "model_version_id": version, "request_id": request_id,
            "principal": principal,
            "feature_digest": self.digest(features or {}),
            "prediction_digest": self.digest({"prediction": prediction}),
            # Null unless somebody decided to retain content for this model.
            # That decision has a reason and an end date attached, which is the
            # whole difference between a governed log and a data lake.
            "features": features if retain_content else None,
            "prediction": {"value": prediction} if retain_content else None,
            "explanation": explanation if retain_content else None,
            "latency_ms": latency_ms, "outcome": outcome, "reason": reason,
            "classification": classification,
            "retain_until": moment + retain * DAY, "at": moment,
        }
        return self.repo.add(row)

    def _reason(self, model: Dict[str, Any], outcome: str, boundary_ok: bool,
                retain_content: bool) -> Optional[str]:
        """Whether to keep this call, and what put it in the log.

        Order matters. The interesting reasons are checked before the sampler,
        because a refusal that the sampler happened to select would be recorded
        as `sampled` — and then a reader counting refusals would be counting a
        coincidence.
        """
        if outcome in ALWAYS:
            return outcome if outcome in REASONS else "error"
        if not boundary_ok:
            return "boundary"
        if retain_content:
            return "always"
        rate = SAMPLE_BY_TIER.get(model.get("tier") or 4, DEFAULT_SAMPLE)
        return "sampled" if self._roll() < rate else None

    # --------------------------------------------------------------- digest
    def digest(self, value: Any) -> str:
        """A keyed digest of what was asked or answered.

        Keyed with HMAC rather than salted-and-stored: a salt on the row makes
        the row self-contained and therefore enumerable by anybody who has the
        row, which is the opposite of what a digest instead of the data is for.
        The key is configuration and is never written down beside the digest.
        """
        canonical = canonical_digest(value)
        if not self.key:
            # Reported rather than refused: an instance running without a key
            # still logs, and `posture` says the digests are enumerable so
            # somebody can decide about it. Refusing here would mean an
            # unconfigured instance silently logs nothing at all, which is a
            # worse failure and a quieter one.
            return canonical
        return "hmac:" + hmac.new(self.key.encode("utf-8"),
                                  canonical.encode("utf-8"),
                                  hashlib.sha256).hexdigest()

    def _classification(self, urn: str) -> str:
        if self.classification is None:
            return "internal"
        try:
            return self.classification.of_model(urn)["classification"]
        except Exception:
            logger.warning("could not derive a classification for %s; the "
                           "inference log falls back to the default retention",
                           urn, exc_info=True)
            return "internal"

    def _version(self, urn: str, semver: Optional[str]) -> Optional[str]:
        if not semver:
            versions = self.registry.versions(urn)
            return versions[-1]["id"] if versions else None
        found = self.registry.version(urn, semver)
        return found["id"] if found else None

    # ------------------------------------------------------------------ read
    def for_model(self, urn: str, limit: int = 100) -> Dict[str, Any]:
        model = self.registry.require(urn)
        rows = self.repo.many(model_id=model["id"])[-limit:]
        by_reason: Dict[str, int] = {}
        for row in rows:
            by_reason[row["reason"]] = by_reason.get(row["reason"], 0) + 1
        held = sum(1 for row in rows if row.get("features") is not None)
        return {
            "urn": urn, "inferences": rows, "count": len(rows),
            "by_reason": by_reason, "holding_content": held,
            "sample_rate": SAMPLE_BY_TIER.get(model.get("tier") or 4,
                                              DEFAULT_SAMPLE),
            "detail": self._detail(model, rows, by_reason, held),
        }

    @staticmethod
    def _detail(model, rows, by_reason, held) -> str:
        if not rows:
            return ("nothing has been logged for this model — which means "
                    "either that it has not been called or that the sampler "
                    "has not selected a call, and those are different facts")
        rate = SAMPLE_BY_TIER.get(model.get("tier") or 4, DEFAULT_SAMPLE)
        out = (f"{len(rows)} inference(s) logged at a tier "
               f"{model.get('tier')} sampling rate of {100 * rate:.0f}%: "
               + ", ".join(f"{n} {reason}"
                           for reason, n in sorted(by_reason.items())))
        if held:
            out += (f". {held} of them hold the feature values themselves, "
                    f"which is a retention decision somebody took rather than "
                    f"a default")
        return out

    # ------------------------------------------------------------- retention
    def expire_due(self, now: Optional[float] = None) -> Dict[str, Any]:
        """Delete what nobody may keep any longer.

        A real deletion, not a flag. A retention period enforced by a column
        somebody could select around is not a retention period, and this is the
        one table in the platform where deleting is the correct behaviour —
        everything else is append-only because its content is the record, and
        this one's content is somebody else's personal data.
        """
        moment = now if now is not None else time.time()
        dropped = 0
        by_class: Dict[str, int] = {}
        for row in self.repo.many():
            if (row.get("retain_until") or 0) > moment:
                continue
            self.repo.remove(id=row["id"])
            dropped += 1
            key = row.get("classification") or "internal"
            by_class[key] = by_class.get(key, 0) + 1
        return {
            "dropped": dropped, "by_classification": by_class,
            "detail": (f"{dropped} inference record(s) reached the end of "
                       f"their retention and were deleted. Deleted rather than "
                       f"marked: a retention period enforced by a column "
                       f"somebody could select around is not a retention period"
                       if dropped else
                       "no inference record has reached the end of its "
                       "retention"),
        }

    # --------------------------------------------------------------- posture
    def posture(self, now: Optional[float] = None) -> Dict[str, Any]:
        """What this instance is holding, and what it is not saying about it."""
        moment = now if now is not None else time.time()
        rows = self.repo.many()
        overdue = [r for r in rows if (r.get("retain_until") or 0) <= moment]
        with_content = [r for r in rows if r.get("features") is not None]
        by_class: Dict[str, int] = {}
        for row in rows:
            key = row.get("classification") or "internal"
            by_class[key] = by_class.get(key, 0) + 1
        return {
            "records": len(rows), "holding_content": len(with_content),
            "by_classification": by_class,
            "past_retention": len(overdue),
            "keyed_digests": bool(self.key),
            "retention_days": dict(RETAIN_DAYS),
            "sampling": dict(SAMPLE_BY_TIER),
            "detail": self._posture_detail(rows, with_content, overdue,
                                           bool(self.key)),
        }

    @staticmethod
    def _posture_detail(rows, with_content, overdue, keyed) -> str:
        out = (f"{len(rows)} inference record(s), {len(with_content)} of them "
               f"holding the feature values themselves")
        if overdue:
            out += (f". {len(overdue)} are past their retention and have not "
                    f"been deleted, which means the batch has not run — and a "
                    f"retention period nothing enforces is a policy document")
        if not keyed:
            out += (". The digests are UNKEYED on this instance, so a digest "
                    "of a small feature vector — an age, a postcode, a band — "
                    "is a lookup table anybody with the same hash function can "
                    "enumerate. Set `inference.digest_key`")
        return out

    def retained(self) -> List[Dict[str, Any]]:
        """Which models are holding content, for a reader who has to justify it."""
        out = []
        for model in self.registry.list():
            rows = [r for r in self.repo.many(model_id=model["id"])
                    if r.get("features") is not None]
            if rows:
                out.append({"urn": model.get("urn"), "records": len(rows),
                            "classification": rows[0].get("classification")})
        return out
