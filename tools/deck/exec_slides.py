"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

THE EXECUTIVE BRIEFING — twenty slides for a CIO and business heads.

**What this deck is not.** It is not the 123-slide design deck with the
engineering removed. An executive audience is not a technical audience reading
more slowly; they are answering different questions — what is the exposure, what
does it cost, what changes on Monday, and what happens if we do nothing — and a
deck that answers those in an appendix has not answered them.

So the shape is: the problem in the language of loss, the four failures that
cause it, what MAYA is in one sentence, the six things it does that nothing
else does, the evidence it is real, the cost, and the decision being asked for.

**No number here is aspirational.** Every figure on these slides is either
measured (test counts, soak results, case-study output) or is explicitly marked
as an estimate. A deck that mixes the two teaches an executive to discount all
of it.
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
    with open(os.path.join(HERE, "exec_body.py"), encoding="utf-8") as handle:
        exec(compile(handle.read(), "exec_body.py", "exec"), namespace)
    namespace["prs"].save(out_path)
    return len(namespace["prs"].slides._sldIdLst)


DEFAULT_OUT = (pathlib.Path(__file__).resolve().parents[2]
               / "docs" / "MAYA-Executive-Briefing.pptx")

if __name__ == "__main__":
    target = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUT
    target.parent.mkdir(parents=True, exist_ok=True)
    print("slides:", build(str(target)), "->", target)
