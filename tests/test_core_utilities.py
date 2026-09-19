"""
The small core pieces everything else leans on: typed configuration accessors
and ${…} resolution, the configuration parsers, the compression seam, log
formatting, and the sandbox runner's in-process helpers.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import json
import logging

import numpy as np
import pytest

from maya.core import compress, config_parsers as cp
from maya.core.properties_configurator import PropertiesConfigurator


@pytest.fixture()
def props(tmp_path, monkeypatch):
    path = tmp_path / "app.properties"
    path.write_text("\n".join([
        "# a comment", "// another", "port = 8600", "ratio=0.25", "flag=yes", "off=Off",
        "num_flag=2", "bad_int=abc", "hosts=a, b ,, c", "ints=1,x,3", "floats=1.5, y, 2",
        "no_ints=x,y", "base=/srv", "path=${base}/data", "missing=${nope}/x",
        "json={\"root\": \"${base}\", \"n\": 1}", "db.main.url=u1", "db.replica.url=u2",
        "not a pair",
    ]) + "\n")
    monkeypatch.setattr("sys.argv", ["pytest"])
    PropertiesConfigurator.reset_instance()
    pc = PropertiesConfigurator([str(path)])
    yield pc, tmp_path
    PropertiesConfigurator.reset_instance()


def test_typed_accessors(props):
    pc, _ = props
    assert pc.get_int("port") == 8600 and pc.get_int("bad_int", 7) == 7
    assert pc.get_int("absent") is None and pc.get_int("absent", 3) == 3
    assert pc.get_float("ratio") == 0.25 and pc.get_float("bad_int", 1.5) == 1.5
    assert pc.get_float("absent", 2.0) == 2.0
    assert pc.get_bool("flag") is True and pc.get_bool("off") is False
    assert pc.get_bool("num_flag") is True and pc.get_bool("bad_int", None) is None
    assert pc.get_bool("absent", True) is True
    assert pc.get_list("hosts") == ["a", "b", "c"] and pc.get_list("absent") is None
    assert pc.get_list("hosts", delim=";") == ["a, b ,, c"]
    assert pc.get_int_list("ints") == [1, 3] and pc.get_int_list("no_ints") is None
    assert pc.get_float_list("floats") == [1.5, 2.0] and pc.get_float_list("absent") is None
    assert pc.get_int_list("absent") is None and pc.get_float_list("no_ints") is None


def test_pattern_queries_and_listing(props):
    pc, _ = props
    assert sorted(pc.get_values_by_pattern(r"db\..*\.url")) == ["u1", "u2"]
    assert pc.get_properties_by_pattern(r"db\.main") == {"db.main.url": "u1"}
    assert pc.get_values_by_pattern("(") == [] and pc.get_properties_by_pattern("(") == {}
    everything = pc.get_all_properties()
    assert everything["port"] == "8600" and "not a pair" not in everything
    assert set(pc.get_all_sources()) >= {"port", "ratio"}


def test_placeholder_resolution_in_strings_files_and_json(props):
    pc, tmp = props
    assert pc.get("path") == "/srv/data"
    assert pc.resolve_string_content("at ${base} and ${base}") == "at /srv and /srv"
    assert pc.resolve_string_content("no placeholders") == "no placeholders"
    assert pc.resolve_string_content("${nope}") == "${nope}"                 # left as-is
    text = tmp / "t.txt"
    text.write_text("root=${base}\n  indented ${base}\n")
    assert pc.load_and_resolve_file_content(text) == ["root=/srv", "  indented /srv"]
    with pytest.raises(FileNotFoundError):
        pc.load_and_resolve_file_content(tmp / "missing.txt")
    assert pc.resolve_string_json_content('{"a": "${base}"}') == {"a": "/srv"}
    js = tmp / "c.json"
    js.write_text('{"dir": "${base}/x", "n": 2}')
    assert pc.load_and_resolve_json_file_content(js) == {"dir": "/srv/x", "n": 2}
    with pytest.raises(ValueError):
        pc.resolve_string_json_content("{not json ${base}")


def test_yaml_flattening_and_parsing(tmp_path):
    flat = cp.flatten_yaml({"a": {"b": 1, "c": True, "d": None},
                            "tags": ["x", "y"], "people": [{"n": "p"}, {"n": "q"}],
                            "mixed": [1, [2, 3]]})
    assert flat["a.b"] == "1" and flat["a.c"] == "true" and flat["a.d"] == ""
    assert flat["tags"] == "x,y" and flat["tags.0"] == "x" and flat["tags.1"] == "y"
    assert "people" not in flat and flat["people.1.n"] == "q"
    assert "mixed" not in flat and flat["mixed.1.0"] == "2"
    assert cp.parse_yaml_text("") == {}
    with pytest.raises(cp.ConfigParseError, match="mapping at its root"):
        cp.parse_yaml_text("- a\n- b\n", source="list.yaml")
    with pytest.raises(cp.ConfigParseError, match="Invalid YAML"):
        cp.parse_yaml_text("a: [unclosed", source="bad.yaml")
    assert cp.detect_format("x.YML") == "yaml" and cp.detect_format("x.conf") == "properties"
    y = tmp_path / "app.yaml"
    y.write_text("server:\n  port: 9000\n")
    assert cp.parse_config_file(str(y)) == {"server.port": "9000"}
    pfile = tmp_path / "app.properties"
    pfile.write_text("a=1\n=nokey\n")
    assert cp.parse_config_file(str(pfile)) == {"a": "1"}


def test_the_default_config_prefers_yaml(tmp_path):
    with pytest.raises(FileNotFoundError):
        cp.find_default_config(str(tmp_path))
    (tmp_path / "application.properties").write_text("a=1\n")
    assert cp.find_default_config(str(tmp_path)).endswith("application.properties")
    (tmp_path / "application.yml").write_text("a: 1\n")
    assert cp.find_default_config(str(tmp_path)).endswith("application.yml")
    (tmp_path / "application.yaml").write_text("a: 1\n")
    assert cp.find_default_config(str(tmp_path)).endswith("application.yaml")


def test_compression_round_trips_under_both_codecs(monkeypatch):
    import zlib
    data = b"maya " * 1000
    assert compress.decompress(compress.compress(data)) == data
    zl = b"MZL1" + zlib.compress(data)
    assert compress.decompress(zl) == data                   # readable whichever codec wrote it
    monkeypatch.setattr(compress.Backends, "selected", staticmethod(lambda seam: "zlib"))
    assert compress.compress(data).startswith(b"MZL1")
    with pytest.raises(ValueError, match="Unknown compression header"):
        compress.decompress(b"XXXX" + data)


def test_procstat_reports_memory_under_either_backend(monkeypatch):
    stats = compress.procstat()
    assert stats["rss_mb"] and stats["rss_mb"] > 0
    monkeypatch.setattr(compress.Backends, "selected", staticmethod(lambda seam: "resource"))
    fallback = compress.procstat()
    assert fallback["rss_mb"] > 0 and fallback["cpu_percent"] is None


def test_json_logs_carry_the_trace_and_exceptions(tmp_path):
    from maya.observability import logs, tracing
    root = logging.getLogger()
    saved = (list(root.handlers), root.level)
    try:
        logfile = tmp_path / "logs" / "maya.log"
        logs.configure("debug", fmt="json", logfile=str(logfile))
        log = logging.getLogger("maya.test")
        with tracing.span("unit") as ctx:
            log.info("hello %s", "world")
        try:
            raise RuntimeError("boom")
        except RuntimeError:
            log.exception("failed")
        for handler in root.handlers:
            handler.flush()
        lines = [json.loads(x) for x in logfile.read_text().splitlines()]
        assert lines[0]["message"] == "hello world" and lines[0]["trace_id"] == ctx.trace_id
        assert lines[1]["level"] == "ERROR" and "RuntimeError: boom" in lines[1]["exc"]
        assert "trace_id" not in lines[1]
        logs.configure("info", fmt="text")
        assert isinstance(root.handlers[0].formatter, logging.Formatter)
        assert not isinstance(root.handlers[0].formatter, logs.JsonFormatter)
    finally:
        root.handlers[:] = saved[0]
        root.setLevel(saved[1])


def test_the_sandbox_runner_helpers():
    from maya.security import sandbox_runner as sr
    assert sr._jsonable({"a": np.arange(3), 1: (np.float64(2.5), [np.int64(4)])}) == \
        {"a": [0, 1, 2], "1": [2.5, [4]]}

    class Model:
        def fit(self, X, y, ctx):
            return {"n": len(X["x"]), "y": y, "seed": ctx.seed}

        def predict(self, X, params, ctx):
            return X["x"] * params["a"]

    ns = {"Model": Model, "fn": lambda X, params: X["x"] + params["b"]}
    fit = sr._call(ns, "Model", {"mode": "fit", "X": {"x": [1, 2]}, "y": [0, 1], "seed": 9})
    assert fit == {"n": 2, "y": [0, 1], "seed": 9}
    pred = sr._call(ns, "Model", {"mode": "predict", "X": {"x": [1, 2]}, "params": {"a": 3}})
    assert pred.tolist() == [3, 6]
    assert sr._call(ns, "fn", {"X": {"x": [1]}, "params": {"b": 1}}).tolist() == [2]
    assert set(sr._DENY) == {"x86_64", "aarch64"} and 59 in sr._DENY["x86_64"][1]   # execve
