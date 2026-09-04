"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.
"""
"""Geometry audit for generated decks.

Distinguishes two cases, because they are not the same defect:

  * A **container** -- a shape with a visible fill or outline (card, code block,
    callout, table cell). Text exceeding it visibly escapes its border, which is
    always a defect.
  * A **plain textbox** -- no fill, no outline. Text flowing past its nominal
    height is invisible *unless* it collides with something below it. Only the
    collision is a defect.

Reporting every textbox overflow would bury the real problems, which is how the
code-block overflow on the design deck survived the first audit.
"""
import sys, os
from pptx import Presentation
from pptx.util import Emu

EMU = 914400.0
SW, SH = 13.333, 7.5
FOOTER_Y = SH - 0.55
SANS, SERIF = "Calibri", "Georgia"
INTRINSIC = 1.10          # line_spacing multiplies the intrinsic line box, not the point size

DECK = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
    os.path.dirname(__file__), "..", "..", "docs", "Models-as-Parametric-Kernels.pptx")


def est_lines(text, width_in, fs, bold, font):
    if not text:
        return 1
    frac = 0.505 if font != SERIF else 0.545
    if font in ("Consolas", "Courier New"):
        frac = 0.600
    if bold:
        frac += 0.022
    cpl = max(4, int(width_in / (fs * frac / 72.0)))
    lines, cur = 1, 0
    for w in text.split():
        need = len(w) + (1 if cur else 0)
        if cur + need > cpl:
            lines += 1
            cur = len(w)
            while cur > cpl:
                lines += 1
                cur -= cpl
        else:
            cur += need
    return lines


# A chevron's notch eats width on both sides, and an arrow's head eats it on
# one. Measuring these as plain rectangles under-counts the lines their text
# needs, which is exactly how text ends up outside a shape that the audit
# called clean.
NOTCHED = {"CHEVRON", "PENTAGON", "HOME_PLATE"}
POINTED = {"RIGHT_ARROW", "LEFT_ARROW", "UP_ARROW", "DOWN_ARROW",
           "STRIPED_RIGHT_ARROW", "NOTCHED_RIGHT_ARROW"}


def usable_width(sh):
    """The width text may actually occupy inside this shape.

    Margins are read from the shape rather than assumed. A textbox here is
    created with zero margins and an auto-shape with a tenth of an inch each
    side; assuming one number for both makes the audit pessimistic about half
    the deck and optimistic about the other half, and an audit that cries wolf
    is an audit somebody stops reading.
    """
    W = (sh.width or 0) / EMU
    H = (sh.height or 0) / EMU
    tf = sh.text_frame
    margins = ((tf.margin_left or 0) + (tf.margin_right or 0)) / EMU
    W -= margins
    kind = str(getattr(sh, "shape_type", "") or "")
    name = str(getattr(sh, "name", "") or "").upper()
    for token in NOTCHED:
        if token in kind.upper() or token in name:
            return max(0.3, W - 2 * 0.18 * H)     # notch in, point out
    for token in POINTED:
        if token in kind.upper() or token in name:
            return max(0.3, W - 0.18 * H)
    return W


def text_extent(sh):
    """Estimated rendered height of a shape's text, in inches."""
    W = usable_width(sh)
    total = 0.0
    for p in sh.text_frame.paragraphs:
        ptxt = "".join(r.text for r in p.runs)
        if not ptxt:
            total += 6 / 72.0
            continue
        r0 = p.runs[0]
        fs = r0.font.size.pt if r0.font.size else 12
        font = r0.font.name or SANS
        ls = p.line_spacing if isinstance(p.line_spacing, float) else 1.22
        indent = 0.35 if p.level else 0.0
        n = est_lines(ptxt, max(0.4, W - indent), fs, bool(r0.font.bold), font)
        total += n * fs * max(ls, 1.15) * INTRINSIC / 72.0
        total += ((p.space_before.pt if p.space_before else 0)
                  + (p.space_after.pt if p.space_after else 0)) / 72.0
    return total


def is_container(sh):
    """Visible border or fill => overflow is visible => it is a defect."""
    try:
        if sh.fill.type is not None and sh.fill.type != 5:      # 5 == background/none
            return True
    except Exception:
        pass
    try:
        if sh.line.fill.type is not None and sh.line.fill.type != 5:
            return True
    except Exception:
        pass
    return False


def enclosing(sh, L, T, W, H, boxes):
    """The smallest visible container this shape sits inside, if any."""
    best = None
    for o, oL, oT, oW, oH in boxes:
        if o is sh or not is_container(o):
            continue
        if oW < 0.2 or oH < 0.2:            # accent bars and rules, not cards
            continue
        if not (oL - 0.02 <= L and oT - 0.02 <= T
                and L + W <= oL + oW + 0.02 and T <= oT + oH + 0.02):
            continue
        if best is None or oW * oH < best[3] * best[4]:
            best = (o, oL, oT, oW, oH)
    return best


def main():
    prs = Presentation(DECK)
    issues = []
    for idx, slide in enumerate(prs.slides, 1):
        boxes = []
        # A slide only has a footer if the thin rule was drawn. Title and divider
        # slides have none, and the footer's own text legitimately sits below it.
        has_footer = any(
            sh.top is not None and 6.90 <= sh.top / EMU <= 7.00
            and (sh.height or 0) / EMU < 0.05 for sh in slide.shapes)
        for sh in slide.shapes:
            if sh.left is None or sh.top is None:
                continue
            L, T = sh.left / EMU, sh.top / EMU
            W, H = (sh.width or 0) / EMU, (sh.height or 0) / EMU
            boxes.append((sh, L, T, W, H))
            if L < -0.02 or T < -0.02 or L + W > SW + 0.02 or T + H > SH + 0.02:
                issues.append(f"S{idx:02d} OFF-SLIDE    ({L:.2f},{T:.2f}) {W:.2f}x{H:.2f}")

        for sh, L, T, W, H in boxes:
            if not sh.has_text_frame or not sh.text_frame.text.strip():
                continue
            need = text_extent(sh)
            label = sh.text_frame.text.strip().replace("\n", " ")[:54]

            if is_container(sh) and need > H + 0.06:
                issues.append(f"S{idx:02d} OVERFLOWS BORDER  need {need:.2f}\" have {H:.2f}\" :: {label!r}")
                continue

            # A textbox with no fill is still bounded by whatever it sits
            # inside. Its overflow escapes that container's border just as
            # visibly as if the text belonged to the container itself, and
            # checking only filled shapes is how a card's body spilling out of
            # its own card went unreported.
            host = enclosing(sh, L, T, W, H, boxes)
            if host is not None:
                hostL, hostT, hostW, hostH = host[1:]
                # The same 0.06" tolerance every other check here uses: the
                # estimator simulates wrapping rather than measuring it, and a
                # check tighter than its own error reports noise.
                if T + need > hostT + hostH + 0.06:
                    issues.append(
                        f"S{idx:02d} ESCAPES ITS CARD  text to {T + need:.2f}\" "
                        f"card ends {hostT + hostH:.2f}\" :: {label!r}")
                    continue

            bottom = T + max(need, H)
            # only content that STARTS above the rule can collide with it;
            # the footer's own label starts below it, by design
            if has_footer and T < FOOTER_Y - 0.02 and bottom > FOOTER_Y + 0.05:
                issues.append(f"S{idx:02d} HITS FOOTER   bottom {bottom:.2f}\" :: {label!r}")
                continue
            if bottom > SH - 0.05:
                issues.append(f"S{idx:02d} PAST SLIDE    bottom {bottom:.2f}\" :: {label!r}")
                continue

            # A free textbox only matters if its overflow lands on something
            # else. Any shape that carries text is a target, not only a filled
            # one: text printed over text is the defect a reader actually sees,
            # and a bare textbox below is just as ruined as a card.
            if need > H + 0.06:
                for o, oL, oT, oW, oH in boxes:
                    if o is sh:
                        continue
                    carries = (o.has_text_frame and o.text_frame.text.strip())
                    if not (is_container(o) or carries):
                        continue
                    if oT < T + H - 0.02:            # not below us
                        continue
                    # Require real horizontal overlap rather than a shared edge,
                    # so columns standing side by side are not reported.
                    share = min(L + W, oL + oW) - max(L, oL)
                    if share < 0.25 * min(W, oW):
                        continue
                    if T + need > oT + 0.04:
                        issues.append(
                            f"S{idx:02d} COLLIDES      text to {T+need:.2f}\" meets shape at {oT:.2f}\" :: {label!r}")
                        break

    if issues:
        print(f"{len(issues)} issue(s)")
        print("\n".join(issues))
        sys.exit(1)
    print("no geometry issues detected")


main()
