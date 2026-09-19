"""Gate 15b — UI ↔ SDK parity, the UI side of SC-13.

The web tier is an SDK client (gate 5 keeps it from anything deeper), so UI → SDK
holds by construction. This gate proves SDK → UI: every SDK endpoint is reached by
some web page or action. A paged variant (``page``, ``x_page``) reaches the endpoint
of the list it pages. The few endpoints that are not UI actions by nature are named
below, each with the reason; anything else unreached fails the gate.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import re
import sys

from _common import ROOT, report

NOT_UI = {
    "auth.oidc_backchannel_logout": "server to server: the IdP calls it, never a browser",
    "events.stream": "a server-sent event stream for integrations; the UI pages events",
    "jobs.events": "a server-sent progress stream for SDK and CLI; the UI polls the job",
    "workflow.population": "the policy page shows the population from the policy itself",
}


def sdk_methods() -> list[tuple[str, str]]:
    """(namespace, method) for every SDK method bound to an API endpoint."""
    from maya.sdk.client import Client
    from maya.sdk.resources import ENDPOINTS
    probe = Client.__new__(Client)
    probe._bind(object())
    ns_of = {type(v).__name__: k for k, v in vars(probe).items()
             if not k.startswith("_") and type(v).__module__.startswith("maya.sdk")}
    return sorted((ns_of[c], m) for c, m in (name.split(".") for name in set(ENDPOINTS.values())))


def web_calls() -> set[tuple[str, str]]:
    text = "".join(p.read_text(encoding="utf-8")
                   for p in sorted((ROOT / "maya" / "web").rglob("*.py")))
    calls = set(re.findall(r"\.(\w+)\.(\w+)\(", text))
    # "page" pages "list"; "x_page" pages "x"
    calls |= {(ns, "list") for ns, m in calls if m == "page"}
    calls |= {(ns, m[:-5]) for ns, m in calls if m.endswith("_page")}
    return calls


def main() -> int:
    reached = web_calls()
    missing = [f"{ns}.{m}: no web page or action reaches it"
               for ns, m in sdk_methods()
               if (ns, m) not in reached and f"{ns}.{m}" not in NOT_UI]
    stale = [f"{k}: listed as not a UI action, but the web tier now reaches it"
             for k in NOT_UI if tuple(k.split(".")) in reached]
    return report("UI ↔ SDK parity (every SDK endpoint reachable from the UI)",
                  missing + stale)


if __name__ == "__main__":
    sys.exit(main())
