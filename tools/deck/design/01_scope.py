# ============================================================ SCOPE
_state["chapter"] = "Front matter"
sl, y = content("What this document is, and what it is not", "Front matter · scope")
data = [["Document", "Level", "Answers"],
        ["03 — Requirements", "What must be true", "~200 numbered requirements, personas, regulatory traceability"],
        ["04 — Architecture", "What the containers are, and why", "Deployable units, bounded contexts, extensibility, failure modes"],
        ["14 — Detailed design  ← this deck", "What each component does internally",
         "Interfaces, algorithms, transaction boundaries, concurrency, error taxonomy, SLOs, capacity"],
        ["05–09 — Annexes", "Specific surfaces in depth", "Data model, warrants, features, UI, security"],
        ["11 — Adversarial review", "What was wrong with all of it", "27 findings; 17 required redesign — folded in here"]]
th = table(sl, data, ML, y, CW, col_w=[3.3, 3.0, 5.3], row_h=0.46, fs=11, bold_col0=True, first_col_color=CRIMSON)
rect(sl, ML, y + th + 0.30, CW, 0.95, fill=PARCH)
rect(sl, ML, y + th + 0.30, 0.045, 0.95, fill=CRIMSON)
tf = txt(sl, ML + 0.30, y + th + 0.44, CW - 0.6, 0.75)
runs(tf, [("Test of adequacy. ", CRIMSON, True),
          ("An engineer who has read the architecture should be able to open this document and begin implementing a component "
           "without inventing an interface, guessing a transaction boundary, or deciding an error code. Where that is not yet "
           "true, it is a gap in this document rather than a decision left to the reader.", INK, False)],
     size=12, first=True, space_after=0, line=1.28)
