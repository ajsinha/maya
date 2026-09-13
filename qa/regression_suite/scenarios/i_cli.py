"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section I — the CLI, which exists to be called from a pipeline.

"A pipeline that calls MAYA and ignores its exit code is the same defect with
a nicer name." So the whole surface reduces to three exit codes and the rule
that decides between them — and the one that matters most is the third: an
answer carrying no verdict is UNDETERMINED, never affirmative, because reading
an absent field as a yes is how a deployment gate silently stops gating.
"""
from __future__ import annotations

import pathlib
import sys

# The SDK ships beside the platform rather than inside it — it is what a
# client installs — so it is not on the path by import alone.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]
                       / "sdk" / "python"))

from maya_sdk.cli import (COMMANDS, REFUSED, UNREACHABLE,
                          VERDICT_FIELDS, build_parser, main)
from qa.regression_suite.scenarios.common import FAIL, PASS, Ctx, Result, case


@case("QA-PLT-367", "The three exit codes are three")
def plt_367(ctx: Ctx) -> Result:
    """0, 1 and 2 must be distinct, or a pipeline cannot tell "MAYA refused"
    from "MAYA could not be reached" — and those call for opposite
    responses."""
    codes = {0: "ok", REFUSED: "refused", UNREACHABLE: "unreachable"}
    if len(codes) != 3:
        return FAIL, (f"the exit codes collide: refused={REFUSED}, "
                      f"unreachable={UNREACHABLE}")
    if REFUSED == 0 or UNREACHABLE == 0:
        return FAIL, "a failure shares the success code"
    return PASS, f"0, {REFUSED}, {UNREACHABLE}"


@case("QA-PLT-366", "An answer with no verdict field")
def plt_366(ctx: Ctx) -> Result:
    """The sharpest case here. A verdict command whose answer carries none of
    the verdict fields must NOT exit 0 — an absent field read as a yes is a
    gate that stopped gating without anybody noticing.
    """
    import inspect
    source = inspect.getsource(main)
    marker = source.find("UNDETERMINED")
    if marker < 0:
        return FAIL, ("nothing reports an absent verdict, so a command "
                      "asking for one may exit 0 on an answer that carried "
                      "none")
    tail = source[marker:marker + 400]
    if f"return {UNREACHABLE}" not in tail and "UNREACHABLE" not in tail:
        return FAIL, (f"an undetermined verdict does not exit "
                      f"{UNREACHABLE}: {tail[:120]}")
    if "return 0" in source[source.find("verdict is None"):marker]:
        return FAIL, "an absent verdict returns 0 before it is reported"
    return PASS, f"an absent verdict is UNDETERMINED and exits {UNREACHABLE}"


@case("QA-PLT-4200", "The verdict fields are a closed list")
def plt_4200(ctx: Ctx) -> Result:
    """A verdict is read from named fields and nothing else. Falling back to
    "any truthy key" would make an unrelated field decide a deployment."""
    if not VERDICT_FIELDS:
        return FAIL, "no verdict fields are declared"
    for field in VERDICT_FIELDS:
        if not field.isidentifier():
            return FAIL, f"'{field}' is not a field name"
    return PASS, f"{len(VERDICT_FIELDS)}: {', '.join(VERDICT_FIELDS)}"


@case("QA-PLT-368", "A non-verdict command against a refusing platform")
def plt_368(ctx: Ctx) -> Result:
    """A refusal is a refusal whether or not the command asked for a
    verdict — the platform said no, and the pipeline has to hear it."""
    import inspect
    source = inspect.getsource(main)
    refusal = source[source.find("except Refused"):][:220]
    # `return REFUSED`, the constant — the literal `1` never appears.
    if "return REFUSED" not in refusal:
        return FAIL, (f"a refusal does not exit {REFUSED}: {refusal[:120]}")
    if "stderr" not in refusal:
        return FAIL, "a refusal is not written to stderr"
    return PASS, f"a refusal exits {REFUSED} on stderr, verdict or not"


@case("QA-PLT-369", "A non-verdict command reporting bad news")
def plt_369(ctx: Ctx) -> Result:
    """Bad news answered successfully is exit 0. A command that reported a
    breach and exited 1 would make every pipeline treat information as
    failure."""
    import inspect
    source = inspect.getsource(main)
    marker = source.find('getattr(args, "decides"')
    if marker < 0:
        return FAIL, "nothing distinguishes a verdict command from a report"
    window = source[marker:marker + 120]
    if "return 0" not in window:
        return FAIL, (f"a non-verdict command does not exit 0 on a rendered "
                      f"answer: {window[:110]}")
    return PASS, "a report exits 0 whatever it says"


@case("QA-PLT-376", "Answers on stdout, refusals on stderr")
def plt_376(ctx: Ctx) -> Result:
    """A pipeline pipes stdout somewhere. A refusal arriving there is a
    refusal parsed as data."""
    import inspect
    source = inspect.getsource(main)
    for phrase in ("except Refused", "except Unreachable"):
        # Long enough to clear the comment block inside the Unreachable
        # branch, which explains at length why it is NOT the refusal code.
        window = source[source.find(phrase):][:900]
        if "stderr" not in window:
            return FAIL, f"{phrase} does not write to stderr"
    rendered = source[source.find("print(render(answer"):][:120]
    if "stderr" in rendered:
        return FAIL, "the rendered answer goes to stderr"
    return PASS, "answers to stdout, both failure paths to stderr"


@case("QA-PLT-370", "An unknown subcommand and a missing positional")
def plt_370(ctx: Ctx) -> Result:
    """argparse's own exit code for a usage error is 2, which is the same
    code as UNREACHABLE — and that is right: in both cases the pipeline
    learned nothing about the model."""
    parser = build_parser()
    for argv in (["no-such-command"], []):
        try:
            parser.parse_args(argv)
        except SystemExit as exc:
            if exc.code not in (UNREACHABLE, 2):
                return FAIL, (f"{argv} exited {exc.code}, not {UNREACHABLE}")
            continue
        return FAIL, f"{argv} was accepted as a command line"
    return PASS, f"a usage error exits {UNREACHABLE}"


@case("QA-PLT-373", "A flag that suppresses a refusal")
def plt_373(ctx: Ctx) -> Result:
    """There must not be one. A `--force` on a governance client is the
    control removed for whoever most wants it removed."""
    text = build_parser().format_help()
    for flag in ("--force", "--ignore", "--no-verify", "--skip",
                 "--allow-failure", "--yes"):
        if flag in text:
            return FAIL, f"the CLI offers {flag}"
    return PASS, "no flag suppresses a refusal"


@case("QA-PLT-374", "A password on the command line")
def plt_374(ctx: Ctx) -> Result:
    """A password in argv is a password in the shell history, in `ps`, and in
    the CI log."""
    text = build_parser().format_help()
    for flag in ("--password", "--secret", "--token", "--api-key"):
        if flag in text:
            return FAIL, (f"the CLI accepts {flag} in argv, so a credential "
                          f"lands in shell history, `ps` and the CI log")
    return PASS, "no credential is accepted on the command line"


@case("QA-PLT-371", "No credentials in the environment")
def plt_371(ctx: Ctx) -> Result:
    """The refusal has to say what to set. A client that fails with
    'unauthorised' when the variable is simply absent sends somebody to the
    wrong problem."""
    import inspect

    from maya_sdk import cli
    source = inspect.getsource(cli._client)
    if "environ" not in source and "getenv" not in source:
        return FAIL, "the client reads no credentials from the environment"
    # The names live in an `ENV` mapping rather than as literals here.
    env = getattr(cli, "ENV", None)
    if not env:
        return FAIL, "no environment variable mapping is declared"
    for key in ("url", "user", "password", "token"):
        if key not in env:
            return FAIL, f"no environment variable for '{key}'"
    return PASS, f"reads {', '.join(sorted(env.values()))}"


@case("QA-PLT-4201", "Every command declares whether it decides")
def plt_4201(ctx: Ctx) -> Result:
    """`decides` is what turns an answer into an exit code. A command where
    it was forgotten silently exits 0 whatever the platform said."""
    undeclared = [row[0] for row in COMMANDS if not isinstance(row[-1], bool)]
    if undeclared:
        return FAIL, f"commands not declaring `decides`: {undeclared}"
    deciding = [row[0] for row in COMMANDS if row[-1]]
    if not deciding:
        return FAIL, "no command decides anything, so the exit codes are unused"
    return PASS, (f"{len(COMMANDS)} commands, {len(deciding)} of them "
                  f"deciding: {', '.join(deciding)}")


@case("QA-PLT-372", "Malformed JSON on the command line")
def plt_372(ctx: Ctx) -> Result:
    """A body that does not parse is a usage error, not a platform one — and
    it must not be sent as a string and refused by the server, which would
    report it as MAYA's problem."""
    # argparse exits by RAISING SystemExit, so a case running a CLI has to
    # catch it or it terminates the whole run — which is how the scenario
    # runner once died at the first tool that behaved correctly.
    try:
        code = main(["call", "POST", "/api/v1/models", "--body", "{not json"])
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else UNREACHABLE
    if code == 0:
        return FAIL, "malformed JSON was accepted"
    if code != UNREACHABLE:
        return FAIL, (f"malformed JSON exited {code}, not {UNREACHABLE}; a "
                      f"usage error reads as a platform refusal")
    return PASS, f"exits {UNREACHABLE}"
