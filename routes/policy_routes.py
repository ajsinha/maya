"""
MAYA — versioned gates.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

A policy tightens a gate. It cannot loosen one — the checks written in the
registry are the floor — and it cannot be published until its own cases pass.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import Field

from fastapi import HTTPException, Request

from core.platform.configuration import FORMAT, Configuration
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


class ConfigurationIn(Body):
    """A configuration document, in the platform's own format.

    `rationale` is required on apply and `approved_by` on any plan that
    loosens: a configuration that tightens can be a deployment, one that
    loosens is a decision, and the whole risk of configuration-as-code is that
    the two travel in the same pull request.
    """
    format: str = FORMAT
    configuration: Dict[str, Any] = Field(default_factory=dict)
    rationale: str = ""
    approved_by: str = ""


class ConnectorIn(Body):
    """A document the source system exported.

    There is no field for a credential and no endpoint that connects to
    anything. A governance register holding read access to every ML platform in
    the bank is a large attack surface for a read-only need.
    """
    document: Any
    ingest: bool = False


class SweepIn(Body):
    """One sweep from a scanner MAYA does not run.

    Every field is optional **here** and required by the contract, which is
    not a contradiction: a 422 naming three missing fields is the framework
    answering, and the framework stops at the first shape it dislikes. The
    contract answers with every problem at once and says why each matters,
    which is the difference between a scanner author fixing three things in
    one round and re-running over forty thousand files three times.

    `recall_known` is almost always false. The register computes precision
    from the dismissals and cannot compute recall — it has no idea what the
    scanner did not look at.
    """
    scanner: str = ""
    scope: str = ""
    recall_known: Optional[bool] = None
    candidates: List[Dict[str, Any]] = Field(default_factory=list)


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
            # A gate that does not exist answered `{"versions": []}` — the same
            # answer as a real gate nobody has ever changed. Somebody auditing
            # whether a gate had been relaxed could mistype it and be told,
            # convincingly, that it never had been.
            from core.policy.common import GATES
            from routes.base import STATUS
            if gate not in GATES:
                raise HTTPException(STATUS["unknown_gate"], {
                    "error": "unknown_gate",
                    "detail": f"'{gate}' is not a policy gate",
                    "remediation": "one of " + ", ".join(GATES)})
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
            # Not strict: this is the sandbox. A caller asking "what would the
            # gate decide about these facts" expects the ones they did not name
            # to take their documented defaults — which is exactly what the LIVE
            # path must not do.
            return self.guard(
                lambda: policies.decide(body.gate, body.facts, strict=False))

        # ---------------------------------------------------- configuration
        @self.app.get(f"{api}/configuration/boundary", tags=["policy"])
        def configuration_boundary(request: Request):
            """What is configuration, what is code, and why the line is there.

            Published, because *why can I not configure X* is a question with
            an answer, and the answer is more useful than the absence.
            """
            self.authorise(request, "policy:read")
            return Configuration.boundary()

        @self.app.get(f"{api}/configuration", tags=["policy"])
        def export_configuration(request: Request, sections: str = ""):
            """What is in force, as a document.

            Read from the registers rather than from whatever was last applied
            — the difference between a description of the platform and a
            description of somebody's intentions.
            """
            self.authorise(request, "policy:read",
                           estate_wide="exporting the platform configuration")
            wanted = [s.strip() for s in sections.split(",") if s.strip()]
            return self.guard(lambda: self.ctx["configuration"].export(
                sections=wanted or None))

        @self.app.post(f"{api}/configuration/plan", tags=["policy"])
        def plan_configuration(request: Request, body: ConfigurationIn):
            """Exactly what would change, and which way each change points.

            Read `loosens` first. *Three rules changed* is not a reviewable
            sentence; *two of these three let something through that is refused
            today* is.
            """
            self.authorise(request, "policy:read",
                           estate_wide="planning a configuration change")
            return self.guard(lambda: self.ctx["configuration"].plan(
                {"format": body.format, "configuration": body.configuration}))

        @self.app.post(f"{api}/configuration/apply", tags=["policy"])
        def apply_configuration(request: Request, body: ConfigurationIn):
            """Record that a configuration was applied, with its diff.

            A governance act and not a deployment step. Each section is applied
            through its own register, which keeps its own approval — a path
            here that wrote policies directly would be a second way to publish
            a gate, and the second way is always the one without the signature.
            """
            who = self.authorise(
                request, "policy:publish",
                estate_wide="applying a configuration across the platform")
            return self.guard(lambda: self.ctx["configuration"].apply(
                {"format": body.format, "configuration": body.configuration},
                body.rationale, actor=self.actor(who),
                approved_by=body.approved_by))

        # ---------------------------------------------- plugin discovery
        @self.app.get(f"{api}/plugins/contract", tags=["policy"])
        def plugin_contract(request: Request):
            """What a firm's package declares, and what it may extend."""
            self.authorise(request, "policy:read")
            from core.plugins.discovery import PluginDiscovery
            return PluginDiscovery.contract()

        @self.app.get(f"{api}/plugins/discovered", tags=["policy"])
        def discovered(request: Request):
            """What is installed, read from metadata. Nothing is imported.

            Read `state`. `seen` means installed and **not enabled** — which is
            the point: installing makes an extension available and
            configuration makes it used, because a control that took effect
            when somebody bumped a dependency is one nobody changed on purpose.
            """
            self.authorise(request, "policy:read",
                           estate_wide="listing installed extensions")
            return self.guard(lambda: self.ctx["plugin_discovery"].discover())

        @self.app.post(f"{api}/plugins/enable", tags=["policy"])
        def enable_plugin(request: Request, axis: str, name: str):
            """Import and register one plugin. Refused unless config names it."""
            who = self.authorise(
                request, "policy:publish",
                estate_wide="loading a third-party extension")
            return self.guard(lambda: self.ctx["plugin_discovery"].enable(
                axis, name, actor=self.actor(who)))

        # ------------------------------------------------------ connectors
        @self.app.get(f"{api}/connectors", tags=["policy"])
        def connectors(request: Request):
            """What each connector reads, and what no connector can bring."""
            self.authorise(request, "model:read")
            from core.discovery.connectors import Connectors
            return Connectors.describe()

        @self.app.post(f"{api}/connectors/{{source}}", tags=["policy"])
        def read_connector(request: Request, source: str, body: ConnectorIn):
            """Parse an export into candidates for triage. Registers nothing."""
            who = self.authorise(
                request, "model:read",
                estate_wide="importing candidates from an ML platform export")
            engine = self.ctx["connectors"]
            if body.ingest:
                return self.guard(lambda: engine.ingest(
                    source, body.document, actor=self.actor(who)))
            return self.guard(lambda: engine.read(source, body.document))

        # ------------------------------------------------ scanner contract
        @self.app.get(f"{api}/scanner-contract", tags=["policy"])
        def scanner_contract(request: Request):
            """What a scanner has to send, and why MAYA does not run one."""
            self.authorise(request, "model:read")
            from core.discovery.contract import ScannerContract
            return ScannerContract.contract()

        @self.app.post(f"{api}/scanner-contract/check", tags=["policy"])
        def check_sweep(request: Request, body: SweepIn):
            """What is wrong with this sweep — all of it, before anything is stored."""
            self.authorise(request, "model:read",
                           estate_wide="checking a discovery sweep")
            return self.guard(lambda: self.ctx["scanner_contract"].check(
                body.model_dump()))

        @self.app.post(f"{api}/scanner-contract/ingest", status_code=201,
                       tags=["policy"])
        def ingest_sweep(request: Request, body: SweepIn):
            """Check, then hand to the register. Refused as a whole or not at all."""
            who = self.authorise(request, "model:register",
                                 estate_wide="ingesting a discovery sweep")
            return self.guard(lambda: self.ctx["scanner_contract"].ingest(
                body.model_dump(), actor=self.actor(who)))

        @self.app.get(f"{api}/scanner-contract/grade", tags=["policy"])
        def grade_scanner(request: Request, scanner: str = ""):
            """What the register knows about a scanner, and what it cannot know."""
            self.authorise(request, "model:read",
                           estate_wide="grading a discovery scanner")
            return self.guard(
                lambda: self.ctx["scanner_contract"].grade(scanner))

        # ------------------------------------------- the database backstop
        @self.app.get(f"{api}/row-level-security", tags=["policy"])
        def row_level_security(request: Request):
            """Whether a database backstop is in force under the scope check.

            **The scope check is the control.** It decides, it carries the
            reasoning, and it produces a refusal somebody can act on. This is
            the backstop for the case the control cannot cover: the endpoint
            somebody wrote last week and forgot to filter, where the honest
            outcome is zero rows rather than another entity's models.

            Three things to read, in order. `available` is false on SQLite and
            there is nothing to be done about that — row-level security is a
            PostgreSQL feature. `connecting_role_is_exempt` matters more than
            anything below it: a superuser bypasses RLS entirely, `FORCE` or
            not, so a deployment that applied every statement perfectly and
            then connected as `postgres` has a policy that does nothing and a
            configuration that looks correct. And `forced` rather than
            `enabled`: enabled-without-forced is the configuration that looks
            right in a screenshot and lets the table owner read everything.
            """
            self.authorise(request, "policy:read",
                           estate_wide="reading the database backstop")
            rls = getattr(request.app.state, "rls", None)
            if rls is None:
                return {"available": False,
                        "detail": "no row-level security is wired"}
            return rls.posture()
