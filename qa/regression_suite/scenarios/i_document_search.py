"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section I — searching the corpus, and knowing what the search could not see.

Retrieval here is **exact rather than semantic**, and that is a decision: the
question a supervisor asks is *show me where you wrote that*, and an
approximate answer to it is worse than none, because the reader cannot tell a
miss from an absence.

Which makes `could_not_be_read` and `coverage` the load-bearing half of the
module. A PDF filed and never extracted is invisible to a search, and invisible
is exactly how it looks to somebody who searched and found nothing. Every case
here is about whether the platform can tell those two apart — and about whether
the figure that is supposed to answer that can itself be moved by something
other than filing more readable documents.
"""
from __future__ import annotations

from qa.regression_suite.scenarios.common import (BLOCKED, FAIL, PASS, Ctx,
                                                  Result, case, code_of)

S = "/api/v1/document-search"
A = "/api/v1/attachments"
M = "/api/v1/models"
SHAPE = {"model_class": "logistic", "domain": "credit",
         "legal_entity": "LE-US-01", "purpose": "credit_decision"}


def _model(ctx: Ctx) -> str:
    name = ctx.unique("ds")
    ctx.api.post(M, json={"urn": f"maya://model/{name}", "name": name,
                          "owner": "owner", **SHAPE}, auth=ctx.people["owner"])
    return f"maya://model/{name}"


def _file(ctx: Ctx, urn: str, body: bytes, *, filename: str = "note.txt",
          media: str = "text/plain", title: str = "a filed note", **form):
    data = {"urn": urn, "kind": "vendor_documentation", "title": title,
            "model_level": "true"}
    data.update({k: str(v) for k, v in form.items()})
    return ctx.api.post(A, data=data,
                        files={"file": (filename, body, media)},
                        auth=ctx.people["owner"])


def _search(ctx: Ctx, q: str, **params):
    query = "&".join(f"{k}={v}" for k, v in params.items())
    return ctx.api.get(f"{S}?q={q}" + (f"&{query}" if query else ""),
                       auth=ctx.people["risk"])


def _coverage(ctx: Ctx, auth=None):
    return ctx.api.get(f"{S}/coverage", auth=auth or ctx.people["risk"])


def _engine(ctx: Ctx):
    return ctx.ui.app.state.ctx.get("document_search")


# --------------------------------------------------------------- the refusals
@case("QA-PLT-167", "A search whose query is nothing but stop words")
def plt_167(ctx: Ctx) -> Result:
    """A query of only common words returns the corpus, and refusing it is
    the difference between a search and a dump."""
    from core.docs.search import STOP
    got = _search(ctx, "the%20a%20of")
    if got.status_code < 400:
        body = got.json() or {}
        return FAIL, (f"a query of only stop words was accepted and answered "
                      f"{body.get('matches')} match(es) over "
                      f"{body.get('documents_searched')} document(s)")
    if code_of(got) != "empty_query":
        return FAIL, f"refused '{code_of(got)}' at {got.status_code}"
    if got.status_code != 422:
        return FAIL, f"refused at {got.status_code} rather than 422"
    if "common words are ignored" not in got.text:
        return FAIL, (f"the refusal does not explain why a non-empty query "
                      f"counts as none: {got.text[:160]}")
    single = _search(ctx, "x")
    if single.status_code < 400:
        return FAIL, "a single-character term is not treated as no term"
    return PASS, (f"refused 'empty_query' 422 over {len(STOP)} stop words, "
                  f"and a one-character term too")


@case("QA-PLT-168", "Search `limit` at 0, 200, 201, and `abc`")
def plt_168(ctx: Ctx) -> Result:
    """The framework refuses a non-integer with one body shape and the
    service refuses an out-of-range integer with another. Both are 422, and
    a client parsing refusals has to know which layer answered."""
    from core.docs.search import MAX_LIMIT
    answers = {}
    for value in (0, MAX_LIMIT, MAX_LIMIT + 1, "abc"):
        got = _search(ctx, "model", limit=value)
        answers[str(value)] = (got.status_code, code_of(got), got.text[:80])
    if answers[str(MAX_LIMIT)][0] >= 400:
        return FAIL, f"limit={MAX_LIMIT} was refused: {answers[str(MAX_LIMIT)]}"
    for edge in ("0", str(MAX_LIMIT + 1)):
        if answers[edge][1] != "limit_out_of_range":
            return FAIL, (f"limit={edge} answered '{answers[edge][1]}' rather "
                          f"than 'limit_out_of_range': {answers[edge]}")
    if answers["abc"][0] != 422:
        return FAIL, f"limit=abc answered {answers['abc'][0]}"
    if not answers["abc"][1]:
        return FAIL, (
            f"limit=abc is refused 422 with no `error` code at all "
            f"({answers['abc'][2]!r}), while 0 and {MAX_LIMIT + 1} are refused "
            f"422 with `limit_out_of_range`. Two 422 shapes on one parameter, "
            f"and a client that reads `error` sees nothing on the third")
    return PASS, (
        f"{MAX_LIMIT} accepted; 0 and {MAX_LIMIT + 1} refused "
        f"'limit_out_of_range'; 'abc' refused "
        f"'{answers['abc'][1]}' — every 422 on this parameter carries a code, "
        f"so one client path reads all three")


# ------------------------------------------------------------- what it cannot see
@case("QA-PLT-178", "Search over an estate where nothing is indexed")
def plt_178(ctx: Ctx) -> Result:
    """The case the whole module is written against. An empty result over an
    unread corpus looks identical to an empty result over a read one, and
    only `could_not_be_read` and the detail tell them apart."""
    urn = _model(ctx)
    filed = _file(ctx, urn, b"%PDF-1.4 the capital ratio is 12.4 percent",
                  filename="scan.pdf", media="application/pdf")
    if filed.status_code >= 400:
        return BLOCKED, f"the PDF could not be filed: {filed.text[:150]}"
    got = _search(ctx, "ratio", urn=urn)
    if got.status_code >= 400:
        return BLOCKED, f"the search was refused: {got.text[:150]}"
    body = got.json() or {}
    if body.get("documents_searched") != 0:
        return BLOCKED, (f"{body.get('documents_searched')} document(s) were "
                         f"searched, so this estate is not fully unread")
    if not body.get("could_not_be_read"):
        return FAIL, ("nothing was searched and nothing is listed as unread, "
                      "so an empty answer is indistinguishable from an empty "
                      "corpus")
    unread = body["could_not_be_read"][0]
    if unread.get("media_type") != "application/pdf":
        return FAIL, f"the unread entry does not say what format it is: {unread}"
    if "invisible" not in (body.get("detail") or ""):
        return FAIL, (f"the detail does not say an empty answer means nothing "
                      f"here: {body.get('detail')[:160]}")
    return PASS, (f"0 searched, {len(body['could_not_be_read'])} unread named "
                  f"with their media type, and the detail says so")


@case("QA-PLT-169", "Coverage driven to 1.0 by mislabelling one file")
def plt_169(ctx: Ctx) -> Result:
    """`text_indexed` is `media_type in TEXT_MEDIA`, and the media type is
    whatever the uploader's client declared. So the readable half of the
    corpus is a claim the uploader makes about their own file, and coverage
    is computed from it."""
    urn = _model(ctx)
    binary = b"%PDF-1.4\n\x00\x01\x02 stress \xff\xfe not text at all"
    honest = _file(ctx, urn, binary, filename="honest.pdf",
                   media="application/pdf", title="filed honestly")
    if honest.status_code >= 400:
        return BLOCKED, f"the PDF could not be filed: {honest.text[:150]}"
    before = (_coverage(ctx).json() or {}).get("coverage")
    # Different bytes: the register refuses a second attachment with the same
    # digest, and a case blocked on `already_attached` proves nothing about
    # the media type.
    careless = _file(ctx, urn, binary + b" (second copy)",
                     filename="careless.pdf", media="text/plain",
                     title="filed as text")
    if careless.status_code >= 400:
        return BLOCKED, f"the mislabelled file was refused: {careless.text[:150]}"
    row = careless.json() or {}
    if not row.get("text_indexed"):
        return PASS, ("the register decided for itself that this is not text, "
                      "so the declared media type does not drive coverage")
    after = (_coverage(ctx).json() or {}).get("coverage")
    hit = _search(ctx, "stress", urn=urn)
    found = (hit.json() or {}).get("results") or []
    return FAIL, (
        f"near-identical binary filed twice — as `application/pdf` and as "
        f"`text/plain` — move coverage from {before} to {after}, because "
        f"`text_indexed` is `media_type in TEXT_MEDIA` and the media type is "
        f"whatever the uploading client declared. The mislabelled copy is now "
        f"counted as searchable and its bytes are searched as text "
        f"({len(found)} result(s) for a term inside it). Coverage is the "
        f"figure a reader is told to check BEFORE trusting an empty result, "
        f"and it can be raised by describing a binary badly")


@case("QA-PLT-170", "A genuinely extractable PDF declared honestly")
def plt_170(ctx: Ctx) -> Result:
    """Counted unread, permanently. `text_indexed` is written once, at
    attach, and no route writes it again — so the honest uploader is
    penalised, the careless one rewarded, and no operation changes the
    answer."""
    import inspect

    from core.attachments.register import AttachmentRegister
    urn = _model(ctx)
    filed = _file(ctx, urn, b"%PDF-1.4 the leverage ratio is 4.1 percent",
                  filename="real.pdf", media="application/pdf")
    if filed.status_code >= 400:
        return BLOCKED, f"the PDF could not be filed: {filed.text[:150]}"
    if (filed.json() or {}).get("text_indexed"):
        return PASS, "a PDF is extracted at attach after all"
    source = inspect.getsource(AttachmentRegister)
    writers = [ln.strip() for ln in source.splitlines()
               if "text_indexed" in ln and ("set(" in ln or "=" in ln)
               and "row" not in ln]
    import pathlib
    routes = pathlib.Path("routes").rglob("*.py")
    named = [p.name for p in routes
             if "text_indexed" in p.read_text(encoding="utf-8")]
    if named:
        return PASS, f"a route can change it: {named}"
    return FAIL, (
        f"a text-bearing PDF filed under its true media type is counted "
        f"unread and stays unread: `text_indexed` is written once in "
        f"`attach()` as `media_type in TEXT_MEDIA` and no route in the API "
        f"writes it again — there is no re-index, no extract, no correction. "
        f"The only way to make this document searchable is to file it again "
        f"declaring a media type it does not have, which is the behaviour the "
        f"coverage figure is supposed to discourage. Writers found in the "
        f"register: {writers or 'none besides the insert'}")


@case("QA-PLT-173", "Superseding every unread document with a text note")
def plt_173(ctx: Ctx) -> Result:
    """Coverage counts CURRENT attachments, so superseding an unread PDF
    with a two-line note removes the document the figure was measuring and
    raises it. The number goes up and the corpus gets thinner."""
    urn = _model(ctx)
    pdf = _file(ctx, urn, b"%PDF-1.4 the counterparty limit is 250m",
                filename="policy.pdf", media="application/pdf",
                title="the policy")
    if pdf.status_code >= 400:
        return BLOCKED, f"the PDF could not be filed: {pdf.text[:150]}"
    attachment_id = (pdf.json() or {}).get("id")
    before = _coverage(ctx).json() or {}
    note = _file(ctx, urn, b"superseded; see the policy team",
                 filename="note.txt", media="text/plain",
                 title="a note", supersedes=attachment_id)
    if note.status_code >= 400:
        return BLOCKED, f"the supersession failed: {note.text[:150]}"
    after = _coverage(ctx).json() or {}
    if after.get("coverage", 0) <= before.get("coverage", 0):
        return PASS, (f"coverage did not rise: {before.get('coverage')} → "
                      f"{after.get('coverage')}")
    hit = _search(ctx, "counterparty", urn=urn)
    found = (hit.json() or {}).get("results") or []
    return FAIL, (
        f"superseding an unread PDF with a {len(b'superseded; see the policy team')}-byte "
        f"text note moved coverage from {before.get('coverage')} to "
        f"{after.get('coverage')} ({before.get('unread')} unread → "
        f"{after.get('unread')}) while the content it measured became "
        f"unreachable: a term inside the superseded document now returns "
        f"{len(found)} result(s). The figure a reader is told to check before "
        f"trusting an empty answer is improved by removing the documents it "
        f"was counting")


@case("QA-PLT-171",
      "Coverage on an empty estate versus a principal who can see nothing")
def plt_171(ctx: Ctx) -> Result:
    """"Nothing is filed" and "you may not see what is filed" are opposite
    facts. One is a register with a gap; the other is a reader with a scope,
    and telling them apart is the whole job of this figure."""
    urn = _model(ctx)
    filed = _file(ctx, urn, b"the capital ratio is 12.4 percent")
    if filed.status_code >= 400:
        return BLOCKED, f"nothing could be filed: {filed.text[:150]}"
    who = ctx.unique("scoped")
    made = ctx.api.post("/api/v1/principals",
                        json={"username": who, "display_name": who,
                              "roles": ["model_risk_manager"],
                              "password": f"{who}-pw",
                              "legal_entities": ["LE-XX-99"], "domains": []})
    if made.status_code >= 400:
        return BLOCKED, f"the scoped reader could not be created: {made.text[:150]}"
    blind = _coverage(ctx, auth=(who, f"{who}-pw")).json() or {}
    if blind.get("documents"):
        return BLOCKED, f"the scoped reader can see {blind['documents']} documents"
    engine = _engine(ctx)
    if engine is None:
        return BLOCKED, "no search engine is wired"
    registry = ctx.ui.app.state.ctx["registry"]
    real = type(registry).list
    type(registry).list = lambda self: []
    try:
        empty = engine.coverage(principal=None)
    finally:
        type(registry).list = real
    if blind.get("detail") != empty.get("detail"):
        return PASS, (f"distinguishable: {blind.get('detail')[:60]!r} against "
                      f"{empty.get('detail')[:60]!r}")
    return FAIL, (
        f"an estate with nothing filed and a reader who may see nothing both "
        f"answer coverage {blind.get('coverage')} over "
        f"{blind.get('documents')} document(s) with the identical sentence: "
        f"{blind.get('detail')!r}. The first is a register with a gap and the "
        f"second is a scope doing its job; a reader told the first when the "
        f"truth is the second concludes the bank has filed nothing")


@case("QA-PLT-172", "Coverage against a `kind`- or `urn`-filtered search")
def plt_172(ctx: Ctx) -> Result:
    """The pairing has to be honest. `search` narrows by `urn` and `kind`;
    `coverage` takes neither and the route passes neither — so "nothing
    matches" sits next to a figure computed over a different corpus."""
    import inspect

    from core.docs.search import DocumentSearch
    signature = inspect.signature(DocumentSearch.coverage)
    narrowing = [p for p in signature.parameters if p in ("urn", "kind")]
    urn = _model(ctx)
    other = _model(ctx)
    if _file(ctx, other, b"the capital ratio is 12.4 percent").status_code >= 400:
        return BLOCKED, "the readable document could not be filed"
    if _file(ctx, urn, b"%PDF-1.4 nothing readable", filename="x.pdf",
             media="application/pdf").status_code >= 400:
        return BLOCKED, "the unreadable document could not be filed"
    found = _search(ctx, "ratio", urn=urn).json() or {}
    figure = _coverage(ctx).json() or {}
    if narrowing:
        return PASS, f"coverage narrows by {narrowing}"
    if figure.get("coverage", 0) == 0:
        return BLOCKED, "the estate-wide figure is zero, so nothing is implied"
    return FAIL, (
        f"a search narrowed to one model answers {found.get('matches')} "
        f"match(es) over {found.get('documents_searched')} document(s) "
        f"searched and {len(found.get('could_not_be_read') or [])} unread, "
        f"while `GET {S}/coverage` — the figure the search's own detail line "
        f"tells a reader to check first — answers {figure.get('coverage')} "
        f"over {figure.get('documents')} document(s) across the whole estate. "
        f"`coverage()` takes no `urn` and no `kind`, and the route passes "
        f"neither, so the two numbers are about different corpora and nothing "
        f"says so")


@case("QA-PLT-174", "A quarantined or rejected attachment in the search results")
def plt_174(ctx: Ctx) -> Result:
    """`_candidates` yields every current attachment regardless of state, so
    a document the register REJECTED is still searched and its text still
    quoted back — with `state` on the hit, which is honest but not a filter."""
    from core.attachments.common import STATES
    urn = _model(ctx)
    filed = _file(ctx, urn, b"the rejected figure is 99.9 percent",
                  title="a rejected note")
    if filed.status_code >= 400:
        return BLOCKED, f"the document could not be filed: {filed.text[:150]}"
    attachment_id = (filed.json() or {}).get("id")
    rejected = ctx.api.post(f"{A}/{attachment_id}/review",
                            json={"accept": False,
                                  "note": "wrong figure, do not use"},
                            auth=ctx.people["validator"])
    if rejected.status_code >= 400:
        return BLOCKED, f"the document could not be rejected: {rejected.text[:150]}"
    got = _search(ctx, "99.9", urn=urn)
    if got.status_code >= 400:
        return BLOCKED, f"the search was refused: {got.text[:150]}"
    results = (got.json() or {}).get("results") or []
    mine = [r for r in results if r.get("attachment_id") == attachment_id]
    if not mine:
        return PASS, ("a rejected document is excluded from search results")
    hit = mine[0]
    return FAIL, (
        f"a document the register rejected — state {hit.get('state')!r}, "
        f"reviewed with 'wrong figure, do not use' — is returned by search "
        f"with its text quoted back: {hit.get('quote')[:70]!r}. "
        f"`_candidates` yields every current attachment and filters only on "
        f"`kind`, so none of the {len(STATES)} states narrows the corpus. The "
        f"hit carries `state`, which is honest and is not a filter: a reader "
        f"searching for a figure finds the one the bank refused")


@case("QA-PLT-176", "A search run with no principal while an authoriser is wired")
def plt_176(ctx: Ctx) -> Result:
    """`scoped` reports the WIRING, not whether scoping ran. A response that
    says it was scoped and was not is the leak the scope check exists
    against, wearing the label of the control."""
    engine = _engine(ctx)
    if engine is None:
        return BLOCKED, "no search engine is wired"
    if engine.authz is None:
        return BLOCKED, "no authoriser is wired into the search"
    urn = _model(ctx)
    if _file(ctx, urn, b"the capital ratio is 12.4 percent").status_code >= 400:
        return BLOCKED, "nothing could be filed"
    out = engine.search("ratio", principal=None)
    if not out.get("scoped"):
        return PASS, ("`scoped` is false when no principal was applied, so it "
                      "reports the filtering rather than the wiring")
    if not out.get("results"):
        return BLOCKED, "the unscoped search found nothing to leak"
    return FAIL, (
        f"`search(principal=None)` with an authoriser wired returned "
        f"{len(out['results'])} result(s) across "
        f"{out.get('documents_searched')} document(s) — `_visible` applies the "
        f"filter only `if self.authz is not None and principal is not None`, "
        f"so nothing was filtered — and the answer reports `scoped: true`, "
        f"because that flag is `self.authz is not None`. It describes the "
        f"wiring. A caller reading it concludes the estate was narrowed to "
        f"them when the whole corpus was searched")


@case("QA-PLT-175", "A search with `limit=1` over many matches")
def plt_175(ctx: Ctx) -> Result:
    """`matches` is the total before the page and `results` is the page. A
    client that renders `matches` as the number of rows it received is wrong
    by everything it did not ask for — so the two must be visibly different
    numbers on one answer."""
    urn = _model(ctx)
    for n in range(6):
        made = _file(ctx, urn, f"the liquidity ratio is {n}.4 percent".encode(),
                     filename=f"note{n}.txt", title=f"note {n}")
        if made.status_code >= 400:
            return BLOCKED, f"note {n} could not be filed: {made.text[:130]}"
    got = _search(ctx, "liquidity", urn=urn, limit=1)
    if got.status_code >= 400:
        return BLOCKED, f"the search was refused: {got.text[:150]}"
    body = got.json() or {}
    if len(body.get("results") or []) != 1:
        return FAIL, (f"limit=1 returned {len(body.get('results') or [])} "
                      f"result(s)")
    if body.get("matches") != 6:
        return FAIL, (f"six documents match and `matches` reports "
                      f"{body.get('matches')} — the total is not pre-limit")
    if body.get("documents_searched", 0) < 6:
        return FAIL, (f"only {body.get('documents_searched')} document(s) were "
                      f"searched")
    return PASS, (f"matches {body['matches']} over "
                  f"{body['documents_searched']} searched, one row returned")


@case("QA-PLT-177", "Two documents, one term, wildly different densities")
def plt_177(ctx: Ctx) -> Result:
    """The occurrence component is capped at 999, so beyond the cap two
    documents of very different relevance rank by title. Reported rather
    than called wrong — a cap is a defensible choice — but a tie broken
    alphabetically is not a ranking anybody can defend to a supervisor."""
    from core.docs.search import _match  # noqa: F401  (reachability)
    urn = _model(ctx)
    thin = ("basel " * 1000).encode()
    thick = ("basel " * 100000).encode()
    a = _file(ctx, urn, thin, filename="a.txt", title="aaa thin")
    b = _file(ctx, urn, thick, filename="b.txt", title="zzz thick")
    if a.status_code >= 400 or b.status_code >= 400:
        return BLOCKED, "the two documents could not be filed"
    got = _search(ctx, "basel", urn=urn)
    if got.status_code >= 400:
        return BLOCKED, f"the search was refused: {got.text[:150]}"
    results = (got.json() or {}).get("results") or []
    scores = {r["title"]: r["score"] for r in results}
    if len(scores) < 2:
        return BLOCKED, f"only {len(scores)} result(s): {scores}"
    if scores.get("aaa thin") != scores.get("zzz thick"):
        return PASS, f"the two rank differently: {scores}"
    first = results[0]["title"]
    return FAIL, (
        f"a document mentioning the term a thousand times and one mentioning "
        f"it a hundred thousand times score identically ({scores}) — the "
        f"occurrence component is `min(occurrences, 999)`, so both saturate — "
        f"and the tie is broken by `h['title']`, which put {first!r} first. "
        f"Best-match-first is the promise on the route; past the cap the order "
        f"is alphabetical and nothing says so")


# ------------------------------------------------------------------ the share
def _fresh_share(ctx: Ctx, sharing, urn: str, attempt: int):
    """One share per round. A round that reused the previous share would be
    refused `share_exhausted` by the first round's successful read, which is
    the cap working and not the race being run."""
    try:
        made = sharing.share(urn, recipient=f"an examiner {attempt}",
                             purpose="review", max_reads=1,
                             content_digest="sha256:" + "a" * 64, actor="qa")
    except Exception:
        return ""
    return made.get("reference") or (made.get("share") or {}).get("reference")


@case("QA-PLT-160", "Ten concurrent reads of a `max_reads: 1` share",
      isolated=True)
def plt_160(ctx: Ctx) -> Result:
    """The counter is a read-modify-write with no lock, and a leaked link is
    exactly the condition that produces simultaneous reads. A cap that holds
    only when nobody races it is not a cap."""
    import inspect
    from concurrent.futures import ThreadPoolExecutor

    from core.export.sharing import ExportSharing
    source = inspect.getsource(ExportSharing.open_share)
    if 'set({"reads": share["reads"] + 1}' not in source:
        return PASS, "the counter is no longer a read-modify-write"
    sharing = ctx.ui.app.state.ctx.get("export_sharing")
    if sharing is None:
        return BLOCKED, "no sharing service is wired"
    urn = _model(ctx)
    try:
        share = sharing.share(urn, recipient="an examiner", purpose="review",
                              max_reads=1, content_digest="sha256:" + "a" * 64,
                              actor="qa")
    except Exception as exc:
        return BLOCKED, f"the share could not be created: {exc}"
    reference = share.get("reference") or (share.get("share") or {}).get("reference")
    if not reference:
        return BLOCKED, f"the share carries no reference: {sorted(share)}"
    # ROUNDS, not one race. Ten threads against an unguarded read-modify-write
    # win or lose on timing: three runs of this case served 1, then 5, then 2
    # of ten. A case that reports a control working because the scheduler
    # happened to serialise it is exactly the false pass this pass exists to
    # find, so the race is run repeatedly and the WORST round is the answer.
    rounds, worst, seen = 5, 0, []
    for attempt in range(rounds):
        reference = _fresh_share(ctx, sharing, urn, attempt)
        if not reference:
            return BLOCKED, "a share could not be created"
        served, refused = [], []

        def read(_n, ref=reference, s=served, r=refused):
            try:
                sharing.open_share(ref, seen_from="qa")
                s.append(1)
            except Exception as exc:
                r.append(getattr(exc, "code", type(exc).__name__))

        with ThreadPoolExecutor(max_workers=10) as pool:
            list(pool.map(read, range(10)))
        seen.append(len(served))
        worst = max(worst, len(served))
    if worst <= 1:
        return PASS, (
            f"the cap held across {rounds} rounds of ten simultaneous reads "
            f"(served {seen}). Read what held it — `open_share` is still a "
            f"read-modify-write with no lock and no conditional update, and "
            f"what serialised these was the database's own write lock under "
            f"one process. ADR-016 chooses that topology, so the cap is safe "
            f"where MAYA is deployed as specified and rests on the deployment "
            f"rather than on this code")
    return FAIL, (
        f"a share capped at one read served {worst} of ten simultaneous reads "
        f"at worst across {rounds} rounds (served {seen}). "
        f"`open_share` reads `share['reads']` "
        f"before the state check and writes `reads + 1` after serving, with no "
        f"lock and no conditional update — racers that read the same count "
        f"all pass the cap and all serve. `max_reads` is the control "
        f"a firm relies on when a link has gone somewhere it should not, and "
        f"a leaked link is precisely the condition that produces concurrent "
        f"reads")


# ------------------------------------------------------- the documentation graph
@case("QA-PLT-179",
      "A markdown link in the shipped documentation that resolves to a 500")
def plt_179(ctx: Ctx) -> Result:
    """The crawler treats anything that is not a 404 as fine, so a
    documentation set whose targets all error passes. 3xx is genuinely a
    pass — it is a redirect to sign-in — and 5xx is not."""
    import inspect

    from tests import test_documentation_links as crawler
    source = inspect.getsource(
        crawler.TestTheServedLinks.test_every_absolute_link_is_a_route_this_app_answers)
    if "500" in source or "< 500" in source or "server error" in source.lower():
        return PASS, "the crawler distinguishes a server error from a redirect"
    if "== 404" not in source and "!= 404" not in source:
        return BLOCKED, "the crawler no longer keys on 404"
    path = f"/qa-documentation-target-{ctx.unique('x')}"

    @ctx.ui.app.get(path)
    def broken():
        raise RuntimeError("this documentation target errors")

    got = ctx.api.get(path, auth=ctx.people["risk"])
    if got.status_code < 500:
        return BLOCKED, f"the probe route answered {got.status_code}"
    return FAIL, (
        f"`tests/test_documentation_links.py` asks each absolute link for its "
        f"status and fails only on 404 — the comment says 3xx means the route "
        f"exists, which is right, and a {got.status_code} is treated the same "
        f"way. A documentation set every one of whose targets raises would "
        f"pass this crawler, and the reader following a link gets an error "
        f"page rather than the page the documentation promised. The check "
        f"that exists to stop a reader concluding the documentation is "
        f"unmaintained cannot see the state that most looks that way")
