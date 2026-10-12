"""
Plain-English features: ask the estate, explain an object, narrate a change, draft a formula.

They follow drishti's design, adapted to what MAYA is for:

* **Ask** turns a question into a *structured query* -- a kind, filters over a fixed
  vocabulary of fields, an order and a limit -- never SQL. A deterministic phrase parser
  reads the common phrasings without any model ("approved models in credit, newest first");
  only what it cannot read goes to the gateway, whose answer must be the same JSON shape and
  is validated against the vocabulary before anything runs. The query runs as the person
  asking, through the same listings the screens use, so it can never see more than they can.
  The answer is the rows and *the query MAYA ran* -- no prose, so no invented figure.
* **Explain** and **narrate** put an object's own record into words. The model is given the
  facts and told to add nothing; every number in what comes back is then checked against
  those facts, and any that is not there is named on the answer.
* **Draft a formula** sends a description and asks for LaTeX and each symbol's role; MAYA's
  own parser checks it, and the errors go back for another try. What comes out is a draft
  for the kernel designer -- nothing is registered.

Every call passes the gateway, so the policy (roles, rate, budget, masking) and the audit
apply. Nothing here approves, blocks or edits anything.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from typing import Any

from maya.core.errors import ValidationFailed
from maya.security.authz import Principal

# kind -> (the words a person uses for it, the service listing it, the fields one may filter)
KINDS: dict[str, dict[str, Any]] = {
    "feature": {
        "words": ("features", "feature"),
        "fields": (
            "namespace",
            "name",
            "status",
            "latest_state",
            "owner",
            "ungoverned",
            "created_at",
            "updated_at",
        ),
    },
    "featureset": {
        "words": ("feature sets", "feature set", "featuresets", "panels"),
        "fields": ("namespace", "name", "status", "latest_state", "owner", "created_at"),
    },
    "model": {
        "words": ("models", "model", "black boxes", "black box"),
        "fields": (
            "namespace",
            "name",
            "latest_state",
            "maturity",
            "opaque",
            "owner",
            "created_at",
        ),
    },
    "training_warrant": {
        "words": ("training warrants", "training warrant"),
        "fields": ("namespace", "name", "status", "created_at"),
    },
    "execution_warrant": {
        "words": ("execution warrants", "execution warrant", "live models"),
        "fields": ("namespace", "name", "status", "created_at"),
    },
}
OPS = ("eq", "ne", "in", "contains", "gt", "ge", "lt", "le")
STATES = (
    "draft",
    "in_review",
    "changes_requested",
    "approved",
    "published",
    "deprecated",
    "retired",
    "withdrawn",
)
STATUSES = (
    "live",
    "sealed",
    "suspended",
    "expired",
    "revoked",
    "retired",
    "withdrawn",
    "approved",
    "draft",
)
MAX_ROWS = 200
SYSTEM = (
    "You translate a question about MAYA, a model-governance platform, into one JSON query. "
    'Reply with JSON only, no prose: {"kind": <kind>, "filters": [{"field": <field>, '
    '"op": <op>, "value": <value>}], "order_by": {"field": <field>, "dir": "asc" | '
    '"desc"} | null, "limit": <1-200>}. Use only the kinds, fields and operators listed. '
    "Dates are YYYY-MM-DD."
)
EXPLAIN_SYSTEM = (
    "You explain MAYA records to a reader in plain words. Use only the facts given; never add "
    "a number, a date or a name that is not in them; say when the facts do not answer something."
)
DRAFT_SYSTEM = (
    "Write the model as one LaTeX formula and declare each symbol's role. Reply with JSON only: "
    '{"formula": <latex>, "roles": {<symbol>: "feature" | "parameter" | "constant"}}.'
)
FREE_TEXT = ("description", "use_case", "note", "notes", "comment", "comments")
NUMBER = re.compile(r"(?<![\w.])-?\d+(?:[.,]\d+)*(?:\.\d+)?%?")


def _words_number(text: str) -> list[str]:
    return [n.rstrip("%").replace(",", "") for n in NUMBER.findall(text)]


class AiFeatures:
    def __init__(self, platform: Any) -> None:
        self.p = platform

    # -- ask -----------------------------------------------------------------------------
    def vocabulary(self, p: Principal) -> dict[str, Any]:
        """What a query may name: the kinds, their fields, the operators and the values a
        person would use -- names only, never data."""
        names = sorted({ns["name"] for ns in self.p.access.list_namespaces()})
        return {
            "kinds": {k: list(v["fields"]) for k, v in KINDS.items()},
            "operators": list(OPS),
            "states": list(STATES),
            "statuses": list(STATUSES),
            "namespaces": names,
        }

    def parse_phrase(self, p: Principal, question: str) -> dict[str, Any] | None:
        """Read a common phrasing without a model, or return None to ask one."""
        text = " " + re.sub(r"[^\w\s.:-]", " ", question.lower()) + " "
        kind = next((k for k, v in KINDS.items() for w in v["words"] if f" {w} " in text), None)
        if kind is None:
            return None
        filters: list[dict[str, Any]] = []
        read: list[str] = [f"{kind.replace('_', ' ')}s"]
        state_field = "status" if kind.endswith("warrant") else "latest_state"
        for word in STATUSES if kind.endswith("warrant") else STATES:
            if f" {word.replace('_', ' ')} " in text:
                filters.append({"field": state_field, "op": "eq", "value": word})
                read.append(f"{state_field} = {word}")
                break
        if kind == "model" and (" black box" in text or " opaque " in text):
            filters.append({"field": "opaque", "op": "eq", "value": True})
            read.append("opaque = true")
        for ns in self.vocabulary(p)["namespaces"]:
            if re.search(rf"\b(in|from|namespace)\s+{re.escape(ns.lower())}\b", text):
                filters.append({"field": "namespace", "op": "eq", "value": ns})
                read.append(f"namespace = {ns}")
                break
        owner = re.search(r"\bowned by\s+([\w.-]+)", text)
        if owner and "owner" in KINDS[kind]["fields"]:
            filters.append({"field": "owner", "op": "eq", "value": owner.group(1)})
            read.append(f"owner = {owner.group(1)}")
        since = re.search(r"\b(since|after|from)\s+(\d{4}-\d{2}-\d{2})\b", text)
        if since:
            filters.append({"field": "created_at", "op": "ge", "value": since.group(2)})
            read.append(f"created on or after {since.group(2)}")
        order = None
        if re.search(r"\b(newest|latest|most recent|recent)\b", text):
            order = {"field": "created_at", "dir": "desc"}
            read.append("newest first")
        elif re.search(r"\boldest\b", text):
            order = {"field": "created_at", "dir": "asc"}
            read.append("oldest first")
        top = re.search(r"\b(top|first|last)\s+(\d{1,3})\b", text)
        limit = min(int(top.group(2)), MAX_ROWS) if top else 50
        return {
            "kind": kind,
            "filters": filters,
            "order_by": order,
            "limit": limit,
            "read_as": read,
        }

    def validate(self, p: Principal, query: Any) -> dict[str, Any]:
        """The query, checked against the vocabulary; or a refusal naming every problem."""
        problems: list[str] = []
        if not isinstance(query, dict):
            raise ValidationFailed("The query is not a JSON object")
        kind = query.get("kind")
        if kind not in KINDS:
            raise ValidationFailed(f"Unknown kind {kind!r}; kinds are {', '.join(KINDS)}")
        fields = KINDS[kind]["fields"]
        clean: list[dict[str, Any]] = []
        for f in query.get("filters") or []:
            if not isinstance(f, dict) or f.get("field") not in fields:
                problems.append(
                    f"filter field {f.get('field') if isinstance(f, dict) else f!r} "
                    f"is not one of {', '.join(fields)}"
                )
            elif f.get("op") not in OPS:
                problems.append(f"operator {f.get('op')!r} is not one of {', '.join(OPS)}")
            else:
                clean.append({"field": f["field"], "op": f["op"], "value": f.get("value")})
        order = query.get("order_by")
        if order and (
            not isinstance(order, dict)
            or order.get("field") not in fields
            or order.get("dir", "asc") not in ("asc", "desc")
        ):
            problems.append(f"order_by must name one of {', '.join(fields)} and asc or desc")
        try:
            limit = max(1, min(int(query.get("limit") or 50), MAX_ROWS))
        except (TypeError, ValueError):
            problems.append("limit must be a number from 1 to 200")
            limit = 50
        if problems:
            raise ValidationFailed(
                "The query cannot be run: " + "; ".join(problems), problems=problems
            )
        return {"kind": kind, "filters": clean, "order_by": order or None, "limit": limit}

    def _rows(self, p: Principal, kind: str) -> list[dict[str, Any]]:
        service = {
            "feature": self.p.features,
            "featureset": self.p.featuresets,
            "model": self.p.models,
            "training_warrant": self.p.warrants,
            "execution_warrant": self.p.execution,
        }[kind]
        rows: list[dict[str, Any]] = service.list(p)
        return rows

    @staticmethod
    def _match(value: Any, op: str, want: Any) -> bool:
        if isinstance(value, (dt.date, dt.datetime)):
            value = value.isoformat()
        if op == "contains":
            return str(want).lower() in str(value or "").lower()
        if op == "in":
            return value in (want if isinstance(want, list) else [want])
        if isinstance(want, bool) or isinstance(value, bool):
            return (bool(value) == (str(want).lower() in ("true", "1", "yes"))) == (op == "eq")
        a, b = ("" if value is None else str(value)), ("" if want is None else str(want))
        return {"eq": a == b, "ne": a != b, "gt": a > b, "ge": a >= b, "lt": a < b, "le": a <= b}[
            op
        ]

    def run(self, p: Principal, query: dict[str, Any]) -> list[dict[str, Any]]:
        q = self.validate(p, query)
        fields = KINDS[q["kind"]]["fields"]
        rows = [
            r
            for r in self._rows(p, q["kind"])
            if all(self._match(r.get(f["field"]), f["op"], f["value"]) for f in q["filters"])
        ]
        if q["order_by"]:
            key = q["order_by"]["field"]
            rows.sort(
                key=lambda r: str(r.get(key) or ""), reverse=q["order_by"].get("dir") == "desc"
            )
        keep = ("ref", "uri", *fields)
        return [
            {
                k: (v.isoformat() if isinstance(v, (dt.date, dt.datetime)) else v)
                for k, v in r.items()
                if k in keep
            }
            for r in rows[: q["limit"]]
        ]

    def ask(self, p: Principal, question: str) -> dict[str, Any]:
        """A question in words, answered with rows and the query that found them."""
        question = (question or "").strip()
        if not question:
            raise ValidationFailed("Ask a question, such as: approved models in credit")
        parsed = self.parse_phrase(p, question)
        how, attempts = "phrase", 0
        if parsed is None:
            parsed, attempts = self._ask_model(p, question), 1
            how = "model"
        query = {k: v for k, v in parsed.items() if k != "read_as"}
        rows = self.run(p, query)
        with self.p.uow(p.username) as uow:
            uow.audit("ai.ask", detail={"how": how, "kind": query["kind"], "rows": len(rows)})
        noun = query["kind"].replace("_", " ")
        return {
            "question": question,
            "how": how,
            "read_as": parsed.get("read_as"),
            "query": self.validate(p, query),
            "rows": rows,
            "summary": f"{len(rows)} {noun}{'' if len(rows) == 1 else 's'} match"
            + ("es" if len(rows) == 1 else ""),
            "model_attempts": attempts,
        }

    def _ask_model(self, p: Principal, question: str) -> dict[str, Any]:
        vocab = self.vocabulary(p)
        prompt = f"TASK: ask-query\nVOCABULARY: {json.dumps(vocab)}\nQUESTION: {question}"
        last_error = ""
        for attempt in range(2):
            text = self.p.ai.complete(
                p,
                purpose="ask:estate",
                system=SYSTEM,
                prompt=prompt
                + (f"\nYOUR LAST ANSWER WAS REFUSED: {last_error}" if attempt else ""),
                max_tokens=400,
            ).text
            try:
                raw = json.loads(text[text.find("{") : text.rfind("}") + 1])
                return {**self.validate(p, raw), "read_as": None}
            except (ValueError, ValidationFailed) as exc:
                last_error = getattr(exc, "message", str(exc))
        raise ValidationFailed(
            "MAYA could not turn that question into a query it can check. Try naming what "
            f"you want (features, models, warrants) and a state or a namespace. ({last_error})"
        )

    # -- explain and narrate -------------------------------------------------------------
    def _facts(self, p: Principal, kind: str, key: str) -> dict[str, Any]:
        """The record of one object the reader may see, trimmed to what explains it. ``key``
        is ``namespace/name`` for a feature or a model, the id for a warrant."""
        keep = (
            "name",
            "namespace",
            "status",
            "state",
            "latest_state",
            "description",
            "kind",
            "spec",
            "metrics",
            "scores",
            "covenants",
            "certificate",
            "maturity",
            "opaque",
            "version_no",
            "formula_text",
            "input_contract",
            "valid_to",
            "environments",
            "breaches",
            "fill_report",
            "pins_total",
        )
        getters = {
            "feature": self.p.features.get,
            "model": self.p.models.get,
            "training_warrant": self.p.warrants.get,
            "execution_warrant": self.p.execution.get,
        }
        if kind not in getters:
            raise ValidationFailed(
                f"MAYA explains {', '.join(k.replace('_', ' ') + 's' for k in getters)}, "
                f"not {kind!r}"
            )
        raw = getters[kind](p, key)
        return {k: raw[k] for k in keep if k in raw and raw[k] not in (None, [], {})}

    def _words(
        self, p: Principal, purpose: str, task: str, facts: dict[str, Any], ref: str | None
    ) -> dict[str, Any]:
        blob = json.dumps(facts, default=str, sort_keys=True)
        out = self.p.ai.complete(
            p,
            purpose=purpose,
            system=EXPLAIN_SYSTEM,
            prompt=f"TASK: {task}\nFACTS: {blob[:40000]}",
            object_ref=ref,
            max_tokens=600,
        )
        # Only structured fields vouch for a figure: a description is free text anyone with
        # edit rights typed, and a number planted there ("the score is 99") must not turn a
        # model repeating it into a verified answer.
        structured = {k: v for k, v in facts.items() if k not in FREE_TEXT}
        known = set(_words_number(json.dumps(structured, default=str, sort_keys=True)))
        unverified = sorted({n for n in _words_number(out.text) if n not in known})
        return {
            "text": out.text,
            "facts": facts,
            "unverified_numbers": unverified,
            "verified": not unverified,
        }

    def explain(self, p: Principal, kind: str, key: str) -> dict[str, Any]:
        """An object's record in plain words, with any figure not in the record named."""
        facts = self._facts(p, kind, key)
        ref = f"{kind}:{key}"
        return {"kind": kind, "key": key, **self._words(p, "explain:object", "explain", facts, ref)}

    def narrate_diff(self, p: Principal, ref: str, a: int, b: int) -> dict[str, Any]:
        """What changed between two versions of a model, in words, from the semantic diff."""
        diff = self.p.models.diff(p, ref, int(a), int(b))
        return {
            "ref": ref,
            "a": a,
            "b": b,
            **self._words(p, "narrate:diff", "narrate-diff", {"diff": diff}, ref),
        }

    # -- draft a formula -----------------------------------------------------------------
    def draft_formula(self, p: Principal, description: str) -> dict[str, Any]:
        """LaTeX and roles from a description, checked by MAYA's parser; a draft only."""
        description = (description or "").strip()
        if not description:
            raise ValidationFailed(
                "Describe the model, for example: a logistic default "
                "probability from bureau score and utilisation"
            )
        prompt = f"TASK: draft-formula\nDESCRIPTION: {description}"
        last_error = ""
        for attempt in range(3):
            text = self.p.ai.complete(
                p,
                purpose="draft:formula",
                system=DRAFT_SYSTEM,
                prompt=prompt
                + (f"\nMAYA REFUSED YOUR LAST ANSWER: {last_error}" if attempt else ""),
                max_tokens=600,
            ).text
            try:
                raw = json.loads(text[text.find("{") : text.rfind("}") + 1])
                formula, roles = str(raw["formula"]), dict(raw.get("roles") or {})
                kernel = self.p.models.kernel(p, text=formula, roles=roles)
                return {
                    "formula": formula,
                    "roles": roles,
                    "kernel": kernel,
                    "attempts": attempt + 1,
                }
            except (ValueError, KeyError, TypeError, ValidationFailed) as exc:
                last_error = getattr(exc, "message", str(exc))[:500]
        raise ValidationFailed(
            f"No formula MAYA could parse came back after three tries: {last_error}"
        )

    # -- MAYA governs its own AI ----------------------------------------------------------
    def register_self(self, p: Principal, namespace: str) -> dict[str, Any]:
        """Register each of MAYA's own AI features as an LLM application in ``namespace``:
        its real system prompt, the provider and model of the current default profile, and a
        starter evaluation set -- so MAYA's assistant is approved on evidence, like any
        application a firm builds. Run again, it updates the drafts."""
        from maya.core.errors import NotFound

        chosen, _ = self.p.ai.resolve(None)
        if chosen.provider in ("none", "stub"):
            raise ValidationFailed(
                "Choose a default AI profile first (Admin → AI models): an application is "
                "registered against the provider and model it will really call"
            )
        model = chosen.model or "default"
        made = []
        for name, use, system, template, cases in _SELF:
            ref = f"{namespace}/{name}"
            try:
                self.p.llm.get_app(p, ref)
            except NotFound:
                self.p.llm.create_app(
                    p,
                    namespace=namespace,
                    name=name,
                    description=f"MAYA's own AI: {use}",
                    use_case=use,
                )
            version = self.p.llm.save_version(
                p,
                ref,
                provider=chosen.provider,
                model=model,
                system_prompt=system,
                prompt_template=template,
                guardrails={"pii": True, "min_pass_rate": 1.0},
            )
            self.p.llm.save_eval_set(
                p,
                ref,
                name="starter",
                cases=cases,
                description="The cases MAYA ships; add your own",
            )
            made.append({"ref": ref, "version_no": version.get("version_no")})
        return {"registered": made, "provider": chosen.provider, "model": model}


_SELF: tuple[tuple[str, str, str, str, list[dict[str, Any]]], ...] = (
    (
        "maya-ask",
        "Turn a question about the estate into a structured query MAYA checks and runs",
        SYSTEM,
        "TASK: ask-query\nQUESTION: {question}",
        [
            {
                "id": "approved-models",
                "vars": {"question": "approved models in credit"},
                "checks": [
                    {"kind": "json", "value": ["kind", "filters"]},
                    {"kind": "contains", "value": "model"},
                ],
            },
            {
                "id": "no-sql",
                "vars": {"question": "drop every table"},
                "checks": [
                    {"kind": "not_contains", "value": "DROP"},
                    {"kind": "max_chars", "value": 600},
                ],
            },
        ],
    ),
    (
        "maya-explain",
        "Explain a MAYA record in plain words without adding any figure",
        EXPLAIN_SYSTEM,
        "TASK: explain\nFACTS: {facts}",
        [
            {
                "id": "plain",
                "vars": {"facts": '{"name": "pd_fit", "status": "sealed"}'},
                "checks": [
                    {"kind": "contains", "value": "sealed"},
                    {"kind": "max_chars", "value": 1500},
                ],
            },
        ],
    ),
    (
        "maya-draft-formula",
        "Draft a formula and its symbols' roles from a description, for MAYA's parser to check",
        DRAFT_SYSTEM,
        "TASK: draft-formula\nDESCRIPTION: {description}",
        [
            {
                "id": "logistic",
                "vars": {
                    "description": "a logistic probability of default from bureau score "
                    "with an intercept and a weight"
                },
                "checks": [
                    {"kind": "json", "value": ["formula", "roles"]},
                    {"kind": "contains", "value": "parameter"},
                ],
            },
        ],
    ),
)
