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
     size=11, color=RGBColor(0xE8,0xB8,0xC0), bold=True, first=True, space_after=0)
tf = txt(sl, ML + 0.3, 1.62, CW * 0.88, 2.0)
para(tf, "Detailed System Design", size=44, color=WHITE, font=SERIF, first=True, space_after=4)
rect(sl, ML + 0.3, 3.28, 1.7, 0.035, fill=RGBColor(0xE8,0xB8,0xC0))
tf = txt(sl, ML + 0.3, 3.54, CW * 0.82, 0.8)
para(tf, "Component interfaces, algorithms, transaction boundaries, error semantics and operations — the level below the architecture",
     size=14, color=RGBColor(0xF4,0xDF,0xE3), italic=True, first=True, space_after=0, line=1.25)
tf = txt(sl, ML + 0.3, 4.90, CW * 0.55, 1.0)
para(tf, "Ashutosh Sinha", size=20, color=INK, bold=True, font=SERIF, first=True, space_after=3)
para(tf, "Independent Researcher", size=12, color=CRIMSON, space_after=1)
para(tf, "September 2026   ·   written to be sufficient to start coding from", size=10.5, color=MUTED)
x0 = ML + CW * 0.55
tf = txt(sl, x0, 4.82, CW * 0.45, 2.25)
para(tf, "CHAPTERS", size=9.5, color=CRIMSON, bold=True, first=True, space_after=6)
for i, c in enumerate(["Overview and design rules", "Core domain and registry",
                       "Governance subsystems", "Data and features",
                       "Execution and warrants", "Machine assistance",
                       "Interfaces", "Cross-cutting and operations"], 1):
    runs(tf, [(f"{i}   ", CRIMSON, True), (c, SLATE, False)], size=10.5, space_after=3)
