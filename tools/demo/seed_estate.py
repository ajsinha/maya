"""
MAYA — a demonstration estate.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Builds an estate somebody can actually review: several models across several
trainability classes, taken through the governed path by DIFFERENT people,
with features, a featureset, warrants, parameters, telemetry, documents and a
finding.

Everything here goes through the HTTP API, as a client would. Nothing is
inserted. That is the point: an estate assembled by writing rows would show
screens in states the platform cannot actually reach, and a review of those
screens would be a review of fiction.

    python tools/demo/seed_estate.py --data ./data/demo

The result is a data directory and a SQLite database that can be copied.
"""
from __future__ import annotations

import argparse
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

PEOPLE = {
    "d.raman":  (["model_developer"],     "dev-pw",   "D Raman"),
    "l.fontaine": (["model_developer"],   "dev-pw",   "L Fontaine"),
    "j.okafor": (["model_owner"],         "owner-pw", "J Okafor"),
    "a.mehta":  (["validator"],           "val-pw",   "A Mehta"),
    "s.iqbal":  (["model_risk_manager"],  "mrm-pw",   "S Iqbal"),
    "t.nowak":  (["operator"],            "ops-pw",   "T Nowak"),
    "r.silva":  (["auditor"],             "aud-pw",   "R Silva"),
}


def _fail(what, response):
    print(f"   ! {what}: {response.status_code} {response.text[:220]}")


def _ok(what, response, expected=(200, 201)):
    if response.status_code in expected:
        return True
    _fail(what, response)
    return False


def build(client) -> None:
    admin = ("admin", "admin123")

    print("principals")
    for username, (roles, password, display) in PEOPLE.items():
        r = client.post("/api/v1/principals", auth=admin, json={
            "username": username, "display_name": display, "roles": roles,
            "password": password,
            "legal_entities": ["LE-US-01", "LE-UK-01"]})
        _ok(f"  {username}", r, (201, 409))
    who = {u: (u, p) for u, (_, p, _) in PEOPLE.items()}

    # ---------------------------------------------------------------- models
    # Deliberately across trainability classes, because the fibration says a
    # T3 and a T8 are asked for different evidence and the screens should show
    # that difference rather than one shape repeated.
    catalogue = [
        {"key": "credit.pd.smallbiz", "name": "Small business PD",
         "domain": "credit", "purpose": "12-month PD at origination",
         "exposure": 2.4e9, "purpose_class": "regulatory_capital",
         "kernel": {"parameter_kind": "estimated_coefficients",
                    "fit_procedure": "estimate", "output_kind": "class_probabilities",
                    "input_schema": [{"name": "dscr", "dtype": "numeric"},
                                     {"name": "ltv", "dtype": "numeric"},
                                     {"name": "years_trading", "dtype": "numeric"}],
                    "output_schema": [{"name": "pd_12m", "dtype": "numeric"}]},
         "contract": {"assumptions": [{"key": "dscr", "minimum": 0, "maximum": 20},
                                      {"key": "ltv", "minimum": 0, "maximum": 2}],
                      "guarantees": [{"key": "pd_12m", "minimum": 0, "maximum": 1},
                                     {"key": "gini", "minimum": 0.42}],
                      "on_boundary_violation": "reject"}},
        {"key": "credit.ecl.stage2", "name": "ECL stage 2 stack",
         "domain": "credit", "purpose": "IFRS 9 lifetime ECL for stage 2",
         "exposure": 8.1e9, "purpose_class": "financial_reporting",
         "kernel": {"parameter_kind": "estimated_coefficients",
                    "fit_procedure": "estimate", "output_kind": "point_estimate",
                    "input_schema": [{"name": "pd_12m", "dtype": "numeric"},
                                     {"name": "lgd", "dtype": "numeric"},
                                     {"name": "ead", "dtype": "numeric"},
                                     {"name": "discount_rate", "dtype": "numeric"}],
                    "output_schema": [{"name": "ecl", "dtype": "numeric"}]},
         "contract": {"assumptions": [{"key": "pd_12m", "minimum": 0, "maximum": 1},
                                      {"key": "lgd", "minimum": 0, "maximum": 1}],
                      "guarantees": [{"key": "ecl", "minimum": 0}],
                      "on_boundary_violation": "reject"}},
        {"key": "market.var.equity", "name": "Equity VaR",
         "domain": "market", "purpose": "1-day 99% VaR on the equity book",
         "exposure": 5.5e8, "purpose_class": "regulatory_capital",
         "kernel": {"parameter_kind": "calibration_set",
                    "fit_procedure": "calibrate", "output_kind": "point_estimate",
                    "input_schema": [{"name": "returns", "dtype": "numeric"}],
                    "output_schema": [{"name": "var_99", "dtype": "numeric"}]},
         "contract": {"assumptions": [{"key": "returns", "minimum": -1, "maximum": 1}],
                      "guarantees": [{"key": "var_99", "minimum": 0}]}},
        {"key": "aml.screening.rules", "name": "Sanctions screening rules",
         "domain": "financial_crime", "purpose": "Name screening escalation",
         "exposure": 1.2e7, "purpose_class": "risk_management",
         "kernel": {"parameter_kind": "rule_set", "fit_procedure": "author",
                    "output_kind": "decision",
                    "input_schema": [{"name": "match_score", "dtype": "numeric"},
                                     {"name": "country", "dtype": "string"}],
                    "output_schema": [{"name": "action", "dtype": "string"}]},
         "contract": {"assumptions": [{"key": "match_score", "minimum": 0, "maximum": 100}],
                      "guarantees": []}},
        {"key": "ops.summariser.llm", "name": "Complaint summariser",
         "domain": "operations", "purpose": "Summarise complaint free text",
         "exposure": 4.0e6, "purpose_class": "commercial",
         "kernel": {"parameter_kind": "opaque", "fit_procedure": "none",
                    "output_kind": "text",
                    "input_schema": [{"name": "complaint_text", "dtype": "string"}],
                    "output_schema": [{"name": "summary", "dtype": "string"}]},
         "contract": {"assumptions": [], "guarantees": []}},
    ]

    print("models, tiers and versions")
    urns = {}
    for spec in catalogue:
        urn = f"maya://model/{spec['key']}"
        urns[spec["key"]] = urn
        r = client.post("/api/v1/models", auth=who["j.okafor"], json={
            "urn": urn, "name": spec["name"], "model_class": spec["key"],
            "domain": spec["domain"], "owner": "person/j.okafor",
            "legal_entity": "LE-US-01", "purpose": spec["purpose"]})
        if not _ok(f"  register {spec['key']}", r, (201, 409)):
            continue
        _ok(f"  tier {spec['key']}",
            client.post(f"/api/v1/models/{spec['key']}/assess", auth=who["j.okafor"],
                        json={"exposure": spec["exposure"],
                              "purpose_class": spec["purpose_class"]}))
        _ok(f"  version {spec['key']}",
            client.post(f"/api/v1/models/{spec['key']}/versions", auth=who["d.raman"],
                        json={"semver": "1.0.0", "kernel": spec["kernel"],
                              "contract": spec["contract"],
                              "artifact_digest": f"sha256:{spec['key']:x<64}"[:71]}),
            (201, 409))

    # A second version of the PD model, so refinement and alias history have
    # something to say. Its contract refines the first: same assumptions, a
    # stronger discrimination floor.
    stronger = dict(catalogue[0]["contract"])
    stronger["guarantees"] = [{"key": "pd_12m", "minimum": 0, "maximum": 1},
                              {"key": "gini", "minimum": 0.47}]
    _ok("  version credit.pd.smallbiz 1.1.0",
        client.post("/api/v1/models/credit.pd.smallbiz/versions", auth=who["d.raman"],
                    json={"semver": "1.1.0", "kernel": catalogue[0]["kernel"],
                          "contract": stronger,
                          "artifact_digest": "sha256:" + "b" * 64}), (201, 409))

    print("the typed edge: PD feeds the ECL stack")
    _ok("  input_to", client.post("/api/v1/model-relations", auth=who["j.okafor"],
        json={"from_urn": urns["credit.pd.smallbiz"],
              "to_urn": urns["credit.ecl.stage2"], "kind": "input_to",
              "note": "the PD term of the ECL calculation"}), (201, 409))

    print("approvals")
    # How a version is approved depends on its TIER, which is the whole point:
    # a tier 1 or 2 version needs a quorum of two duties, a tier 3 or 4 is
    # approved by one authorised person. Asking for a quorum where none is
    # required is refused, so the seed follows the register rather than
    # assuming one shape.
    for key in ("credit.pd.smallbiz", "credit.ecl.stage2", "market.var.equity",
                "aml.screening.rules", "ops.summariser.llm"):
        opened = client.post("/api/v1/version-approvals", auth=who["s.iqbal"],
                             json={"urn": urns[key], "semver": "1.0.0"})
        if opened.status_code == 201:
            approval = opened.json()["id"]
            for signer, role in ((who["s.iqbal"], "model_risk_manager"),
                                 (who["a.mehta"], "validator")):
                _ok(f"  sign {key} as {role}",
                    client.post(f"/api/v1/version-approvals/{approval}/sign",
                                auth=signer, json={"role": role}))
        elif (opened.json() or {}).get("error") == "no_quorum_required":
            _ok(f"  approve {key} (no quorum at this tier)",
                client.post(f"/api/v1/models/{key}/versions/1.0.0/approve",
                            auth=who["s.iqbal"]))
        else:
            _fail(f"  open {key}", opened)

    print("the record itself, through the register")
    # Not the same act as approving a version, and until a review walked the
    # path by hand nothing here did it: a model whose own record sat in `draft`
    # resolved a warrant exactly like one that had been through the whole
    # register. Done AFTER the versions exist, because an approved record is
    # frozen and a new version is a change to the model.
    for key in ("credit.pd.smallbiz", "credit.ecl.stage2", "market.var.equity",
                "aml.screening.rules"):
        _ok(f"  submit {key}",
            client.post(f"/api/v1/models/{key}/submit", auth=who["j.okafor"],
                        json={"note": "ready for second-line review"}))
        _ok(f"  approve {key}",
            client.post(f"/api/v1/models/{key}/approve", auth=who["s.iqbal"],
                        json={"note": "reviewed and approved"}))
    # `ops.summariser.llm` is deliberately left in draft, so the estate shows
    # both states and the screens have something to distinguish.

    print("aliases")
    for key in ("credit.pd.smallbiz", "credit.ecl.stage2", "market.var.equity",
                "aml.screening.rules", "ops.summariser.llm"):
        _ok(f"  champion {key}",
            client.put(f"/api/v1/models/{key}/aliases", auth=who["s.iqbal"],
                       json={"environment": "prod", "alias": "champion",
                             "semver": "1.0.0"}))

    print("features, a view with rows, and a featureset")
    features = [
        ("dscr", "debt service coverage ratio at origination"),
        ("ltv", "loan to value at origination"),
        ("years_trading", "years the business has traded"),
        ("default_12m", "did the facility default within 12 months"),
    ]
    for name, description in features:
        _ok(f"  define {name}",
            client.post("/api/v1/features", auth=who["d.raman"], json={
                "name": name, "entity": "facility", "dtype": "numeric",
                "description": description, "owner": "person/d.raman",
                "source_system": "originations"}), (201, 409))

    # A view is what actually holds values. Declaring the feature and holding
    # its values are separate acts here, which is why a seed that only defined
    # features would produce a catalogue with nothing behind it.
    _ok("  create view",
        client.post("/api/v1/feature-views", auth=who["d.raman"], json={
            "name": "sb_origination", "entity": "facility",
            "owner": "person/d.raman",
            "features": [name for name, _ in features],
            "description": "origination facts for small-business facilities"}),
        (201, 409))

    now = time.time()
    day = 86400.0
    random.seed(11)
    rows = []
    for i in range(240):
        event = now - (400 - i) * day
        rows.append({"entity_id": f"FAC-{i:05d}",
                     "event_ts": event,
                     # Learned two days after the fact, which is the gap the
                     # point-in-time rule exists for.
                     "ingest_ts": event + 2 * day,
                     "dscr": round(random.uniform(0.6, 4.5), 3),
                     "ltv": round(random.uniform(0.2, 1.4), 3),
                     "years_trading": random.randint(0, 30),
                     "default_12m": 1 if random.random() < 0.07 else 0})
    _ok("  materialise 240 rows",
        client.post("/api/v1/feature-views/sb_origination/materialise",
                    auth=who["d.raman"], json={"rows": rows}), (200, 201))

    _ok("  declare featureset",
        client.post("/api/v1/featuresets", auth=who["d.raman"], json={
            "name": "sb_core", "entity": "facility",
            "slots": {"dscr": "numeric", "ltv": "numeric",
                      "years_trading": "numeric", "default_12m": "numeric"},
            "description": "the four fields the small-business PD reads"}),
        (201, 409))
    _ok("  fill it",
        client.post("/api/v1/featuresets/sb_core/versions", auth=who["d.raman"],
                    json={"bindings": {"dscr": "dscr", "ltv": "ltv",
                                       "years_trading": "years_trading",
                                       "default_12m": "default_12m"},
                          "note": "first fill"}), (200, 201, 409))

    print("warrants")
    for key, use in (("credit.pd.smallbiz", "origination_decision"),
                     ("credit.ecl.stage2", "financial_reporting"),
                     ("market.var.equity", "capital_calculation")):
        _ok(f"  grant {key}",
            client.post("/api/v1/warrants", auth=who["j.okafor"], json={
                "urn": f"{urns[key]}#champion", "environment": "prod",
                "principal": "svc/decisioning", "declared_use": use}),
            (200, 201, 409))

    print("documents")
    for key, kind, title in (
            ("credit.pd.smallbiz", "model_development_document",
             "Small business PD — development"),
            ("credit.pd.smallbiz", "validation_report",
             "Small business PD — independent validation"),
            ("credit.ecl.stage2", "model_development_document",
             "ECL stage 2 — methodology")):
        _ok(f"  attach {kind} to {key}",
            client.post("/api/v1/attachments", auth=who["d.raman"],
                        data={"urn": urns[key], "kind": kind, "title": title,
                              "model_level": "true"},
                        files={"file": (f"{key}-{kind}.md",
                                        f"# {title}\n\nWritten for the demonstration "
                                        f"estate.\n".encode(),
                                        "text/markdown")}),
            (201, 409))

    print("telemetry")
    scores = [{"entity_id": f"FAC-{i:05d}", "scored_at": now - (60 - i) * 3600,
               "score": round(random.uniform(0.001, 0.35), 5)}
              for i in range(60)]
    # Taking delivery of telemetry is `monitor:observe`, which the operator role
    # does not carry — judging a monitor and receiving its rows are separate
    # duties. The admin stands in for the engine's service principal here.
    _ok("  scores", client.post("/api/v1/telemetry", auth=admin, json={
        "urn": urns["credit.pd.smallbiz"], "semver": "1.0.0", "stream": "scores",
        "rows": scores, "source": "decisioning"}), (200, 201))

    print("a finding")
    _ok("  raise", client.post("/api/v1/findings", auth=who["a.mehta"], json={
        "urn": urns["credit.ecl.stage2"],
        "title": "LGD input has no upstream owner",
        "severity": "Medium",
        "owner": "person/j.okafor",
        "category": "data",
        "description": "The stack reads an LGD it does not produce and no "
                       "registered model produces it either, so the input has "
                       "no owner and no contract behind it."}), (200, 201))

    print("the scheduler, once, so the batch has run")
    _ok("  run", client.post("/api/v1/scheduler/run", auth=who["t.nowak"], json={}),
        (200, 201))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", default="./data/demo",
                        help="the data directory to build the estate in")
    args = parser.parse_args()

    data = Path(args.data).resolve()
    data.mkdir(parents=True, exist_ok=True)
    config = data / "application.yaml"
    config.write_text(f"""
app: {{name: MAYA, version: "0.1.0", tagline: "Model & AI Lifecycle Assurance",
       slogan: "Evidence, not assertion.",
       principle: "A model is a representation of the world. Governance is knowing the difference."}}
server: {{host: 0.0.0.0, port: 5006}}
database: {{url: "sqlite:///{data}/sqlite/maya.db"}}
data: {{dir: "{data}", artifacts: "{data}/artifacts",
        attachments: "{data}/attachments",
        delta: {{dir: "{data}/delta", features: "{data}/delta/features",
                snapshots: "{data}/delta/snapshots",
                telemetry: "{data}/delta/telemetry",
                monitoring: "{data}/delta/monitoring"}}}}
risk:
  exposure_bands: {{negligible: 0, low: 1000000, moderate: 50000000,
                   material: 500000000, critical: 5000000000}}
  purpose_ranks: {{commercial: 1, risk_management: 2, financial_reporting: 3,
                  regulatory_capital: 4}}
  review_months: {{1: 12, 2: 18, 3: 24, 4: 36}}
warrants: {{jitter_pct: 0, signing_key: demo-signing-secret,
         ttl_seconds: {{1: 3600, 2: 3600, 3: 3600, 4: 3600}},
         grace_seconds: {{1: 0, 2: 0, 3: 900, 4: 900}}}}
execution: {{captive: {{enabled: true, max_seconds: 5}}}}
logging: {{level: WARNING}}
""")

    from fastapi.testclient import TestClient

    from core.config import PropertiesConfigurator
    from run_maya_web import create_app

    PropertiesConfigurator.reset()
    app = create_app(PropertiesConfigurator(str(config), reload_interval=0))
    with TestClient(app) as client:
        build(client)

    print(f"\nestate built in {data}")
    print(f"run it with:  MAYA_CONFIG={config} python run_maya_web.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
