---
title: Reading MAYA comfortably
slug: reading-maya-comfortably
section: Getting started
order: 30
icon: eyeglasses
summary: Text size and theme, where the controls are, and what MAYA guarantees about legibility — contrast that clears WCAG AA in both themes, a visible focus ring on every control, a way past the navigation, and a choice that survives a reload without a flash.
audience: Everyone
---

# Reading MAYA comfortably

Governance work is reading work. A validator comparing two runs, an approver
reading a warrant, a reviewer working through a findings table — all of it is
somebody looking at small type for a long time, often on a machine they did not
choose. Two controls, both in the **Appearance** menu in the top bar, and a set
of guarantees underneath them.

## Text size

Five steps: **Small**, **Normal**, **Large**, **Larger**, **Largest** — from
0.9× to 1.5× of the default.

The scale moves **everything together**, not just body text. Every size in the
interface is expressed as a ratio of one root number, so a heading stays a
heading and a table stays proportionate; only the root number changes. Scaling
body text alone is the usual way this is done, and it leaves every heading,
chip, badge and table header exactly where it was, which looks broken and reads
worse than not scaling at all.

**This is not your browser's zoom, and it is deliberately not.** Zoom scales the
*layout* — at 150%, a portfolio table becomes a table you can see two columns
of, and horizontal scrolling to read a row is worse than small type. Changing
the text size leaves the layout to reflow around it, so a wide table stays a
wide table with larger type in it. Browser zoom still works, and the two
compose; they solve different problems.

Your choice is stored in the browser and applied **before the first paint**, so
a reload does not flash the default size at you. It is per-browser rather than
per-account: it follows the machine you are reading on, which is the thing
that actually varies.

## Theme

**Light**, **Dark**, or **System** — System follows what your operating system
is set to, including when it changes at dusk. The same menu, above the text
sizes. It is applied before the first paint for the same reason.

## What is guaranteed, not just offered

These are asserted by tests rather than checked by eye, because "it looked fine
on my monitor" is how contrast regressions ship:

- **Every text pair clears WCAG AA**, in *both* themes — including badges,
  which carry colour as meaning and are the easiest thing to get wrong, and
  menu items, which must contrast with the menu they are in rather than with
  the bar they drop from.
- **Every control that can take focus shows a ring**, and the ring inverts on
  crimson surfaces so it does not vanish into the bar. It is `:focus-visible`,
  so it appears for keyboard users without ringing every mouse click.
- **There is a way past the navigation** — a skip link — so a keyboard or
  screen-reader user does not walk the whole bar on every page.
- **Reduced motion is honoured.** If your system asks for less animation, MAYA
  stops animating.
- **No template pins a size in pixels or paints its own colour.** Every colour
  resolves through a token and every size through the scale, which is what
  makes the two controls above work everywhere rather than in most places.
- **Fonts are served by MAYA**, not fetched from a font host — so the interface
  renders identically on a network that cannot reach one, and no third party
  learns which pages a bank's staff read.

## If something is still hard to read

Tell whoever runs your MAYA instance rather than working around it. Contrast and
sizing here are properties of the interface that are tested on every change, so
a page that is hard to read is a defect with a place to be fixed — and a
workaround in one browser does not help the next person.
