"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

THE CONCEPTS DECK — twenty slides on the ideas, the formalism and the shapes.

**The audience.** Somebody who wants to know whether the ideas are sound before
caring whether the software is good: an architect, a quantitatively-minded head
of model risk, an academic reader. So there is no roadmap here, no business
case, no build status and no screenshots — the design deck carries all of those
across 123 slides, and the executive briefing carries the money.

**The claim these slides have to earn.** That the governance controls are
consequences of a definition rather than a list of practices: say precisely what
a model IS, and most of the platform follows.
"""
# -*- coding: utf-8 -*-
import os
import pathlib
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def build(out_path):
    namespace = {"__name__": "__deck__", "os": os,
                 "__file__": os.path.join(HERE, "theme.py")}
    for name in ("theme.py", os.path.join("design", "__preamble__.py")):
        with open(os.path.join(HERE, name), encoding="utf-8") as handle:
            exec(compile(handle.read(), name, "exec"), namespace)
    with open(os.path.join(HERE, "concepts_body.py"), encoding="utf-8") as handle:
        exec(compile(handle.read(), "concepts_body.py", "exec"), namespace)
    namespace["prs"].save(out_path)
    return len(namespace["prs"].slides._sldIdLst)


DEFAULT_OUT = (pathlib.Path(__file__).resolve().parents[2]
               / "docs" / "MAYA-Concepts-and-Formalism.pptx")

if __name__ == "__main__":
    target = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUT
    target.parent.mkdir(parents=True, exist_ok=True)
    print("slides:", build(str(target)), "->", target)
