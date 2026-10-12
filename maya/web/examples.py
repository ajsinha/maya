"""
The examples gallery: definitions somebody can read, copy, or open as a draft.

Each example is a complete, valid object of its kind -- a feature definition, a feature-set
mapping, warrant terms, covenants, a workflow policy fragment -- written the way a careful
practitioner would write it, with a note saying what it shows and why each choice is made.
Feature definitions open in the feature designer already filled in (``?example=<slug>``);
formula templates, which live in ``kernel_templates``, open in the kernel designer.

``tests/test_examples.py`` holds every feature definition to MAYA's own validator, so an
example cannot rot into one the designer would refuse.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

from typing import Any

FEATURES: list[dict[str, Any]] = [
    {
        "slug": "daily-closes",
        "title": "Daily closing prices on a business calendar",
        "summary": "A CSV of closes, filled forward across short gaps but never from a stale "
        "price, and refused if a close is missing or negative.",
        "note": "The calendar creates the business days the vendor skipped; forward_fill may "
        "fill at most three in a row and never from a price more than five days old, so a "
        "long outage shows as nulls the quality contract then refuses to pin.",
        "definition": {
            "index": ["date", "symbol"],
            "index_types": {"date": "date", "symbol": "string"},
            "schema": [{"name": "close", "type": "float64", "unit": "USD"}],
            "source": {"type": "csv"},
            "resolution": {
                "grid": {"calendar": "ISO_business_days"},
                "rules": {"close": "forward_fill(limit=3, max_age=5)"},
            },
            "transform": [],
            "quality": [
                {"check": "not_null", "attr": "close"},
                {"check": "range", "attr": "close", "min": 0, "max": 100000},
            ],
        },
    },
    {
        "slug": "monthly-macro",
        "title": "A monthly macro series, read as it was known",
        "summary": "Regional unemployment published a month after the month it describes, "
        "carried to each date only once it had been published.",
        "note": "last_known_as_of(lag=30) gives each date the latest value that had been "
        "published thirty days earlier, so a backtest never reads a figure before its "
        "release. Revisions arrive as restatements with their own knowledge time.",
        "definition": {
            "index": ["date", "region"],
            "index_types": {"date": "date", "region": "string"},
            "schema": [
                {"name": "unemployment_rate", "type": "float64", "unit": "percent"},
            ],
            "source": {"type": "csv"},
            "resolution": {
                "grid": "as_is",
                "rules": {"unemployment_rate": "last_known_as_of(lag=30)"},
            },
            "transform": [],
            "quality": [
                {"check": "range", "attr": "unemployment_rate", "min": 0, "max": 100},
                {"check": "unique_on_index"},
            ],
        },
    },
    {
        "slug": "loan-balances-sql",
        "title": "Loan balances from a warehouse, read-only",
        "summary": "Month-end balances pulled by a SELECT on a named connection, with every "
        "loan required to appear once per month.",
        "note": "A sql source names a connection an administrator defined under Admin → "
        "Sources; the password lives in an environment variable, never here. MAYA runs "
        "SELECT only, and records the rows it read as an ingest with its knowledge time.",
        "definition": {
            "index": ["month_end", "loan_id"],
            "index_types": {"month_end": "date", "loan_id": "string"},
            "schema": [
                {"name": "balance", "type": "float64", "unit": "GBP"},
                {"name": "days_past_due", "type": "int64"},
            ],
            "source": {
                "type": "sql",
                "connection": "warehouse",
                "query": "SELECT month_end, loan_id, balance, days_past_due FROM loan_month_end",
            },
            "resolution": {"grid": "as_is", "rules": {}},
            "transform": [],
            "quality": [
                {"check": "not_null", "attr": "balance"},
                {"check": "range", "attr": "days_past_due", "min": 0, "max": 3650},
                {"check": "unique_on_index"},
            ],
        },
    },
    {
        "slug": "fx-rates-checked",
        "title": "FX rates with a sanity check on daily moves",
        "summary": "Daily rates where a jump of more than ten per cent in a day blocks the pin "
        "until somebody looks.",
        "note": "max_daily_change catches the fat-finger and the wrong-unit file that a range "
        "check would let through; allowed_values keeps the currency codes to the ones the "
        "desk trades.",
        "definition": {
            "index": ["date", "ccy"],
            "index_types": {"date": "date", "ccy": "string"},
            "schema": [{"name": "rate_to_usd", "type": "float64"}],
            "source": {"type": "csv"},
            "resolution": {
                "grid": {"calendar": "ISO_business_days"},
                "rules": {"rate_to_usd": "forward_fill(limit=2)"},
            },
            "transform": [],
            "quality": [
                {"check": "not_null", "attr": "rate_to_usd"},
                {"check": "max_daily_change", "attr": "rate_to_usd", "max": 0.10},
                {"check": "allowed_values", "attr": "ccy", "values": ["EUR", "GBP", "JPY"]},
            ],
        },
    },
    {
        "slug": "bureau-scores",
        "title": "Bureau scores per applicant",
        "summary": "One score per applicant per pull date, kept inside the bureau's scale.",
        "note": "An event-indexed feature: applicants are scored when they apply, not on a "
        "calendar, so the grid is as_is and no rule fills anything -- a missing score stays "
        "missing, which is the honest answer.",
        "definition": {
            "index": ["pull_date", "applicant_id"],
            "index_types": {"pull_date": "date", "applicant_id": "string"},
            "schema": [{"name": "bureau_score", "type": "int64"}],
            "source": {"type": "csv"},
            "resolution": {"grid": "as_is", "rules": {}},
            "transform": [],
            "quality": [
                {"check": "range", "attr": "bureau_score", "min": 300, "max": 900},
                {"check": "unique_on_index"},
            ],
        },
    },
]

# Objects shown to read and copy: what each looks like in full.
OTHERS: list[dict[str, Any]] = [
    {
        "slug": "featureset-mapping",
        "kind": "Feature set",
        "title": "A credit panel mapped to a model's inputs",
        "note": "Each attribute names the feature it comes from; the set aligns them on one "
        "index. Outer alignment keeps every applicant; the fill policy is stated once here, "
        "not decided afresh in every query.",
        "help": "/help/featuresets",
        "body": {
            "index": ["pull_date", "applicant_id"],
            "alignment": "outer",
            "attributes": [
                {"name": "bureau", "feature": "credit/bureau_scores@v1", "attr": "bureau_score"},
                {"name": "utilisation", "feature": "credit/revolving@v2", "attr": "utilisation"},
                {"name": "dti", "feature": "credit/affordability@v1", "attr": "dti"},
            ],
        },
    },
    {
        "slug": "training-warrant",
        "kind": "Training warrant",
        "title": "Terms for fitting a scorecard",
        "note": "The split is recorded rather than remembered; the test rows are escrowed and "
        "never downloaded, and every blind score against them is counted. The bindings map "
        "each feature input of the model to a column of the pinned set; an input with the "
        "same name as its column needs no entry.",
        "help": "/help/warrants",
        "body": {
            "model": "credit/pd_scorecard@v1",
            "featureset": "maya://featureset/credit/panel#fit/2025-06-30",
            "spec": {
                "target": "default_12m",
                "split": {"train": 0.7, "validation": 0.15, "test": 0.15},
                "seed": 42,
                "holdout": "escrowed",
                "bindings": {"bureau": "bureau_score", "utilisation": "util", "dti": "dti"},
            },
        },
    },
    {
        "slug": "covenants",
        "kind": "Execution warrant",
        "title": "Covenants that suspend a live model",
        "note": "A breach suspends the warrant at once and every consuming call fails closed. "
        "The population stability baseline is fixed when the warrant is drawn, so it cannot "
        "drift with the population it is meant to watch.",
        "help": "/help/warrants#execution-warrants",
        "body": [
            {"kind": "input_null_rate", "attr": "bureau", "max": 0.05},
            {"kind": "input_range", "attr": "utilisation", "min": 0, "max": 1.5},
            {"kind": "input_psi", "attr": "utilisation", "max": 0.25},
            {"kind": "output_range", "min": 0, "max": 1},
            {"kind": "staleness_days", "max": 7},
        ],
    },
    {
        "slug": "workflow-transition",
        "kind": "Workflow policy",
        "title": "An approval that needs the owner too, in production",
        "note": "A transition names the states it leaves, the capability it needs, the checks "
        "it runs and the approvals it requires; an approval can apply only in production. A "
        "policy is itself changed by a draft and activated by a second administrator.",
        "help": "/help/workflow",
        "body": {
            "approve": {
                "from": ["in_review"],
                "to": "approved",
                "capability": "A",
                "approvals": [
                    {"role": "model_manager", "count": 1},
                    {"role": "model_owner", "count": 1, "when": "prod"},
                ],
                "checks": ["parameters_approved", "no_open_blocking_comments"],
            }
        },
    },
]


def feature(slug: str) -> dict[str, Any] | None:
    return next((e for e in FEATURES if e["slug"] == slug), None)
