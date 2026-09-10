"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

One call over a chain of models, and the refusal that makes it worth having.

A discount curve feeds a valuation feeds a provision. The caller wants one
authorisation and one answer; the register holds three models, three approvals,
three sets of limitations and three tiers. A composite warrant is the object
that reconciles those — and the reconciliation is almost entirely about what it
**refuses**.

**A chain is as governed as its least governed link.** So a composite resolves
only if every node resolves: one blocked finding anywhere, one revoked grant,
one unapproved version, and the whole composite is refused, naming the node and
the reason. A composite that resolved while one node was blocked would defeat
the entire blast-radius argument — the reason `input_to` edges are tracked at
all is that a change upstream reaches downstream, and an authorisation that
ignored the upstream state would be routing around the only control that knows.

**The composite's tier is the join of its nodes'.** A chain is at least as risky
as its riskiest component, by the same lattice reasoning that governs data
classification: a thing built out of parts is not less risky than its riskiest
part. That is derived and cannot be declared lower.

**There is no single signed descriptor.** This is the design decision that will
be argued with, and it is deliberate: signing one would be MAYA asserting that
the chain *as a whole* is authorised, and nothing established that. Three people
approved three models for three purposes; none of them approved the composition.
What comes back is the nodes in topological order, each with its own descriptor,
each carrying its own limitations — so the caller executes a chain it can
account for rather than a black box the register vouched for.

**Cycles are refused rather than truncated.** A cyclic feeder graph is a model
that reads its own output, and answering with a truncated order would give a
caller a chain that runs and is wrong.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from core.execution.errors import WarrantError
from core.log import get_logger

logger = get_logger(__name__)

#: The edge that means composition. `derives_from` is provenance and
#: `challenger_of` is an argument; neither is a call somebody makes.
COMPOSING = "input_to"

#: A chain longer than this is almost certainly a cycle the edge check missed
#: or a graph nobody understands, and either way is refused rather than walked.
MAX_NODES = 32


class CompositeWarrants:
    """Resolves a DAG of models as one unit, and refuses it as one unit."""

    def __init__(self, registry, composition, warrants):
        self.registry, self.composition = registry, composition
        self.warrants = warrants

    # ------------------------------------------------------------------ shape
    def chain(self, terminal_urn: str) -> Dict[str, Any]:
        """The models feeding a terminal, in the order they must be called."""
        terminal = self.registry.require(terminal_urn)
        order: List[str] = []
        seen: set = set()
        cycle: List[str] = []
        self._walk(terminal, order, seen, [], cycle)
        if cycle:
            raise WarrantError(
                "cyclic_composition",
                "this feeder graph contains a cycle: "
                + " → ".join(cycle),
                "a model that reads its own output has no order to be called "
                "in, and answering with a truncated one would hand a caller a "
                "chain that runs and is wrong")
        if len(order) > MAX_NODES:
            raise WarrantError(
                "composition_too_deep",
                f"{len(order)} models feed {terminal_urn}, past the {MAX_NODES} "
                f"this will walk",
                "a chain this long is a graph nobody understands; resolve the "
                "sub-chains separately so each is somebody's to account for")
        rows = [self.registry.require(urn) for urn in order]
        tiers = [r.get("tier") for r in rows if r.get("tier") is not None]
        return {
            "terminal": terminal_urn,
            "order": order, "nodes": len(order),
            # The join, not the terminal's own. A chain is at least as risky as
            # its riskiest part, and tier 1 is the most severe.
            "tier": min(tiers) if tiers else None,
            "terminal_tier": terminal.get("tier"),
            "untiered": [r["urn"] for r in rows if r.get("tier") is None],
            "detail": self._chain_detail(terminal, rows, tiers),
        }

    def _walk(self, model: Dict[str, Any], order: List[str], seen: set,
              path: List[str], cycle: List[str]) -> None:
        """Depth-first over the feeders, terminal last."""
        if cycle:
            return
        if model["urn"] in path:
            cycle.extend(path[path.index(model["urn"]):] + [model["urn"]])
            return
        if model["urn"] in seen or len(order) > MAX_NODES:
            return
        for edge in self.composition.edges.many(to_model=model["id"]):
            if edge["kind"] != COMPOSING:
                continue
            upstream = self.registry.catalogue.by_id(edge["from_model"])
            if upstream:
                self._walk(upstream, order, seen, path + [model["urn"]], cycle)
        if cycle:
            return
        seen.add(model["urn"])
        order.append(model["urn"])

    @staticmethod
    def _chain_detail(terminal, rows, tiers) -> str:
        if len(rows) == 1:
            return (f"{terminal['urn']} reads no other model's output, so it is "
                    f"not a composition — a composite warrant over one node is "
                    f"an ordinary warrant with extra words")
        out = (f"{len(rows)} model(s) in the chain feeding "
               f"{terminal['urn']}, in call order")
        if tiers and min(tiers) != terminal.get("tier"):
            out += (f". The composite is tier {min(tiers)} while its terminal is "
                    f"tier {terminal.get('tier')}: a chain is at least as risky "
                    f"as its riskiest part, and that is derived rather than "
                    f"declared because the only direction anybody ever wants to "
                    f"move it is down")
        untiered = [r["urn"] for r in rows if r.get("tier") is None]
        if untiered:
            out += (f". {len(untiered)} node(s) carry no tier at all, so the "
                    f"composite's tier is a join over an incomplete set")
        return out

    # ---------------------------------------------------------------- resolve
    def resolve(self, terminal_urn: str, environment: str, principal: str,
                declared_use: str, verb: str = "score",
                now: Optional[float] = None) -> Dict[str, Any]:
        """Resolve every node, or refuse the whole composite naming the one.

        There is no single signed descriptor. Signing one would be MAYA
        asserting the chain **as a whole** is authorised, and nothing
        established that: three people approved three models for three
        purposes, and none of them approved the composition.
        """
        shape = self.chain(terminal_urn)
        moment = now if now is not None else time.time()
        descriptors, refusals = [], []
        for urn in shape["order"]:
            try:
                descriptors.append({
                    "urn": urn,
                    "descriptor": self.warrants.resolve(
                        urn, environment, principal, declared_use, verb=verb)})
            except WarrantError as refused:
                # Collected, not raised here: a caller told only about the
                # first refusal fixes it, retries, and is told about the
                # second. A chain with three problems takes three round trips
                # to discover, and each one looks like a new failure.
                logger.info("composite over %s refused at %s: %s",
                            terminal_urn, urn, refused.code)
                refusals.append({"urn": urn, "error": refused.code,
                                 "detail": refused.detail,
                                 "remediation": refused.remediation})
        if refusals:
            raise WarrantError(
                "composite_refused",
                f"{len(refusals)} of {shape['nodes']} node(s) in the chain "
                f"feeding {terminal_urn} refuse: "
                + "; ".join(f"{r['urn']} — {r['detail']}" for r in refusals),
                "a chain is as governed as its least governed link, so the "
                "composite refuses as one unit. Every refusing node is named "
                "here rather than one at a time, because a caller told only "
                "about the first fixes it, retries and discovers the second")
        logger.info("composite over %s resolved %d node(s) for %s",
                    terminal_urn, len(descriptors), principal)
        return {
            "terminal": terminal_urn, "environment": environment,
            "principal": principal, "declared_use": declared_use,
            "resolved_at": moment,
            "order": shape["order"], "nodes": descriptors,
            "tier": shape["tier"],
            "composite_descriptor": None,
            "detail": (
                f"{len(descriptors)} node(s) resolved, each with its own signed "
                f"descriptor and its own limitations, in call order. **There is "
                f"no composite descriptor and that is deliberate**: signing one "
                f"would be asserting that this chain as a whole is authorised, "
                f"and nothing established that — three approvals were given for "
                f"three models and none of them was for the composition"),
        }

    # ------------------------------------------------------------------ check
    def check(self, terminal_urn: str, environment: str, principal: str,
              declared_use: str) -> Dict[str, Any]:
        """Would this composite resolve? Without issuing anything.

        Worth its own method: the question *can this chain run* is asked far
        more often than the chain is run, and answering it by resolving would
        mint descriptors nobody intends to use.
        """
        try:
            out = self.resolve(terminal_urn, environment, principal,
                               declared_use)
        except WarrantError as refused:
            # Logged at INFO rather than swallowed: a refusal is a governance
            # decision and this is the endpoint people call to find out about
            # one, so the answer carrying it is not a reason for the log not to.
            logger.info("composite check on %s for %s does not resolve: %s",
                        terminal_urn, principal, refused.code)
            return {"terminal": terminal_urn, "resolves": False,
                    "error": refused.code, "detail": refused.detail,
                    "remediation": refused.remediation}
        return {"terminal": terminal_urn, "resolves": True,
                "nodes": len(out["nodes"]), "order": out["order"],
                "tier": out["tier"],
                "detail": f"every node in this chain resolves for {principal}"}

    # ----------------------------------------------------------------- estate
    def across_the_estate(self) -> Dict[str, Any]:
        """Every terminal that has a chain behind it."""
        rows = []
        for model in self.registry.list():
            upstream = [e for e in
                        self.composition.edges.many(to_model=model["id"])
                        if e["kind"] == COMPOSING]
            if not upstream:
                continue
            try:
                rows.append(self.chain(model["urn"]))
            except WarrantError as refused:
                logger.warning("chain behind %s cannot be walked: %s",
                               model["urn"], refused.code)
                rows.append({"terminal": model["urn"], "order": [],
                             "nodes": 0, "tier": None,
                             "error": refused.code, "detail": refused.detail})
        rows.sort(key=lambda r: (r.get("tier") or 9, -r["nodes"]))
        broken = [r for r in rows if r.get("error")]
        raised = [r for r in rows
                  if r.get("tier") is not None
                  and r.get("terminal_tier") is not None
                  and r["tier"] < r["terminal_tier"]]
        return {
            "composites": rows, "count": len(rows),
            "tier_raised_by_the_chain": [r["terminal"] for r in raised],
            "unwalkable": [r["terminal"] for r in broken],
            "detail": (
                f"{len(rows)} model(s) read another model's output"
                + (f", and {len(raised)} of them are riskier as a chain than "
                   f"the register records them individually — which is the "
                   f"number a feeder graph exists to produce" if raised else "")
                + (f". {len(broken)} chain(s) cannot be walked at all"
                   if broken else "")
                if rows else
                "no model reads another model's output, so there is nothing to "
                "compose. Worth reading as a fact about the recorded edges "
                "rather than about the estate: a feeder relation nobody entered "
                "is a chain nothing here can see"),
        }
