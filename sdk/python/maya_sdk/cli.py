"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

A command line, and the one thing it must never let a pipeline do.

`FR-PLT-002` asks for a Python SDK **and** a CLI with notebook and CI
integration. The SDK is the hard half and it was built first. What a CLI adds is
the place a pipeline calls a governance platform from — and that is exactly the
place the platform's whole argument goes to die:

> `mypy || true` is the defect this codebase is named for, and a CI step that
> calls MAYA and ignores its exit code is the same defect with a nicer name.

So the interesting design decision here is not the command surface. It is the
**exit codes**, and specifically that there are three of them:

| | Meaning | What a pipeline should do |
|---|---|---|
| **0** | MAYA answered, and the answer was yes | proceed |
| **1** | MAYA answered, and the answer was **no** | stop; the refusal says why and what to do |
| **2** | MAYA was **not reached**, the command was wrong, or the answer carried no verdict this tool can read | stop, and do not treat this as a verdict |

The separation between 1 and 2 is the whole point. `Refused` and `Unreachable`
are already distinct on the SDK side for the same reason, and collapsing them
here would hand a pipeline the conclusion that **an unreachable register is
compliance**. A build that goes green because the governance platform was down
is worse than one with no gate at all, because somebody believes it.

## What it does not do

**No command suppresses a refusal.** There is no `--force`, no `--yes` and no
`--ignore-errors`: a flag that skipped a refusal would be the one bypass in a
platform whose entire argument is that a refusal means something, and it would be
in the surface most likely to be run unattended.

**It decides nothing.** Every command is one call, rendered. Where an answer
looks like a judgement — *is this ready*, *may this ship* — the judgement was
made by the platform, and this prints it. A CLI that evaluated anything locally
would be a second implementation of a rule, in the copy that ships separately.

**Refusals are printed whole.** Code, detail and **remediation**, on three lines.
The remediation is the half that makes a refusal usable and the half every
wrapper throws away; a CLI that printed `error: refused` would teach people that
this platform's refusals are noise.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from maya_sdk.client import Maya
from maya_sdk.errors import MayaError, Refused, Unreachable

#: MAYA answered and the answer was no. A real result, and a pipeline that
#: cannot tell it from a crash will eventually ship past one.
REFUSED = 1

#: MAYA was not reached, the command was malformed, or a verdict-shaped command
#: came back in a shape this tool cannot read. Never a verdict.
UNREACHABLE = 2

#: The fields a verdict-shaped answer may carry its decision in. If none of them
#: is present the answer is UNDETERMINED, not affirmative — reading an absent
#: verdict as a yes is the same defect as reading an outage as compliance.
VERDICT_FIELDS: Tuple[str, ...] = ("ready", "permitted", "ok", "passed")

#: Read from the environment so a pipeline holds credentials where it already
#: holds credentials, rather than in a command line that ends up in a build log.
ENV = {"url": "MAYA_URL", "user": "MAYA_USER", "password": "MAYA_PASSWORD",
       "token": "MAYA_TOKEN"}


def _client(args: argparse.Namespace) -> Maya:
    return Maya(base_url=args.url or os.environ.get(ENV["url"],
                                                    "http://localhost:5006"),
                username=os.environ.get(ENV["user"], ""),
                password=os.environ.get(ENV["password"], ""),
                api_key=os.environ.get(ENV["token"], ""),
                timeout=args.timeout)


# --------------------------------------------------------------- the commands
#
# Each is (name, help, handler). A handler takes the client and the parsed
# arguments and returns whatever the platform said; printing and exit codes
# happen once, in `main`, so no command can invent its own.
def _whoami(maya: Maya, _args) -> Any:
    return maya.whoami()


def _health(maya: Maya, _args) -> Any:
    return maya.health()


def _models(maya: Maya, args) -> Any:
    return maya.models.get(args.urn) if args.urn else maya.models.list()


def _versions(maya: Maya, args) -> Any:
    return maya.versions.list(args.urn)


def _findings(maya: Maya, args) -> Any:
    """One model's findings, or the estate's ageing view.

    Two different calls rather than one with a filter, because the platform
    answers them differently: for a model it is a list, and across the estate it
    is an ageing analysis. Flattening them here would throw away the half that
    says which of them are overdue.
    """
    return maya.findings.for_model(args.urn) if args.urn \
        else maya.findings.ageing()


def _worklist(maya: Maya, _args) -> Any:
    return maya.call("GET", "/worklist")


def _evidence(maya: Maya, _args) -> Any:
    return maya.verify_evidence()


def _readiness(maya: Maya, args) -> Any:
    """May this model make this move — the answer a pipeline actually wants.

    The judgement is the platform's. This prints it and sets the exit code from
    it, which is the entire contribution of a CLI to a build.
    """
    return maya.lifecycle.readiness(args.urn, transition=args.transition)


def _call(maya: Maya, args) -> Any:
    """The escape hatch, because the API is the product.

    A CLI that only wraps the subjects somebody thought of on the day is one
    people stop using the moment they need the fifth endpoint. Every route is
    reachable here, under the same authentication and the same refusals.
    """
    body = json.loads(args.json) if args.json else None
    # `--absolute` because not everything is under the versioned API:
    # `/health/ready` deliberately is not, since a monitoring probe should not
    # have to track an API version. An escape hatch that could not reach it
    # would send people back to curl on the first thing they tried.
    return maya.call(args.method.upper(), args.path, json=body,
                     absolute=args.absolute)


#: `name, help, arguments, handler, decides` — `decides` marks a command whose
#: ANSWER is a verdict, so a pipeline can gate on its exit code. Everything else
#: exits 0 when the platform answered at all, because "there are four open
#: findings" is a fact and not a failure, and a tool that exited non-zero on a
#: fact is a tool people wrap in `|| true`.
COMMANDS: Tuple[Tuple[str, str, Sequence[Tuple[str, Dict[str, Any]]],
                      Callable[..., Any], bool], ...] = (
    ("whoami", "who this credential is, and what it may do", (), _whoami, False),
    ("health", "whether the platform is up and what it depends on", (),
     _health, False),
    ("models", "the estate, or one model", (("--urn", {"default": ""}),),
     _models, False),
    ("versions", "the versions of one model",
     (("urn", {}),), _versions, False),
    ("findings", "open findings, across the estate or for one model",
     (("--urn", {"default": ""}),), _findings, False),
    ("worklist", "what is waiting on you", (), _worklist, False),
    ("evidence", "verify the evidence chain end to end", (), _evidence, False),
    ("ready", "may this model make this move, and what is missing if not",
     (("urn", {}),
      ("--transition", {"default": "attest"})), _readiness, True),
    ("call", "any endpoint, under the same authentication and refusals",
     (("method", {}), ("path", {}),
      ("--json", {"default": "", "help": "request body, as JSON"}),
      ("--absolute", {"action": "store_true",
                      "help": "the path is not under /api/v1"})),
     _call, False),
)


#: Resolved by name at dispatch time rather than bound into the parser, so the
#: mapping from a command to what it does is one readable thing — and so a test
#: can stand in for one handler without rebuilding the parser.
HANDLERS: Dict[str, Callable[..., Any]] = {
    name: handler for name, _h, _a, handler, _d in COMMANDS}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="maya",
        # Raw, because the exit codes are the point of this help text and
        # argparse's reflow breaks "1 = MAYA refused" across two lines.
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="MAYA — Model & AI Lifecycle Assurance. "
                    "Exit 0 = yes, 1 = MAYA refused, 2 = MAYA was not reached.",
        epilog="Credentials come from the environment: "
               f"{ENV['url']}, {ENV['user']}, {ENV['password']}, "
               f"{ENV['token']}. No flag suppresses a refusal.")
    parser.add_argument("--url", default="", help="platform base url")
    parser.add_argument("--json", action="store_true", dest="as_json",
                        help="print the answer as JSON rather than as text")
    parser.add_argument("--timeout", type=float, default=30.0)
    subs = parser.add_subparsers(dest="command", required=True)
    for name, help_text, arguments, _handler, decides in COMMANDS:
        sub = subs.add_parser(name, help=help_text)
        for flag, options in arguments:
            sub.add_argument(flag, **options)
        sub.set_defaults(decides=decides)
    return parser


# ------------------------------------------------------------------ rendering
def render(answer: Any, as_json: bool) -> str:
    """Readable by default, JSON on request. Never a summary of a refusal."""
    if as_json:
        return json.dumps(answer, indent=2, sort_keys=True, default=str)
    if isinstance(answer, dict):
        return _lines(answer)
    if isinstance(answer, list):
        return "\n".join(_lines(row) if isinstance(row, dict) else str(row)
                         for row in answer)
    return str(answer)


def _lines(row: Dict[str, Any], indent: int = 0) -> str:
    out: List[str] = []
    pad = " " * indent
    width = max((len(str(k)) for k in row), default=0)
    for key, value in row.items():
        if isinstance(value, dict):
            out.append(f"{pad}{key}:")
            out.append(_lines(value, indent + 2))
        elif isinstance(value, list) and value and isinstance(value[0], dict):
            out.append(f"{pad}{key}: [{len(value)}]")
            for item in value[:20]:
                out.append(_lines(item, indent + 2))
                out.append("")
        elif isinstance(value, list):
            out.append(f"{pad}{key.ljust(width)}  "
                       f"{', '.join(str(v) for v in value) or '—'}")
        else:
            out.append(f"{pad}{key.ljust(width)}  {value}")
    return "\n".join(out)


def render_refusal(exc: Refused) -> str:
    """All three parts, always.

    A wrapper that prints `error: refused` has thrown away the half that tells
    somebody what to do, and it teaches them that this platform's refusals are
    noise.
    """
    out = [f"REFUSED ({exc.status}) {exc.code}", f"  {exc.detail}"]
    if exc.remediation:
        out.append(f"  → {exc.remediation}")
    if exc.request_id:
        out.append(f"  [request {exc.request_id}]")
    return "\n".join(out)


def main(argv: Optional[Sequence[str]] = None) -> int:
    """One call, rendered, with the exit code the answer deserves."""
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        maya = _client(args)
        answer = HANDLERS[args.command](maya, args)
    except Refused as exc:
        print(render_refusal(exc), file=sys.stderr)
        return REFUSED
    except Unreachable as exc:
        # NOT the refusal code. A build that went green because the governance
        # platform was down is worse than one with no gate, because somebody
        # believes it.
        print(f"UNREACHABLE  {exc}\n"
              f"  → this is not a verdict. MAYA did not answer, so nothing "
              f"about this model has been established either way",
              file=sys.stderr)
        return UNREACHABLE
    except (MayaError, ValueError) as exc:
        print(f"ERROR  {exc}", file=sys.stderr)
        return UNREACHABLE

    print(render(answer, args.as_json))
    if not getattr(args, "decides", False):
        return 0
    verdict = _verdict(answer)
    if verdict is None:
        # A verdict-shaped command whose verdict field is absent. NOT zero:
        # this tool could not determine what the platform decided, which is the
        # same position as not having reached it — and treating an unreadable
        # answer as a yes is the identical failure to treating an unreachable
        # register as compliance, one layer in.
        print(f"UNDETERMINED  this command asks for a verdict and the answer "
              f"carried none of {', '.join(VERDICT_FIELDS)}\n"
              f"  → not a yes. The platform answered, but not in a shape this "
              f"tool can read, so nothing has been established either way",
              file=sys.stderr)
        return UNREACHABLE
    if not verdict:
        # The command's ANSWER was no. Not an error and not a crash: the
        # platform was reached, it decided, and the decision was negative —
        # which is exactly what a pipeline asked it for.
        return REFUSED
    return 0


def _verdict(answer: Any) -> Optional[bool]:
    """The platform's own verdict, or `None` where there is not one.

    Reads the platform's field rather than inferring anything: `ready` is the
    answer `/lifecycle-readiness` gives, and a CLI deciding readiness from the
    parts would be a second implementation of the rule in the copy that ships
    separately. `None` is a third value on purpose — an absent verdict is not a
    negative one, and it is certainly not an affirmative one.
    """
    if not isinstance(answer, dict):
        return None
    for field in VERDICT_FIELDS:
        if field in answer:
            return bool(answer[field])
    return None


if __name__ == "__main__":               # pragma: no cover - console entry
    sys.exit(main())
