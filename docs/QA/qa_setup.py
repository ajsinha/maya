"""
MAYA — build the estate the QA cheatsheet walks through. Windows, macOS, Linux.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

    python docs/QA/qa_setup.py
    python docs/QA/qa_setup.py --url http://host:5006 --user admin --password ...

The same estate `qa-setup.sh` builds, in Python — because that shell script
needs bash and curl, and a Windows tester has neither by default. This is the
version to use; the shell one is kept for anybody already scripted around it.

**Written with the SDK, not with raw HTTP**, which is the point of having one.
Every call below is `maya.features.define(...)` or `maya.models.register(...)`,
so the script doubles as a worked example of the client a bank would actually
build against — and if a call here is awkward, that is the SDK's problem to
fix rather than the script's to route around.

**Idempotent.** Re-running against an estate that already has these is not an
error: each step reports "already there" and continues. A setup script that
fails on its second run is one people stop trusting on the first.
"""
from __future__ import annotations

import argparse
import pathlib
import sys

# The SDK, from this checkout. A tester running the QA pack has the repository
# and may not have `pip install`ed anything, so the path is added rather than
# assumed — the alternative is a first step that fails on an import.
ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "sdk" / "python"))

from maya_sdk import Maya
from maya_sdk.errors import MayaError, Refused, Unreachable


def parse() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Build the estate the MAYA QA cheatsheet walks through.")
    p.add_argument("--url", default="http://127.0.0.1:5006",
                   help="where MAYA is (default: %(default)s)")
    p.add_argument("--user", default="admin")
    p.add_argument("--password", default="maya-admin-dev")
    return p.parse_args()


def say(step: str, what: str) -> None:
    print(f"\n{step}  {what}")


def done(detail: str) -> None:
    print(f"     {detail}")


def attempt(what: str, call, *, already: str = "already there"):
    """Run one setup step, and treat "it exists" as success.

    A conflict on a second run is the platform refusing correctly — the model
    urn is unique, the feature name is unique — so it is reported and stepped
    over. Any OTHER refusal is printed in full and stops the script, because a
    setup that carries on past a real refusal produces an estate that does not
    match what the cheatsheet then describes.
    """
    try:
        call()
        return True
    except Refused as exc:
        if exc.status in (409, 422) and _is_duplicate(exc):
            done(f"{what}: {already}")
            return False
        print(f"\n  REFUSED  {what}")
        print(f"     {exc.detail}")
        if getattr(exc, "remediation", ""):
            print(f"     {exc.remediation}")
        raise SystemExit(2) from exc


def load_once(maya, view: str, rows: list) -> None:
    """Materialise, unless this view already has a version.

    Loading values is the ONE step that is not naturally idempotent: every
    upload becomes a new version, by design — a version is what a featureset
    pins and half a version is not something anybody can pin. So a second run
    of this script silently produced `qa_borrower` v2, and the cheatsheet's
    "qa_borrower v1 (3 rows, one a restatement)" quietly stopped describing
    what a tester was looking at.

    Asked rather than assumed: the platform is the one that knows.
    """
    existing = maya.views.versions(view).get("versions", [])
    if existing:
        done(f"{view}: already has v{existing[-1]['version']}, not loading again")
        return
    maya.views.materialise(view, rows=rows)
    done(f"{view}: {len(rows)} row(s) loaded as v1")


def _is_duplicate(exc: Refused) -> bool:
    text = f"{exc.code} {exc.detail}".lower()
    return any(word in text for word in
               ("already", "duplicate", "exists", "taken"))


ROWS_BORROWER = [
    # C1 and C2 as first known. Both clocks on every row, always: `event_ts` is
    # when the fact was true, `ingest_ts` is when we learned it.
    {"entity_id": "C1", "event_ts": 100.0, "ingest_ts": 110.0,
     "dscr": 1.20, "ltv": 0.62,
     "monthly_balances": [10, 11, 12, 11, 10, 9, 9, 10, 11, 12, 13, 12],
     "correlation": [[1, 0.3, 0.1], [0.3, 1, 0.2], [0.1, 0.2, 1]]},
    {"entity_id": "C2", "event_ts": 100.0, "ingest_ts": 110.0,
     "dscr": 2.10, "ltv": 0.35,
     "monthly_balances": [20, 21, 22, 21, 20, 19, 19, 20, 21, 22, 23, 22],
     "correlation": [[1, 0, 0], [0, 1, 0], [0, 0, 1]]},
    # THE RESTATEMENT, and the reason this estate is worth building: same
    # entity, same event time, later ingest time, materially worse numbers. A
    # training set built for a decision made before ingest 900 must still see
    # 1.20, and one built after must see 0.40. Section 9 of the cheatsheet is
    # about exactly this row.
    {"entity_id": "C1", "event_ts": 100.0, "ingest_ts": 900.0,
     "dscr": 0.40, "ltv": 0.81,
     "monthly_balances": [5, 5, 4, 4, 3, 3, 2, 2, 1, 1, 0, 0],
     "correlation": [[1, 0.9, 0.8], [0.9, 1, 0.7], [0.8, 0.7, 1]]},
]

ROWS_OUTCOMES = [
    {"entity_id": "C1", "event_ts": 500.0, "ingest_ts": 505.0, "defaulted_12m": 1},
    {"entity_id": "C2", "event_ts": 500.0, "ingest_ts": 505.0, "defaulted_12m": 0},
]

KERNEL = {
    "runtime": "formula",
    "parameter_kind": "estimated_coefficients",
    "fit_procedure": "estimate",
    "entry": {"expression": "1 / (1 + exp(-(intercept + beta_dscr * dscr "
                            "+ beta_ltv * ltv)))",
              "target": "pd_12m"},
    "input_schema": [
        {"name": "dscr", "dtype": "numeric", "symbol": r"\mathrm{DSCR}",
         "unit": "ratio"},
        {"name": "ltv", "dtype": "numeric", "symbol": r"\mathrm{LTV}",
         "unit": "ratio"},
        {"name": "intercept", "dtype": "numeric", "symbol": r"\alpha"},
        {"name": "beta_dscr", "dtype": "numeric", "symbol": r"\beta_{1}"},
        {"name": "beta_ltv", "dtype": "numeric", "symbol": r"\beta_{2}"},
    ],
    "output_schema": [{"name": "pd_12m", "dtype": "numeric",
                       "unit": "probability"}],
}


def main() -> int:
    args = parse()
    maya = Maya(args.url, args.user, args.password)

    try:
        who = maya.whoami()
    except Unreachable as exc:
        print(f"Cannot reach MAYA at {args.url}: {exc}")
        print("Start it with:  python run_maya_web.py")
        return 1
    except MayaError as exc:
        print(f"MAYA refused the sign-in: {exc}")
        return 1
    print(f"Connected to {args.url} as {who.get('username')} "
          f"({', '.join(who.get('roles') or [])})")

    # ---------------------------------------------------------- 1. people
    say("1.", "people and a role")
    attempt("the feature_curator role", lambda: maya.principals.define_role(
        name="feature_curator",
        description="defines and loads features, nothing else",
        permissions=["feature:read", "feature:define", "feature:materialise",
                     "featureset:define"]))
    attempt("q.tester", lambda: maya.principals.create(
        username="q.tester", display_name="Q Tester",
        roles=["feature_curator"], password="qa-password-long"))
    attempt("svc/qa-runner", lambda: maya.principals.create(
        username="svc/qa-runner", display_name="QA runner",
        kind="service", roles=["service"]))
    done("q.tester (feature_curator), svc/qa-runner (service)")

    # -------------------------------------------------------- 2. features
    say("2.", "features — a scalar, a 12-element array, a 3x3 matrix, a label")
    for spec in (
        dict(name="dscr", dtype="numeric",
             description="debt service coverage ratio"),
        dict(name="ltv", dtype="numeric", description="loan to value"),
        dict(name="monthly_balances", dtype="numeric", shape=[12],
             description="twelve monthly balances"),
        dict(name="correlation", dtype="numeric", shape=[3, 3],
             description="a 3x3 correlation matrix"),
        dict(name="defaulted_12m", dtype="numeric",
             description="1 if the borrower defaulted within 12 months"),
    ):
        attempt(spec["name"], lambda s=spec: maya.features.define(
            entity="borrower", owner="person/d.raman", **s))
    done("dscr, ltv, monthly_balances[12], correlation[3,3], defaulted_12m")

    # ----------------------------------------------------------- 3. views
    say("3.", "views, and data in them (both clocks on every row)")
    attempt("the qa_borrower view", lambda: maya.features.create_view(
        name="qa_borrower", entity="borrower", owner="person/d.raman",
        features=["dscr", "ltv", "monthly_balances", "correlation"],
        description="QA borrower facts"))
    load_once(maya, "qa_borrower", ROWS_BORROWER)
    attempt("the qa_outcomes view", lambda: maya.features.create_view(
        name="qa_outcomes", entity="borrower", owner="person/d.raman",
        features=["defaulted_12m"], description="observed outcomes"))
    load_once(maya, "qa_outcomes", ROWS_OUTCOMES)
    # Not "v1", asserted. The two lines above already said which version each
    # view is at, and a summary repeating a number it did not check is how a
    # script comes to describe an estate somebody else is looking at.
    done("three rows in qa_borrower, one of them a RESTATEMENT of C1 — "
         "same event time, later ingest time, materially worse numbers")

    # ----------------------------------------------------- 4. a featureset
    say("4.", "a featureset, and a version that pins every slot")
    attempt("the qa_pd_inputs featureset", lambda: maya.featuresets.define(
        name="qa_pd_inputs", entity="borrower",
        slots={"coverage": "numeric", "leverage": "numeric",
               "defaulted": "numeric"},
        label_slot="defaulted", outcome_window_days=365,
        description="what the QA PD scorecard reads"))
    attempt("qa_pd_inputs v1", lambda: maya.featuresets.fill(
        "qa_pd_inputs",
        bindings={"coverage": "dscr", "leverage": "ltv",
                  "defaulted": "defaulted_12m"}),
        already="already has a version")
    done("qa_pd_inputs v1 — coverage->dscr, leverage->ltv, "
         "defaulted->defaulted_12m")

    # ---------------------------------------------------------- 5. a model
    say("5.", "a model, tiered, with a formula kernel")
    attempt("the model record", lambda: maya.models.register(
        urn="maya://model/qa.pd.scorecard", name="QA PD scorecard",
        model_class="credit.pd.scorecard", domain="credit",
        owner="person/j.okafor", legal_entity="LE-US-01",
        purpose="12-month probability of default at origination"))
    attempt("its risk tier", lambda: maya.models.assess(
        "qa.pd.scorecard", exposure=250_000_000,
        purpose_class="credit_decision", feature_count=3,
        uses_alternative_data=False, interpretable=True),
        already="already tiered")
    attempt("version 1.0.0", lambda: maya.versions.create(
        "qa.pd.scorecard", semver="1.0.0", kernel=KERNEL),
        already="already exists")
    done("maya://model/qa.pd.scorecard @ 1.0.0")

    print("\ndone")
    print(f"Sign in at {args.url}  —  {args.user} / {args.password}")
    print("Then follow docs/QA/README.md from section 1.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
