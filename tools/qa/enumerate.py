#!/usr/bin/env python3
"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Enumerate the QA case list from the source, so coverage is provable.

A hand-written test plan is a plan somebody's memory produced, and what it
misses is invisible — there is no way to look at it and see the route nobody
thought of. This derives the backbone mechanically from the artefacts that
already describe the system:

| Source | What it yields |
|---|---|
| `openapi.lock.json` | one primary case per **operation**, and a refusal case per operation carrying required fields or a path parameter |
| `routes/base.py` | one case per **mapped refusal code** — the codes are the platform's argument, so each has to be provoked at least once |
| `web/templates/base.html` | one authorised and one refused case per **navbar screen** |
| `core/authz/roles.py` | the role matrix the screen cases draw from |

What it deliberately does **not** produce is the judgement: sequences, boundary
values, races, and the cases that only make sense to somebody who understands
the domain. Those are written by hand into the same file, in the sections this
generator leaves alone. The generator's job is that **nothing is missing**; a
person's job is that what is there is worth running.

    python -m tools.qa.enumerate --out docs/QA/QA-CASES.md
"""
from __future__ import annotations

import argparse
import collections
import json
import pathlib
import re
import sys
from typing import Any, Dict, List, Tuple

ROOT = pathlib.Path(__file__).resolve().parents[2]

#: An operation whose path carries one of these is read-only and cheap; its
#: primary case is a smoke read rather than a state change.
READS = ("GET",)


def operations() -> List[Tuple[str, str, Dict[str, Any]]]:
    lock = json.loads((ROOT / "openapi.lock.json").read_text(encoding="utf-8"))
    out = []
    for path, item in sorted(lock["paths"].items()):
        for method, spec in sorted(item.items()):
            if method.lower() in ("get", "post", "put", "patch", "delete"):
                out.append((method.upper(), path, spec or {}))
    return out


def refusal_codes() -> Dict[str, int]:
    """Every code mapped to a status. These are the platform's argument."""
    text = (ROOT / "routes" / "base.py").read_text(encoding="utf-8")
    return {code: int(status) for code, status in
            re.findall(r'"([a-z][a-z0-9_]+)"\s*:\s*(\d{3})', text)}


def screens() -> List[Tuple[str, str, str]]:
    """`(path, title, permission)` for every navbar entry."""
    text = (ROOT / "web" / "templates" / "base.html").read_text(encoding="utf-8")
    # Four fields, not three: path, title, a one-line description, and the
    # permission. Matching three silently returned nothing and the whole
    # screens section generated zero cases — a generator that finds nothing
    # looks exactly like a system with nothing in it.
    return [(path, title, permission) for path, title, _why, permission in
            re.findall(r'\("(/[a-z0-9/_-]+)",\s*"([^"]+)",\s*"([^"]*)",\s*'
                       r'"([a-z:*]+)"\)', text)]


def _slug(area: str) -> str:
    """An area name as an ID fragment: letters and digits, and never truncated.

    Two bugs lived in one line here. Truncating to twelve characters collided
    `classification` with `classifications`, and `version-approvals` with
    `version-approval-quorum` — three ids that meant two cases each, which is
    an id nobody can report a result against. And a UI area is `ui:dashboard`,
    so the colon went into the id and made it unmatchable by the very regex
    that counts these, which is how a count came out 109 short and looked like
    missing cases rather than malformed ones.
    """
    return re.sub(r"[^A-Z0-9]", "", area.upper()) or "ROOT"


def domain_of(path: str) -> str:
    parts = [p for p in path.split("/") if p]
    if parts[:2] == ["api", "v1"]:
        return parts[2] if len(parts) > 2 else "root"
    return "ui:" + (parts[0] if parts else "root")


def _required(spec: Dict[str, Any]) -> List[str]:
    return [f.rstrip("!") for f in (spec.get("body") or []) if f.endswith("!")]


def _path_params(path: str) -> List[str]:
    return re.findall(r"\{([a-z_]+)[:}]", path)


def build() -> Dict[str, List[Dict[str, str]]]:
    """Every generated case, grouped by section."""
    sections: Dict[str, List[Dict[str, str]]] = collections.OrderedDict()
    counter = collections.Counter()

    def add(section: str, area: str, title: str, expect: str, why: str,
            steps: str) -> None:
        counter[area] += 1
        sections.setdefault(section, []).append({
            "id": f"QA-{_slug(area)}-{counter[area]:03d}",
            "area": area, "title": title, "expect": expect, "why": why,
            "steps": steps})

    # -- A. one primary case per operation ---------------------------------
    for method, path, spec in operations():
        area = domain_of(path)
        params = ", ".join(spec.get("parameters") or []) or "none"
        body = ", ".join(spec.get("body") or []) or "none"
        codes = "/".join(spec.get("responses") or []) or "?"
        add("A. Every operation, once", area,
            f"`{method} {path}` answers on the happy path",
            f"accepted ({codes.split('/')[0]})",
            "an operation nobody has called once is an operation nobody knows "
            "the shape of",
            f"{method} {path} — query: {params}; body: {body}")

    # -- B. a refusal per operation that can be malformed ------------------
    for method, path, spec in operations():
        required = _required(spec)
        if not required:
            continue
        add("B. Required fields", domain_of(path),
            f"`{method} {path}` without {', '.join(required)}",
            "refused (422)",
            "a required field the platform accepts as absent is a column that "
            "fills with nothing and is read as a fact",
            f"{method} {path} omitting: {', '.join(required)}")

    # -- C. an unknown identifier per parameterised operation --------------
    for method, path, _spec in operations():
        names = _path_params(path)
        if not names:
            continue
        add("C. Unknown identifiers", domain_of(path),
            f"`{method} {path}` with a {names[0]} that does not exist",
            "refused (404)",
            "a 500 on an unknown id is the commonest defect in a register, and "
            "it leaks whether the id exists",
            f"{method} {path} with {names[0]}=does-not-exist")

    # -- D. every mapped refusal, provoked ---------------------------------
    for code, status in sorted(refusal_codes().items()):
        add("D. Every refusal code", "refusal",
            f"`{code}` can actually be provoked",
            f"refused ({status})",
            "a refusal the platform maps and cannot emit is a control that "
            "exists in a status table and nowhere else",
            f"construct the state that raises `{code}`; assert the status is "
            f"{status} and that detail and remediation are both present")

    # -- E. every screen, twice --------------------------------------------
    for path, title, permission in screens():
        add("E. Screens", "screen",
            f"{title} ({path}) renders for a principal holding {permission}",
            "accepted (200)",
            "a screen in the bar that answers 403 teaches people that refusals "
            "are noise",
            f"sign in as a role holding {permission}; GET {path}")
        add("E. Screens", "screen",
            f"{title} ({path}) is refused for a principal without {permission}",
            "refused (403)",
            "the navbar is permission-driven; a screen reachable without its "
            "permission is a hole",
            f"sign in as a role without {permission}; GET {path}")
    return sections


def render(sections: Dict[str, List[Dict[str, str]]]) -> str:
    total = sum(len(v) for v in sections.values())
    out = [HEADER.format(total=total, sections=len(sections))]
    out.append("| Section | Cases |\n|---|---|")
    for name, cases in sections.items():
        out.append(f"| {name} | {len(cases)} |")
    out.append(f"| **Generated total** | **{total}** |\n")
    for name, cases in sections.items():
        out.append(f"\n## {name}\n")
        out.append("| ID | Area | Case | Expectation | Steps | Why it matters |")
        out.append("|---|---|---|---|---|---|")
        for c in cases:
            out.append(f"| {c['id']} | `{c['area']}` | {c['title']} | "
                       f"**{c['expect']}** | {c['steps']} | {c['why']} |")
    return "\n".join(out) + "\n"


HEADER = """\
# MAYA — QA case list

**{total} generated cases across {sections} sections**, derived from the source
by `tools/qa/enumerate.py` rather than written from memory. Re-run it after any
wave that adds a route or a refusal; a case list that does not move when the
system does is a case list nobody should trust.

Each case states its **expectation before it runs** — `accepted`, `refused`
with a code, or `reported` — because this platform refuses a great deal on
purpose and a test treating a 409 as a failure has misunderstood the product.

The generator guarantees that **nothing is missing**. It cannot judge whether
what is here is worth running, and it does not produce sequences, boundary
values or races — those are written by hand in the sections after the generated
ones.

"""


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="tools.qa.enumerate")
    parser.add_argument("--out", default="docs/QA/QA-CASES.md")
    parser.add_argument("--count", action="store_true",
                        help="print the counts and write nothing")
    args = parser.parse_args(argv)
    sections = build()
    if args.count:
        for name, cases in sections.items():
            print(f"{len(cases):5}  {name}")
        print(f"{sum(len(v) for v in sections.values()):5}  TOTAL")
        return 0
    path = ROOT / args.out
    path.write_text(render(sections), encoding="utf-8")
    print(f"wrote {args.out}: {sum(len(v) for v in sections.values())} cases")
    return 0


if __name__ == "__main__":                       # pragma: no cover
    sys.exit(main())
