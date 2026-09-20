"""
The book this case study ingests, written to ``data/`` as CSV.

    .venv/bin/python case_studies/07-neural-network/make_data.py

The files are committed, so the study runs with no generation step and a reader can
open the data and see exactly what MAYA was given. The recipe matters more here than in
most studies, because the study's central claim is that a neural network beats a
logistic scorecard on this data, and that claim is only worth anything if the reason is
visible: the label depends on the features through **conjunctions**, and a conjunction is
the thing a linear model cannot represent.

Three feeds, on the grain a card-fraud desk actually monitors — one row per card per day:

* ``card_day_activity.csv`` — the authorisation summary, cut one day after the day it
  describes, so every value is *known* the following morning;
* ``card_profile.csv`` — the customer master extract, a month-end file delivered ten days
  later, carried forward as-of rather than resampled;
* ``fraud_confirmed.csv`` — whether that card-day was later confirmed as fraud, which
  cannot be known until the dispute and chargeback window has closed, 45 days later.

The truth underneath is a **compromise process**, not a formula. A card-day is
compromised with a probability that depends on tenure (new cards and long-dormant ones
are the targeted ones) and on the card's dispute history. A compromised day is worked one
of two ways, and the two look like opposites:

| | ``amount_ratio`` | ``velocity_ratio`` | ``foreign_share`` | ``night_share`` |
| --- | --- | --- | --- | --- |
| cash-out abroad | **4.7x** the card's usual largest authorisation | low, one big purchase | high | as usual |
| card testing | **0.17x** — micro-authorisations of a few pence | **4.7x**, a burst | as usual | high |
| an innocent day | ~1x, sometimes a big-ticket 4x day | ~1x, sometimes a busy 4x day | high for the 30% who travel | high for the 25% who shop at night |

So `amount_ratio` alone is worthless — fraud sits at *both* ends of it — and a big-ticket
day, a busy day, a trip abroad and a night owl are all innocent on their own. Only the
*combinations* are fraud: large **and** foreign, or tiny **and** fast. A logistic
regression in these six drivers must give `amount_ratio` one coefficient for both fraud
modes and cannot; a network with two hidden layers can. That is the whole of the
justification for accepting an unreadable model, and the study reports both AUCs.

Nothing in the feeds says who travels, who shops at night, or which day was compromised.
Those are latent, exactly as they are in a real book.

Copyright (c) 2026 Ashutosh Sinha.  All rights reserved.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
CARDS = 300
FIRST_DAY = dt.date(2025, 3, 1)
DAYS = 45  # 2025-03-01 .. 2025-04-14
PROFILE_DATES = (dt.date(2025, 2, 28), dt.date(2025, 3, 31))
SEED = 20260919


def sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-x))


def generate() -> dict[str, pd.DataFrame]:
    rng = np.random.default_rng(SEED)
    days = [FIRST_DAY + dt.timedelta(days=d) for d in range(DAYS)]
    cards = [f"C{n:05d}" for n in range(CARDS)]
    n = CARDS * DAYS

    # per card, stable over the window: what the profile file reports, and two habits it
    # does not report
    tenure = rng.integers(2, 145, CARDS)
    disputes = rng.poisson(0.25, CARDS)
    traveller = rng.random(CARDS) < 0.30
    night_owl = rng.random(CARDS) < 0.25

    tenure_d = np.repeat(tenure, DAYS).astype(float)
    disputes_d = np.repeat(disputes, DAYS).astype(float)
    traveller_d = np.repeat(traveller, DAYS)
    owl_d = np.repeat(night_owl, DAYS)

    # who gets compromised: new cards, long-dormant cards, and cards with a history
    risk = sigmoid(
        -3.5
        + 1.2 * sigmoid(-(tenure_d - 9.0) / 3.0)
        + 1.0 * sigmoid((tenure_d - 115.0) / 8.0)
        + 0.5 * disputes_d
    )
    compromised = rng.random(n) < risk
    testing = compromised & (rng.random(n) < 0.5)
    cashout = compromised & ~testing

    # innocent behaviour, including the days that look like half of a fraud
    big_ticket = rng.random(n) < 0.15
    busy = rng.random(n) < 0.15
    abroad = traveller_d & (rng.random(n) < 0.5)
    amount = np.where(
        big_ticket, np.exp(rng.normal(1.45, 0.35, n)), np.exp(rng.normal(0.0, 0.40, n))
    )
    velocity = np.where(busy, np.exp(rng.normal(1.40, 0.30, n)), np.exp(rng.normal(0.0, 0.35, n)))
    foreign = np.where(abroad, rng.beta(3.5, 1.4, n), rng.beta(0.28, 3.2, n))
    night = np.where(owl_d, rng.beta(3.0, 2.0, n), rng.beta(0.35, 3.4, n))

    k = int(cashout.sum())  # one large purchase, abroad
    amount[cashout] = np.exp(rng.normal(1.55, 0.35, k))
    foreign[cashout] = rng.beta(3.5, 1.4, k)
    velocity[cashout] = np.exp(rng.normal(-0.35, 0.30, k))

    k = int(testing.sum())  # a burst of micro-authorisations, at night
    amount[testing] = np.exp(rng.normal(-1.75, 0.30, k))
    velocity[testing] = np.exp(rng.normal(1.55, 0.30, k))
    night[testing] = rng.beta(3.0, 1.6, k)

    auths = np.maximum(1, rng.poisson(np.clip(3.0 * velocity, 0.3, None)))
    # the desk confirms almost every compromise once the chargeback lands, and a handful of
    # innocent days are confirmed too: a real label is not the truth, it is a decision
    confirmed = (compromised & (rng.random(n) < 0.90)) | (~compromised & (rng.random(n) < 0.003))

    activity, outcome = [], []
    row = 0
    for card in cards:
        for day in days:
            activity.append(
                {
                    "date": day,
                    "card": card,
                    "amount_ratio": round(float(amount[row]), 4),
                    "foreign_share": round(float(foreign[row]), 4),
                    "night_share": round(float(night[row]), 4),
                    "velocity_ratio": round(float(velocity[row]), 4),
                    "auth_count": int(auths[row]),
                    "kt": f"{day + dt.timedelta(days=1)}T06:00:00Z",
                }
            )
            outcome.append(
                {
                    "date": day,
                    "card": card,
                    "fraud_confirmed": int(confirmed[row]),
                    "kt": f"{day + dt.timedelta(days=45)}T00:00:00Z",
                }
            )
            row += 1

    profile = [
        {
            "date": date,
            "card": card,
            "tenure_months": int(tenure[i]) + months,
            "prior_disputes": int(disputes[i]),
            "kt": f"{date + dt.timedelta(days=10)}T07:00:00Z",
        }
        for months, date in enumerate(PROFILE_DATES)
        for i, card in enumerate(cards)
    ]
    return {
        "card_day_activity": pd.DataFrame(activity),
        "card_profile": pd.DataFrame(profile),
        "fraud_confirmed": pd.DataFrame(outcome),
    }


def main() -> int:
    DATA.mkdir(exist_ok=True)
    for name, frame in generate().items():
        path = DATA / f"{name}.csv"
        frame.to_csv(path, index=False, lineterminator="\n")
        size = path.stat().st_size / 1e6
        print(f"wrote {path.relative_to(HERE.parent.parent)}  {len(frame):,} rows, {size:.1f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
