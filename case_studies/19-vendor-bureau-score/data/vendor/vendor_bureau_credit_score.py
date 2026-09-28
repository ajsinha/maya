"""BureauScore 4.1 -- probability of default within twelve months. Vendor-supplied."""

import math

_W = (-3.1, 2.4, 0.55, -0.06, 0.18)


class Model:
    def fit(self, X, y, ctx):
        return {}  # delivered fitted; nothing to train

    def predict(self, X, params, ctx):
        out = []
        for u, d, a, q in zip(
            X["utilisation"], X["delinquencies"], X["age_of_file"], X["inquiries"]
        ):
            z = _W[0] + _W[1] * u + _W[2] * d + _W[3] * a + _W[4] * q
            out.append(1.0 / (1.0 + math.exp(-z)))
        return {"score": out}
