"""No screen may render a refusal as "[object Object]".

Three screens each had their own renderer and all three did
`escapeHtml(body.detail)`. On a MAYA refusal `detail` is a sentence and that
works. On a VALIDATION error it is not — FastAPI answers 422 with an ARRAY of
pydantic error objects, and an array of objects rendered as a string is the
literal text `[object Object]`.

So typing a letter into a number box, leaving a required field blank, or
sending a field the schema does not know — the three commonest things a person
does wrong — produced **"Refused — [object Object]"** on every authoring screen
in the platform. The API said exactly which field and why; the interface threw
it away and showed nothing.
"""
from __future__ import annotations

import json
import pathlib
import re
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[1]
JS = ROOT / "web" / "static" / "js"


def _run(script: str) -> str:
    """Evaluate `refusal.js` plus a snippet, under node if it is available."""
    source = (JS / "refusal.js").read_text(encoding="utf-8")
    program = "var window = {};\n" + source + "\n" + script
    out = subprocess.run(["node", "-e", program], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    return out.stdout.strip()


def _node() -> bool:
    return subprocess.run(["which", "node"], capture_output=True).returncode == 0


class TestTheServerActuallySendsTheseShapes:
    """The renderer's job is decided by what the API sends, so pin that first."""

    def test_a_validation_error_is_a_list_of_objects(self, registered, people):
        from tests.conftest import NAME

        r = registered.post(f"/api/v1/models/{NAME}/assess", auth=people["j.okafor"],
                            json={"exposure": "not-a-number",
                                  "purpose_class": "commercial"})
        assert r.status_code == 422
        detail = r.json()["detail"]
        assert isinstance(detail, list) and isinstance(detail[0], dict), \
            "this is the shape that rendered as [object Object]"
        assert detail[0]["loc"][-1] == "exposure" and detail[0]["msg"]

    def test_a_missing_field_is_the_same_shape(self, registered, people):
        from tests.conftest import NAME

        r = registered.post(f"/api/v1/models/{NAME}/assess", auth=people["j.okafor"],
                            json={"exposure": 2e9})
        assert isinstance(r.json()["detail"], list)

    def test_a_maya_refusal_is_a_sentence(self, registered, people):
        from tests.conftest import NAME

        r = registered.post(f"/api/v1/models/{NAME}/assess", auth=people["j.okafor"],
                            json={"exposure": 2e9,
                                  "purpose_class": "regulatory_capital"})
        assert r.status_code == 422
        assert isinstance(r.json()["detail"], str)
        assert r.json()["remediation"], "and it says what to do"


class TestEveryScreenReadsRefusalsTheSameWay:

    def test_nothing_reads_a_refusal_body_except_the_one_reader(self):
        """The defect, as a grep, and scoped to what it actually is.

        Plenty of screens render `something.detail` and that is fine — a PIT
        report and a composition result both carry a `detail` sentence from
        MAYA's own domain objects. The bug was only ever in the REFUSAL path,
        where `detail` may be an array. So the rule is about `responseJSON`:
        nine files each opened one, and all nine got the array wrong.
        """
        offenders = []
        for path in sorted(JS.glob("*.js")):
            if path.name == "refusal.js":
                continue
            for number, line in enumerate(
                    path.read_text(encoding="utf-8").splitlines(), 1):
                if "responseJSON" not in line:
                    continue
                # Passing a synthesised `{responseJSON: ...}` INTO a renderer is
                # a caller, not a second reader of the shape.
                if re.search(r"refusal\(\s*\{\s*responseJSON", line):
                    continue
                offenders.append(f"{path.name}:{number}")
        assert offenders == [], (
            "these open a refusal body themselves instead of going through "
            "`MAYA.refusal.read`, and `detail` is an array on every validation "
            "error: " + ", ".join(offenders))

    def test_every_renderer_goes_through_the_one_reader(self):
        renderers = {"model-algebra.js", "warrant-author.js",
                     "featureset-author-define.js", "featureset-author-bind.js",
                     "featureset-author-assemble.js", "feature-author.js",
                     "ruleset-editor.js", "package.js"}
        for name in renderers:
            body = (JS / name).read_text(encoding="utf-8")
            assert "MAYA.refusal.read" in body, name

    def test_the_reader_loads_on_every_page(self):
        base = (ROOT / "web" / "templates" / "base.html").read_text(encoding="utf-8")
        assert "/static/js/refusal.js" in base, \
            "a shared reader three pages cannot see is three copies again"


class TestTheReaderItself:
    """Run under node where it is available, so the JavaScript is executed
    rather than described."""

    VALIDATION = json.dumps({"detail": [
        {"type": "float_parsing", "loc": ["body", "exposure"],
         "msg": "Input should be a valid number"},
        {"type": "missing", "loc": ["body", "kernel", "input_schema", 0, "dtype"],
         "msg": "Field required"}]})

    def test_a_validation_error_becomes_readable_lines(self):
        if not _node():
            import pytest
            pytest.skip("node is not installed")
        out = _run(
            f"var r = window.MAYA.refusal.read({{responseJSON: {self.VALIDATION},"
            f" status: 422}});"
            "console.log(JSON.stringify(r.lines));")
        lines = json.loads(out)
        assert lines == ["exposure — Input should be a valid number",
                         "kernel.input_schema[0].dtype — Field required"]
        assert "[object Object]" not in out

    def test_a_sentence_detail_is_left_alone(self):
        if not _node():
            import pytest
            pytest.skip("node is not installed")
        body = json.dumps({"error": "fact_not_supplied", "detail": "say which",
                           "remediation": "send it"})
        out = _run(f"var r = window.MAYA.refusal.read({{responseJSON: {body},"
                   " status: 422});"
                   "console.log(JSON.stringify([r.lines, r.code, r.remediation]));")
        assert json.loads(out) == [["say which"], "fact_not_supplied", "send it"]

    def test_a_body_with_nothing_useful_still_says_something(self):
        if not _node():
            import pytest
            pytest.skip("node is not installed")
        out = _run("var r = window.MAYA.refusal.read("
                   "{statusText: 'Bad Gateway', status: 502});"
                   "console.log(JSON.stringify(r.lines));")
        assert json.loads(out) == ["Bad Gateway"]
