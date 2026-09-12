"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Refusal codes quoted in the help, against the ones the platform can raise.

A documentation audit named this **the largest unexamined surface remaining**,
and it is the classic rot in a platform whose whole argument is that a refusal
means something: a code is renamed in the source, the help page keeps quoting
the old one, and a reader who hits the new one finds nothing when they search
for it. Worse is the other direction — a page documenting a refusal the platform
cannot produce, which teaches somebody to expect a control that is not there.

`test_refusal_discipline` already checks that every coded refusal is mapped to a
status. Nothing checked that the codes **printed for users** exist at all.

## The rule on each side, kept narrow on purpose

**In the source**, a refusal code is one of three shapes — raised through an
error class, built as an `"error":` field, or mapped in `routes/base.py`'s status
table. All three are real ways this platform emits one.

**In the help**, a refusal code is a backticked token in a table row that also
carries an **HTTP status**. That is how every refusal table in `content/` is
written, and it is what separates a code from the hundreds of backticked field
names, parameters and column names those pages also contain. A looser rule
produced forty candidates of which six were codes; this one produces no noise,
which is the difference between a check people keep and one they delete.
"""
from __future__ import annotations

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]

#: Pages that speak to a user. The design documents are excluded deliberately:
#: they discuss refusals that were considered and rejected, and a check that
#: could not tell those apart would be one nobody could satisfy.
AUDIENCE = (list((ROOT / "content" / "help").glob("*.md"))
            + list((ROOT / "content" / "tutorials").glob("*.md")))


def _emitted() -> set:
    """Every code this platform can put in front of a caller."""
    source = "\n".join(
        p.read_text(encoding="utf-8")
        for p in list((ROOT / "core").rglob("*.py"))
        + list((ROOT / "routes").glob("*.py"))
        + list((ROOT / "db").rglob("*.py")))
    codes = set(re.findall(r'\(\s*"([a-z][a-z0-9_]+)"\s*,', source))
    # `{"error": "no_captive_engine", ...}` — a refusal built as a dict rather
    # than raised. Missed on the first pass, and it is a real shape.
    codes |= set(re.findall(r'"error"\s*:\s*"([a-z][a-z0-9_]+)"', source))
    # The status table: several codes to a line, so this is not line-anchored.
    codes |= set(re.findall(
        r'"([a-z][a-z0-9_]+)"\s*:\s*\d{3}\b',
        (ROOT / "routes" / "base.py").read_text(encoding="utf-8")))
    return codes


def _quoted() -> dict:
    """Backticked tokens in table rows that also carry an HTTP status."""
    found = {}
    for path in AUDIENCE:
        for number, line in enumerate(path.read_text(encoding="utf-8")
                                      .splitlines(), 1):
            if not line.startswith("|") or not re.search(r"\|\s*[45]\d\d\s*\|",
                                                         line):
                continue
            for token in re.findall(r"`([a-z][a-z0-9]*(?:_[a-z0-9]+)+)`", line):
                found.setdefault(token, []).append(
                    f"{path.relative_to(ROOT)}:{number}")
    return found


def test_every_refusal_code_in_the_help_is_one_the_platform_can_raise():
    """A page documenting a refusal that cannot happen teaches somebody to
    expect a control that is not there."""
    emitted = _emitted()
    wrong = [f"{code} ({', '.join(where)})"
             for code, where in sorted(_quoted().items())
             if code not in emitted]
    assert not wrong, (
        "these refusal codes are documented for users and the platform does "
        "not emit them:\n    " + "\n    ".join(wrong)
        + "\nRename the document to match the source, or delete the row.")


def test_the_check_can_see_all_three_shapes_a_refusal_takes():
    """A guard on the guard. Each of these is emitted a different way, and an
    extractor that missed one would pass by being blind."""
    emitted = _emitted()
    for code in ("quorum_required",        # raised through an error class
                 "no_captive_engine",      # built as an "error" field
                 "feature_refused"):       # mapped in the status table only
        assert code in emitted, f"the extractor cannot see {code}"


def test_the_help_actually_documents_refusals():
    """If the table shape ever changes, this check would silently pass on an
    empty set — which is the failure mode every discipline test here has."""
    quoted = _quoted()
    assert len(quoted) > 30, (
        f"only {len(quoted)} refusal codes found in the help; the table shape "
        f"this reads has probably changed and the check is now vacuous")
