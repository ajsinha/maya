"""
LLM applications under the same discipline as models.

An LLM application is a model whose "formula" is a provider, a model name, a system prompt,
a prompt template, sampling parameters and guardrails. MAYA cannot read the weights, so it
governs what it can pin down:

* **The version is the definition.** Every field that changes behaviour is sealed into a
  definition hash; editing is allowed only in draft, and any change after that is a new
  version, judged again.
* **The evaluation set is the holdout.** Named cases -- the template's variables and the
  checks the answer must pass -- hashed as content, so "passed the evaluation" always names
  which evaluation, in which state. The owner maintains it, and so may a model manager:
  a validator adds the case that breaks the application without asking its author.
* **Checks are deterministic.** ``contains``, ``not_contains``, ``equals``, ``regex``,
  ``max_chars``, ``json`` (the answer parses, optionally with required keys). No model grades
  another model here: a judgement MAYA cannot reproduce is not evidence it can seal.
* **Guardrails run on every answer**: blocked terms, a length cap, and personal-data patterns
  (e-mail addresses, card numbers that pass the Luhn check, phone numbers). A violation fails
  the case whatever its checks said.
* **Two ways to run.** *Recorded*: the answers were produced elsewhere -- any provider,
  any harness -- and are submitted for scoring. *Live*: MAYA calls the provider itself;
  today that is Anthropic, through the assistant's client, and the run records it.
* **Approval needs evidence.** A version is submitted only with an evaluation run on its
  own definition hash, against an evaluation set in its current state, that meets the
  version's pass-rate threshold (all cases, by default) with no guardrail violation. It is
  approved by a model manager or administrator who neither owns the application nor
  submitted the version.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import builtins
import json
import re
import string
from typing import Any, Callable

from maya.core import djson
from maya.core.clock import utcnow
from maya.core.errors import (
    ConflictError,
    NotApproved,
    NotFound,
    PermissionDenied,
    ValidationFailed,
)
from maya.security.authz import Principal

PROVIDERS = ("anthropic", "openai", "azure_openai", "bedrock", "vertex", "self_hosted", "other")
LIVE_PROVIDERS = ("anthropic",)
CHECKS = ("contains", "not_contains", "equals", "regex", "max_chars", "json")
DECIDERS = ("admin", "model_manager")
MAX_CASES = 500
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_CARD = re.compile(r"\b(?:\d[ -]?){13,19}\b")
_PHONE = re.compile(r"(?<!\d)(?:\+\d{1,3}[ -]?)?(?:\(?\d{2,4}\)?[ -]?){2,4}\d{3,4}(?!\d)")


def _luhn(digits: str) -> bool:
    total, alt = 0, False
    for ch in reversed(digits):
        d = int(ch)
        if alt:
            d = d * 2 - 9 if d * 2 > 9 else d * 2
        total += d
        alt = not alt
    return total % 10 == 0


def pii_found(text: str) -> builtins.list[str]:
    """Kinds of personal data visible in ``text``."""
    kinds = []
    if _EMAIL.search(text):
        kinds.append("email address")
    for m in _CARD.finditer(text):
        digits = re.sub(r"\D", "", m.group())
        if 13 <= len(digits) <= 19 and _luhn(digits):
            kinds.append("card number")
            break
    if any(len(re.sub(r"\D", "", m.group())) >= 10 for m in _PHONE.finditer(text)):
        kinds.append("phone number")
    return kinds


def template_fields(template: str) -> builtins.list[str]:
    """The ``{name}`` placeholders a prompt template reads, in order, each once."""
    names: builtins.list[str] = []
    try:
        parsed = list(string.Formatter().parse(template))
    except ValueError as exc:
        raise ValidationFailed(f"The prompt template does not parse: {exc}") from exc
    for _, name, spec, conv in parsed:
        if name is None:
            continue
        if not name.isidentifier() or spec or conv:
            raise ValidationFailed(
                f"'{{{name}}}' is not a plain placeholder; use {{name}} with a simple name"
            )
        if name not in names:
            names.append(name)
    return names


def render(template: str, variables: dict[str, Any]) -> str:
    missing = [n for n in template_fields(template) if n not in variables]
    if missing:
        raise ValidationFailed(f"The case does not supply {missing}", missing=missing)
    return template.format(**{k: variables[k] for k in template_fields(template)})


def run_check(check: dict[str, Any], text: str) -> tuple[bool, str]:
    kind, value = check.get("kind"), check.get("value")
    if kind == "contains":
        return str(value).lower() in text.lower(), f"contains '{value}'"
    if kind == "not_contains":
        return str(value).lower() not in text.lower(), f"does not contain '{value}'"
    if kind == "equals":
        return text.strip() == str(value).strip(), "equals the reference"
    if kind == "regex":
        return re.search(str(value), text) is not None, f"matches /{value}/"
    if kind == "max_chars":
        return len(text) <= int(value or 0), f"at most {value} characters"
    if kind == "json":
        try:
            doc = json.loads(text)
        except json.JSONDecodeError:
            return False, "parses as JSON"
        keys = value or []
        ok = isinstance(doc, dict) and all(k in doc for k in keys)
        return ok, "parses as JSON" + (f" with keys {keys}" if keys else "")
    return False, f"unknown check '{kind}'"


def guardrail_violations(guardrails: dict[str, Any], text: str) -> builtins.list[str]:
    out = []
    for term in guardrails.get("blocked_terms") or []:
        if str(term).lower() in text.lower():
            out.append(f"blocked term '{term}'")
    cap = guardrails.get("max_chars")
    if cap and len(text) > int(cap):
        out.append(f"longer than {cap} characters")
    if guardrails.get("pii", True):
        out.extend(f"personal data: {k}" for k in pii_found(text))
    return out


def _validate_cases(cases: Any) -> builtins.list[dict[str, Any]]:
    if not isinstance(cases, list) or not cases:
        raise ValidationFailed("An evaluation set is a non-empty list of cases")
    if len(cases) > MAX_CASES:
        raise ValidationFailed(f"At most {MAX_CASES} cases in one evaluation set")
    seen, out = set(), []
    for i, case in enumerate(cases):
        if not isinstance(case, dict):
            raise ValidationFailed(f"Case {i + 1} is not an object")
        cid = str(case.get("id") or f"case-{i + 1}")
        if cid in seen:
            raise ValidationFailed(f"Case id '{cid}' appears twice")
        seen.add(cid)
        checks = case.get("checks") or []
        if not checks:
            raise ValidationFailed(f"Case '{cid}' has no checks; a case that checks nothing passes")
        for c in checks:
            if c.get("kind") not in CHECKS:
                raise ValidationFailed(f"Case '{cid}': check kind is one of {', '.join(CHECKS)}")
            if c["kind"] == "regex":
                try:
                    re.compile(str(c.get("value")))
                except re.error as exc:
                    raise ValidationFailed(f"Case '{cid}': the regex does not compile: {exc}")
        out.append({"id": cid, "vars": dict(case.get("vars") or {}), "checks": checks})
    return out


class LlmService:
    def __init__(self, platform: Any) -> None:
        self.p = platform
        # the live runner, replaceable in tests; (version, prompt) -> {"text", ...}
        self.runner: Callable[[dict[str, Any], str], dict[str, Any]] | None = None

    # -- applications ----------------------------------------------------------------
    def _app(self, uow: Any, p: Principal, ref: str, action: str = "read") -> tuple[Any, Any]:
        parts = ref.strip().split("/")
        if len(parts) != 2 or not all(parts):
            raise ValidationFailed("An LLM application is named namespace/name")
        ns = uow.repo("namespaces").find_one(name=parts[0])
        app = uow.repo("llm_apps").find_one(namespace_id=ns["id"], name=parts[1]) if ns else None
        if app is None:
            raise NotFound(f"LLM application '{ref}' does not exist")
        self.p.access.require(uow, p, action, "model", app)
        return app, ns

    @staticmethod
    def _ref(app: dict[str, Any], ns: dict[str, Any]) -> str:
        return f"{ns['name']}/{app['name']}"

    def create_app(
        self,
        p: Principal,
        *,
        namespace: str,
        name: str,
        description: str = "",
        use_case: str = "",
    ) -> dict[str, Any]:
        if not re.fullmatch(r"[a-z0-9][a-z0-9_\-]{0,127}", name):
            raise ValidationFailed("An application name is lowercase letters, digits, - and _")
        if not use_case.strip():
            raise ValidationFailed(
                "Say what the application is used for; it is reviewed against its use"
            )
        with self.p.uow(p.username) as uow:
            ns = self.p.access.namespace(uow, namespace)
            self.p.access.require(
                uow, p, "create", "model", {"id": "new", "namespace_id": ns["id"], "name": name}
            )
            if uow.repo("llm_apps").find_one(namespace_id=ns["id"], name=name):
                raise ConflictError(f"LLM application '{namespace}/{name}' already exists")
            app = uow.repo("llm_apps").add(
                {
                    "namespace_id": ns["id"],
                    "name": name,
                    "owner_id": p.user_id,
                    "description": description,
                    "use_case": use_case.strip(),
                }
            )
            uow.audit("llm.app_created", object_type="llm_app", object_ref=f"{namespace}/{name}")
            return app

    def list_apps(self, p: Principal) -> builtins.list[dict[str, Any]]:
        out = []
        with self.p.uow() as uow:
            for app in uow.repo("llm_apps").list(order_by=["name"]):
                if not self.p.access.allowed(uow, p, "read", "model", app):
                    continue
                ns = uow.repo("namespaces").get(app["namespace_id"])
                latest = uow.repo("llm_app_versions").list(
                    app_id=app["id"], order_by=["-version_no"], limit=1
                )
                approved = uow.repo("llm_app_versions").list(
                    app_id=app["id"], state="approved", order_by=["-version_no"], limit=1
                )
                out.append(
                    {
                        **app,
                        "namespace": ns["name"],
                        "ref": self._ref(app, ns),
                        "latest": latest[0] if latest else None,
                        "approved": approved[0] if approved else None,
                    }
                )
        return out

    def get_app(self, p: Principal, ref: str) -> dict[str, Any]:
        with self.p.uow() as uow:
            app, ns = self._app(uow, p, ref)
            versions = uow.repo("llm_app_versions").list(app_id=app["id"], order_by=["-version_no"])
            sets = uow.repo("llm_eval_sets").list(app_id=app["id"], order_by=["name"])
            ids = [v["id"] for v in versions]
            runs = (
                uow.repo("llm_eval_runs").list(version_id__in=ids, order_by=["-created_at"])
                if ids
                else []
            )
            owner = uow.repo("users").get(app["owner_id"])
            return {
                **app,
                "namespace": ns["name"],
                "ref": self._ref(app, ns),
                "owner": owner["username"] if owner else None,
                "versions": versions,
                "eval_sets": sets,
                "runs": runs,
                "can_edit": self.p.access.allowed(uow, p, "update", "model", app),
                "providers": PROVIDERS,
                "live_providers": LIVE_PROVIDERS,
            }

    # -- versions --------------------------------------------------------------------
    @staticmethod
    def _definition(fields: dict[str, Any]) -> str:
        keys = ("provider", "model", "system_prompt", "prompt_template", "parameters", "guardrails")
        return djson.canonical_hash({k: fields.get(k) for k in keys})

    def save_version(
        self,
        p: Principal,
        ref: str,
        *,
        provider: str,
        model: str,
        system_prompt: str = "",
        prompt_template: str,
        parameters: dict[str, Any] | None = None,
        guardrails: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Edit the draft, or open a new version when the latest one is no longer a draft."""
        if provider not in PROVIDERS:
            raise ValidationFailed(f"provider is one of {', '.join(PROVIDERS)}")
        if not model.strip():
            raise ValidationFailed("Name the model the application calls")
        if not template_fields(prompt_template):
            raise ValidationFailed(
                "The prompt template reads no {placeholder}; every case would ask the same thing"
            )
        guard = {"pii": True, "min_pass_rate": 1.0, **(guardrails or {})}
        rate = float(guard["min_pass_rate"])
        if not 0.5 <= rate <= 1.0:
            raise ValidationFailed("min_pass_rate is between 0.5 and 1.0")
        fields = {
            "provider": provider,
            "model": model.strip(),
            "system_prompt": system_prompt,
            "prompt_template": prompt_template,
            "parameters": dict(parameters or {}),
            "guardrails": guard,
        }
        fields["definition_hash"] = self._definition(fields)
        with self.p.uow(p.username) as uow:
            app, ns = self._app(uow, p, ref, "update")
            latest = uow.repo("llm_app_versions").list(
                app_id=app["id"], order_by=["-version_no"], limit=1
            )
            if latest and latest[0]["state"] == "draft":
                row = uow.repo("llm_app_versions").update(latest[0]["id"], fields)
            else:
                no = latest[0]["version_no"] + 1 if latest else 1
                row = uow.repo("llm_app_versions").add(
                    {"app_id": app["id"], "version_no": no, "state": "draft", **fields}
                )
            uow.audit(
                "llm.version_saved",
                object_type="llm_app",
                object_ref=f"{self._ref(app, ns)}@v{row['version_no']}",
                detail={"definition_hash": row["definition_hash"]},
            )
            return row

    def _version(self, uow: Any, app: dict[str, Any], version_no: int) -> dict[str, Any]:
        v = uow.repo("llm_app_versions").find_one(app_id=app["id"], version_no=int(version_no))
        if v is None:
            raise ValidationFailed(f"There is no version {version_no}")
        return v

    # -- evaluation ------------------------------------------------------------------
    def save_eval_set(
        self, p: Principal, ref: str, *, name: str, cases: Any, description: str = ""
    ) -> dict[str, Any]:
        """Create or replace an evaluation set. Replacing it changes its hash, so a run
        against the old content no longer counts as evidence for a submission."""
        clean = _validate_cases(cases)
        digest = djson.canonical_hash(clean)
        with self.p.uow(p.username) as uow:
            # The owner maintains the evaluation set, and so may a validator: a model manager
            # must be able to add the case that breaks the application without asking the
            # person whose work it tests.
            validator = any(r in p.roles for r in DECIDERS)
            app, ns = self._app(uow, p, ref, "read" if validator else "update")
            row = uow.repo("llm_eval_sets").find_one(app_id=app["id"], name=name)
            values = {"cases": clean, "content_hash": digest, "description": description}
            if row:
                row = uow.repo("llm_eval_sets").update(row["id"], values)
            else:
                row = uow.repo("llm_eval_sets").add({"app_id": app["id"], "name": name, **values})
            uow.audit(
                "llm.eval_set_saved",
                object_type="llm_app",
                object_ref=self._ref(app, ns),
                detail={"eval_set": name, "cases": len(clean), "hash": digest},
            )
            return row

    def _live(self, version: dict[str, Any], prompt: str) -> dict[str, Any]:
        if self.runner is not None:
            return self.runner(version, prompt)
        if version["provider"] not in LIVE_PROVIDERS:
            raise ValidationFailed(
                f"MAYA does not call {version['provider']} itself; run the evaluation where the "
                "application runs and submit the answers as a recorded run"
            )
        from maya.assistant.claude import client_from, complete

        prm = version["parameters"] or {}
        return complete(
            client_from(self.p.settings),
            model=version["model"],
            system=version["system_prompt"],
            prompt=prompt,
            max_tokens=int(prm.get("max_tokens", 1024)),
            temperature=prm.get("temperature"),
        )

    def run_eval(
        self,
        p: Principal,
        ref: str,
        version_no: int,
        eval_set: str,
        *,
        responses: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Score a version on an evaluation set: ``responses`` (case id -> answer) for a
        recorded run, or none for MAYA to call the provider live."""
        with self.p.uow() as uow:
            app, ns = self._app(uow, p, ref)
            version = self._version(uow, app, version_no)
            es = uow.repo("llm_eval_sets").find_one(app_id=app["id"], name=eval_set)
            if es is None:
                raise ValidationFailed(f"There is no evaluation set '{eval_set}'")
        mode = "recorded" if responses is not None else "live"
        if responses is not None:
            missing = [c["id"] for c in es["cases"] if c["id"] not in responses]
            if missing:
                raise ValidationFailed(
                    f"A recorded run answers every case; missing {missing[:10]}",
                    missing=len(missing),
                )
        results, passed, violations = [], 0, 0
        guard = version["guardrails"] or {}
        for case in es["cases"]:
            prompt = render(version["prompt_template"], case["vars"])
            if responses is not None:
                answer, meta = str(responses[case["id"]]), {}
            else:
                out = self._live(version, prompt)
                answer = out["text"]
                meta = {k: v for k, v in out.items() if k != "text"}
            checks = [
                {"check": why, "passed": ok}
                for ok, why in (run_check(c, answer) for c in case["checks"])
            ]
            broken = guardrail_violations(guard, answer)
            ok = all(c["passed"] for c in checks) and not broken
            passed += ok
            violations += bool(broken)
            results.append(
                {
                    "case": case["id"],
                    "passed": ok,
                    "checks": checks,
                    "guardrails": broken,
                    "answer": answer[:4000],
                    **meta,
                }
            )
        n = len(results)
        with self.p.uow(p.username) as uow:
            row = uow.repo("llm_eval_runs").add(
                {
                    "version_id": version["id"],
                    "eval_set_id": es["id"],
                    "eval_set_hash": es["content_hash"],
                    "definition_hash": version["definition_hash"],
                    "mode": mode,
                    "cases": n,
                    "passed": passed,
                    "pass_rate": passed / n if n else 0.0,
                    "guardrail_violations": violations,
                    "results": results,
                }
            )
            uow.audit(
                "llm.evaluated",
                object_type="llm_app",
                object_ref=f"{self._ref(app, ns)}@v{version['version_no']}",
                detail={"eval_set": eval_set, "mode": mode, "passed": passed, "cases": n},
            )
            return row

    # -- approval --------------------------------------------------------------------
    def _evidence(self, uow: Any, version: dict[str, Any]) -> dict[str, Any] | None:
        """The best run that still counts: same definition, evaluation set unchanged."""
        need = float((version["guardrails"] or {}).get("min_pass_rate", 1.0))
        for run in uow.repo("llm_eval_runs").list(
            version_id=version["id"], order_by=["-pass_rate", "-created_at"]
        ):
            es = uow.repo("llm_eval_sets").get(run["eval_set_id"])
            if (
                run["definition_hash"] == version["definition_hash"]
                and es
                and es["content_hash"] == run["eval_set_hash"]
                and run["pass_rate"] >= need
                and run["guardrail_violations"] == 0
            ):
                return run
        return None

    def submit(self, p: Principal, ref: str, version_no: int) -> dict[str, Any]:
        with self.p.uow(p.username) as uow:
            app, ns = self._app(uow, p, ref, "update")
            v = self._version(uow, app, version_no)
            if v["state"] != "draft":
                raise NotApproved(f"Version {version_no} is '{v['state']}', not a draft")
            if self._evidence(uow, v) is None:
                need = (v["guardrails"] or {}).get("min_pass_rate", 1.0)
                raise NotApproved(
                    "Submission needs an evaluation run on this exact definition, against an "
                    f"evaluation set as it now stands, passing at least {need:.0%} of cases with "
                    "no guardrail violation"
                )
            row = uow.repo("llm_app_versions").update(
                v["id"],
                {"state": "in_review", "submitted_by": p.username, "submitted_at": utcnow()},
            )
            uow.audit(
                "llm.submitted",
                object_type="llm_app",
                object_ref=f"{self._ref(app, ns)}@v{version_no}",
            )
            return row

    def decide(
        self, p: Principal, ref: str, version_no: int, decision: str, note: str
    ) -> dict[str, Any]:
        if decision not in ("approve", "reject"):
            raise ValidationFailed("decision is 'approve' or 'reject'")
        if not note.strip():
            raise ValidationFailed("A decision records why")
        if not any(r in p.roles for r in DECIDERS):
            raise PermissionDenied("An LLM application is approved by a model manager")
        with self.p.uow(p.username) as uow:
            app, ns = self._app(uow, p, ref)
            v = self._version(uow, app, version_no)
            if v["state"] != "in_review":
                raise NotApproved(f"Version {version_no} is '{v['state']}', not in review")
            owner = uow.repo("users").get(app["owner_id"])
            if p.username in (v["submitted_by"], owner["username"] if owner else None):
                raise PermissionDenied(
                    "Whoever owns the application or submitted the version does not approve it"
                )
            if decision == "approve" and self._evidence(uow, v) is None:
                raise NotApproved("The evaluation evidence no longer holds; evaluate again")
            state = "approved" if decision == "approve" else "rejected"
            if state == "approved":
                for old in uow.repo("llm_app_versions").list(app_id=app["id"], state="approved"):
                    uow.repo("llm_app_versions").update(old["id"], {"state": "retired"})
            row = uow.repo("llm_app_versions").update(
                v["id"],
                {
                    "state": state,
                    "decided_by": p.username,
                    "decided_at": utcnow(),
                    "decision_note": note.strip(),
                },
            )
            uow.audit(
                f"llm.{state}",
                object_type="llm_app",
                object_ref=f"{self._ref(app, ns)}@v{version_no}",
                detail={"note": note.strip()},
            )
            return row
