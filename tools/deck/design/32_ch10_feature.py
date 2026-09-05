# ============================================================ CH 10
divider("10", "What a Feature Is",
        "Five things it is not, and what each one costs when you assume otherwise.",
        ["Not always a number",
         "Derived features",
         "The leakage rules",
         "Sealing and ownership"])

# ------------------------------------------------------------ dimensionality
sl, y = content("A feature is not always a number", "Engineering a feature")
h = code(sl, ML, y, CW * 0.52, [
 '{"name": "usd_curve", "entity": "book_id",',
 ' "dtype": "numeric",',
 ' "shape": [10],',
 ' "components": ["1m","3m","6m","1y","2y",',
 '                "3y","5y","7y","10y","30y"]}',
], fs=9.5)
data = [["Shape", "Kind", "Example"],
        ["[]", "scalar", "debt service coverage"],
        ["[10]", "vector", "a curve at ten tenors"],
        ["[10, 10]", "matrix", "the correlation between them"],
        ["[5, 10, 10]", "tensor", "that matrix under five scenarios"]]
table(sl, data, ML, y + h + 0.28, CW * 0.52, col_w=[1.3, 1.2, 4.4],
      row_h=0.30, fs=9.5, hfs=9.5, bold_col0=True, first_col_color=CRIMSON)

x = ML + CW * 0.56
tf = txt(sl, x, y, CW * 0.44, 3.4)
para(tf, "The component order IS the axis order", size=12.5, color=CRIMSON,
     bold=True, font=SERIF, first=True, space_after=8)
para(tf, "A curve whose tenors came back alphabetically would be a different "
         "curve \u2014 and one nobody would notice was wrong. Resolution "
         "preserves insertion order and never sorts.",
     size=11, color=INK, space_after=10, line=1.25)
para(tf, "The names are what make composition mean something. \u201cDrop the "
         "50-year point\u201d is an operation on a name; on an anonymous array "
         "it is an operation on an index, and an index is not a meaning.",
     size=11, color=SLATE, space_after=10, line=1.25)
para(tf, "A declared shape is checked against the values that arrive. A shape "
         "nobody verifies is a comment, and a model given ten tenors where it "
         "expected eleven produces an answer rather than an error.",
     size=11, color=SLATE, space_after=0, line=1.25)

# ---------------------------------------------------------- derived features
sl, y = content("Derived features, and the four rules", "Engineering a feature")
h = code(sl, ML, y, CW * 0.50, [
 "lot_to_living_ratio = lot_size_sqft / living_area_sqft",
 "property_age        = year(event_ts) - year_built",
 "log_living_area     = log(living_area_sqft)",
 "",
 "# arithmetic, comparison, nine total functions,",
 "# the row's own clock. whitelisted at the AST,",
 "# so what cannot be expressed cannot be smuggled in.",
], fs=9)
note(sl, ML, y + h + 0.26, CW * 0.50, 1.14,
     "MAYA transforms features it holds; ",
     "it does not run models. Computing x / y over a stored column is the same "
     "class of act as the null rate it already reports for every "
     "materialisation. ",
     "Running a kernel is not.")

x = ML + CW * 0.54
tf = txt(sl, x, y, CW * 0.46, 0.32)
para(tf, "Four rules, each because the alternative fails quietly", size=12,
     color=CRIMSON, bold=True, font=SERIF, first=True, space_after=0)
data = [["Rule", "What it prevents"],
        ["Lineage is the transitive closure",
         "a primitive retired under something deriving from it"],
        ["ingest_ts(Z) = max(inputs)",
         "the easiest way to leak the future: a value appearing knowable "
         "before its inputs were"],
        ["No slot may derive from the label",
         "leakage with a division sign in front of it"],
        ["Certification is the meet",
         "deriving from an uncertified feature to launder it"]]
table(sl, data, x, y + 0.40, CW * 0.46, col_w=[2.3, 3.1], row_h=0.30, fs=9,
      hfs=9, bold_col0=True, first_col_color=CRIMSON)

# ------------------------------------------------------------------ leakage
sl, y = content("The one that gets refused", "Engineering a feature")
h = code(sl, ML, y, CW * 0.54, [
 "feature: price_per_sqft",
 "inputs:  [sale_price, living_area_sqft]",
 "         # sale_price is the featureset's LABEL",
 "",
 "409  'price_per_sqft' is computed from 'sale_price',",
 "     which this featureset declares as its label \u2014 a",
 "     feature derived from the label leaks the answer",
 "     into the training set.",
], fs=9)
tf = txt(sl, ML, y + h + 0.28, CW * 0.54, 1.5)
para(tf, "The check walks the WHOLE lineage, not the immediate inputs: a "
         "derivation of a derivation of the label is still the label.",
     size=11, color=INK, first=True, space_after=8, line=1.25)
para(tf, "And it runs before the view is resolved, so the message is "
         "\u201cyou cannot train on the answer\u201d rather than "
         "\u201cno view supplies that\u201d.",
     size=11, color=SLATE, space_after=0, line=1.25)

x = ML + CW * 0.58
tf = txt(sl, x, y, CW * 0.42, 3.6)
para(tf, "Why this one matters more than it looks", size=12.5, color=CRIMSON,
     bold=True, font=SERIF, first=True, space_after=8)
para(tf, "A model trained on a feature derived from its own label performs "
         "extraordinarily in validation and fails on the first case it has not "
         "already seen.",
     size=11, color=INK, space_after=10, line=1.25)
para(tf, "It is not caught by any metric, because every metric agrees the model "
         "is excellent. It is caught by knowing what the column was made from "
         "\u2014 which is why the lineage is recorded rather than inferred.",
     size=11, color=SLATE, space_after=10, line=1.25)
para(tf, "The same argument produces the ingest-clock rule, the point-in-time "
         "assembly rule, and the refusal to normalise without an as_of. They "
         "are one idea applied four times.",
     size=11, color=SLATE, space_after=0, line=1.25)

# --------------------------------------------------- sealing and ownership
sl, y = content("Sealed, ephemeral, owned", "Engineering a feature")
card(sl, ML, y, CW * 0.315, 2.5, "1", "Sealed",
     "Final: no amendment, no further versions, no change of owner \u2014 and "
     "still composable. That combination is the point. A parent that cannot "
     "move is a parent worth building on, and evolution moves to a child where "
     "it stays visible.")
card(sl, ML + CW * 0.343, y, CW * 0.315, 2.5, "2", "Ephemeral",
     "A time to live, then destroyed. Cannot be sealed \u2014 permanent and "
     "temporary are not two flags that happen to be set. Cannot be composed "
     "from: a child that resolves today and dangles tomorrow. Its rows go; its "
     "evidence stays.")
card(sl, ML + CW * 0.686, y, CW * 0.314, 2.5, "3", "Owned",
     "Two facts kept apart. The CREATOR is history and never moves. The OWNER "
     "is a responsibility, transferred by name with the handover witnessed. An "
     "owner field that quietly becomes a leaver's username is how a model ends "
     "up accountable to nobody.")
note(sl, ML, y + 2.72, CW, 0.92,
     "Sealing is its own permission. ",
     "Whoever may define a thing is not automatically who may end it, so it "
     "sits with the second line. Breaking a seal is administrators-only and "
     "needs a reason \u2014 ",
     "a seal anybody could lift would not be a seal.")
