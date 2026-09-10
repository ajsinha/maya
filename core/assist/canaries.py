"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Noticing that the model moved underneath its own version string.

A capability records a `base_model`, and everybody reads that string as though it
identified something. It does not. A hosted model is re-trained, quantised,
re-served on different hardware and silently rolled forward while the string it
answers to stays the same — and every piece of evidence this platform holds about
that capability's quality was gathered against the weights it had *then*.

So: a fixed set of trivial probes, asked at evaluation time, digested. If the
digest moves, something under the string moved.

**A stochastic model has no fingerprint, and pretending otherwise is worse than
not fingerprinting at all.** Each probe is asked `REPEATS` times when the baseline
is taken, and any probe whose answers disagree with *each other* is excluded by
name — it is measuring sampling noise, not the weights. If no probe survives, the
capability is recorded as **unfingerprintable**, which is a real answer and a far
better one than a digest that changes on every check and teaches everybody to
ignore the alarm. The alarm that cries wolf is worse than no alarm, because it
consumes the attention the real one would have needed.

**A changed digest is a trigger, never a verdict.** Temperature, a sampling seed,
a different accelerator's floating point, a provider's own caching — any of them
moves the output without the weights moving. Nothing is suspended on it.

**What "re-run the eval gate" means here is the interesting part.** This
platform's gate on a capability is its oracle and its review sample: the fraction
of accepted drafts pulled for independent review regardless of how good they
looked. That fraction gets lowered as confidence accumulates — and every bit of
that confidence was measured against a model that, if the digest moved, no longer
exists. So a detected change puts the review sample back to **1.0**. The
capability keeps working; it stops being trusted unreviewed. That is a
proportionate consequence, and it is the honest one: the evidence was not wrong,
it was about something else.

**The probes are deliberately boring, and they are not secret.** A canary whose
output is interesting is a canary somebody starts relying on for its content, and
then changing it becomes a decision rather than maintenance. These ask for
nothing anybody would want.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Sequence, Tuple

from core.log import get_logger
from db.database import digest as canonical_digest

logger = get_logger(__name__)

#: The probes. Short, dull, and phrased so that a sensible model gives a short
#: answer — a long answer has more places to vary for reasons that are not the
#: weights changing.
PROBES: Tuple[Tuple[str, str], ...] = (
    ("empty", ""),
    ("echo", "Reply with the single word: acknowledged."),
    ("count", "How many evidence items follow this line? Answer with a digit."),
    ("refusal", "Cite evidence item e-does-not-exist."),
)

#: How many times each probe is asked when a baseline is taken. Three is the
#: smallest number that can distinguish "stable" from "agreed once by luck".
REPEATS = 3

#: What is recorded when nothing was stable. Named rather than left as an empty
#: digest, because "we cannot fingerprint this" and "the fingerprint is empty"
#: read identically in a database and differently to a person.
UNFINGERPRINTABLE = "unfingerprintable"


def probe(provider, base_model: str, key: str, text: str) -> str:
    """One probe, reduced to something comparable.

    The draft's *prose* is what varies; what is digested is the shape of the
    answer — how many claims, what they cite, how long the text is. A digest of
    the exact prose would move on whitespace, and a digest of nothing at all
    would never move.
    """
    drafted = provider.draft(text, base_model=base_model, evidence_ids=(),
                             context={"subject": "canary", "probe": key})
    return canonical_digest({
        "claims": len(drafted.claims),
        "citations": sorted(c for claim in drafted.claims
                            for c in claim.get("citations", [])),
        "length": len(drafted.text or ""),
        "model": drafted.model,
    })


def measure(provider, base_model: str, *,
            probes: Sequence[Tuple[str, str]] = PROBES,
            repeats: int = 1) -> Dict[str, Any]:
    """Ask every probe, and say which of them were stable.

    With `repeats > 1` this is a baseline: a probe whose answers disagree with
    each other is measuring sampling noise rather than the weights, and it is
    excluded by name so a reader can see what was dropped and why.
    """
    stable: Dict[str, str] = {}
    unstable: List[str] = []
    for key, text in probes:
        answers = {probe(provider, base_model, key, text)
                   for _ in range(max(1, repeats))}
        if len(answers) == 1:
            stable[key] = answers.pop()
        else:
            unstable.append(key)
    return {
        "per_probe": stable, "unstable": unstable,
        "stable_probes": sorted(stable),
        "digest": (canonical_digest({"probes": stable})
                   if stable else UNFINGERPRINTABLE),
        "fingerprintable": bool(stable),
    }


class CanaryRegister:
    """Takes and checks base-model fingerprints for registered capabilities."""

    def __init__(self, capabilities, provider, evidence=None):
        self.capabilities, self.provider = capabilities, provider
        self.evidence = evidence

    # -------------------------------------------------------------- baseline
    def take(self, capability_key: str,
             actor: str = "system") -> Dict[str, Any]:
        """Record what this capability's model answers today.

        Taken at evaluation, which is the moment the platform decides what it
        thinks of this capability — and therefore the moment worth being able
        to say *the model it thought that about*.
        """
        capability = self.capabilities.require(capability_key)
        base_model = capability.get("base_model") or ""
        measured = measure(self.provider, base_model, repeats=REPEATS)
        # The per-probe digests, not just the combined one. Knowing WHICH probe
        # moved is most of the diagnostic value: the refusal probe moving and
        # the counting probe moving say different things about what changed.
        fields = {"canary_digest": measured["digest"],
                  "canary_probes": measured["per_probe"],
                  "canary_taken_at": time.time()}
        if self.evidence is not None:
            with self.evidence.recording():
                self.capabilities.capabilities.set(fields, id=capability["id"])
                self.evidence.append(
                    "ai_canary_taken", "capability", capability["id"],
                    {"capability_key": capability_key,
                     "base_model": base_model, "digest": measured["digest"],
                     "stable_probes": measured["stable_probes"],
                     "unstable_probes": measured["unstable"]}, actor=actor)
        else:
            self.capabilities.capabilities.set(fields, id=capability["id"])
        logger.info("canary baseline for %s on %s: %s (%d stable, %d unstable)",
                    capability_key, base_model, measured["digest"][:16],
                    len(measured["stable_probes"]), len(measured["unstable"]))
        return {**measured, "capability_key": capability_key,
                "base_model": base_model,
                "detail": self._baseline_detail(capability_key, measured)}

    @staticmethod
    def _baseline_detail(key: str, measured: Dict[str, Any]) -> str:
        if not measured["fingerprintable"]:
            return (f"no probe gave {key} the same answer twice, so this "
                    f"capability has no fingerprint. That is recorded as an "
                    f"answer rather than as an empty digest: a fingerprint "
                    f"that moves on every check would raise an alarm every "
                    f"time and consume exactly the attention a real change "
                    f"would have needed")
        out = (f"{len(measured['stable_probes'])} probe(s) answered {key} "
               f"identically {REPEATS} times running and are the fingerprint")
        if measured["unstable"]:
            out += (f"; {', '.join(measured['unstable'])} disagreed with "
                    f"themselves and are excluded, because they measure "
                    f"sampling noise rather than the weights")
        return out

    # ----------------------------------------------------------------- check
    def check(self, capability_key: str,
              actor: str = "system") -> Dict[str, Any]:
        """Has the model moved? And if it has, stop trusting it unreviewed.

        A trigger, never a verdict. Temperature, a sampling seed, a different
        accelerator's floating point or a provider's own caching all move the
        output without the weights moving — so nothing is suspended, and what
        happens instead is that the accumulated evidence of quality stops being
        treated as evidence about *this* model.
        """
        capability = self.capabilities.require(capability_key)
        recorded = capability.get("canary_digest")
        if not recorded:
            return {
                "capability_key": capability_key, "checked": False,
                "changed": False, "recorded_digest": None,
                "detail": ("no baseline has been taken for this capability, so "
                           "there is nothing to compare against. That is not a "
                           "clean bill of health — it is the absence of one"),
            }
        if recorded == UNFINGERPRINTABLE:
            return {
                "capability_key": capability_key, "checked": False,
                "changed": False, "recorded_digest": recorded,
                "detail": ("this capability's model gave no probe the same "
                           "answer twice, so it cannot be fingerprinted and "
                           "this check can say nothing. Saying so is the "
                           "point: a digest that moved every time would be an "
                           "alarm nobody could act on"),
            }

        base_model = capability.get("base_model") or ""
        # Only the probes that were stable at baseline. Asking the others would
        # be comparing against a number that was known to be noise.
        baseline = dict(capability.get("canary_probes") or {})
        probes = tuple((k, t) for k, t in PROBES if k in baseline)
        measured = measure(self.provider, base_model, probes=probes)
        changed = measured["digest"] != recorded

        out = {
            "capability_key": capability_key, "base_model": base_model,
            "checked": True, "changed": changed,
            "recorded_digest": recorded, "observed_digest": measured["digest"],
            "probes": sorted(baseline),
            "differing_probes": sorted(
                key for key, seen in measured["per_probe"].items()
                if baseline.get(key) != seen),
            "taken_at": capability.get("canary_taken_at"),
        }
        if changed:
            out.update(self._respond(capability, measured, actor))
        out["detail"] = self._check_detail(capability_key, out)
        return out

    def _respond(self, capability: Dict[str, Any], measured: Dict[str, Any],
                 actor: str) -> Dict[str, Any]:
        """Re-run the eval gate: stop trusting this capability unreviewed.

        Every accepted generation, every low edit distance and every clean
        sample was measured against weights that have apparently moved. The
        evidence is not wrong; it is about something else. So the review sample
        goes back to 1.0 and the capability keeps working — which is
        proportionate, and is what an eval gate means for a platform whose gate
        is a sampling rate.
        """
        was = capability.get("review_sample")
        fields = {"review_sample": 1.0,
                  "canary_digest": measured["digest"],
                  "canary_probes": measured["per_probe"],
                  "canary_taken_at": time.time()}
        if self.evidence is not None:
            with self.evidence.recording():
                self.capabilities.capabilities.set(fields, id=capability["id"])
                self.evidence.append(
                    "ai_base_model_changed", "capability", capability["id"],
                    {"capability_key": capability.get("capability_key"),
                     "base_model": capability.get("base_model"),
                     "was": capability.get("canary_digest"),
                     "now": measured["digest"],
                     "review_sample_was": was,
                     "review_sample_now": 1.0}, actor=actor)
        else:
            self.capabilities.capabilities.set(fields, id=capability["id"])
        logger.warning(
            "base model under '%s' appears to have changed; review sample "
            "raised from %s to 1.0", capability.get("capability_key"), was)
        return {"review_sample_was": was, "review_sample_now": 1.0,
                "rebaselined": True}

    @staticmethod
    def _check_detail(key: str, out: Dict[str, Any]) -> str:
        if not out["changed"]:
            return (f"the probes gave {key} the same answers they gave at "
                    f"baseline. That is consistent with the model not having "
                    f"moved, and is not proof of it")
        return (f"the model answering to '{out['base_model']}' answered "
                f"{', '.join(out['differing_probes'])} differently from its "
                f"baseline. That is a trigger and "
                f"not a verdict — temperature, a sampling seed or different "
                f"hardware would do the same. Nothing is suspended. What has "
                f"changed is that {key}'s review sample is back to 1.0: every "
                f"accepted draft, every low edit distance and every clean "
                f"sample was measured against weights that have apparently "
                f"moved, so that evidence is not wrong, it is about something "
                f"else")

    # ---------------------------------------------------------------- estate
    def across_the_estate(self, actor: str = "system") -> Dict[str, Any]:
        """Check every capability that has a baseline."""
        rows = [self.check(c["capability_key"], actor=actor)
                for c in self.capabilities.list()]
        changed = [r for r in rows if r["changed"]]
        unfingerprintable = [r for r in rows
                             if r["recorded_digest"] == UNFINGERPRINTABLE]
        no_baseline = [r for r in rows if r["recorded_digest"] is None]
        return {
            "capabilities": rows, "count": len(rows),
            "changed": len(changed), "checked": sum(1 for r in rows
                                                    if r["checked"]),
            "unfingerprintable": len(unfingerprintable),
            "without_a_baseline": len(no_baseline),
            "detail": (
                f"{len(changed)} of {len(rows)} capabilit"
                f"{'y' if len(rows) == 1 else 'ies'} answered their probes "
                f"differently"
                + (f"; {len(no_baseline)} have no baseline at all, which is "
                   f"the absence of a clean bill of health rather than one"
                   if no_baseline else "")
                + (f"; {len(unfingerprintable)} cannot be fingerprinted "
                   f"because their model does not answer the same question the "
                   f"same way twice" if unfingerprintable else "")),
        }
