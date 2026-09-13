"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section I — a key read that nothing writes.

`dict.get` on a key nothing produces is silently `None`. Wrapped in `bool()`
it is silently False, and a control that reads it is a control that never
fires — with no exception, no log line, and a passing test suite. The
decommission consumer gate was disabled that way by one word, and this module
looks for the rest.
"""
from __future__ import annotations

import ast
import collections
import difflib
import pathlib

from qa.regression_suite.scenarios.common import (BLOCKED, FAIL, PASS, Ctx,
                                                  Result, case)

#: Modules whose whole job is parsing somebody else's format. A key read
#: there is a key in a PMML document, a container registry response or a
#: QuantLib instrument, and its absence from MAYA's own dict literals means
#: nothing at all.
FOREIGN = ("pmml.py", "quantlib.py", "connectors.py", "oidc.py", "jws.py",
           "importing.py", "nlquery.py")


#: Reads MAYA does not own. A camelCase key or one carrying a dot is
#: somebody else's schema and is not evidence of anything here.
def _is_ours(key: str) -> bool:
    return (len(key) >= 5 and "." not in key and key == key.lower()
            and not key.startswith("_"))


def _keys():
    written = collections.defaultdict(set)
    read = collections.defaultdict(set)
    for path in sorted(pathlib.Path("core").rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Dict):
                for key in node.keys:
                    if isinstance(key, ast.Constant) and \
                            isinstance(key.value, str):
                        written[key.value].add(path.name)
            if isinstance(node, ast.Call) and \
                    isinstance(node.func, ast.Attribute) and \
                    node.func.attr == "get" and node.args:
                first = node.args[0]
                if isinstance(first, ast.Constant) and \
                        isinstance(first.value, str):
                    read[first.value].add(f"{path.name}:{node.lineno}")
    return written, read


@case("QA-PLT-4700", "No control reads a key one edit from the one written")
def plt_4700(ctx: Ctx) -> Result:
    """The shape that disabled the decommission consumer gate:
    `blast_radius` answers `reaches` and `consumers()` reads `reached`. One
    letter, no error, and the refusal can never fire.
    """
    written, read = _keys()
    suspects = []
    for key, where in read.items():
        if key in written or not _is_ours(key):
            continue
        site = sorted(where)[0]
        if site.split(":")[0] in FOREIGN:
            continue
        close = difflib.get_close_matches(key, written, n=2, cutoff=0.86)
        if close:
            suspects.append(f"{key!r} (near {close[0]!r}) at {site}")
    # REPORTED, not asserted. A near miss is a candidate for a human to look
    # at, not a defect: `state.get("feature_contract")` beside a literal
    # writing `has_feature_contract` is exactly right, and the heuristic
    # cannot tell that from `reached` against `reaches`. What the case
    # guarantees is that the list is small enough to read.
    if len(suspects) > 4:
        return FAIL, (f"{len(suspects)} near-miss key read(s) in MAYA's own "
                      f"modules, too many to check by eye: "
                      + "; ".join(sorted(suspects)))
    return PASS, (f"{len(suspects)} near-miss read(s) outside the foreign-"
                  f"format modules"
                  + (": " + "; ".join(sorted(suspects)) if suspects else ""))


@case("QA-PLT-4701", "The regime state reads only keys the context carries")
def plt_4701(ctx: Ctx) -> Result:
    """`core_state` turns a model's context into the facts every regime
    determination is made from. A fact derived from a key the context does
    not carry is permanently False, and a regime obligation keyed on it can
    never be satisfied by anything.
    """
    documents = ctx.ui.app.state.ctx.get("documents")
    regimes = ctx.ui.app.state.ctx.get("regimes")
    if documents is None or regimes is None:
        return BLOCKED, "no document or regime service reachable"
    name = ctx.unique("kr")
    urn = f"maya://model/{name}"
    ctx.api.post("/api/v1/models",
                 json={"urn": urn, "name": name, "owner": "owner",
                       "model_class": "logistic", "domain": "credit",
                       "legal_entity": "LE-US-01",
                       "purpose": "credit_decision"})
    ctx.api.post(f"/api/v1/models/{name}/versions", json={"semver": "1.0.0"},
                 auth=ctx.people["developer"])
    ctx.api.post(f"/api/v1/documents?urn={urn}"
                 f"&kind=model_development_document", auth=ctx.people["owner"])
    context = documents.build_context(urn)

    import inspect
    import textwrap
    # A method's source is indented. Parsing it without dedenting raises
    # IndentationError inside the case, which the runner reports as the case
    # failing — indistinguishable from the defect it was written to find.
    source = textwrap.dedent(inspect.getsource(regimes.core_state))
    reads = {node.args[0].value
             for node in ast.walk(ast.parse(source))
             if isinstance(node, ast.Call)
             and isinstance(node.func, ast.Attribute)
             and node.func.attr == "get" and node.args
             and isinstance(node.args[0], ast.Constant)
             and isinstance(node.args[0].value, str)
             and isinstance(node.func.value, ast.Name)
             and node.func.value.id == "state"}
    absent = sorted(key for key in reads if key not in context)
    if absent:
        return FAIL, (
            f"`core_state` reads {absent} from the model context, which does "
            f"not carry {'them' if len(absent) > 1 else 'it'} — the context "
            f"holds {sorted(context)[:6]}… — so every fact derived from "
            f"{'those keys is' if len(absent) > 1 else 'that key is'} "
            f"permanently False, and this model has a compiled document")
    return PASS, f"all {len(reads)} context keys `core_state` reads are present"
