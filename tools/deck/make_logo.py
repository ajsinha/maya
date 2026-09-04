"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.
"""
"""Render the MAYA logo lockup to PNG.

The SVG in assets/logo/ is the source of truth for web and Markdown. This exists
because ImageMagick's SVG text rendering mishandles letter-spacing, and the deck
needs a raster asset it can embed.
"""
import os, sys
from PIL import Image, ImageDraw, ImageFont

OUT = sys.argv[1] if len(sys.argv) > 1 else "assets/logo"
CRIMSON, INK, SLATE, RULE, WHITE = (0xA5,0x1C,0x30), (0x1C,0x1C,0x1E), (0x4A,0x4F,0x57), (0xD8,0xD4,0xCF), (255,255,255)
SERIF   = "/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf"
SERIF_I = "/usr/share/fonts/truetype/liberation/LiberationSerif-Italic.ttf"
SANS    = "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"
S = 4   # supersample factor


def mark(size, bg=CRIMSON, fg=WHITE, radius_ratio=0.203):
    """A square inscribed in a circle.

    The oldest model there is -- Archimedes approximated pi this way. A tractable
    figure standing in for one it can never quite be. The gap is the model error;
    the four points are where the model and the world agree.
    """
    import math
    n = size * S
    img = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(img, "RGBA")
    if bg:
        d.rounded_rectangle([0, 0, n - 1, n - 1], radius=int(n * radius_ratio), fill=bg)
    u = n / 512.0
    P = lambda x, y: (x * u, y * u)
    ghost = (fg[0], fg[1], fg[2], 140)
    R, k = 150, 0.86
    d.ellipse([P(256 - R, 256 - R), P(256 + R, 256 + R)], outline=ghost, width=max(1, int(12 * u)))
    rr = R * k
    v = [(256 + rr * math.cos(-math.pi / 2 + math.pi / 2 * i),
          256 + rr * math.sin(-math.pi / 2 + math.pi / 2 * i)) for i in range(4)]
    d.line([P(*q) for q in v] + [P(*v[0])], fill=fg, width=max(1, int(32 * u)), joint="curve")
    for q in v:
        d.ellipse([P(q[0] - 17, q[1] - 17), P(q[0] + 17, q[1] + 17)], fill=fg)
    return img.resize((size, size), Image.LANCZOS)


def tracked(d, xy, text, font, fill, spacing=0):
    x, y = xy
    for ch in text:
        d.text((x, y), ch, font=font, fill=fill)
        x += d.textlength(ch, font=font) + spacing
    return x


def lockup(path):
    W, H = 1180 * S, 320 * S
    img = Image.new("RGBA", (W, H), (255, 255, 255, 0))
    d = ImageDraw.Draw(img)
    m = mark(272 * S)
    img.alpha_composite(m, (24 * S, 24 * S))
    f_name = ImageFont.truetype(SERIF, 112 * S)
    f_tag  = ImageFont.truetype(SANS, 32 * S)
    f_slog = ImageFont.truetype(SERIF_I, 34 * S)
    tracked(d, (356 * S, 46 * S), "MAYA", f_name, INK, spacing=10 * S)
    tracked(d, (360 * S, 160 * S), "Model & AI Lifecycle Assurance", f_tag, CRIMSON, spacing=1.5 * S)
    d.line([(360 * S, 224 * S), (560 * S, 224 * S)], fill=RULE, width=3 * S)
    d.text((360 * S, 244 * S), "Evidence, not assertion.", font=f_slog, fill=SLATE)
    return img.resize((1180, 320), Image.LANCZOS).save(path)


os.makedirs(OUT, exist_ok=True)
lockup(os.path.join(OUT, "maya-lockup.png"))
mark(1024).save(os.path.join(OUT, "maya-mark.png"))
mark(256).save(os.path.join(OUT, "maya-mark-256.png"))
mark(64).save(os.path.join(OUT, "maya-mark-64.png"))
mark(512, bg=None, fg=CRIMSON).save(os.path.join(OUT, "maya-mark-transparent.png"))
mark(512, bg=None, fg=WHITE).save(os.path.join(OUT, "maya-mark-white.png"))   # knockout, for crimson
print("logo assets written to", OUT)
