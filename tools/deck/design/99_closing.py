# ============================================================ CLOSING
_state["chapter"] = "Closing"

sl, y = content("What this commits to", "Closing")
outs = [("A model is a representation, and error is a quantity",
         "Not a defect to be eliminated. Every version carries an operating "
         "boundary, and a warrant outside it is refused rather than answered — "
         "which is the mark, drawn as a control."),
        ("Governance is never in the serving path",
         "MAYA issues a warrant; an engine acts on it. If MAYA is down, "
         "authorised scoring continues and only new issuance stops. Governance "
         "must not be the bank's single point of failure."),
        ("Nobody is asked to believe anything",
         "Every claim is bound to the artefact it rests on, in one append-only "
         "record — which is also the record segregation of duties is decided "
         "from, because two accounts of who did what can disagree."),
        ("Nothing derivable is stored",
         "Tier, worklist, estate summary, documentation, dossier, board pack: "
         "computed. A stored derivation is one that can go stale, and the stale "
         "one is what somebody reads."),
        ("The laws are the acceptance criteria",
         "Fifteen of twenty-one foundational laws run, and all fourteen warrant "
         "laws run before a signature. The six that do not are named with the "
         "reason, because a law stated but not executed prevented nothing."),
        ("The compliant path is the fast path",
         "If registering a model properly took forty lines of plumbing and "
         "getting it wrong took four, the register would fill with models "
         "nobody registered properly.")]
cw2 = (CW - 0.30 * 2) / 3
for i, (t, d) in enumerate(outs):
    card(sl, ML + (i % 3) * (cw2 + 0.30), y + (i // 3) * 2.30, cw2, 2.10,
         f"0{i+1}", t, d)

# ------------------------------------------------------ what it does not do
sl, y = content("And what it does not do", "Closing · the honest half")
data = [["Not built", "What that means today"],
        ["Evidence chain anchoring",
         "verification compares the chain against itself. Self-consistency of a "
         "chain an attacker could rewrite proves less than it appears to; WORM "
         "and RFC-3161 timestamping remain a design"],
        ["Asymmetric warrant signatures",
         "HMAC today, so verifying a warrant requires holding the key that could "
         "mint one — the wrong shape for a contract handed to engines you do not "
         "control"],
        ["An online feature store",
         "the Delta namespace IS the serving contract. Until a store exists, "
         "L-17 has nothing to compare against and training–serving skew is not "
         "detectable"],
        ["Six foundational laws",
         "L-6, L-11, L-13, L-14, L-15, L-17 — each named in chapter 8 with the "
         "reason it does not yet run"],
        ["Composite warrants and the interaction premium",
         "typed composition gives L-14 something to quantify over; the aggregate "
         "ρ is not built"],
        ["Discovery",
         "nothing sweeps for unregistered models or scans an EUC estate. The "
         "inventory is what somebody registered"]]
th = table(sl, data, ML, y, CW, col_w=[3.6, 8.034],
           row_h=0.38, fs=10, hfs=10, bold_col0=True, first_col_color=CRIMSON)
note(sl, ML, y + th + 0.28, CW, 1.05,
     "A deck that ends on what it built has told you half of it. ",
     "This list is maintained in 12 §0 and in the law table, and both are "
     "checked by tests — because the gap is the part that goes stale first, and "
     "it is the part a reader most needs to be told without asking.")

# -------------------------------------------------------------- last slide
sl = blank()
rect(sl, 0, 0, SW, SH, fill=CRIMSON)
rect(sl, 0, 0, 0.20, SH, fill=CRIMSON_D)
tf = txt(sl, ML + 0.4, 2.05, CW * 0.72, 2.0)
para(tf, "A model is a representation of the world.", size=30, color=WHITE,
     font=SERIF, first=True, space_after=6, line=1.2)
para(tf, "Governance is knowing the difference.", size=30,
     color=RGBColor(0xF2, 0xD8, 0xDC), font=SERIF, space_after=0, line=1.2)
rect(sl, ML + 0.4, 4.55, 1.7, 0.035, fill=RGBColor(0xE8, 0xB8, 0xC0))
tf = txt(sl, ML + 0.4, 4.85, CW * 0.6, 0.9)
para(tf, "MAYA  ·  Evidence, not assertion.", size=13,
     color=RGBColor(0xF4, 0xDF, 0xE3), bold=True, first=True, space_after=4)
para(tf, "Ashutosh Sinha  ·  Independent Researcher", size=11,
     color=RGBColor(0xE8, 0xB8, 0xC0), space_after=0)
_state["n"] += 1
