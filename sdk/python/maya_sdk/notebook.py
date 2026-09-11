"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Reading MAYA in a notebook, where a refusal is easiest to lose.

`FR-PLT-002` asks for notebook integration alongside the CLI, and the useful
version of that is narrower than it sounds. A notebook already renders dicts, and
wrapping every answer in a widget would be decoration.

**What a notebook actually breaks is the refusal.** A `Refused` arrives as a
traceback: twenty lines of frames, and at the bottom a message that happens to
contain the remediation. The remediation is the half that tells somebody what to
do, and in that position it is the half nobody reads — so people learn to treat
MAYA's refusals as errors, which is precisely the reading this platform exists to
prevent.

`install()` puts the three parts at the top, in that order, with the frames
collapsed underneath. Nothing is swallowed: the exception still propagates, the
cell still fails, and a notebook run as a job still stops. The change is only
what a person sees first.

**It does not import IPython at all**, and not by contortion. The SDK has no
dependencies on purpose — a governance platform that cannot be deployed
air-gapped is one somebody works around — and the test that holds that line
walks every import statement in the package rather than trusting a `try`.

It turns out not to need one. *If IPython is not already in `sys.modules`, you
are not in a notebook*, so the honest lookup is the one that asks whether it is
there rather than the one that tries to put it there. What this module carries
instead is a one-method `Html`: `_repr_html_` is the whole protocol a notebook
needs, and standing in for it costs less than depending on it.
"""
from __future__ import annotations

import html
import sys
from typing import Any, Dict, Optional

from maya_sdk.errors import Refused, Unreachable

#: The colours are named rather than themed: a notebook may be light or dark and
#: this has no way to ask, so it leans on the border and the weight instead of
#: on a background nobody can predict.
STYLE = ("border-left:4px solid #b3261e;padding:.5rem .75rem;"
         "margin:.25rem 0;font-family:ui-monospace,SFMono-Regular,monospace;"
         "font-size:.85rem;line-height:1.45")


class Html:
    """A fragment a notebook renders and everything else can still read.

    `IPython.display.HTML` would do this, and importing it would make these
    helpers unusable — and untestable — anywhere IPython is not installed. The
    protocol is one method, so standing in for it costs less than depending on
    it.
    """

    def __init__(self, data: str):
        self.data = data

    def _repr_html_(self) -> str:
        return self.data

    def __repr__(self) -> str:                # pragma: no cover - console only
        return self.data


def as_html(exc: Refused) -> str:
    """A refusal as three labelled parts, remediation included."""
    parts = [f'<div style="{STYLE}">',
             f'<div><strong>REFUSED {html.escape(exc.code)}</strong> '
             f'<span style="opacity:.7">({exc.status})</span></div>',
             f'<div>{html.escape(exc.detail)}</div>']
    if exc.remediation:
        parts.append(f'<div style="margin-top:.4rem">&rarr; '
                     f'{html.escape(exc.remediation)}</div>')
    if exc.request_id:
        parts.append(f'<div style="opacity:.6;margin-top:.4rem">request '
                     f'{html.escape(exc.request_id)}</div>')
    parts.append("</div>")
    return "".join(parts)


def unreachable_html(exc: Unreachable) -> str:
    """Not a verdict, and it says so.

    The distinction the SDK draws between `Refused` and `Unreachable` is worth
    nothing if a notebook renders them the same way — somebody reading a red box
    concludes MAYA said no, when MAYA said nothing.
    """
    return (f'<div style="{STYLE};border-left-color:#7a5900">'
            f'<div><strong>UNREACHABLE</strong></div>'
            f'<div>{html.escape(str(exc))}</div>'
            f'<div style="margin-top:.4rem">&rarr; this is not a verdict. '
            f'MAYA did not answer, so nothing has been established either '
            f'way.</div></div>')


def install(shell: Optional[Any] = None) -> bool:
    """Render refusals readably in this notebook. Returns whether it took.

    Registers a custom handler for the two exception types that carry a
    decision. Everything else keeps IPython's own traceback, because a bug in
    somebody's own cell is not a governance answer and dressing it up as one
    would be the same conflation pointed the other way.
    """
    shell = shell or _shell()
    if shell is None:
        return False

    def _render(_shell, _etype, exc, _tb, tb_offset=None):
        _display(Html(as_html(exc) if isinstance(exc, Refused)
                      else unreachable_html(exc)))
        # Still raised. The cell fails, a papermill run stops, and a notebook
        # executed as a job does not go green past a refusal — the rendering
        # changes what a person sees first, never what happened.
        raise exc

    # One call with both types: `set_custom_exc` replaces the whole
    # registration rather than adding to it, so a second call would silently
    # drop the first.
    shell.set_custom_exc((Refused, Unreachable), _render)
    return True


def table(rows: Any, columns: Optional[Dict[str, str]] = None) -> Any:
    """A list of dicts as an HTML table, for reading rather than for analysis.

    Deliberately not a DataFrame: pandas is not a dependency of this package and
    a governance answer is usually read, not aggregated. Somebody who wants a
    frame has `pd.DataFrame(answer)` and does not need this.
    """
    if isinstance(rows, dict):
        rows = rows.get("items") or rows.get("models") or [rows]
    rows = list(rows or [])
    if not rows:
        # Not an empty table. An empty result and an empty ESTATE look the same
        # on a screen, and the second is almost never what happened — a scope
        # is.
        return Html("<em>nothing to show &mdash; which is not the same as "
                    "nothing existing; check what this call was scoped to</em>")
    keys = list(columns or {k: k for k in rows[0]})
    head = "".join(f"<th style='text-align:left;padding:.2rem .6rem'>"
                   f"{html.escape((columns or {}).get(k, k))}</th>"
                   for k in keys)
    body = "".join(
        "<tr>" + "".join(
            f"<td style='padding:.2rem .6rem'>"
            f"{html.escape(str(row.get(k, '')))}</td>" for k in keys) + "</tr>"
        for row in rows)
    return Html(f"<table style='font-size:.85rem;border-collapse:collapse'>"
                f"<thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>")


def _display(fragment: "Html") -> None:
    """Through IPython where it is already loaded, printed where it is not.

    Looked up in `sys.modules` rather than imported: if IPython is not already
    there, this is not a notebook and there is nothing to display into. That
    also keeps the package's import list free of it, which is a line the suite
    checks rather than a claim the docs make.
    """
    module = sys.modules.get("IPython.display")
    if module is None:                      # pragma: no cover - no notebook
        print(fragment.data)
        return
    module.display(module.HTML(fragment.data))


def _shell() -> Optional[Any]:
    """The running notebook, or nothing. Same reasoning as `_display`."""
    module = sys.modules.get("IPython")
    if module is None:
        return None
    return module.get_ipython()
