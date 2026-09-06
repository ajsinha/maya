"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The MAYA deck: philosophy, foundations, concepts, system design and
worked examples — twenty-five chapters in five parts.

**Why this is a driver over a directory rather than one file.** The deck grew past a hundred and fifty slides when the practitioner material was merged in, and the
generator with it — past the fifteen-hundred-line limit this repository holds
every source file to. Splitting by chapter is the same answer the API test suite
got: cut by subject, because a file cut at the fifteen-hundredth line is two
files nobody can name.

Each chapter is executed into ONE namespace, in order, sharing the helpers and
the running slide counter. That is the same `exec` idiom `theme.py` already uses,
and it is deliberate: a chapter is a script that draws slides, not a module with
an interface, and giving it one would be inventing a contract to satisfy an
import system rather than a reader.
"""
# -*- coding: utf-8 -*-
import os
import pathlib
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CHAPTERS = os.path.join(HERE, "design")


def _run(path, namespace):
    with open(path, encoding="utf-8") as handle:
        exec(compile(handle.read(), path, "exec"), namespace)


def build(out_path):
    # `os` and `__file__` are seeded because theme.py resolves the logo path
    # relative to itself, and an exec'd file gets neither for free.
    namespace = {"__name__": "__deck__", "os": os,
                 "__file__": os.path.join(HERE, "theme.py")}
    _run(os.path.join(HERE, "theme.py"), namespace)
    _run(os.path.join(CHAPTERS, "__preamble__.py"), namespace)
    # Numeric order IS the chapter order, so the file names carry the sequence
    # rather than a list here that can disagree with what is on disk.
    for name in sorted(os.listdir(CHAPTERS)):
        if name.endswith(".py") and not name.startswith("__"):
            _run(os.path.join(CHAPTERS, name), namespace)
    namespace["prs"].save(out_path)
    return len(namespace["prs"].slides._sldIdLst)


# The deck is a document, so it belongs beside the documents. Defaulting to the
# working directory put a second copy in the project root every time anybody
# built it from there, and two copies of a 155-slide deck differ the moment one
# of them is rebuilt — with nothing to say which is current.
DEFAULT_OUT = (pathlib.Path(__file__).resolve().parents[2]
               / "docs" / "MAYA-Model-and-Feature-Management.pptx")

if __name__ == "__main__":
    target = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUT
    target.parent.mkdir(parents=True, exist_ok=True)
    print("slides:", build(str(target)), "->", target)
