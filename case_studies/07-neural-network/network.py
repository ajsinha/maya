"""
The desk's implementation of the fraud network: the file MAYA is given as the artifact.

This is one file, used twice. ``fit_parameters.py`` imports it to train, and
``setup_model.py`` uploads *these bytes* to MAYA as the model version's code artifact, so
the six-rung ladder runs the same lines the desk ran and the artifact hash MAYA stores is
the sha256 of this file. Keeping one implementation is deliberate: a black box has no
closed form to compare code against, so the least a study can do is not have two versions
of the code to disagree with each other.

It conforms to MAYA's model interface (§8.3): a class ``Model`` with ``fit(X, y, ctx)``
and ``predict(X, params, ctx)``. ``X`` is a mapping of column name to array — the sandbox
hands over lists, the desk hands over numpy, and ``np.asarray`` takes both. ``params`` is
the parameter set: eight arrays, 209 numbers, and nothing else. There is no file to open
and no state on the instance, because a parameter that is not in the parameter set is a
parameter nobody approved.

The architecture is fixed here and stated identically in the specification document:

    6 inputs -> 12 tanh -> 8 tanh -> 1 sigmoid

trained by plain mini-batch gradient descent on the Bernoulli log-likelihood, He-normal
initialisation, a fixed epoch count and **no early stopping** — so nothing the fit does
depends on the validation partition, and the only source of randomness is ``ctx.seed``.

Copyright (c) 2026 Ashutosh Sinha.  All rights reserved.
"""

from __future__ import annotations

from typing import Any

import numpy as np

# The column order is part of the model: the weight matrix's first row belongs to
# amount_ratio, and a caller that reorders the columns gets a different model with the
# same parameters. Stating it here is what stops that.
COLUMNS = (
    "amount_ratio",
    "foreign_share",
    "night_share",
    "velocity_ratio",
    "tenure_months",
    "prior_disputes",
)
HIDDEN = (12, 8)
EPOCHS = 80
BATCH = 256
LEARNING_RATE = 0.15


def design(X: Any) -> np.ndarray:
    """The six drivers, in the declared order, as a float matrix."""
    return np.column_stack([np.asarray(X[name], dtype=float) for name in COLUMNS])


def initial_parameters(seed: int) -> dict[str, np.ndarray]:
    """The weights before any data: He-normal from ``seed``, zero biases, no scaling.

    A network's parameters are only reproducible from a seed, so the seed is declared in
    the warrant and this function is what it means. The standardisation is the identity
    until it is fitted, which is why ``x_mean`` is zero and ``x_scale`` is one here.
    """
    rng = np.random.default_rng(seed)
    widths = (len(COLUMNS), *HIDDEN, 1)
    params: dict[str, np.ndarray] = {}
    for layer, (fan_in, fan_out) in enumerate(zip(widths, widths[1:]), start=1):
        params[f"W{layer}"] = rng.normal(0.0, np.sqrt(2.0 / fan_in), (fan_in, fan_out))
        params[f"b{layer}"] = np.zeros(fan_out)
    params["x_mean"] = np.zeros(len(COLUMNS))
    params["x_scale"] = np.ones(len(COLUMNS))
    return params


def forward(
    matrix: np.ndarray, params: dict[str, Any]
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Both hidden activations and the output probability, for one batch or a whole book."""
    standardised = (matrix - np.asarray(params["x_mean"], dtype=float)) / np.asarray(
        params["x_scale"], dtype=float
    )
    first = np.tanh(standardised @ np.asarray(params["W1"], dtype=float) + np.asarray(params["b1"]))
    second = np.tanh(first @ np.asarray(params["W2"], dtype=float) + np.asarray(params["b2"]))
    logit = second @ np.asarray(params["W3"], dtype=float) + np.asarray(params["b3"])
    return first, second, 1.0 / (1.0 + np.exp(-logit))


class Model:
    """The fraud network, to MAYA's model interface."""

    def fit(self, X: Any, y: Any, ctx: Any) -> dict[str, Any]:
        """Train from ``ctx.seed`` and return the parameter set, and nothing else.

        Mini-batch gradient descent on the Bernoulli log-likelihood. The only randomness
        is the initialisation and the batch order, both drawn from one generator seeded
        with ``ctx.seed``, so two fits of the same rows with the same seed are identical.
        """
        matrix = design(X)
        target = np.asarray(y, dtype=float).reshape(-1, 1)
        params = initial_parameters(int(ctx.seed))
        params["x_mean"] = matrix.mean(axis=0)
        params["x_scale"] = matrix.std(axis=0)
        rng = np.random.default_rng(int(ctx.seed))
        rows = len(matrix)
        for _ in range(EPOCHS):
            order = rng.permutation(rows)
            for start in range(0, rows, BATCH):
                batch = order[start : start + BATCH]
                block, wanted = matrix[batch], target[batch]
                first, second, out = forward(block, params)
                standardised = (block - params["x_mean"]) / params["x_scale"]
                # d(-loglik)/d(logit) for a sigmoid output is (p - y), per row
                delta3 = (out - wanted) / len(batch)
                delta2 = (delta3 @ params["W3"].T) * (1.0 - second**2)
                delta1 = (delta2 @ params["W2"].T) * (1.0 - first**2)
                params["W3"] = params["W3"] - LEARNING_RATE * (second.T @ delta3)
                params["b3"] = params["b3"] - LEARNING_RATE * delta3.sum(axis=0)
                params["W2"] = params["W2"] - LEARNING_RATE * (first.T @ delta2)
                params["b2"] = params["b2"] - LEARNING_RATE * delta2.sum(axis=0)
                params["W1"] = params["W1"] - LEARNING_RATE * (standardised.T @ delta1)
                params["b1"] = params["b1"] - LEARNING_RATE * delta1.sum(axis=0)
        return params

    def predict(self, X: Any, params: dict[str, Any], ctx: Any) -> np.ndarray:
        """The probability that each card-day is later confirmed as fraud."""
        del ctx  # the forward pass is a pure function of the inputs and the parameters
        return forward(design(X), params)[2].ravel()
