#!/usr/bin/env python3
"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

CASE STUDY 9 — A polygenic risk score: genomics, and a limitation that is a
property of the model rather than a caveat about it (T2).

    PRS(i) = sum over variants j of  beta_j * dosage_ij

    A weighted sum of how many copies of each risk allele a person carries.
    The weights come from a genome-wide association study; the dosages come
    from that person's genotype.

**Why a governance platform should care about this.** A PRS is used to decide
who gets screened earlier, who gets statins, who is offered risk-reducing
surgery. It is a model that acts on people, its inputs are the most protected
data there is, and it has a known, measured, published failure mode that most
deployments do not record.

**That failure mode is the point of this case study.** A PRS fitted on
European-ancestry cohorts loses most of its discriminative power in African
ancestry — the effect sizes are estimated in one population and the linkage
disequilibrium structure differs in another. It is not a bug and it is not
fixable by better software. It is a property of the parameter set, it is
QUANTIFIED, and MAYA is a place where it travels with the numbers rather than
living in a paper nobody reads at the point of use.

**Who does what.** MAYA registers. The GWAS was run elsewhere, by somebody
else, years ago; the scoring is arithmetic in this file.
"""
from __future__ import annotations

import pathlib
import sys
from typing import Dict, List, Optional

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from _common.casekit import (DAY, Maya, Say, approve_version, attempt,
                             connect, document, ensure_cast, ensure_filled,
                             ensure_version, equation, latex_escape, load_once, mathematics, parse,
                             put_record_in_force, save_json, table)

HERE = pathlib.Path(__file__).resolve().parent
URN = "maya://model/clinical.genomics.cad_prs"
SHORT = "clinical.genomics.cad_prs"
SEMVER = "1.0.0"
VIEW = "subject_genotypes"
FEATURESET = "cad_prs_inputs"
ENTITY = "subject"

AS_OF = 1_767_225_600.0
WINDOW_FROM = 1_704_067_200.0      # 2024-01-01
GENOTYPED_AT = AS_OF - 120 * DAY   # the sample was taken
CALLED_AT = AS_OF - 100 * DAY      # the variant calls came back from the lab

#: The variants. Real rsIDs at real loci associated with coronary artery
#: disease in the published GWAS literature — 9p21 is the most replicated
#: locus in all of complex-trait genetics. The EFFECT SIZES here are
#: illustrative and the README says so: real summary statistics are available
#: from the GWAS Catalog and PGS Catalog under terms this repository should not
#: redistribute.
VARIANTS = [
    # rsID,        locus,       effect allele, beta (log odds per allele)
    ("rs1333049",  "9p21.3",    "C",  0.29),
    ("rs4977574",  "9p21.3",    "G",  0.26),
    ("rs17114036", "PPAP2B",    "A",  0.14),
    ("rs11206510", "PCSK9",     "T",  0.11),
    ("rs6725887",  "WDR12",     "C",  0.17),
    ("rs9982601",  "SLC5A3",    "T",  0.18),
]

#: Twelve subjects' dosages: 0, 1 or 2 copies of the effect allele. Synthetic.
DOSAGES = {
    "SUB-0001": [2, 2, 1, 0, 1, 1], "SUB-0002": [0, 0, 1, 1, 0, 0],
    "SUB-0003": [1, 1, 2, 1, 1, 2], "SUB-0004": [2, 1, 1, 2, 2, 1],
    "SUB-0005": [0, 1, 0, 0, 1, 0], "SUB-0006": [1, 2, 2, 1, 0, 1],
    "SUB-0007": [2, 2, 2, 2, 1, 2], "SUB-0008": [0, 0, 0, 1, 0, 1],
    "SUB-0009": [1, 0, 1, 0, 2, 0], "SUB-0010": [1, 1, 1, 1, 1, 1],
    "SUB-0011": [2, 1, 0, 1, 1, 2], "SUB-0012": [0, 1, 1, 0, 0, 1],
}

#: THE STATED LIMITATION, quantified. Published transferability studies report
#: roughly this pattern for CAD scores developed in European cohorts. These
#: figures are illustrative of a real and well-documented effect; the README
#: cites the literature rather than pretending these are measurements.
TRANSFERABILITY = [
    ("European",       1.00, "the development population"),
    ("South Asian",    0.72, "attenuated; different LD structure"),
    ("East Asian",     0.65, "attenuated; several loci not polymorphic"),
    ("African",        0.42, "SEVERELY attenuated; shorter LD blocks mean the "
                             "tag SNPs do not tag the causal variants"),
]


def kernel_expression() -> str:
    """The score, as one closed form the register holds.

    Six variants, so it is written out. A production score uses hundreds of
    thousands of variants and would be an artifact rather than an expression —
    which is a real boundary and the README says where it falls.
    """
    return " + ".join(f"beta_{rs} * dose_{rs}" for rs, _l, _a, _b in VARIANTS)


KERNEL = {
    "runtime": "formula",
    "parameter_kind": "estimated_coefficients",
    "fit_procedure": "estimate",
    "deterministic": True,
    "entry": {"expression": kernel_expression(), "target": "prs_cad"},
    "input_schema": [
        {"name": f"dose_{rs}", "dtype": "numeric",
         "symbol": rf"g_{{{i}}}", "unit": "copies of the effect allele, 0-2"}
        for i, (rs, _l, _a, _b) in enumerate(VARIANTS, start=1)
    ],
    "parameter_schema": [
        {"name": f"beta_{rs}", "dtype": "numeric",
         "symbol": rf"\beta_{{{i}}}", "unit": "log odds per effect allele"}
        for i, (rs, _l, _a, _b) in enumerate(VARIANTS, start=1)
    ],
    "output_schema": [{"name": "prs_cad", "dtype": "numeric",
                       "unit": "log-odds score, unstandardised"}],
}


def rows() -> List[Dict[str, object]]:
    out = []
    for subject, doses in DOSAGES.items():
        row = {"entity_id": subject,
               # The two clocks are genuinely different here and the gap is
               # weeks: a sample is TAKEN on one day and the variant calls come
               # back from the laboratory on another. A score computed "as of"
               # a date must not use calls that had not been returned yet.
               "event_ts": GENOTYPED_AT, "ingest_ts": CALLED_AT}
        for (rs, _l, _a, _b), dose in zip(VARIANTS, doses):
            row[f"dose_{rs}"] = float(dose)
        out.append(row)
    return out


def score(doses: List[int]) -> float:
    return sum(b * d for (_rs, _l, _a, b), d in zip(VARIANTS, doses))


# ================================================================== the build
def main() -> int:
    args = parse("Case study 9 — a polygenic risk score")
    out = pathlib.Path(args.out) if args.out else HERE
    say = Say("CASE STUDY 9 — a polygenic risk score, and a limitation that is "
              "a property")

    maya = connect(args)
    say.step("Make sure the people exist")
    people = ensure_cast(maya, args.url)

    # ------------------------------------------------------------ features
    say.step("Register one feature per variant — and flag what they are")
    for rs, locus, allele, _beta in VARIANTS:
        attempt(f"dose_{rs} ({locus})",
                lambda r=rs, l=locus, a=allele: maya.features.define(
                    name=f"dose_{r}", entity=ENTITY, dtype="numeric",
                    description=f"copies of the {a} effect allele at {r} "
                                f"({l}), 0-2",
                    owner="person/a.mehta", source_system="genotyping array",
                    sensitivity="restricted",
                    # The two flags that matter, and they are not decoration:
                    # genotype is personal data under GDPR Article 9 and
                    # ancestry is inferable from it, which makes every one of
                    # these a potential proxy for a protected characteristic.
                    pii=True, protected_basis=True))
    say.did("pii=True and protected_basis=True on every variant. Genotype is "
            "special-category data, and ancestry is inferable from it — so "
            "these are proxies for a protected characteristic whether or not "
            "anybody intended them to be")

    say.step("Load the genotypes — and note the gap between the two clocks")
    attempt("the view", lambda: maya.features.create_view(
        name=VIEW, entity=ENTITY, owner="person/a.mehta",
        features=[f"dose_{rs}" for rs, _l, _a, _b in VARIANTS],
        description=(f"variant dosages. event_ts is when the sample was taken; "
                     f"ingest_ts is when the laboratory returned the calls, "
                     f"{(CALLED_AT - GENOTYPED_AT) / DAY:.0f} days later.")))
    load_once(maya, VIEW, rows())
    say.did(f"{(CALLED_AT - GENOTYPED_AT) / DAY:.0f} days between the sample "
            f"and the calls. A score computed 'as of' a clinic date must not "
            f"use calls that had not come back yet — which is the same "
            f"bitemporal rule as a bank's, with a longer lag")

    say.step("Declare the featureset")
    attempt(FEATURESET, lambda: maya.featuresets.define(
        name=FEATURESET, entity=ENTITY,
        slots={f"dose_{rs}": "numeric" for rs, _l, _a, _b in VARIANTS},
        description="the variant dosages a coronary artery disease PRS reads"))
    fs_version = ensure_filled(
        maya, FEATURESET,
        {f"dose_{rs}": f"dose_{rs}" for rs, _l, _a, _b in VARIANTS})

    # --------------------------------------------------------------- model
    say.step("Register the model")
    attempt("the model", lambda: maya.models.register(
        urn=URN, name="Coronary artery disease polygenic risk score",
        model_class="clinical.risk.genomic", domain="clinical",
        owner="person/j.okafor", legal_entity="LE-UK-01",
        purpose="stratifying screening and preventive therapy for coronary "
                "artery disease"))
    attempt("its risk tier", lambda: maya.models.assess(
        SHORT, exposure=0, purpose_class="clinical_decision",
        feature_count=len(VARIANTS), uses_alternative_data=True,
        interpretable=True), already="already tiered")
    version_record = ensure_version(maya, SHORT, semver=SEMVER, kernel=KERNEL)
    say.maya(f"trainability class {version_record.get('trainability_class')}")

    say.step("Approve the version")
    _approved, tier = approve_version(
        maya, people, urn=URN, semver=SEMVER,
        statement="Six-variant CAD score. The transferability limitation is "
                  "quantified on the parameter set and was the substance of "
                  "the review.")
    say.maya(f"risk tier {tier}")

    say.step("Put the record in force")
    put_record_in_force(maya, people, urn=URN,
                        note="Genomic risk score, owned by clinical genetics.")

    say.step("Grant the standing entitlements")
    lab_grant = attempt("estimate, in the lab", lambda: maya.warrants.grant(
        urn=URN, principal="person/a.mehta",
        declared_use="model_development", environment="lab"))
    grant_id = (lab_grant or {}).get("id") or _existing_grant(maya, URN, "lab")
    attempt("stratify, in the clinic", lambda: maya.warrants.grant(
        urn=URN, principal="person/a.mehta",
        declared_use="clinical_decision", environment="prod"))

    # ---------------------------------------------------- training warrant
    say.step("Ask MAYA for the TRAINING warrant")
    fit_warrant = maya.warrants.for_fitting(
        urn=f"{URN}@{SEMVER}", principal="person/a.mehta",
        featureset=FEATURESET, featureset_version=fs_version,
        window={"from": WINDOW_FROM, "to": AS_OF}, as_of=AS_OF)
    fit_id = fit_warrant.get("warrant_id")
    say.maya(f"training warrant {fit_id}")
    save_json(out / "warrant-training.json", fit_warrant,
              what="the training warrant")

    # ------------------------------------------------- deliver the weights
    say.step("Deliver the GWAS effect sizes — with the limitation attached")
    say.note("the GWAS was run years ago, on a different cohort, by somebody "
             "else. MAYA is not fitting anything; it is taking delivery of "
             "numbers with a provenance")
    values = {f"beta_{rs}": beta for rs, _l, _a, beta in VARIANTS}
    for name, beta in values.items():
        print(f"        {name:<22} {beta:>7.3f}")

    recorded = attempt("the parameter set", lambda: maya.parameters.record(
        urn=URN, semver=SEMVER, name="cad-prs-eur-2024", kind="coefficients",
        values=values, provenance="fitted", warrant_id=grant_id,
        featureset=FEATURESET, featureset_version=fs_version,
        window={"from": WINDOW_FROM, "to": AS_OF}, as_of=AS_OF,
        diagnostics={
            "variants": len(VARIANTS),
            "development_ancestry": "European",
            "source": "GWAS summary statistics; see the README for the "
                      "catalogues these are drawn from",
            "fit_warrant_document": fit_id,
            # The limitation, QUANTIFIED, travelling with the numbers.
            "transferability_r2_ratio": {
                name: ratio for name, ratio, _why in TRANSFERABILITY},
            "limitation":
                "Developed in European-ancestry cohorts. Discriminative "
                "performance attenuates in other ancestries — to roughly 42% "
                "of European in African ancestry — because effect sizes are "
                "estimated in one population and linkage disequilibrium "
                "structure differs in another. This is a property of the "
                "parameter set, not a defect to be fixed downstream.",
            "not_measured": "calibration in this clinic's own population",
        },
        note="European-ancestry weights; transferability attenuation "
             "quantified in the diagnostics"))
    parameter_set_id = (recorded or {}).get("id") or \
        (recorded or {}).get("parameter_set_id")

    say.step("A different person accepts it — and the limitation is what they "
             "are accepting")
    if parameter_set_id:
        attempt("accepted by s.iqbal (second line)",
                lambda: people["s.iqbal"].parameters.review(
                    parameter_set_id, accept=True,
                    note="Accepted for the European-ancestry screening pathway "
                         "ONLY. The attenuation figures are on the set; use "
                         "outside that pathway is a different decision that "
                         "nobody has taken."),
                already="already reviewed")
    say.did("the acceptance names the population it is accepted FOR. A "
            "parameter set approved without a population is one that will be "
            "used on everybody")

    # -------------------------------------------------- execution + scoring
    say.step("Ask MAYA for the EXECUTION warrant")
    run_warrant = None
    try:
        run_warrant = maya.warrants.resolve(
            urn=f"{URN}@{SEMVER}", principal="person/a.mehta",
            declared_use="clinical_decision", environment="prod", verb="score")
        say.maya(f"execution warrant {run_warrant.get('warrant_id')}")
        save_json(out / "warrant-execution.json", run_warrant,
                  what="the execution warrant")
    except Exception as exc:
        say.note(f"execution warrant not issued: {exc}")

    maths = mathematics(maya, URN, SEMVER)
    scored: List[Dict[str, object]] = []
    if run_warrant is not None:
        say.step("Score the cohort — LOCALLY, under that warrant")
        coefficients = _coefficients(run_warrant, maya, values)
        ranked = sorted(DOSAGES.items(), key=lambda kv: -score(kv[1]))
        print(f"        {'subject':<12}{'PRS':>8}{'percentile':>12}"
              f"   {'alleles carried'}")
        n = len(ranked)
        for rank, (subject, doses) in enumerate(ranked):
            value = _predict(maths, subject, doses, coefficients)
            pct = 100.0 * (n - rank - 0.5) / n
            scored.append({"subject": subject, "prs": value, "percentile": pct})
            print(f"        {subject:<12}{value:>8.3f}{pct:>11.0f}%   "
                  f"{sum(doses)} of {2 * len(VARIANTS)}")
        say.engine(f"{len(scored)} subjects scored locally")
        say.note("a PRS is meaningless as an absolute number — it is a "
                 "PERCENTILE within a reference population, and the reference "
                 "population is the one the weights came from. That is the "
                 "same limitation again, wearing different clothes")

    say.step("Write the LaTeX specification")
    path = write_document(out, maths, version_record, fit_warrant, run_warrant,
                          values, scored, tier)
    print(f"\n    LaTeX written to {path}")

    print(f"\n{'=' * 78}")
    print("Done. A clinical model whose most important property is a stated,")
    print("quantified limitation — travelling with the numbers, not in a paper.")
    print(f"{'=' * 78}")
    return 0


def _existing_grant(maya: Maya, urn: str, environment: str) -> Optional[str]:
    for row in (maya.call("GET", "/warrants") or {}).get("warrants", []):
        if row.get("model_urn") == urn and row.get("environment") == environment:
            return row.get("id")
    return None


def _coefficients(warrant, maya: Maya, fallback):
    ref = (warrant.get("parameters") or {}).get("source") or {}
    set_id = ref.get("parameter_set")
    if not set_id:
        return fallback
    return (maya.parameters.get(str(set_id)) or {}).get("values") or fallback


def _predict(maths, subject: str, doses: List[int], coefficients) -> float:
    namespace: Dict[str, object] = {}
    exec(compile(str(maths.get("python") or ""),                  # noqa: S102
                 "<maya-derived>", "exec"), namespace)
    row = {f"dose_{rs}": float(d)
           for (rs, _l, _a, _b), d in zip(VARIANTS, doses)}
    wanted = list(maths.get("inputs") or []) + list(maths.get("parameters") or [])
    supplied = {**row, **coefficients}
    return float(namespace["predict"](**{k: supplied[k] for k in wanted}))


def write_document(out, maths, version_record, fit_warrant, run_warrant,
                   values, scored, tier):
    variant_rows = [[latex_escape(rs), latex_escape(locus), allele,
                     f"{beta:.3f}"] for rs, locus, allele, beta in VARIANTS]
    transfer_rows = [[latex_escape(name), f"{ratio:.2f}", latex_escape(why)]
                     for name, ratio, why in TRANSFERABILITY]
    top = [s for s in scored][:4]
    blocks = [
        r"\section{What this model is}",
        r"A polygenic risk score for coronary artery disease: "
        r"$\mathrm{PRS}_i = \sum_j \beta_j g_{ij}$, a weighted sum of how many "
        r"copies of each risk allele a person carries. The weights come from a "
        r"genome-wide association study; the dosages come from that person's "
        r"genotype. MAYA classifies it \textbf{T2} --- coefficients estimated "
        r"from a sample.",
        "It is used to decide who is screened earlier and who is offered "
        "preventive therapy, which is what makes the section below the most "
        "important one in this document.",

        r"\section{The equation, as the register holds it}",
        equation(str(maths.get("latex") or ""),
                 str(maths.get("expression") or "")),

        r"\section{The variants and their weights}",
        table(variant_rows,
              header=["rsID", "Locus", "Effect allele", r"$\beta$"],
              spec="lllr"),
        r"The 9p21.3 locus is the most replicated association in complex-trait "
        r"genetics. \textbf{The effect sizes here are illustrative}; real "
        r"summary statistics are published in the GWAS Catalog and the PGS "
        r"Catalog under terms this repository does not redistribute.",

        r"\section{The limitation, which is a property and not a caveat}",
        "A PRS developed in European-ancestry cohorts loses much of its "
        "discriminative power in other ancestries. Effect sizes are estimated "
        "in one population and linkage-disequilibrium structure differs in "
        "another, so the tag variants do not tag the causal variants equally "
        "well. This is not a defect to be fixed downstream:",
        table(transfer_rows,
              header=["Ancestry", r"Relative $R^2$", "Why"],
              spec=r"lrp{78mm}"),
        r"\textbf{It travels with the parameter set.} The attenuation figures "
        r"are diagnostics on the recorded coefficients, so anybody reading the "
        r"numbers reads the limitation at the same moment --- rather than "
        r"finding it in a paper, or not finding it. And the second-line "
        r"acceptance names the population the set is accepted \emph{for}: a "
        r"parameter set approved without a population is one that will be used "
        r"on everybody.",

        r"\section{Protected data, declared as such}",
        r"Every variant feature carries \texttt{pii=True} and "
        r"\texttt{protected\_basis=True}. Genotype is special-category data, "
        r"and \emph{ancestry is inferable from it} --- which makes each of "
        r"these a potential proxy for a protected characteristic whether or "
        r"not anybody intended it. Declaring it makes the fairness question "
        r"answerable by query rather than by interview.",

        r"\section{The cohort}",
        table([[latex_escape(str(s["subject"])), f"{float(s['prs']):.3f}",
                f"{float(s['percentile']):.0f}\\%"] for s in top],
              header=["Subject", "PRS", "Percentile"], spec="lrr"),
        r"Highest four of twelve. \textbf{A PRS is meaningless as an absolute "
        r"number} --- it is a percentile within a reference population, and the "
        r"reference population is the one the weights came from. That is the "
        r"transferability limitation again, wearing different clothes.",

        r"\section{Governance}",
        table([["Model URN", latex_escape(str(version_record.get("urn", "—")))],
               ["Version", latex_escape(str(version_record.get("semver", "—")))],
               ["Trainability class",
                latex_escape(str(version_record.get("trainability_class", "—")))],
               ["Risk tier", str(tier)],
               ["Variants", str(len(VARIANTS))],
               ["Training warrant",
                latex_escape(str((fit_warrant or {}).get("warrant_id", "—")))],
               ["Execution warrant",
                latex_escape(str((run_warrant or {}).get("warrant_id", "not issued")))]],
              header=["Field", "Value"], spec="ll"),
    ]
    return document(path=out / "prs-specification.tex",
                    title="Coronary Artery Disease PRS --- Model Specification",
                    subtitle=latex_escape("Registered in MAYA · " + SHORT),
                    blocks=blocks)


if __name__ == "__main__":
    raise SystemExit(main())
