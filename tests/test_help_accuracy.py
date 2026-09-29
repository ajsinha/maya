"""
The in-product help, checked against the code it describes.

Help rots quietly: a setting is renamed, a route moves, a default changes, and the page that
explains it goes on saying the old thing. Everything in the help that can be checked
mechanically is checked here -- every setting it names exists, every default it states in
parentheses is the real default, every REST call it shows is served, every SDK call and CLI
command exists, every repository path it names is there, every metric it names is exported
-- and the configuration reference covers every setting MAYA has.

What cannot be checked this way (that a sentence describes behaviour correctly) is not
claimed to be.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import argparse
import html
import re
import sys
from pathlib import Path

import pytest

from maya.config.schema import SETTINGS
from maya.observability.metrics import METRICS

ROOT = Path(__file__).resolve().parents[1]
PARTS = ROOT / "maya" / "web" / "templates" / "help" / "parts"
GUIDES = ROOT / "maya" / "web" / "guides"
KEYS = {s.key: str(s.default) for s in SETTINGS}
PREFIXES = {k.split(".")[0] for k in KEYS}
# optional files the help tells the reader to create
OPTIONAL = {"config/application.local.yaml", "config/llm_profiles.yaml"}
FAMILIES = ("seams.",)
ROOT_PATHS = {
    "/healthz",
    "/readyz",
    "/metrics",
}  # served beside the API, not under it  # documented as `seams.<name>`
EXTENSIONS = r"\.(py|ya?ml|json|md|csv|toml|sql|txt|j2|html|pdf|db|zip|parquet|xlsx)$"


def _pages() -> list[tuple[str, str]]:
    out = []
    for p in sorted(PARTS.glob("*.html")):
        out.append((p.name, html.unescape(re.sub(r"{#.*?#}", "", p.read_text(), flags=re.S))))
    for p in sorted(GUIDES.glob("*.md")):
        out.append((p.name, p.read_text()))
    return out


PAGES = _pages()


def _code_names() -> set[str]:
    """Every dotted name the code spells as a string: audit actions, events, job types."""
    names: set[str] = set()
    for p in (ROOT / "maya").rglob("*.py"):
        names |= set(re.findall(r'"([a-z_]+\.[a-z_.]+)"', p.read_text(errors="ignore")))
        names |= {f"{a}.*" for a in re.findall(r'f"([a-z_]+)\.\{', p.read_text(errors="ignore"))}
    # f"llm.{provider}.model" builds setting keys, not event names: no wildcard for it
    return names - {"llm.*", "lets.*", "scratch.*"}


def _snippets(text: str) -> list[tuple[int, str]]:
    out = []
    for n, line in enumerate(text.splitlines(), 1):
        for a, b in re.findall(r"`([^`\n]+)`|<code>(.*?)</code>", line):
            out.append((n, re.sub(r"<[^>]+>", "", a or b).strip()))
    return out


def test_every_setting_the_help_names_exists():
    names = _code_names()
    wrong = []
    for page, text in PAGES:
        for n, code in _snippets(text):
            m = re.match(r"^([a-z_]+(?:\.[a-z0-9_]+)+)(?=$|[:=\s])", code)
            if not m or m.group(1).split(".")[0] not in PREFIXES:
                continue
            key = m.group(1)
            if re.search(EXTENSIONS, key) or key.startswith(FAMILIES):
                continue
            known = key in KEYS or key in names or any(k.startswith(key + ".") for k in KEYS)
            dynamic = any(n.endswith(".*") and key.startswith(n[:-1]) for n in names)
            if not (known or dynamic):
                wrong.append(f"{page}:{n} {key}")
    assert wrong == [], "settings the help names that do not exist:\n" + "\n".join(wrong)


def test_every_default_the_help_states_is_the_real_default():
    wrong = []
    words = ("daily", "hourly", "weekly")
    for page, text in PAGES:
        for n, line in enumerate(text.splitlines(), 1):
            for key, val in re.findall(
                r"(?:`|<code>)([a-z_]+(?:\.[a-z0-9_]+)+)(?:`|</code>)\s*\(`?([0-9][^)`]{0,20})`?\)",
                line,
            ):
                if key not in KEYS:
                    continue
                stated = val.strip().split()[0]
                if stated != KEYS[key] and not stated.startswith(words):
                    wrong.append(f"{page}:{n} {key} says ({val}), the default is {KEYS[key]!r}")
    assert wrong == [], "\n".join(wrong)


def _routes() -> list[tuple[re.Pattern[str], set[str]]]:
    sys.path.insert(0, str(ROOT / "tools" / "ci"))
    try:
        from _common import api_app
    finally:
        sys.path.remove(str(ROOT / "tools" / "ci"))
    out = []
    for path, ops in api_app().openapi()["paths"].items():
        p = path.removeprefix("/api/v1")
        out.append(
            (re.compile("^" + re.sub(r"\\\{[^}]+\\\}", "[^/]+", re.escape(p)) + "$"), set(ops))
        )
    return out


def test_every_rest_call_the_help_shows_is_served():
    routes = _routes()
    wrong = []
    for page, text in PAGES:
        for n, line in enumerate(text.splitlines(), 1):
            for method, path in re.findall(
                r"\b(GET|POST|PUT|DELETE|PATCH)\s+`?(/api/v1/[A-Za-z0-9_\-/{}<>:.…]+|/[a-z][A-Za-z0-9_\-/{}<>:.…]+)",
                line,
            ):
                if not path.startswith("/api/") and not page.endswith(".md"):
                    continue
                p = re.sub(r"</?code.*$", "", path).removeprefix("/api/v1").rstrip(".,;:)")
                p = re.sub(r"<[^>]+>|\{[^}]*\}|\.\.\.|…", "X", p.split("?")[0])
                if p in ROOT_PATHS:
                    continue
                if not any(rx.match(p) and method.lower() in ms for rx, ms in routes):
                    wrong.append(f"{page}:{n} {method} {path}")
    assert wrong == [], "REST calls the help shows that are not served:\n" + "\n".join(wrong)


def test_every_sdk_call_and_cli_command_exists():
    import maya.sdk.client as client
    from maya.cli.__main__ import _parser

    bound = dict(
        re.findall(r"self\.(\w+) = (\w+)\(transport\)", (ROOT / "maya/sdk/client.py").read_text())
    )
    cli: dict[str, set[str]] = {}
    for action in _parser()._actions:
        if isinstance(action, argparse._SubParsersAction):
            for group, sub in action.choices.items():
                cli[group] = {
                    c
                    for a in sub._actions
                    if isinstance(a, argparse._SubParsersAction)
                    for c in a.choices
                }
    wrong = []
    for page, text in PAGES:
        for n, line in enumerate(text.splitlines(), 1):
            for attr, method in re.findall(r"\b(?:my|client|sdk)\.([a-z_]+)\.([a-z_]+)\(", line):
                if attr in bound and not hasattr(getattr(client, bound[attr]), method):
                    wrong.append(f"{page}:{n} my.{attr}.{method}()")
            for group, cmd in re.findall(r"python -m maya\.cli\s+([a-z-]+)\s+([a-z-]+)", line):
                if group in cli and cmd not in cli[group]:
                    wrong.append(f"{page}:{n} maya {group} {cmd}")
    assert wrong == [], "\n".join(wrong)


def test_every_repository_path_and_metric_the_help_names_exists():
    described = set(METRICS._help)
    wrong = []
    for page, text in PAGES:
        for n, line in enumerate(text.splitlines(), 1):
            for f in re.findall(
                r"(?<![\w/.~])((?:config|docs|tools|case_studies|maya)/[A-Za-z0-9_\-./]+)", line
            ):
                f = f.rstrip(".,;:)")
                if f in OPTIONAL or any(c in f for c in "<>*{}"):
                    continue
                if not (ROOT / f).exists():
                    wrong.append(f"{page}:{n} {f}")
            for metric in re.findall(r"\bmaya_[a-z_]+\b", line):
                base = re.sub(r"_(bucket|count|sum)$", "", metric)
                if (
                    metric.endswith("_")
                    or not metric.endswith(
                        ("_total", "_seconds", "_bytes", "_info", "_count", "_bucket", "_sum")
                    )
                    and metric not in described
                ):
                    continue  # key prefixes, package names and the like
                if base not in described and metric not in described:
                    wrong.append(f"{page}:{n} {metric}")
    assert wrong == [], "\n".join(wrong)


def test_the_configuration_reference_covers_every_setting():
    text = (GUIDES / "configuration-reference.md").read_text()
    listed = set(re.findall(r"`([a-z_]+(?:\.[a-z0-9_]+)+)`", text))
    # a row may document a pair as `auth.sso.saml.sp_cert` / `sp_cert_file`
    for head, _, tail in re.findall(r"`([a-z_.]+)\.([a-z_]+)` / `([a-z_]+)`", text):
        listed.add(f"{head}.{tail}")
    missing = sorted(k for k in KEYS if k not in listed and not k.startswith("seams"))
    assert missing == [], "settings missing from the configuration reference: " + ", ".join(missing)


@pytest.mark.parametrize("key", ["auth.password.min_length", "auth.password.require_classes"])
def test_the_password_policy_defaults_are_stated_correctly(key):
    """The defaults once drifted in two guides at once; keep them pinned."""
    text = (GUIDES / "configuration-reference.md").read_text()
    assert f"| `{key}` | `{KEYS[key]}` |" in text
