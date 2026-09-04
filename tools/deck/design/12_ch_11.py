# ============================================================ CH 11
divider("11", "Composing a Featureset",
        "A schema, versions that fill it, and one fold that does both.",
        ["Schema and constituents", "The composition monoid",
         "Rolling forward", "Retrieval policy"])

# ----------------------------------------------------- schema vs constituents
sl, y = content("A featureset declares a schema; a version fills it",
                "Composing a featureset")
h = code(sl, ML, y, CW * 0.56, [
 "featureset: inflation",
 "schema:  gb_index: numeric",
 "         us_index: numeric",
 "         daily_index: numeric",
 "",
 "@v1   gb_index\u2192UKRPI  us_index\u2192USCPI  daily\u2192DAILY_INFL",
 "@v2   gb_index\u2192UKRPI  us_index\u2192USCPI  daily\u2192EUHICP",
], fs=9.5)
tf = txt(sl, ML, y + h + 0.28, CW * 0.56, 1.8)
para(tf, "@v2 draws on a different feature entirely, and a model defined over "
         "inflation does not change: it reads daily_index, and always did.",
     size=11.5, color=INK, first=True, space_after=9, line=1.25)
para(tf, "A version that CANNOT fill the schema is refused. It is not a version "
         "of this featureset \u2014 it is a different one, or it is a model "
         "change, and the register decides which so nobody has to remember.",
     size=11, color=SLATE, space_after=0, line=1.25)

x = ML + CW * 0.60
tf = txt(sl, x, y, CW * 0.40, 0.32)
para(tf, "Every binding pins exactly", size=12.5, color=CRIMSON, bold=True,
     font=SERIF, first=True, space_after=0)
data = [["", ""],
        ["feature", "which signal fills the slot"],
        ["view", "which view supplies its values"],
        ["view_version", "which version of that view"],
        ["delta_version", "which write to that path"],
        ["namespace", "the resolved Delta location"]]
th = table(sl, data, x, y + 0.40, CW * 0.40, col_w=[1.5, 3.4], header=False,
           row_h=0.29, fs=9.5, bold_col0=True, first_col_color=CRIMSON)
note(sl, x, y + 0.40 + th + 0.18, CW * 0.40, 1.30,
     "A path is mutable. ",
     "A set that named views without pinning them would resolve to different "
     "bytes next month with its digest unchanged \u2014 which is adversarial "
     "finding C-2, ",
     "one level out from the view.")

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

tf = txt(sl, ML, y + h1 + 1.32, CW, 0.44)
runs(tf, [("The parent is sealed, and that is the point. ", CRIMSON, True),
          ("A sealed feature takes no amendment and can still be composed from, "
           "so a parent that cannot move is a parent worth building on \u2014 "
           "and the change lives in the child, where a reviewer sees it.",
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
para(tf, "That is the only rule there is. If a parent could beat a child, "
         "naming a parent would be an act of surrender; if the order did not "
         "matter, \u2018combine these two\u2019 would be ambiguous whenever "
         "they disagreed.",
     size=10, color=SLATE, space_after=10, line=1.24)
runs(tf, [("A child inherits the parents\u2019 retrieval policy the same way",
           CRIMSON, True),
          (" \u2014 one fold, applied to slots, to components and to policy.",
           SLATE, False)],
     size=10, space_after=0, line=1.24)


# ------------------------------------------ modifying something with children
sl, y = content("Modifying something other things are built on",
                "Composing a featureset")

BW4 = (CW - 3 * 0.22) / 4
for i, (num, title, body) in enumerate([
    ("1", "Amend it",
     "Changes the definition and advances its version. Allowed while the "
     "feature is open, and every child records which version it composed "
     "against."),
    ("2", "Seal it",
     "No amendment, no further versions, no change of owner \u2014 and still "
     "composable. A parent that cannot move is a parent worth building on."),
    ("3", "Compose a child",
     "The way to change a sealed thing. The change lives where a reviewer sees "
     "it, beside the parent it departs from."),
    ("4", "Roll forward",
     "For a featureset: mint a version re-resolved to the newest view "
     "versions, with a diff naming every slot that moved."),
]):
    xx = ML + i * (BW4 + 0.22)
    card(sl, xx, y, BW4, 2.15, num, title, body)

DY = y + 2.38
rect(sl, ML, DY, CW, 1.02, fill=PARCH)
rect(sl, ML, DY, 0.05, 1.02, fill=CRIMSON)
tf = txt(sl, ML + 0.26, DY + 0.13, CW - 0.5, 0.80)
para(tf, "And if a parent is amended anyway?", size=11.5, color=CRIMSON,
     bold=True, font=SERIF, first=True, space_after=5)
runs(tf, [("The child says so. ", INK, True),
          ("A composition records the parent\u2019s definition version at the "
           "moment it resolved, so a parent that has moved since shows up as "
           "drift on every child that reads it \u2014 ",
           INK, False),
          ("composed against v1, now at v3.", CRIMSON, True),
          ("  Not a failed read: a child whose parent has moved is something to "
           "be told about, not something that should stop working. But it is "
           "never silent, because a stable name over moving contents is the "
           "failure this platform was built around.", SLATE, False)],
     size=9.8, space_after=0, line=1.22)

tf = txt(sl, ML, DY + 1.20, CW, 0.40)
runs(tf, [("Which is why sealing and composing are the same idea from two "
           "sides. ", CRIMSON, True),
          ("A sealed parent cannot drift, because the amendment that would "
           "move it is refused \u2014 so sealing turns a promise about "
           "stability into a property of the object.", SLATE, False)],
     size=10, first=True, space_after=0, line=1.22)


# ------------------------------------------------------------ the monoid
sl, y = content("Composition: one fold, two objects", "Composing a featureset")
h = code(sl, ML, y, CW * 0.54, [
 "compose([a, b, c])  =  merge(merge(a, b), c)",
 "                       then the object's OWN operations",
 "",
 "merge is associative;  {} is its identity",
 "  \u21d2 composition is a MONOID",
 "  \u21d2 'a combination of features is a feature'",
 "     is a statement, not an aspiration",
], fs=9.5)
tf = txt(sl, ML, y + h + 0.26, CW * 0.54, 1.5)
para(tf, "Left to right, the rightmost wins, and an object\u2019s own "
         "operations are applied last \u2014 because if a parent could "
         "override a child, naming a parent would be an act of surrender.",
     size=11, color=INK, first=True, space_after=8, line=1.25)
para(tf, "Inheriting from one parent and combining several are the same "
         "operation at different arities, so there is one mechanism and "
         "inheritance is the one-parent case.",
     size=11, color=SLATE, space_after=0, line=1.25)

x = ML + CW * 0.58
tf = txt(sl, x, y, CW * 0.42, 0.32)
para(tf, "Every operation is total", size=12.5, color=CRIMSON, bold=True,
     font=SERIF, first=True, space_after=0)
data = [["Refused", "Because"],
        ["drop of something absent",
         "a drop that quietly does nothing leaves a child differing from what "
         "its author wrote"],
        ["add of something present",
         "say override \u2014 the two read differently to a reviewer and should"],
        ["override of something absent", "say add"],
        ["a cycle", "there is no fixed point to resolve to"],
        ["an ephemeral parent", "it resolves today and dangles tomorrow"]]
table(sl, data, x, y + 0.40, CW * 0.42, col_w=[2.0, 3.5], row_h=0.29, fs=9,
      hfs=9, bold_col0=True, first_col_color=CRIMSON)

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

# --------------------------------------------------------------- alignment
sl, y = content("Aligning onto an axis, and the leakage that cannot hide",
                "Composing a featureset")
data = [["Rule", "Fills from", "Safe for training"],
        ["flat_forward", "the last observation", "yes"],
        ["flat_backward", "the next observation", "no"],
        ["linear", "both neighbours", "no"],
        ["nearest", "whichever is closer", "no"]]
h = table(sl, data, ML, y, CW * 0.50, col_w=[1.6, 2.9, 2.2], row_h=0.30,
          fs=10, hfs=10, bold_col0=True, first_col_color=CRIMSON)
tf = txt(sl, ML, y + h + 0.26, CW * 0.50, 1.8)
para(tf, "The last three reach into the future. They are right for drawing a "
         "curve or for an explicitly retrospective backtest, and wrong for "
         "training.",
     size=11, color=INK, first=True, space_after=8, line=1.25)
para(tf, "They are not refused. They are stamped honestly.",
     size=11.5, color=CRIMSON, bold=True, space_after=0, line=1.25)

x = ML + CW * 0.54
h2 = code(sl, x, y, CW * 0.46, [
 "grid  t=0   100.0   ingest_ts 0.0",
 "grid  t=1   400.0   ingest_ts 3.0   \u2190 filled from t=3",
 "grid  t=2   400.0   ingest_ts 3.0",
 "grid  t=3   400.0   ingest_ts 3.0",
 "",
 "# a point-in-time read at as_of = 1",
 "# excludes rows 2 and 3 by the ORDINARY rule",
], fs=9)
tf = txt(sl, x, y + h2 + 0.26, CW * 0.46, 1.6)
para(tf, "A value derived from a later observation inherits that "
         "observation\u2019s ingest clock, because that is genuinely when it "
         "became knowable.",
     size=11, color=INK, first=True, space_after=8, line=1.25)
para(tf, "The leakage is not caught by a check. It is made arithmetically "
         "impossible to hide, by the bitemporal machinery already here.",
     size=11, color=SLATE, space_after=0, line=1.25)
