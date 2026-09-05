"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Which runtimes this engine actually implements.

The grammar names eighteen. No engine implements all of them, and the useful
thing an engine can do is be **precise about which** — so a warrant naming a
runtime this engine does not have is refused by name, listing what it does have,
rather than failing three layers down inside an artifact loader.

The refusal distinguishes two cases that need different actions: a runtime this
engine has never implemented (route the warrant elsewhere) and one it implements
but whose dependency is missing (install the package).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from core.execution.errors import WarrantError
from core.execution.runtimes.base import Invocation, Runtime
from core.log import get_logger

logger = get_logger(__name__)


class RuntimeRegistry:
    """The runtimes an engine offers, and the honest refusal for the rest."""

    def __init__(self, runtimes: Optional[List[Runtime]] = None):
        self._runtimes: Dict[str, Runtime] = {}
        for runtime in runtimes or []:
            self.add(runtime)

    def add(self, runtime: Runtime) -> None:
        self._runtimes[runtime.key] = runtime
        # A runtime may answer for more than one key where the grammar's
        # distinction is about who holds the artifact rather than about how it
        # is invoked.
        for also in getattr(runtime, "ALSO", ()):
            self._runtimes[also] = runtime

    def get(self, key: str) -> Optional[Runtime]:
        return self._runtimes.get(key)

    def keys(self) -> List[str]:
        return sorted(self._runtimes)

    def describe(self) -> List[Dict[str, Any]]:
        """What this engine can run, and why it cannot run the rest."""
        return [{"runtime": key, "usable": runtime.available() is None,
                 "unavailable_because": runtime.available()}
                for key, runtime in sorted(self._runtimes.items())]

    def invoke(self, call: Invocation) -> Any:
        key = (call.warrant.get("realisation") or {}).get("runtime")
        runtime = self._runtimes.get(key)
        if runtime is None:
            raise WarrantError(
                "no_runtime",
                f"this engine does not implement the '{key}' runtime",
                f"it implements {', '.join(self.keys())}; route this warrant to an "
                "engine that has the runtime, or register the version against one "
                "of these")
        if (why := runtime.available()) is not None:
            raise WarrantError(
                "runtime_unavailable",
                f"the '{key}' runtime is implemented but not usable here: {why}",
                "install the missing dependency, or route this warrant elsewhere")
        return runtime.invoke(call)
