"""Gate 3a — the SDK's public surface against a committed snapshot (plan §7).

What an SDK user can call: ``maya.sdk.__all__``, and for ``Client`` and
``AsyncClient`` every public method and every resource namespace's public
methods, each with its signature (parameter names, kinds, defaults). The
snapshot is ``tools/ci/public_symbols.lock.json``; a removed or changed symbol
breaks someone's code, so any difference fails until
``python tools/ci/public_symbols.py --update`` records it as intended.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import inspect
import json
import sys
from typing import Any

from _common import ROOT, report

LOCK = ROOT / "tools" / "ci" / "public_symbols.lock.json"


def _sig(fn: Any) -> str:
    try:
        sig = inspect.signature(fn)
    except (TypeError, ValueError):
        return "?"
    params = [p.replace(annotation=inspect.Parameter.empty) for p in sig.parameters.values()]
    return str(sig.replace(parameters=params, return_annotation=inspect.Signature.empty))


def _methods(cls: type) -> dict[str, str]:
    return {name: _sig(fn) for name, fn in sorted(inspect.getmembers(cls, callable))
            if not name.startswith("_")}


def surface() -> dict[str, Any]:
    import maya.sdk as sdk
    from maya.sdk.client import AsyncClient, Client
    out: dict[str, Any] = {"maya.sdk.__all__": sorted(sdk.__all__)}
    for cls in (Client, AsyncClient):
        entry: dict[str, Any] = {"methods": _methods(cls), "namespaces": {}}
        probe = cls.__new__(cls)
        probe._bind(object())                       # namespaces, bound to nothing
        for name, value in sorted(vars(probe).items()):
            if not name.startswith("_") and inspect.isclass(type(value)) and \
                    type(value).__module__.startswith("maya.sdk"):
                entry["namespaces"][name] = {"class": type(value).__name__,
                                             "methods": _methods(type(value))}
        out[cls.__name__] = entry
    return out


def _diff(old: Any, new: Any, where: str = "") -> list[str]:
    if isinstance(old, dict) and isinstance(new, dict):
        out = [f"removed {where}.{k}" for k in sorted(set(old) - set(new))]
        out += [f"added {where}.{k}" for k in sorted(set(new) - set(old))]
        for k in sorted(set(old) & set(new)):
            out += _diff(old[k], new[k], f"{where}.{k}")
        return out
    return [] if old == new else [f"changed {where}: {old} -> {new}"]


def main(argv: list[str]) -> int:
    now = surface()
    if "--update" in argv:
        LOCK.write_text(json.dumps(now, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        print(f"wrote {LOCK.relative_to(ROOT)}")
        return 0
    if not LOCK.exists():
        return report("SDK public symbols", [f"{LOCK.name} is missing; run with --update"])
    changes = _diff(json.loads(LOCK.read_text(encoding="utf-8")), now)
    if changes:
        changes.append("if intended: python tools/ci/public_symbols.py --update, and review")
    return report("SDK public symbols", changes)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
