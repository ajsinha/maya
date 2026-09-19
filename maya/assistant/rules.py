"""
The deterministic challenger: what can be found without judgement.

Each check reads the dossier and returns findings; none needs a network, none
is a guess. The Claude provider starts from these and adds what reading the
document and the definition as a whole can find.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import re
from typing import Any

from maya.formula.specdoc import section_completeness
from maya.resolution.rules import parse_rule

PLACEHOLDER = re.compile(r"\b(TODO|TBD|FIXME|to be (written|completed|confirmed)|lorem ipsum)\b",
                         re.I)
THIN_WORDS = 25


def finding(severity: str, category: str, title: str, detail: str,
            evidence: Any = None) -> dict[str, Any]:
    return {"severity": severity, "category": category, "title": title, "detail": detail,
            "evidence": evidence, "source": "rules"}


def _rules_of(definition: dict[str, Any]) -> dict[str, Any]:
    res = definition.get("resolution") or {}
    rules = dict(res.get("rules") or {})
    if res.get("default"):
        rules["*default*"] = res["default"]
    return rules


def resolution_findings(definition: dict[str, Any], where: str) -> list[dict[str, Any]]:
    out = []
    for attr, spec in _rules_of(definition).items():
        try:
            rule = parse_rule(spec)
        except Exception:  # noqa: BLE001 - an unparseable rule is the validator's to refuse
            continue
        if rule.non_causal:
            out.append(finding(
                "high", "look_ahead", f"Non-causal fill on {where}.{attr}",
                f"'{rule.canonical()}' fills a gap with a value observed later. A backtest or "
                "a training set built on it can see the future unless the warrant certifies "
                "otherwise.", {"attribute": attr, "rule": rule.canonical()}))
        if rule.name in ("forward_fill", "backward_fill", "linear_interp") and \
                rule.params.get("limit") is None and rule.params.get("max_age") is None:
            out.append(finding(
                "medium", "unbounded_fill", f"Unbounded fill on {where}.{attr}",
                f"'{rule.canonical()}' has no limit or max_age: a feed that stops will be "
                "carried forward indefinitely and look healthy.",
                {"attribute": attr, "rule": rule.canonical()}))
    return out


def schema_findings(definition: dict[str, Any], previous: dict[str, Any] | None,
                    where: str) -> list[dict[str, Any]]:
    if not previous:
        return []
    now = {a["name"]: a for a in definition.get("schema") or []}
    before = {a["name"]: a for a in previous.get("schema") or []}
    out = []
    for name in sorted(set(before) - set(now)):
        out.append(finding("high", "schema_drift", f"{where}: attribute '{name}' removed",
                           "Consumers of the previous version that read it will break or "
                           "silently lose it.", {"attribute": name}))
    for name in sorted(set(now) & set(before)):
        a, b = before[name], now[name]
        for key in ("type", "unit"):
            if a.get(key) != b.get(key):
                out.append(finding("medium", "schema_drift",
                                   f"{where}: '{name}' {key} changed",
                                   f"{key} was {a.get(key)!r}, is now {b.get(key)!r}.",
                                   {"attribute": name, key: [a.get(key), b.get(key)]}))
    for name in sorted(set(now) - set(before)):
        out.append(finding("info", "schema_drift", f"{where}: attribute '{name}' added",
                           "New attributes are safe for existing consumers.", {"attribute": name}))
    if previous.get("index") != definition.get("index"):
        out.append(finding("high", "schema_drift", f"{where}: index changed",
                           "Every join and pin keyed on the old index changes meaning.",
                           {"before": previous.get("index"), "after": definition.get("index")}))
    return out


def feature_findings(dossier: dict[str, Any]) -> list[dict[str, Any]]:
    d, name = dossier["definition"], dossier["ref"]
    out = resolution_findings(d, name) + schema_findings(d, dossier.get("previous"), name)
    if not d.get("quality") and (d.get("source") or {}).get("type") != "derived":
        out.append(finding("low", "data_quality", "No quality contract",
                           "Nothing checks this feature's data before a pin is sealed; a null "
                           "or out-of-range feed would be pinned as it is.", None))
    lic = d.get("licence") or {}
    if lic.get("redistribution") in ("none", "internal"):
        out.append(finding("info", "licence", f"Licensed: redistribution {lic['redistribution']}",
                           "Downloads and exports of this data, and of anything derived from "
                           "it, are restricted by the vendor's terms.", lic))
    return out


def featureset_findings(dossier: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for m in dossier.get("members", []):
        out += resolution_findings(m.get("definition") or {}, f"{dossier['ref']}.{m['attr']}")
    if (dossier["definition"].get("alignment") or {}).get("mode") == "outer":
        out.append(finding("low", "data_quality", "Outer alignment",
                           "Rows missing from any member are kept with nulls; check that the "
                           "model tolerates them.", None))
    return out


def _thin(body: str) -> bool:
    words = re.sub(r"\\[a-zA-Z]+\*?|[{}$\\]", " ", body).split()
    return len(words) < THIN_WORDS or bool(PLACEHOLDER.search(body))


def model_findings(dossier: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    spec = dossier.get("spec_latex") or ""
    sections = {s["section"]: s for s in section_completeness(spec)}
    from maya.formula.specdoc import _sections
    bodies = dict(_sections(spec))
    for name in ("Scope and Limitations", "Known Weaknesses", "Assumptions"):
        s = sections.get(name) or {}
        if not s.get("present") or s.get("empty"):
            out.append(finding("high", "missing_limitations", f"'{name}' is missing",
                               "A reviewer cannot judge fitness for use without it.", None))
        elif _thin(bodies.get(name, "")):
            out.append(finding("medium", "missing_limitations", f"'{name}' is thin",
                               f"Under {THIN_WORDS} words, or placeholder text: it states too "
                               "little to challenge.", {"section": name}))
    state = dossier.get("spec_state") or {}
    if state.get("needs_review") or (state.get("bound_ir_hash") and
                                     state["bound_ir_hash"] != dossier.get("ir_hash")):
        out.append(finding("high", "doc_ir_inconsistency",
                           "The document describes a different formula",
                           "The formula IR changed after the specification was last bound to "
                           "it; the document may describe mathematics the model no longer "
                           "computes.", {"bound": state.get("bound_ir_hash"),
                                         "current": dossier.get("ir_hash")}))
    ir = dossier.get("formula_ir") or {}
    if "black_box" in ir:
        out.append(finding("info", "other", "Declared black box",
                           "No closed form: conformance testing and bundle re-execution are "
                           "unavailable, so covenants are the main control.", None))
    for inp in ir.get("inputs", []):
        if inp.get("role") == "parameter" and not inp.get("bounds"):
            out.append(finding("low", "other", f"Parameter '{inp['name']}' has no bounds",
                               "An uploaded parameter set cannot be checked against a "
                               "plausible range.", {"parameter": inp["name"]}))
    if dossier.get("diff"):
        out.append(finding("info", "other", "Mathematical change from the previous version",
                           "; ".join(dossier["diff"])[:600], dossier["diff"]))
    return out


def challenge(dossier: dict[str, Any]) -> dict[str, Any]:
    fn = {"feature_version": feature_findings, "featureset_version": featureset_findings,
          "model_version": model_findings}[dossier["object_type"]]
    findings = fn(dossier)
    order = {s: i for i, s in enumerate(("high", "medium", "low", "info"))}
    findings.sort(key=lambda f: order[f["severity"]])
    counts = {s: sum(f["severity"] == s for f in findings) for s in order}
    summary = ("No findings." if not findings else
               ", ".join(f"{n} {s}" for s, n in counts.items() if n) + " finding(s).")
    return {"summary": summary, "findings": findings}
