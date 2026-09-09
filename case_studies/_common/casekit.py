"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Shared plumbing for the case studies.

**What MAYA is, and what these scripts are.** MAYA is a *register*. It holds
models, features, featuresets, versions, warrants and evidence; it does not
train anything and it does not run anything. Each case study script is the other
side of that boundary — it plays the bank's own modelling engine. It fits in its
own process, with its own arithmetic, and then hands MAYA the numbers under a
warrant MAYA issued.

So the division of labour in every script is the same, and it is the point:

    MAYA registers        the feature, the view version, the featureset binding,
                          the model, the version and its kernel, the warrant,
                          the parameter set, the evidence
    the script computes   the fit, the calibration, the diagnostics, the
                          prediction

Nothing here calls `/execute` or `/parameter-fits`. MAYA ships a captive engine
for demonstrations and a captive estimator, and using either in a case study
would teach the opposite of what these case studies exist to show.

Standard library plus the MAYA SDK, which is itself standard library only.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT / "sdk" / "python") not in sys.path:
    sys.path.insert(0, str(ROOT / "sdk" / "python"))

from maya_sdk import Maya, Refused

# The two clocks, as seconds. Every feature row MAYA accepts carries both, and
# a row missing either is refused at the upload rather than during assembly —
# which is the whole reason the platform can answer "what was knowable then".
DAY = 86_400.0


# --------------------------------------------------------------------- output
class Say:
    """Narration that a demo audience can follow line by line."""

    def __init__(self, title: str) -> None:
        self.title = title
        self._step = 0
        print(f"\n{'=' * 78}\n{title}\n{'=' * 78}")

    def step(self, what: str) -> None:
        self._step += 1
        print(f"\n[{self._step}] {what}")

    @staticmethod
    def did(detail: str) -> None:
        print(f"    · {detail}")

    @staticmethod
    def maya(detail: str) -> None:
        """Something the REGISTER now holds."""
        print(f"    ✓ MAYA: {detail}")

    @staticmethod
    def engine(detail: str) -> None:
        """Something this script computed. MAYA did not do this."""
        print(f"    ⚙ engine (not MAYA): {detail}")

    @staticmethod
    def note(detail: str) -> None:
        print(f"    ! {detail}")


def parse(description: str) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=description)
    p.add_argument("--url", default="http://127.0.0.1:5006",
                   help="the MAYA instance (default: %(default)s)")
    p.add_argument("--user", default="admin")
    p.add_argument("--password", default="maya-admin-dev")
    p.add_argument("--out", default=None,
                   help="where to write the LaTeX document "
                        "(default: this case study's folder)")
    p.add_argument("--offline", action="store_true",
                   help="do not reach the network for source data")
    return p.parse_args()


def connect(args: argparse.Namespace) -> Maya:
    maya = Maya(args.url, args.user, args.password)
    who = maya.call("GET", "/me")
    print(f"    connected to {args.url} as {who.get('principal', args.user)}")
    return maya


# ------------------------------------------------------------- idempotence
#: Refusals that mean "the register is already in the state you asked for".
#: These are not failures on a second run, and one of them is a control worth
#: naming: `review_says_nothing` is MAYA refusing to move a tier's review date
#: when the facts have not moved, so that re-running a script cannot manufacture
#: the appearance of a review nobody performed.
BENIGN_ON_RERUN = ("review_says_nothing",)


def attempt(what: str, call: Callable[[], Any], *,
            already: str = "already registered",
            benign: Iterable[str] = ()) -> Optional[Any]:
    """Run a registration, tolerating the case where it is already there.

    A case study somebody runs twice must not fail the second time, and it must
    not pretend the second run created anything. A duplicate is reported as a
    duplicate — silence would let a broken script look like a working one, which
    is the failure mode this whole platform is about.
    """
    try:
        result = call()
        print(f"    ✓ MAYA: {what}")
        return result
    except Refused as exc:
        code = (getattr(exc, "code", "") or "").lower()
        if _is_duplicate(exc) or code in {c.lower() for c in
                                          tuple(benign) + BENIGN_ON_RERUN}:
            print(f"    = {what} — {already} [{exc.code}]")
            return None
        print(f"    ✗ {what} REFUSED [{exc.code}]")
        print(f"      {exc.detail}")
        if getattr(exc, "remediation", None):
            print(f"      → {exc.remediation}")
        raise


def _is_duplicate(exc: Refused) -> bool:
    code = (getattr(exc, "code", "") or "").lower()
    detail = (getattr(exc, "detail", "") or "").lower()
    return ("exists" in code or "duplicate" in code or "already" in code
            or "exists" in detail or "already" in detail)


def ensure_filled(maya: Maya, featureset: str,
                  bindings: Dict[str, str]) -> int:
    """Fill the featureset once, and return the version to pin.

    A second `fill` is a second VERSION, correctly — the platform is right to
    make one, because a new binding is a new thing to pin. But a demo script run
    twice should not silently accumulate versions that differ in nothing, so
    this asks first and says which it is using.
    """
    existing = (maya.featuresets.get(featureset) or {}).get("versions") or []
    if existing:
        version = int(existing[-1]["version"])
        print(f"    = {featureset} already has v{version} — pinning that, "
              f"not filling again")
        return version
    maya.featuresets.fill(featureset, bindings=bindings)
    version = int((maya.featuresets.get(featureset)["versions"])[-1]["version"])
    print(f"    ✓ MAYA: {featureset} v{version} — every slot pinned to a "
          f"feature, a view and a view version")
    return version


def ensure_version(maya: Maya, short_name: str, *, semver: str,
                   kernel: Dict[str, Any]) -> Dict[str, Any]:
    """Create the version, or return the one already there.

    Asked before attempted, rather than attempted and forgiven. Once a model
    record is **attested** it is immutable, and MAYA refuses a new version with
    `this model is attested and therefore immutable; open an amendment` — which
    is the correct answer to a real change and the wrong thing to happen on the
    second run of a demo that is changing nothing. Checking first keeps the
    control intact and the script re-runnable.
    """
    for row in maya.versions.list(short_name):
        if row.get("semver") == semver:
            print(f"    = version {semver} already exists — not recreating it")
            return row
    made = maya.versions.create(short_name, semver=semver, kernel=kernel)
    print(f"    ✓ MAYA: version {semver}")
    return made


#: The cast every case study needs, because a governed model cannot be approved
#: by the person who built it. These are the four hats the platform's own
#: refusals assume exist: whoever builds, whoever owns, and the two second-line
#: signatures a tier 1 or tier 2 version requires.
CAST = (
    ("a.mehta", "Anika Mehta", ["model_developer"], "quant-password-long"),
    ("j.okafor", "Jide Okafor", ["model_owner"], "owner-password-long"),
    ("s.iqbal", "Sana Iqbal", ["model_risk_manager"], "mrm-password-long"),
    ("v.chen", "Wei Chen", ["validator"], "validator-password-long"),
)


def ensure_cast(maya: Maya, url: str) -> Dict[str, Maya]:
    """Create the four people, and return a client signed in as each.

    Not decoration. Every interesting refusal in these case studies is a
    segregation-of-duties refusal, and you cannot demonstrate one with a single
    administrator account: the platform is right to let an admin do everything,
    which is exactly why an admin cannot show you that the control works.
    """
    clients: Dict[str, Maya] = {}
    for username, display, roles, password in CAST:
        attempt(f"{username} ({', '.join(roles)})",
                lambda u=username, d=display, r=roles, p=password:
                maya.principals.create(username=u, display_name=d, roles=r,
                                       password=p),
                already="already exists")
        clients[username] = Maya(url, username, password)
    return clients


#: Who wears which hat, for the two roles a tier 1 or 2 quorum names.
SIGNS_AS = {"model_risk_manager": "s.iqbal", "validator": "v.chen"}


def approve_version(maya: Maya, people: Dict[str, Maya], *, urn: str,
                    semver: str, statement: str) -> Tuple[bool, Optional[int]]:
    """Walk the approval path this version actually requires.

    The platform is asked what it needs rather than told: `approvals.needed()`
    returns the tier, whether a quorum applies, which roles must sign, and what
    the status already is. A script that decided for itself would be a second
    copy of the quorum rule, and the second copy is the one that goes stale.

    Tier 1 and 2 need **two signatures in two named roles**, and the same person
    may not sign twice under two hats — which is why the case studies create
    four people rather than doing everything as an administrator.

    Returns (approved, tier).
    """
    needed = maya.approvals.needed(urn=urn, semver=semver)
    tier = needed.get("tier")
    print(f"    · {needed.get('detail')}")
    if needed.get("status") == "approved":
        print(f"    = version {semver} is already approved")
        return True, tier

    if not needed.get("quorum_required"):
        signer = people.get("s.iqbal") or maya
        attempt(f"{semver} approved by s.iqbal", lambda: signer.versions.approve(
            urn, semver, note=statement), already="already approved")
        return True, tier

    approval_id = needed.get("open_approval")
    if not approval_id:
        opened = maya.versions.open_quorum(urn=urn, semver=semver)
        approval_id = opened.get("id") or opened.get("approval_id")
        print(f"    ✓ MAYA: version approval {approval_id} opened")
    else:
        print(f"    = approval {approval_id} is already open")

    for role in (needed.get("required_roles") or []):
        who = SIGNS_AS.get(role)
        signer = people.get(who) if who else None
        if signer is None:
            print(f"    ! nobody in this cast holds {role}; quorum incomplete")
            return False, tier
        attempt(f"signed by {who} as {role}",
                lambda s=signer, r=role: s.versions.sign_quorum(
                    approval_id, role=r, statement=statement),
                already="already signed")

    after = maya.approvals.needed(urn=urn, semver=semver)
    ok = after.get("status") == "approved"
    print(f"    {'✓ MAYA: version ' + semver + ' is approved' if ok else '! still ' + str(after.get('status'))}")
    return ok, tier


def put_record_in_force(maya: Maya, people: Dict[str, Maya], *,
                        urn: str, note: str) -> str:
    """Walk the MODEL RECORD's lifecycle, which is separate from the version's.

    Two lifecycles have to complete before a warrant resolves, and confusing
    them is the commonest surprise in a first demo. Approving the **version**
    says *this mathematics was reviewed*. Approving the **record** says *this
    model is a thing the bank runs, owned by somebody, at a tier*. A warrant
    needs both, and MAYA's refusal says so in as many words.

    Attestation is the third step and a different act again: approval is a
    decision, attestation is a signature putting the model **in force**.
    """
    def status_now() -> str:
        state = maya.lifecycle.state(urn)
        return str(state.get("status") or state.get("state") or "unknown")

    was = status_now()
    print(f"    · the record is '{was}'")
    # Asked, not attempted. An attested record is immutable and MAYA answers
    # `cannot 'submit' a model that is 'attested'; from here you may: amend,
    # retire` — the right answer to a real change, and the wrong thing to happen
    # on a second run that is changing nothing.
    if was in ("attested", "in_force"):
        print("    = already in force; nothing to submit, approve or attest")
        return was

    mrm = people.get("s.iqbal") or maya
    if was == "draft":
        attempt("submitted for review",
                lambda: maya.lifecycle.submit(urn, note=note),
                already="already submitted")
    if status_now() in ("submitted", "under_review", "in_review"):
        attempt("approved by s.iqbal (model risk)",
                lambda: mrm.lifecycle.approve(urn, note=note),
                already="already approved")

    # Attestation takes a signature from every required role, and each person
    # may sign only for a role they actually hold.
    for role, who in (("model_risk_manager", "s.iqbal"),
                      ("model_owner", "j.okafor")):
        signer = people.get(who)
        if signer is None:
            continue
        attempt(f"attested by {who} as {role}",
                lambda s=signer, r=role: s.models.attest(urn, role=r),
                already="already attested")

    after = maya.lifecycle.state(urn)
    status = str(after.get("status") or after.get("state") or "unknown")
    print(f"    ✓ MAYA: the record is now '{status}'")
    return status


def expect_refusal(what: str, call: Callable[[], Any]) -> Optional[Refused]:
    """Assert that MAYA REFUSES something, and show the refusal.

    A control nobody has seen refuse is a control nobody has tested. Each case
    study exercises at least one, because "it let us do the right thing" and
    "it would have stopped the wrong thing" are different claims and only the
    second is a control.
    """
    try:
        call()
    except Refused as exc:
        print(f"    ✓ refused as it should be: {what}")
        print(f"      [{exc.code}] {exc.detail}")
        if getattr(exc, "remediation", None):
            print(f"      → {exc.remediation}")
        return exc
    print(f"    ✗ NOT REFUSED — {what} was allowed, and should not have been")
    return None


def load_once(maya: Maya, view: str, rows: List[Dict[str, Any]]) -> int:
    """Materialise rows as one view version, unless the view already has one.

    One upload is one view version, because a version is what a featureset pins
    and half a version is not something anybody can pin.
    """
    existing = maya.views.versions(view).get("versions", [])
    if existing:
        n = existing[-1].get("version")
        print(f"    = {view} already has data (at version {n}) — not loading again")
        return int(n)
    maya.views.materialise(view, rows=rows)
    n = maya.views.versions(view)["versions"][-1]["version"]
    print(f"    ✓ MAYA: {len(rows):,} rows into {view}, as version {n}")
    return int(n)


def newest_version(maya: Maya, featureset: str) -> int:
    versions = maya.call("GET", f"/featuresets/{featureset}")
    got = versions.get("versions") or []
    if not got:
        raise SystemExit(f"{featureset} has no version to pin")
    return int(got[-1]["version"])


# ------------------------------------------------------------------- LaTeX
def latex_escape(text: str) -> str:
    for a, b in (("\\", r"\textbackslash{}"), ("&", r"\&"), ("%", r"\%"),
                 ("$", r"\$"), ("#", r"\#"), ("_", r"\_"), ("{", r"\{"),
                 ("}", r"\}"), ("~", r"\textasciitilde{}"),
                 ("^", r"\textasciicircum{}")):
        text = text.replace(a, b)
    return text


def mathematics(maya: Maya, urn: str, semver: str) -> Dict[str, Any]:
    """The equation, DERIVED by MAYA from the expression it holds.

    Not stored, and that is the point worth making to an audience: a `latex`
    field filled in by whoever wrote the model would be a second description of
    one thing, and two descriptions drift — with the one nobody executes
    drifting first. MAYA renders the syntax tree it holds, so the equation in
    this document and the definition in the register cannot disagree.
    """
    return maya.call("GET", "/mathematics", params={"urn": urn, "semver": semver})


def document(*, path: pathlib.Path, title: str, subtitle: str, blocks: List[str]) -> pathlib.Path:
    """Write a standalone LaTeX document. No packages beyond a base install."""
    head = "\n".join([
        r"\documentclass[11pt,a4paper]{article}",
        r"\usepackage[T1]{fontenc}",
        r"\usepackage[utf8]{inputenc}",
        r"\usepackage{amsmath,amssymb}",
        r"\usepackage[margin=25mm]{geometry}",
        r"\usepackage{longtable}",
        r"\usepackage{booktabs}",
        r"\setlength{\parindent}{0pt}",
        r"\setlength{\parskip}{6pt}",
        r"\title{" + title + "}",
        r"\author{" + subtitle + "}",
        r"\date{\today}",
        r"\begin{document}",
        r"\maketitle",
    ])
    body = "\n\n".join(blocks)
    tail = r"\end{document}"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{head}\n\n{body}\n\n{tail}\n", encoding="utf8")
    return path


def equation(latex: str, expression: str, *, limit: int = 420) -> str:
    """Typeset the derived equation, or show the expression when it is huge.

    MAYA renders LaTeX from the syntax tree it holds, which is the right source
    — but a model that inlines a rational approximation of the normal CDF
    produces several thousand characters of it, and there is no page width at
    which that is readable. Rather than hand-write a tidier equation, which
    would be the second description this whole mechanism exists to avoid, a long
    one is shown as the **expression itself**: still exactly what the register
    holds, just not pretending to be a display equation.

    Note what is NOT done here: no blank line ever goes inside an `equation`
    environment. One did, and `pdflatex` answered `Missing $ inserted` and
    produced no PDF at all — a document that silently failed to build is a
    deliverable nobody notices is missing.
    """
    if len(latex) <= limit:
        return "\\begin{equation}\n" + latex + "\n\\end{equation}"
    wrapped = "\n".join(expression[i:i + 88]
                        for i in range(0, len(expression), 88))
    return ("\\textbf{The expression, verbatim from the register.} "
            "MAYA also derives a typeset form of this from the same syntax "
            "tree; it runs to "
            f"{len(latex):,} characters because the normal CDF is inlined, so "
            "the definitive statement is given here as the expression itself "
            "rather than as an unreadable display equation. Ask "
            "\\texttt{GET /api/v1/mathematics} for the typeset form.\n\n"
            "{\\footnotesize\\begin{verbatim}\n" + wrapped +
            "\n\\end{verbatim}}")


def table(rows: Iterable[Iterable[Any]], *, header: Iterable[str],
          spec: str) -> str:
    """A booktabs table, escaped."""
    head = " & ".join(rf"\textbf{{{latex_escape(str(h))}}}" for h in header)
    body = " \\\\\n".join(
        " & ".join(latex_escape(str(c)) for c in row) for row in rows)
    return "\n".join([
        rf"\begin{{center}}\begin{{tabular}}{{{spec}}}", r"\toprule",
        head + r" \\", r"\midrule", body + r" \\", r"\bottomrule",
        r"\end{tabular}\end{center}",
    ])


def save_json(path: pathlib.Path, payload: Any, *, what: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf8")
    print(f"    ✓ wrote {what}: {path}")


__all__ = [
    "BENIGN_ON_RERUN",
    "CAST",
    "DAY",
    "ROOT",
    "Maya",
    "Refused",
    "Say",
    "approve_version",
    "attempt",
    "connect",
    "document",
    "ensure_cast",
    "ensure_filled",
    "ensure_version",
    "equation",
    "expect_refusal",
    "latex_escape",
    "load_once",
    "mathematics",
    "newest_version",
    "parse",
    "put_record_in_force",
    "save_json",
    "table",
]
