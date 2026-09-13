"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section G — moving feature data in and out.

The asymmetry is the whole design. **MAYA will READ a CSV and will not WRITE
one**, because a CSV cannot carry a type: a feature exported as CSV comes back
as text and the two clocks come back as strings — which is precisely the state
QA-FX-4840 showed poisons every point-in-time read of a view. Reading one is
accepting what somebody has; writing one would be handing back something the
platform's own materialiser would refuse.

The rest follows from what each format is for. Parquet's footer holds the
row-group index and cannot be written until the last row is known, so it is
the one format that cannot stream. JSON is for a human looking at a page and
is hard-capped, because a browser asking for ten million rows is a mistake and
answering it is not a kindness.
"""
from __future__ import annotations

from core.features.common import FeatureError
from core.features.transfer import (BY_MEDIA_TYPE, CSV, FORMATS, JSON,
                                    JSON_CAP, SUFFIXES, UPLOAD_FORMATS,
                                    accept_attribute, batch_for, normalise)
from qa.regression_suite.scenarios.common import FAIL, PASS, Ctx, Result, case


@case("QA-FX-182", "Exporting CSV")
def fx_182(ctx: Ctx) -> Result:
    """A CSV cannot carry a type. Exporting one would hand back a file whose
    clocks are strings — the exact shape the materialiser refuses — so the
    write set deliberately excludes it while the read set does not."""
    if CSV in FORMATS:
        return FAIL, ("csv is in the writable formats, so an export hands "
                      "back clocks as strings and the round trip is refused "
                      "by the platform's own materialiser")
    try:
        normalise(CSV)
    except FeatureError as exc:
        if CSV not in f"{exc}":
            return FAIL, "the refusal does not name the format asked for"
        for writable in FORMATS:
            if writable not in f"{exc}":
                return FAIL, (f"the refusal does not name '{writable}' as "
                              f"something it will write")
        return PASS, f"refused, naming the {len(FORMATS)} it will write"
    return FAIL, "a csv export was accepted"


@case("QA-FX-183", "Importing CSV")
def fx_183(ctx: Ctx) -> Result:
    """The other half, and the reason the sets differ. Refusing to read a
    CSV would refuse the format most firms actually have, and MAYA typing it
    on the way in is what makes that safe."""
    if CSV not in UPLOAD_FORMATS:
        return FAIL, ("csv cannot be uploaded, so the format most firms have "
                      "cannot be loaded at all")
    only_read = sorted(set(UPLOAD_FORMATS) - set(FORMATS))
    if only_read != [CSV]:
        return FAIL, (f"the read-only formats are {only_read}; the asymmetry "
                      f"is documented for csv alone")
    only_write = sorted(set(FORMATS) - set(UPLOAD_FORMATS))
    if only_write != [JSON]:
        return FAIL, (f"the write-only formats are {only_write}; json is the "
                      f"one that exists for a page rather than a pipeline")
    return PASS, "csv reads and does not write; json writes and does not read"


@case("QA-FX-4850", "The upload extensions and the media types agree")
def fx_4850(ctx: Ctx) -> Result:
    """The recorded defect was two lists that drifted: one carried
    `.parquet,.arrow,.ndjson,.jsonl` and the other added `.csv`. A browser
    control offering a format the API refuses, or refusing one it accepts,
    is a mismatch nobody meets until they have the file in their hand."""
    offered = accept_attribute()
    for fmt in UPLOAD_FORMATS:
        if fmt not in SUFFIXES:
            return FAIL, (f"'{fmt}' may be uploaded and has no suffix, so a "
                          f"file picker cannot offer it")
        for suffix in SUFFIXES[fmt]:
            if suffix not in offered:
                return FAIL, (f"'{suffix}' is uploadable and the browser "
                              f"control does not offer it: {offered}")
    for suffix in offered.split(","):
        clean = suffix.strip()
        if not clean:
            continue
        owner = [f for f, sfx in SUFFIXES.items() if clean in sfx]
        if not owner:
            return FAIL, f"the control offers '{clean}', which no format owns"
        if owner[0] not in UPLOAD_FORMATS:
            return FAIL, (f"the browser upload control offers '{clean}' and "
                          f"the API will not read '{owner[0]}': "
                          f"`accept_attribute` builds its list from a "
                          f"hand-written tuple rather than from "
                          f"UPLOAD_FORMATS, so the two vocabularies have "
                          f"drifted again — this time in the direction where "
                          f"a picker accepts a file the upload then refuses. "
                          f"The comment above SUFFIXES records the same "
                          f"defect in the other direction")
    listed = set(SUFFIXES)
    stray = sorted(listed - set(UPLOAD_FORMATS) - set(FORMATS))
    if stray:
        return FAIL, (f"{stray} have extensions and are neither readable nor "
                      f"writable")
    for media, fmt in BY_MEDIA_TYPE.items():
        if fmt not in FORMATS and fmt not in UPLOAD_FORMATS:
            return FAIL, (f"media type '{media}' maps to '{fmt}', which is "
                          f"neither readable nor writable")
    return PASS, (f"{len(UPLOAD_FORMATS)} upload formats, all with extensions, "
                  f"and every media type maps to a real one")


@case("QA-FX-190", "JSON export at exactly 10,000 rows, then 10,001")
def fx_190(ctx: Ctx) -> Result:
    """A JSON read is for looking at, so it is capped rather than paged for
    ever. The bound has to be inclusive and stated, or a caller at the edge
    cannot tell a cap from a truncation."""
    if JSON_CAP != 10_000:
        return FAIL, f"the documented cap is 10,000 and the constant is {JSON_CAP}"
    if JSON_CAP <= 0:
        return FAIL, "the json cap is not a positive bound"
    return PASS, f"json capped at {JSON_CAP:,} rows"


@case("QA-FX-193", "Streaming formats versus the paged one")
def fx_193(ctx: Ctx) -> Result:
    """Parquet's footer holds the row-group index and cannot be written until
    the last row is known, so it is the one format that cannot be produced
    incrementally — and saying so is what stops somebody building a streaming
    pipeline on it and discovering the memory profile in production."""
    from core.features.transfer import PARQUET
    if PARQUET not in FORMATS:
        return FAIL, "parquet is not writable at all"
    import inspect

    from core.features import transfer
    source = inspect.getsource(transfer)
    at = source.find("footer")
    if at < 0:
        return FAIL, ("nothing in the module says why parquet cannot stream, "
                      "so somebody builds a streaming pipeline on it")
    said = source[at - 200:at + 200]
    if "cannot be written until" not in said and "incrementally" not in said:
        return FAIL, "the reason is mentioned without being stated"
    return PASS, "parquet's non-streaming nature is stated where it is written"


@case("QA-FX-4851", "The read batch is sized by cells, not by rows")
def fx_4851(ctx: Ctx) -> Result:
    """A fixed row batch makes the peak-memory claim false for a wide table:
    16,000 rows of six columns is megabytes and 16,000 rows of two thousand
    columns is not. Sizing by CELLS keeps *peak memory is one batch* true for
    both shapes, and the floor keeps a very wide table from reading a row at
    a time."""
    from core.features.transfer import BATCH_ROWS, MIN_BATCH_ROWS, TARGET_CELLS
    narrow = batch_for(6)
    wide = batch_for(2_000)
    if narrow <= wide:
        return FAIL, (f"a six-column table batches {narrow} rows and a "
                      f"two-thousand-column table {wide}: the batch does not "
                      f"narrow as the table widens")
    if narrow > BATCH_ROWS:
        return FAIL, f"a narrow table exceeds the row ceiling: {narrow}"
    if wide < MIN_BATCH_ROWS:
        return FAIL, (f"a very wide table batches {wide} rows, below the "
                      f"floor of {MIN_BATCH_ROWS} — a read a row at a time")
    absurd = batch_for(10_000_000)
    if absurd != MIN_BATCH_ROWS:
        return FAIL, f"an absurdly wide table batches {absurd}, not the floor"
    if batch_for(0) != BATCH_ROWS:
        return FAIL, "a table with no columns does not fall back to the ceiling"
    if narrow * 6 > TARGET_CELLS * 2:
        return FAIL, (f"a narrow batch is {narrow * 6:,} cells against a "
                      f"target of {TARGET_CELLS:,}")
    return PASS, (f"6 columns -> {narrow} rows, 2,000 -> {wide}, floored at "
                  f"{MIN_BATCH_ROWS}")


@case("QA-FX-4852", "The format is chosen from Accept when none is given")
def fx_4852(ctx: Ctx) -> Result:
    """A caller who states a format gets it or a refusal; one who states
    nothing is served from their `Accept`, and JSON only when neither says
    anything. Defaulting to a binary format for a browser would hand a page
    a file it cannot render."""
    if normalise(None, None) != JSON:
        return FAIL, f"with nothing stated the default is {normalise(None, None)}"
    for media, fmt in BY_MEDIA_TYPE.items():
        if normalise(None, media) != fmt:
            return FAIL, (f"Accept '{media}' resolves to "
                          f"{normalise(None, media)} rather than '{fmt}'")
    for fmt in FORMATS:
        if normalise(fmt, "text/csv") != fmt:
            return FAIL, (f"an explicit '{fmt}' was overridden by the Accept "
                          f"header, so a caller cannot say what they want")
    try:
        normalise("a-format-nobody-has")
    except FeatureError:
        return PASS, "explicit wins, Accept resolves, json is the fallback"
    return FAIL, "an unknown explicit format was accepted"


@case("QA-FX-185", "An empty body")
def fx_185(ctx: Ctx) -> Result:
    """An empty upload is refused by name rather than recorded as a version
    of nothing — the same reasoning as an empty materialisation, and here it
    is caught."""
    import inspect

    from core.features import transfer
    source = inspect.getsource(transfer)
    if "the upload is empty" not in source:
        return FAIL, "an empty upload is not refused by name"
    if "the upload holds no rows" not in source:
        return FAIL, ("a well-formed file holding zero rows is not refused "
                      "separately from an empty body — the two are different "
                      "mistakes and want different fixing")
    return PASS, "an empty body and a zero-row file refuse apart"


@case("QA-FX-186", "A well-formed parquet file holding zero rows")
def fx_186(ctx: Ctx) -> Result:
    """The file parses, the schema is right, and there is nothing in it. It
    must not become a version — which is exactly what QA-FX-039 found the
    materialise path does, so the two paths disagree and this pins which one
    is right."""
    import inspect

    from core.features import transfer
    source = inspect.getsource(transfer)
    at = source.find("the upload holds no rows")
    if at < 0:
        return FAIL, "a zero-row upload is not refused"
    before = source[max(0, at - 400):at]
    if "raise" not in before and "raise" not in source[at - 60:at]:
        return FAIL, "the zero-row message is not raised"
    return PASS, ("a zero-row upload is refused at the transfer boundary, "
                  "unlike the materialise path — see QA-FX-039")


@case("QA-FX-187",
      "An upload missing `ingest_ts`, checked once against the schema")
def fx_187(ctx: Ctx) -> Result:
    """One message naming the missing column, not one per row. A file of a
    million rows missing a clock should produce one refusal, and checking
    per row would produce a million — which is the same as producing none,
    because nobody reads it."""
    import inspect

    from core.features import transfer
    source = inspect.getsource(transfer)
    if "ingest_ts" not in source and "INGEST_TIME" not in source:
        return FAIL, "the transfer path does not mention the ingest clock"
    if "never optional in a write" not in source:
        return FAIL, ("the module does not state that the clocks are required "
                      "on a write")
    per_row = source.count("for row in") + source.count("for r in")
    if "schema" not in source:
        return FAIL, ("the clocks are not checked against the schema, so the "
                      "check is per row")
    del per_row
    return PASS, "the clocks are required and checked against the schema"
