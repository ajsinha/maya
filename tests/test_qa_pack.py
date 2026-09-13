"""
MAYA — the QA pack's examples must be real.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The cheatsheet is handed to testers outside the organisation, and an example
that does not work costs one of them an afternoon and costs the document its
credibility — after the second wrong command nobody trusts the first.

It has happened. Two endpoints in an early draft were invented — a
`/features/{name}/policy` that never existed and a `POST` where the real API
takes a `PUT` — and both were in the document before anybody ran them.

So the Python examples are checked against the SDK's actual surface: every
`maya.<subject>.<method>(...)` in the README must name a subject the client
has, a method that subject defines, and keyword arguments that method accepts.
That is a static check and it cannot prove an example produces the right
answer — `qa_setup.py`, which makes the same calls for real, is the part that
does.
"""
from __future__ import annotations

import ast
import inspect
import pathlib
import re
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
README = ROOT / "docs" / "QA" / "README.md"
sys.path.insert(0, str(ROOT / "sdk" / "python"))

from maya_sdk import Maya

#: Built once. Constructing a client needs no server — the transport is only
#: used when a call is made.
CLIENT = Maya("http://127.0.0.1:1", "x", "y")

#: Names that are locals in an example rather than the client: a second client
#: for another persona, or a value from an earlier step.
OTHER_CLIENTS = {"tester", "service", "mrm", "owner", "validator"}


def python_blocks() -> list:
    """Every ```python fenced block in the cheatsheet."""
    return re.findall(r"```python\n(.*?)```", README.read_text(encoding="utf-8"),
                      re.S)


def sdk_calls():
    """(subject, method, keywords, source) for every SDK call in an example."""
    found = []
    for block in python_blocks():
        try:
            tree = ast.parse(block)
        except SyntaxError as exc:                    # the example does not parse
            found.append(("<syntax>", str(exc), (), block))
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not isinstance(func, ast.Attribute):
                continue
            owner = func.value
            # maya.<subject>.<method>(...)
            if isinstance(owner, ast.Attribute) and \
                    isinstance(owner.value, ast.Name) and \
                    owner.value.id in {"maya"} | OTHER_CLIENTS:
                found.append((owner.attr, func.attr,
                              tuple(k.arg for k in node.keywords if k.arg),
                              block))
            # maya.<method>(...) — whoami, call, health, verify_evidence
            elif isinstance(owner, ast.Name) and \
                    owner.id in {"maya"} | OTHER_CLIENTS:
                found.append(("", func.attr,
                              tuple(k.arg for k in node.keywords if k.arg),
                              block))
    return found


class TestEveryExampleParses:
    def test_the_readme_has_python_beside_its_curl(self):
        """A Windows tester has no bash and no curl, and the pack is handed to
        people outside the organisation."""
        text = README.read_text(encoding="utf-8")
        assert text.count("```python") >= 40, \
            "the Python examples have gone missing from the cheatsheet"
        assert text.count("```bash") >= 40, "so have the curl ones"

    def test_every_python_block_is_valid_python(self):
        broken = []
        for block in python_blocks():
            try:
                ast.parse(block)
            except SyntaxError as exc:
                broken.append(f"line {exc.lineno}: {exc.msg}\n{block[:200]}")
        assert broken == [], "\n\n".join(broken)


class TestEveryExampleNamesSomethingReal:
    """The failure this exists for: an example nobody ran, in a document
    somebody is following instead of asking."""

    def test_every_subject_exists_on_the_client(self):
        missing = sorted({subject for subject, _, _, _ in sdk_calls()
                          if subject and not hasattr(CLIENT, subject)})
        assert missing == [], (
            f"the cheatsheet calls maya.{{{', '.join(missing)}}}, which the "
            f"SDK does not have")

    def test_every_method_exists_on_its_subject(self):
        missing = []
        for subject, method, _, _ in sdk_calls():
            target = getattr(CLIENT, subject) if subject else CLIENT
            if not hasattr(target, method):
                missing.append(f"maya.{subject + '.' if subject else ''}{method}")
        assert missing == [], (
            "the cheatsheet calls these, and the SDK does not define them: "
            + ", ".join(sorted(set(missing))))

    def test_every_keyword_is_one_the_method_accepts(self):
        """A keyword the method does not take is a TypeError the reader meets,
        not the platform — and the reader will assume the platform."""
        wrong = []
        for subject, method, keywords, _ in sdk_calls():
            target = getattr(CLIENT, subject) if subject else CLIENT
            function = getattr(target, method, None)
            if function is None:
                continue
            signature = inspect.signature(function)
            if any(p.kind is p.VAR_KEYWORD
                   for p in signature.parameters.values()):
                continue                              # **kwargs takes anything
            for keyword in keywords:
                if keyword not in signature.parameters:
                    wrong.append(
                        f"maya.{subject + '.' if subject else ''}{method}"
                        f"({keyword}=...) — it takes "
                        f"{', '.join(sorted(signature.parameters))}")
        assert wrong == [], "\n  ".join(sorted(set(wrong)))

    def test_required_arguments_are_supplied(self):
        """`for_fitting` needs a window and an as_of, and an example that omits
        them fails at the reader's terminal rather than here."""
        missing = []
        for subject, method, keywords, _ in sdk_calls():
            target = getattr(CLIENT, subject) if subject else CLIENT
            function = getattr(target, method, None)
            if function is None:
                continue
            required = {
                name for name, p in inspect.signature(function).parameters.items()
                if p.default is p.empty and p.kind is p.KEYWORD_ONLY}
            if absent := sorted(required - set(keywords)):
                missing.append(
                    f"maya.{subject + '.' if subject else ''}{method} omits "
                    f"{', '.join(absent)}")
        assert missing == [], "\n  ".join(sorted(set(missing)))

    def test_the_check_can_fail(self):
        """A validator that passes everything is one nobody can trust."""
        assert not hasattr(CLIENT, "a_subject_nobody_wrote")
        assert not hasattr(CLIENT.models, "a_method_nobody_wrote")


class TestTheSdkDocumentsEverythingItHas:
    """The README's table listed seven subjects while the client had
    twenty-five, which is worse than listing none: a reader concludes the SDK
    cannot do the other eighteen and writes raw calls for things it already
    had.

    That is not hypothetical — a shipped tutorial fell back to `client.call()`
    for methods the SDK defined, and ten governance subjects were once written
    and never attached. The failure is always the same shape: the capability
    exists and nothing tells anybody.
    """

    SDK_README = ROOT / "sdk" / "python" / "README.md"

    @staticmethod
    def _subjects():
        return sorted(name for name in vars(CLIENT)
                      if not name.startswith("_")
                      and name not in ("transport", "api", "last_request_id"))

    def test_every_subject_is_in_the_table(self):
        table = self.SDK_README.read_text(encoding="utf-8")
        missing = [s for s in self._subjects() if f"`maya.{s}`" not in table]
        assert missing == [], (
            "the SDK has these and its README does not mention them: "
            + ", ".join(missing))

    def test_the_table_names_nothing_that_does_not_exist(self):
        """The other direction. A table naming a subject the client dropped
        sends a reader looking for something that is gone."""
        import re

        table = self.SDK_README.read_text(encoding="utf-8")
        named = set(re.findall(r"`maya\.([a-z_]+)`", table))
        real = set(self._subjects())
        # `whoami`, `health`, `verify_evidence` and `call` are methods on the
        # client rather than subjects, and are listed as such.
        methods = {"whoami", "health", "verify_evidence", "call"}
        phantom = sorted(named - real - methods)
        assert phantom == [], (
            "the README names these and the client does not have them: "
            + ", ".join(phantom))

    def test_the_check_would_notice_a_new_subject(self):
        """A guard on the guard: if the client grew a subject tomorrow, the
        first test must fail rather than pass vacuously."""
        assert len(self._subjects()) > 20
        assert "principals" in self._subjects()


class TestTheSetupScriptIsCrossPlatform:
    """`qa-setup.sh` needs bash and curl. A Windows tester has neither, and the
    QA pack is given to people outside the organisation."""

    SCRIPT = ROOT / "docs" / "QA" / "qa_setup.py"

    def test_it_exists_and_is_python(self):
        assert self.SCRIPT.is_file()
        ast.parse(self.SCRIPT.read_text(encoding="utf-8"))

    def test_it_uses_the_sdk_rather_than_raw_http(self):
        """The point of having an SDK. A setup script full of `requests.post`
        would be a worked example of not using the client the product ships."""
        body = self.SCRIPT.read_text(encoding="utf-8")
        assert "from maya_sdk import Maya" in body
        assert "maya.features.define" in body
        assert "maya.models.register" in body
        assert "requests." not in body and "urllib.request" not in body

    def test_it_shells_out_to_nothing(self):
        """`subprocess` here would mean a dependency on some binary, which is
        the thing being escaped."""
        body = self.SCRIPT.read_text(encoding="utf-8")
        assert "subprocess" not in body
        assert "os.system" not in body

    def test_the_readme_offers_it_first(self):
        text = README.read_text(encoding="utf-8")
        assert "python docs/QA/qa_setup.py" in text
        assert text.index("qa_setup.py") < text.index("qa-setup.sh"), \
            "the cross-platform one should be the one a reader meets first"

    @pytest.mark.parametrize("subject,method", [
        ("principals", "define_role"), ("principals", "create"),
        ("features", "define"), ("features", "create_view"),
        ("views", "materialise"), ("views", "versions"),
        ("featuresets", "define"), ("featuresets", "fill"),
        ("models", "register"), ("models", "assess"),
        ("versions", "create"),
    ])
    def test_every_call_it_makes_is_a_real_one(self, subject, method):
        assert hasattr(getattr(CLIENT, subject), method)


class TestTheSetupScriptBuildsTheEstateTheCheatsheetDescribes:
    """Three ways the pack shipped an estate the document did not describe.

    All three were found by running `qa_setup.py` against an empty instance —
    which nobody had, because it had only ever been run against a database that
    already had the model in it.
    """

    PY = ROOT / "docs" / "QA" / "qa_setup.py"
    SH = ROOT / "docs" / "QA" / "qa-setup.sh"

    def test_the_version_is_created_before_the_tier_is_assessed(self):
        """`assess` reads the trainability class off the latest version, and
        refuses where the tier turns on a class it cannot see. Asking for the
        tier first ended the script with `SystemExit(2)`: no version, no
        kernel, and a cheatsheet describing a model that was never built."""
        import ast as _ast
        source = self.PY.read_text(encoding="utf-8")
        tree = _ast.parse(source)
        main = next(n for n in tree.body
                    if isinstance(n, _ast.FunctionDef) and n.name == "main")
        steps = _ast.get_source_segment(source, main) or ""
        assert steps.index("maya.versions.create") < steps.index("tier_once"), \
            "qa_setup.py assesses the tier before creating the version"
        sh = self.SH.read_text(encoding="utf-8")
        assert sh.index("/models/qa.pd.scorecard/versions") \
            < sh.index("/models/qa.pd.scorecard/assess"), \
            "qa-setup.sh assesses the tier before creating the version"

    @pytest.mark.parametrize("username", ["q.tester", "svc/qa-runner", "s.iqbal",
                                          "j.okafor", "a.mehta", "d.raman"])
    def test_it_creates_every_account_the_cheatsheet_signs_in_as(self, username):
        """The document's sign-in table listed people the script never made, so
        every command from section 8 onwards — the approval workflow,
        attestation, alias promotion — answered 401 for a tester following it
        in order."""
        for script in (self.PY, self.SH):
            assert username in script.read_text(encoding="utf-8"), \
                f"{script.name} does not create {username}"
        assert username in README.read_text(encoding="utf-8")

    def test_the_coefficients_are_parameters_and_not_inputs(self):
        """L-W10 asks whether the featureset provides everything
        `input_schema` names. A kernel declaring its own coefficients as inputs
        demands a featureset carrying `intercept`, `beta_dscr` and `beta_ltv` —
        columns no training set has, because they are what training produces.
        Section 9 could not be completed against the estate this built."""
        import ast as _ast
        tree = _ast.parse(self.PY.read_text(encoding="utf-8"))
        kernel = next(node.value for node in tree.body
                      if isinstance(node, _ast.Assign)
                      and getattr(node.targets[0], "id", "") == "KERNEL")
        spec = _ast.literal_eval(kernel)
        inputs = {f["name"] for f in spec["input_schema"]}
        parameters = {f["name"] for f in spec["parameter_schema"]}
        assert inputs == {"dscr", "ltv"}
        assert {"intercept", "beta_dscr", "beta_ltv"} <= parameters
        assert not (inputs & parameters)

    def test_the_shell_twin_declares_the_same_split(self):
        body = self.SH.read_text(encoding="utf-8")
        assert '"parameter_schema"' in body
        head = body[:body.index('"parameter_schema"')]
        assert '"intercept"' not in head[head.index('"input_schema"'):], \
            "the coefficients are still in input_schema in qa-setup.sh"

    def test_the_cheatsheet_shows_the_same_kernel(self):
        text = README.read_text(encoding="utf-8")
        assert '"parameter_schema"' in text
        assert "schema_not_satisfied" in text


    def test_re_running_it_does_not_re_assess_a_tier(self):
        """The second step that is not naturally idempotent. Re-sending the
        same facts is refused — re-running the formula moves the review date
        without anything having been reviewed — so the script asks whether the
        model is tiered and does nothing if it is, rather than routing around
        the refusal with a canned `review_note` claiming a review happened."""
        import ast as _ast
        source = self.PY.read_text(encoding="utf-8")
        tree = _ast.parse(source)
        helper = next((n for n in tree.body
                       if isinstance(n, _ast.FunctionDef) and n.name == "tier_once"),
                      None)
        assert helper is not None, "qa_setup.py re-assesses on every run"
        # The statements only — the docstring explains why `review_note` is
        # NOT used, and a substring check over it would read as the opposite.
        body = [n for n in helper.body
                if not (isinstance(n, _ast.Expr)
                        and isinstance(n.value, _ast.Constant)
                        and isinstance(n.value.value, str))]
        code = "\n".join(_ast.get_source_segment(source, n) or "" for n in body)
        assert '"tier"' in code, "it does not ask whether the model is tiered"
        assert "review_note" not in code, \
            "a setup script asserting that a review happened is the failure " \
            "the same-facts refusal exists to stop"
