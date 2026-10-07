"""
Render MAYA's favicons from the logo, so the browser tab shows the mark itself.

    python tools/brand/favicons.py

Every icon is rasterised from ``maya/web/static/img/maya-mark.svg`` by Inkscape -- the
square inscribed in a circle on crimson, with its four points -- and the multi-size
``favicon.ico`` is assembled from the small PNGs. Modern browsers use the SVG directly;
the PNGs and the ICO are for the ones that do not, and for home-screen shortcuts.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image

IMG = Path(__file__).resolve().parents[2] / "maya" / "web" / "static" / "img"
SOURCE = IMG / "maya-mark.svg"
SIZES = {
    "favicon-16.png": 16,
    "favicon-32.png": 32,
    "favicon-48.png": 48,
    "apple-touch-icon.png": 180,
    "icon-192.png": 192,
    "icon-512.png": 512,
}


def main() -> int:
    inkscape = shutil.which("inkscape")
    if not inkscape:
        print("Inkscape is needed to rasterise the SVG: install it and run again.")
        return 1
    for name, px in SIZES.items():
        subprocess.run(
            [
                inkscape,
                str(SOURCE),
                "--export-type=png",
                f"--export-filename={IMG / name}",
                f"--export-width={px}",
                f"--export-height={px}",
            ],
            check=True,
            capture_output=True,
        )
    # the old 64-pixel raster is replaced by the 48-pixel render under its old name, so
    # nothing that linked favicon.png breaks
    shutil.copyfile(IMG / "favicon-48.png", IMG / "favicon.png")
    icons = [Image.open(IMG / f"favicon-{px}.png") for px in (16, 32, 48)]
    icons[-1].save(
        IMG / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)], append_images=icons[:-1]
    )
    print("favicons written to", IMG)
    return 0


if __name__ == "__main__":
    sys.exit(main())
