# ============================================================ CH 3
_state["chapter"] = "3 · Five Positions, and Their Cost"

sl, y = content("Five positions, and what each one costs",
                "Philosophy · the stance")
data = [["Position", "What it means", "What it costs"],
        ["It does not run models",
         "MAYA issues a signed, expiring, entitlement-bound warrant and an "
         "engine acts on it",
         "MAYA cannot guarantee anything about a run it never saw — only about "
         "the authority behind it"],
        ["Evidence, not assertion",
         "every claim is bound to the artefact it rests on, in an append-only "
         "hash-linked record",
         "the record can only be as good as what was written to it; anchoring "
         "it outside the system is not built"],
        ["Refusals are the product",
         "every refusal names what was violated and what to do about it",
         "a platform that refuses is a platform people route around unless the "
         "compliant path is also the fast one"],
        ["Laws, not conventions",
         "twenty-one foundational laws stated, of which eighteen are executable "
         "and run in the ordinary test suite",
         "three do not run; the rest run on every push and a failing one fails "
         "the build"],
        ["Derived, not entered",
         "risk tier, worklist, estate summary, documentation, board pack: "
         "computed from the register",
         "computation costs latency, and a derivation nobody can read is a "
         "black box of its own"]]
th = table(sl, data, ML, y, CW, col_w=[2.7, 4.5, 4.434],
           row_h=0.42, fs=10, hfs=10, bold_col0=True, first_col_color=CRIMSON)
note(sl, ML, y + th + 0.26, CW, 1.15,
     "A position with no stated cost is marketing. ",
     "Each of these is a trade, and the right-hand column is the half that "
     "usually goes unwritten. Two of the five are worked out on their own "
     "slide next — the first, because it decides the whole architecture, and "
     "the third, because it is the one people find strange. The other three "
     "are argued where they bite, in chapters 7, 8 and 19.")

# ------------------------------------------------- the nine refusals
sl, y = content("Nine things it will not build, and what each one protects",
                "Philosophy · the refusals are load-bearing")
data = [["Asked for", "Refused because", "What would stop meaning anything"],
        ["Managed serving",
         "the register and the runtime would be one process — and one that "
         "argues a warrant survives its own unavailability",
         "every claim to be an independent record of execution"],
        ["Convert an artifact",
         "converting means loading and running a model",
         "the equivalence claim it holds to a standard"],
        ["Submit training jobs",
         "the register would be on the failure path of what it observes",
         "the run register as an account of somebody else's work"],
        ["Accept a `passed` flag",
         "whoever computed the number would set the pass mark",
         "the threshold this firm's second line set"],
        ["Recommend promotion",
         "it would pre-empt the approval it is evidence for",
         "the second-line approval itself"],
        ["Edit a compiled document",
         "every sentence cites a node; the prose would outlive the citation",
         "traceability of every sentence in it"],
        ["Configure the state graph",
         "a firm could add a transition that skips approval",
         "'approved' meaning the same in two institutions"],
        ["Sign artifacts",
         "the platform would hold the key that could forge one",
         "the provenance check, verifying its own signature"],
        ["Hide the cheap remediation",
         "a solver with no view on KIND recommends the waiver every time",
         "the difference between safe and looking compliant"]]
th = table(sl, data, ML, y, CW, col_w=[2.3, 4.6, 4.734], row_h=0.36, fs=9,
           hfs=9.5, bold_col0=True, first_col_color=CRIMSON)
note(sl, ML, y + th + 0.20, CW, 1.05,
     "One sentence underneath all nine. ",
     "A platform that both authorises an act and performs it is the only "
     "witness to its own execution. Every row above is that sentence applied "
     "to a different request — and the useful question when evaluating a "
     "governance platform is not what it can do, but what it declines to do "
     "and whether the answer is about architecture or about a roadmap.")

# ------------------------------------------ it does not run models, in detail
sl, y = content("Why governance must not be in the serving path",
                "Philosophy · the serving path")
steps(sl, ML, y, CW, [
    ("01", "A consumer holds a name", "maya://model/credit.pd.smallbiz#champion "
                                      "— an alias, never a version, never a path"),
    ("02", "The name resolves at the moment of use",
     "against the policy in force then, not the policy in force when the caller "
     "was written"),
    ("03", "An engine acts on the warrant",
     "MAYA is not on the path; if it is down, already-authorised scoring "
     "continues"),
    ("04", "Only new issuance stops",
     "which is the correct failure mode: governance must not be the bank's "
     "single point of failure"),
], h=1.75)
note(sl, ML, y + 2.05, CW, 1.20,
     "Nobody redeploys to promote a version, because no consumer ever held "
     "one. ",
     "Revocation bites when the current warrant expires — sixty seconds for a "
     "Tier 1 model. And an open blocking finding stops the name resolving at "
     "all, so a validation finding stops the model rather than generating an "
     "email somebody files.")

# ----------------------------------------------- refusals are the product
sl, y = content("What a refusal has to contain to be worth having",
                "Philosophy · refusals")
h = code(sl, ML, y, CW * 0.56, [
    '{"error":       "nothing_to_fit",',
    ' "detail":      "markets.pricing.vanilla 1.0.0 is T0: it has no',
    '                 parameters, so there is no point of P to move to",',
    ' "remediation": "if this model does have parameters, the version',
    '                 declares the wrong parameter kind; fix the version',
    '                 rather than the warrant"}',
], fs=9.5, title="A REFUSAL, IN FULL")

x = ML + CW * 0.60
tf = txt(sl, x, y, CW * 0.40, 3.4)
para(tf, "Three parts, and the third is the one clients throw away",
     size=12.5, color=CRIMSON, bold=True, font=SERIF, first=True, space_after=9)
for lead, rest in [
    ("error ", "— a code a caller can branch on, and it says WHO must act"),
    ("detail ", "— which fact about the request made it incoherent, named"),
    ("remediation ", "— what to do instead. Without it a refusal is a wall, and "
                     "a wall is what people build a workaround around"),
]:
    runs(tf, [(lead, CRIMSON, True), (rest, SLATE, False)], size=10.5,
         space_after=8)
para(tf, "Notice what it does not say: “no”. It names the fact that made the "
         "request meaningless, and points at the version rather than the "
         "request — because that is where the error is.",
     size=10.5, color=INK, space_after=0, line=1.26)

note(sl, ML, y + h + 0.30, CW * 0.56, 1.15,
     "The interesting behaviour of this platform is what it will not do. ",
     "Chapter 15 collects every refusal it can issue; they are the clearest "
     "statement of what the design believes.")
