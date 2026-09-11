"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

FR-PLT-002: a command line, and the three exit codes that are the whole point.

The command surface is the easy half. What a CLI adds is the place a pipeline
calls a governance platform from, and that is exactly where the platform's
argument goes to die: `mypy || true` is the defect this codebase is named for,
and a CI step that ignores MAYA's exit code is the same defect wearing a hat.

So these tests are mostly about **1 versus 2**. `Refused` means MAYA answered and
the answer was no. `Unreachable` means MAYA did not answer. Collapsing them hands
a pipeline the conclusion that *an unreachable register is compliance* — a build
that goes green because the governance platform was down, which is worse than no
gate at all because somebody believes it.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "sdk" / "python"))

from maya_sdk.cli import (COMMANDS, HANDLERS, REFUSED, UNREACHABLE,
                          build_parser, main, render, render_refusal)
from maya_sdk.errors import Refused, Unreachable


@pytest.fixture
def run(monkeypatch, client, capsys):
    """`main()` against the real application, in process."""
    from maya_sdk.client import Maya

    class _Transport:
        def request(self, method, path, *, json=None, content=None,
                    params=None, headers=None):
            clean = {k: v for k, v in (params or {}).items() if v is not None}
            return client.request(method, path, json=json, content=content,
                                  params=clean or None, headers=headers,
                                  auth=client.auth)

    monkeypatch.setattr("maya_sdk.cli._client",
                        lambda _args: Maya(transport=_Transport()))

    def _run(*argv):
        code = main(list(argv))
        captured = capsys.readouterr()
        return code, captured.out, captured.err
    return _run


class TestTheThreeExitCodes:
    def test_an_answer_is_zero(self, run):
        code, out, _err = run("health")
        assert code == 0 and out.strip()

    def test_a_refusal_is_one(self, run, monkeypatch):
        monkeypatch.setitem(HANDLERS, "whoami",
                            _raises(Refused(422, "no_tier", "no risk tier",
                                            "assess the model first")))
        code, _out, err = run("whoami")
        assert code == REFUSED
        assert "no_tier" in err

    def test_not_being_reached_is_two_and_not_one(self, run, monkeypatch):
        """The separation is the whole point: a build that went green because
        the governance platform was down is worse than one with no gate."""
        monkeypatch.setitem(HANDLERS, "whoami",
                            _raises(Unreachable("connection refused")))
        code, _out, err = run("whoami")
        assert code == UNREACHABLE
        assert code != REFUSED
        assert "this is not a verdict" in err
        assert "nothing about this model has been established" in err

    def test_the_codes_are_documented_in_the_help(self):
        text = build_parser().format_help()
        assert "1 = MAYA refused" in text and "2 = MAYA was not reached" in text


class TestARefusalIsPrintedWhole:
    def test_all_three_parts_survive(self):
        out = render_refusal(Refused(409, "quorum_required",
                                     "a tier 1 version needs two signatures",
                                     "open an approval at POST /version-approvals"))
        assert "quorum_required" in out
        assert "two signatures" in out
        assert "POST /version-approvals" in out

    def test_the_request_id_is_carried(self):
        out = render_refusal(Refused(409, "x", "y", "z", request_id="req-42"))
        assert "req-42" in out

    def test_a_refusal_goes_to_stderr_not_stdout(self, run, monkeypatch):
        monkeypatch.setitem(HANDLERS, "whoami",
                            _raises(Refused(403, "forbidden", "no", "ask")))
        _code, out, err = run("whoami")
        assert "forbidden" in err and "forbidden" not in out


class TestNoFlagSuppressesARefusal:
    def test_there_is_no_force_or_yes_or_ignore(self):
        text = build_parser().format_help()
        for flag in ("--force", "--yes", "--ignore-errors", "--no-verify"):
            assert flag not in text

    def test_the_help_says_so(self):
        assert "No flag suppresses a refusal" in build_parser().format_help()


class TestItDecidesNothing:
    def test_only_the_verdict_command_gates_on_its_answer(self):
        """Everything else exits 0 when the platform answered at all. "There
        are four open findings" is a fact, and a tool that exited non-zero on a
        fact is a tool people wrap in `|| true`."""
        gating = [name for name, _h, _a, _fn, decides in COMMANDS if decides]
        assert gating == ["ready"]

    def test_a_negative_verdict_exits_one(self, run, monkeypatch):
        monkeypatch.setitem(HANDLERS, "ready",
                            lambda _m, _a: {"ready": False, "missing": ["tier"]})
        code, out, _err = run("ready", "maya://model/x")
        assert code == REFUSED
        assert "missing" in out

    def test_an_affirmative_verdict_exits_zero(self, run, monkeypatch):
        monkeypatch.setitem(HANDLERS, "ready",
                            lambda _m, _a: {"ready": True})
        assert run("ready", "maya://model/x")[0] == 0

    def test_it_reads_the_platforms_own_field(self, run, monkeypatch):
        """Not inferred from the parts. A CLI deciding readiness from what it
        found would be a second implementation of the rule."""
        monkeypatch.setitem(HANDLERS, "ready",
                            lambda _m, _a: {"missing": ["tier", "owner"]})
        assert run("ready", "maya://model/x")[0] == 0


class TestTheEscapeHatch:
    def test_any_endpoint_is_reachable(self, run):
        code, out, _err = run("call", "GET", "/models")
        assert code == 0 and out.strip()

    def test_a_path_outside_the_versioned_api_is_reachable(self, run):
        """`/health/ready` is deliberately not under /api/v1, and an escape
        hatch that could not reach it would send people back to curl."""
        code, out, _err = run("call", "GET", "/health/ready", "--absolute")
        assert code == 0 and out.strip()

    def test_a_path_that_does_not_exist_is_a_refusal_not_a_crash(self, run):
        assert run("call", "GET", "/nothing-here")[0] == REFUSED

    def test_a_body_is_passed_through(self, run, monkeypatch):
        seen = {}
        monkeypatch.setitem(HANDLERS, "call",
                            lambda _m, a: seen.update(json.loads(a.json)) or seen)
        run("call", "POST", "/x", "--json", '{"reason": "because"}')
        assert seen == {"reason": "because"}

    def test_malformed_json_is_two_rather_than_one(self, run):
        """A command this tool could not even send is not a governance
        verdict."""
        assert run("call", "POST", "/x", "--json", "{")[0] == UNREACHABLE


class TestRendering:
    def test_readable_by_default(self):
        out = render({"urn": "maya://model/x", "tier": 1}, as_json=False)
        assert "maya://model/x" in out and "{" not in out

    def test_json_on_request(self):
        out = render({"tier": 1}, as_json=True)
        assert json.loads(out) == {"tier": 1}

    def test_a_list_of_rows_renders_each(self):
        out = render([{"a": 1}, {"a": 2}], as_json=False)
        assert "1" in out and "2" in out

    def test_an_empty_list_renders_without_raising(self):
        assert render([], as_json=False) == ""

    def test_a_nested_answer_keeps_its_shape(self):
        out = render({"band": {"name": "tier-1"}}, as_json=False)
        assert "band:" in out and "tier-1" in out


class TestCredentialsComeFromTheEnvironment:
    def test_the_help_names_the_variables(self):
        text = build_parser().format_help()
        for var in ("MAYA_URL", "MAYA_USER", "MAYA_PASSWORD", "MAYA_TOKEN"):
            assert var in text

    def test_no_password_flag_exists(self):
        """A password on a command line ends up in a build log."""
        assert "--password" not in build_parser().format_help()


def _raises(exc):
    def _fn(_maya, _args):
        raise exc
    return _fn


class TestInANotebook:
    """What a notebook breaks is the refusal, and only the refusal.

    An answer already renders. A `Refused` arrives as a traceback whose last
    line happens to contain the remediation — the half that says what to do,
    in the position nobody reads. People learn from that to treat MAYA's
    refusals as errors, which is exactly the reading this platform exists to
    prevent.
    """

    def test_the_remediation_is_in_the_rendering(self):
        from maya_sdk.notebook import as_html
        out = as_html(Refused(409, "quorum_required", "two signatures",
                              "open an approval at POST /version-approvals"))
        assert "quorum_required" in out
        assert "POST /version-approvals" in out

    def test_unreachable_is_rendered_differently_and_says_it_is_not_a_verdict(
            self):
        """Rendering the two the same way is worth nothing: somebody reading a
        red box concludes MAYA said no, when MAYA said nothing."""
        from maya_sdk.notebook import unreachable_html
        out = unreachable_html(Unreachable("connection refused"))
        assert "not a verdict" in out
        assert "REFUSED" not in out

    def test_it_escapes_what_came_off_the_wire(self):
        from maya_sdk.notebook import as_html
        out = as_html(Refused(422, "x", "<script>alert(1)</script>", ""))
        assert "<script>" not in out and "&lt;script&gt;" in out

    def test_installing_without_a_notebook_does_nothing_and_says_so(self):
        """The SDK has no dependencies on purpose, and a module that made
        `import maya_sdk` require a notebook stack would move that problem into
        every caller."""
        from maya_sdk.notebook import install
        assert install() is False

    def test_it_never_imports_ipython(self):
        """Not by `try`, but by not having the statement at all: if IPython is
        not already in `sys.modules`, this is not a notebook and there is
        nothing to import. `test_import_discipline` walks every import in the
        package, so a guarded one would still be one."""
        import ast
        source = (Path(__file__).resolve().parents[1] / "sdk" / "python" /
                  "maya_sdk" / "notebook.py").read_text(encoding="utf-8")
        named = set()
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Import):
                named |= {a.name for a in node.names}
            elif isinstance(node, ast.ImportFrom):
                named.add(node.module or "")
        assert not {m for m in named if m.split(".")[0] == "IPython"}

    def test_it_still_raises_so_a_scheduled_notebook_does_not_go_green(self):
        from maya_sdk import notebook

        class _Shell:
            def set_custom_exc(self, types, handler):
                self.types, self.handler = types, handler

        shell = _Shell()
        assert notebook.install(shell) is True
        assert set(shell.types) == {Refused, Unreachable}
        with pytest.raises(Refused):
            shell.handler(shell, Refused, Refused(403, "a", "b", "c"), None)

    def test_both_types_are_registered_in_one_call(self):
        """`set_custom_exc` replaces the whole registration rather than adding
        to it, so a second call would silently drop the first."""
        from maya_sdk import notebook

        class _Shell:
            def __init__(self):
                self.calls = []

            def set_custom_exc(self, types, handler):
                self.calls.append(types)

        shell = _Shell()
        notebook.install(shell)
        assert len(shell.calls) == 1

    def test_an_empty_table_does_not_read_as_nothing_existing(self):
        from maya_sdk.notebook import table
        out = table([])
        assert "not the same as nothing existing" in getattr(out, "data", "")
