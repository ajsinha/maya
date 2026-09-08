"""
MAYA — the same feature store, in Apache Iceberg.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Two table formats, chosen by configuration, and nothing above `db/` knowing
which. The risk is the same one two Delta implementations carried: they can
differ in a way nothing notices until somebody asks a question of data written
by the other.

So the conformance evidence is not the tests below — it is that the WHOLE
platform suite passes with `MAYA_TABLE_FORMAT=iceberg`, at the same count. What
is here is the part a general suite cannot reach: the places the two formats
genuinely differ, pinned so that a difference is a decision rather than a
surprise.

Three real ones, and each is here because it broke something:

  * **A version is a different kind of number.** Delta counts 0, 1, 2; Iceberg
    uses a 19-digit int64 snapshot id. `feature_view_version.delta_version` is
    `BigInteger` for that reason, and every screen that spelled a pin by hand
    said "delta v0" — which is a false statement on an Iceberg estate, about
    the one field a reviewer reads to know a namespace cannot move.
  * **An all-null column has no type.** Arrow infers `pa.null()`, Delta stores
    it and Iceberg v2 refuses it outright. MAYA knows the answer — a feature
    declares its dtype — and simply was not passing it down.
  * **Iceberg needs a catalog** where Delta needs a path, and the two URIs it
    wants are spelled differently on Windows.
"""
from __future__ import annotations

import pathlib


import pytest

from db import table_backend
from db.delta_store import DeltaStore, arrow_type, typed_arrow

pyiceberg = pytest.importorskip(
    "pyiceberg", reason="pyiceberg is optional; the Iceberg store needs it")

from db.iceberg_store import IcebergStore

NOW = 1_700_000_000.0
ROWS = [
    {"entity_id": "b1", "event_ts": NOW - 200, "ingest_ts": NOW, "dscr": 1.10},
    {"entity_id": "b2", "event_ts": NOW - 100, "ingest_ts": NOW, "dscr": 2.10},
    # The restatement: same entity, same event time, later ingest.
    {"entity_id": "b1", "event_ts": NOW - 200, "ingest_ts": NOW + 500,
     "dscr": 0.40},
]


@pytest.fixture(params=["delta", "iceberg"])
def store(request, tmp_path):
    """Each store in turn, so one test body specifies both."""
    if request.param == "delta":
        return DeltaStore(tmp_path / "d")
    return IcebergStore(tmp_path / "i")


class TestBothStoresBehaveTheSame:
    """One body, two formats. Two bodies would be two specifications."""

    def test_a_write_makes_a_readable_table(self, store):
        store.write("features/borrower/risk/v1", ROWS)
        assert store.exists("features/borrower/risk/v1")
        assert len(store.read("features/borrower/risk/v1")) == 3

    def test_a_missing_table_is_empty_rather_than_an_error(self, store):
        assert not store.exists("features/borrower/nothing/v1")
        assert store.read("features/borrower/nothing/v1").empty
        assert store.version("features/borrower/nothing/v1") == -1

    def test_a_version_is_returned_and_pins_a_read(self, store):
        first = store.write("t/v1", ROWS[:2])
        second = store.write("t/v1", ROWS[2:])
        assert first != second
        assert len(store.read("t/v1")) == 3
        assert len(store.read("t/v1", first)) == 2

    def test_an_overwrite_replaces_the_rows(self, store):
        store.write("t/v1", ROWS)
        store.write("t/v1", ROWS[:1], mode="overwrite")
        assert len(store.read("t/v1")) == 1

    def test_the_point_in_time_read_is_the_same_rule(self, store):
        """The restatement must be invisible before its ingest time and
        authoritative after — which is the whole platform in one assertion."""
        store.write("t/v1", ROWS)
        before = store.as_of("t/v1", NOW, NOW + 100)
        after = store.as_of("t/v1", NOW, NOW + 1000)
        assert float(before[before.entity_id == "b1"].dscr.iloc[0]) == 1.10
        assert float(after[after.entity_id == "b1"].dscr.iloc[0]) == 0.40

    def test_it_is_the_SAME_function_and_not_a_copy(self):
        """`point_in_time` is imported by both stores. A second implementation
        — even a faster one written against Iceberg's own filtering — would be
        the disagreement `pit_order_key` exists to prevent."""
        import inspect

        from db import delta_store, iceberg_store

        assert "point_in_time" in inspect.getsource(iceberg_store)
        assert iceberg_store.point_in_time is delta_store.point_in_time

    def test_the_dataset_streams_the_same_columns(self, store):
        store.write("t/v1", ROWS)
        assert set(store.dataset("t/v1").schema.names) >= {
            "entity_id", "event_ts", "ingest_ts", "dscr"}
        assert store.columns_of("t/v1") >= {"entity_id", "dscr"}

    def test_an_all_null_column_takes_the_declared_type(self, store):
        """Ordinary rather than exceptional: a feature with nothing inside the
        window, or one every row of which was withdrawn. Arrow cannot infer a
        type from no values; Delta stored a null column that reads back as
        nothing and Iceberg refused the write outright."""
        rows = [{"entity_id": "b1", "event_ts": NOW, "ingest_ts": NOW,
                 "dscr": None},
                {"entity_id": "b2", "event_ts": NOW, "ingest_ts": NOW,
                 "dscr": None}]
        store.write("t/v1", rows, dtypes={"dscr": "numeric"})
        assert len(store.read("t/v1")) == 2

    def test_row_count_counts(self, store):
        store.write("t/v1", ROWS)
        assert store.row_count("t/v1") == 3


class TestTheTypeHint:
    def test_it_only_touches_columns_with_no_values(self):
        """A column that HAS values is typed from them, and a hint that
        overrode inference would be a way to store a float as a string."""
        import pyarrow as pa

        rows = [{"a": 1.5, "b": None}, {"a": 2.5, "b": None}]
        table = typed_arrow(rows, {"a": "string", "b": "numeric"})
        assert pa.types.is_floating(table.schema.field("a").type), \
            "`a` has values; inference wins"
        assert pa.types.is_floating(table.schema.field("b").type)

    def test_without_a_hint_nothing_changes(self):
        import pyarrow as pa

        table = typed_arrow([{"b": None}], None)
        assert pa.types.is_null(table.schema.field("b").type)

    @pytest.mark.parametrize("dtype,check", [
        ("numeric", "is_floating"), ("integer", "is_integer"),
        ("boolean", "is_boolean"), ("categorical", "is_string"),
        ("string", "is_string"),
        # MAYA's clocks are epoch seconds throughout, so a date column is a
        # double here — see the schema's own note on why they are not a date
        # type.
        ("date", "is_floating"), ("datetime", "is_floating"),
    ])
    def test_each_maya_dtype_maps(self, dtype, check):
        import pyarrow as pa

        assert getattr(pa.types, check)(arrow_type(dtype))

    def test_an_unknown_dtype_defaults_rather_than_refusing(self):
        """Only reached for a column with NO values: getting it wrong costs
        the type of an empty column, and refusing would stop a materialisation
        over a feature that happens to have nothing in this window."""
        import pyarrow as pa

        assert pa.types.is_string(arrow_type("something-nobody-declared"))


class TestTheIdentifierIsThePath:
    """`features/borrower/qa_borrower/v1` is a namespace and a table, which is
    what the path already means and reads correctly in any catalog browser a
    bank points at it. Flattening would put
    `features__borrower__qa_borrower__v1` in front of somebody."""

    def test_a_path_becomes_a_namespace_and_a_name(self):
        assert IcebergStore.identifier("features/borrower/risk/v1") == \
            ("features", "borrower", "risk", "v1")

    def test_a_windows_path_separator_is_handled(self):
        """The register stores forward slashes, but a caller on Windows may
        hand this a path built with `os.path.join`."""
        assert IcebergStore.identifier(r"features\borrower\risk\v1") == \
            ("features", "borrower", "risk", "v1")

    def test_empty_segments_are_dropped(self):
        assert IcebergStore.identifier("//features//risk//") == \
            ("features", "risk")


class TestTheCatalogUrisAreWrittenForThePlatform:
    """The catalog wants a `file://` warehouse and a SQLAlchemy URL, and both
    are spelled differently on Windows — `file:///C:/maya/data` against
    `file:///home/...`, and `sqlite:///C:/...` against `sqlite:////home/...`
    with four slashes. `pathlib` produces both correctly; an f-string written
    on one platform does not."""

    def test_the_posix_spelling(self):
        from pathlib import PurePosixPath

        path = PurePosixPath("/srv/maya/data/delta")
        assert path.as_uri() == "file:///srv/maya/data/delta"
        assert f"sqlite:///{path.as_posix()}" == "sqlite:////srv/maya/data/delta"

    def test_the_windows_spelling(self):
        from pathlib import PureWindowsPath

        path = PureWindowsPath(r"C:\maya\data\delta")
        assert path.as_uri() == "file:///C:/maya/data/delta"
        assert f"sqlite:///{path.as_posix()}" == "sqlite:///C:/maya/data/delta"

    def test_the_store_builds_them_from_a_path_object(self):
        """Asserted on the SOURCE, because the bug would be a hand-written
        string that works on whichever platform its author was using."""
        import inspect

        from db import iceberg_store

        source = inspect.getsource(iceberg_store.IcebergStore._open_catalog)
        assert "as_uri()" in source
        assert "as_posix()" in source

    def test_a_real_catalog_opens_and_round_trips(self, tmp_path):
        store = IcebergStore(tmp_path / "wh")
        store.write("ns/table/v1", ROWS)
        assert store.row_count("ns/table/v1") == 3
        assert (tmp_path / "wh" / "_iceberg_catalog.db").is_file(), \
            "the default catalog is a file inside the warehouse, so a laptop " \
            "needs no external service"

    def test_a_relative_root_is_resolved(self, tmp_path, monkeypatch):
        """A file URI cannot express a relative path, and the shipped
        configuration says `dir: ./data` — so a DEFAULT install would have
        failed at the first write while every test using an absolute
        `tmp_path` passed."""
        monkeypatch.chdir(tmp_path)
        store = IcebergStore(pathlib.Path("data/delta"))
        assert store.root.is_absolute()
        store.write("ns/t/v1", ROWS)
        assert store.row_count("ns/t/v1") == 3

    def test_a_catalog_may_be_configured_instead(self, tmp_path):
        """Glue, Nessie, Polaris or REST, where a bank already runs one."""
        store = IcebergStore(tmp_path / "wh", catalog={
            "uri": f"sqlite:///{(tmp_path / 'own.db').as_posix()}",
            "warehouse": (tmp_path / "wh").as_uri()})
        store.write("ns/t/v1", ROWS)
        assert (tmp_path / "own.db").is_file()
        assert not (tmp_path / "wh" / "_iceberg_catalog.db").exists()


class TestTheFormatIsChosenOnce:
    def test_delta_is_the_default(self, monkeypatch):
        """Not by inertia: it is what four hours of soak and the whole suite
        twice over have actually run against."""
        monkeypatch.delenv(table_backend.ENV, raising=False)
        assert table_backend.chosen() == "delta"
        assert table_backend.chosen(None) == "delta"

    def test_configuration_selects_it(self, monkeypatch):
        monkeypatch.delenv(table_backend.ENV, raising=False)
        assert table_backend.chosen("iceberg") == "iceberg"

    def test_the_environment_wins_over_the_file(self, monkeypatch):
        monkeypatch.setenv(table_backend.ENV, "iceberg")
        assert table_backend.chosen("delta") == "iceberg"

    def test_an_unknown_format_is_refused_rather_than_ignored(self, monkeypatch):
        monkeypatch.setenv(table_backend.ENV, "parquet")
        with pytest.raises(ValueError, match="not a table format"):
            table_backend.chosen()

    def test_build_returns_the_store_it_names(self, tmp_path, monkeypatch):
        monkeypatch.delenv(table_backend.ENV, raising=False)
        assert isinstance(table_backend.build(tmp_path / "a"), DeltaStore)
        assert isinstance(table_backend.build(tmp_path / "b", "iceberg"),
                          IcebergStore)

    def test_it_describes_what_is_underneath(self, tmp_path, monkeypatch):
        monkeypatch.delenv(table_backend.ENV, raising=False)
        delta = table_backend.describe(table_backend.build(tmp_path / "a"))
        iceberg = table_backend.describe(
            table_backend.build(tmp_path / "b", "iceberg"))
        assert delta["table_format"] == "delta"
        # For Delta it also says WHICH implementation, since MAYA has its own
        # for estates that forbid binary wheels.
        assert delta["backend"] in ("deltalake", "maya_deltalake")
        assert iceberg["table_format"] == "iceberg"
        assert "BIGINT" in iceberg["detail"]

    def test_the_two_stores_offer_the_same_surface(self):
        """A method on one and not the other is a call site that works until
        somebody changes the configuration."""
        theirs = {m for m in dir(DeltaStore) if not m.startswith("_")}
        ours = {m for m in dir(IcebergStore) if not m.startswith("_")}
        assert not theirs - ours, f"Iceberg is missing {sorted(theirs - ours)}"


class TestASnapshotIdFitsTheColumn:
    """PostgreSQL INTEGER stops at 2,147,483,647 and an Iceberg snapshot id is
    19 digits. SQLite would swallow the overflow silently and PostgreSQL would
    not — right on the database somebody develops against, wrong on the one
    they deploy to."""

    def test_the_version_columns_are_bigint(self):
        import sqlalchemy as sa

        from db.schema.tables import METADATA

        for table in ("feature_view_version", "dataset_snapshot"):
            column = METADATA.tables[table].columns["delta_version"]
            assert isinstance(column.type, sa.BigInteger), \
                f"{table}.delta_version must hold an int64 snapshot id"

    def test_a_real_snapshot_id_is_wider_than_an_int32(self, tmp_path):
        store = IcebergStore(tmp_path / "wh")
        snapshot = store.write("ns/t/v1", ROWS)
        assert snapshot > 2_147_483_647, (
            f"the id {snapshot} happens to be small; the column must still be "
            f"BIGINT because ids are int64 by specification")

    def test_and_survives_a_round_trip_through_the_register(self, client):
        """Through the API, so the column type is exercised rather than
        reasoned about."""
        if table_backend.chosen() != "iceberg":
            pytest.skip("this asserts the id the running format produces")
        client.post("/api/v1/features", json={
            "name": "wide", "entity": "borrower", "dtype": "numeric",
            "description": "d", "owner": "person/admin"})
        client.post("/api/v1/feature-views", json={
            "name": "wide_view", "entity": "borrower", "owner": "person/admin",
            "features": ["wide"]})
        client.post("/api/v1/feature-views/wide_view/materialise", json={
            "rows": [{"entity_id": "b1", "event_ts": NOW, "ingest_ts": NOW,
                      "wide": 1.0}]})
        versions = client.get(
            "/api/v1/feature-views/wide_view/versions").json()
        pinned = versions.get("versions", versions)[0]["delta_version"]
        assert pinned > 2_147_483_647
