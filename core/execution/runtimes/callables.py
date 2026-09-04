"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Registered Python callables.

The simplest runtime, and the one a deployment uses to demonstrate the whole
governed path before it has any real artifacts. A callable is bound to a version
id in process, so there is nothing to load and nothing to verify — which is
exactly why it is unsuitable for anything but development, and says so.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from core.execution.errors import WarrantError
from core.execution.runtimes.base import Invocation


class CallableRuntime:
    """Invokes a callable bound to a version id."""

    key = "python.callable"

    # A descriptor-only realisation means MAYA holds the governance and does not
    # locate the artifact -- the engine supplies the model. A bound callable is
    # exactly that, so the same runtime answers for both keys. This is the vendor
    # black box case: the bank holds the licence, the engine holds the artifact.
    ALSO = ("descriptor_only",)

    def __init__(self) -> None:
        self._bound: Dict[str, Callable[[Dict[str, Any]], Any]] = {}

    def bind(self, version_id: str, fn: Callable[[Dict[str, Any]], Any]) -> None:
        self._bound[version_id] = fn

    def available(self) -> Optional[str]:
        return None

    def invoke(self, call: Invocation) -> Any:
        fn = self._bound.get(call.version_id)
        if fn is None:
            runtime = (call.warrant.get("realisation") or {}).get("runtime")
            if runtime == "descriptor_only":
                raise WarrantError(
                    "no_runtime",
                    f"version {call.version_id} is registered descriptor-only, so "
                    "MAYA does not locate its artifact and this engine must supply "
                    "the model itself — and nothing is bound for it",
                    "bind the vendor's model to this version in the engine, or "
                    "register the version with a locatable artifact and a runtime")
            raise WarrantError(
                "no_runtime",
                f"no callable is bound for version {call.version_id}",
                "bind one with engine.register_runtime(version_id, fn), or "
                "register the version with a locatable artifact and a real runtime")
        return fn(call.inputs)
