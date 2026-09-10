"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Finding what a firm has installed, and the reason finding it is not using it.

A bank's own test type, its own document template, its own fibre for a class its
estate has and this one does not --- all of these belong in the firm's own
package rather than in a pull request against this repository. `entry_points`
is the ordinary Python answer and it is the right one.

It also has a property that is fine for a plotting library and not fine here:
**an entry point takes effect because something was installed.** A transitive
dependency bump, a base image rebuild, a `pip install` somebody ran to fix an
unrelated problem --- any of those can put code into a governance platform, and
nobody reviewed a change because nobody made one.

So the two acts are separated, and the separation is the whole module.

  * **`discover()` reads and does not import.** It lists what declares itself,
    from packaging metadata, without executing a line of it. An entry point can
    be *seen* without being trusted.
  * **`enable()` imports, and only what configuration names.** Installing makes
    a plugin available; a firm's own configuration makes it used. A control
    changed by a dependency bump is not a control.

**A closed axis is reported, not ignored.** A package declaring itself against
`runtime_adapters` --- an axis closed because execution the grammar never
described is not extension --- comes back as *refused, and here is the axis and
why it is closed*. Silently skipping it would lose the one fact worth having:
somebody tried, and either they misunderstood the boundary or they disagree with
it, and both are worth a conversation.

**And a fibre may add obligations and never remove one.** A third-party fibre
for a trainability class is genuinely useful --- a firm with an estate this
vocabulary does not describe should be able to say what its own class owes ---
but a fibre that could *drop* an obligation is a way to loosen every control on
that class from outside the platform. Load-time comparison against the shipped
fibre refuses a narrowing by name. This is the same rule configuration-as-code
follows, arriving in a second place because it is the same risk: the thing that
makes extension safe is that it can only tighten.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Sequence, cast

from core.log import get_logger
from core.plugins.common import PluginError
from core.plugins.registry import AXES, OPEN

logger = get_logger(__name__)

#: The entry-point group a firm's package declares against. One group with the
#: axis in the name rather than a group per axis, so a listing is one read and
#: an unknown axis is visible rather than silently unlisted.
GROUP = "maya.extensions"

SEEN, ENABLED, REFUSED = "seen", "enabled", "refused"
STATES = (SEEN, ENABLED, REFUSED)

#: Fibres are extensible and constrained. Declared here rather than in AXES
#: because the constraint is not "open or closed" — it is "open, and only
#: upward", which is a third state the axis table does not have and should not
#: grow for one member.
FIBRES = "fibres"
FIBRE_RULE = (
    "a third-party fibre may ADD evidence obligations to a trainability class "
    "and may never remove one. A fibre that could drop an obligation is a way "
    "to loosen every control on that class from outside the platform, and the "
    "thing that makes extension safe is that it can only tighten"
)


class PluginDiscovery:
    """Lists what is installed. Imports only what configuration names."""

    def __init__(self, extensions=None, fibres=None, enabled=None,
                 evidence=None):
        self.extensions, self.fibres = extensions, fibres
        # What this firm has decided to use. Empty means nothing is enabled,
        # which is the correct resting state for a fresh install: the packages
        # that happen to be present have not been chosen.
        self.enabled = list(enabled or [])
        self.evidence = evidence

    # -------------------------------------------------------------- discover
    def discover(self, now: Optional[float] = None) -> Dict[str, Any]:
        """What declares itself, read from metadata. Nothing is imported."""
        moment = now if now is not None else time.time()
        found: List[Dict[str, Any]] = []
        for point in self._entry_points():
            axis, name = _split(point.name)
            found.append(self._describe(point, axis, name))
        found.sort(key=lambda r: (r["state"] != REFUSED, r["axis"], r["name"]))
        by_state: Dict[str, int] = {}
        for row in found:
            by_state[row["state"]] = by_state.get(row["state"], 0) + 1
        return {
            "group": GROUP, "found": found, "count": len(found),
            "by_state": by_state,
            "enabled": list(self.enabled),
            "imported_anything": False,
            "discovered_at": moment,
            "detail": self._detail(found, by_state),
        }

    @staticmethod
    def _entry_points() -> List[Any]:
        """Packaging metadata only. This does not import the package."""
        from importlib.metadata import entry_points
        try:
            return list(entry_points(group=GROUP))
        except TypeError:                       # pragma: no cover - old API
            # Python 3.9 has no `group=` keyword and returns a mapping. The
            # cast is because the two versions genuinely return different
            # types and the checker only ever sees this one's; without it the
            # fallback fails to type-check on the platform that does not need
            # it, which is a poor reason to drop support for the one that does.
            logger.debug("entry_points(group=...) unsupported; falling back")
            legacy = cast(Any, entry_points())
            return list(legacy.get(GROUP, []))

    def _describe(self, point: Any, axis: str, name: str) -> Dict[str, Any]:
        spec = AXES.get(axis)
        if axis == FIBRES:
            return {"axis": axis, "name": name, "declares": point.value,
                    "distribution": _distribution(point),
                    "state": ENABLED if self._is_enabled(axis, name) else SEEN,
                    "rule": FIBRE_RULE, "why": ""}
        if spec is None:
            return {"axis": axis, "name": name, "declares": point.value,
                    "distribution": _distribution(point), "state": REFUSED,
                    "why": (f"'{axis}' is not an extension axis this platform "
                            f"has. The axes are {', '.join(sorted(AXES))} and "
                            f"{FIBRES}, and an entry point naming something "
                            f"else is reported rather than ignored — somebody "
                            f"either misunderstood the boundary or disagrees "
                            f"with it, and both are worth knowing")}
        if spec["state"] != OPEN:
            return {"axis": axis, "name": name, "declares": point.value,
                    "distribution": _distribution(point), "state": REFUSED,
                    "why": (f"'{axis}' is closed, and it protects "
                            f"{spec.get('protects', 'a control')}. A package "
                            f"declaring against it is reported rather than "
                            f"skipped, because the fact that somebody tried is "
                            f"the part worth having")}
        return {"axis": axis, "name": name, "declares": point.value,
                "distribution": _distribution(point),
                "state": ENABLED if self._is_enabled(axis, name) else SEEN,
                "why": ""}

    def _is_enabled(self, axis: str, name: str) -> bool:
        return f"{axis}:{name}" in self.enabled or f"{axis}:*" in self.enabled

    @staticmethod
    def _detail(found: Sequence[Dict[str, Any]],
                by_state: Dict[str, int]) -> str:
        if not found:
            return (f"nothing declares itself under `{GROUP}`. That is the "
                    f"ordinary state for a stock install and it is read from "
                    f"packaging metadata rather than assumed — nothing was "
                    f"imported to find out")
        out = (f"{len(found)} entry point(s): "
               + ", ".join(f"{n} {s}" for s, n in sorted(by_state.items())))
        refused = [r for r in found if r["state"] == REFUSED]
        if refused:
            out += (f". {len(refused)} declare against a closed or unknown "
                    f"axis and are named rather than skipped")
        seen = [r for r in found if r["state"] == SEEN]
        if seen:
            out += (f". {len(seen)} are installed and **not enabled**, which is "
                    f"the point of this listing: installing makes a plugin "
                    f"available and configuration makes it used. A control "
                    f"changed by a dependency bump is not a control")
        out += ". Nothing here was imported."
        return out

    # ---------------------------------------------------------------- enable
    def enable(self, axis: str, name: str, *, actor: str = "system",
               now: Optional[float] = None) -> Dict[str, Any]:
        """Import and register one plugin. Refused unless configuration names it.

        This is the only method here that executes third-party code, and it does
        so for exactly one entry point that a person put in configuration.
        """
        if not self._is_enabled(axis, name):
            raise PluginError(
                "not_enabled",
                f"'{axis}:{name}' is installed and is not enabled in this "
                f"firm's configuration",
                "add it under `plugins.enabled`. Installing a package makes an "
                "extension available; a person naming it makes it used — and a "
                "governance control that took effect because somebody bumped a "
                "dependency would be a control nobody changed on purpose")
        point = next((p for p in self._entry_points()
                      if _split(p.name) == (axis, name)), None)
        if point is None:
            raise PluginError(
                "not_installed",
                f"nothing declares '{axis}:{name}' under `{GROUP}`",
                "install the package that provides it, or remove it from "
                "`plugins.enabled` — a configuration naming a plugin that is "
                "not there is a control somebody believes is running")
        described = self._describe(point, axis, name)
        if described["state"] == REFUSED:
            raise PluginError(
                "axis_closed", described["why"],
                "extend through the supported axis instead; the refusal names "
                "which control the closure protects")

        moment = now if now is not None else time.time()
        loaded = point.load()                    # the one import, on purpose
        if axis == FIBRES:
            self._check_fibre(name, loaded)
        elif self.extensions is not None:
            self.extensions.register(
                axis, name, owner=_distribution(point) or "unknown",
                does=getattr(loaded, "__doc__", "") or "",
                fn=loaded, actor=actor)
        if self.evidence is not None:
            self.evidence.append(
                "plugin_enabled", "platform", f"{axis}:{name}",
                {"axis": axis, "name": name, "declares": point.value,
                 "distribution": _distribution(point)}, actor=actor)
        logger.info("enabled plugin %s:%s from %s", axis, name,
                    _distribution(point))
        return {**described, "state": ENABLED, "enabled_at": moment,
                "enabled_by": actor,
                "detail": (f"'{axis}:{name}' is loaded from "
                           f"{_distribution(point)}. It was imported because "
                           f"configuration named it, not because it was "
                           f"installed")}

    def _check_fibre(self, name: str, loaded: Any) -> None:
        """A fibre may add obligations and never remove one.

        Compared against the shipped fibre for the same class at load time,
        because a narrowing discovered at first use is a narrowing that has
        already been in force for a while.
        """
        if self.fibres is None:
            return
        shipped = getattr(self.fibres, "for_class", lambda _c: None)(name)
        if not shipped:
            return
        theirs = set(getattr(loaded, "obligations", lambda: set())() or set())
        ours = set(shipped.get("evidence") or shipped.get("obligations") or [])
        dropped = sorted(ours - theirs)
        if dropped:
            raise PluginError(
                "fibre_narrows_obligations",
                f"the fibre for '{name}' drops {', '.join(dropped)}, which this "
                f"platform's own fibre for that class requires",
                FIBRE_RULE)

    # ------------------------------------------------------------------ what
    @staticmethod
    def contract() -> Dict[str, Any]:
        """What a firm's package has to declare, and what it may extend."""
        return {
            "group": GROUP,
            "naming": "<axis>:<name>, e.g. `test_types:kendall_tau`",
            "open": [a for a, s in AXES.items() if s["state"] == OPEN] + [FIBRES],
            "closed": {a: s.get("protects", "")
                       for a, s in AXES.items() if s["state"] != OPEN},
            "fibre_rule": FIBRE_RULE,
            "installing_is_not_enabling": True,
            "detail": ("discovery reads packaging metadata and imports "
                       "nothing. Enabling imports exactly one entry point that "
                       "a person named in configuration — because an extension "
                       "that took effect because somebody bumped a dependency "
                       "is a governance control nobody changed on purpose"),
        }


def _split(raw: str) -> tuple:
    axis, _, name = raw.partition(":")
    return axis.strip(), (name.strip() or raw.strip())


def _distribution(point: Any) -> str:
    dist = getattr(point, "dist", None)
    return getattr(dist, "name", "") or getattr(dist, "metadata", {}).get(
        "Name", "") if dist else ""
