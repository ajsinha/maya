"""
The loan tape and the servicer's report this case study ingests, written to ``data/``.

    .venv/bin/python case_studies/02-mortgage-cashflow/make_data.py

Two files, because the study is about a model whose answer can be checked against
something a third party independently reported:

* ``loan_tape.csv`` — a monthly snapshot of 1,400 fixed-rate mortgages: the balance
  outstanding, the coupon, the original term and the loan's age. This is the state the
  cashflow model reads. The tape is cut two business days after month end, which is
  its knowledge time.
* ``servicer_report.csv`` — what the servicer actually collected and remitted for each
  loan that month, net of its fee. This is *not* an input to the model. It is the
  independent record the model's output is measured against, and it arrives a fortnight
  after the month it covers, because that is when servicers report.

The tape is exact level-payment amortisation, disturbed the way a real book is: about
one loan in fifty makes a partial prepayment in a given month, so the balance falls
faster than the schedule; and about one remittance in eighty is short, because a
borrower paid late. Rounding to the penny does the rest. So the model's answer and the
servicer's report agree closely and never exactly — which is the interesting case,
because a model that matches its benchmark to the penny is usually reading the
benchmark.

Copyright (c) 2026 Ashutosh Sinha.  All rights reserved.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
LOANS = 1_400
FIRST = (2024, 1)
MONTHS = 21  # 2024-01 .. 2025-09
SEED = 20260920
SERVICING_FEE = 0.0025  # 25 basis points a year, the contractual rate


def month_ends() -> list[dt.date]:
    out = []
    year, month = FIRST
    for _ in range(MONTHS):
        first_next = dt.date(year + month // 12, month % 12 + 1, 1)
        out.append(first_next - dt.timedelta(days=1))
        year, month = first_next.year, first_next.month
    return out


def level_payment(balance: float, annual_rate: float, months_left: int) -> float:
    """The constant monthly payment that amortises ``balance`` over ``months_left``."""
    i = annual_rate / 12.0
    return balance * i / (1.0 - (1.0 + i) ** -months_left)


def generate() -> dict[str, pd.DataFrame]:
    rng = np.random.default_rng(SEED)
    dates = month_ends()
    tape, report = [], []
    for k in range(LOANS):
        loan = f"L{k:05d}"
        term = int(rng.choice([180, 240, 300, 360], p=[0.1, 0.15, 0.2, 0.55]))
        rate = round(float(np.clip(rng.normal(0.055, 0.009), 0.02, 0.095)), 5)
        original = round(float(rng.uniform(80_000, 620_000)), 2)
        age = int(rng.integers(1, min(term - MONTHS - 1, 200)))
        balance = original
        # Wind the loan forward to its current age before the window opens. The remaining
        # term shortens by one each month; holding it fixed amortises far too fast, which
        # is exactly the error this study's conformance test is built to catch.
        for paid in range(age):
            payment = level_payment(balance, rate, term - paid)
            balance = max(balance - (payment - balance * rate / 12.0), 0.0)
        for m, date in enumerate(dates):
            age_now = age + m
            months_left = term - age_now
            if months_left <= 1 or balance <= 1.0:
                break
            payment = level_payment(balance, rate, months_left)
            interest = balance * rate / 12.0
            principal = payment - interest
            fee = balance * SERVICING_FEE / 12.0
            tape.append(
                {
                    "date": date,
                    "loan": loan,
                    "balance": round(balance, 2),
                    "rate": rate,
                    "term": term,
                    "age": age_now,
                    "original_balance": original,
                    "kt": f"{date + dt.timedelta(days=2)}T07:00:00Z",
                }
            )
            # what the servicer collected: the scheduled amount, less its fee, plus the
            # ordinary untidiness of a real remittance
            shortfall = float(rng.random() < 0.012) * principal * float(rng.uniform(0.2, 1.0))
            remitted = payment - fee - shortfall + float(rng.normal(0, 0.35))
            report.append(
                {
                    "date": date,
                    "loan": loan,
                    "remitted": round(remitted, 2),
                    "kt": f"{date + dt.timedelta(days=15)}T12:00:00Z",
                }
            )
            curtailment = float(rng.random() < 0.02) * float(rng.uniform(500, 6_000))
            balance = max(balance - principal - curtailment, 0.0)
    return {"loan_tape": pd.DataFrame(tape), "servicer_report": pd.DataFrame(report)}


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
