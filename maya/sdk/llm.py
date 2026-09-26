"""
SDK: LLM applications -- versions, evaluation sets, runs and approval.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

from typing import Any

from maya.sdk.base import _Resource, endpoint
from maya.sdk.transport import seg


def _app(ref: str) -> str:
    ns, _, name = ref.partition("/")
    return f"{seg(ns)}/{seg(name)}"


class Llm(_Resource):
    """LLM applications governed like models: sealed versions, evaluations, approval."""

    @endpoint("GET", "/llm/apps")
    def apps(self) -> Any:
        return self._c("GET", "/llm/apps")

    @endpoint("POST", "/llm/apps")
    def create_app(self, namespace: str, name: str, use_case: str, description: str = "") -> Any:
        body = {
            "namespace": namespace,
            "name": name,
            "use_case": use_case,
            "description": description,
        }
        return self._c("POST", "/llm/apps", json_body=body)

    @endpoint("GET", "/llm/apps/{namespace}/{name}")
    def app(self, ref: str) -> Any:
        return self._c("GET", f"/llm/apps/{_app(ref)}")

    @endpoint("PUT", "/llm/apps/{namespace}/{name}/draft")
    def save_version(
        self,
        ref: str,
        *,
        provider: str,
        model: str,
        prompt_template: str,
        system_prompt: str = "",
        parameters: dict[str, Any] | None = None,
        guardrails: dict[str, Any] | None = None,
    ) -> Any:
        body = {
            "provider": provider,
            "model": model,
            "prompt_template": prompt_template,
            "system_prompt": system_prompt,
            "parameters": parameters,
            "guardrails": guardrails,
        }
        return self._c("PUT", f"/llm/apps/{_app(ref)}/draft", json_body=body)

    @endpoint("PUT", "/llm/apps/{namespace}/{name}/eval-sets")
    def save_eval_set(
        self, ref: str, name: str, cases: list[dict[str, Any]], description: str = ""
    ) -> Any:
        body = {"name": name, "cases": cases, "description": description}
        return self._c("PUT", f"/llm/apps/{_app(ref)}/eval-sets", json_body=body)

    @endpoint("POST", "/llm/apps/{namespace}/{name}/versions/{version_no}/runs")
    def run_eval(
        self,
        ref: str,
        version_no: int,
        eval_set: str,
        responses: dict[str, str] | None = None,
    ) -> Any:
        return self._c(
            "POST",
            f"/llm/apps/{_app(ref)}/versions/{int(version_no)}/runs",
            json_body={"eval_set": eval_set, "responses": responses},
        )

    @endpoint("POST", "/llm/apps/{namespace}/{name}/versions/{version_no}/submit")
    def submit(self, ref: str, version_no: int) -> Any:
        return self._c("POST", f"/llm/apps/{_app(ref)}/versions/{int(version_no)}/submit")

    @endpoint("POST", "/llm/apps/{namespace}/{name}/versions/{version_no}/decision")
    def decide(self, ref: str, version_no: int, decision: str, note: str) -> Any:
        return self._c(
            "POST",
            f"/llm/apps/{_app(ref)}/versions/{int(version_no)}/decision",
            json_body={"decision": decision, "note": note},
        )
