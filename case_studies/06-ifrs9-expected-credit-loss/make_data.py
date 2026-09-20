"""
The two feeds this case study ingests, written to ``data/`` as CSV.

    .venv/bin/python case_studies/06-ifrs9-expected-credit-loss/make_data.py

Expected credit loss is a product of three estimates, so the data has to support three
fits and one realised outcome to measure the product against.

* ``exposures.csv`` — the monthly book: the drawn balance, the committed limit, the
  collateral securing it, how many months the account is in arrears, and the probability
  of default recorded **at origination**, which IFRS 9 needs because a *significant
  increase* in credit risk is a comparison against origination and not against a
  threshold. Cut three business days after month end.
* ``outcomes.csv`` — what happened over the following twelve months: whether the account
  defaulted, the loss rate realised on it if it did, and the money actually lost. Known a
  year and a day later.

The behaviour underneath:

* default is a logistic hazard in arrears, utilisation and the loan-to-value on the
  collateral — arrears dominating, as it does in every real book;
* the loss rate given default falls with collateral coverage, through a logistic, so it
  stays inside [0, 1] where a loss rate belongs;
* an account that defaults draws down part of its remaining limit first, which is why
  exposure at default is more than the balance drawn today and why the third member of the
  model exists at all.

The realised loss is therefore zero for almost every account and large for a few. That is
the honest shape of the problem and it is the reason §7 of the README argues about what a
per-account error statistic can and cannot tell you.

Copyright (c) 2026 Ashutosh Sinha.  All rights reserved.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
ACCOUNTS = 520
FIRST = (2023, 7)
MONTHS = 24  # 2023-07 .. 2025-06
SEED = 20260923

# The generating coefficients, reported in the README so each member's fit can be compared
# against the process it is estimating.
TRUE_PD = {"p0": -4.35, "pArr": 0.92, "pUtil": 1.55, "pLtv": 1.10}
TRUE_LGD = {"l0": 0.95, "lCov": -2.60}
TRUE_CCF = 0.55  # the share of the undrawn limit a defaulting borrower takes first


def month_ends(n: int) -> list[dt.date]:
    out = []
    year, month = FIRST
    for _ in range(n):
        first_next = dt.date(year + month // 12, month % 12 + 1, 1)
        out.append(first_next - dt.timedelta(days=1))
        year, month = first_next.year, first_next.month
    return out


def generate() -> dict[str, pd.DataFrame]:
    rng = np.random.default_rng(SEED)
    dates = month_ends(MONTHS + 12)
    exposures, outcomes = [], []
    for k in range(ACCOUNTS):
        account = f"E{k:05d}"
        commitment = round(float(rng.uniform(15_000, 320_000)), 2)
        collateral = round(commitment * float(np.clip(rng.normal(1.15, 0.35), 0.15, 2.4)), 2)
        quality = float(rng.normal())  # latent, never observed
        pd_origination = round(float(np.clip(0.012 - 0.006 * quality, 0.001, 0.12)), 5)
        drawn = commitment * float(np.clip(rng.beta(2.4, 2.0), 0.02, 0.99))
        arrears = 0
        path = []
        for m in range(len(dates)):
            utilisation = min(drawn / commitment, 1.0)
            ltv = min(drawn / max(collateral, 1.0), 3.0)
            z = (
                TRUE_PD["p0"]
                + TRUE_PD["pArr"] * arrears
                + TRUE_PD["pUtil"] * utilisation
                + TRUE_PD["pLtv"] * min(ltv, 2.0)
                - 0.45 * quality
            )
            monthly_default = 1.0 / (1.0 + np.exp(-z)) / 12.0
            path.append(
                {
                    "date": dates[m],
                    "drawn": round(drawn, 2),
                    "commitment": round(commitment, 2),
                    "collateral": collateral,
                    "arrears": arrears,
                    "pd_origination": pd_origination,
                    "defaulted": int(rng.random() < monthly_default),
                }
            )
            # arrears build and cure; the balance drifts up on a stressed account
            if rng.random() < 0.06 + 0.10 * utilisation:
                arrears = min(arrears + 1, 6)
            elif arrears and rng.random() < 0.4:
                arrears -= 1
            drawn = float(np.clip(drawn * (1.0 + 0.004 * arrears) - drawn * 0.006, 0.0, commitment))
            collateral = round(collateral * (1.0 + float(rng.normal(0.0015, 0.004))), 2)

        for m in range(MONTHS):
            row = path[m]
            window = path[m + 1 : m + 13]
            first_default = next((i for i, r in enumerate(window) if r["defaulted"]), None)
            if first_default is None:
                defaulted, loss_rate, realised = 0, 0.0, 0.0
            else:
                at_default = window[first_default]
                undrawn = max(at_default["commitment"] - at_default["drawn"], 0.0)
                ead = at_default["drawn"] + TRUE_CCF * undrawn
                coverage = at_default["collateral"] / max(ead, 1.0)
                lz = TRUE_LGD["l0"] + TRUE_LGD["lCov"] * min(coverage, 3.0)
                loss_rate = float(
                    np.clip(1.0 / (1.0 + np.exp(-lz)) + rng.normal(0, 0.05), 0.0, 1.0)
                )
                defaulted, realised = 1, ead * loss_rate
            exposures.append(
                {
                    "date": row["date"],
                    "account": account,
                    "drawn": row["drawn"],
                    "commitment": row["commitment"],
                    "collateral": row["collateral"],
                    "arrears": row["arrears"],
                    "pd_origination": row["pd_origination"],
                    "kt": f"{row['date'] + dt.timedelta(days=3)}T06:00:00Z",
                }
            )
            outcomes.append(
                {
                    "date": row["date"],
                    "account": account,
                    "defaulted12": defaulted,
                    "loss_rate": round(loss_rate, 4),
                    "realised_loss12": round(realised, 2),
                    "kt": f"{row['date'] + dt.timedelta(days=366)}T00:00:00Z",
                }
            )
    return {"exposures": pd.DataFrame(exposures), "outcomes": pd.DataFrame(outcomes)}


def main() -> int:
    DATA.mkdir(exist_ok=True)
    frames = generate()
    for name, frame in frames.items():
        path = DATA / f"{name}.csv"
        frame.to_csv(path, index=False, lineterminator="\n")
        print(
            f"wrote {path.relative_to(HERE.parent.parent)}  {len(frame):,} rows, "
            f"{path.stat().st_size / 1e6:.2f} MB"
        )
    out = frames["outcomes"]
    defaulted = out[out["defaulted12"] == 1]
    print(f"twelve-month default rate   {out['defaulted12'].mean():.2%} ({len(defaulted):,} rows)")
    print(f"mean loss rate given default {defaulted['loss_rate'].mean():.1%}")
    print(f"realised loss, total         {out['realised_loss12'].sum():,.0f}")
    print(
        f"realised loss, per account   mean {out['realised_loss12'].mean():,.0f}, "
        f"zero on {(out['realised_loss12'] == 0).mean():.1%} of rows"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
