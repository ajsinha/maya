"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Which parts of this platform a deployment may extend, and which it may not.

The requirement asks for a plugin architecture across eight axes. Built as eight
open sockets it would be the fastest way to remove every control in this
platform, so the answer is not eight sockets — it is a **statement of which axes
are open and why the others are not**, with the open ones genuinely open.

**The dividing line is whether the extension changes a governance answer.**

A notification channel changes *how somebody is told*. A test type changes *what
was measured*, and the measurement is recorded with its own digest, reviewed by a
person, and challenged by a validator — the extension is inside a control rather
than around it. Those are safe to open, and they are open.

A runtime adapter changes *what may execute*. A format changes *what may be
loaded*. A policy evaluator changes *what the gate says*. A connector changes
*what the register will believe about data it did not see*. Each of those is a
place where a plugin is not an extension but a **removal**: the whole of the
artifact-format decision is that the vocabulary contains no `pickle`, and an open
format axis is a `pickle` loader arriving by pull request. So they stay closed,
and the refusal names what the closure is protecting rather than saying no.

**A closed axis is not a missing feature; it is the feature.** The alternative is
a platform whose controls a deployment can widen without anybody deciding to —
and a governance platform that can be extended into permissiveness is one whose
assurances mean whatever the last plugin author thought.

**Registering something is a governance act**, not an import. An open axis takes
a name, an owner and what it is for, refuses a name that already exists, and puts
the registration on the evidence chain — because *who added the test everybody
has been passing* is a question somebody will ask.
"""
from __future__ import annotations

import time
from typing import Any, Callable, Dict, List, Optional

from core.log import get_logger
from core.plugins.common import PluginError

logger = get_logger(__name__)

OPEN, CLOSED = "open", "closed"

#: The eight axes the requirement names, whether each is open, and — for the
#: closed ones — what the closure is protecting. The reason is the point: an
#: axis closed with no reason recorded is one somebody will open.
AXES: Dict[str, Dict[str, Any]] = {
    "test_types": {
        "state": OPEN,
        "is": "a measurement over two series, producing a value and a verdict",
        "why": "the extension sits INSIDE a control rather than around it: the "
               "result carries its own digest, a person reviews it, and a "
               "validator challenges it. A firm's own discrimination measure is "
               "exactly the kind of thing it should be able to add",
    },
    "metric_types": {
        "state": OPEN,
        "is": "a monitored quantity with a threshold and a cadence",
        "why": "same reason: a monitor's readings are evidence and are treated "
               "as evidence. A firm that measures something this platform has "
               "not heard of is a firm doing its job",
    },
    "templates": {
        "state": OPEN,
        "is": "a document shape, filled from the register",
        "why": "a template decides what a document SAYS, and every claim in it "
               "is still assembled from evidence the register holds — a "
               "template cannot make the platform believe anything",
    },
    "notification_channels": {
        "state": OPEN,
        "is": "somewhere to send a digest",
        "why": "it changes how somebody is told and nothing else. The one axis "
               "where a plugin has no governance meaning at all",
    },
    "connectors": {
        "state": CLOSED,
        "is": "a source the register will believe about data it did not see",
        "protects": "provenance. A connector decides what enters the register "
                    "as fact, and an open connector axis is a way to write "
                    "into the inventory without going through registration — "
                    "which is the one thing the inventory exists to prevent",
    },
    "formats": {
        "state": CLOSED,
        "is": "an artifact this platform will load",
        "protects": "the decision that the vocabulary contains no `pickle`. An "
                    "open format axis is a pickle loader arriving by pull "
                    "request, and 'we validate the artifact' without naming the "
                    "check is the sentence that precedes every incident",
    },
    "policy_evaluators": {
        "state": CLOSED,
        "is": "code that decides what a gate says",
        "protects": "the gates themselves. A policy evaluator that can return "
                    "*permitted* is a way to widen every control in the "
                    "platform from outside it, and a rule set is already the "
                    "supported way to change what a gate decides — declaratively, "
                    "reviewably, and without executing anybody's code",
    },
    "runtime_adapters": {
        "state": CLOSED,
        "is": "something that may execute a model",
        "protects": "the warrant grammar's four axes. A new model technology is "
                    "already a new value in one of them, which is extension "
                    "without arbitrary code — and an open adapter axis is "
                    "execution the grammar never described",
    },
}


def describe() -> Dict[str, Any]:
    """Every axis, its state, and what the closure protects."""
    rows = [{"axis": k, **v} for k, v in AXES.items()]
    open_axes = [r["axis"] for r in rows if r["state"] == OPEN]
    closed = [r["axis"] for r in rows if r["state"] == CLOSED]
    return {
        "axes": rows, "open": open_axes, "closed": closed,
        "detail": (
            f"{len(open_axes)} of {len(rows)} axes are open. The dividing line "
            f"is whether the extension changes a governance ANSWER: a "
            f"notification channel changes how somebody is told, and a runtime "
            f"adapter changes what may execute. The four closed ones are each a "
            f"place where a plugin would be a removal rather than an "
            f"extension — a closed axis here is not a missing feature, it is "
            f"the feature, because a governance platform that can be extended "
            f"into permissiveness is one whose assurances mean whatever the "
            f"last plugin author thought"),
    }


class ExtensionPoints:
    """Registers extensions on the open axes, and refuses the closed ones."""

    def __init__(self, evidence=None):
        self.evidence = evidence
        self._registered: Dict[str, Dict[str, Dict[str, Any]]] = {
            axis: {} for axis, spec in AXES.items() if spec["state"] == OPEN}

    # ------------------------------------------------------------- register
    def register(self, axis: str, name: str, *, owner: str, does: str,
                 implementation: Optional[Callable] = None,
                 actor: str = "system") -> Dict[str, Any]:
        """Add something on an open axis. A governance act, not an import."""
        spec = AXES.get(axis)
        if spec is None:
            raise PluginError(
                "unknown_axis", f"'{axis}' is not an extension axis",
                "one of " + ", ".join(AXES))
        if spec["state"] == CLOSED:
            raise PluginError(
                "axis_closed",
                f"'{axis}' is closed, and that is the feature rather than a "
                f"missing one. It protects {spec['protects']}",
                self._alternative(axis))
        if not (owner or "").strip():
            raise PluginError(
                "owner_required",
                "an extension with no owner is code nobody answers for, "
                "running inside a governance platform",
                "name the person or team accountable for it")
        if not (does or "").strip():
            raise PluginError(
                "purpose_required",
                "an extension that does not say what it is for is one nobody "
                "can decide to remove",
                "say what it measures, sends or produces")
        if name in self._registered[axis]:
            existing = self._registered[axis][name]
            raise PluginError(
                "already_registered",
                f"'{name}' is already registered on {axis} by "
                f"{existing['owner']}. Silently replacing it would change what "
                f"a recorded result MEANS without changing its name, and every "
                f"measurement taken under the old one would still say it was "
                f"taken under this",
                "register it under a different name; a measurement's name is "
                "part of what the measurement claims")

        row = {"axis": axis, "name": name, "owner": owner.strip(),
               "does": does.strip(), "registered_by": actor,
               "registered_at": time.time(),
               "implementation": implementation}
        self._registered[axis][name] = row
        if self.evidence is not None:
            with self.evidence.recording():
                self.evidence.append(
                    "extension_registered", "platform", axis,
                    {"axis": axis, "name": name, "owner": owner,
                     "does": does}, actor=actor)
        logger.info("extension '%s' registered on %s by %s", name, axis, actor)
        return {k: v for k, v in row.items() if k != "implementation"}

    @staticmethod
    def _alternative(axis: str) -> str:
        """What to do instead. A refusal that names no route is a wall."""
        return {
            "connectors": ("import through the baseline path, which records "
                           "what arrived and what it is missing rather than "
                           "asserting it as fact"),
            "formats": ("use one of the permitted formats. If a genuinely new "
                        "one is needed, it is a change to the vocabulary and "
                        "goes through review — which is the point"),
            "policy_evaluators": ("author a rule set. It changes what a gate "
                                  "decides, declaratively and reviewably, "
                                  "without executing anybody's code"),
            "runtime_adapters": ("add the technology to the warrant grammar's "
                                 "vocabularies. A new model technology is "
                                 "already a new value in one of four axes, "
                                 "which is extension without arbitrary code"),
        }.get(axis, "there is no route on this axis, deliberately")

    # ------------------------------------------------------------------ read
    def registered(self, axis: str = "") -> Dict[str, Any]:
        """What this deployment has added."""
        if axis and axis not in AXES:
            raise PluginError("unknown_axis",
                              f"'{axis}' is not an extension axis",
                              "one of " + ", ".join(AXES))
        rows = []
        for name, extensions in self._registered.items():
            if axis and name != axis:
                continue
            for row in extensions.values():
                rows.append({k: v for k, v in row.items()
                             if k != "implementation"})
        rows.sort(key=lambda r: (r["axis"], r["name"]))
        axes = describe()
        return {
            "extensions": rows, "count": len(rows),
            **axes,
            # The axis map's own reading, kept rather than overwritten: *why
            # four are closed* and *what this deployment added* are different
            # answers and a reader needs both.
            "axes_detail": axes["detail"],
            "detail": (
                f"{len(rows)} extension(s) registered on the open axes"
                if rows else
                "nothing has been registered. The open axes are open and "
                "unused, which is the resting state — and the closed ones are "
                "closed on purpose"),
        }

    def get(self, axis: str, name: str) -> Optional[Callable]:
        """The implementation, for whatever dispatches on this axis."""
        return (self._registered.get(axis, {}).get(name) or {}).get(
            "implementation")

    def names(self, axis: str) -> List[str]:
        return sorted(self._registered.get(axis, {}))
