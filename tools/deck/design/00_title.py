# ============================================================ TITLE
_state["n"] = 0
sl = blank()
rect(sl, 0, 0, SW, SH, fill=WHITE)
rect(sl, 0, 0, SW, 4.35, fill=CRIMSON)
rect(sl, 0, 4.35, SW, 0.06, fill=GOLD)
rect(sl, 0, 0, 0.20, 4.35, fill=CRIMSON_D)
LOGO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..",
                    "assets", "logo", "maya-mark-white.png")
if os.path.exists(LOGO):
    sl.shapes.add_picture(LOGO, In(ML + 0.30), In(0.70), In(0.80), In(0.80))
tf = txt(sl, ML + 1.24, 0.99, CW - 1.04, 0.34)
para(tf, "MAYA  ·  MODEL & AI LIFECYCLE ASSURANCE PLATFORM",
     size=11, color=RGBColor(0xE8, 0xB8, 0xC0), bold=True, first=True,
     space_after=0)
tf = txt(sl, ML + 0.3, 1.52, CW * 0.86, 2.2)
para(tf, "Model and Feature Management", size=38, color=WHITE, font=SERIF,
     first=True, space_after=2)
para(tf, "Concepts and System Design", size=38, color=WHITE, font=SERIF,
     space_after=4)
rect(sl, ML + 0.3, 3.32, 1.7, 0.035, fill=RGBColor(0xE8, 0xB8, 0xC0))
tf = txt(sl, ML + 0.3, 3.56, CW * 0.84, 0.8)
para(tf, "The philosophy, the foundations, the concepts a practitioner works "
         "with, the design of the system that holds them — and worked examples "
         "throughout",
     size=13.5, color=RGBColor(0xF4, 0xDF, 0xE3), italic=True, first=True,
     space_after=0, line=1.25)
tf = txt(sl, ML + 0.3, 4.86, CW * 0.50, 1.2)
para(tf, "Ashutosh Sinha", size=20, color=INK, bold=True, font=SERIF,
     first=True, space_after=3)
para(tf, "Independent Researcher", size=12, color=CRIMSON, space_after=1)
para(tf, "September 2026", size=10.5, color=MUTED)

x0 = ML + CW * 0.50
tf = txt(sl, x0, 4.72, CW * 0.50, 2.4)
para(tf, "IN FIVE PARTS", size=9.5, color=CRIMSON, bold=True, first=True,
     space_after=6)
for numeral, name, detail in [
    ("I", "Philosophy", "what a model is, and what goes wrong when you forget"),
    ("II", "Foundations", "the mathematics, run as tests rather than claimed"),
    ("III", "Concepts", "the objects a practitioner works with"),
    ("IV", "System design", "components, algorithms, boundaries"),
    ("V", "Worked examples", "eight kinds of model, then real data"),
]:
    runs(tf, [(f"{numeral:<4}", CRIMSON, True), (f"{name}  ", INK, True),
              (detail, SLATE, False)], size=10, space_after=4)
