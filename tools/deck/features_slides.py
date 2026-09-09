"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

THE FEATURE PLATFORM DECK — twenty slides on features and featuresets.

**The audience.** A data or feature-platform engineer, and the model-risk person
who signs off on what a model was fitted on. Somebody who has probably already
built or bought a feature store.

**The thread.** A feature store answers *what is the value*; a register has to
answer *what was knowable, when* — and prove the answer is the same one it gave
last year. Two clocks, version pins, composition that type-checks and a
retrieval API that pins rather than reads the head all fall out of that one
difference.
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
    with open(os.path.join(HERE, "features_body.py"), encoding="utf-8") as handle:
        exec(compile(handle.read(), "features_body.py", "exec"), namespace)
    namespace["prs"].save(out_path)
    return len(namespace["prs"].slides._sldIdLst)


DEFAULT_OUT = (pathlib.Path(__file__).resolve().parents[2]
               / "docs" / "MAYA-Feature-Platform.pptx")

if __name__ == "__main__":
    target = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUT
    target.parent.mkdir(parents=True, exist_ok=True)
    print("slides:", build(str(target)), "->", target)
