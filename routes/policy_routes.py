"""
MAYA — versioned gates.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

A policy tightens a gate. It cannot loosen one — the checks written in the
registry are the floor — and it cannot be published until its own cases pass.
"""
from __future__ import annotations

from typing import Any, Dict, List

from fastapi import Request

from core.policy import GATES, describe_facts, vocabulary
from core.policy.language import describe as describe_language
from routes.base import Body, Routes


class DraftIn(Body):
    gate: str
    rule: str
    reason: str
    cases: List[Dict[str, Any]]
    note: str = ""


class TryIn(Body):
    gate: str
    facts: Dict[str, Any] = {}


class PolicyRoutes(Routes):
    def register(self) -> None:
        policies, api = self.ctx["policies"], self.api

        @self.app.get(f"{api}/policies", tags=["policy"])
        def gates(request: Request):
            """Every gate: what is in force, where it came from, what it reads."""
            self.principal(request)
            return {"gates": policies.describe(),
                    "language": describe_language(),
                    "applies": "in addition to the checks written in the "
                               "registry, never instead of them: a policy can "
                               "add a condition and cannot remove one"}

        @self.app.get(f"{api}/policies/facts/{{gate}}", tags=["policy"])
        def facts(request: Request, gate: str):
            """The facts a policy on this gate may read, and nothing else."""
            self.principal(request)
            if gate not in GATES:
                raise self.not_found(f"no gate '{gate}'")
            return {"gate": gate, "facts": describe_facts(gate),
                    "vocabulary": vocabulary(gate)}

        @self.app.get(f"{api}/policies/history/{{gate}}", tags=["policy"])
        def history(request: Request, gate: str):
            """Every version, superseded ones included. Somebody will ask."""
            self.authorise(request, "policy:read")
            return {"gate": gate, "versions": policies.history(gate)}

        @self.app.post(f"{api}/policies", status_code=201, tags=["policy"])
        def draft(request: Request, body: DraftIn):
            """Write a policy and its cases. Nothing is in force until published.

            The cases are checked here: a rule that reads a fact the gate does
            not publish, or that does not behave as its own cases declare, is
            refused now rather than at the moment of a governance decision.
            """
            who = self.authorise(request, "policy:author")
            return self.guard(lambda: policies.draft(
                body.gate, body.rule, body.reason, body.cases,
                self.actor(who), body.note))

        @self.app.post(f"{api}/policies/{{policy_id}}/publish", tags=["policy"])
        def publish(request: Request, policy_id: str):
            """Put it in force. Authoring and publishing are separate duties.

            The response carries a diff of the outgoing policy's cases replayed
            against the incoming rule, so a change that loosens a gate is
            something somebody decided rather than something somebody discovered.
            """
            # The policy id is the SUBJECT, so the duties check can find the
            # `policy_drafted` node this person may have recorded against it.
            # Without it the check looks for evidence under an empty subject,
            # finds none, and permits everything — which is how the screen came
            # to claim an enforcement that never ran.
            who = self.authorise(request, "policy:publish", subject_id=policy_id)
            return self.guard(lambda: policies.publish(policy_id,
                                                       self.actor(who)))

        @self.app.get(f"{api}/policies/{{policy_id}}", tags=["policy"])
        def read(request: Request, policy_id: str):
            self.authorise(request, "policy:read")
            return self.guard(lambda: policies.require(policy_id))

        @self.app.post(f"{api}/policies/try", tags=["policy"])
        def try_it(request: Request, body: TryIn):
            """What the rule in force would decide about these facts.

            For somebody about to change a policy, and for somebody trying to
            understand a refusal they have already had.
            """
            self.authorise(request, "policy:read")
            return self.guard(lambda: policies.decide(body.gate, body.facts))
