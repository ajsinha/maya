"""
MAYA — the administration screens.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Administering this platform was, until now, an act you performed with `curl`.
Every one of these things — who may act, which rulebook is in force, what the
batch last did, whether the evidence chain still agrees with the anchors
written outside the database — had an API and no screen, which meant the people
who own those decisions could not see them without a developer beside them.

Read-only, deliberately. Each screen shows the state and names the endpoint
that changes it; the acts themselves stay where their evidence and their
segregation checks already live.
"""
from __future__ import annotations

import time
from typing import Any, Dict

from fastapi import Request
from fastapi.responses import HTMLResponse

from core.authz import DESCRIPTIONS, INCOMPATIBLE_ROLES, ROLES
from core.execution.grammar import vocabulary
from core.log import get_logger
from routes.base import Routes, login_required

logger = get_logger(__name__)


class AdminRoutes(Routes):
    def register(self) -> None:

        def gate(request: Request, permission: str):
            """Signed in, and holding the permission the screen's API needs.

            The same permission the API asks for, not a page-only rule: two
            authorisation rules for one thing is how a screen ends up showing
            what its endpoint refuses.
            """
            if (r := login_required(request)) is not None:
                return r, None
            who = self.page_principal(request)
            if who is None or not self.ctx["authz"].permits(who, permission):
                return self.refused_page(request, permission), None
            return None, who

        # ------------------------------------------------------------- index
        @self.app.get("/admin", response_class=HTMLResponse, tags=["ui"])
        def admin_index(request: Request):
            """What administering this platform consists of, and who may."""
            if (r := login_required(request)) is not None:
                return r
            who = self.page_principal(request)
            held = self.ctx["authz"].permissions(who) if who else frozenset()
            return self.page(request, "admin_index.html", held=held)

        # -------------------------------------------------- people and roles
        @self.app.get("/admin/principals", response_class=HTMLResponse, tags=["ui"])
        def principals_page(request: Request):
            """Who may act, what each role carries, and the duties that may
            never be held together."""
            refusal, who = gate(request, "principal:read")
            if refusal is not None:
                return refusal
            people = self.ctx["principals"]
            rows = people.list()
            authz = self.ctx["authz"]
            # Computed per person rather than per role: somebody may hold two
            # roles, and the union is what they can actually do.
            for row in rows:
                row["effective"] = sorted(authz.permissions(row))
                row["conflicts"] = [
                    {"roles": [a, b], "reason": reason}
                    for a, b, reason in INCOMPATIBLE_ROLES
                    if a in (row.get("roles") or []) and b in (row.get("roles") or [])]
            return self.page(
                request, "admin_principals.html", people=rows,
                roles=[{"name": name, "description": DESCRIPTIONS.get(name, ""),
                        "permissions": sorted(perms), "held_by":
                            sum(1 for r in rows if name in (r.get("roles") or []))}
                       for name, perms in sorted(ROLES.items())],
                incompatible=[{"roles": [a, b], "reason": reason}
                              for a, b, reason in INCOMPATIBLE_ROLES],
                segregation=authz.segregation.describe(),
                may_manage=authz.permits(who, "principal:manage"))

        # ------------------------------------------------ regulatory regimes
        @self.app.get("/admin/regimes", response_class=HTMLResponse, tags=["ui"])
        def regimes_page(request: Request):
            """Which rulebook is in force, what each demands, and whether the
            encoding of it is consistent."""
            refusal, who = gate(request, "regime:read")
            if refusal is not None:
                return refusal
            regimes = self.ctx["regimes"]
            active = set(regimes.active())
            rows = []
            for key, r in sorted(regimes.library.items()):
                # A regime whose encoding does not survive translation must not
                # be shown as merely "inactive": it cannot be activated at all,
                # and an administrator wondering why deserves the reason here.
                try:
                    satisfaction = regimes.check(key)
                except Exception as exc:                     # pragma: no cover
                    logger.warning("regime %s could not be checked: %s", key, exc)
                    # Same key the real answer uses. A failure shape with keys of
                    # its own is how a template comes to read one of them and
                    # silently render the other case.
                    satisfaction = {"holds": False, "detail": str(exc),
                                    "failures": [], "untranslated_terms": []}
                rows.append({
                    "key": key, "title": r["title"], "authority": r["authority"],
                    "active": key in active,
                    "vocabulary": sorted(r["signature"].terms),
                    "obligations": [{"key": s.key, "text": s.text,
                                     "citation": s.citation} for s in r["sentences"]],
                    "satisfaction": satisfaction})
            return self.page(request, "admin_regimes.html", regimes=rows,
                             may_activate=self.ctx["authz"].permits(who, "regime:activate"))

        # -------------------------------------------------- the batch
        @self.app.get("/admin/scheduler", response_class=HTMLResponse, tags=["ui"])
        def scheduler_page(request: Request):
            """What runs on a schedule, what each is for, and what it last did.

            A scheduler nobody notices has stopped is the same failure as a
            monitor nobody notices has stopped, one level up — so the health of
            the scheduler itself is the first thing on the page.
            """
            refusal, who = gate(request, "scheduler:read")
            if refusal is not None:
                return refusal
            scheduler = self.ctx["scheduler"]
            return self.page(
                request, "admin_scheduler.html",
                catalogue=scheduler.catalogue(),
                health=scheduler.health(),
                history=list(reversed(scheduler.history(50))),
                now=time.time(),
                may_run=self.ctx["authz"].permits(who, "scheduler:run"))

        # ------------------------------------------------ evidence integrity
        @self.app.get("/admin/evidence", response_class=HTMLResponse, tags=["ui"])
        def evidence_page(request: Request):
            """The hash chain, and whether it agrees with a second medium.

            Both questions, side by side and labelled, because they are not the
            same question. `verify_chain` compares the chain against itself,
            which a rewritten chain passes. The anchors are heads written to
            WORM storage outside the database; only that comparison says
            anything an attacker holding the database cannot arrange.
            """
            refusal, _who = gate(request, "evidence:read")
            if refusal is not None:
                return refusal
            evidence = self.ctx["evidence"]
            seq, head = evidence.head()
            return self.page(
                request, "admin_evidence.html",
                # Not evidence, but the same question one layer down: is the
                # store still the shape the code expects? The schema is applied
                # with CREATE TABLE IF NOT EXISTS, so an existing table is
                # skipped and a new column is never added — an instance can
                # therefore run for weeks on a schema that does not match its
                # own release and fail inside a workflow.
                drift=self.ctx["db"].drift(),
                chain=evidence.verify_chain(),
                anchors=evidence.verify_against_anchors(),
                checkpoint=evidence.checkpoint(),
                head_seq=seq, head_hash=head,
                anchor_root=getattr(getattr(evidence, "anchors", None), "root", None))

        # ------------------------------------------------ runtimes and fibres
        @self.app.get("/admin/runtimes", response_class=HTMLResponse, tags=["ui"])
        def runtimes_page(request: Request):
            """What may execute, and what each trainability class carries.

            The warrant grammar and the fibration are one screen because they
            are one question asked twice: what this platform will admit, and
            what it demands of what it admits.
            """
            refusal, _who = gate(request, "model:read")
            if refusal is not None:
                return refusal
            fibres = self.ctx["fibres"]
            return self.page(
                request, "admin_runtimes.html",
                grammar=vocabulary(),
                fibres=[_describe(fibres.of(k)) for k in fibres.classes()],
                gaps=fibres.totality())


def _describe(fibre: Any) -> Dict[str, Any]:
    """One fibre, flattened for a template. The same shape the API publishes,
    so the screen and the endpoint cannot describe a class differently."""
    return {"trainability_class": fibre.trainability_class, "label": fibre.label,
            "evidence": list(fibre.evidence), "lifecycle": list(fibre.lifecycle),
            "metrics": list(fibre.metrics), "templates": list(fibre.templates),
            "soundness": fibre.soundness, "outcomes": fibre.outcomes,
            "answers": fibre.answers}
