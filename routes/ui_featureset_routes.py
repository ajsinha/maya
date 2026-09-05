"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The screens for composing a featureset and filling its slots.

Split out of `ui_routes.py` rather than added to it. That file holds the pages
that *read* the register; these author into it, and the two have different
failure modes — a read page that breaks shows nothing, an authoring page that
breaks writes something wrong.

**These screens decide nothing.** Every refusal a user sees here is the API's,
rendered; nothing about whether an act is permitted is computed in the browser
or in this module. A page that made a governance decision locally would be a
second implementation of a rule, and a second implementation disagrees with the
first eventually, in the direction of permitting more — because that is the
direction in which nobody files a bug.

## The whole algebra, and where each part is answered

Six screens, in the order somebody uses them:

``/featuresets/author``
    Compose. Everything typed goes to ``POST /featuresets/preview`` on every
    keystroke, and the *Declare* button is enabled by that call returning 200
    and by nothing else.

``/featureset/{name}/bind``
    Fill the schema and publish a version; seal; roll forward. There is no dry
    run for bindings — the platform previews the composition and none of the
    filling — so the publish is the check, and the page says so rather than
    claiming a verdict it cannot get. A refused publish writes nothing.

``/featureset/{name}/plan/{version}``
    What an execution engine reads: the pinned namespaces and Delta versions,
    the point-in-time rule, the slots and what fills each.

``/featureset/{name}/assemble``
    Build a training set from a pinned version and read back both layers of the
    point-in-time verification, including what layer 2's independent
    recomputation disagreed about.

``/featureset/{name}/refusals``
    The refusals this object exists for — leakage however many hops away, an
    unfilled slot, a schema a wider model cannot consume — answered live for
    this featureset by the code that enforces them.

``/featuresets/lattice``
    ``refines``, ``meet`` and ``join`` over any two schemas in the register.
    The order underneath featureset satisfaction, `L-W10`, and `L-12`.

## Two things this module computes, and why that is not a second implementation

The lattice page and the schema half of the refusals page call
``core.domain.lattice`` and ``FeatureRegistry.featureset_satisfies`` directly,
because **there is no HTTP endpoint for either** — the platform answers *does
this featureset provide what that kernel reads* only as a side effect of issuing
a fit warrant, which writes. Calling the one implementation from a page is the
same thing `Routes.may_view` does with the authorisation policy: one rule, asked
from two places. It is not the same thing as reimplementing the rule in
JavaScript, and the distinction is the whole of the discipline.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from fastapi import Request
from fastapi.responses import HTMLResponse

from core.domain.lattice import NoMeet, TOP, join, meet, provides, refines, schema_of
from core.domain.schemas import Schema
from core.features import policy as retrieval_policy
from core.features.alignment import RULES as ALIGN_RULES, RULE_MEANING, LOOKS_AHEAD
from core.features.composition import describe as describe_composition
from core.features.normalisation import METHODS, METHOD_MEANING
from core.features.preparation import STRATEGIES, STRATEGY_MEANING
from core.features.sets import PIT_RULE
from core.log import get_logger, swallowed
from routes.base import Routes, login_required

logger = get_logger(__name__)

#: How many rows of a pinned namespace the assembly page shows. Enough to build
#: a spine against real entities and to see the two clocks that decide what the
#: point-in-time rule admits; not enough to be a data export, which is what the
#: bulk endpoints on the plan page are for.
SAMPLE_ROWS = 25


class FeaturesetAuthoringRoutes(Routes):
    def register(self) -> None:
        # ---------------------------------------------------------- compose
        @self.app.get("/featuresets/author", response_class=HTMLResponse,
                      tags=["ui"])
        def define_page(request: Request):
            """Compose a featureset, and see what it would resolve to first.

            The composition half is previewable and the identifying half is not:
            `/featuresets/preview` takes slots, parents, operations and defaults
            and refuses exactly what `define` refuses about them, but it never
            sees the name, the label slot or the outcome window. So the button
            follows the preview, and the page says plainly which refusals it
            cannot show you until you press it.
            """
            if (r := login_required(request)) is not None:
                return r
            if not self.may_view(request, "featureset:define"):
                return self.refused_page(request, "Declaring a featureset")
            features = self.ctx["features"]
            return self.page(
                request, "featureset_author_define.html",
                featuresets=self._declared(features),
                catalogue=self._catalogue(features),
                dtypes=self._dtypes(features),
                retrieval=self._retrieval(),
                composition=describe_composition())

        # ------------------------------------------------------------- fill
        @self.app.get("/featureset/{name}/bind", response_class=HTMLResponse,
                      tags=["ui"])
        def bind_page(request: Request, name: str):
            """Bind each slot to a feature, and publish a version.

            The page shows which views carry each feature because the platform
            refuses an ambiguous binding rather than guessing at one, and a
            person cannot name the view they meant without knowing there are
            two. It lists them; it does not choose between them.
            """
            if (r := login_required(request)) is not None:
                return r
            features = self.ctx["features"]
            if (missing := self._absent(request, features, name)) is not None:
                return missing
            if not self.may_view(request, "featureset:publish"):
                return self.refused_page(request, f"Publishing {name}")
            featureset = features.sets.resolved(name)
            versions = features.sets.versions_of(name)
            return self.page(
                request, "featureset_author_bind.html",
                featureset=featureset, versions=versions,
                latest=versions[-1] if versions else None,
                plans={v["version"]: features.featureset_plan(name, v["version"])
                       for v in versions},
                restatements={v["version"]: features.restatements(name, v["version"])
                              for v in versions},
                catalogue=self._catalogue(features),
                supply=self._supply(features),
                # Sealing is a second-line act and publishing is a first-line
                # one, so the person filling the schema usually may not seal it.
                # Offering the button anyway would be an inert control, and an
                # inert control teaches somebody that the platform is broken.
                may_seal=int(self.may_view(request, "featureset:seal")),
                pit_rule=PIT_RULE)

        # ------------------------------------------------------------- plan
        @self.app.get("/featureset/{name}/plan/{version}",
                      response_class=HTMLResponse, tags=["ui"])
        def plan_page(request: Request, name: str, version: int):
            """The document an execution engine reads, rendered for a reviewer.

            It exists as a page because the pin is the part a reviewer has to
            check and the part they cannot see anywhere else: a namespace
            without a Delta version is a path, and a path is mutable.
            """
            if (r := login_required(request)) is not None:
                return r
            features = self.ctx["features"]
            if (missing := self._absent(request, features, name)) is not None:
                return missing
            if not self.may_view(request, "feature:read"):
                return self.refused_page(request, f"The featureset {name}")
            versions = features.sets.versions_of(name)
            row = next((v for v in versions if v["version"] == version), None)
            if row is None:
                return self.page(request, "not_found.html", http_status=404,
                                 name=f"{name} v{version}")
            previous = next((v for v in versions if v["version"] == version - 1),
                            None)
            return self.page(
                request, "featureset_author_plan.html",
                featureset=features.sets.resolved(name),
                plan=features.featureset_plan(name, version),
                version=row, versions=versions,
                moved=features.sets.diff(previous, row) if previous else None,
                previous=previous,
                attachments=self._attachments(request, row["id"]),
                restatements=features.restatements(name, version))

        # --------------------------------------------------------- assemble
        @self.app.get("/featureset/{name}/assemble", response_class=HTMLResponse,
                      tags=["ui"])
        def assemble_page(request: Request, name: str, version: int = 0):
            """Assemble a point-in-time-correct training set, and read the proof.

            The set supplies the columns and the pins; the caller supplies the
            spine and the `as_of`. That division is the whole design, and it is
            also why this page shows the rows already in the pinned namespaces:
            a spine invented against entities that do not exist assembles a
            table of nulls and teaches nobody what the bound does.
            """
            if (r := login_required(request)) is not None:
                return r
            features = self.ctx["features"]
            if (missing := self._absent(request, features, name)) is not None:
                return missing
            if not self.may_view(request, "feature:assemble"):
                return self.refused_page(request, f"Assembling from {name}")
            versions = features.sets.versions_of(name)
            chosen = (next((v for v in versions if v["version"] == version), None)
                      if version else (versions[-1] if versions else None))
            plan = (features.featureset_plan(name, chosen["version"])
                    if chosen else None)
            return self.page(
                request, "featureset_author_assemble.html",
                featureset=features.sets.resolved(name),
                versions=versions, chosen=chosen, plan=plan,
                rows=self._sample(features, plan) if plan else {},
                snapshots=self._snapshots(features, name),
                pit_rule=PIT_RULE)

        # --------------------------------------------------------- refusals
        @self.app.get("/featureset/{name}/refusals", response_class=HTMLResponse,
                      tags=["ui"])
        def refusals_page(request: Request, name: str):
            """What this featureset refuses, answered live rather than described.

            Each answer comes from the code that enforces it — the leakage
            closure from `derived.dependants_of`, the schema comparison from
            `featureset_satisfies`, which is `core.domain.lattice.refines`. This
            module supplies the question and renders the answer.
            """
            if (r := login_required(request)) is not None:
                return r
            features = self.ctx["features"]
            if (missing := self._absent(request, features, name)) is not None:
                return missing
            if not self.may_view(request, "feature:read"):
                return self.refused_page(request, f"The featureset {name}")
            featureset = features.sets.resolved(name)
            versions = features.sets.versions_of(name)
            latest = versions[-1] if versions else None
            return self.page(
                request, "featureset_author_refusals.html",
                featureset=featureset, latest=latest,
                leakage=self._leakage(features, featureset, latest),
                unfilled=self._unfilled(features, featureset, latest),
                consumers=self._consumers(request, features, name),
                blind_spot=self._schema_blind_spot(features, name),
                supply=self._supply(features))

        # ---------------------------------------------------------- lattice
        @self.app.get("/featuresets/lattice", response_class=HTMLResponse,
                      tags=["ui"])
        def lattice_page(request: Request, left: str = "", right: str = ""):
            """`refines`, `meet` and `join` over two schemas in the register.

            One order sits under featureset satisfaction (`L-W10`), version
            substitutability (`L-12`) and typed composition, and it is written
            once in `core.domain.lattice`. Meet and join had no caller in the
            platform at all before this page: the structure was asserted in the
            law tests and unavailable to anybody deciding whether one featureset
            could serve two models. That question is exactly a meet.
            """
            if (r := login_required(request)) is not None:
                return r
            if not self.may_view(request, "feature:read"):
                return self.refused_page(request, "The schema lattice")
            operands = self._operands(request)
            by_key = {o["key"]: o for o in operands}
            a, b = by_key.get(left), by_key.get(right)
            return self.page(
                request, "featureset_author_lattice.html",
                operands=operands, left=a, right=b,
                comparison=self._compare(a, b) if a and b else None,
                fold=self._fold(left, right),
                composition=describe_composition())

    # -------------------------------------------------------------- plumbing
    def _absent(self, request: Request, features, name: str):
        """A 404 page when there is no such featureset, otherwise None.

        Returned rather than raised because these are pages: a browser asking
        for a featureset that does not exist wants the not-found page, not a
        JSON problem document.
        """
        if features.sets is None or features.sets.get(name) is None:
            return self.page(request, "not_found.html", http_status=404,
                             name=name)
        return None

    # ------------------------------------------------------------- the register
    @staticmethod
    def _declared(features) -> List[Dict[str, Any]]:
        """Every featureset, with enough of its state to link into the flow."""
        if features.sets is None:
            return []
        rows = []
        for row in features.sets.list():
            versions = features.sets.versions_of(row["name"])
            rows.append({**features.sets.resolved(row["name"]),
                         "versions": versions,
                         "latest": versions[-1] if versions else None})
        return rows

    @staticmethod
    def _catalogue(features) -> List[Dict[str, Any]]:
        """The features a slot may be bound to, with what a binder has to know.

        A derived feature is flagged and its lineage carried, because a derived
        feature is the one that can leak: a primitive cannot be computed from
        the label, and a derivation of a derivation of the label still is.
        """
        derived = features.derived
        out = []
        for row in features.list_features():
            name = row["name"]
            is_derived = bool(derived and derived.is_derived(name))
            out.append({"name": name, "dtype": row.get("dtype"),
                        "entity": row.get("entity"),
                        "description": row.get("description", ""),
                        "certification": row.get("certification", "experimental"),
                        "derived": int(is_derived),
                        "rests_on": (sorted(derived.lineage(name))
                                     if is_derived else [])})
        return out

    @staticmethod
    def _dtypes(features) -> List[str]:
        """The types actually present in the catalogue.

        Offered rather than invented: a slot's type must equal its feature's
        exactly, so a list of types nothing in the register carries is a list of
        slots nothing can fill.
        """
        return sorted({row.get("dtype") for row in features.list_features()
                       if row.get("dtype")})

    @staticmethod
    def _retrieval() -> Dict[str, Any]:
        """What a default retrieval policy may say, from the code that checks it.

        A screen holding its own list of fill strategies is a second list, and
        the copy is the one that drifts — the placeholder on the older
        featuresets page offers `flat_forward` as a fill strategy, which is an
        alignment rule, so the example it teaches is refused.
        """
        return {
            "sections": list(retrieval_policy.SECTIONS),
            "fill": [{"value": s, "means": STRATEGY_MEANING[s]} for s in STRATEGIES],
            "normalise": [{"value": m, "means": METHOD_MEANING[m]} for m in METHODS],
            "align": [{"value": r, "means": RULE_MEANING[r],
                       "point_in_time_safe": int(r not in LOOKS_AHEAD)}
                      for r in ALIGN_RULES],
            "precedence": "parents left to right, then the object, then the "
                          "request; the rightmost wins",
        }

    @staticmethod
    def _supply(features) -> Dict[str, List[Dict[str, Any]]]:
        """feature -> the materialised view versions carrying it.

        The same rows `_locate` reads when a binding does not name a view. It is
        listed, not resolved: where two views carry one feature the platform
        refuses the binding and asks for a name, and a screen that picked for
        the user would be choosing which bytes a model trains on.
        """
        supply: Dict[str, List[Dict[str, Any]]] = {}
        for view in features.views.views.many():
            for version in features.views.versions_of(view["name"]):
                namespace = features.views.namespace_of(view, version["version"])
                for feature in version.get("features") or []:
                    supply.setdefault(feature, []).append(
                        {"view": view["name"], "version": version["version"],
                         "namespace": namespace,
                         "delta_version": version.get("delta_version"),
                         "rows": version.get("row_count")})
        return supply

    def _attachments(self, request: Request,
                     subject_id: str) -> List[Dict[str, Any]]:
        """Documents filed against this featureset version.

        The register can hold them — `attach` takes a `subject_type` and a
        `subject_id`, and a featureset version is exactly the case its docstring
        names — but the listing endpoint is addressed by model URN, so there is
        no way to ask *what is filed against this subject* over HTTP. Read here
        from the same register the API reads, and reported as a gap.
        """
        register = self.ctx.get("attachments")
        if register is None:
            return []
        try:
            rows = register.attachments.many(subject_id=subject_id)
        except (KeyError, TypeError, AttributeError) as exc:
            swallowed(logger, exc, "listed documents filed against a featureset "
                                   "version",
                      detail=f"subject {subject_id}; the page renders without "
                             f"the attachment card rather than failing, because "
                             f"the plan is what the page is for",
                      level=logging.INFO)
            return []
        return sorted(rows, key=lambda r: r.get("attached_at") or 0)

    # ---------------------------------------------------------------- refusals
    @staticmethod
    def _leakage(features, featureset: Dict[str, Any],
                 latest: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Which features cannot fill any other slot, because they read the label.

        The closure, not the immediate inputs: `dependants_of` is the inverse of
        the `depends_on` that `refuse_if_reads` calls, over the same lineage, so
        what is listed here is exactly what a publish would refuse — including
        the case people disbelieve, where the leak is three derivations away and
        no expression mentions the label at all.
        """
        slot = featureset.get("label_slot")
        if not slot:
            return {"label_slot": None}
        bound = ((latest or {}).get("bindings") or {}).get(slot) or {}
        label_feature = bound.get("feature")
        refused = []
        if label_feature and features.derived:
            for name in features.derived.dependants_of(label_feature):
                refused.append({"feature": name,
                                "hops": len(features.derived.lineage(name)),
                                "rests_on": sorted(features.derived.lineage(name))})
        return {"label_slot": slot, "feature": label_feature,
                "refused": refused,
                "outcome_window_days": featureset.get("outcome_window_days")}

    @staticmethod
    def _unfilled(features, featureset: Dict[str, Any],
                  latest: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Each slot, whether the newest version fills it, and what could.

        `candidates` is the catalogue filtered to the slot's own type, which is
        a listing rather than a decision — the type check that refuses a
        mismatch runs in `sets.publish`, on the feature the person chose.
        """
        bindings = (latest or {}).get("bindings") or {}
        rows = []
        for slot, spec in sorted(featureset["slots"].items()):
            rows.append({
                "slot": slot, "dtype": spec.get("dtype"),
                "nullable": int(bool(spec.get("nullable"))),
                "filled": int(slot in bindings),
                "feature": (bindings.get(slot) or {}).get("feature"),
                "candidates": sorted(row["name"] for row in features.list_features()
                                     if row.get("dtype") == spec.get("dtype")),
                "inherited": int(slot in (featureset.get("inherited_slots") or []))})
        return rows

    def _consumers(self, request: Request, features,
                   name: str) -> List[Dict[str, Any]]:
        """Which model versions this featureset can and cannot be fitted from.

        Law L-W10, asked here rather than waited for: a fit warrant naming a set
        that does not provide what the kernel declares it reads is refused with
        `schema_not_satisfied`, and until now the only way to find that out was
        to try to issue one. The verdict is `featureset_satisfies`, which is
        `core.domain.lattice.refines` — the same comparison the warrant service
        makes and the same one L-12 makes when a version replaces another.

        Scoped by the rule the API applies, because the answer names the model
        versions somebody may see.
        """
        rows = []
        for model, version in self._visible_versions(request):
            declared = version.get("input_schema") or []
            if not declared:
                continue
            holds, missing = features.featureset_satisfies(
                name, schema_of({f["name"]: f for f in declared}))
            rows.append({"model": model["name"], "urn": model["urn"],
                         "semver": version["semver"],
                         "holds": int(holds), "missing": list(missing),
                         "reads": [f["name"] for f in declared]})
        return rows

    @staticmethod
    def _schema_blind_spot(features, name: str) -> List[str]:
        """Slots this featureset resolves to that `L-W10` does not look at.

        **Expected to be empty, and kept because it was not.**

        `FeaturesetRegistry.schema` used to build the comparison from the
        featureset's own row while `publish` filled the resolved schema, so a
        set composed from parents resolved to a full schema, published versions
        that filled it, and then satisfied no kernel at all — refused
        `schema_not_satisfied` for slots it demonstrably had. This page reported
        the gap rather than papering over it, and `schema()` now resolves.

        The check stays. It costs one comparison, it is the cheapest possible
        guard against the two readings drifting apart again, and a page that
        stops asking is a page that would not notice.
        """
        resolved = features.sets.resolved(name)
        seen = {field.name for field in features.sets.schema(name).fields}
        label = resolved.get("label_slot")
        return sorted(set(resolved["slots"]) - seen - ({label} if label else set()))

    def _visible_versions(self, request: Request) -> List[Tuple[dict, dict]]:
        """Every (model, version) the signed-in person may see."""
        registry = self.ctx["registry"]
        who = self.page_principal(request)
        if who is None:
            return []
        return [(model, version)
                for model in self.ctx["authz"].visible(who, registry.list())
                for version in registry.versions(model["urn"])]

    # ----------------------------------------------------------- the lattice
    def _operands(self, request: Request) -> List[Dict[str, Any]]:
        """Every schema in the register, as something two of which can be picked.

        Featuresets and model-version input schemas, because those are the two
        kinds of thing the order is ever asked about: *can this set serve that
        kernel*, and *can this set stand in for that one*.
        """
        features = self.ctx["features"]
        out: List[Dict[str, Any]] = []
        for row in (features.sets.list() if features.sets is not None else []):
            name = row["name"]
            # `FeaturesetRegistry.schema` and not the resolved slots, so this
            # page gives the answer the platform ENFORCES rather than a second,
            # kinder one. Where the two differ the page says so; see
            # `_schema_blind_spot`.
            schema = features.sets.schema(name)
            label = features.sets.resolved(name).get("label_slot")
            blind = self._schema_blind_spot(features, name)
            out.append({"key": f"fs:{name}", "kind": "featureset", "name": name,
                        "label": f"featureset {name}",
                        "detail": (f"{len(schema.fields)} slot(s)"
                                   + (f", label {label} excluded" if label else "")
                                   + (f", {len(blind)} inherited and unseen"
                                      if blind else "")),
                        "invisible": blind,
                        "schema": schema})
        for model, version in self._visible_versions(request):
            declared = version.get("input_schema") or []
            if not declared:
                continue
            out.append({"key": f"mv:{model['urn']}@{version['semver']}",
                        "kind": "model version", "name": model["name"],
                        "label": f"{model['name']} {version['semver']} reads",
                        "detail": f"{len(declared)} declared input(s)",
                        "schema": schema_of({f["name"]: f for f in declared})})
        out.append({"key": "top", "kind": "top", "name": "⊤",
                    "label": "⊤ — the empty schema",
                    "detail": "demands nothing, so everything refines it",
                    "schema": TOP})
        return out

    @staticmethod
    def _fields(schema: Schema) -> List[Dict[str, Any]]:
        """A schema as rows a table can render."""
        return [{"name": f.name, "dtype": f.dtype,
                 "nullable": int(f.nullable),
                 "minimum": f.minimum, "maximum": f.maximum}
                for f in schema.fields]

    def _compare(self, a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
        """`refines` both ways, the meet, the join, and the covariant direction.

        Every value here is `core.domain.lattice`'s. The meet is partial and its
        failure is the informative case — two schemas whose shared field holds
        two types have no meet, and the honest answer to *can one featureset
        serve both these models* is then no, with the slot named.
        """
        forward, backward = refines(a["schema"], b["schema"]), refines(b["schema"], a["schema"])
        result: Dict[str, Any] = {
            "forward": {"holds": int(forward.holds), "missing": list(forward.missing),
                        "narrowed": list(forward.narrowed), "reason": forward.reason()},
            "backward": {"holds": int(backward.holds), "missing": list(backward.missing),
                         "narrowed": list(backward.narrowed), "reason": backward.reason()},
            "join": self._fields(join(a["schema"], b["schema"])),
            "provides": list(provides(a["schema"], b["schema"])),
            "equivalent": int(forward.holds and backward.holds),
        }
        try:
            result["meet"] = self._fields(meet(a["schema"], b["schema"]))
            result["no_meet"] = None
        except NoMeet as exc:
            swallowed(logger, exc, "computed the meet of two schemas",
                      detail="the meet is partial by design; a shared field "
                             "holding two dtypes has no greatest lower bound, "
                             "and the page renders the clash rather than an "
                             "empty schema",
                      level=logging.INFO)
            result["meet"] = []
            result["no_meet"] = {
                "conflicts": [{"field": name, "left": left, "right": right}
                              for name, (left, right) in sorted(exc.conflicts.items())],
                "detail": str(exc)}
        # The identity, checked rather than claimed: ⊤ demands nothing, so
        # meeting with it changes nothing and everything refines it.
        result["top_is_identity"] = int(
            self._fields(meet(a["schema"], TOP)) == self._fields(a["schema"])
            and refines(a["schema"], TOP).holds)
        return result

    def _fold(self, left: str, right: str) -> Optional[Dict[str, Any]]:
        """The composition fold, run both ways round, on two real featuresets.

        Associativity and the identity are laws, asserted in
        `tests/test_composition.py` (`L-19`). What a screen can usefully show is
        the part people get wrong: the fold is **not commutative** — the
        rightmost parent wins where two disagree — so composing `[a, b]` and
        `[b, a]` are different featuresets whenever the parents overlap.

        Both answers come from `sets.preview`, which is the same fold `define`
        runs, with nothing written.
        """
        features = self.ctx["features"]
        names = [key[3:] for key in (left, right) if key.startswith("fs:")]
        if len(names) != 2 or features.sets is None:
            return None
        forward = features.sets.preview(composes=[{"name": n} for n in names])
        backward = features.sets.preview(
            composes=[{"name": n} for n in reversed(names)])
        differs = sorted(slot for slot in set(forward["slots"]) | set(backward["slots"])
                         if forward["slots"].get(slot) != backward["slots"].get(slot))
        return {"order": names, "forward": forward["slots"],
                "backward": backward["slots"], "differs": differs}

    # ------------------------------------------------------------- assembly
    def _sample(self, features, plan: Dict[str, Any]) -> Dict[str, Any]:
        """A window onto the bytes each pinned namespace actually holds.

        Read at the pinned Delta version rather than at the namespace's head,
        for the same reason the assembler does: a namespace is a path and a path
        is mutable, so reading the head would show a page that disagrees with
        the assembly it is describing.
        """
        out: Dict[str, Any] = {}
        for namespace, delta_version in {
                (b["namespace"], b.get("delta_version")) for b in plan["slots"]}:
            try:
                frame = features.delta.read(namespace, delta_version)
            except (FileNotFoundError, OSError, ValueError, KeyError) as exc:
                swallowed(logger, exc, "sampled a pinned namespace for the "
                                       "assembly page",
                          detail=f"{namespace} at delta v{delta_version}; the "
                                 f"page renders without the sample rather than "
                                 f"failing, and the assembly itself reads the "
                                 f"same pin",
                          level=logging.WARNING)
                continue
            # Through pandas' own JSON writer rather than `to_dict`, because
            # `to_dict` hands back numpy scalars and a template that renders one
            # is fine while `tojson` on the same value is a TypeError — a page
            # that works until somebody materialises an integer column.
            records = ([] if frame.empty
                       else json.loads(frame.head(SAMPLE_ROWS).to_json(
                           orient="records")))
            out[namespace] = {
                "delta_version": delta_version,
                "columns": [] if frame.empty else list(frame.columns),
                "rows": records,
                "total": 0 if frame.empty else len(frame)}
        return out

    def _snapshots(self, features, name: str) -> List[Dict[str, Any]]:
        """Training sets already assembled from this featureset."""
        try:
            rows = features.snapshots.many(featureset=name)
        except (KeyError, TypeError, AttributeError) as exc:
            swallowed(logger, exc, "listed the training sets built from a "
                                   "featureset",
                      detail=f"featureset {name}; the page renders without the "
                             f"history rather than failing",
                      level=logging.INFO)
            return []
        return sorted(rows, key=lambda r: r.get("created_at") or 0, reverse=True)
