"""
Workbench pages through their forms: the structured feature designer (create,
save with optimistic concurrency, save-and-submit, draft preview), ingest with
restatements and duplicate detection, the upload wizard, and the feature set
builder — each checked against what the platform stored.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import pytest

from tests.conftest import PASSWORD, price_csv
from tests.test_web_journeys import Browser, site  # noqa: F401 - the shared estate fixture

DESIGN = {
    "namespace": "quant", "mode": "source", "index_name": ["date", "symbol"],
    "index_type": ["date", "string"], "attr_name": ["close", ""],
    "attr_type": ["float64", ""], "attr_unit": ["USD", ""], "attr_tag": ["price", ""],
    "attr_rule": ["forward_fill(limit=2)", ""], "grid": "as_is", "source_type": "csv",
    "transform": "[]", "quality": '[{"check": "not_null", "attr": "close"}]',
    "description": "closing prices", "tags": "eq, daily",
    "licence_vendor": "Acme", "licence_redistribution": "internal",
}


@pytest.fixture(scope="module")
def dana(site):  # noqa: F811
    w, app = site
    return w, Browser(app, "dana", PASSWORD)


def test_the_designer_creates_saves_and_submits(dana):
    w, b = dana
    assert "Kind of definition" in b.get("/workbench/features/new").text
    r = b.post("/workbench/features/new", {**DESIGN, "name": "wb_close"}, expect="success")
    assert "/workbench/features/quant/wb_close/edit" in str(r.url)
    f = w.p.features.get(w.dana, "quant/wb_close")
    d = f["versions"][0]["definition"]
    assert d["index"] == ["date", "symbol"] and d["schema"] == [
        {"name": "close", "type": "float64", "unit": "USD", "tag": "price"}]
    assert d["resolution"]["rules"] == {"close": "forward_fill(limit=2)"}
    assert d["licence"] == {"vendor": "Acme", "redistribution": "internal"}
    assert f["tags"] == ["eq", "daily"]
    row_version = f["versions"][0]["row_version"]
    b.post("/workbench/features/quant/wb_close/edit",
           {**DESIGN, "attr_rule": ["zero", ""], "row_version": str(row_version)},
           expect="success")
    assert w.p.features.get(w.dana, "quant/wb_close")["versions"][0]["definition"][
        "resolution"]["rules"] == {"close": "zero"}
    stale = b.post("/workbench/features/quant/wb_close/edit",
                   {**DESIGN, "row_version": str(row_version)}, expect="danger")
    assert "changed" in stale.text.lower() or "conflict" in stale.text.lower()
    w.p.features.ingest(w.dana, "quant/wb_close", price_csv(4), fmt="csv")
    preview = b.get("/workbench/features/quant/wb_close/preview").text
    assert "draft preview" in preview and "close" in preview
    r = b.post("/workbench/features/quant/wb_close/edit",
               {**DESIGN, "then": "submit"}, expect="success")
    assert "/catalog/features/quant/wb_close" in str(r.url)
    assert w.p.features.get(w.dana, "quant/wb_close")["versions"][0]["state"] == "in_review"


def test_the_designer_builds_derived_and_extending_definitions(dana):
    w, b = dana
    b.post("/workbench/features/new", {
        "namespace": "quant", "name": "wb_union", "mode": "derived", "operator": "union",
        "operands": "maya://feature/quant/xy@v1\nmaya://feature/quant/xy@v1",
        "options": '{"collision": "prefer_left"}', "grid": "as_is", "transform": "[]",
        "quality": "[]", "index_name": ["date", "symbol"], "index_type": ["date", "string"],
        "attr_name": ["x"], "attr_type": ["float64"], "attr_unit": [""], "attr_tag": [""],
        "attr_rule": [""]}, expect="success")
    src = w.p.features.get(w.dana, "quant/wb_union")["versions"][0]["definition"]["source"]
    assert src["type"] == "derived" and src["derivation"]["operator"] == "union"
    assert len(src["derivation"]["operands"]) == 2
    b.post("/workbench/features/new", {
        "namespace": "quant", "name": "wb_child", "mode": "extends",
        "parent": "maya://feature/quant/xy@v1", "binding": "pinned",
        "override": '{"resolution": {"rules": {"x": "zero"}}}'}, expect="success")
    ext = w.p.features.get(w.dana, "quant/wb_child")["versions"][0]["definition"]["extends"]
    assert ext == {"parent": "maya://feature/quant/xy@v1", "binding": "pinned",
                   "override": {"resolution": {"rules": {"x": "zero"}}}}
    r = b.post("/workbench/features/new", {**DESIGN, "name": "wb_bad", "quality": "{oops"},
               expect="danger")
    assert "not valid JSON" in r.text


def test_ingest_through_the_form_reports_restatements_and_duplicates(dana):
    w, b = dana
    w.p.features.create(w.dana, namespace="quant", name="wb_ing", definition={
        k: v for k, v in w.p.features.get(w.dana, "quant/xy")["versions"][0]["definition"]
        .items()})
    assert "Ingest" in b.get("/workbench/features/quant/wb_ing/ingest").text
    from tests.test_warrants import xy_csv
    first = xy_csv(5)
    r = b.post("/workbench/features/quant/wb_ing/ingest", {"fmt": "csv", "note": "v1"},
               files={"file": ("a.csv", first, "text/csv")}, expect="success")
    assert "Ingested 15 row(s)" in r.text
    r = b.post("/workbench/features/quant/wb_ing/ingest", {"fmt": "csv"},
               files={"file": ("a.csv", first, "text/csv")}, expect="warning")
    assert "RESTATEMENT" in r.text and "uploaded before" in r.text
    r = b.post("/workbench/features/quant/wb_ing/ingest", {"fmt": "csv"}, expect="danger")
    assert "Choose a file to ingest" in r.text


def test_the_upload_wizard_proposes_then_creates(dana):
    w, b = dana
    csv = b"date,ticker,close,volume\n2026-01-02,AAA,10.5,100\n2026-01-05,AAA,10.7,120\n"
    r = b.post("/workbench/upload", {"fmt": "csv"},
               files={"file": ("My Prices-2026.csv", csv, "text/csv")})
    assert "my_prices_2026" in r.text
    key = __import__("re").search(r'name="key" value="([^"]+)"', r.text).group(1)
    r = b.post("/workbench/upload/confirm", {
        **DESIGN, "key": key, "name": "wizard_px", "index_name": ["date", "ticker"],
        "index_type": ["date", "string"], "attr_name": ["close", "volume"],
        "attr_type": ["float64", "int64"], "attr_unit": ["", ""], "attr_tag": ["", ""],
        "attr_rule": ["", ""], "licence_vendor": "", "licence_redistribution": ""},
        expect="success")
    assert "2 row(s) ingested" in r.text
    assert w.p.features.get(w.dana, "quant/wizard_px")["ingests"][0]["rows"] == 2
    r = b.post("/workbench/upload/confirm", {**DESIGN, "key": key, "name": "again"},
               expect="danger")
    assert "upload expired" in r.text
    r = b.post("/workbench/upload", {"fmt": "csv"}, expect="danger")
    assert "Choose a file to upload" in r.text


def test_the_feature_set_builder(site):  # noqa: F811
    w, app = site
    devi = Browser(app, "devi", PASSWORD)
    assert "Attribute" in devi.get("/workbench/featuresets/new").text
    form = {"namespace": "quant", "name": "wb_panel", "index": "date, symbol",
            "grid": "as_is", "align_mode": "asof", "tolerance_days": "3",
            "asof_direction": "backward", "start": "2026-01-01", "universe": "AAA, BBB",
            "global_rules": '{"x": "zero"}', "global_default": "none", "group_policies": "[]",
            "m_attr": ["x", "y", ""], "m_ref": ["maya://feature/quant/xy@v1"] * 2 + [""],
            "m_source": ["x", "y", ""], "m_cast": ["", "", ""], "m_rule": ["", "zero", ""]}
    r = devi.post("/workbench/featuresets/new", form, expect="success")
    assert "/workbench/featuresets/quant/wb_panel/edit" in str(r.url)
    d = w.p.featuresets.get(w.devi, "quant/wb_panel")["versions"][0]["definition"]
    assert d["alignment"] == {"mode": "asof", "tolerance_days": 3, "direction": "backward"}
    assert d["filters"] == {"start": "2026-01-01", "universe": ["AAA", "BBB"]}
    assert [m["attr"] for m in d["members"]] == ["x", "y"] and d["members"][1]["rule"] == "zero"
    assert d["global_policy"] == {"rules": {"x": "zero"}, "default": "none"}
    devi.post("/workbench/featuresets/quant/wb_panel/edit",
              {**form, "align_mode": "left", "align_member": "x"}, expect="success")
    d = w.p.featuresets.get(w.devi, "quant/wb_panel")["versions"][0]["definition"]
    assert d["alignment"] == {"mode": "left", "member": "x"}
    pv = devi.c.get("/workbench/featuresets/quant/wb_panel/preview")
    assert pv.status_code == 422 and "does not carry the set index" in pv.text
    devi.post("/workbench/featuresets/quant/wb_panel/edit", {**form, "align_mode": "inner"},
              expect="success")
    assert "feature set draft preview" in devi.get(
        "/workbench/featuresets/quant/wb_panel/preview").text
    r = devi.post("/workbench/featuresets/quant/wb_panel/edit",
                  {**form, "align_mode": "inner", "then": "submit"}, expect="success")
    assert "/catalog/featuresets/quant/wb_panel" in str(r.url)
    devi.post("/workbench/featuresets/new", {
        "namespace": "quant", "name": "wb_panel_ext", "mode": "extends",
        "parent": "maya://featureset/quant/panel@v1", "binding": "pinned",
        "override": "{}"}, expect="success")
    ext = w.p.featuresets.get(w.devi, "quant/wb_panel_ext")["versions"][0]["definition"]
    assert ext["extends"]["parent"] == "maya://featureset/quant/panel@v1"
