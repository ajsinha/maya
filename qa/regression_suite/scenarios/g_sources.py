"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section G — feature sources: a query the register runs against somebody
else's database.

The control is narrow and the reasoning behind it is what makes it usable: a
source may only READ, and the check is a word-boundary match on the FIRST
keyword rather than a search anywhere, "because `SELECT ... FROM updates` is a
perfectly good query and refusing it would be a control that refuses correct
work — which people then route around".
"""
from __future__ import annotations

from core.features.sources import FORMATS, SQL
from qa.regression_suite.scenarios.common import FAIL, PASS, Ctx, Result, case


def _check(statement: str):
    """Ask the source register whether this statement is a read."""
    # `SourceRegistry`, not `SourceRegister` — and `SourceError` extends
    # `FeatureError`, so catching the base is enough.
    from core.features.common import FeatureError
    from core.features.sources import SourceRegistry
    try:
        SourceRegistry._check_statement(statement)
    except FeatureError as exc:
        return exc
    except AttributeError:
        return "missing"
    return None


@case("QA-FX-5600", "Every write verb is refused")
def fx_5600(ctx: Ctx) -> Result:
    """The whole list, not a sample. A verb left out is a source that can
    change somebody else's database while the register calls it a read."""
    verbs = ("INSERT", "UPDATE", "DELETE", "DROP", "TRUNCATE", "ALTER",
             "CREATE", "GRANT", "REVOKE", "MERGE", "REPLACE", "ATTACH",
             "COPY", "CALL", "EXEC")
    allowed = []
    for verb in verbs:
        outcome = _check(f"{verb} INTO t VALUES (1)")
        if outcome == "missing":
            return FAIL, "there is no statement check to call"
        if outcome is None:
            allowed.append(verb)
    if allowed:
        return FAIL, (f"these statements were accepted as reads: {allowed}")
    return PASS, f"all {len(verbs)} write verbs refused"


@case("QA-FX-5601", "A read whose table is named after a write verb")
def fx_5601(ctx: Ctx) -> Result:
    """"`SELECT ... FROM updates` is a perfectly good query and refusing it
    would be a control that refuses correct work — which people then route
    around." The refusal has to be wrong in neither direction."""
    for statement in ("SELECT * FROM updates",
                      "SELECT id, created FROM deletes WHERE x = 1",
                      "SELECT insert_count FROM metrics",
                      "  SELECT * FROM alter_log  "):
        outcome = _check(statement)
        if outcome == "missing":
            return FAIL, "there is no statement check to call"
        if outcome is not None:
            return FAIL, (f"a legitimate read was refused: {statement!r} "
                          f"({outcome})")
    return PASS, "four reads mentioning write verbs all accepted"


@case("QA-FX-5602", "Leading whitespace and case do not hide a write")
def fx_5602(ctx: Ctx) -> Result:
    """A check anchored to the start of the string is stepped around by a
    newline if it is not written carefully."""
    for statement in ("   delete from t", "\n\tDROP TABLE t",
                      "UpDaTe t SET x = 1", "\n   insert into t values (1)"):
        outcome = _check(statement)
        if outcome == "missing":
            return FAIL, "there is no statement check to call"
        if outcome is None:
            return FAIL, (f"a write was accepted as a read: {statement!r}")
    return PASS, "whitespace and case do not disguise a write"


@case("QA-FX-5603", "A second statement appended to a read")
def fx_5603(ctx: Ctx) -> Result:
    """"A source is one query; a semicolon in the middle is either a mistake
    or somebody appending a second statement to a read." """
    for statement in ("SELECT 1; DROP TABLE t",
                      "SELECT 1 ; DELETE FROM t",
                      "SELECT 1;UPDATE t SET x = 1"):
        outcome = _check(statement)
        if outcome == "missing":
            return FAIL, "there is no statement check to call"
        if outcome is None:
            return FAIL, f"a second statement was accepted: {statement!r}"
    return PASS, "an appended statement is refused"


@case("QA-FX-5604", "A trailing semicolon is not a second statement")
def fx_5604(ctx: Ctx) -> Result:
    """The other direction again. Most SQL clients add one, and refusing it
    would be a control that refuses correct work."""
    for statement in ("SELECT * FROM t;", "SELECT * FROM t ;  ",
                      "SELECT * FROM t;\n"):
        outcome = _check(statement)
        if outcome == "missing":
            return FAIL, "there is no statement check to call"
        if outcome is not None:
            return FAIL, (f"a trailing semicolon was refused: {statement!r} "
                          f"({outcome})")
    return PASS, "a trailing semicolon is accepted"


@case("QA-FX-5605", "An empty statement")
def fx_5605(ctx: Ctx) -> Result:
    """A source that reads nothing is a view that will never materialise, and
    the failure arrives at the first pull rather than at registration."""
    for statement in ("", "   ", "\n\t"):
        outcome = _check(statement)
        if outcome == "missing":
            return FAIL, "there is no statement check to call"
        if outcome is None:
            return FAIL, f"an empty statement was accepted: {statement!r}"
    return PASS, "an empty statement is refused"


@case("QA-FX-5606", "A format that is not one")
def fx_5606(ctx: Ctx) -> Result:
    """The format decides how the bytes are read. An unknown one is a pull
    that fails at the point the data is needed."""
    from core.features.common import FeatureError
    from core.features.sources import SourceRegistry
    try:
        SourceRegistry._check_format("spreadsheet")
    except FeatureError as exc:
        if not any(f in str(exc) + getattr(exc, "remediation", "")
                   for f in FORMATS):
            return FAIL, f"the refusal does not name the formats: {exc}"
        return PASS, f"refused, naming {len(FORMATS)} formats"
    except AttributeError:
        return PASS, ("no separate format check to call; the vocabulary is "
                      f"{sorted(FORMATS)}")
    return FAIL, "an unknown format was accepted"


@case("QA-FX-5607", "The write check is anchored, not a substring search")
def fx_5607(ctx: Ctx) -> Result:
    """The design note, asserted on the construct. A search anywhere would
    refuse correct work; a match with no word boundary would accept
    `DELETEX`."""
    import inspect

    from core.features import sources
    pattern = getattr(sources, "_WRITE", None)
    if pattern is None:
        return FAIL, "there is no write pattern to inspect"
    text = pattern.pattern
    if not text.startswith("^"):
        return FAIL, ("the write check is not anchored to the start, so it "
                      "searches anywhere and refuses correct reads")
    if r"\b" not in text:
        return FAIL, (r"the write check has no \b, so a table called "
                      r"`updates_v2` would be read as an UPDATE")
    doc = " ".join(inspect.getsource(sources)[:4000].split())
    if "route around" not in doc:
        return FAIL, ("the reasoning for the narrow match is not recorded, so "
                      "somebody will widen it")
    return PASS, f"anchored with word boundaries: {text[:40]}…"


@case("QA-FX-5608", "SQL is not the only source kind")
def fx_5608(ctx: Ctx) -> Result:
    """A firm whose features come from files should not have to wrap them in
    a database to register them."""
    if len(FORMATS) < 3:
        return FAIL, f"only {len(FORMATS)} source format(s): {sorted(FORMATS)}"
    if SQL not in str(FORMATS) and SQL not in FORMATS:
        return PASS, f"{len(FORMATS)} file formats, SQL handled separately"
    return PASS, f"{len(FORMATS)} formats: {sorted(FORMATS)}"
