"""
MAYA — the two Delta implementations must agree.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

`deltalake` is a compiled Rust extension and some estates forbid binary wheels,
so `maya_deltalake` implements the six calls MAYA makes, in pure Python. Two
implementations of the layer the evidence lives in is the most dangerous thing
in this codebase, and the danger is specific: they can differ in a way nothing
notices until an auditor asks a question of a table written by the other one.

So this file does three things, and the third is the one that matters.

**Both are held to the same tests.** Every behavioural test below runs twice,
once per implementation, from one body — because two test bodies is two
specifications and they drift.

**They must read each other.** Written by one, read by the other, in both
directions, for append, for overwrite and for time travel. This is what makes
`maya_deltalake` a Delta writer rather than a private format that happens to
work: a table MAYA produces on a locked-down estate has to open in Spark, and
one produced by Spark has to open in MAYA.

**Everything outside the subset refuses by name.** A fallback that quietly does
less than the thing it stands in for is the failure this is written against.

The cross-implementation tests skip when `deltalake` is absent, and say so.
`tools/ci/` runs the whole MAYA suite a second time with
`MAYA_DELTA_BACKEND=maya_deltalake`, which is the real conformance evidence:
not that the fallback passes tests written for it, but that it passes the three
thousand written for the platform.
"""
from __future__ import annotations

import json
import pathlib

import pandas as pd
import pytest

import maya_deltalake
from maya_deltalake import DeltaProtocolError

try:
    import deltalake
    HAVE_REAL = True
except ImportError:                                   # pragma: no cover
    deltalake = None
    HAVE_REAL = False

NEEDS_REAL = pytest.mark.skipif(
    not HAVE_REAL, reason="the deltalake package is not installed, so the two "
                          "implementations cannot be compared here")

ROWS = [{"entity_id": "b1", "event_ts": 1.5, "ingest_ts": 9.0, "dscr": 1.10},
        {"entity_id": "b2", "event_ts": 2.5, "ingest_ts": 9.0, "dscr": 1.20}]
MORE = [{"entity_id": "b3", "event_ts": 3.5, "ingest_ts": 9.0, "dscr": 1.30}]


def _impl(name):
    if name == "maya_deltalake":
        return maya_deltalake.DeltaTable, maya_deltalake.write_deltalake
    return deltalake.DeltaTable, deltalake.write_deltalake


IMPLEMENTATIONS = ["maya_deltalake"] + (["deltalake"] if HAVE_REAL else [])


@pytest.fixture(params=IMPLEMENTATIONS)
def both(request):
    """Each implementation in turn, so one test body specifies both."""
    return _impl(request.param)


@pytest.fixture
def table(tmp_path):
    return str(tmp_path / "t")


# =========================================================================
#  The same behaviour, from both
# =========================================================================
class TestTheyBehaveTheSame:
    def test_a_write_creates_version_zero(self, both, table):
        DeltaTable, write = both
        write(table, pd.DataFrame(ROWS))
        assert DeltaTable(table).version() == 0

    def test_an_append_makes_the_next_version(self, both, table):
        DeltaTable, write = both
        write(table, pd.DataFrame(ROWS))
        write(table, pd.DataFrame(MORE), mode="append")
        opened = DeltaTable(table)
        assert opened.version() == 1
        assert len(opened.to_pandas()) == 3

    def test_time_travel_returns_the_earlier_table(self, both, table):
        """The reason MAYA pins a Delta version at all: a contract points at a
        version, and reading it later must give the same rows."""
        DeltaTable, write = both
        write(table, pd.DataFrame(ROWS))
        write(table, pd.DataFrame(MORE), mode="append")
        opened = DeltaTable(table)
        opened.load_as_version(0)
        assert len(opened.to_pandas()) == 2
        assert opened.version() == 0

    def test_an_overwrite_replaces_the_rows(self, both, table):
        DeltaTable, write = both
        write(table, pd.DataFrame(ROWS))
        write(table, pd.DataFrame(MORE), mode="overwrite")
        assert len(DeltaTable(table).to_pandas()) == 1

    def test_and_the_overwritten_version_is_still_readable(self, both, table):
        """An overwrite removes files from the LIVE set and leaves the bytes,
        which is what makes travelling back past one work."""
        DeltaTable, write = both
        write(table, pd.DataFrame(ROWS))
        write(table, pd.DataFrame(MORE), mode="overwrite")
        opened = DeltaTable(table)
        opened.load_as_version(0)
        assert len(opened.to_pandas()) == 2

    def test_an_overwrite_may_replace_the_schema(self, both, table):
        """MAYA relies on this: replacing an ORPHAN left by a materialisation
        that wrote Delta and died before recording it, where the view may have
        been redefined in between — which is often WHY the first attempt
        failed."""
        DeltaTable, write = both
        write(table, pd.DataFrame(ROWS))
        write(table, pd.DataFrame([{"quite": "different", "shape": 1}]),
              mode="overwrite", schema_mode="overwrite")
        back = DeltaTable(table).to_pandas()
        assert list(back.columns) == ["quite", "shape"]

    def test_the_dataset_streams_the_same_rows(self, both, table):
        """`to_pyarrow_dataset` is what the transfer layer reads, so that a
        large table moves in record batches rather than as one object."""
        DeltaTable, write = both
        write(table, pd.DataFrame(ROWS))
        dataset = DeltaTable(table).to_pyarrow_dataset()
        assert set(dataset.schema.names) == set(ROWS[0])
        assert dataset.to_table().num_rows == 2

    def test_the_row_count_survives_many_appends(self, both, table):
        DeltaTable, write = both
        write(table, pd.DataFrame(ROWS))
        for i in range(8):
            write(table, pd.DataFrame([{**MORE[0], "entity_id": f"x{i}"}]),
                  mode="append")
        opened = DeltaTable(table)
        assert opened.version() == 8
        assert len(opened.to_pandas()) == 10

    def test_every_intermediate_version_is_reachable(self, both, table):
        DeltaTable, write = both
        write(table, pd.DataFrame(ROWS))
        for i in range(4):
            write(table, pd.DataFrame([{**MORE[0], "entity_id": f"x{i}"}]),
                  mode="append")
        for version in range(5):
            opened = DeltaTable(table)
            opened.load_as_version(version)
            assert len(opened.to_pandas()) == 2 + version


# =========================================================================
#  They must read each other
# =========================================================================
@NEEDS_REAL
class TestTheyReadEachOther:
    """A table MAYA writes on a locked-down estate has to open in Spark, and a
    table Spark writes has to open in MAYA. That is the difference between a
    Delta writer and a private format that happens to work."""

    def test_the_real_one_reads_what_ours_wrote(self, table):
        maya_deltalake.write_deltalake(table, pd.DataFrame(ROWS))
        maya_deltalake.write_deltalake(table, pd.DataFrame(MORE), mode="append")
        opened = deltalake.DeltaTable(table)
        assert opened.version() == 1
        assert len(opened.to_pandas()) == 3
        assert set(opened.to_pandas()["entity_id"]) == {"b1", "b2", "b3"}

    def test_ours_reads_what_the_real_one_wrote(self, table):
        deltalake.write_deltalake(table, pd.DataFrame(ROWS))
        deltalake.write_deltalake(table, pd.DataFrame(MORE), mode="append")
        opened = maya_deltalake.DeltaTable(table)
        assert opened.version() == 1
        assert len(opened.to_pandas()) == 3

    def test_they_interleave(self, table):
        """The case that actually happens: an estate installs the package after
        running without it, or a table is copied between the two."""
        maya_deltalake.write_deltalake(table, pd.DataFrame(ROWS))
        deltalake.write_deltalake(table, pd.DataFrame(MORE), mode="append")
        maya_deltalake.write_deltalake(
            table, pd.DataFrame([{**MORE[0], "entity_id": "b4"}]), mode="append")
        for opened in (deltalake.DeltaTable(table), maya_deltalake.DeltaTable(table)):
            assert opened.version() == 2
            assert len(opened.to_pandas()) == 4

    def test_time_travel_agrees_across_them(self, table):
        maya_deltalake.write_deltalake(table, pd.DataFrame(ROWS))
        maya_deltalake.write_deltalake(table, pd.DataFrame(MORE), mode="append")
        theirs, ours = deltalake.DeltaTable(table), maya_deltalake.DeltaTable(table)
        theirs.load_as_version(0)
        ours.load_as_version(0)
        assert len(theirs.to_pandas()) == len(ours.to_pandas()) == 2

    def test_an_overwrite_by_ours_is_seen_by_theirs(self, table):
        deltalake.write_deltalake(table, pd.DataFrame(ROWS))
        maya_deltalake.write_deltalake(table, pd.DataFrame(MORE), mode="overwrite")
        assert len(deltalake.DeltaTable(table).to_pandas()) == 1
        travelled = deltalake.DeltaTable(table)
        travelled.load_as_version(0)
        assert len(travelled.to_pandas()) == 2

    def test_the_same_rows_come_back_whichever_reads(self, table):
        """Compared as SETS. Delta guarantees a set of rows, not a sequence,
        and both implementations are entitled to their own order — which is
        safe because MAYA's point-in-time read sorts by a total, content-based
        key precisely so two readers cannot break a tie differently."""
        maya_deltalake.write_deltalake(table, pd.DataFrame(ROWS + MORE))
        theirs = deltalake.DeltaTable(table).to_pandas()
        ours = maya_deltalake.DeltaTable(table).to_pandas()
        assert set(theirs.columns) == set(ours.columns)
        def rows_of(frame):
            return sorted(tuple(sorted(row.items()))
                          for row in frame.to_dict("records"))

        assert rows_of(theirs) == rows_of(ours)

    def test_the_schema_string_is_identical(self, table):
        """Byte-for-byte where it can be. A schema that differs only in
        whitespace is fine; one that differs in a TYPE is a column that reads
        back wrongly, and comparing the parsed structure catches that."""
        ours_path, theirs_path = table + "-o", table + "-t"
        frame = pd.DataFrame(ROWS)
        maya_deltalake.write_deltalake(ours_path, frame)
        deltalake.write_deltalake(theirs_path, frame)

        def schema_of(path):
            first = pathlib.Path(path) / "_delta_log" / "00000000000000000000.json"
            for line in first.read_text().splitlines():
                action = json.loads(line)
                if "metaData" in action:
                    return json.loads(action["metaData"]["schemaString"])
            raise AssertionError("no metaData in the first commit")

        assert schema_of(ours_path) == schema_of(theirs_path)

    def test_the_protocol_versions_match(self, table):
        ours_path, theirs_path = table + "-o", table + "-t"
        maya_deltalake.write_deltalake(ours_path, pd.DataFrame(ROWS))
        deltalake.write_deltalake(theirs_path, pd.DataFrame(ROWS))

        def protocol_of(path):
            first = pathlib.Path(path) / "_delta_log" / "00000000000000000000.json"
            for line in first.read_text().splitlines():
                action = json.loads(line)
                if "protocol" in action:
                    return action["protocol"]
            raise AssertionError("no protocol in the first commit")

        assert protocol_of(ours_path) == protocol_of(theirs_path)


# =========================================================================
#  Everything outside the subset refuses by name
# =========================================================================
class TestItRefusesRatherThanApproximates:
    """A fallback that quietly does less than the thing it stands in for is the
    failure this whole package is written against."""

    def test_an_object_store_is_refused(self, table):
        with pytest.raises(DeltaProtocolError, match="local filesystem only"):
            maya_deltalake.write_deltalake(
                table, pd.DataFrame(ROWS),
                storage_options={"AWS_REGION": "eu-west-2"})

    def test_partitioning_is_refused(self, table):
        with pytest.raises(DeltaProtocolError, match="does not partition"):
            maya_deltalake.write_deltalake(table, pd.DataFrame(ROWS),
                                           partition_by=["entity_id"])

    def test_an_unknown_write_mode_is_refused(self, table):
        with pytest.raises(DeltaProtocolError, match="not a write mode"):
            maya_deltalake.write_deltalake(table, pd.DataFrame(ROWS),
                                           mode="upsert")

    def test_a_missing_table_is_refused_rather_than_read_as_empty(self, tmp_path):
        """"A path that is not a table" and "a table that is empty" are
        different answers, and returning nothing for the first would let a
        typo look like an empty feature view."""
        with pytest.raises(DeltaProtocolError, match="no Delta table"):
            maya_deltalake.DeltaTable(str(tmp_path / "nothing-here"))

    def test_a_version_that_never_existed_is_refused(self, table):
        """Reading the nearest one instead would answer a question nobody
        asked — and every caller of time travel is reproducing something."""
        maya_deltalake.write_deltalake(table, pd.DataFrame(ROWS))
        opened = maya_deltalake.DeltaTable(table)
        with pytest.raises(DeltaProtocolError, match="does not exist"):
            opened.load_as_version(7)

    def test_a_table_needing_a_newer_reader_is_refused(self, tmp_path):
        """Deletion vectors mean rows marked deleted without being rewritten.
        A reader that ignores them returns rows that are not there — so the
        protocol requires refusing, and this does."""
        table = tmp_path / "v3"
        (table / "_delta_log").mkdir(parents=True)
        (table / "_delta_log" / "00000000000000000000.json").write_text(
            json.dumps({"protocol": {"minReaderVersion": 3,
                                     "minWriterVersion": 7,
                                     "readerFeatures": ["deletionVectors"]}})
            + "\n")
        opened = maya_deltalake.DeltaTable(str(table))
        with pytest.raises(DeltaProtocolError, match="deletionVectors|reader version"):
            opened.to_pandas()

    @pytest.mark.parametrize("arrow_type", ["duration", "time32", "time64",
                                            "interval"])
    def test_an_unmappable_type_is_refused_rather_than_stringified(self, arrow_type):
        """Delta has no duration, no time-of-day and no interval. A type
        silently mapped to `string` is a column that reads back as text on the
        other implementation, and the first thing anybody does with a feature
        value is arithmetic.

        The first version of this used a LIST as its example, which is now
        supported — so the test was asserting a refusal the code had
        deliberately stopped making. Parameterised over types Delta genuinely
        lacks, so it keeps testing the rule rather than yesterday's boundary.
        """
        import pyarrow as pa

        from maya_deltalake.protocol import delta_type

        unmappable = {"duration": pa.duration("s"), "time32": pa.time32("s"),
                      "time64": pa.time64("us"),
                      "interval": pa.month_day_nano_interval()}[arrow_type]
        with pytest.raises(DeltaProtocolError, match="does not map the Arrow type"):
            delta_type(unmappable)

    def test_a_nested_type_of_something_unmappable_is_refused_too(self):
        """The refusal has to survive nesting, or `[duration]` would be an
        array of a type that does not exist."""
        import pyarrow as pa

        from maya_deltalake.protocol import delta_type

        with pytest.raises(DeltaProtocolError, match="does not map the Arrow type"):
            delta_type(pa.list_(pa.duration("s")))

    def test_an_append_that_does_not_fit_the_schema_is_refused(self, table):
        """The real implementation raises here and MAYA relies on it. Silently
        widening would let a materialisation write columns the contract never
        pinned."""
        maya_deltalake.write_deltalake(table, pd.DataFrame(ROWS))
        with pytest.raises(DeltaProtocolError, match="does not match"):
            maya_deltalake.write_deltalake(
                table, pd.DataFrame([{"entirely": "other"}]), mode="append")

    def test_writing_over_an_existing_table_without_saying_so_is_refused(self, table):
        maya_deltalake.write_deltalake(table, pd.DataFrame(ROWS))
        with pytest.raises(DeltaProtocolError, match="already exists"):
            maya_deltalake.write_deltalake(table, pd.DataFrame(MORE))

    def test_ignore_leaves_it_alone(self, table):
        maya_deltalake.write_deltalake(table, pd.DataFrame(ROWS))
        maya_deltalake.write_deltalake(table, pd.DataFrame(MORE), mode="ignore")
        assert maya_deltalake.DeltaTable(table).version() == 0


class TestShapedFeaturesSurviveBothWays:
    """A yield curve is one feature with `shape: [12]`, a correlation structure
    is `[3, 3]`. Delta describes those as an array and an array of arrays, and
    the first version of this refused them — correctly, since guessing a type
    is worse, but MAYA's whole point about features is that a curve is not ten
    scalars."""

    SHAPED = [{"entity_id": "b1", "vec": [1.0, 2.0, 3.0],
               "mat": [[1.0, 2.0], [3.0, 4.0]], "tag": "x"}]

    def test_an_array_and_a_matrix_round_trip(self, both, table):
        DeltaTable, write = both
        write(table, pd.DataFrame(self.SHAPED))
        back = DeltaTable(table).to_pandas().to_dict("records")[0]
        assert list(back["vec"]) == [1.0, 2.0, 3.0]
        assert [list(row) for row in back["mat"]] == [[1.0, 2.0], [3.0, 4.0]]

    @NEEDS_REAL
    def test_the_shaped_schema_is_written_identically(self, table):
        """Byte-comparable, because a shape recorded differently is a curve
        that arrives with the wrong number of tenors under the other reader."""
        ours, theirs = table + "-o", table + "-t"
        maya_deltalake.write_deltalake(ours, pd.DataFrame(self.SHAPED))
        deltalake.write_deltalake(theirs, pd.DataFrame(self.SHAPED))

        def schema_of(path):
            first = pathlib.Path(path) / "_delta_log" / "00000000000000000000.json"
            return next(json.loads(json.loads(line)["metaData"]["schemaString"])
                        for line in first.read_text().splitlines()
                        if "metaData" in line)

        assert schema_of(ours) == schema_of(theirs)

    @NEEDS_REAL
    def test_the_real_one_reads_our_shaped_values(self, table):
        maya_deltalake.write_deltalake(table, pd.DataFrame(self.SHAPED))
        back = deltalake.DeltaTable(table).to_pandas().to_dict("records")[0]
        assert list(back["vec"]) == [1.0, 2.0, 3.0]
        assert [list(row) for row in back["mat"]] == [[1.0, 2.0], [3.0, 4.0]]


class TestTheLogIsTheRealFormat:
    def test_a_commit_is_one_json_object_per_line(self, table):
        maya_deltalake.write_deltalake(table, pd.DataFrame(ROWS))
        first = pathlib.Path(table) / "_delta_log" / "00000000000000000000.json"
        actions = [json.loads(line) for line in first.read_text().splitlines()]
        kinds = {next(iter(a)) for a in actions}
        assert {"protocol", "metaData", "add", "commitInfo"} <= kinds

    def test_the_commit_filename_is_twenty_digits(self, table):
        """Readers list the directory and sort as STRINGS, so version 10 must
        sort after version 9. The width is part of the format."""
        maya_deltalake.write_deltalake(table, pd.DataFrame(ROWS))
        for _ in range(11):
            maya_deltalake.write_deltalake(table, pd.DataFrame(MORE), mode="append")
        names = sorted(p.name for p in
                       (pathlib.Path(table) / "_delta_log").glob("*.json"))
        assert names[0] == "00000000000000000000.json"
        assert names[-1] == "00000000000000000011.json"
        assert maya_deltalake.DeltaTable(table).version() == 11

    def test_an_overwrite_writes_removes_and_keeps_the_bytes(self, table):
        maya_deltalake.write_deltalake(table, pd.DataFrame(ROWS))
        before = {p.name for p in pathlib.Path(table).glob("*.parquet")}
        maya_deltalake.write_deltalake(table, pd.DataFrame(MORE), mode="overwrite")
        second = pathlib.Path(table) / "_delta_log" / "00000000000000000001.json"
        actions = [json.loads(line) for line in second.read_text().splitlines()]
        assert any("remove" in a for a in actions)
        after = {p.name for p in pathlib.Path(table).glob("*.parquet")}
        assert before < after, "the removed file's bytes stay; that is time travel"

    def test_the_engine_says_which_implementation_wrote_it(self, table):
        """The first question anybody asks of a fallback is which versions it
        wrote, and the log should not need a person to answer it."""
        maya_deltalake.write_deltalake(table, pd.DataFrame(ROWS))
        first = pathlib.Path(table) / "_delta_log" / "00000000000000000000.json"
        info = next(json.loads(line) for line in first.read_text().splitlines()
                    if "commitInfo" in line)["commitInfo"]
        assert "maya_deltalake" in info["engineInfo"]

    def test_a_lost_race_removes_the_file_it_wrote(self, table, monkeypatch):
        """`O_EXCL` is the protocol's concurrency primitive: two writers racing
        for version N means exactly one creates the file. The loser's Parquet
        file is removed rather than left orphaning bytes no commit references.

        Simulated by making the writer compute a STALE next version, which is
        what a competing commit landing between the log read and the commit
        amounts to. Planting a commit beforehand does not simulate this — the
        writer simply sees a table that has advanced and writes the version
        after it, which is correct and is a different situation.
        """
        from maya_deltalake import table as table_module

        maya_deltalake.write_deltalake(table, pd.DataFrame(ROWS))
        before = {p.name for p in pathlib.Path(table).glob("*.parquet")}
        monkeypatch.setattr(table_module, "_latest_version", lambda root: -1)
        with pytest.raises(DeltaProtocolError, match="written by somebody else"):
            maya_deltalake.write_deltalake(table, pd.DataFrame(MORE), mode="append")
        after = {p.name for p in pathlib.Path(table).glob("*.parquet")}
        assert before == after, "the loser's data file was left behind"

    def test_the_table_is_intact_after_a_lost_race(self, table, monkeypatch):
        """The point of removing the loser's file: what is on disk afterwards
        is exactly what the winner committed."""
        from maya_deltalake import table as table_module

        maya_deltalake.write_deltalake(table, pd.DataFrame(ROWS))
        monkeypatch.setattr(table_module, "_latest_version", lambda root: -1)
        with pytest.raises(DeltaProtocolError):
            maya_deltalake.write_deltalake(table, pd.DataFrame(MORE), mode="append")
        monkeypatch.undo()
        opened = maya_deltalake.DeltaTable(table)
        assert opened.version() == 0
        assert len(opened.to_pandas()) == 2


class TestTheBackendIsChosenOnce:
    def test_the_default_prefers_the_real_one_where_it_exists(self):
        """Asked of a fresh process with the environment CLEARED, because the
        suite itself is run a second time with `MAYA_DELTA_BACKEND` set — and
        a test that read this process's already-chosen backend would then be
        asserting the opposite of what it says."""
        import os
        import subprocess
        import sys

        root = pathlib.Path(__file__).resolve().parents[1]
        environment = {k: v for k, v in os.environ.items()
                       if k != "MAYA_DELTA_BACKEND"}
        environment["PYTHONPATH"] = str(root)
        result = subprocess.run(
            [sys.executable, "-c",
             "from db.delta_backend import BACKEND; print(BACKEND)"],
            capture_output=True, text=True, cwd=root, env=environment)
        chosen = result.stdout.strip()
        assert chosen in ("deltalake", "maya_deltalake"), result.stderr[-400:]
        if HAVE_REAL:
            assert chosen == "deltalake", \
                "where the reference implementation is installed, use it"

    def test_the_environment_can_force_ours(self, tmp_path):
        import subprocess
        import sys

        result = subprocess.run(
            [sys.executable, "-c",
             "from db.delta_backend import BACKEND; print(BACKEND)"],
            capture_output=True, text=True,
            cwd=pathlib.Path(__file__).resolve().parents[1],
            env={"PATH": "/usr/bin:/bin", "MAYA_DELTA_BACKEND": "maya_deltalake",
                 "PYTHONPATH": str(pathlib.Path(__file__).resolve().parents[1])})
        assert "maya_deltalake" in result.stdout, result.stderr[-500:]

    def test_an_unknown_backend_is_refused_rather_than_ignored(self, tmp_path):
        """A setting quietly ignored is worse than one not offered."""
        import subprocess
        import sys

        result = subprocess.run(
            [sys.executable, "-c", "import db.delta_backend"],
            capture_output=True, text=True,
            cwd=pathlib.Path(__file__).resolve().parents[1],
            env={"PATH": "/usr/bin:/bin", "MAYA_DELTA_BACKEND": "sqlite",
                 "PYTHONPATH": str(pathlib.Path(__file__).resolve().parents[1])})
        assert result.returncode != 0
        assert "not a Delta backend" in result.stderr

    def test_nothing_imports_deltalake_directly_any_more(self):
        """Three import sites is three places to get the fallback wrong — the
        usual way being that two fall back and the third raises ImportError at
        the moment somebody exports a large table."""
        root = pathlib.Path(__file__).resolve().parents[1]
        offenders = []
        for path in list(root.glob("core/**/*.py")) + list(root.glob("db/*.py")) \
                + list(root.glob("routes/*.py")):
            if path.name == "delta_backend.py":
                continue
            body = path.read_text(encoding="utf-8")
            if "from deltalake import" in body or "import deltalake" in body:
                offenders.append(str(path.relative_to(root)))
        assert offenders == [], (
            "these import deltalake directly rather than through "
            "db/delta_backend.py: " + ", ".join(offenders))

    def test_it_describes_itself_for_health_and_for_a_soak_report(self):
        from db.delta_backend import describe

        described = describe()
        assert described["backend"] in ("deltalake", "maya_deltalake")
        assert isinstance(described["reference_implementation"], bool)
        assert described["detail"]
