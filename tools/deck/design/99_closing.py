# ============================================================ CLOSING
_state["chapter"] = "Closing"
sl, y = content("What this design commits to", "Closing")
outs = [("Immutability is enforced, not asserted",
         "Triggers that raise, append-only database roles, a chain anchored outside the system. Silence is never an acceptable enforcement mechanism."),
        ("Every derived value carries its derivation",
         "Tier, status, scope, health — each written with its inputs, rule version and rationale, in the same transaction."),
        ("Extension without migration",
         "Model classes are fibres, regulators are institutions. Nine plugin points. A new kind of model needs no DDL and no front-end release."),
        ("Governance is not a single point of failure",
         "If the control plane is down, authorised scoring continues. Only new issuance and changes stop."),
        ("The compliant path is the fast path",
         "SDK-first, schema-generated forms, compiled documentation. If governance is slower than the workaround, the inventory rots."),
        ("The theory is tested",
         "Seventeen laws run today and a failing one fails the build. The remaining twelve are stated and marked as not yet executable — because a document claiming all of them run is the decay it was written to prevent.")]
cw2 = (CW - 0.30 * 2) / 3
for i, (t, d) in enumerate(outs):
    card(sl, ML + (i % 3) * (cw2 + 0.30), y + (i // 3) * 2.30, cw2, 2.10, f"0{i+1}", t, d)

_state["n"] += 1
sl = blank()
rect(sl, 0, 0, SW, SH, fill=CRIMSON)
rect(sl, 0, 0, 0.20, SH, fill=CRIMSON_D)
if os.path.exists(LOGO):
    sl.shapes.add_picture(LOGO, In(ML + 0.38), In(1.62), In(0.92), In(0.92))
tf = txt(sl, ML + 0.4, 2.70, CW * 0.82, 1.6)
para(tf, "Detailed System Design", size=38, color=WHITE, font=SERIF, first=True, space_after=6)
para(tf, "Evidence, not assertion.", size=17, color=RGBColor(0xF2,0xD8,0xDC), italic=True, font=SERIF, space_after=8)
rect(sl, ML + 0.4, 4.02, 1.6, 0.035, fill=RGBColor(0xE8,0xB8,0xC0))
tf = txt(sl, ML + 0.4, 4.30, CW * 0.74, 1.5)
para(tf, "Ashutosh Sinha", size=18, color=WHITE, bold=True, first=True, space_after=4)
para(tf, "Independent Researcher   ·   ajsinha@gmail.com", size=12, color=RGBColor(0xF2,0xD8,0xDC), space_after=14)
para(tf, "Full document: docs/14-detailed-design.md   ·   Architecture: docs/04-architecture.md   ·   Adversarial review: docs/11-adversarial-review.md",
     size=10.5, color=RGBColor(0xE8,0xC4,0xCA), line=1.3)
para(tf, "© 2026 Ashutosh Sinha. All rights reserved. Proprietary and confidential — see LICENSE and NOTICE. "
         "Not legal, regulatory or financial advice.",
     size=8.5, color=RGBColor(0xD8,0xA0,0xAC), space_before=10, line=1.25)
