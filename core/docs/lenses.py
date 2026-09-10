"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Lenses: one section each, and what it reads.

A lens is a function from platform state to prose plus the evidence it rested
on. Sections are lenses rather than templates because a template interpolates
values it was handed, while a lens goes and looks — so a section cannot silently
describe a state that no longer holds.

Two conventions make the output honest rather than merely generated.

A lens that cannot fill its section says **why**, in the document, in the place
the content would have been. A model development document with a blank
"Validation" heading and one that says "no validation has been recorded for this
version" look identical to a skim and are completely different findings.

And every lens returns the evidence node ids it used. A section resting on
nothing is visible as a section resting on nothing.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

# A lens returns (markdown, cited evidence ids). Returning None for the prose
# means "I could not fill this", and the compiler records it as a gap.
Rendered = Tuple[Optional[str], List[str]]


@dataclass(frozen=True)
class Lens:
    key: str
    heading: str
    render: Callable[[Dict[str, Any]], Rendered]
    required: bool = True
    note: str = ""


def _cite(nodes: List[Dict[str, Any]], *kinds: str) -> List[str]:
    """Evidence ids of the given kinds. What this section actually rests on."""
    return [n["id"] for n in nodes if n["kind"] in kinds]


def _table(rows: List[Tuple[str, Any]]) -> str:
    body = "\n".join(f"| {k} | {'' if v is None else v} |" for k, v in rows)
    return f"| | |\n|---|---|\n{body}\n"


# ---------------------------------------------------------------- the lenses
def identity(ctx: Dict[str, Any]) -> Rendered:
    m = ctx["model"]
    return _table([
        ("URN", f"`{m['urn']}`"),
        ("Name", m["name"]),
        ("Model class", m["model_class"]),
        ("Domain", m["domain"]),
        ("Owner", m["owner"]),
        ("Legal entity", m["legal_entity"]),
        ("Declared purpose", m["purpose"]),
        ("Origin", m["origin"]),
        ("Record state", f"**{m['status']}**"),
    ]) + (f"\n{m['description']}\n" if m.get("description") else ""), \
        _cite(ctx["evidence"], "model_registered", "model_updated")


def classification(ctx: Dict[str, Any]) -> Rendered:
    v = ctx.get("version")
    if not v:
        return None, []
    klass = v["trainability_class"]
    text = _table([
        ("Version", f"`{v['semver']}`"),
        ("Trainability class", f"**{klass}**"),
        ("Parameter kind", f"`{v['parameter_kind']}`"),
        ("Fit procedure", f"`{v['fit_procedure']}`"),
        ("Deterministic", v["deterministic"]),
        ("Manifest digest", f"`{v['manifest_digest'][:32]}…`"),
        ("Artifact digest", f"`{v['artifact_digest']}`" if v.get("artifact_digest")
         else "*none recorded — this version is descriptor-only*"),
    ])
    text += (f"\nThe class is **derived** from how the parameter object is inhabited "
             f"(`{v['parameter_kind']}` obtained by `{v['fit_procedure']}`), not "
             f"declared. It determines which evidence is appropriate here: asking a "
             f"T0 model for a training set is a type error, not a gap.\n")
    return text, _cite(ctx["evidence"], "version_created", "version_approved")


def risk_tier(ctx: Dict[str, Any]) -> Rendered:
    a = ctx.get("assessment")
    if not a:
        return None, []
    text = _table([
        ("Tier", f"**{a['tier']}**"),
        ("Materiality", a.get("materiality")),
        ("Complexity", a.get("complexity")),
        ("Ruleset version", f"`{a.get('ruleset_version')}`"),
    ])
    if a.get("rationale"):
        text += f"\n**Derivation.** {a['rationale']}\n"
    if a.get("required_controls"):
        controls = "\n".join(f"- {c}" for c in a["required_controls"])
        text += f"\n**Controls required at this tier.**\n\n{controls}\n"
    return text, _cite(ctx["evidence"], "tier_assigned")


def methodology(ctx: Dict[str, Any]) -> Rendered:
    v = ctx.get("version")
    if not v:
        return None, []
    def schema(rows):
        if not rows:
            return "*none declared*"
        head = "| Field | Type | Range |\n|---|---|---|\n"
        return head + "\n".join(
            f"| `{f['name']}` | {f.get('dtype')} | "
            f"{f.get('minimum', '')}–{f.get('maximum', '')} |" for f in rows)
    return (f"**Inputs**\n\n{schema(v['input_schema'])}\n\n"
            f"**Outputs**\n\n{schema(v['output_schema'])}\n\n"
            "Input schemas are contravariant and output schemas covariant, so a "
            "replacement version must accept everything this one accepts and "
            "promise everything it promises, or the alias move is refused.\n"), \
        _cite(ctx["evidence"], "version_created")


def assumptions(ctx: Dict[str, Any]) -> Rendered:
    """Assumptions and limitations: the registers first, the contract after.

    This read only the version contract's numeric bounds. Two consequences
    followed, and both were bad in the quiet way. A model with no numeric
    contract — a vendor score, a generative assembly, an elicited scorecard —
    rendered the section as NOTHING, so a document about the model whose
    limitations matter most said least about them. And where a person had taken
    the trouble to record structured statements in the two registers, the
    document could not see them, which is what `FR-INV-007` means by the gap
    that most directly weakens this document.

    So the registers lead. The contract's bounds follow as what a machine
    enforces at call time, which is a smaller and harder claim.
    """
    if (gap := unreadable(ctx, "assumptions")) is not None:
        return gap
    if (gap := unreadable(ctx, "limitations")) is not None:
        return gap

    parts: List[str] = []
    cites: List[Any] = []
    asm = ctx.get("assumptions") or {}
    lim = ctx.get("limitations") or {}

    standing_asm = [a for a in (asm.get("assumptions") or [])
                    if not a.get("withdrawn_at")]
    standing_lim = [ln for ln in (lim.get("limitations") or [])
                    if not ln.get("withdrawn_at")]

    if standing_asm:
        parts.append(
            "**What this model relies on being true.** An assumption can stop "
            "being true while the model runs, which is what separates it from "
            "a limitation. The column that matters is the last one: an "
            "assumption with no monitor is one the platform believes and would "
            "not notice becoming false.\n\n"
            "| Ref | Kind | Materiality | Assumption | Tested by |\n"
            "|---|---|---|---|---|\n"
            + "\n".join(
                f"| `{a['reference']}` | {a['kind']} | {a.get('materiality', '—')} "
                f"| {a['statement']} | "
                + (f"monitor `{str(a['monitor_id'])[:12]}`"
                   if a.get("monitor_id") else "**nothing**")
                + " |"
                for a in standing_asm) + "\n")
        parts.append(f"\n{asm.get('detail', '')}\n")
        # A material assumption with nothing compensating for it is a risk
        # nobody has decided about, and it is worth its own sentence rather
        # than a reader counting the table.
        exposed = [a for a in standing_asm
                   if a.get("materiality") in ("material", "critical")
                   and not a.get("monitor_id")
                   and not (a.get("mitigation") or "").strip()]
        if exposed:
            parts.append(
                "\n> **" + str(len(exposed)) + " assumption(s) here are "
                "material or worse, monitored by nothing and mitigated by "
                "nothing: "
                + ", ".join(f"`{a['reference']}`" for a in exposed)
                + ". That combination is not a gap in the document; it is a "
                "decision nobody has taken.**\n")
        mitigations = [a for a in standing_asm
                       if (a.get("mitigation") or "").strip()]
        if mitigations:
            parts.append(
                "\n**Mitigations.**\n\n"
                + "\n".join(f"- `{a['reference']}` — {a['mitigation']}"
                             for a in mitigations) + "\n")
        cites += _cite(ctx["evidence"], "assumption_recorded")

    if standing_lim:
        parts.append(
            "\n**What this model cannot do.** A limitation is a boundary of "
            "competence rather than a claim about the world, so it does not "
            "stop being true — it is simply what the model is.\n\n"
            "| Ref | Kind | Limitation | Enforced by |\n|---|---|---|---|\n"
            + "\n".join(
                f"| `{ln['reference']}` | {ln['kind']} | {ln['statement']} | "
                + (f"contract clause `{ln['bound_key']}`"
                   if ln.get("bound_key") else "**nothing**") + " |"
                for ln in standing_lim) + "\n")
        parts.append(f"\n{lim.get('detail', '')}\n")
        cites += _cite(ctx["evidence"], "limitation_recorded")

    v = ctx.get("version")
    contract = (v or {}).get("contract") or {}

    def bounds(items, label):
        if not items:
            return f"*no {label} declared*\n"
        return "\n".join(
            f"- `{b['key']}` " +
            (f"between {b.get('minimum')} and {b.get('maximum')}"
             if b.get("minimum") is not None or b.get("maximum") is not None
             else f"in {b.get('allowed')}")
            for b in items) + "\n"

    if contract:
        parts.append(
            "\n**Enforced at call time.** These are the subset a machine can "
            "check on every invocation. Outside them the guarantee is void and "
            "the execution engine refuses rather than extrapolating.\n\n"
            + bounds(contract.get("assumptions"), "bounded assumptions")
            + "\n**Guarantees** — what the model promises when they hold.\n\n"
            + bounds(contract.get("guarantees"), "guarantees"))
        cites += _cite(ctx["evidence"], "version_created")
    elif standing_asm or standing_lim:
        # Said rather than omitted. A reader who sees no bounds section should
        # know it is a property of the model and not of the compiler.
        parts.append(
            "\n**Nothing here is enforced at call time.** This version "
            "declares no numeric operating contract, because its inputs are "
            "not the kind of thing an interval bounds. Everything above is "
            "recorded and read, not checked on invocation.\n")

    if not parts:
        return None, []
    return "".join(parts), cites


def data_and_features(ctx: Dict[str, Any]) -> Rendered:
    contract = ctx.get("feature_contract")
    if not contract:
        return None, []
    rows = "\n".join(f"| `{i['view']}` | v{i['version']} | `{i['namespace']}` |"
                     for i in contract["items"])
    return (f"The version is pinned to exact feature view versions. Serving reads "
            f"these namespaces and no others; publishing a later view version does "
            f"not move what this model is served.\n\n"
            f"| Feature view | Pinned version | Serving namespace |\n|---|---|---|\n{rows}\n\n"
            f"Contract digest: `{contract['digest'][:32]}…`\n"), \
        _cite(ctx["evidence"], "feature_contract_bound")


def validation(ctx: Dict[str, Any]) -> Rendered:
    if (gap := unreadable(ctx, "validations")) is not None:
        return gap
    episodes = ctx.get("validations") or []
    if not episodes:
        return None, []
    out = []
    for e in episodes:
        results = ctx["results_by_validation"].get(e["id"], [])
        out.append(
            f"**{e['kind'].replace('_', ' ').title()}** — validators "
            f"{', '.join(e['validators'])}; independence "
            f"{'attested' if e['independence'].get('independent') else 'NOT established'}; "
            f"outcome **{e['outcome'] or e['status']}**.\n")
        if results:
            rows = "\n".join(
                f"| `{r['test_key']}` | {r['value']:.6g} | `{r['threshold']}` | "
                f"{'pass' if r['passed'] else '**fail**'} |"
                for r in results if r["value"] is not None)
            out.append(f"\n| Test | Value | Threshold | |\n|---|---|---|---|\n{rows}\n")
        if e.get("conditions"):
            out.append("\nConditions: " + "; ".join(e["conditions"]) + "\n")
    return "\n".join(out), _cite(ctx["evidence"], "validation_opened",
                                 "test_result_recorded", "validation_concluded")


def unreadable(ctx: Dict[str, Any], what: str) -> Optional[Rendered]:
    """The section a source could not be read for, said plainly.

    An empty list from `_optional` meant both "nothing is recorded" and "the
    read raised", and the lenses reported the first for both — so a board pack
    could assert "No findings are open against this model" on the strength of a
    finding register that threw, and the compiler would then persist it, stamp
    the evidence head and append `document_compiled` to the chain. A document
    that cannot read a source says so; it does not guess the reassuring answer.
    """
    if what in (ctx.get("unreadable") or ()):
        return (f"**This section could not be compiled.** {what.capitalize()} "
                f"could not be read when this document was built, so its "
                f"absence below is not evidence that there are none. Rebuild "
                f"the document once the source is reachable.\n", [])
    return None


def findings(ctx: Dict[str, Any]) -> Rendered:
    if (gap := unreadable(ctx, "findings")) is not None:
        return gap
    open_findings = ctx.get("findings") or []
    if not open_findings:
        return ("No findings are open against this model.\n", [])
    rows = "\n".join(
        f"| {f['severity']}{' **(blocking)**' if f['blocking'] else ''} | {f['title']} "
        f"| {f['owner']} | {f['source']} |" for f in open_findings)
    return (f"| Severity | Finding | Owner | Source |\n|---|---|---|---|\n{rows}\n\n"
            "A blocking finding refuses warrant resolution and alias promotion, so "
            "a model with one open is not servable.\n"), \
        _cite(ctx["evidence"], "finding_raised", "finding_closed")


def monitoring(ctx: Dict[str, Any]) -> Rendered:
    if (gap := unreadable(ctx, "monitoring")) is not None:
        return gap
    status = ctx.get("monitoring") or {}
    detail = status.get("detail") or []
    if not detail:
        return None, []
    rows = []
    for m in detail:
        obs = m.get("last_observation")
        rows.append(
            f"| {m['name']} | {m['kind'].replace('_', ' ')} | `{m['test_key']}` | "
            f"`{m['threshold']}` | "
            + (f"{obs['value']:.4g} ({'pass' if obs['passed'] else '**breach**'})"
               if obs and obs["value"] is not None else "*not yet evaluated*") + " |")
    text = ("| Monitor | Asks | Test | Threshold | Last observation |\n"
            "|---|---|---|---|---|\n" + "\n".join(rows) + "\n")
    delayed = [m for m in detail if m.get("label_delay_days")]
    if delayed:
        text += ("\nPerformance monitors declare an outcome window; a cohort is not "
                 "measured until its outcomes have matured. "
                 + "; ".join(f"`{m['name']}` waits {m['label_delay_days']:g} days"
                             for m in delayed) + ".\n")
    return text, _cite(ctx["evidence"], "monitor_defined", "monitor_evaluated",
                       "monitor_breached")


def lifecycle(ctx: Dict[str, Any]) -> Rendered:
    flow = ctx.get("lifecycle")
    if not flow:
        return None, []
    text = _table([("Record state", f"**{flow['state']}**"),
                   ("Meaning", flow["meaning"]),
                   ("Open to change", flow["mutable"])])
    att = flow.get("open_attestation")
    if att:
        text += (f"\nAn attestation is open: signed by "
                 f"{', '.join(att['signed_roles']) or 'nobody yet'}; awaiting "
                 f"{', '.join(att['outstanding_roles'])}.\n")
    if flow.get("attested_at"):
        text += ("\nThe record is attested and therefore immutable. Changing it "
                 "requires an amendment, which must itself be attested.\n")
    history = flow.get("amendment_history") or []
    if history:
        rows = "\n".join(f"| {a['reference']} | {a['reason']} | {a['status']} |"
                         for a in history)
        text += f"\n**Amendments**\n\n| Ref | Reason | Status |\n|---|---|---|\n{rows}\n"
    return text, _cite(ctx["evidence"], "model_submit", "model_approve",
                       "model_attest", "attestation_signed", "amendment_opened")


def execution(ctx: Dict[str, Any]) -> Rendered:
    grants = ctx.get("warrants") or []
    if not grants:
        return None, []
    rows = "\n".join(
        f"| {g['principal']} | {g['declared_use']} | {g['environment']} | "
        f"{'revoked' if g['revoked'] else 'active'} |" for g in grants)
    return ("A consumer holds only a URN. Artifact location, schemas, operating "
            "boundary and policy are resolved at the moment of use into a signed, "
            "expiring warrant.\n\n"
            f"| Principal | Approved use | Environment | |\n|---|---|---|---|\n{rows}\n"), \
        _cite(ctx["evidence"], "warrant_issued", "warrant_revoked")


def overlays(ctx: Dict[str, Any]) -> Rendered:
    status = ctx.get("overlays") or {}
    rows_in = status.get("detail_rows") or []
    if not rows_in:
        return None, []
    rows = "\n".join(
        f"| {o['reference']} | {o['name']} | {o['kind']} | {o['status']} | "
        f"{o['renewals']} | "
        + (f"{o['assessment']['materiality']['magnitude']:,.2f}"
           if o["assessment"]["materiality"].get("measured") else "*unmeasured*")
        + f" | {'**yes**' if o['assessment']['escalate'] else 'no'} |"
        for o in rows_in)
    text = ("A post-model adjustment is part of the number the model produces, so "
            "a document that omits them describes a model nobody runs.\n\n"
            "| Ref | Adjustment | Kind | Status | Renewals | Magnitude | Persistent |\n"
            "|---|---|---|---|---|---|---|\n" + rows + "\n\n"
            f"{status.get('detail', '')}.\n")
    persistent = [o for o in rows_in if o["assessment"]["escalate"]]
    if persistent:
        text += ("\nAn overlay past its renewal limit is an unversioned model "
                 "change: either the model should be corrected, or the adjustment "
                 "built into it and validated.\n")
    return text, _cite(ctx["evidence"], "overlay_proposed", "overlay_approved",
                       "overlay_renewed", "overlay_measured")


def regimes(ctx: Dict[str, Any]) -> Rendered:
    if (gap := unreadable(ctx, "regime determinations")) is not None:
        return gap
    determinations = (ctx.get("regimes") or {}).get("regimes") or []
    if not determinations:
        return None, []
    rows = "\n".join(
        f"| {d['title']} | {d['authority']} | {d['satisfied']}/"
        f"{d['satisfied'] + d['unmet']} | "
        + ("**satisfied**" if d["compliant"] else "**not satisfied**") + " |"
        for d in determinations)
    text = ("Each supervisor is evaluated in its own vocabulary rather than "
            "against a merged checklist, because regimes disagree about what "
            "words mean and flattening them is how a scope determination becomes "
            "indefensible.\n\n"
            "| Regime | Authority | Obligations met | |\n|---|---|---|---|\n"
            + rows + "\n")
    for d in determinations:
        unmet = [o for o in d["obligations"] if not o["satisfied"]]
        if not unmet:
            continue
        text += (f"\n**{d['title']} — outstanding**\n\n"
                 + "\n".join(f"- {o['text']} *({o['citation']})*" for o in unmet)
                 + "\n")
    if (ctx.get("regimes") or {}).get("disagreement"):
        text += ("\nThe activated regimes **disagree** about this model. That is a "
                 "fact about the estate rather than a defect: in scope for one "
                 "supervisor and out of scope for another is something somebody "
                 "needs to know.\n")
    return text, _cite(ctx["evidence"], "regime_activated", "tier_assigned")


def attachments(ctx: Dict[str, Any]) -> Rendered:
    """The documents somebody wrote, as opposed to the ones MAYA compiled.

    A compiled document states what the register knows. This section states what
    the humans filed, whether a second person accepted it, and — deliberately —
    what was rejected. A documentation section that lists only the papers that
    passed makes a review look tidier than it was.
    """
    filed = ctx.get("attachments") or []
    if not filed:
        return None, []
    rows = "\n".join(
        f"| {a['title']} | `{a['kind']}` | {_state(a)} | `{a['digest'][7:19]}…` |"
        for a in filed)
    status = ctx.get("attachment_status") or {}
    rejected = status.get("rejected") or 0
    tail = (f"\n\n{rejected} document{'s' if rejected != 1 else ''} "
            f"{'were' if rejected != 1 else 'was'} rejected and remain"
            f"{'' if rejected != 1 else 's'} in the register."
            if rejected else "")
    return (f"Documents filed against this model, stored by digest. What was "
            f"accepted is what is served: the store re-verifies the hash on the "
            f"way out.\n\n"
            f"| Document | Kind | State | Digest |\n|---|---|---|---|\n{rows}\n"
            f"{tail}\n"), \
        _cite(ctx["evidence"], "document_attached", "document_accepted",
              "document_rejected")


def _state(row: Dict[str, Any]) -> str:
    """Accepted by whom — because 'accepted' without a name is not a control."""
    if row["state"] == "accepted":
        return f"accepted by {row['reviewed_by']}"
    if row["state"] == "rejected":
        return f"rejected — {row['review_note']}"
    return "awaiting review"


def provenance(ctx: Dict[str, Any]) -> Rendered:
    nodes = ctx["evidence"]
    chain = ctx.get("chain") or {}
    kinds: Dict[str, int] = {}
    for n in nodes:
        kinds[n["kind"]] = kinds.get(n["kind"], 0) + 1
    rows = "\n".join(f"| `{k}` | {c} |" for k, c in sorted(kinds.items()))
    # The count is of entries about THIS MODEL, not of the whole chain. Quoting
    # the platform-wide length here made every model's document change whenever
    # anything happened anywhere — so a document could go stale because a
    # different team registered a model, and a reader comparing two copies of
    # the same document would find a difference that meant nothing.
    #
    # Validity stays global, correctly: a chain is valid or it is not, and a
    # break anywhere is a break that reaches this document's evidence too.
    return (f"Every statement in this document is drawn from an append-only, "
            f"hash-chained record. The chain is currently "
            f"**{'valid' if chain.get('valid') else 'BROKEN'}**, and "
            f"{len(nodes)} entries in it are about this model.\n\n"
            f"| Evidence kind | Entries about this model |\n|---|---|\n{rows}\n"), \
        [n["id"] for n in nodes]
