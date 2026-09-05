# ============================================================ CH 14
divider("14", "Documentation, as a Graph",
        "Five moments, five objects, and the pins that connect them.",
        ["When documentation actually arrives", "The moment that had no document",
         "The dossier", "What travels to somebody without a login"])

# ------------------------------------------------------- five moments
sl, y = content("Documentation does not arrive all at once about one thing",
                "Documentation · five moments")
data = [["When", "About", "Example", "Could it be filed?"],
        ["before anything runs", "the MODEL",
         "the methodology paper, the literature the approach comes from", "yes"],
        ["a version is created", "the VERSION",
         "the specification of that kernel", "yes"],
        ["a fit warrant executes", "the PARAMETER SET",
         "the convergence study, the note explaining one morning", "NO"],
        ["a featureset is filled", "the FEATURESET VERSION",
         "the data dictionary, the source-system agreement", "NO"],
        ["validation concludes", "the VALIDATION",
         "the independent recode, the reviewer's working", "yes"]]
th = table(sl, data, ML, y, CW, col_w=[2.4, 2.5, 4.9, 1.834],
           row_h=0.36, fs=10, hfs=10, bold_col0=True, first_col_color=CRIMSON)
note(sl, ML, y + th + 0.30, CW, 1.55,
     "Two of the five were unfilable, and they are the two that matter most. ",
     "A calibrated model produces a parameter set every morning. A featureset's "
     "documentation is read by every model fitted from it, so filing it against "
     "one of them makes it invisible to the rest — and filing it against the "
     "SET rather than the version describes something that has since moved, "
     "which is finding C-2 in documentation's clothing.")

# ------------------------------------------------- the training record
sl, y = content("Two hundred and fifty governed acts a year, none of them readable",
                "Documentation · the training record")
tf = txt(sl, ML, y, CW * 0.52, 3.4)
para(tf, "Hull–White is solved every morning.", size=13, color=CRIMSON,
     bold=True, font=SERIF, first=True, space_after=10)
para(tf, "Each solve is a governed act: a warrant behind it, a featureset "
         "version read, diagnostics returned, a reviewer's signature on it.",
     size=12, color=INK, space_after=9, line=1.28)
para(tf, "And none of them had a record anybody could read. The note explaining "
         "the one morning it went wrong lived in an email.",
     size=12, color=INK, space_after=9, line=1.28)
para(tf, "So the record is COMPILED, from what the register already holds. All "
         "two hundred and fifty exist whether or not somebody had time to write "
         "one — and the one that needs a human note has a place to put it, as an "
         "attachment against the same subject.",
     size=11, color=SLATE, space_after=0, line=1.28)

x = ML + CW * 0.56
data = [["Section", "From"],
        ["What this is", "kind, provenance, state"],
        ["Under what authority", "the warrant id"],
        ["What it read", "the featureset VERSION, window, as_of, snapshot"],
        ["What it produced", "the values and their digest"],
        ["What the fit reported", "the diagnostics"],
        ["Who accepted it", "and who recorded it — never the same person"]]
th = table(sl, data, x, y, CW * 0.44, col_w=[2.0, 3.34],
           row_h=0.30, fs=9.5, hfs=9.5, bold_col0=True, first_col_color=CRIMSON)
note(sl, x, y + th + 0.26, CW * 0.44, 1.5,
     "A fit with no warrant is a NAMED GAP, not a blank section. ",
     "A fitted set with no warrant has no answer to “which data produced these "
     "numbers”, and that is worth saying out loud rather than leaving a heading "
     "with nothing under it.")

# ------------------------------------------------------------ the dossier
sl, y = content("The dossier: the graph, walked from a model",
                "Documentation · the holistic view")
h = code(sl, ML, y, CW * 0.56, [
    "model",
    " ├── attached : methodology paper, literature, vendor note",
    " ├── compiled : development document, model card, Annex IV",
    " └── version 1.0.0",
    "      ├── attached : kernel specification",
    "      ├── compiled : validation report",
    "      ├── parameter set ps-8817      (fitted 2026-03-31)",
    "      │    ├── compiled : TRAINING RECORD",
    "      │    └── attached : convergence study",
    "      └── fitted from  featureset sb_core @ v1",
    "           ├── attached : data dictionary, source agreement",
    "           └── feature dscr",
    "                └── attached : business definition",
], fs=9, title="COMPUTED, NEVER STORED")

x = ML + CW * 0.60
tf = txt(sl, x, y, CW * 0.40, 3.8)
para(tf, "Three properties", size=12.5, color=CRIMSON, bold=True, font=SERIF,
     first=True, space_after=9)
for lead, rest in [
    ("It follows the pins, not the names. ",
     "sb_core@v1, never sb_core. A document about the set describes something "
     "that has since moved."),
    ("Gaps are named. ",
     "Every node with nothing filed says what was expected. A page that "
     "silently omits what it could not find reads as complete."),
    ("It is computed. ",
     "Its inputs are all versioned or immutable, so there is nothing to keep in "
     "step — and a stored dossier would be a second account of the "
     "documentation, able to disagree with the first."),
]:
    runs(tf, [("→  ", CRIMSON, True), (lead, INK, True), (rest, SLATE, False)],
         size=10.5, space_after=8)

# ------------------------------------------------------------ export pack
sl, y = content("And the whole of it travels to somebody without a login",
                "Documentation · the export pack")
steps(sl, ML, y, CW, [
    ("01", "Self-contained", "they cannot query the platform, so the pack "
                             "carries the register state, the documents, the "
                             "attachments and the evidence segment"),
    ("02", "Digested", "they cannot take its word for anything, so every member "
                       "is hashed and the manifest is hashed over the members"),
    ("03", "Comparable", "the content digest EXCLUDES the manifest, so two packs "
                         "of the same state agree — “has anything changed” is "
                         "one comparison"),
    ("04", "Honest", "gaps.md first: what could not be included, and why"),
], h=1.80)
note(sl, ML, y + 2.10, CW, 1.60,
     "Two things it deliberately does not do. ",
     "It does not AUTHOR anything — the documents are rendered, not compiled, "
     "because cutting a pack monthly should not silently author four documents a "
     "month. And it does not re-materialise personal data: a flagged node "
     "carries its erasable pointer into the pack exactly as it does in the "
     "platform, because resolving it would put personal data where an erasure "
     "request cannot reach it.")
