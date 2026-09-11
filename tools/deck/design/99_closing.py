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
         "Eighteen of twenty-one foundational laws run, and all fourteen warrant "
         "laws run before a signature. The three that do not are named with the "
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
# Two slides rather than one, and the split is the argument. A GAP closes with
# effort; a REFUSAL closes only by making something else untrue. Putting them
# in one table let a reader take the whole list for a backlog.
sl, y = content("What is not built", "Closing \u00b7 the honest half")
data = [["Not built", "What that means today"],
        ["An EUC scanner",
         "MAYA does not crawl the bank\u2019s drives and should not \u2014 a sweep needs "
         "credentials to every repository, notebook server and shared drive in "
         "the institution. The receiving half is built and the CONTRACT a "
         "scanner must meet is published; running one is somebody else\u2019s job, "
         "and nobody has"],
        ["Three foundational laws",
         "L-6, L-11, L-13 \u2014 each named in chapter 8 with the reason. L-14 and "
         "L-17 were on this list and now run. The three that remain are honest "
         "refusals: building a document `put` to satisfy the lens laws would be "
         "building the wrong thing"],
        ["The infrastructure Part IV assumes",
         "no cache, no broker, no outbox, no read replica, no row-level "
         "security, no metrics endpoint \u2014 docs/14 \u00a727 and \u00a728 hold the "
         "list, and every performance figure here is a target, not a measurement"]]
th = table(sl, data, ML, y, CW, col_w=[3.6, 8.034],
           row_h=0.34, fs=9.5, hfs=9.5, bold_col0=True,
           first_col_color=CRIMSON)
note(sl, ML, y + th + 0.22, CW, 0.86,
     "Three rows, and one of them is not code. ",
     "The sweep is a job somebody with the credentials has to run, and it is "
     "deliberately last: a sweep against a register that is not yet good "
     "produces a queue nobody triages, ",
     "which is how every discovery programme that fails, fails.")

sl, y = content("And what will not be built", "Closing \u00b7 the honest half")
data = [["Refused", "What closing it would cost"],
        ["The interaction premium",
         "L-14 says the copy map is the obstruction, so any single figure over "
         "the component ratings is blind to exactly what it would exist to "
         "find. What composes is the ORDER \u2014 the worst tier at stake \u2014 and "
         "not a magnitude"],
        ["An examiner portal",
         "handing a pack over IS built: a time-boxed link to a content digest, "
         "revocable, recording every read including the refused ones. A portal "
         "authenticates a third party INTO the register, and whatever that "
         "session reaches, they reach"],
        ["An online feature store",
         "\u00a77 says MAYA will not sit on the serving path. L-17 is no longer "
         "blocked on it \u2014 the engine attests which namespaces it read and "
         "MAYA compares. A store would buy OBSERVATION rather than "
         "attestation, a smaller claim than this row used to make"],
        ["Non-repudiation to a third party",
         "a warrant is signed with a key DERIVED from the audience, so a "
         "compromised engine forges warrants for itself and nobody else. What "
         "asymmetry would add is proof of authorship to somebody outside the "
         "bank, which nobody has asked for. Published at GET /warrant-signing"],
        ["Spark inside MAYA",
         "monitoring at estate scale moves the SCAN to whatever the firm "
         "already runs \u2014 PSI, AUC and KS are functions of sufficient "
         "statistics, which add across partitions \u2014 while MAYA computes the "
         "metric and compares it. Unlike an external observation, that one "
         "can be replayed"]]
th = table(sl, data, ML, y, CW, col_w=[3.6, 8.034],
           row_h=0.34, fs=9, hfs=9, bold_col0=True, first_col_color=CRIMSON)
note(sl, ML, y + th + 0.22, CW, 0.80,
     "A deck that ends on what it built has told you half of it. ",
     "These five are not a backlog. Each would close only by making something "
     "else untrue \u2014 a theorem, an architecture principle, or a sentence this "
     "platform has been telling people. ",
     "That distinction is what a reader most needs without asking.")

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
tf = txt(sl, ML + 0.4, 4.85, CW * 0.74, 1.5)
para(tf, "MAYA  ·  Evidence, not assertion.", size=13,
     color=RGBColor(0xF4, 0xDF, 0xE3), bold=True, first=True, space_after=4)
para(tf, "Ashutosh Sinha  ·  Independent Researcher  ·  ajsinha@gmail.com",
     size=11, color=RGBColor(0xE8, 0xB8, 0xC0), space_after=10)
para(tf, "Featuresets and parameters: docs/15-featuresets-and-parameters.md   "
         "\u00b7   Composition and retrieval: docs/16-features-composed-and-shaped.md   "
         "\u00b7   Feature platform: docs/07-feature-platform.md",
     size=9.5, color=RGBColor(0xE8, 0xC4, 0xCA), space_after=8, line=1.28)
para(tf, "\u00a9 2026 Ashutosh Sinha. All rights reserved. Proprietary and "
         "confidential \u2014 see LICENSE and NOTICE. Not legal, regulatory or "
         "financial advice.",
     size=8.5, color=RGBColor(0xD8, 0xA0, 0xAC), space_after=0, line=1.25)
_state["n"] += 1
