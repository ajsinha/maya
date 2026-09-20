"""
§29.7: the documented mathematics is authoritative, and the code has to agree with it.

The six-rung ladder asks whether an artifact parses, imports nothing forbidden and runs.
That is a different question from whether it *computes the model*, and the commonest
implementation bugs are perfectly valid Python that passes every rung. So the differential
test runs with the ladder rather than when somebody remembers to ask, its result is kept
against the artifact hash it tested, and a closed-form version whose code contradicts its
own specification cannot be moved on.

The case that found this: a level-payment mortgage amortised over the original term
instead of the term remaining. One expression, invisible on a new loan, wrong on every
seasoned one, and never caught by a test written from the same misunderstanding.

Copyright (c) 2026 Ashutosh Sinha.  All rights reserved.
"""

from __future__ import annotations

import pytest

from maya.core.errors import NotApproved, ValidationFailed
from tests.conftest import approved_feature, price_csv
from tests.test_warrants import complete_spec

MORTGAGE = r"""
i = \frac{rate}{12}
n = term - age
annuity = \frac{1 - (1 + i)^{-n}}{i}
netCash = \frac{balance}{annuity}
"""
ROLES = {"rate": "feature", "term": "feature", "age": "feature", "balance": "feature"}
SAMPLE = {
    "balance": [250_000.0, 75_000.0],
    "rate": [0.0325, 0.0615],
    "term": [360.0, 180.0],
    "age": [1.0, 149.0],
}
RIGHT = '''
"""The level payment that amortises the balance over the payments remaining."""

import numpy as np


class Model:
    def fit(self, X, y, ctx):
        return {}

    def predict(self, X, params, ctx):
        balance = np.asarray(X["balance"], dtype=float)
        monthly = np.asarray(X["rate"], dtype=float) / 12.0
        remaining = np.asarray(X["term"], dtype=float) - np.asarray(X["age"], dtype=float)
        growth = (1.0 + monthly) ** remaining
        return balance * monthly * growth / (growth - 1.0)
'''
WRONG = RIGHT.replace(
    'remaining = np.asarray(X["term"], dtype=float) - np.asarray(X["age"], dtype=float)',
    'remaining = np.asarray(X["term"], dtype=float)',
)


@pytest.fixture(scope="module")
def mortgage(world):
    w = world
    w.p.access.create_namespace(w.admin, name="cash", preset="standard")
    w.p.models.create(w.mona, namespace="cash", name="annuity", formula=MORTGAGE, roles=ROLES)
    w.p.models.update_draft(w.mona, "cash/annuity", spec_latex=complete_spec("annuity"))
    return w


def upload(w, source: str) -> dict:
    w.p.models.upload_artifact(w.mona, "cash/annuity", source, sample=SAMPLE, params={})
    w.drain()
    return w.p.models.get(w.mona, "cash/annuity")["versions"][0]["artifact_report"] or {}


def test_the_ladder_also_compares_the_code_with_the_mathematics(mortgage):
    """Uploading is enough: nobody has to remember to ask for the comparison."""
    report = upload(mortgage, RIGHT)
    assert report["passed"] is True
    got = report["conformance"]
    assert got["agreed"] == got["total"] > 0
    assert (
        got["artifact_hash"]
        == mortgage.p.models.get(mortgage.mona, "cash/annuity")["versions"][0]["artifact_hash"]
    )
    assert "unit interval" in got["domain"], "and it says which domain it used"


def test_a_version_whose_code_contradicts_its_specification_cannot_be_submitted(mortgage):
    w = mortgage
    report = upload(w, WRONG)
    assert report["passed"] is True, "the ladder is happy: it is valid, running Python"
    assert report["conformance"]["agreed"] == 0, "and it computes something else entirely"
    with pytest.raises(NotApproved, match="disagrees with the specification"):
        w.p.models.transition(w.mona, "cash/annuity", 1, "submit")
    upload(w, RIGHT)
    assert w.p.models.transition(w.mona, "cash/annuity", 1, "submit")["state"] == "in_review"


def test_a_result_belongs_to_the_code_it_tested(mortgage):
    """A clean run is not inherited by whatever is uploaded next."""
    w = mortgage
    version = w.p.models.get(w.mona, "cash/annuity")["versions"][0]
    clean = version["artifact_report"]["conformance"]
    assert clean["artifact_hash"] == version["artifact_hash"], "it tested what is attached"
    stale = {
        "artifact_hash": "a different artifact entirely",
        "formula_ir": version["formula_ir"],
        "artifact_report": {"conformance": clean},
    }
    ok, detail = w.p.models.check_conformance(None, {"row": stale})
    assert not ok and "has not been tested against the specification since it changed" in detail


def test_the_domain_can_be_a_real_feature_set_and_the_report_says_so(mortgage):
    """Numbers near 1 do not test a mortgage. A named feature set supplies the real domain."""
    w = mortgage
    approved_feature(w, "px", price_csv(8), ns="cash")
    fs_def = {
        "index": ["date", "symbol"],
        "members": [
            {"attr": attr, "ref": "maya://feature/cash/px@v1", "source_attr": "close"}
            for attr in ("balance", "rate", "term", "age")
        ],
    }
    w.p.featuresets.create(w.devi, namespace="cash", name="dom", definition=fs_def)
    w.p.featuresets.transition(w.devi, "cash/dom", 1, "submit")
    w.p.featuresets.transition(w.mick, "cash/dom", 1, "approve")
    out = w.p.models.conformance(
        w.mona, "cash/annuity", 1, n=200, featureset="maya://featureset/cash/dom@v1"
    )
    assert "resampled from maya://featureset/cash/dom@v1" in out["domain"]
    assert out["agreed"] == out["total"] == 200
    # and the recorded result is replaced by the better-founded one
    got = w.p.models.get(w.mona, "cash/annuity")["versions"][0]["artifact_report"]["conformance"]
    assert "resampled from" in got["domain"]


def test_a_feature_set_that_cannot_supply_the_domain_is_refused_by_name(mortgage):
    w = mortgage
    thin = {
        "index": ["date", "symbol"],
        "members": [
            {"attr": "balance", "ref": "maya://feature/cash/px@v1", "source_attr": "close"}
        ],
    }
    w.p.featuresets.create(w.devi, namespace="cash", name="thin", definition=thin)
    w.p.featuresets.transition(w.devi, "cash/thin", 1, "submit")
    w.p.featuresets.transition(w.mick, "cash/thin", 1, "approve")
    with pytest.raises(ValidationFailed, match="does not expose"):
        w.p.models.conformance(
            w.mona, "cash/annuity", 1, n=10, featureset="maya://featureset/cash/thin@v1"
        )


def test_a_black_box_has_nothing_to_compare_against(world):
    """A declared black box skips the comparison by name, rather than failing it."""
    ir = {
        "inputs": [{"name": "x", "type": "float64"}],
        "outputs": [{"name": "score"}],
        "black_box": {"estimates": "a score", "architecture": "vendor-hosted ensemble"},
    }
    ok, detail = world.p.models.check_conformance(
        None, {"row": {"artifact_hash": "abc", "formula_ir": ir, "artifact_report": {}}}
    )
    assert ok and "no closed form" in detail
    ok, detail = world.p.models.check_conformance(
        None, {"row": {"artifact_hash": None, "formula_ir": ir, "artifact_report": {}}}
    )
    assert ok and "nothing to compare" in detail


# The case that found the next one: a model whose parameters are signed. A yield curve's
# slope and curvature factors are either sign, so the middle of their declared bounds is
# exactly zero.
CURVE = r"""
z = \frac{\tau}{\lambda}
L_{slope} = \frac{1 - e^{-z}}{z}
y = \beta_{0} + \beta_{1} L_{slope}
"""
CURVE_ROLES = {
    "\\tau": "feature",
    "\\beta_{0}": "parameter",
    "\\beta_{1}": "parameter",
    "\\lambda": "parameter",
}
CURVE_BOUNDS = {"beta0": [0.0, 0.25], "beta1": [-0.25, 0.25], "lambda": [0.25, 6.0]}
CURVE_WRONG = '''
"""A two-factor Nelson-Siegel curve, with the loading divided by the wrong thing."""

import numpy as np


class Model:
    def fit(self, X, y, ctx):
        return {}

    def predict(self, X, params, ctx):
        maturity = np.asarray(X["tau"], dtype=float)
        scaled = maturity / float(params["lambda"])
        loading = (1.0 - np.exp(-scaled)) / maturity  # the bug: tau, not tau / lambda
        return params["beta0"] + params["beta1"] * loading
'''


def test_the_comparison_is_not_run_where_a_signed_parameter_is_zero(world):
    """The values a differential test uses are part of what it establishes.

    A parameter placed at the middle of its declared bounds is *exactly zero* whenever those
    bounds straddle zero, and a factor of zero switches off the term it multiplies — so the
    comparison quietly stops testing that part of the mathematics. Here the shape of a yield
    curve hangs off a signed factor: at its midpoint an implementation that computes the
    slope loading wrongly agrees with the specification on every row, because nothing
    multiplies the loading. The default point is therefore off-centre, and the values used
    are recorded beside the count so a reviewer can see where the test looked.
    """
    import numpy as np

    from maya.formula.conformance import conformance_test, sample_inputs
    from maya.formula.parse import parse_model
    from maya.services.models import ModelService

    w = world
    ir = parse_model(CURVE, roles=CURVE_ROLES)
    ir["inputs"] = [
        {**i, "bounds": CURVE_BOUNDS[i["name"]]} if i["name"] in CURVE_BOUNDS else i
        for i in ir["inputs"]
    ]
    defaults = ModelService._default_params({"formula_ir": ir})
    assert set(defaults) == set(CURVE_BOUNDS)
    assert all(value != 0.0 for value in defaults.values()), "a zero tests nothing"
    assert all(lo <= defaults[name] <= hi for name, (lo, hi) in CURVE_BOUNDS.items()), (
        "and every value is inside the bounds the model declared"
    )

    def wrong(x: dict, params: dict) -> dict:
        maturity = np.asarray(x["tau"], dtype=float)
        scaled = maturity / params["lambda"]
        loading = (1.0 - np.exp(-scaled)) / maturity
        return {"y": params["beta0"] + params["beta1"] * loading}

    samples = sample_inputs(ir, {"tau": np.linspace(0.1, 30.0, 64)}, n=200, seed=7)
    midpoints = {name: (lo + hi) / 2 for name, (lo, hi) in CURVE_BOUNDS.items()}
    blind = conformance_test(ir, wrong, samples, midpoints)
    assert blind["agreed"] == blind["total"] == 200, "at the midpoints, nothing looks wrong"
    assert conformance_test(ir, wrong, samples, defaults)["agreed"] == 0, "off centre, every row"

    w.p.access.create_namespace(w.admin, name="rate", preset="standard")
    w.p.models.create(w.mona, namespace="rate", name="ns", formula=CURVE, roles=CURVE_ROLES)
    w.p.models.update_draft(w.mona, "rate/ns", ir=ir, spec_latex=complete_spec("ns"))
    w.p.models.upload_artifact(w.mona, "rate/ns", CURVE_WRONG, sample={"tau": [0.5, 2.0, 10.0]})
    w.drain()
    got = w.p.models.get(w.mona, "rate/ns")["versions"][0]["artifact_report"]["conformance"]
    assert got["agreed"] == 0, "and the same bug is caught end to end, on upload"
    assert got["params"] == defaults, "with the values it was run at on the record"
    with pytest.raises(NotApproved, match="disagrees with the specification"):
        w.p.models.transition(w.mona, "rate/ns", 1, "submit")
