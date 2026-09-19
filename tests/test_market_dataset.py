"""
The synthetic market dataset of §23 (``maya.testing.market``): deterministic by
seed, awkward exactly where its docstring says, and usable end to end — ingested
through the testing kit, pinned, trained on under a certified warrant, and read
point in time before a restatement (SC-11 on this dataset).

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import datetime as dt
import io

import pandas as pd
import pyarrow.parquet as pq
import pytest

from maya.core.calendars import is_business_day
from maya.resolution.types import parse_type
from maya.testing import Maya, market

SEED = 11


@pytest.fixture(scope="module")
def data() -> market.MarketData:
    return market.generate(SEED, symbols=4)


# -- determinism -------------------------------------------------------------------------------
def test_same_seed_same_bytes_different_seed_different_data(data):
    again = market.generate(SEED, symbols=4)
    for name in ("prices_csv", "fundamentals_csv", "messy_prices_csv", "surface_parquet"):
        assert getattr(data, name)() == getattr(again, name)(), name
    other = market.generate(SEED + 1, symbols=4)
    assert other.prices_csv() != data.prices_csv()
    assert other.fundamentals_csv() != data.fundamentals_csv()


# -- shape and irregularities, as documented ---------------------------------------------------
def test_prices_only_on_open_exchange_days(data):
    days = {d.date() for d in data.prices["date"]}
    assert all(is_business_day("NYSE", d) and d.weekday() < 5 for d in days)
    assert data.events["holidays"] and not days & set(data.events["holidays"])
    assert list(data.prices.columns) == ["date", "symbol", "close", "volume", "adj_factor", "kt"]
    assert not data.prices.duplicated(["date", "symbol"]).any()
    assert data.prices["volume"].isna().any() and data.prices["close"].notna().all()


def test_gaps_late_listing_and_delisting(data):
    px, ev = data.prices, data.events
    keys = set(zip(px["date"].dt.date, px["symbol"]))
    assert ev["gaps"] and not keys & set(ev["gaps"])
    first, last = px["date"].min().date(), px["date"].max().date()
    late = px[px["symbol"] == ev["late_listing"]["symbol"]]["date"].dt.date
    assert late.min() == ev["late_listing"]["first_day"] > first
    gone = px[px["symbol"] == ev["delisting"]["symbol"]]["date"].dt.date
    assert gone.max() == ev["delisting"]["last_day"] < last


def test_split_halves_the_raw_close_and_the_factor_adjusts_it(data):
    split = data.events["split"]
    s = data.prices[data.prices["symbol"] == split["symbol"]].set_index("date")
    ex = pd.Timestamp(split["ex_date"])
    before, after = s[s.index < ex], s[s.index >= ex]
    assert (before["adj_factor"] == 0.5).all() and (after["adj_factor"] == 1.0).all()
    raw_jump = after["close"].iloc[0] / before["close"].iloc[-1]
    adjusted_jump = raw_jump / 0.5
    assert 0.4 < raw_jump < 0.6 and 0.8 < adjusted_jump < 1.2


def test_restatements_reissue_the_same_key_later(data):
    f = data.fundamentals
    restated = f[f["revision"] == 1]
    assert len(restated) == len(data.events["restatements"]) >= 1
    for _, row in restated.iterrows():
        orig = f[(f["date"] == row["date"]) & (f["symbol"] == row["symbol"]) &
                 (f["revision"] == 0)]
        assert len(orig) == 1
        assert row["kt"] > orig["kt"].iloc[0] and row["eps"] != orig["eps"].iloc[0]
        assert row["period_end"] == orig["period_end"].iloc[0]
    assert not f[f["revision"] == 0].duplicated(["date", "symbol"]).any()
    assert all(is_business_day("NYSE", d.date()) for d in f["date"])


def test_surface_is_a_three_by_four_tensor_and_the_messy_file_is_messy(data):
    assert parse_type(market.SURFACE_DEF["schema"][0]["type"]).shape == (3, 4)
    assert all(len(v) == 12 for v in data.surface["surface"])
    assert set(data.surface["date"]) <= set(data.prices["date"])
    messy = data.messy_prices_csv()
    text = messy.decode("utf-8-sig")
    assert messy.startswith(b"\xef\xbb\xbf") and "\r\n" in text and '"' in text
    dates = [line.split(",")[0] for line in text.splitlines()[1:]]
    assert {"-" in d and d[:4].isdigit() for d in dates} == {True, False}
    assert any("/" in d for d in dates) and any(d[3:6].isalpha() for d in dates)


# -- end to end through MAYA -------------------------------------------------------------------
@pytest.fixture(scope="module")
def maya():
    with Maya.start() as m:
        yield m


def _download(client, ref: str, kind: str = "features") -> pd.DataFrame:
    body = getattr(client, kind).download(ref)["data"]
    return pq.read_table(io.BytesIO(body)).to_pandas()


def test_market_to_certified_warrant_and_point_in_time(maya, data):
    prices = maya.approved_feature("prices", data.prices_csv(), market.PRICES_DEF)
    funds = maya.approved_feature("fundamentals", data.fundamentals_csv(),
                                  market.FUNDAMENTALS_DEF)
    first = data.events["restatements"][0]
    before = first["restated_kt"] - dt.timedelta(seconds=1)

    # SC-11 on this dataset: as known before the restatement, the original number
    dana = maya.client("dana")
    day = str(first["date"])
    point = {"start": day, "end": day}
    old = dana.features.preview(f"maya://feature/{funds}@v1", as_of_known=before.isoformat(),
                                **point)
    new = dana.features.preview(f"maya://feature/{funds}@v1", **point)
    pick = [r for r in old["rows"] if r["symbol"] == first["symbol"]]
    assert pick[0]["eps"] == pytest.approx(first["original_eps"]) and pick[0]["revision"] == 0
    pick = [r for r in new["rows"] if r["symbol"] == first["symbol"]]
    assert pick[0]["eps"] == pytest.approx(first["restated_eps"]) and pick[0]["revision"] == 1

    # a cascade pin as known just before the restatement, fundamentals as-of joined
    pin = maya.approved_featureset(
        "panel", {"close": prices, "eps": funds, "revenue": funds},
        alignment={"mode": "asof", "tolerance_days": 120},
        pin=("pit", before.date()), as_of_known=before)
    model = maya.approved_model("eps_linear", "eps_hat = a*sales + b",
                                {"a": "parameter", "b": "parameter"})
    tw = maya.training_warrant("eps_fit", model, pin,
                               {"target": "eps", "bindings": {"sales": "revenue"}})
    assert tw["contract_report"]["ok"] and tw["contract_report"]["mapping"] == {"sales": "revenue"}
    cert = tw["leakage_certificate"]
    assert cert["status"] == "certified" and cert["violations"] == 0
    assert cert["rows_examined"] > 0 and cert["signature"]["algorithm"] == "Ed25519"
    got = maya.client("devi").training.get(tw["id"])
    assert got["featureset_ref"] == pin

    # the pinned panel carries the original eps on and after the announcement
    panel = _download(maya.client("devi"), pin, "featuresets")
    rows = panel[(panel["symbol"] == first["symbol"]) &
                 (pd.to_datetime(panel["date"]) >= pd.Timestamp(first["date"]))]
    assert len(rows) and rows["eps"].iloc[0] == pytest.approx(first["original_eps"])
    assert pd.to_datetime(panel["date"]).max() <= pd.Timestamp(before.date())


def test_a_pin_that_includes_restatements_is_refused_a_certificate(maya, data):
    """Restated numbers are known long after their event date: training on them as
    though known on the day is leakage, and the certificate refuses it."""
    ref = maya.ref("fundamentals")
    last = data.events["restatements"][-1]["restated_kt"] + dt.timedelta(hours=1)
    pin = maya.approved_featureset("restated_panel", {"eps": ref, "revenue": ref},
                                   pin=("late", last.date()), as_of_known=last)
    model = maya.ref("eps_linear") + "@v1"
    tw = maya.training_warrant("eps_late", model, pin,
                               {"target": "eps", "bindings": {"sales": "revenue"}})
    cert = tw["leakage_certificate"]
    assert cert["status"] == "refused"
    assert cert["violations"] == len(data.events["restatements"])


def test_messy_csv_ingests_to_exactly_the_clean_rows(maya, data):
    clean = maya.ref("prices")
    messy = maya.approved_feature("prices_messy", data.messy_prices_csv(), market.PRICES_DEF)
    dana = maya.client("dana")
    a = _download(dana, f"maya://feature/{clean}@v1")
    b = _download(dana, f"maya://feature/{messy}@v1")
    assert len(a) == len(data.prices) and a.equals(b)


def test_the_surface_ingests_as_a_tensor_from_parquet(maya, data):
    ref = maya.approved_feature("surface", None, market.SURFACE_DEF)
    dana = maya.client("dana")
    dana.features.ingest(ref, data.surface_parquet(), fmt="parquet", filename="surface.parquet")
    got = _download(dana, f"maya://feature/{ref}@v1")
    assert len(got) == len(data.surface)
    assert [list(v) for v in got["surface"]] == data.surface["surface"].tolist()
