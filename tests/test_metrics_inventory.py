"""
The §20 metric list, line by line, against what `/metrics` actually exposes.

The audit found about half of §20's metrics missing, which was hard to see from
the code because nothing held the list and the exposition side by side. This test
is that list: one row per phrase in the specification, each naming the series
that answers it. A metric that gets renamed, or a phrase that is claimed and then
removed, fails here.

It asserts on the rendered exposition rather than on the registry, because the
registry can describe a metric that nothing ever emits — and a described metric
with no samples is an alert that never fires.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import datetime as dt
import re

import pytest

from tests.conftest import World, approved_feature, build_platform, price_csv

# Each §20 phrase, and the series that answers it. Series suffixed _bucket/_count are
# histograms; a name alone must appear with at least one sample line.
SECTION_20 = {
    "request rate per endpoint": "maya_http_requests_total",
    "latency histograms per endpoint": "maya_http_request_duration_seconds_bucket",
    "error rate per endpoint": 'maya_http_requests_total{.*status="',
    "job queue depth per job type": "maya_job_queue_depth",
    "job wait time": "maya_job_wait_seconds_count",
    "job run time per job type": "maya_job_duration_seconds_count",
    "job failure rate per job type": 'maya_job_runs_total{.*outcome="',
    "resolution rows per second": "maya_resolution_rows_total",
    "resolution bytes per second": "maya_resolution_bytes_total",
    "resolution seconds (the denominator)": "maya_resolution_seconds_total",
    "Delta file counts per table": "maya_delta_files",
    "Delta small-file ratio per table": "maya_delta_small_file_ratio",
    "database pool utilization": "maya_db_pool_connections",
    "slow-query count": "maya_db_slow_queries_total",
    "cache hit rates": "maya_cache_hits_total",
    "active sessions": "maya_sessions_active",
    "authorization denials": "maya_authz_denials_total",
    "pins created per namespace": "maya_namespace_pins",
    "bytes stored per namespace": "maya_namespace_pin_bytes",
}


@pytest.fixture(scope="module")
def scraped():
    """One platform that has actually done some work, and its exposition text."""
    platform = build_platform()
    w = World(platform)
    platform.access.create_namespace(w.admin, name="obs")
    ref = approved_feature(w, "metered", price_csv(6), ns="obs")
    platform.features.pin(w.mick, ref, version_no=1, pin_name="m", as_of=dt.date(2026, 1, 6))
    platform.jobs.drain()
    with pytest.raises(Exception):  # one refusal, so the denial counter has a sample
        platform.features.create(w.mona, namespace="obs", name="nope", definition={})
    from maya.api.app import create_api
    from starlette.testclient import TestClient

    web = TestClient(create_api(platform))
    web.get("/api/v1/features")
    body = TestClient(create_api(platform)).get("/metrics").text
    yield w, body
    platform.shutdown()


@pytest.mark.parametrize("phrase,series", sorted(SECTION_20.items()))
def test_every_metric_section_20_lists_is_exposed(scraped, phrase, series):
    _, body = scraped
    pattern = re.compile("^" + series, re.M)
    assert pattern.search(body), f"§20 asks for {phrase}; no {series} sample in /metrics"


def test_the_exposition_stays_well_formed_with_every_new_family(scraped):
    """Labels now carry table paths and namespace names; the format must survive them."""
    _, body = scraped
    label = r'[a-zA-Z_][a-zA-Z0-9_]*="(?:[^"\\]|\\.)*"'
    sample = re.compile(rf"^[a-z_:][a-z0-9_:]*(\{{{label}(?:,{label})*\}})? -?[0-9.e+]+$")
    for line in body.splitlines():
        if line and not line.startswith("#"):
            assert sample.match(line), line
    assert body.count("# TYPE maya_delta_files gauge") == 1, "described once, not per sample"


def test_resolution_throughput_can_be_divided_into_a_rate(scraped):
    """Rows and bytes per second are counters over a seconds counter, so a scrape interval
    divides into a rate. A gauge of "the last one's speed" would not."""
    _, body = scraped
    rows = float(re.search(r"^maya_resolution_rows_total\{kind=\"feature\"\} (\S+)", body, re.M)[1])
    secs = float(
        re.search(r"^maya_resolution_seconds_total\{kind=\"feature\"\} (\S+)", body, re.M)[1]
    )
    assert rows > 0 and secs > 0 and rows / secs > 0


def test_pins_and_bytes_are_attributed_to_the_namespace_that_owns_them(scraped):
    w, body = scraped
    assert re.search(r'^maya_namespace_pins\{kind="feature",namespace="obs"\} [1-9]', body, re.M)
    assert re.search(
        r'^maya_namespace_pin_bytes\{kind="feature",namespace="obs"\} [1-9]', body, re.M
    )


def test_a_cache_reports_zeros_before_its_first_lookup(scraped):
    """A missing series reads as "no traffic or no cache, we cannot tell"; zeros do not."""
    _, body = scraped
    for cache in ("session_principal", "api_key_secret", "audit_chain", "metrics_lake"):
        assert re.search(rf'^maya_cache_hits_total\{{cache="{cache}"\}} ', body, re.M), cache
        assert re.search(rf'^maya_cache_misses_total\{{cache="{cache}"\}} ', body, re.M), cache


def test_the_audit_chain_cache_records_its_hits(scraped):
    """The one cache in a module this batch owns, instrumented to prove the mechanism."""
    w, _ = scraped
    from maya.observability.metrics import METRICS

    w.p.ops.health()
    before = METRICS._counters["maya_cache_hits_total"].get((("cache", "audit_chain"),), 0)
    w.p.ops.health()  # inside health.audit_verify_seconds: this one must be a hit
    after = METRICS._counters["maya_cache_hits_total"][(("cache", "audit_chain"),)]
    assert after > before


def test_slow_queries_are_counted_without_recording_any_statement_text(scraped):
    """§20 forbids logging data values, and a statement carries literals, so the metric is a
    count and nothing else."""
    _, body = scraped
    assert re.search(r"^maya_db_statements_total \d", body, re.M)
    assert re.search(r"^maya_db_slow_queries_total \d", body, re.M)
    assert "SELECT" not in body and "select " not in body


def test_the_pool_gauges_describe_sqlites_single_writer_honestly(scraped):
    w, body = scraped
    status = w.p.db.pool_status()
    if w.p.db.is_sqlite:
        assert status == {
            "in_use": 0,
            "available": 1,
            "overflow": 0,
            "size": 1,
            "max_overflow": 0,
        }
    else:
        assert status["size"] >= 1 and status["max_overflow"] >= 0
    assert re.search(r'^maya_db_pool_limit\{kind="size"\} \d', body, re.M)
