"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

A reference EUC scanner, and the reason it lives in `tools/` rather than `core/`.

## Why this is not part of the platform

MAYA does not crawl the bank's drives, and the argument has never been about
effort. A sweep needs read access to every shared drive, notebook server,
repository and mailbox in the institution — the broadest standing access anybody
holds — and granting it to the governance register would hand the system whose
whole argument is that it holds no standing power the largest standing power in
the building.

So the crawl runs **where the data is, under whoever already has the access**,
and hands the result over. `core/discovery/contract.py` publishes what a sweep
must carry. This is a scanner that satisfies that contract: a worked reference a
firm can run as-is, read, or replace with their own.

It imports nothing from `core/`. That is deliberate and is checked by a test —
a scanner that shared code with the register it reports to is a scanner whose
findings are partly the register's own opinion, and the precision figure the
register computes would then be grading itself.

## What it looks for, and what it will not claim

Spreadsheets, notebooks and loose scripts that **behave like models**: a formula
that fits or projects, a regression call, a hard-coded coefficient table, a
scoring loop. Each match is evidence a person can check, and the evidence is
carried on the candidate rather than summarised — a triager needs to see
`=LINEST(` and the sheet it was on, not a similarity score.

Three things it refuses to do, each of which is how a discovery programme dies.

**It does not decide.** Every candidate is a candidate. `confidence` is capped
strictly below certainty, because finding a regression formula is evidence that
somebody built something and not evidence that it is a model in the governed
sense — that determination belongs to triage and needs facts no file holds.

**It does not read content it cannot justify reading.** The matchers run over
formulas, code and cell text. Nothing here opens a mailbox, nothing follows a
network share it was not pointed at, and the `--scope` it was given is recorded
verbatim so the sweep's coverage is a stated claim rather than an assumption.

**It does not claim recall.** `recall_known` is false and always will be. A
scanner cannot know what it did not look at, and the register grades precision
from triage outcomes rather than taking the scanner's word for anything.

## Running it

    python -m tools.scanner.sweep /mnt/finance /mnt/risk \\
        --scanner euc-sweep --scope "finance and risk shares, not archive" \\
        --out sweep.json

    python -m tools.scanner.sweep ... --submit https://maya.internal \\
        --api-key "$MAYA_API_KEY"

`--out` writes the document; `--submit` posts it to
`/api/v1/scanner-contract/ingest`. Writing first and posting second is the
ordinary way to run this: a sweep is worth keeping, and a scanner that only ever
posted would make its own output unreviewable.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

#: The name this scanner reports itself under. Stable on purpose: the register
#: computes precision per scanner, and one that renames itself between sweeps
#: has no history to compute it over.
SCANNER = "euc-sweep"

#: What is opened at all. A sweep that tried every file on a share would spend
#: its time on images and its findings on nothing.
EXTENSIONS = {
    ".xlsx": "spreadsheet", ".xlsm": "spreadsheet", ".xls": "spreadsheet",
    ".csv": "data", ".ipynb": "notebook", ".py": "script", ".r": "script",
    ".R": "script", ".sas": "script", ".sql": "script", ".m": "script",
}

#: Files above this are skipped and **counted**, not silently ignored. A sweep
#: that quietly dropped the largest workbooks would report high precision over
#: the easy half of the estate.
MAX_BYTES = 64 * 1024 * 1024

#: Directory names never descended into. Each would produce candidates that are
#: real files and not anybody's model.
SKIP_DIRS = frozenset({
    ".git", ".svn", "node_modules", "__pycache__", ".venv", "venv",
    "site-packages", ".ipynb_checkpoints", ".tox", "dist", "build",
})

#: What a match is worth. Deliberately none of them is 1.0 — see the module
#: docstring. The numbers are a triage ORDER rather than a probability, and the
#: contract requires them strictly below certainty for exactly that reason.
SIGNALS: Tuple[Tuple[str, str, float, str], ...] = (
    ("regression", r"\bLINEST\s*\(|\bLOGEST\s*\(|\bTREND\s*\(|\bFORECAST[.\w]*\s*\(",
     0.75, "a spreadsheet formula that FITS a relationship. This is the "
           "clearest signal there is: somebody estimated parameters here"),
    ("solver", r"\bSolver(?:Ok|Solve|Add)\b|\bGoalSeek\b",
     0.7, "an optimiser was run over this sheet, which means parameters were "
          "chosen to fit something"),
    ("statistics", r"\bNORM\.?S?\.?(?:DIST|INV)\s*\(|\bSTDEV[.\w]*\s*\(|"
                   r"\bCORREL\s*\(|\bPERCENTILE[.\w]*\s*\(",
     0.5, "distributional arithmetic. Common in reporting too, which is why "
          "this scores lower than a fit"),
    ("scorecard", r"\bVLOOKUP\s*\(|\bXLOOKUP\s*\(|\bINDEX\s*\([^)]*MATCH\s*\(",
     0.45, "a lookup table applied row by row, which is what a scorecard is "
           "when it lives in a spreadsheet"),
    ("ml_library", r"\b(?:sklearn|statsmodels|xgboost|lightgbm|catboost|torch|"
                   r"tensorflow|keras|prophet|pmdarima)\b",
     0.8, "a modelling library is imported. In a script this is close to "
          "conclusive that something was fitted"),
    ("fit_call", r"\.\s*fit\s*\(|\bglm\s*\(|\blm\s*\(|\bPROC\s+(?:REG|LOGISTIC|"
                 r"GLM|HPLOGISTIC)\b|\bols\s*\(",
     0.8, "an explicit fit. The verb is the evidence"),
    ("predict_call", r"\.\s*predict(?:_proba)?\s*\(|\bSCORE\s+DATA\s*=",
     0.65, "something is being scored, so a fitted object exists somewhere "
           "even if it is not in this file"),
    ("coefficients", r"(?i)\b(?:coefficient|beta_|intercept|weight[s]?_|"
                     r"odds[_ ]ratio|log[_ ]odds|scorecard|pd_|lgd_|ead_)\w*",
     0.4, "vocabulary that names model parameters. Weak alone and useful "
          "alongside anything else"),
)

#: Two matches from different families are worth more than two of the same.
#: One `VLOOKUP` is a lookup; a `VLOOKUP` beside a `LINEST` is a scorecard being
#: applied to a fitted relationship.
FAMILY_BONUS = 0.08

#: The ceiling. The contract requires confidence strictly below 1.0 and this
#: stays well under it, because the gap between "this file contains a
#: regression" and "this is a model the bank must govern" is not a gap a
#: scanner can close.
MAX_CONFIDENCE = 0.9


# --------------------------------------------------------------- extracting
def _read_text(path: Path) -> str:
    """Whatever text this file has, or empty when it cannot be read.

    A file that cannot be decoded is not an error: a share holds binaries,
    corrupt files and things somebody locked. It is counted as unreadable so
    the sweep's coverage figure is honest.
    """
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def _read_notebook(path: Path) -> str:
    """A notebook's source, without its outputs.

    Outputs are excluded deliberately. A printed dataframe full of the word
    `coefficient` is not evidence that this notebook fits anything, and
    including outputs is how a scanner reaches thirty percent precision.
    """
    try:
        document = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
    except (OSError, ValueError):
        return ""
    cells = document.get("cells") or []
    out = []
    for cell in cells:
        source = cell.get("source")
        if isinstance(source, list):
            out.append("".join(source))
        elif isinstance(source, str):
            out.append(source)
    return "\n".join(out)


def _read_workbook(path: Path) -> str:
    """Formulas and shared strings from an .xlsx, without a dependency.

    An .xlsx is a zip of XML. The formulas live in `<f>` elements inside each
    sheet and the text in `sharedStrings.xml`, and pulling those two out is
    enough to find a `LINEST` — which is the whole job here. openpyxl would do
    it more thoroughly and is a dependency this tool does not take, for the same
    reason nothing else in this repository does: a scanner a firm cannot run
    inside its own perimeter without an approval cycle is a scanner nobody runs.

    A legacy `.xls` is a binary format this does not read, and it says so on
    the sweep rather than reporting the file as clean.
    """
    try:
        with zipfile.ZipFile(path) as book:
            parts = []
            for name in book.namelist():
                if name.startswith("xl/worksheets/") and name.endswith(".xml"):
                    parts.append(book.read(name).decode("utf-8", "ignore"))
                elif name.endswith("sharedStrings.xml"):
                    parts.append(book.read(name).decode("utf-8", "ignore"))
            return "\n".join(parts)
    except (OSError, zipfile.BadZipFile, KeyError):
        return ""


def extract(path: Path) -> Tuple[str, bool]:
    """The text to match against, and whether the file could be read at all."""
    suffix = path.suffix
    if suffix in (".xlsx", ".xlsm"):
        text = _read_workbook(path)
    elif suffix == ".xls":
        # A legacy binary workbook. Not read, and named as not read.
        return "", False
    elif suffix == ".ipynb":
        text = _read_notebook(path)
    else:
        text = _read_text(path)
    return text, bool(text)


# ---------------------------------------------------------------- matching
def signals_in(text: str) -> List[Dict[str, Any]]:
    """Every signal found, with the text that matched it.

    The matched text travels to the register. A triager opening a candidate
    needs to see `=LINEST(B2:B99,A2:A99)` and where it was, not a score — and a
    scanner that reported only a score is one nobody can grade, because nobody
    can tell a true finding from a false one without opening the file anyway.
    """
    found = []
    for name, pattern, weight, why in SIGNALS:
        match = re.search(pattern, text)
        if match is None:
            continue
        excerpt = match.group(0)
        # Bounded, because a matched string can be a whole formula and a
        # candidate is not a place to store somebody's spreadsheet.
        found.append({"signal": name, "matched": excerpt[:160],
                      "weight": weight, "why": why})
    return found


def confidence_of(found: Iterable[Dict[str, Any]]) -> float:
    """The triage order for a file, capped well below certainty.

    The strongest signal plus a bonus for corroboration from a different
    family. Not a probability and not presented as one: the contract requires
    a number strictly below 1.0, and this stays under `MAX_CONFIDENCE` because
    the distance between *this file contains a regression* and *this is a model
    the bank must govern* is not a distance a scanner can travel.
    """
    found = list(found)
    if not found:
        return 0.0
    best = max(f["weight"] for f in found)
    families = len({f["signal"] for f in found})
    return round(min(best + FAMILY_BONUS * (families - 1), MAX_CONFIDENCE), 3)


def fingerprint_of(path: Path, text: str) -> str:
    """Something intrinsic that survives the file moving.

    The content digest, not the path. A spreadsheet that changes folder is the
    same spreadsheet, and keying on the path means next month's sweep raises it
    again and the dismissal somebody recorded is lost — which is exactly how a
    discovery queue comes back the same size forever.

    Extracted text rather than raw bytes, because an .xlsx re-saved without
    edits has different bytes and the same formulas. That is the identity a
    triager means.
    """
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


# ------------------------------------------------------------------ sweeping
def sweep(roots: List[Path], *, scanner: str = SCANNER, scope: str = "",
          floor: float = 0.4, max_bytes: int = MAX_BYTES,
          now: Optional[float] = None) -> Dict[str, Any]:
    """Walk the roots and produce a sweep document for the contract.

    `floor` drops the weakest matches. It is a real trade and the counts say
    which way it went: raising it produces a shorter queue that misses more,
    and the register cannot tell the difference because it cannot see what was
    dropped. So `below_floor` is reported, and the floor itself travels on the
    sweep — a precision figure means something different at 0.4 than at 0.7.
    """
    candidates: List[Dict[str, Any]] = []
    seen: Dict[str, Dict[str, Any]] = {}
    stats = {"files_seen": 0, "files_read": 0, "unreadable": 0,
             "too_large": 0, "below_floor": 0, "duplicates": 0}
    for root in roots:
        for path in _walk(root, stats, max_bytes):
            stats["files_seen"] += 1
            text, readable = extract(path)
            if not readable:
                stats["unreadable"] += 1
                continue
            stats["files_read"] += 1
            found = signals_in(text)
            if not found:
                continue
            score = confidence_of(found)
            if score < floor:
                stats["below_floor"] += 1
                continue
            digest = fingerprint_of(path, text)
            if digest in seen:
                # The same content in two places. One candidate, both
                # locations — a triager deciding about it is deciding once.
                stats["duplicates"] += 1
                seen[digest]["evidence"].setdefault("also_at", []).append(
                    str(path))
                continue
            candidate = {
                "fingerprint": digest,
                "location": str(path),
                "source": "drive",
                "confidence": score,
                "evidence": {
                    "kind": EXTENSIONS.get(path.suffix, "file"),
                    "signals": found,
                    "bytes": _size(path),
                    "modified_at": _mtime(path),
                },
                "proposed_as": "euc",
            }
            seen[digest] = candidate
            candidates.append(candidate)
    candidates.sort(key=lambda c: -c["confidence"])
    return {
        "scanner": scanner,
        "scope": scope or _scope_from(roots),
        # Always false, and it is not a defect. A scanner cannot know what it
        # did not look at; the register grades precision from triage and says
        # plainly that recall is not computable.
        "recall_known": False,
        "swept_at": now if now is not None else time.time(),
        "confidence_floor": floor,
        "coverage": stats,
        "candidates": candidates,
        "detail": _detail(stats, candidates, floor),
    }


def _detail(stats: Dict[str, int], candidates: List[Dict[str, Any]],
            floor: float) -> str:
    out = (f"{len(candidates)} candidate(s) from {stats['files_seen']} file(s) "
           f"seen, at a confidence floor of {floor}")
    if stats["below_floor"]:
        out += (f". {stats['below_floor']} file(s) matched something and fell "
                f"below the floor — raising it shortens the queue and the "
                f"register cannot tell what was dropped, which is why the "
                f"floor travels on the sweep")
    if stats["unreadable"]:
        out += (f". {stats['unreadable']} file(s) could not be read, including "
                f"any legacy .xls — reported rather than counted as clean, "
                f"because a file nothing looked at is not a file with nothing "
                f"in it")
    if stats["too_large"]:
        out += (f". {stats['too_large']} file(s) were over the size limit and "
                f"skipped. They are counted here because a sweep that quietly "
                f"dropped the largest workbooks would report high precision "
                f"over the easy half of the estate")
    if stats["duplicates"]:
        out += (f". {stats['duplicates']} duplicate(s) collapsed onto the "
                f"candidate they share content with, so a triager decides once")
    return out


def _scope_from(roots: List[Path]) -> str:
    """What was swept, when nobody said.

    A path list is a poor scope statement and it is better than none: the
    register requires the field precisely so that *what was not looked at* is
    somebody's stated claim rather than an assumption, and a default that
    described nothing would let the requirement be satisfied by accident.
    """
    return ("no scope was stated, so this is the literal root list: "
            + ", ".join(str(r) for r in roots)
            + ". Prefer --scope: it should say what was NOT swept")


def _walk(root: Path, stats: Dict[str, int], max_bytes: int) -> Iterable[Path]:
    for current, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS
                   and not d.startswith(".")]
        for name in files:
            path = Path(current) / name
            if path.suffix not in EXTENSIONS:
                continue
            size = _size(path)
            if size > max_bytes:
                stats["too_large"] += 1
                continue
            yield path


def _size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def _mtime(path: Path) -> Optional[float]:
    try:
        return path.stat().st_mtime
    except OSError:
        return None


# ---------------------------------------------------------------- submitting
def submit(document: Dict[str, Any], base_url: str, *, api_key: str = "",
           username: str = "", password: str = "",
           timeout: float = 60.0) -> Dict[str, Any]:
    """POST the sweep to the register's contract endpoint.

    Standard library only. This tool is meant to run on a file server inside a
    bank's perimeter, and a scanner that needs a package install before it can
    be run is a scanner nobody runs.

    It does not retry. A sweep that timed out may well have been ingested, and
    a second POST would double the queue — the register deduplicates on the
    fingerprint, so the damage is bounded, but "bounded damage" is not a reason
    to cause it.
    """
    # The scheme is checked rather than trusted. `--submit file:///etc/passwd`
    # would otherwise make this tool read a local file and call it a register,
    # which is a small hole in a program whose whole job is reading files it
    # was pointed at — and this one is pointed at things by a cron line
    # somebody wrote a year ago.
    if not re.match(r"^https?://", base_url):
        raise SystemExit(
            f"--submit takes an http(s) URL and got {base_url!r}. Other "
            f"schemes are refused rather than handled: a `file:` target would "
            f"make this read a local path and report the result as a "
            f"register's answer")
    request = urllib.request.Request(       # noqa: S310 - scheme checked above
        base_url.rstrip("/") + "/api/v1/scanner-contract/ingest",
        data=json.dumps(document).encode("utf-8"),
        headers={"Content-Type": "application/json",
                 **_auth(api_key, username, password)},
        method="POST")
    try:
        with urllib.request.urlopen(              # noqa: S310 - see above
                request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "ignore")
        # The register refuses a sweep as a WHOLE when it misses the contract,
        # and the refusal names every problem at once. Printing it verbatim is
        # the useful thing: it is a list of things to fix in this scanner.
        raise SystemExit(
            f"the register refused this sweep ({exc.code}):\n{body}\n\n"
            f"a sweep is refused whole rather than in part — a partial ingest "
            f"would produce a precision figure grading the rows MAYA chose to "
            f"keep rather than this scanner") from exc
    except urllib.error.URLError as exc:
        raise SystemExit(
            f"could not reach the register at {base_url}: {exc.reason}. "
            f"Nothing was submitted and nothing was decided — this is not a "
            f"refusal") from exc


def _auth(api_key: str, username: str, password: str) -> Dict[str, str]:
    if api_key:
        return {"Authorization": "Bearer " + api_key}
    if username:
        token = base64.b64encode(
            f"{username}:{password}".encode("utf-8")).decode("ascii")
        return {"Authorization": "Basic " + token}
    return {}


# ---------------------------------------------------------------------- cli
def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="tools.scanner.sweep",
        description="A reference EUC scanner for MAYA's discovery contract. "
                    "It runs where the data is, under whoever already has the "
                    "access, and hands the result over.")
    parser.add_argument("roots", nargs="+", type=Path,
                        help="directories to sweep")
    parser.add_argument("--scanner", default=SCANNER,
                        help="the name this sweep reports under. Keep it "
                             "stable: precision is computed per scanner, and "
                             "one that renames itself has no history")
    parser.add_argument("--scope", default="",
                        help="what was swept — and more usefully, what was "
                             "NOT. The register cannot compute recall and asks "
                             "the scanner to state its reach")
    parser.add_argument("--floor", type=float, default=0.4,
                        help="drop candidates below this confidence (0.4)")
    parser.add_argument("--max-bytes", type=int, default=MAX_BYTES)
    parser.add_argument("--out", type=Path,
                        help="write the sweep document here")
    parser.add_argument("--submit", metavar="BASE_URL",
                        help="POST it to a MAYA instance as well")
    parser.add_argument("--api-key", default=os.environ.get("MAYA_API_KEY", ""))
    parser.add_argument("--username", default="")
    parser.add_argument("--password", default="")
    args = parser.parse_args(argv)

    document = sweep(args.roots, scanner=args.scanner, scope=args.scope,
                     floor=args.floor, max_bytes=args.max_bytes)
    if args.out:
        args.out.write_text(json.dumps(document, indent=2), encoding="utf-8")
        print(f"wrote {args.out}", file=sys.stderr)
    elif not args.submit:
        print(json.dumps(document, indent=2))
    print(document["detail"], file=sys.stderr)
    if args.submit:
        result = submit(document, args.submit, api_key=args.api_key,
                        username=args.username, password=args.password)
        print(json.dumps(result, indent=2))
        print("\nNothing here is a registered model. Every one of these is a "
              "candidate somebody has to triage, and the register will not "
              "let it become anything else on its own.", file=sys.stderr)
    return 0


if __name__ == "__main__":                       # pragma: no cover
    raise SystemExit(main())
