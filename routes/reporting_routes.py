"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Risk appetite and the board pack over HTTP.

`build` computes without recording; `cut` records. The split matters: somebody
preparing for a meeting should be able to see what the pack will say without
creating the pack the committee will later be minuted against.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import HTTPException, Request
from fastapi.responses import Response
from pydantic import Field

from core.authz.scope import Scope
from core.reporting import NO_COMPOSITE, STATUS_MEANING
from core.reporting.returns import RegulatoryReturns
from core.reporting.views import SavedViews
from routes.base import Body, Routes


class CostIn(Body):
    """One attested cost figure.

    `urn` is optional and its absence is the interesting case: a bill line
    nobody can tie to a registered model is the finding this exists to surface.
    """
    amount: float
    currency: str
    period_start: float
    period_end: float
    source: str
    urn: str = ""
    reference: str = ""


class BudgetIn(Body):
    """Declared budgets, by one of the register's own ownership dimensions."""
    budgets: Dict[str, float] = Field(default_factory=dict)
    by: str = "owner"
    since: Optional[float] = None
    until: Optional[float] = None
    raise_findings: bool = False


class AppetiteIn(Body):
    metric: str
    limit: float
    rationale: str
    amber: Optional[float] = None
    scope: Dict[str, Any] = Field(default_factory=dict)
    owner: str = ""
    review_at: Optional[float] = None


class RetireIn(Body):
    metric: str
    scope: Dict[str, Any] = Field(default_factory=dict)
    reason: str = ""


class QueryIn(Body):
    """A structured query. There is deliberately no field for query text.

    A layer that accepted SQL could promise nothing about what a query can
    reach, and the first thing a BI tool does with table access is invent its
    own definition of the most important word in the register.
    """
    entity: str
    select: Optional[List[str]] = None
    where: List[Dict[str, Any]] = Field(default_factory=list)
    order_by: str = ""
    descending: bool = False
    limit: int = 1000


class SaveViewIn(Body):
    name: str
    entity: str
    query: Dict[str, Any] = Field(default_factory=dict)
    description: str = ""
    #: Shared views carry their QUERY and never their rows, so sharing one
    #: cannot disclose a row the reader's own scope does not reach.
    shared: bool = False


class AskIn(Body):
    """A question in English, and a limit on the rows it may return.

    Notably absent: anything that would let the caller supply the structured
    query directly. That is `/query`. Keeping the two apart means an answer
    from this endpoint always carries a translation somebody can read.
    """
    question: str
    limit: int = 100


class PackIn(Body):
    period: str = ""
    scope: Dict[str, Any] = Field(default_factory=dict)
    note: str = ""


class ReportingRoutes(Routes):
    def register(self) -> None:
        api = self.api
        appetite = self.ctx["appetite"]
        packs = self.ctx["board_packs"]

        # ------------------------------------------------------- appetite
        @self.app.get(f"{api}/portfolio/dimensions", tags=["reporting"])
        def portfolio_dimensions(request: Request):
            """The dimensions the register can be cut by, and what each means."""
            self.principal(request)
            from core.estate.portfolio import DIMENSIONS
            return {"dimensions": [{"dimension": k, "means": v}
                                  for k, v in DIMENSIONS.items()]}

        @self.app.get(f"{api}/portfolio", tags=["reporting"])
        def portfolio_cut(request: Request, dimension: str = "tier"):
            """The register grouped by one dimension, with what is owed in each.

            Ordered by outstanding work rather than alphabetically, because a
            cut sorted by name buries whatever needs doing.
            """
            self.authorise(request, "report:read")
            return self.guard(
                lambda: self.ctx["portfolio"].by(dimension))

        @self.app.get(f"{api}/portfolio/heatmap", tags=["reporting"])
        def portfolio_heatmap(request: Request, rows: str = "domain",
                              columns: str = "tier"):
            """A cross-tabulation, shaded by what is owed rather than by count.

            A grid coloured by count tells you where the models are, which
            nobody needed a grid to learn. A cell with forty healthy models and
            a cell with one that is missing its validation are not the same
            cell, and a count-coloured grid draws them identically.
            """
            self.authorise(request, "report:read")
            return self.guard(
                lambda: self.ctx["portfolio"].heatmap(rows, columns))

        @self.app.get(f"{api}/portfolio/trend", tags=["reporting"])
        def portfolio_trend(request: Request, points: int = 12,
                            span_days: float = 365.0):
            """The register as it stood, at intervals, folded from the chain.

            Not a snapshot table. A nightly snapshot starts on the day somebody
            remembered to add it and is wrong for every day before that; this
            is a series of as-at projections, true for every date the chain
            covers, and each point carries the chain hash that makes it
            verifiable rather than asserted.
            """
            self.authorise(request, "report:read")
            return self.guard(
                lambda: self.ctx["portfolio"].trend(points, span_days))

        @self.app.get(f"{api}/portfolio/aggregate", tags=["reporting"])
        def portfolio_aggregate(request: Request):
            """How much rides on the models that are not right.

            SR 26-2 VI is about aggregate risk, and the aggregate question is
            not *how many*. Read `exposure_coverage` alongside the figure: a
            weighted answer over a third of an estate presented as *the* answer
            would be worse than the count it replaced.
            """
            self.authorise(request, "report:read")
            return self.guard(lambda: self.ctx["portfolio"].aggregate())

        @self.app.get(f"{api}/risk-appetite/metrics", tags=["reporting"])
        def metrics(request: Request):
            """What may be held to a limit, and what each indicator is for."""
            self.principal(request)
            return {**appetite.vocabulary(), "statuses": STATUS_MEANING}

        @self.app.get(f"{api}/risk-appetite", tags=["reporting"])
        def in_force(request: Request):
            """Every live limit, least specific scope first."""
            self.principal(request)
            return {"appetite": appetite.in_force()}

        @self.app.post(f"{api}/risk-appetite", status_code=201, tags=["reporting"])
        def declare(request: Request, body: AppetiteIn):
            """Set a limit. Setting one over an existing limit versions it."""
            who = self.authorise(request, "policy:publish")
            return self.guard(lambda: appetite.declare(
                metric=body.metric, limit=body.limit, rationale=body.rationale,
                amber=body.amber, scope=body.scope, owner=body.owner,
                review_at=body.review_at, actor=self.actor(who)))

        @self.app.post(f"{api}/risk-appetite/retire", tags=["reporting"])
        def retire(request: Request, body: RetireIn):
            who = self.authorise(request, "policy:publish")
            return self.guard(lambda: appetite.retire(
                body.metric, scope=body.scope, reason=body.reason,
                actor=self.actor(who)))

        @self.app.get(f"{api}/risk-appetite/history/{{metric}}", tags=["reporting"])
        def history(request: Request, metric: str):
            """Every version of one limit, so a relaxation is findable."""
            self.principal(request)
            # "So a relaxation is findable" — and an unknown metric answered
            # with an empty history, which is exactly what a limit that has
            # never been relaxed looks like. The docstring states the purpose
            # this defeated.
            from core.reporting.common import METRICS
            from routes.base import STATUS
            known = {getattr(m, "key", getattr(m, "name", str(m)))
                     for m in METRICS}
            if metric not in known:
                # `STATUS`, not a literal: the code is already mapped and a
                # second opinion here is how one refusal comes to answer two
                # different statuses depending on which route raised it.
                raise HTTPException(STATUS["unknown_metric"], {
                    "error": "unknown_metric",
                    "detail": f"'{metric}' is not a risk appetite metric",
                    "remediation": "one of " + ", ".join(sorted(known))})
            return {"metric": metric, "versions": appetite.history(metric)}

        # ------------------------------------------------------ board pack
        @self.app.post(f"{api}/board-packs/preview", tags=["reporting"])
        def preview(request: Request, body: PackIn):
            """What the pack would say, without creating one.

            Somebody preparing for a meeting should be able to look before the
            committee is minuted against what they find.
            """
            self.authorise(request, "report:read")
            return self.guard(lambda: packs.build(period=body.period,
                                                  scope=body.scope))

        @self.app.post(f"{api}/board-packs", status_code=201, tags=["reporting"])
        def cut(request: Request, body: PackIn):
            """Record the pack. This is the one a minute refers to."""
            who = self.authorise(request, "report:cut")
            return self.guard(lambda: packs.cut(
                period=body.period, scope=body.scope, note=body.note,
                actor=self.actor(who)))

        @self.app.get(f"{api}/board-packs", tags=["reporting"])
        def listing(request: Request, limit: int = 12):
            self.authorise(request, "report:read")
            return {"packs": packs.history(limit=limit),
                    "no_composite": NO_COMPOSITE}

        @self.app.get(f"{api}/board-packs/{{pack_id}}", tags=["reporting"])
        def one(request: Request, pack_id: str):
            """A pack as it was read, not as it would be recomputed today."""
            self.authorise(request, "report:read")
            return self.guard(lambda: packs.get(pack_id))

        # ------------------------------------------------- the semantic layer
        @self.app.get(f"{api}/semantic-layer", tags=["reporting"])
        def semantic_layer(request: Request):
            """Every entity, field and operator this layer publishes.

            Read before querying. A field marked `derived` is computed by the
            same code the screens use, which is the point: `in_force` here is
            the platform's `in_force` and not somebody's `status = 'approved'`.
            """
            self.authorise(request, "report:read")
            return self.ctx["semantics"].describe()

        @self.app.post(f"{api}/query", tags=["reporting"])
        def run_query(request: Request, body: QueryIn):
            """Run one structured query under the caller's own scope.

            Scope filters rows rather than refusing the call, and the answer
            says how many rows it removed: a total that is silently short gets
            reconciled against somebody else's and the gap blamed on a bug.
            """
            who = self.authorise(
                request, "report:read",
                estate_wide=f"querying the {body.entity} entity")
            return self.guard(lambda: self.ctx["semantics"].query(
                body.entity, select=body.select, where=body.where,
                order_by=body.order_by, descending=body.descending,
                limit=body.limit, scope=Scope.of(who)))

        # --------------------------------------------------------- saved views
        @self.app.get(f"{api}/saved-views", tags=["reporting"])
        def list_views(request: Request):
            """Your own views, and everything shared with you."""
            who = self.authorise(request, "report:read")
            return self.guard(
                lambda: self.ctx["saved_views"].list(self.actor(who)))

        @self.app.post(f"{api}/saved-views", status_code=201, tags=["reporting"])
        def save_view(request: Request, body: SaveViewIn):
            """Keep a query. It is run once here, so a broken view is refused
            while its author is present rather than in front of a committee."""
            who = self.authorise(request, "report:read")
            return self.guard(lambda: self.ctx["saved_views"].save(
                body.name, body.entity, body.query, self.actor(who),
                description=body.description, shared=body.shared))

        @self.app.get(f"{api}/saved-views/{{view_id}}", tags=["reporting"])
        def run_view(request: Request, view_id: str,
                     limit: Optional[int] = None):
            """Run a saved view **under your scope, not its author's**."""
            who = self.authorise(request, "report:read",
                                 estate_wide="running a saved view")
            return self.guard(lambda: self.ctx["saved_views"].run(
                view_id, self.actor(who), scope=Scope.of(who), limit=limit))

        @self.app.delete(f"{api}/saved-views/{{view_id}}", tags=["reporting"])
        def delete_view(request: Request, view_id: str):
            who = self.authorise(request, "report:read")
            return self.guard(lambda: self.ctx["saved_views"].delete(
                view_id, self.actor(who)))

        # ------------------------------------------------------------- export
        @self.app.get(f"{api}/export-formats", tags=["reporting"])
        def export_formats(request: Request):
            """What is offered, and what is refused with the reason.

            An unexplained absence reads as an oversight and gets raised as one
            every quarter.
            """
            self.authorise(request, "report:read")
            return SavedViews.formats()

        @self.app.post(f"{api}/query/export", tags=["reporting"])
        def export_query(request: Request, body: QueryIn, format: str = "csv"):
            """Serialise a query's rows. Recorded: an export is a disclosure."""
            who = self.authorise(
                request, "report:read",
                estate_wide=f"exporting the {body.entity} entity")
            out = self.guard(lambda: self.ctx["saved_views"].export(
                body.entity, format,
                {"select": body.select, "where": body.where,
                 "order_by": body.order_by, "descending": body.descending,
                 "limit": body.limit},
                self.actor(who), scope=Scope.of(who)))
            return Response(
                out["bytes"], media_type=out["media_type"],
                headers={"Content-Disposition":
                         f'attachment; filename="{out["filename"]}"',
                         "X-Rows": str(out["rows"]),
                         "X-Outside-Scope": str(out["outside_scope"]),
                         "X-Truncated": str(out["truncated"]).lower()})

        # -------------------------------------------------- regulatory returns
        @self.app.get(f"{api}/regulatory-returns", tags=["reporting"])
        def returns_catalogue(request: Request):
            """Every return, and which of its fields the register cannot answer.

            Published before anybody runs one, so the gaps are known in advance
            rather than found in the output.
            """
            self.authorise(request, "report:read")
            return RegulatoryReturns.catalogue()

        @self.app.get(f"{api}/regulatory-returns/{{name}}", tags=["reporting"])
        def regulatory_return(request: Request, name: str,
                              now: Optional[float] = None):
            """Extract one return.

            MAYA extracts and does not file. A field the register cannot answer
            comes back empty and named in the header — a plausible value in a
            box nobody knew the answer to is the one output here that goes to a
            supervisor.
            """
            who = self.authorise(
                request, "report:read",
                estate_wide=f"extracting the {name} return over the estate")
            return self.guard(lambda: self.ctx["regulatory_returns"].extract(
                name, now=now, scope=Scope.of(who)))

        # ------------------------------------------------ asking in English
        @self.app.get(f"{api}/ask/vocabulary", tags=["reporting"])
        def ask_vocabulary(request: Request):
            """What a question may be built from, published before anybody asks."""
            self.authorise(request, "report:read")
            return self.ctx["nl_query"].vocabulary()

        @self.app.post(f"{api}/ask", tags=["reporting"])
        def ask(request: Request, body: AskIn):
            """Translate a question, show the query, and run it if it stands.

            The answer always carries `proposed`. An interface that showed only
            the rows would be one where nobody could tell a misread question
            from a wrong number — and the misread question is far commoner.
            """
            who = self.authorise(request, "report:read",
                                 estate_wide="asking a question of the estate")
            return self.guard(lambda: self.ctx["nl_query"].ask(
                body.question, scope=Scope.of(who), limit=body.limit,
                actor=self.actor(who)))

        @self.app.post(f"{api}/ask/translate", tags=["reporting"])
        def translate(request: Request, body: AskIn):
            """The query a question becomes, without running it."""
            self.authorise(request, "report:read")
            return self.guard(
                lambda: self.ctx["nl_query"].translate(body.question))

        # --------------------------------------------------- concentration
        @self.app.get(f"{api}/concentration", tags=["reporting"])
        def concentration(request: Request, urn: Optional[str] = None,
                          now: Optional[float] = None):
            """What several models depend on at once.

            `aggregate_score` is always None and always will be. A network that
            *copies* a dependency and one that *duplicates* it produce
            identical component ratings, so any figure computed from those
            ratings is blind to exactly the thing this exists to find. What
            composes is the order — the worst tier at stake — and not a
            magnitude.
            """
            engine = self.ctx["concentration"]
            if urn is None:
                self.authorise(request, "report:read",
                               estate_wide="scanning the estate for shared "
                                           "dependencies")
                return self.guard(lambda: engine.across_the_estate(now=now))
            model = self.guard(lambda: self.ctx["registry"].require(urn))
            self.authorise(request, "report:read", model=model)
            return self.guard(lambda: engine.of_model(urn, now=now))

        @self.app.get(f"{api}/concentration/single-points", tags=["reporting"])
        def single_points(request: Request, now: Optional[float] = None):
            """What the estate would lose if one thing stopped working.

            Named as a **dependency** rather than asserted as a failure point:
            whether it can fail is a fact about a pipeline, a cluster and an
            on-call rota, and MAYA holds none of the three. Half of the
            judgement is here and the answer says which half.
            """
            self.authorise(request, "report:read",
                           estate_wide="reading the estate's single points of "
                                       "dependency")
            return self.guard(
                lambda: self.ctx["concentration"].single_points_of_failure(
                    now=now))

        # ------------------------------------------------- what it all costs
        @self.app.get(f"{api}/cost", tags=["reporting"])
        def cost_posture(request: Request):
            """What this computes, and the two things it will not claim.

            **It does not observe cost.** MAYA does not run models, so a figure
            it computed would be a price somebody typed multiplied by a call
            count it also did not observe, printed as a measurement.

            **It does not enforce a budget.** MAYA is not on the serving path
            and cannot decline a model's next invocation, so a budget claiming
            to enforce would be claiming a control it has no way to exercise.
            A breach raises a finding, with an owner.
            """
            self.principal(request)
            from core.estate.cost import EstateCost
            return EstateCost.posture()

        @self.app.get(f"{api}/cost/showback", tags=["reporting"])
        def showback(request: Request, by: str = "owner",
                     since: Optional[float] = None,
                     until: Optional[float] = None):
            """The estate's attested cost, cut by a dimension the register knows.

            Read `unattributed_share` first. It is the number this exists to
            produce: a bill is complete by construction, so a cost nobody has
            tied to a registered model looks exactly like an attributed one
            until somebody asks who owns it. The total is available from the
            bill and nobody needs a governance register to add it up.

            Currencies are **not converted**. A total summed across them is
            wrong by the exchange rate, MAYA holds no rate, and the mixture is
            reported rather than flattened into a number somebody would put in
            a board pack.
            """
            self.authorise(request, "report:read",
                           estate_wide="reading estate cost")
            return self.guard(lambda: self.ctx["estate_cost"].showback(
                by, since=since, until=until))

        @self.app.post(f"{api}/cost", status_code=201, tags=["reporting"])
        def record_cost(request: Request, body: CostIn):
            """Take one attested cost figure and attribute it.

            The attribution comes from the **register** rather than from the
            cost record: a cost attributed by whoever produced the bill is
            attributed to whatever they thought the ownership was.

            A line naming no model, or naming one that is not registered,
            lands `unattributed` rather than being refused. That line is the
            finding, and refusing it would delete the finding.
            """
            who = self.authorise(request, "report:read",
                                 estate_wide="recording estate cost")
            return self.guard(lambda: self.ctx["estate_cost"].record(
                amount=body.amount, currency=body.currency,
                period_start=body.period_start, period_end=body.period_end,
                source=body.source, urn=body.urn, reference=body.reference,
                actor=self.actor(who)))

        @self.app.post(f"{api}/cost/budgets", tags=["reporting"])
        def against_budget(request: Request, body: BudgetIn):
            """Compare attested cost with declared budgets.

            **Nothing is blocked and nothing will be.** What a breach does is
            raise a finding with an owner, through the register that already
            does that — weaker than a hard stop, and what is true.
            """
            who = self.authorise(request, "report:read",
                                 estate_wide="comparing cost with budgets")
            return self.guard(lambda: self.ctx["estate_cost"].against_budget(
                body.budgets, body.by, since=body.since, until=body.until,
                raise_findings=body.raise_findings, actor=self.actor(who)))
