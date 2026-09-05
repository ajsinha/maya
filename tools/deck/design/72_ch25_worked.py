# ============================================================ CH 25
divider("25", "A Worked Example",
        "Real data, real fits: the S&P 500 and the US unemployment rate.",
        ["The data, and its two clocks",
         "The gap that is really there",
         "Two models over one X",
         "Extending it, and what that forces"])

# ------------------------------------------------------------- the raw data
sl, y = content("Two real series, on two different clocks",
                "A worked example")

data = [["entity_id", "event_ts", "ingest_ts", "px_close"],
        ["us_equity_index", "2026-08-27", "2026-08-27", "7730.99"],
        ["us_equity_index", "2026-08-28", "2026-08-28", "7711.76"],
        ["us_equity_index", "2026-08-31", "2026-08-31", "7686.14"],
        ["us_equity_index", "2026-09-01", "2026-09-01", "7631.47"],
        ["us_equity_index", "2026-09-02", "2026-09-02", "7666.60"]]
h = table(sl, data, ML, y, CW * 0.46, col_w=[1.85, 1.35, 1.35, 1.2],
          row_h=0.27, fs=8.5, hfs=8.5, bold_col0=True)
tf = txt(sl, ML, y + h + 0.14, CW * 0.46, 0.44)
runs(tf, [("sp500_daily.csv", CRIMSON, True),
          ("   FRED series SP500, 258 rows. The two clocks are equal: an index "
           "close is known the day it happens.", SLATE, False)],
     size=8.8, first=True, space_after=0, line=1.18)

data2 = [["entity_id", "event_ts", "ingest_ts", "u3_rate"],
         ["us_equity_index", "2026-06-30", "2026-07-03", "4.2"],
         ["us_equity_index", "2026-07-31", "2026-08-07", "4.1"],
         ["us_equity_index", "2026-08-31", "2026-09-04", "4.1"]]
h2 = table(sl, data2, ML, y + h + 0.62, CW * 0.46,
           col_w=[1.85, 1.35, 1.35, 1.2], row_h=0.27, fs=8.5, hfs=8.5,
           bold_col0=True)
tf = txt(sl, ML, y + h + h2 + 0.76, CW * 0.46, 0.60)
runs(tf, [("us_unemployment_monthly.csv", CRIMSON, True),
          ("   FRED series UNRATE. ingest_ts is the first Friday of the "
           "following month \u2014 the BLS release convention, computed and "
           "labelled as such rather than passed off as a fetched vintage date.",
           SLATE, False)],
     size=8.8, first=True, space_after=0, line=1.18)

x = ML + CW * 0.50
tf = txt(sl, x, y, CW * 0.50, 0.34)
para(tf, "August\u2019s rate was true on the 31st and known on the 4th",
     size=13, color=CRIMSON, bold=True, font=SERIF, first=True, space_after=8)
para(tf, "A model trained on the 1st of September using August\u2019s figure "
         "is using a number that did not exist yet. It back-tests beautifully "
         "and disappoints in production, and no metric says why.",
     size=11, color=INK, space_after=10, line=1.25)
para(tf, "That is not a hypothetical about leakage. It is the ordinary shape "
         "of every macroeconomic series a bank uses \u2014 published late, "
         "revised afterwards \u2014 and it is why every row here carries two "
         "stamps rather than one.",
     size=11, color=SLATE, space_after=10, line=1.25)
runs(tf, [("Both are scalars, shape []. ", CRIMSON, True),
          ("The curve earlier was a vector; these are not. The shape is "
           "declared either way, because a shape nobody states is a shape "
           "somebody assumes.", SLATE, False)],
     size=11, space_after=0, line=1.25)
note(sl, x, y + 3.18, CW * 0.50, 0.92,
     "The numbers on these slides were not invented. ",
     "Both files were pulled from FRED on 4 September 2026 and ship beside the "
     "deck in docs/examples/ \u2014 ",
     "every figure that follows was computed from them.")


# ---------------------------------------------------- the gap and the fill
sl, y = content("The gap in October is really there", "A worked example")

data = [["month", "S&P 500 close", "return %", "u3 rate", "as the set reads it"],
        ["2025-09", "6688.46", "+3.53", "4.4", "4.4"],
        ["2025-10", "6840.20", "+2.27", "\u2014  not published",
         "4.4   carried forward"],
        ["2025-11", "6849.09", "+0.13", "4.5", "4.5"],
        ["2025-12", "6845.50", "\u22120.05", "4.4", "4.4"],
        ["2026-03", "6528.52", "\u22125.09", "4.3", "4.3"],
        ["2026-04", "7209.01", "+10.42", "4.3", "4.3"],
        ["2026-08", "7686.14", "+2.62", "4.1", "4.1"]]
h = table(sl, data, ML, y, CW * 0.60, col_w=[1.1, 1.55, 1.15, 1.6, 1.58],
          row_h=0.28, fs=9, hfs=9, bold_col0=True, first_col_color=CRIMSON)
tf = txt(sl, ML, y + h + 0.18, CW * 0.60, 0.60)
runs(tf, [("Twelve months, one of them missing. ", CRIMSON, True),
          ("FRED publishes no unemployment rate for October 2025. Nothing was "
           "constructed to make this slide interesting \u2014 the hole is in "
           "the series.", SLATE, False)],
     size=10, first=True, space_after=0, line=1.22)

x = ML + CW * 0.64
h2 = code(sl, x, y, CW * 0.36, [
 "defaults:",
 "  align: {axis: event_ts,",
 "          rule:  flat_forward}",
 "  fill:  {u3_rate: keep}",
 "",
 "# filled: 1 of 12 (8.3%)",
 "# carried from 2025-09,",
 "#   ingest_ts 2025-10-03",
], fs=8.5)
tf = txt(sl, x, y + h2 + 0.22, CW * 0.36, 2.4)
para(tf, "Forward, and only forward", size=12, color=CRIMSON, bold=True,
     font=SERIF, first=True, space_after=7)
para(tf, "Interpolating October between September and November would use "
         "November\u2019s 4.5 \u2014 published on the 5th of December \u2014 "
         "to fill a row dated the 31st of October.",
     size=10, color=INK, space_after=8, line=1.22)
para(tf, "The platform allows that and stamps it honestly: the filled value "
         "would carry December\u2019s ingest clock, so a point-in-time read in "
         "October excludes it. The leakage is not forbidden, it is made "
         "impossible to hide.",
     size=10, color=SLATE, space_after=8, line=1.22)
runs(tf, [("And the fill rate is part of the answer. ", CRIMSON, True),
          ("One month in twelve is 8%, which is fine. Past a fifth, the report "
           "says so loudly.", SLATE, False)],
     size=10, space_after=0, line=1.22)


# --------------------------------------------------- two models over one X
sl, y = content("Two models, one featureset, both fitted to these twelve months",
                "A worked example")

HW = (CW - 0.40) / 2
h = code(sl, ML, y, HW, [
 "multiple linear regression   \u2014  fitted, n = 10",
 "",
 "next_return  =   43.314",
 "               \u2212  9.708 \u00d7 u3_rate",
 "               \u2212  0.105 \u00d7 prev_return",
 "",
 "kind   estimated_coefficients   \u2192  T2",
 "D(Y)   point_estimate",
 "R\u00b2 = 0.082      residual sd = 4.53 %",
], fs=9)
tf = txt(sl, ML, y + h + 0.22, HW, 1.15)
runs(tf, [("An R\u00b2 of 0.08 is a bad model. ", CRIMSON, True),
          ("Ten monthly observations cannot support three parameters, and the "
           "register stores that verdict beside the coefficients rather than "
           "leaving it in a notebook. A platform that only recorded the "
           "coefficients would make this look like a result.", SLATE, False)],
     size=10, first=True, space_after=0, line=1.22)

x = ML + HW + 0.40
h2 = code(sl, x, y, HW, [
 "GARCH(1,1)   \u2014  maximum likelihood, same returns",
 "",
 "\u03c3\u00b2\u209c  =  3.7684",
 "      + 0.320 \u00d7 \u03b5\u00b2\u209c\u208b\u2081",
 "      + 0.400 \u00d7 \u03c3\u00b2\u209c\u208b\u2081",
 "",
 "kind   estimated_coefficients   \u2192  T2",
 "D(Y)   predictive_distribution",
 "log-likelihood \u221231.90   long-run sd = 3.67 %",
], fs=9)
tf = txt(sl, x, y + h2 + 0.22, HW, 1.15)
runs(tf, [("Persistence \u03b1+\u03b2 = 0.72. ", CRIMSON, True),
          ("Low for a monthly series, which is what twelve observations buy "
           "you. Same features, same entity, same grain \u2014 a different "
           "kernel, a different P, and an output that is a distribution rather "
           "than a number.", SLATE, False)],
     size=10, first=True, space_after=0, line=1.22)

note(sl, ML, y + h + 1.48, CW, 1.10,
     "Two warrants, two parameter sets, one featureset version. ",
     "Each fit warrant names macro_core@v1 and its own model version; each "
     "returns a parameter set recording which featureset version produced it. "
     "Nothing about the data was duplicated to serve two models, and neither "
     "model had to know the other existed \u2014 ",
     "which is what a named presentation of X buys.")


# ---------------------------------------------------- extending the set
sl, y = content("Extending the featureset, and what that forces",
                "A worked example")

h = code(sl, ML, y, CW * 0.47, [
 "featureset: macro_plus",
 "composes:   [macro_core]",
 "operations: [{op: add, name: term_spread}]",
 "",
 "\u2192 macro_plus resolves to FOUR slots",
 "  px_close  u3_rate  prev_return  term_spread",
], fs=9)
tf = txt(sl, ML, y + h + 0.20, CW * 0.47, 1.4)
runs(tf, [("Not a new version of macro_core. ", CRIMSON, True),
          ("Adding a slot changes the schema, and the schema is what a kernel "
           "is defined over \u2014 so it is a new featureset composed from the "
           "old, and macro_core@v1 is untouched for whoever is already using "
           "it.", SLATE, False)],
     size=10, first=True, space_after=0, line=1.22)
note(sl, ML, y + h + 1.66, CW * 0.47, 1.28,
     "The refusal is the feature. ",
     "Widening a featureset under a model never defined over it is the failure "
     "all of this exists to make visible, and it lands at the warrant \u2014 ",
     "before anything is fitted, rather than when somebody notices a "
     "coefficient vector has four entries.")

x = ML + CW * 0.51
h3 = code(sl, x, y, CW * 0.49, [
 "POST /api/v1/fit-warrants",
 "  { model: mlr@1.0.0, featureset: macro_plus }",
 "",
 "409 schema_not_satisfied",
 "    'macro_plus' provides term_spread, which this",
 "    version does not declare in its input schema.",
 "    Bind a featureset whose schema covers the",
 "    kernel's inputs, or create a model version",
 "    whose input schema matches this set \u2014 adding",
 "    a regressor is a MODEL change, not a data one.",
], fs=8.5)
tf = txt(sl, x, y + h3 + 0.20, CW * 0.49, 0.42)
para(tf, "So a third model goes over the wider X:", size=10.5, color=INK,
     bold=True, first=True, space_after=0)
data = [["", ""],
        ["what", "gradient-boosted classifier: drawdown next month"],
        ["kind", "learned_weights  \u2014  T3, not T2"],
        ["fit", "train, not estimate"],
        ["D(Y)", "class_probabilities, not a point estimate"],
        ["reads", "macro_plus@v1, all four slots"]]
table(sl, data, x, y + h3 + 0.66, CW * 0.49, col_w=[0.95, 4.75], header=False,
      row_h=0.27, fs=9, bold_col0=True, first_col_color=CRIMSON)

# ------------------------------------------------------- the data, embedded
sl, y = content("The data itself", "A worked example")

tf = txt(sl, ML, y, CW * 0.52, 2.6)
para(tf, "Both files are inside this deck.", size=13, color=CRIMSON, bold=True,
     font=SERIF, first=True, space_after=9)
para(tf, "Double-click either icon and it opens in Excel. They are the data "
         "every number "
         "in this chapter was computed from, carrying their own provenance in "
         "the header \u2014 which series, from where, retrieved when, and "
         "which column means what.",
     size=11, color=INK, space_after=10, line=1.25)
runs(tf, [("Including what is not certain. ", CRIMSON, True),
          ("The unemployment file says plainly that its ingest_ts is the BLS "
           "release CONVENTION computed from the calendar, not a fetched "
           "vintage date. The lag is real and material; the exact day may be a "
           "day or two out, and a file that did not say so would be inviting "
           "somebody to rely on it.", SLATE, False)],
     size=11, space_after=10, line=1.25)
para(tf, "A deck that quotes figures nobody can check is a deck that has to be "
         "believed. These can be checked.",
     size=11, color=INK, bold=True, space_after=0, line=1.25)

x = ML + CW * 0.56
HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "..", "docs", "examples")

# Embedded as WORKBOOKS, not as OLE packages. An OLE package must be wrapped in
# a compound document, and handing PowerPoint raw bytes under that prog id
# produces an icon that opens nothing -- which is what the first attempt did.
# A .xlsx is a known type and opens on a double-click with no wrapper at all.
import xlsx as _xlsx
from pptx.enum.shapes import PROG_ID

files = [("sp500_daily", "S&P 500, daily close", "S&P 500 daily",
          "FRED series SP500  \u00b7  258 rows  \u00b7  Sep 2025 \u2013 Sep 2026"),
         ("us_unemployment_monthly", "US unemployment rate (U-3)",
          "US unemployment",
          "FRED series UNRATE  \u00b7  12 months  \u00b7  one of them empty")]
yy = y + 0.06
for stem, title, sheet, detail in files:
    source = os.path.join(DATA, stem + ".csv")
    book = os.path.join(DATA, stem + ".xlsx")
    rect(sl, x, yy, CW * 0.44, 1.34, fill=PARCH, line=RULE)
    rect(sl, x, yy, CW * 0.44, 0.05, fill=CRIMSON)
    if os.path.exists(source):
        _xlsx.from_csv(source, book, sheet)
        sl.shapes.add_ole_object(
            book, PROG_ID.XLSX, In(x + 0.20), In(yy + 0.26),
            width=In(0.62), height=In(0.62))
    tf = txt(sl, x + 0.96, yy + 0.22, CW * 0.44 - 1.18, 0.94)
    para(tf, title, size=11.5, color=INK, bold=True, font=SERIF, first=True,
         space_after=3)
    para(tf, detail, size=9, color=SLATE, space_after=3, line=1.18)
    para(tf, stem + ".xlsx", size=8.5, color=CRIMSON, space_after=0)
    yy += 1.52

note(sl, ML, y + 3.22, CW, 0.86,
     "They also ship in the repository, at docs/examples/, as CSV. ",
     "The deck is regenerated from source rather than edited as a binary, so "
     "the figures and the files cannot drift apart \u2014 ",
     "the generator reads these same two CSVs.")


# ------------------------------------------- end of the engineering part
sl = blank()
rect(sl, 0, 0, SW, SH, fill=CRIMSON)
rect(sl, 0, 0, 0.20, SH, fill=CRIMSON_D)
rect(sl, ML + 0.4, 1.10, 1.7, 0.035, fill=RGBColor(0xE8, 0xB8, 0xC0))
tf = txt(sl, ML + 0.4, 1.40, CW * 0.80, 2.6)
para(tf, "One idea, applied everywhere", size=34, color=WHITE, font=SERIF,
     first=True, space_after=14)
para(tf, "A pin is to a version, never to a name. A clock records when something "
         "became knowable, not when it was written down. A refusal says what to "
         "do instead. And what the platform will not do is written down beside "
         "what it will.",
     size=15, color=RGBColor(0xF4, 0xDF, 0xE3), italic=True, space_after=0,
     line=1.32)
tf = txt(sl, ML + 0.4, 4.22, CW * 0.74, 2.10)
para(tf, "Ashutosh Sinha", size=18, color=WHITE, bold=True, first=True,
     space_after=4)
para(tf, "Independent Researcher   \u00b7   ajsinha@gmail.com", size=12,
     color=RGBColor(0xF2, 0xD8, 0xDC), space_after=14)
para(tf, "Featuresets and parameters: docs/15-featuresets-and-parameters.md   "
         "\u00b7   Composition and retrieval: docs/16-features-composed-and-shaped.md   "
         "\u00b7   Feature platform: docs/07-feature-platform.md",
     size=10.5, color=RGBColor(0xE8, 0xC4, 0xCA), line=1.3)
para(tf, "\u00a9 2026 Ashutosh Sinha. All rights reserved. Proprietary and "
         "confidential \u2014 see LICENSE and NOTICE. Not legal, regulatory or "
         "financial advice.",
     size=8.5, color=RGBColor(0xD8, 0xA0, 0xAC), space_before=10, line=1.25)
