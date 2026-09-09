#!/usr/bin/env python3
"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

CASE STUDY 13 — Short-term electricity load forecasting: a trained network that
has to EARN its opacity, and an artifact whose digest is its identity (T3).

A grid operator forecasts system load an hour ahead. Load is famously U-shaped
in temperature — heating below about 15C, cooling above about 22C, and a
trough between — which is a genuinely non-linear relationship a linear model
cannot represent however many terms you give it.

**What T3's fibre asks for, and what most institutions skip.** MAYA's fibre for
a machine-learned model asks for soundness as:

    "why the opacity was worth it, evidenced by a benchmark against a simpler
     incumbent"

So this case study registers BOTH models. The linear incumbent is a real
registered model with its own version, parameters and approval — not a number
in a slide — and the network's parameter set carries the head-to-head against
it. If the network had not won, the record would say so, and the honest
conclusion would be to ship the linear one.

**The artifact is the model.** A T3 model's parameters are not a row anybody
reads; they are bytes. MAYA holds them by content address, and the case study
shows what that buys: retraining with a different seed and identical code
produces a DIFFERENT digest, which is the only reliable answer to "is this the
model we approved?"

**The limitation that is measured rather than mentioned.** The model is
backtested on OBSERVED temperature and deployed on FORECAST temperature. The
script quantifies the gap instead of noting it, because a limitation without a
number is a sentence in a document nobody acts on.

**Who does what.** MAYA registers, stores the artifact by digest, and warrants.
The training is numpy in this file and the scoring is onnxruntime in this file
— MAYA has a captive engine and this case study deliberately does not use it,
because the boundary being demonstrated is the one where the bank runs its own
models.

REQUIRES `onnx` (the authoring library, in requirements-dev.txt) to build the
graph. MAYA itself needs only `onnxruntime`, which is in requirements.txt.
"""
from __future__ import annotations

import hashlib
import math
import pathlib
import sys
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from _common.casekit import (Maya, Say, approve_version, attempt,
                             connect, document, ensure_cast, ensure_filled,
                             ensure_version, latex_escape, load_once, parse,
                             put_record_in_force, save_json, table)

HERE = pathlib.Path(__file__).resolve().parent

#: Two models, because the fibre asks for two.
URN = "maya://model/grid.load.hourly_network"
SHORT = "grid.load.hourly_network"
BASE_URN = "maya://model/grid.load.hourly_linear"
BASE_SHORT = "grid.load.hourly_linear"
SEMVER = "1.0.0"

VIEW = "grid_hourly_load"
FEATURESET = "load_forecast_inputs"
ENTITY = "grid_hour"

AS_OF = 1_767_225_600.0
WINDOW_FROM = 1_735_689_600.0

#: The feature order. IT IS LOAD-BEARING: MAYA's ONNX runtime builds one input
#: tensor from the version's `input_schema` in declaration order, so this list
#: and the graph's first dimension are the same fact written twice, and they
#: must not drift. Declared once here and used everywhere below.
FEATURES: List[Tuple[str, str]] = [
    ("temperature_c", "dry-bulb temperature at the load centre, degrees Celsius"),
    ("hour_sin", "sine of the hour angle — the daily cycle, without a discontinuity at midnight"),
    ("hour_cos", "cosine of the hour angle"),
    ("is_weekend", "1 on Saturday and Sunday, 0 otherwise"),
]
NAMES = [f for f, _ in FEATURES]

#: The graph's name, written into the ONNX file and into the kernel's
#: entry block. One constant, because two spellings of it is a defect
#: waiting for the day somebody renames one.
GRAPH_NAME = "load_forecast"

TRAIN_ROWS, HELDOUT_ROWS = 1800, 600
SEED_WORLD, SEED_FIT, SEED_REFIT = 20260909, 11, 12
HIDDEN, EPOCHS, LR = 12, 4000, 0.05

#: The forecast error a day-ahead temperature forecast actually carries. The
#: model is BACKTESTED on observed temperature and DEPLOYED on this.
FORECAST_SD_C = 1.8


# ================================================================== the world
def true_load(temp: float, hour: float, weekend: float) -> float:
    """Load in MW. U-shaped in temperature, and that is the whole point.

    Below about 15C people heat; above about 22C they cool; between the two the
    response is flat. A linear model must choose one slope for a relationship
    that has two, and the error it makes is not noise — it is structure.
    """
    heating = max(0.0, 15.0 - temp) * 62.0
    cooling = max(0.0, temp - 22.0) * 84.0
    daily = (900.0 * math.sin((hour - 7) / 24.0 * 2 * math.pi)
             + 300.0 * math.sin((hour - 3) / 12.0 * 2 * math.pi))
    return 5200.0 + heating + cooling + daily - (620.0 if weekend else 0.0)


def world(np):
    """Generate the hours. Synthetic, and the script says so out loud."""
    rng = np.random.default_rng(SEED_WORLD)
    n = TRAIN_ROWS + HELDOUT_ROWS
    temp = rng.normal(14.0, 9.0, n)
    hour = rng.integers(0, 24, n).astype(float)
    weekend = (rng.random(n) < 2 / 7).astype(float)
    load = np.array([true_load(t, h, w)
                     for t, h, w in zip(temp, hour, weekend)])
    load = load + rng.normal(0.0, 55.0, n)          # the irreducible floor
    features = np.column_stack([temp,
                                np.sin(2 * np.pi * hour / 24.0),
                                np.cos(2 * np.pi * hour / 24.0),
                                weekend])
    # What the day-ahead forecast would have said instead of what happened.
    forecast_temp = temp + rng.normal(0.0, FORECAST_SD_C, n)
    forecast = features.copy()
    forecast[:, 0] = forecast_temp
    return features, forecast, load, hour


def r2(np, predicted, actual) -> float:
    return float(1 - ((actual - predicted) ** 2).sum()
                 / ((actual - actual.mean()) ** 2).sum())


def rmse(np, predicted, actual) -> float:
    return float(np.sqrt(((actual - predicted) ** 2).mean()))


# ============================================================== the incumbent
def fit_linear(np, x, y):
    """Ordinary least squares. THE ENGINE'S JOB, and the benchmark."""
    design = np.column_stack([np.ones(len(x)), x])
    beta, *_ = np.linalg.lstsq(design, y, rcond=None)
    return beta


def linear_predict(np, beta, x):
    return np.column_stack([np.ones(len(x)), x]) @ beta


# ================================================================= the network
def fit_network(np, x, y, *, seed: int):
    """A two-layer ReLU network, trained by Adam. THE ENGINE'S JOB.

    Written out rather than imported because the point is the governance, and
    a reader who cannot see what was trained cannot check anything that follows.
    Standardisation statistics are returned with the weights: they are part of
    the model, and a model whose scaler lives somewhere else is a model that
    will one day be served with the wrong one.
    """
    mu, sd = x.mean(0), x.std(0)
    ym, ys = y.mean(), y.std()
    rng = np.random.default_rng(seed)
    z = (x - mu) / sd
    target = ((y - ym) / ys).reshape(-1, 1)
    w1 = rng.normal(0.0, 0.7, (x.shape[1], HIDDEN))
    b1 = np.zeros(HIDDEN)
    w2 = rng.normal(0.0, 0.7, (HIDDEN, 1))
    b2 = np.zeros(1)
    params = {"w1": w1, "b1": b1, "w2": w2, "b2": b2}
    first = {k: np.zeros_like(v) for k, v in params.items()}
    second = {k: np.zeros_like(v) for k, v in params.items()}
    for epoch in range(1, EPOCHS + 1):
        hidden = np.maximum(0.0, z @ w1 + b1)
        out = hidden @ w2 + b2
        delta = (out - target) * 2.0 / len(z)
        grads = {"w2": hidden.T @ delta, "b2": delta.sum(0)}
        back = (delta @ w2.T) * (hidden > 0)
        grads["w1"] = z.T @ back
        grads["b1"] = back.sum(0)
        for key, value in params.items():
            g = grads[key]
            first[key] = 0.9 * first[key] + 0.1 * g
            second[key] = 0.999 * second[key] + 0.001 * g * g
            value -= LR * ((first[key] / (1 - 0.9 ** epoch))
                           / (np.sqrt(second[key] / (1 - 0.999 ** epoch)) + 1e-8))
    return {**params, "mu": mu, "sd": sd, "ym": ym, "ys": ys}


def network_predict(np, p, x):
    z = (x - p["mu"]) / p["sd"]
    out = np.maximum(0.0, z @ p["w1"] + p["b1"]) @ p["w2"] + p["b2"]
    return out.reshape(-1) * p["ys"] + p["ym"]


# ============================================================== the artifact
def export_onnx(np, p, path: pathlib.Path) -> str:
    """Write the graph and return its digest.

    The standardisation and the output rescaling are nodes IN the graph rather
    than folded into the weights. Folding is a legitimate optimisation and it
    would have made the exported bytes no longer contain the trained numbers —
    and 'the artifact is the model' is a claim worth keeping literally true.
    """
    from onnx import TensorProto, helper

    def tensor(name, values, shape):
        return helper.make_tensor(
            name, TensorProto.FLOAT, shape,
            np.asarray(values, dtype=np.float32).reshape(-1).tolist())

    width = p["w1"].shape[0]
    initialisers = [
        tensor("mu", p["mu"], [width]), tensor("sd", p["sd"], [width]),
        tensor("W1", p["w1"], list(p["w1"].shape)), tensor("b1", p["b1"], [HIDDEN]),
        tensor("W2", p["w2"], list(p["w2"].shape)), tensor("b2", p["b2"], [1]),
        tensor("ys", [p["ys"]], [1]), tensor("ym", [p["ym"]], [1]),
    ]
    nodes = [
        helper.make_node("Sub", ["features", "mu"], ["centred"]),
        helper.make_node("Div", ["centred", "sd"], ["scaled"]),
        helper.make_node("MatMul", ["scaled", "W1"], ["h_raw"]),
        helper.make_node("Add", ["h_raw", "b1"], ["h_bias"]),
        helper.make_node("Relu", ["h_bias"], ["h"]),
        helper.make_node("MatMul", ["h", "W2"], ["o_raw"]),
        helper.make_node("Add", ["o_raw", "b2"], ["o_scaled"]),
        helper.make_node("Mul", ["o_scaled", "ys"], ["o_wide"]),
        helper.make_node("Add", ["o_wide", "ym"], ["load_mw"]),
    ]
    graph = helper.make_graph(
        nodes, GRAPH_NAME,
        [helper.make_tensor_value_info("features", TensorProto.FLOAT,
                                       [1, width])],
        [helper.make_tensor_value_info("load_mw", TensorProto.FLOAT, [1, 1])],
        initializer=initialisers)
    model = helper.make_model(graph,
                              opset_imports=[helper.make_opsetid("", 18)])
    model.ir_version = 9
    path.write_bytes(model.SerializeToString())
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_onnx(np, path: pathlib.Path, rows) -> List[float]:
    """Score through onnxruntime — the ARTIFACT, not the numpy that made it."""
    import onnxruntime
    session = onnxruntime.InferenceSession(str(path),
                                           providers=["CPUExecutionProvider"])
    out = []
    for row in rows:
        answer = session.run(
            None, {"features": np.array([row], dtype=np.float32)})
        out.append(float(answer[0].reshape(-1)[0]))
    return out


# ================================================================ the kernels
LINEAR_KERNEL = {
    "runtime": "formula",
    "parameter_kind": "estimated_coefficients",
    "fit_procedure": "estimate",
    "deterministic": True,
    "entry": {"expression": "intercept + b_temperature * temperature_c + "
                            "b_hour_sin * hour_sin + b_hour_cos * hour_cos + "
                            "b_is_weekend * is_weekend",
              "target": "load_mw"},
    "input_schema": [{"name": n, "dtype": "numeric"} for n in NAMES],
    "parameter_schema": [
        {"name": "intercept", "dtype": "numeric"},
        {"name": "b_temperature", "dtype": "numeric"},
        {"name": "b_hour_sin", "dtype": "numeric"},
        {"name": "b_hour_cos", "dtype": "numeric"},
        {"name": "b_is_weekend", "dtype": "numeric"},
    ],
    "output_schema": [{"name": "load_mw", "dtype": "numeric", "unit": "MW"}],
}

NETWORK_KERNEL = {
    "runtime": "onnx",
    "parameter_kind": "learned_weights",
    "fit_procedure": "train",
    "deterministic": True,
    # `graph` is the ONNX graph's own name and is what the grammar requires of
    # this runtime; `input_names` names its single input tensor, which the
    # runtime fills from `input_schema` IN ORDER — which is why that order is
    # declared once, in FEATURES, and read from there everywhere.
    "entry": {"graph": GRAPH_NAME, "input_names": ["features"]},
    "input_schema": [{"name": n, "dtype": "numeric"} for n in NAMES],
    # No `parameter_schema`: a trained network's parameters are the artifact.
    # Listing 73 weights here would be a second, rotting copy of the bytes.
    "output_schema": [{"name": "load_mw", "dtype": "numeric", "unit": "MW"}],
}


def rows_for(np, features, load, hour) -> List[Dict[str, object]]:
    """Both clocks. Meter data is telemetered within the hour, so the gap is
    small — and stated rather than assumed, because 'small' is not 'zero' and
    a model reading an hour that had not closed yet reads a partial total."""
    out = []
    for i in range(len(features)):
        measured = WINDOW_FROM + i * 3600.0
        out.append({
            "entity_id": f"GRID-A-{i:05d}",
            "event_ts": measured,
            "ingest_ts": measured + 900.0,      # settled 15 minutes later
            **{name: float(features[i][k]) for k, name in enumerate(NAMES)},
            "load_mw": float(load[i]),
        })
    return out


# ================================================================== the build
def main() -> int:
    args = parse("Case study 13 — a trained load forecaster")
    out = pathlib.Path(args.out) if args.out else HERE
    say = Say("CASE STUDY 13 — A network that has to earn its opacity")

    try:
        import numpy as np
    except ImportError as exc:
        raise SystemExit(
            "this case study needs numpy: pip install numpy") from exc
    try:
        import onnx                                          # noqa: F401
    except ImportError as exc:
        raise SystemExit(
            "this case study builds an ONNX graph and needs the `onnx` "
            "authoring library:\n"
            "    pip install -r requirements-dev.txt\n"
            "MAYA itself needs only `onnxruntime`, which is in "
            "requirements.txt — `onnx` writes graphs, `onnxruntime` runs "
            "them.") from exc

    # ------------------------------------------------------------ 0. the data
    say.step("Generate the hours, and split off a held-out set")
    features, forecast, load, hour = world(np)
    x_tr, y_tr = features[:TRAIN_ROWS], load[:TRAIN_ROWS]
    x_te, y_te = features[TRAIN_ROWS:], load[TRAIN_ROWS:]
    f_te = forecast[TRAIN_ROWS:]
    say.engine(f"{TRAIN_ROWS} hours to train on, {HELDOUT_ROWS} held out. "
               f"Load is U-shaped in temperature: heating below 15C, cooling "
               f"above 22C, flat between")

    # -------------------------------------------- 1. the incumbent, first
    say.step("Fit the SIMPLER INCUMBENT first — it is the benchmark")
    say.did("T3's fibre asks for 'why the opacity was worth it, evidenced by "
            "a benchmark against a simpler incumbent'. So the incumbent is "
            "built first and registered as a model in its own right")
    beta = fit_linear(np, x_tr, y_tr)
    linear_held = linear_predict(np, beta, x_te)
    linear_r2, linear_rmse = r2(np, linear_held, y_te), rmse(np, linear_held, y_te)
    say.engine(f"linear:  R2 = {linear_r2:.4f}   RMSE = {linear_rmse:7.1f} MW")

    # ------------------------------------------------- 2. the network
    say.step("Train the network")
    trained = fit_network(np, x_tr, y_tr, seed=SEED_FIT)
    network_held = network_predict(np, trained, x_te)
    network_r2 = r2(np, network_held, y_te)
    network_rmse = rmse(np, network_held, y_te)
    say.engine(f"network: R2 = {network_r2:.4f}   RMSE = {network_rmse:7.1f} MW")
    improvement = 100.0 * (1.0 - network_rmse / linear_rmse)
    say.engine(f"RMSE improvement over the incumbent: {improvement:.1f}%")
    say.note("this is the number that justifies the opacity, and it had to be "
             "computed before anybody could claim it. Had it been 2%, the "
             "honest conclusion would be to ship the linear model")

    # ------------------------------------------------- 3. the artifact
    say.step("Export the graph, and score through the ARTIFACT")
    artifact = out / "load-forecast.onnx"
    digest = export_onnx(np, trained, artifact)
    say.engine(f"{artifact.name}: {artifact.stat().st_size} bytes, "
               f"sha256 {digest[:24]}...")
    through_onnx = run_onnx(np, artifact, x_te[:200])
    worst = max(abs(a - b) for a, b in zip(through_onnx, network_held[:200]))
    say.engine(f"onnxruntime against the numpy that trained it: worst "
               f"difference {worst:.6f} MW over 200 rows")
    say.did("checked rather than assumed. An export that silently drops a "
            "layer produces a model of exactly the same shape as a good one, "
            "and nothing downstream can tell")

    # ------------------------- 4. the same code, a different seed
    say.step("Retrain with a different seed and NOTHING else changed")
    refit = fit_network(np, x_tr, y_tr, seed=SEED_REFIT)
    refit_path = out / "load-forecast-refit.onnx"
    refit_digest = export_onnx(np, refit, refit_path)
    refit_rmse = rmse(np, network_predict(np, refit, x_te), y_te)
    say.engine(f"seed {SEED_FIT}: {digest[:24]}...  RMSE {network_rmse:.1f}")
    say.engine(f"seed {SEED_REFIT}: {refit_digest[:24]}...  RMSE {refit_rmse:.1f}")
    say.note(f"same data, same code, same architecture — different bytes. "
             f"Two models that perform within {abs(refit_rmse - network_rmse):.1f} "
             f"MW of each other and are NOT the same model. For a T3 the "
             f"digest is the only reliable answer to 'is this the one we "
             f"approved?'")
    refit_path.unlink(missing_ok=True)

    # ------------------------- 5. observed weather versus forecast weather
    say.step("Score the held-out set on FORECAST temperature instead")
    forecast_pred = network_predict(np, trained, f_te)
    forecast_r2 = r2(np, forecast_pred, y_te)
    forecast_rmse = rmse(np, forecast_pred, y_te)
    say.engine(f"on observed temperature: R2 = {network_r2:.4f}  "
               f"RMSE = {network_rmse:7.1f} MW")
    say.engine(f"on forecast temperature: R2 = {forecast_r2:.4f}  "
               f"RMSE = {forecast_rmse:7.1f} MW")
    say.note(f"the backtest is run on weather that HAPPENED and the model is "
             f"deployed on weather that was PREDICTED. That is "
             f"{100 * (forecast_rmse / network_rmse - 1):.0f}% more error than "
             f"the validation report will say, and it is a property of the "
             f"deployment rather than of the model")

    # ================================================== now the register
    maya = connect(args)
    say.step("Make sure the people exist")
    people = ensure_cast(maya, args.url)

    say.step("Register the features")
    for name, description in FEATURES + [
            ("load_mw", "system load for the hour, megawatts")]:
        attempt(name, lambda n=name, d=description: maya.features.define(
            name=n, entity=ENTITY, dtype="numeric", description=d,
            owner="person/a.mehta", source_system="grid telemetry and the "
                                                  "meteorological feed"))

    say.step("Load the hours")
    attempt("the view", lambda: maya.features.create_view(
        name=VIEW, entity=ENTITY, owner="person/a.mehta",
        features=NAMES + ["load_mw"],
        description="hourly system load and its drivers. event_ts is the hour "
                    "the reading describes; ingest_ts is fifteen minutes "
                    "later, when settlement closed it. temperature_c is the "
                    "OBSERVED temperature — production reads a forecast."))
    load_once(maya, VIEW, rows_for(np, features, load, hour))

    say.step("Declare the featureset")
    attempt(FEATURESET, lambda: maya.featuresets.define(
        name=FEATURESET, entity=ENTITY,
        slots={**{n: "numeric" for n in NAMES}, "load_mw": "numeric"},
        description="the four drivers and the load they explain"))
    fs_version = ensure_filled(
        maya, FEATURESET, {**{n: n for n in NAMES}, "load_mw": "load_mw"})

    # ------------------------------------------- the incumbent, registered
    say.step("Register the INCUMBENT as a model of its own")
    incumbent_set = _register_incumbent(maya, people, say, np, beta,
                                        fs_version, linear_r2, linear_rmse)

    # ------------------------------------------------ the network, registered
    say.step("Store the artifact in MAYA, by content address")
    stored = attempt("the ONNX graph", lambda: maya.artifacts.put(
        artifact, format="onnx"))
    if stored:
        say.maya(f"digest {str(stored.get('digest'))[:24]}..., "
                 f"{stored.get('size')} bytes, stored={stored.get('stored')}")
        say.did("stored by what it IS. Upload the same bytes again and the "
                "store says stored=false rather than keeping a second copy")

    say.step("Register the network as a model")
    attempt("the model", lambda: maya.models.register(
        urn=URN, name="Hourly load forecast network",
        model_class="grid.load.network", domain="energy",
        owner="person/j.okafor", legal_entity="LE-UK-01",
        purpose="forecasting system load an hour ahead, to size reserve and "
                "schedule dispatch"))

    say.step("Register the network's version AGAINST that digest")
    say.did("the digest is the version's identity. MAYA does not need the uri: "
            "the store is the authority on its own contents and fills in "
            "where the bytes are, how big they are and what format they are")
    version_record = ensure_version(
        maya, SHORT, semver=SEMVER, kernel=NETWORK_KERNEL,
        artifact_digest=f"sha256:{digest}")
    say.maya(f"trainability class {version_record.get('trainability_class')} "
             f"— learned_weights inhabited by train")

    assessed = attempt("its risk tier", lambda: maya.models.assess(
        SHORT, exposure=4.0e8, purpose_class="risk_management",
        feature_count=len(NAMES), uses_alternative_data=False,
        # Declared honestly: nobody can say why the network produced this
        # number and not another.
        interpretable=False), already="already tiered")
    if assessed:
        say.maya(str(assessed.get("rationale") or assessed.get("tier")))

    say.step("Relate the two models")
    attempt("benchmark_for", lambda: maya.models.relate(
        from_urn=BASE_URN, to_urn=URN, kind="benchmark_for",
        note="The linear model is the incumbent the network had to beat. It "
             "is a BENCHMARK and not a dependency: the network does not read "
             "its output, so this edge deliberately does not propagate in a "
             "blast radius."), already="already related")

    say.step("Approve the version")
    _ok, tier = approve_version(
        maya, people, urn=URN, semver=SEMVER,
        statement="The opacity is justified by a measured benchmark against "
                  "the registered linear incumbent, on a held-out set. The "
                  "export was checked against the training code and the "
                  "forecast-weather degradation is quantified on the set.")
    say.maya(f"risk tier {tier}")

    say.step("Put the record in force")
    put_record_in_force(maya, people, urn=URN,
                        note="Hourly load forecaster, owned by system "
                             "operations.")

    say.step("Grant the standing entitlements")
    grant = attempt("train, in the lab", lambda: maya.warrants.grant(
        urn=URN, principal="person/a.mehta",
        declared_use="model_development", environment="lab"))
    grant_id = (grant or {}).get("id") or _existing_grant(maya, URN, "lab")
    attempt("forecast, in production", lambda: maya.warrants.grant(
        urn=URN, principal="person/a.mehta",
        declared_use="risk_management", environment="prod"))

    say.step("Ask MAYA for the TRAINING warrant")
    fit_warrant = maya.warrants.for_fitting(
        urn=f"{URN}@{SEMVER}", principal="person/a.mehta",
        featureset=FEATURESET, featureset_version=fs_version,
        window={"from": WINDOW_FROM, "to": AS_OF}, as_of=AS_OF)
    say.maya(f"training warrant {fit_warrant.get('warrant_id')}")
    save_json(out / "warrant-training.json", fit_warrant,
              what="the training warrant")

    say.step("Deliver the parameter set — which is the DIGEST, not the weights")
    recorded = attempt("the trained parameters", lambda: maya.parameters.record(
        urn=URN, semver=SEMVER, name="net-2026-q1", kind="learned_weights",
        values={"artifact_digest": f"sha256:{digest}",
                "artifact_bytes": artifact.stat().st_size,
                "architecture": f"dense {len(NAMES)}-{HIDDEN}-1, ReLU",
                "trainable_parameters": int(
                    trained["w1"].size + trained["b1"].size
                    + trained["w2"].size + trained["b2"].size)},
        provenance="fitted", warrant_id=grant_id,
        featureset=FEATURESET, featureset_version=fs_version,
        window={"from": WINDOW_FROM, "to": AS_OF}, as_of=AS_OF,
        diagnostics={
            # THE SOUNDNESS EVIDENCE T3's FIBRE ASKS FOR.
            "benchmark_against_incumbent": {
                "incumbent": BASE_URN,
                "incumbent_parameter_set": incumbent_set,
                "held_out_hours": HELDOUT_ROWS,
                "incumbent_r2": round(linear_r2, 6),
                "incumbent_rmse_mw": round(linear_rmse, 3),
                "network_r2": round(network_r2, 6),
                "network_rmse_mw": round(network_rmse, 3),
                "rmse_improvement_pct": round(improvement, 2),
                "why_the_opacity_is_worth_it":
                    "Load is U-shaped in temperature — heating below roughly "
                    "15C, cooling above roughly 22C, flat between. A linear "
                    "model must choose one slope for a relationship that has "
                    "two, and the error it makes is structure rather than "
                    "noise. The network recovers the shape; the measured "
                    f"improvement is {improvement:.1f}% of RMSE.",
            },
            "export_verified": {
                "checked_rows": 200,
                "worst_absolute_difference_mw": round(worst, 8),
                "note": "onnxruntime scoring the exported graph, against the "
                        "numpy that trained it. The residual is float32 "
                        "rounding.",
            },
            "training": {"seed": SEED_FIT, "epochs": EPOCHS,
                         "learning_rate": LR, "optimiser": "adam",
                         "hidden_units": HIDDEN,
                         "training_hours": TRAIN_ROWS},
            "reproducibility":
                f"Retraining on the same data with seed {SEED_REFIT} produces "
                f"a different artifact — a different digest, and RMSE "
                f"{refit_rmse:.1f} against {network_rmse:.1f}. The seed is "
                f"recorded because without it 'the same model' is not a thing "
                f"anybody can reproduce, and the DIGEST is what identifies "
                f"which one was approved.",
            # The limitation, measured rather than mentioned.
            "limitation": {
                "backtested_on": "observed temperature",
                "deployed_on": "forecast temperature",
                "forecast_error_sd_c": FORECAST_SD_C,
                "rmse_mw_on_observed": round(network_rmse, 3),
                "rmse_mw_on_forecast": round(forecast_rmse, 3),
                "degradation_pct": round(
                    100 * (forecast_rmse / network_rmse - 1), 1),
                "statement":
                    "Every performance figure above is measured on the "
                    "temperature that occurred. Production reads a day-ahead "
                    "forecast, and on the same held-out hours the error is "
                    f"{100 * (forecast_rmse / network_rmse - 1):.0f}% higher. "
                    "This is a property of the deployment and not of the "
                    "model, and it cannot be improved by retraining.",
            },
            "not_measured": "subgroup performance by season and by weekday, "
                            "and stability under input perturbation — both "
                            "asked for by the T3 fibre and neither done here",
        },
        note="dense network, benchmarked against the registered incumbent"))
    set_id = (recorded or {}).get("id") or (recorded or {}).get("parameter_set_id")

    say.step("A different person accepts it")
    if set_id:
        attempt("accepted by s.iqbal (second line)",
                lambda: people["s.iqbal"].parameters.review(
                    set_id, accept=True,
                    note=f"Accepted. The benchmark against "
                         f"{BASE_SHORT} is on the set and the "
                         f"{improvement:.0f}% RMSE improvement justifies an "
                         f"uninterpretable model here. Note the forecast-"
                         f"weather degradation: operational tolerances must "
                         f"be set from the forecast figure, not the backtest."),
                already="already reviewed")

    say.step("Ask MAYA for the EXECUTION warrant")
    run_warrant = None
    try:
        run_warrant = maya.warrants.resolve(
            urn=f"{URN}@{SEMVER}", principal="person/a.mehta",
            declared_use="risk_management", environment="prod", verb="score")
        say.maya(f"execution warrant {run_warrant.get('warrant_id')}")
        block = (run_warrant.get("realisation") or {}).get("artifact") or {}
        if block:
            say.did("the warrant does not carry the model. It carries what an "
                    "engine needs to FETCH it and check it is the right one")
            print(f"        {'digest':>18}  {str(block.get('digest'))[:38]}...")
            print(f"        {'format':>18}  {block.get('format')}")
            print(f"        {'size':>18}  {block.get('size')} bytes")
            print(f"        {'held by MAYA':>18}  {block.get('held_by_maya')}")
            print(f"        {'executes on load':>18}  "
                  f"{block.get('executes_on_load')}")
            say.did("`executes_on_load: false` is a security fact, not a "
                    "performance one. An ONNX graph is data an engine "
                    "interprets; a pickle or a torchscript bundle is CODE, and "
                    "loading one in a scoring process runs whatever it "
                    "contains. MAYA records which kind it just handed over")
        save_json(out / "warrant-execution.json", run_warrant,
                  what="the execution warrant")
    except Exception as exc:
        say.note(f"execution warrant not issued: {exc}")

    profile: List[Tuple[float, float, float]] = []
    if run_warrant is not None:
        say.step("Forecast across the temperature range — LOCALLY, through ONNX")
        say.did("the U-shape is the reason the network exists, so here it is, "
                "read out of the model rather than asserted")
        grid = [[t, math.sin(2 * math.pi * 18 / 24), math.cos(2 * math.pi * 18 / 24), 0.0]
                for t in (-5.0, 0.0, 5.0, 10.0, 15.0, 18.0, 22.0, 26.0, 30.0, 35.0)]
        predicted = run_onnx(np, artifact, grid)
        straight = linear_predict(np, beta, np.array(grid))
        print(f"        {'temp C':>8}{'network MW':>13}{'linear MW':>12}"
              f"{'linear error':>14}")
        for row, net, lin in zip(grid, predicted, straight):
            truth = true_load(row[0], 18.0, 0.0)
            profile.append((row[0], net, float(lin)))
            print(f"        {row[0]:>8.0f}{net:>13.0f}{lin:>12.0f}"
                  f"{lin - truth:>+14.0f}")
        say.note("the linear model is wrong at both ends and right in the "
                 "middle, which is exactly what one slope does to a U")

    say.step("Write the LaTeX specification")
    path = write_document(out, version_record, digest, artifact,
                          linear_r2, linear_rmse, network_r2, network_rmse,
                          improvement, forecast_r2, forecast_rmse, worst,
                          refit_digest, refit_rmse, profile, fit_warrant,
                          run_warrant, tier)
    print(f"\n    LaTeX written to {path}")

    print(f"\n{'=' * 78}")
    print(f"Done. The opacity was earned — {improvement:.0f}% of the "
          f"incumbent's error —")
    print("and the record says so with a number rather than an adjective.")
    print(f"{'=' * 78}")
    return 0


# ------------------------------------------------------------ the incumbent
def _register_incumbent(maya, people, say, np, beta, fs_version,
                        linear_r2, linear_rmse) -> Optional[str]:
    """The simpler model, registered properly. It is EVIDENCE, not a slide.

    A benchmark that lives in a validation document is a claim; a benchmark
    that is a registered, approved, parameterised model is a thing somebody can
    re-run next year and disagree with.
    """
    attempt("the incumbent model", lambda: maya.models.register(
        urn=BASE_URN, name="Hourly load — linear incumbent",
        model_class="grid.load.linear", domain="energy",
        owner="person/j.okafor", legal_entity="LE-UK-01",
        purpose="the simpler model the network is required to beat"))
    ensure_version(maya, BASE_SHORT, semver=SEMVER, kernel=LINEAR_KERNEL)
    attempt("its risk tier", lambda: maya.models.assess(
        BASE_SHORT, exposure=4.0e8, purpose_class="risk_management",
        feature_count=len(NAMES), uses_alternative_data=False,
        interpretable=True), already="already tiered")
    approve_version(maya, people, urn=BASE_URN, semver=SEMVER,
                    statement="Ordinary least squares on four declared "
                              "regressors. Registered as the benchmark.")
    put_record_in_force(maya, people, urn=BASE_URN,
                        note="Linear incumbent, kept in the register because "
                             "a benchmark nobody can re-run is not evidence.")
    base_grant = attempt("estimate, in the lab", lambda: maya.warrants.grant(
        urn=BASE_URN, principal="person/a.mehta",
        declared_use="model_development", environment="lab"))
    base_grant_id = ((base_grant or {}).get("id")
                     or _existing_grant(maya, BASE_URN, "lab"))
    recorded = attempt("the incumbent's coefficients",
                       lambda: maya.parameters.record(
                           urn=BASE_URN, semver=SEMVER, name="ols-2026-q1",
                           kind="estimated_coefficients",
                           values={"intercept": round(float(beta[0]), 6),
                                   "b_temperature": round(float(beta[1]), 6),
                                   "b_hour_sin": round(float(beta[2]), 6),
                                   "b_hour_cos": round(float(beta[3]), 6),
                                   "b_is_weekend": round(float(beta[4]), 6)},
                           provenance="fitted", warrant_id=base_grant_id,
                           featureset=FEATURESET, featureset_version=fs_version,
                           window={"from": WINDOW_FROM, "to": AS_OF},
                           as_of=AS_OF,
                           diagnostics={
                               "r_squared_held_out": round(linear_r2, 6),
                               "rmse_mw_held_out": round(linear_rmse, 3),
                               "limitation":
                                   "Linear in temperature, and the load "
                                   "response is not. One slope is fitted to a "
                                   "relationship with two, so the model is "
                                   "biased low in cold weather and in hot "
                                   "weather and right in between.",
                           },
                           note="the benchmark the network must beat"))
    set_id = (recorded or {}).get("id") or (recorded or {}).get("parameter_set_id")
    if set_id:
        attempt("accepted by s.iqbal",
                lambda: people["s.iqbal"].parameters.review(
                    set_id, accept=True,
                    note="Accepted as the registered benchmark."),
                already="already reviewed")
    say.maya(f"the incumbent is registered at {BASE_SHORT} — a model a "
             f"reviewer can re-run, not a number in a document")
    return set_id


def _existing_grant(maya: Maya, urn: str, environment: str) -> Optional[str]:
    for row in (maya.call("GET", "/warrants") or {}).get("warrants", []):
        if row.get("model_urn") == urn and row.get("environment") == environment:
            return row.get("id")
    return None


def write_document(out, version_record, digest, artifact, linear_r2,
                   linear_rmse, network_r2, network_rmse, improvement,
                   forecast_r2, forecast_rmse, worst, refit_digest, refit_rmse,
                   profile, fit_warrant, run_warrant, tier):
    blocks = [
        r"\section{What this model is}",
        r"A dense two-layer network forecasting hourly system load from four "
        r"drivers: temperature, the two components of the daily cycle, and a "
        r"weekend indicator. MAYA classifies it \textbf{T3} --- "
        r"`learned\_weights` inhabited by `train` --- and the parameters are "
        r"not a row anybody reads. They are an ONNX graph, held by content "
        r"address.",

        r"\section{Why the opacity was worth it}",
        r"MAYA's fibre for a machine-learned model asks for soundness as "
        r"\emph{``why the opacity was worth it, evidenced by a benchmark "
        r"against a simpler incumbent''}. So the incumbent is a registered, "
        r"approved, parameterised model in its own right --- not a number in a "
        r"validation document --- and the comparison is a diagnostic on this "
        r"model's parameter set.",
        table([["Linear incumbent", f"{linear_r2:.4f}", f"{linear_rmse:.1f}"],
               ["This network", f"{network_r2:.4f}", f"{network_rmse:.1f}"]],
              header=["Model", "$R^2$ held out", "RMSE (MW)"], spec="lrr"),
        rf"The network removes \textbf{{{improvement:.1f}\%}} of the "
        rf"incumbent's error, and the reason is physical rather than "
        rf"statistical: load is \textbf{{U-shaped in temperature}} --- heating "
        rf"below roughly 15\textdegree C, cooling above roughly "
        rf"22\textdegree C, flat between. A linear model must choose one slope "
        rf"for a relationship that has two, so its error is structure and not "
        rf"noise. Had the improvement been two percent, the honest conclusion "
        rf"would have been to ship the incumbent.",
        table([[f"{t:.0f}", f"{net:.0f}", f"{lin:.0f}"]
               for t, net, lin in profile],
              header=["Temperature (\\textdegree C)", "Network (MW)",
                      "Incumbent (MW)"], spec="rrr"),

        r"\section{The artifact is the model}",
        table([["Format", "ONNX, opset 18"],
               ["Bytes", f"{artifact.stat().st_size:,}"],
               ["Digest", r"\texttt{" + latex_escape(digest[:48]) + r"\dots}"],
               ["Trained with seed", str(SEED_FIT)],
               ["Refit with seed", str(SEED_REFIT)],
               ["Refit digest",
                r"\texttt{" + latex_escape(refit_digest[:48]) + r"\dots}"],
               ["Refit RMSE (MW)", f"{refit_rmse:.1f}"]],
              header=["Field", "Value"], spec="ll"),
        r"Retraining on the same data with the same code and a different seed "
        r"produces a \emph{different artifact}: different bytes, a different "
        r"digest, and a model performing within a megawatt or so of the first. "
        r"They are not the same model, and no amount of describing the "
        r"architecture distinguishes them. \textbf{For a T3 the digest is the "
        r"only reliable answer to ``is this the one we approved?''}",
        rf"The export was verified rather than assumed: scoring the graph "
        rf"through `onnxruntime` and comparing against the training code over "
        rf"200 held-out rows, the worst absolute difference was "
        rf"{worst:.6f}\,MW --- float32 rounding. An export that silently drops "
        rf"a layer produces a model of exactly the same shape as a good one.",

        r"\section{Backtested on weather that happened}",
        table([["Observed temperature", f"{network_r2:.4f}",
                f"{network_rmse:.1f}"],
               ["Day-ahead forecast temperature", f"{forecast_r2:.4f}",
                f"{forecast_rmse:.1f}"]],
              header=["Scored on", "$R^2$", "RMSE (MW)"], spec="lrr"),
        rf"Every performance figure in the section above is measured on the "
        rf"temperature that \emph{{occurred}}. Production reads a day-ahead "
        rf"forecast, and on the same held-out hours the error is "
        rf"\textbf{{{100 * (forecast_rmse / network_rmse - 1):.0f}\% higher}}. "
        rf"This is a property of the deployment rather than of the model and "
        rf"cannot be improved by retraining --- so operational tolerances "
        rf"belong on the forecast figure and not on the backtest. It is "
        rf"recorded as a measured quantity because a limitation without a "
        rf"number is a sentence nobody acts on.",

        r"\section{What was not done}",
        r"Named, because the same fibre asks for them: subgroup performance by "
        r"season and by weekday, and stability under input perturbation. "
        r"Neither is measured here, and the parameter set says so under "
        r"`not\_measured` rather than leaving the omission to be discovered.",

        r"\section{Governance}",
        table([["Model URN", latex_escape(URN)],
               ["Benchmark", latex_escape(BASE_URN) + " (`benchmark\\_for`)"],
               ["Version", latex_escape(str(version_record.get("semver", "—")))],
               ["Trainability class",
                latex_escape(str(version_record.get("trainability_class", "—")))],
               ["Risk tier", str(tier)],
               ["Interpretable", "declared False"],
               ["Training warrant",
                latex_escape(str((fit_warrant or {}).get("warrant_id", "—")))],
               ["Execution warrant",
                latex_escape(str((run_warrant or {}).get("warrant_id",
                                                         "not issued")))]],
              header=["Field", "Value"], spec="ll"),
    ]
    return document(path=out / "load-forecast-specification.tex",
                    title="Hourly Load Forecast Network --- Model "
                          "Specification",
                    subtitle=latex_escape("Registered in MAYA · " + SHORT),
                    blocks=blocks)


if __name__ == "__main__":
    raise SystemExit(main())
