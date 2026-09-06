# ============================================================ CH 11
_state["chapter"] = "11 · What a featureset is"

# ----------------------------------------------------- schema vs constituents
sl, y = content("A featureset declares a schema; a version fills it",
                "Composing a featureset")
# The columns are LABELLED, and the label is the whole example: a slot is not
# a kind of feature, it is a name a feature is bound into, at a pinned view
# version. The version pin is the property the right-hand table argues for, so
# it has to be visible here rather than asserted next to an example without it.
h = code(sl, ML, y, CW * 0.56, [
 "featureset: inflation",
 "schema:  gb_index   us_index   daily_index      all numeric",
 "",
 "       slot          \u2192  feature         @ view_version",
 "@v1    gb_index      \u2192  UKRPI           @ 2025-02",
 "       us_index      \u2192  USCPI           @ 2025-02",
 "       daily_index   \u2192  RPI_DAILY_MKT   @ 2025-02",
 "@v2    gb_index      \u2192  UKRPI           @ 2025-06",
 "       us_index      \u2192  USCPI           @ 2025-06",
 "       daily_index   \u2192  RPI_DAILY_DMO   @ 2025-06",
], fs=9.5)
tf = txt(sl, ML, y + h + 0.26, CW * 0.56, 2.2)
runs(tf, [("Like for like. ", CRIMSON, True),
          ("@v2 binds daily_index to a different daily RPI reference \u2014 the "
           "same signal at the same frequency for the same entity, published by "
           "somebody else. A model defined over inflation does not change: it "
           "reads daily_index, and always did.", INK, False)],
     size=11, first=True, space_after=9, line=1.25)
para(tf, "A version that cannot fill the schema is refused: it is a different "
         "featureset, or it is a model change, and the register decides which. "
         "Rolling forward mints a version re-resolved to the newest view "
         "versions, with a diff naming every slot that moved.",
     size=11, color=SLATE, space_after=0, line=1.25)

x = ML + CW * 0.60
tf = txt(sl, x, y, CW * 0.40, 0.32)
para(tf, "Every binding \u2014 what fills a slot, and from where "
         "\u2014 pins exactly", size=12.5, color=CRIMSON, bold=True,
     font=SERIF, first=True, space_after=0)
data = [["", ""],
        ["feature", "which signal fills the slot"],
        ["view", "which view supplies its values"],
        ["view_version", "which version of that view"],
        ["delta_version", "which write to that path"],
        ["namespace", "the resolved location in storage"]]
th = table(sl, data, x, y + 0.40, CW * 0.40, col_w=[1.5, 3.4], header=False,
           row_h=0.29, fs=9.5, bold_col0=True, first_col_color=CRIMSON)
note(sl, x, y + 0.40 + th + 0.18, CW * 0.40, 1.34,
     "A path is mutable. ",
     "A set naming views without pinning them would resolve to different "
     "bytes next month, with its digest \u2014 the hash that names its "
     "contents \u2014 unchanged: ",
     "a stable name over moving contents.")

# --------------------------------------------- worked example: a feature
sl, y = content("Inheriting a feature: a curve with a tenor added",
                "Composing a featureset")

CW3 = (CW - 1.30) / 3
GAPX = 0.65

h1 = listbox(sl, ML, y, CW3, "usd_curve", [
    ("1m", INK, ""), ("3m", INK, ""), ("1y", INK, ""),
    ("5y", INK, ""), ("10y", INK, "")],
    sub="the parent \u2014 sealed, so it cannot move", accent=SLATE,
    fill=PARCH)

x2 = ML + CW3 + GAPX
OPS_H = h1 + 0.24
rect(sl, x2, y, CW3, OPS_H, fill=WHITE, line=RULE)
rect(sl, x2, y, CW3, 0.05, fill=CRIMSON)
tf = txt(sl, x2 + 0.14, y + 0.13, CW3 - 0.28, 0.26)
para(tf, "its own operations", size=11, color=INK, bold=True, font=SERIF,
     first=True, space_after=0)
tf = txt(sl, x2 + 0.14, y + 0.40, CW3 - 0.28, 0.20)
para(tf, "applied last, so they beat everything above", size=7.8, color=SLATE,
     italic=True, first=True, space_after=0)
yy = y + 0.68
for op, target, why in [("add", "30y", "the curve goes further out"),
                        ("drop", "1m", "no longer quoted"),
                        ("override", "3m", "an OIS-based fixing")]:
    tf = txt(sl, x2 + 0.14, yy, CW3 - 0.28, 0.38)
    runs(tf, [(f"{op}  ", CRIMSON, True), (target, INK, True)],
         size=9.5, first=True, space_after=1)
    para(tf, why, size=7.6, color=SLATE, space_after=0)
    yy += 0.40

x3 = x2 + CW3 + GAPX
listbox(sl, x3, y, CW3, "usd_curve_plus", [
    ("3m", INK, "overridden here"), ("1y", SLATE, ""), ("5y", SLATE, ""),
    ("10y", SLATE, ""), ("30y", INK, "added here")],
    sub="1m is gone; the shape follows the components", accent=CRIMSON)

# the arrows between the three columns
down(sl, ML + CW3 + 0.20, y + h1 * 0.42, 0.24, CRIMSON, w=0.24)
down(sl, x2 + CW3 + 0.20, y + h1 * 0.42, 0.24, CRIMSON, w=0.24)

note(sl, ML, y + h1 + 0.28, CW, 0.92,
     "Ask the platform, not the row. ",
     "GET /features/usd_curve_plus/resolved returns the components above AND "
     "where each came from \u2014 3m says it overrode usd_curve. ",
     "The row stores what this feature declares; resolving it is MAYA\u2019s job.")

DY = y + h1 + 1.36
rect(sl, ML, DY, CW, 1.10, fill=PARCH)
rect(sl, ML, DY, 0.05, 1.10, fill=CRIMSON)
tf = txt(sl, ML + 0.26, DY + 0.13, CW - 0.5, 0.88)
para(tf, "And if a parent is amended anyway?", size=11.5, color=CRIMSON,
     bold=True, font=SERIF, first=True, space_after=5)
runs(tf, [("The child says so. ", INK, True),
          ("A composition records the parent\u2019s definition version at the "
           "moment it resolved, so a parent that has moved since shows up as "
           "drift on every child that reads it \u2014 ", INK, False),
          ("composed against v1, now at v3.", CRIMSON, True),
          ("  Not a failed read: a child whose parent has moved is something to "
           "be told about, not something that should stop working.",
           SLATE, False)],
     size=9.8, space_after=0, line=1.22)

tf = txt(sl, ML, DY + 1.24, CW, 0.34)
runs(tf, [("A sealed parent cannot drift ", CRIMSON, True),
          ("\u2014 the amendment that would move it is refused, so sealing "
           "turns a promise about stability into a property of the object.",
           SLATE, False)],
     size=10, first=True, space_after=0, line=1.22)


# ------------------------------------------ worked example: two featuresets
sl, y = content("Combining two featuresets: the rightmost wins",
                "Composing a featureset")

PW = (CW - 0.60) / 2
hA = listbox(sl, ML, y, PW, "retail_core", [
    ("dscr", INK, ""), ("turnover", INK, ""), ("months_on_book", INK, "")],
    sub="first parent \u2014 least prominent", accent=SLATE, fill=PARCH)
listbox(sl, ML + PW + 0.60, y, PW, "sme_core", [
    ("turnover", INK, "3-year average"), ("sector", INK, ""),
    ("directors", INK, "")],
    sub="second parent \u2014 wins any clash", accent=CRIMSON, fill=PARCH)

MID = y + hA + 0.26
rect(sl, ML, MID, CW, 0.40, fill=CRIMSON)
tf = txt(sl, ML + 0.20, MID + 0.08, CW - 0.4, 0.26)
runs(tf, [("compose: [retail_core, sme_core]", WHITE, True),
          ("     folded left to right, later wins     ", RGBColor(0xF4,0xDF,0xE3), False),
          ("then this set\u2019s own operations, last of all",
           RGBColor(0xF4,0xDF,0xE3), False)],
     size=10, first=True, space_after=0)

RES = MID + 0.62
listbox(sl, ML, RES, PW, "sme_retail", [
    ("dscr", SLATE, "from retail_core"),
    ("turnover", INK, "from sme_core \u2014 it overrode retail\u2019s"),
    ("months_on_book", SLATE, "from retail_core"),
    ("sector", SLATE, "from sme_core"),
    ("directors", SLATE, "from sme_core"),
    ("guarantee_cover", INK, "added by this set")],
    sub="what a kernel defined over it actually reads", accent=CRIMSON)

x = ML + PW + 0.60
tf = txt(sl, x, RES, PW, 2.4)
para(tf, "Only one slot clashed", size=12, color=CRIMSON, bold=True,
     font=SERIF, first=True, space_after=8)
para(tf, "Both parents declare turnover. sme_core is named second, so its "
         "3-year average is what the set holds \u2014 and the resolved set "
         "SAYS SO, slot by slot.",
     size=10, color=INK, space_after=10, line=1.24)
para(tf, "If a parent could beat a child, naming a parent would be an act of "
         "surrender; if order did not matter, \u2018combine these two\u2019 "
         "would be ambiguous whenever they disagreed.",
     size=10, color=SLATE, space_after=8, line=1.24)
runs(tf, [("A child inherits the parents\u2019 retrieval policy the same way",
           CRIMSON, True),
          (" \u2014 one fold, applied to slots, to components and to policy.",
           SLATE, False)],
     size=10, space_after=8, line=1.24)
# The resolved schema is what a fit is checked against. Saying it plainly is
# only possible since `FeatureSets.schema` stopped reading the set's own row:
# a set that inherits every slot reported an EMPTY schema and so satisfied no
# kernel at all, which made the ordinary case the one that could not be fitted.
runs(tf, [("A composed set satisfies a kernel exactly as a declared one does",
           CRIMSON, True),
          (" \u2014 the schema L-W10 checks is the RESOLVED one, the same slots "
           "the data fills. Inheriting every slot is the ordinary case, not an "
           "exotic one.", SLATE, False)],
     size=10, space_after=8, line=1.24)
runs(tf, [("Two compositions are refused outright:", CRIMSON, True),
          (" a cycle, which has no fixed point to resolve to; and an ephemeral "
           "parent, which resolves today and dangles tomorrow.", SLATE, False)],
     size=10, space_after=0, line=1.24)


# ------------------------------------------------------------- retrieval
sl, y = content("What MAYA does to values on the way out",
                "Composing a featureset")
steps(sl, ML, y, CW, [
    ("1", "Align", "onto a chosen axis, filling gaps by a stated rule"),
    ("2", "Fit", "statistics from what was knowable at the as_of \u2014 on "
                 "OBSERVED values, before anything is filled"),
    ("3", "Fill", "the gaps, reporting how much of each column was invented"),
    ("4", "Normalise", "everything, including what was filled, and return the "
                       "statistics with the data"),
], h=1.42)
tf = txt(sl, ML, y + 1.62, CW * 0.52, 1.6)
para(tf, "The order is the point.", size=12, color=CRIMSON, bold=True,
     font=SERIF, first=True, space_after=6)
para(tf, "Fitting the normalisation AFTER filling would shrink the spread by "
         "exactly the amount that was invented, because every filled cell sits "
         "at the centre and pulls the variance down.",
     size=11, color=INK, space_after=0, line=1.25)
x = ML + CW * 0.56
tf = txt(sl, x, y + 1.62, CW * 0.44, 1.6)
para(tf, "And the as_of is not optional.", size=12, color=CRIMSON, bold=True,
     font=SERIF, first=True, space_after=6)
para(tf, "A z-score fitted over the whole column encodes what the mean turned "
         "out to be, including the part that had not happened when the row was "
         "scored. The leaky answer is the one somebody would get by accident, "
         "so it is the one that must not be the default.",
     size=11, color=INK, space_after=0, line=1.25)
note(sl, ML, y + 3.42, CW, 0.92,
     "Attached as default behaviour, overridden by the request. ",
     "Parents, then the object, then the caller \u2014 the same left-to-right "
     "fold, merged column by column, so a parent that fills three columns and a "
     "child that normalises one ",
     "end up doing both.")
