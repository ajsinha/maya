"""
Drafting, the two places §29.8 asks for it: a feature definition from a description and a
sample file, and the specification sections an author has not written.

A draft is a **proposal**. Nothing here writes to MAYA, nothing here approves anything, and
everything it produces goes through the same validation as a hand-written definition — so
the worst an assistant can do is waste a minute of somebody's time. Each field says where
it came from (`from`), so a reviewer can see what was inferred from data and what was
guessed from a sentence.

The deterministic drafter is the floor and needs no provider: column names and dtypes carry
most of a definition, and the specification's own required sections carry the skeleton of a
document. With `assistant.provider: claude` the same structures are offered to the model for
improvement, and its version is recorded — but a draft is never accepted on its word.

Copyright (c) 2026 Ashutosh Sinha.  All rights reserved.
"""

from __future__ import annotations

import re
from typing import Any

# column names that are an index rather than a measurement, in the order they usually nest
INDEX_HINTS = (
    ("date", ("date", "asof", "as_of", "dt", "day", "timestamp", "time")),
    ("entity", ("symbol", "ticker", "instrument", "isin", "cusip", "id", "entity", "account")),
)
KNOWLEDGE_HINTS = ("knowledge_time", "published_at", "published", "arrival", "received_at", "kt")


def feature_definition(
    description: str, columns: list[dict[str, Any]], *, name: str = "", fmt: str = "csv"
) -> dict[str, Any]:
    """A proposed feature definition from a sample's columns and a sentence about it.

    ``columns`` is ``[{"name", "type", "nulls", "distinct", "sample"}]`` — whatever the
    caller could read cheaply from the file. Nothing about the *rows* is kept: a draft
    carries structure, never data.
    """
    index, index_types = _index(columns)
    knowledge = next((c["name"] for c in columns if c["name"].lower() in KNOWLEDGE_HINTS), None)
    attributes = [
        c
        for c in columns
        if c["name"] not in index and c["name"] != knowledge and not _is_noise(c["name"])
    ]
    notes: list[str] = []
    if not index:
        notes.append(
            "no column looked like an event date, so the index is a guess: a feature's index "
            "is what its rows are *about*, and getting it wrong is expensive later"
        )
    if knowledge:
        notes.append(f"'{knowledge}' reads as a knowledge time, and is declared as the source's")
    definition = {
        "index": index or [columns[0]["name"]] if columns else [],
        "index_types": index_types,
        "schema": [{"name": c["name"], "type": c["type"]} for c in attributes],
        "source": {"type": fmt, **({"knowledge_time_column": knowledge} if knowledge else {})},
        "resolution": {"grid": "as_is", "rules": _rules(attributes, description)},
        "transform": [],
        "quality": _quality(attributes, index),
    }
    return {
        "name": name or _slug(description),
        "description": description.strip(),
        "definition": definition,
        "from": {
            "index": "column names and types in the sample",
            "schema": "the sample's remaining columns",
            "resolution": "the description, where it says how gaps behave",
            "quality": "nulls and ranges in the sample",
        },
        "notes": notes,
        "review": "This is a draft. Read every rule before you submit it; nothing here has "
        "been validated against how the data actually behaves.",
    }


def _index(columns: list[dict[str, Any]]) -> tuple[list[str], dict[str, str]]:
    index, types = [], {}
    for role, hints in INDEX_HINTS:
        for column in columns:
            lowered = column["name"].lower()
            if any(h == lowered or lowered.startswith(h) or lowered.endswith(h) for h in hints):
                index.append(column["name"])
                types[column["name"]] = "date" if role == "date" else "string"
                break
    return index, types


def _is_noise(name: str) -> bool:
    return name.lower() in ("unnamed: 0", "index", "row", "#")


def _rules(attributes: list[dict[str, Any]], description: str) -> dict[str, str]:
    """A resolution rule per attribute, from what the description says about gaps."""
    text = description.lower()
    if "step" in text or "carry forward" in text or "last known" in text:
        rule = "forward_fill(limit=3)"
    elif "interpolat" in text:
        rule = "linear_interpolate(limit=2)"
    else:
        return {}
    return {c["name"]: rule for c in attributes if c["type"].startswith("float")}


def _quality(attributes: list[dict[str, Any]], index: list[str]) -> list[dict[str, Any]]:
    """Checks the sample supports: nothing speculative, and never a range from one file."""
    checks: list[dict[str, Any]] = []
    if index:
        checks.append({"check": "unique_on_index"})
    for column in attributes:
        if column.get("nulls") == 0:
            checks.append({"check": "not_null", "attr": column["name"]})
    return checks


def _slug(description: str) -> str:
    words = re.findall(r"[a-z0-9]+", description.lower())[:4]
    return "_".join(words) or "new_feature"


def spec_sections(
    latex: str, ir: dict[str, Any], completeness: list[dict[str, Any]]
) -> dict[str, Any]:
    """Drafts for the required sections an author has left empty (§29.8).

    What is drafted is what MAYA can already see: the formula's own inputs, outputs and
    parameters, its bounds, and what the platform knows about calibration and validation.
    Every draft is a **starting point with the gaps named** — a section that says "state the
    limitations" is more use than a paragraph of plausible prose that nobody wrote.
    """
    inputs = [i for i in ir.get("inputs", []) if i.get("role", "feature") == "feature"]
    params = [i for i in ir.get("inputs", []) if i.get("role") == "parameter"]
    outputs = ir.get("outputs", [])
    drafts: dict[str, str] = {}
    missing = [s["section"] for s in completeness if not s["present"] or s["empty"]]
    for section in missing:
        drafts[section] = _section_draft(section, inputs, params, outputs, ir)
    return {
        "missing": missing,
        "drafts": drafts,
        "kept": [s["section"] for s in completeness if s["present"] and not s["empty"]],
        "review": "Drafts for the sections nobody has written yet, from what MAYA can see of "
        "the model. Each names what it cannot know; a reviewer is entitled to refuse a "
        "section that only restates the formula.",
        "latex_hint": "Paste a section under its own \\section{...} heading; the completeness "
        "check reads headings, not order.",
    }


def _section_draft(
    section: str,
    inputs: list[dict[str, Any]],
    params: list[dict[str, Any]],
    outputs: list[dict[str, Any]],
    ir: dict[str, Any],
) -> str:
    names = ", ".join(i["name"] for i in inputs) or "(none declared)"
    out_names = ", ".join(o["name"] for o in outputs) or "(none declared)"
    param_names = ", ".join(p["name"] for p in params) or "(none: this model is not fitted)"
    body = ir.get("body") or ""
    if section == "Purpose":
        return (
            f"This model computes {out_names} from {names}. "
            "STATE: who uses the output, for what decision, and what would be done "
            "differently if it were unavailable."
        )
    if section == "Scope and Limitations":
        return (
            f"In scope: inputs {names} on the grid the feature set declares. "
            "STATE: the population and period the model is fitted for, the conditions under "
            "which it should not be used, and the behaviour at the edges of its input range."
        )
    if section == "Mathematical Formulation":
        return (
            ("The model is \\(" + body + "\\).\n\n") if body else ""
        ) + "STATE: the derivation or the reference, and why this functional form."
    if section == "Assumptions":
        return (
            "STATE each assumption and how it was checked. The formula itself assumes the "
            f"inputs {names} are on a common index and carry no look-ahead; MAYA's leakage "
            "certificate checks the second, not the first."
        )
    if section == "Data and Features Used":
        return (
            f"Inputs: {names}. Outputs: {out_names}.\n\n"
            "STATE: the feature versions or pins this model is fitted on, and any filtering "
            "applied before the fit."
        )
    if section == "Calibration Methodology":
        return (
            f"Parameters: {param_names}.\n\n"
            "STATE: the objective, the optimiser, the split and seed (MAYA records the "
            "warrant's split and seed; quote them here), and how the fit was judged."
        )
    if section == "Validation Evidence":
        return (
            "STATE: in-sample and out-of-sample performance, the metrics and their values, "
            "the benchmark compared against, and the holdout score MAYA issued (a blind "
            "score against the escrowed partition is recorded on the warrant)."
        )
    if section == "Known Weaknesses":
        return (
            "STATE: where the model is known to be wrong, what has been observed rather "
            "than feared, and what monitoring would catch it. Covenants on the execution "
            "warrant are how a breach withdraws the permission automatically."
        )
    if section == "Change Log":
        return "STATE: what changed in this version, why, and who asked for it."
    return f"STATE: {section}."


__all__ = ["INDEX_HINTS", "KNOWLEDGE_HINTS", "feature_definition", "spec_sections"]
