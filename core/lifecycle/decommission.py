"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Taking a model out of service, and the four things that are usually forgotten.

## What `retire` was, and what it was missing

`retire` is a governed transition that deletes nothing, requires a reason, and
appends an evidence node. That is the hard half and it was built first, which
was right.

`FR-INV-018` asks for four more things, and every one of them is a thing a firm
discovers it needed **months later**:

| | The question it answers, asked afterwards |
|---|---|
| **Rationale** | *why was this taken out?* — `reason` existed, as free text on one transition |
| **Replacement** | *what is doing this job now?* |
| **Downstream notification** | *who was relying on it, and were they told?* |
| **Retention class** | *how long do we keep it, and under which obligation?* |

None of those is hard to store. The reason they go missing is that retiring a
model is the moment everybody involved has stopped caring about it, and a form
field nobody is required to fill in is a form field left empty.

## The three refusals

**A retirement with unnotified consumers is refused.** The register already
knows who they are — `blast_radius` computes the models downstream of this one,
typed through `input_to` edges. Retiring into that silently is how a feeder
model disappears and four downstream models start reading nulls that somebody
turns into zeros. The refusal is escapable, deliberately: `acknowledged` records
that somebody looked at the list and decided, which is a different fact from
nobody having looked.

**A replacement that is not registered is refused.** *Replaced by the new
scorecard* is not a replacement link, it is a sentence. If the successor is not
in the register, the honest answers are `none` — genuinely nothing does this job
now — or register it first.

**A retention class MAYA does not have is refused by name.** The classes exist
because the obligations differ: AI Act Art. 19 asks for logs over the system's
lifetime, SOX for seven years of what supported a financial statement, and data
protection for *less* time. A free-text class would be a retention schedule
nobody can act on.

## And what it still does not do

**It notifies nobody.** `notified` records who was *told*, as an attestation by
whoever retired the model — MAYA does not send the mail, because the people who
depend on a model are reachable through channels it does not own, and a platform
claiming to have notified them would be claiming a delivery it never made.

**It archives nothing and deletes nothing.** A retention class is a *statement
of the obligation*, and `core/retention/` already reports the difference between
the backing a class requires and the backing a deployment has. Retiring a model
does not move a byte.
"""
from __future__ import annotations

import time
from typing import Any, Dict, Optional, Sequence, Tuple

from core.lifecycle.common import LifecycleError
from core.log import get_logger
from core.retention import CLASSES

logger = get_logger(__name__)

#: What a decommissioning record has to carry, and why each one is asked for
#: at the moment everybody has stopped caring about the model.
REQUIRED: Tuple[Tuple[str, str], ...] = (
    ("rationale", "why it is being taken out, in more than a word. `retire` "
                  "always required a reason; this is the same field asked for "
                  "properly, because *superseded* answers nothing in two years"),
    ("replacement", "what does this job now — a registered URN, or the "
                    "explicit `none`. Not free text: *replaced by the new "
                    "scorecard* is a sentence, not a link"),
    ("retention_class", "how long the record is kept and under which "
                        "obligation. The classes differ because the "
                        "obligations do"),
)

#: The answer when genuinely nothing replaces it. Spelled out rather than left
#: blank, because blank is indistinguishable from *nobody filled this in* — and
#: a model withdrawn with nothing taking its place is a fact somebody will want
#: to have been told deliberately.
NOTHING = "none"


class Decommissioning:
    """Records what a retirement is, and refuses the three silent versions."""

    def __init__(self, repo, registry, composition=None, lifecycle=None,
                 evidence=None):
        self.repo, self.registry = repo, registry
        self.composition, self.lifecycle = composition, lifecycle
        self.evidence = evidence

    # --------------------------------------------------------------- posture
    @staticmethod
    def posture() -> Dict[str, Any]:
        """What a decommissioning captures, and the two things it does not do."""
        return {
            "notifies_anybody": False,
            "archives_anything": False,
            "deletes_anything": False,
            "required": [{"field": f, "why": w} for f, w in REQUIRED],
            "retention_classes": sorted(CLASSES),
            "why_not_notify": (
                "the people who depend on a model are reachable through "
                "channels MAYA does not own. `notified` records who was TOLD, "
                "as an attestation by whoever retired it — a platform "
                "claiming to have notified them would be claiming a delivery "
                "it never made"),
            "why_not_archive": (
                "a retention class is a statement of the OBLIGATION, and "
                "`core/retention/` already reports the difference between the "
                "backing a class requires and the backing a deployment has. "
                "Retiring a model does not move a byte"),
            "detail": (
                "none of this is hard to store. It goes missing because "
                "retiring a model is the moment everybody involved has "
                "stopped caring about it, and a form field nobody is required "
                "to fill in is a form field left empty"),
        }

    # ------------------------------------------------------------- the check
    def consumers(self, urn: str) -> Dict[str, Any]:
        """Who is reading this model, before anybody retires it.

        Computed from the typed `input_to` edges the register already holds, so
        this is the register's own answer rather than somebody's recollection.
        """
        model = self.registry.require(urn)
        if self.composition is None:
            return {"urn": model["urn"], "known": False, "consumers": [],
                    "detail": ("the model graph is not wired, so MAYA cannot "
                               "say who depends on this. That is not the same "
                               "as nobody depending on it")}
        radius = self.composition.blast_radius(model["urn"])
        downstream = [m for m in (radius.get("reached") or [])
                      if m.get("urn") != model["urn"]]
        live = [m for m in downstream
                if m.get("status") not in ("retired", "deleted")]
        return {
            "urn": model["urn"], "known": True,
            "consumers": downstream, "live": [m["urn"] for m in live],
            "detail": (
                f"{len(live)} live model(s) read this one, of "
                f"{len(downstream)} reached"
                + (". Retiring into that silently is how a feeder model "
                   "disappears and four downstream models start reading nulls "
                   "that somebody turns into zeros" if live else
                   ". Nothing downstream depends on it")),
        }

    # ------------------------------------------------------------- recording
    def decommission(self, urn: str, *, rationale: str, replacement: str,
                     retention_class: str, notified: Optional[Sequence[str]] = None,
                     acknowledged: bool = False, actor: str = "system",
                     now: Optional[float] = None) -> Dict[str, Any]:
        """Record the decommissioning, then retire. Refuses the silent versions.

        The order matters: everything is validated **before** the transition,
        so a refusal leaves the model in service rather than half-retired with
        no record of why.
        """
        model = self.registry.require(urn)
        moment = now if now is not None else time.time()
        why = dict(REQUIRED)

        if not str(rationale).strip() or len(str(rationale).strip()) < 10:
            raise LifecycleError(
                "rationale_required",
                "a decommissioning needs a rationale somebody can read later",
                why["rationale"] + ". Ten characters is a low bar and it is "
                "there to stop `n/a`")
        replacement = str(replacement).strip()
        if not replacement:
            raise LifecycleError(
                "replacement_required",
                "no replacement was named",
                f"name the registered URN that does this job now, or "
                f"'{NOTHING}' if nothing does. Blank is indistinguishable "
                f"from nobody having filled it in, and a model withdrawn with "
                f"nothing taking its place is a fact somebody will want to "
                f"have been told deliberately")
        if replacement != NOTHING:
            self._require_registered(replacement)
        if retention_class not in CLASSES:
            raise LifecycleError(
                "unknown_retention_class",
                f"'{retention_class}' is not a retention class this platform "
                f"has",
                f"the classes are {', '.join(sorted(CLASSES))}. They differ "
                f"because the obligations do — AI Act Art. 19 asks for logs "
                f"over the system's lifetime, SOX for seven years of what "
                f"supported a financial statement, and data protection for "
                f"LESS time. A free-text class would be a retention schedule "
                f"nobody can act on")

        reading = self.consumers(model["urn"])
        unnotified = [u for u in reading.get("live") or []
                      if u not in set(notified or [])]
        if unnotified and not acknowledged:
            raise LifecycleError(
                "consumers_not_notified",
                f"{len(unnotified)} live model(s) read this one and are not "
                f"in `notified`: {', '.join(unnotified[:4])}",
                "list them in `notified` once they have been told, or set "
                "`acknowledged` to record that somebody looked at this list "
                "and decided anyway. The second is a different fact from "
                "nobody having looked, and both are better than a feeder "
                "model disappearing quietly")

        row = {
            "model_id": model["id"], "urn": model["urn"],
            "rationale": str(rationale).strip(), "replacement": replacement,
            "retention_class": retention_class,
            "notified": list(notified or []),
            "unnotified": unnotified,
            "acknowledged": bool(acknowledged),
            "consumers_known": bool(reading.get("known")),
            "decommissioned_by": actor, "decommissioned_at": moment,
        }
        if self.evidence is not None:
            with self.evidence.recording():
                self.repo.add(row)
                self.evidence.append(
                    "model_decommissioned", "model", model["id"],
                    {k: v for k, v in row.items() if k != "model_id"},
                    actor=actor)
        else:
            self.repo.add(row)

        retired = self._retire(model, rationale, actor)
        logger.info("decommissioned %s, replaced by %s, retention %s",
                    model["urn"], replacement, retention_class)
        return {**row, "status": retired.get("status", "retired"),
                "retention": self._retention_note(retention_class),
                "detail": self._detail(row, reading)}

    def _require_registered(self, urn: str) -> None:
        try:
            self.registry.require(urn)
        except Exception as exc:
            logger.info("a decommissioning names '%s' as its replacement and "
                        "it is not registered: %s", urn, exc)
            raise LifecycleError(
                "replacement_not_registered",
                f"'{urn}' is not a model in this register",
                f"register the successor first, or record '{NOTHING}'. A "
                f"replacement that is not in the register is a sentence rather "
                f"than a link, and the question it is meant to answer — *what "
                f"does this job now* — is asked in two years by somebody who "
                f"cannot ask you") from exc

    def _retire(self, model: Dict[str, Any], rationale: str,
                actor: str) -> Dict[str, Any]:
        if self.lifecycle is None:
            return {"status": model.get("status")}
        if model.get("status") == "retired":
            # Already out of service. The record is still worth writing — the
            # four facts were missing before this existed, so every model
            # retired until now has a retirement with none of them.
            return {"status": "retired"}
        return self.lifecycle.retire(model, actor, rationale)

    @staticmethod
    def _retention_note(retention_class: str) -> Dict[str, Any]:
        spec = CLASSES.get(retention_class) or {}
        return {"class": retention_class, **spec,
                "note": ("a period is a FLOOR, never a ceiling. Confusing *may "
                         "now be deleted* with *must now be deleted* is how a "
                         "register loses the record that was about to be "
                         "asked for")}

    @staticmethod
    def _detail(row: Dict[str, Any], reading: Dict[str, Any]) -> str:
        out = (f"{row['urn']} is decommissioned, kept under the "
               f"'{row['retention_class']}' class")
        out += (f", replaced by {row['replacement']}"
                if row["replacement"] != NOTHING else
                ", with **nothing taking its place** — recorded deliberately "
                "rather than left blank")
        if row["notified"]:
            out += f". {len(row['notified'])} consumer(s) were told"
        if row["unnotified"]:
            out += (f". {len(row['unnotified'])} live consumer(s) were NOT "
                    f"told and somebody acknowledged that: "
                    f"{', '.join(row['unnotified'][:3])}")
        if not row["consumers_known"]:
            out += (". The model graph was not readable, so who depends on "
                    "this is unknown — which is not the same as nobody")
        out += (". Nothing was archived and nothing was deleted: the retention "
                "class states the obligation, and MAYA does not move bytes")
        return out

    # ----------------------------------------------------------- reading back
    def of(self, urn: str) -> Dict[str, Any]:
        """The decommissioning record for a model, if it has one."""
        model = self.registry.require(urn)
        row = self.repo.one(model_id=model["id"])
        if row is None:
            return {"urn": model["urn"], "decommissioned": False,
                    "status": model.get("status"),
                    "detail": ("no decommissioning record. A model retired "
                               "before this existed has one of the old "
                               "`retire` transitions instead, which carries a "
                               "reason and none of the other three facts"
                               if model.get("status") == "retired" else
                               "this model is in service")}
        return {**row, "decommissioned": True,
                "retention": self._retention_note(row["retention_class"])}

    def across_the_estate(self) -> Dict[str, Any]:
        """Retired models, and how many were decommissioned properly.

        The number worth having: a retirement recorded before this existed
        carries a reason and nothing else, so *retired* and *decommissioned*
        are two different populations and the gap between them is a backlog
        somebody can work.
        """
        retired, recorded = [], []
        for model in self.registry.list():
            if model.get("status") != "retired":
                continue
            retired.append(model["urn"])
            if self.repo.one(model_id=model["id"]):
                recorded.append(model["urn"])
        missing = [u for u in retired if u not in set(recorded)]
        return {
            "retired": len(retired), "decommissioned": len(recorded),
            "without_a_record": missing,
            "detail": (
                f"{len(recorded)} of {len(retired)} retired model(s) carry a "
                f"decommissioning record"
                + (f". The other {len(missing)} were retired with a reason and "
                   f"none of the other three facts — no replacement link, no "
                   f"notified list, no retention class. That is a backlog "
                   f"somebody can work rather than a defect"
                   if missing else
                   ". Every retirement says what replaced it, who was told "
                   "and how long it is kept")),
        }
