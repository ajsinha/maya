"""
MAYA — test fixtures.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.config import PropertiesConfigurator  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_singleton():
    """Every test gets a clean configurator; the singleton must not leak."""
    PropertiesConfigurator.reset()
    yield
    PropertiesConfigurator.reset()


@pytest.fixture
def write_yaml(tmp_path):
    def _write(name: str, body: str) -> str:
        p = tmp_path / name
        p.write_text(body)
        return str(p)
    return _write


@pytest.fixture
def db():
    from db import Database
    return Database("sqlite:///:memory:")


@pytest.fixture
def repos(db):
    from db import (AliasRepository, EvidenceRepository, HookRepository, ModelRepository,
                    RiskRepository, VersionRepository)
    return {"models": ModelRepository(db), "versions": VersionRepository(db),
            "aliases": AliasRepository(db), "evidence": EvidenceRepository(db),
            "risk": RiskRepository(db), "hooks": HookRepository(db)}


@pytest.fixture
def evidence(repos):
    from core.evidence import EvidenceEngine
    return EvidenceEngine(repos["evidence"])


@pytest.fixture
def registry(repos, evidence):
    from core.registry import ModelRegistry
    return ModelRegistry(repos["models"], repos["versions"], repos["aliases"], evidence)


@pytest.fixture
def tiering():
    from core.risk import TieringEngine
    return TieringEngine(
        {"negligible": 0, "low": 1e6, "moderate": 5e7, "material": 5e8, "critical": 5e9},
        {"commercial": 1, "risk_management": 2, "financial_reporting": 3,
         "regulatory_capital": 4},
        {1: 12, 2: 18, 3: 24, 4: 36})


KERNEL = {"parameter_kind": "estimated_coefficients", "fit_procedure": "estimate",
          "input_schema": [{"name": "dscr", "dtype": "float", "minimum": -5, "maximum": 20}],
          "output_schema": [{"name": "pd_12m", "dtype": "float"}]}
CONTRACT = {"assumptions": [{"key": "dscr", "minimum": -5, "maximum": 20}],
            "guarantees": [{"key": "gini", "minimum": 0.42}],
            "on_boundary_violation": "reject"}
URN = "maya://model/credit.pd.smallbiz"


@pytest.fixture
def kernel_spec():
    import copy
    return copy.deepcopy(KERNEL)


@pytest.fixture
def contract_spec():
    import copy
    return copy.deepcopy(CONTRACT)


@pytest.fixture
def a_model(registry):
    registry.register(URN, "SB PD", "credit.pd.scorecard", "credit",
                      "person/j.okafor", "LE-US-01", "12m PD at origination")
    registry.set_tier(registry.get(URN)["id"], 1)
    return registry.get(URN)


@pytest.fixture
def approved_version(registry, a_model, kernel_spec, contract_spec):
    registry.create_version(URN, "3.2.1", kernel_spec, contract_spec, artifact_digest="sha256:abc")
    return registry.approve_version(URN, "3.2.1")


@pytest.fixture
def hooks(repos, registry, evidence):
    from core.execution import HookService
    return HookService(repos["hooks"], registry, evidence, jitter_pct=0)
