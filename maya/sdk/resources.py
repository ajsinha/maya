"""
SDK resources — one method per public endpoint, and one endpoint per method.

Every method is tagged with the endpoint it calls; ``tools/ci/sdk_parity.py``
compares that registry against the server's routes and fails the build when
either side has something the other lacks (§18.2.1, SC-13). A method returns
whatever the transport returns, so the same class serves the sync client
(values) and the async client (awaitables).

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import json
from typing import Any, Callable

from maya.sdk.transport import Call, seg, split_ref

ENDPOINTS: dict[tuple[str, str], str] = {}


def endpoint(method: str, path: str) -> Callable[[Any], Any]:
    def deco(fn: Any) -> Any:
        ENDPOINTS[(method, path)] = f"{fn.__qualname__}"
        fn.__maya_endpoint__ = (method, path)
        return fn
    return deco


class _Resource:
    def __init__(self, transport: Any) -> None:
        self._t = transport

    def _c(self, method: str, path: str, **kw: Any) -> Any:
        return self._t.call(Call(method, path, **kw))


def _nn(ref: str, kind: str) -> str:
    ns, name = split_ref(ref, kind)
    return f"{seg(ns)}/{seg(name)}"


def _files(data: bytes, filename: str) -> dict[str, Any]:
    return {"file": (filename, data, "application/octet-stream")}


class Auth(_Resource):
    @endpoint("POST", "/auth/login")
    def login(self, username: str, password: str) -> Any:
        return self._c("POST", "/auth/login", json_body={"username": username, "password": password})

    @endpoint("GET", "/auth/sso/config")
    def sso_config(self) -> Any:
        return self._c("GET", "/auth/sso/config")

    @endpoint("POST", "/auth/sso/start")
    def sso_start(self) -> Any:
        return self._c("POST", "/auth/sso/start")

    @endpoint("POST", "/auth/sso/callback")
    def sso_callback(self, code: str, code_verifier: str, nonce: str) -> Any:
        return self._c("POST", "/auth/sso/callback", json_body={
            "code": code, "code_verifier": code_verifier, "nonce": nonce})

    @endpoint("GET", "/auth/mfa")
    def mfa_status(self) -> Any:
        return self._c("GET", "/auth/mfa")

    @endpoint("POST", "/auth/mfa/verify")
    def mfa_verify(self, code: str) -> Any:
        return self._c("POST", "/auth/mfa/verify", json_body={"code": code})

    @endpoint("POST", "/auth/mfa/enroll")
    def mfa_enroll(self) -> Any:
        return self._c("POST", "/auth/mfa/enroll")

    @endpoint("POST", "/auth/mfa/confirm")
    def mfa_confirm(self, code: str) -> Any:
        return self._c("POST", "/auth/mfa/confirm", json_body={"code": code})

    # SAML 2.0 (auth.sso.protocol: saml2)
    @endpoint("GET", "/auth/sso/saml/metadata")
    def saml_metadata(self) -> Any:
        """MAYA's service-provider metadata XML, as bytes plus headers."""
        return self._c("GET", "/auth/sso/saml/metadata", raw=True)

    @endpoint("POST", "/auth/sso/saml/start")
    def saml_start(self, relay_state: str = "") -> Any:
        return self._c("POST", "/auth/sso/saml/start", json_body={"relay_state": relay_state})

    @endpoint("POST", "/auth/sso/saml/acs")
    def saml_acs(self, saml_response: str) -> Any:
        return self._c("POST", "/auth/sso/saml/acs", json_body={"saml_response": saml_response})

    # security keys (WebAuthn) as a second factor
    @endpoint("GET", "/auth/mfa/webauthn")
    def security_keys(self) -> Any:
        return self._c("GET", "/auth/mfa/webauthn")

    @endpoint("DELETE", "/auth/mfa/webauthn/{key_id}")
    def remove_security_key(self, key_id: str) -> Any:
        return self._c("DELETE", f"/auth/mfa/webauthn/{seg(key_id)}")

    @endpoint("POST", "/auth/mfa/webauthn/register/options")
    def security_key_register_options(self) -> Any:
        return self._c("POST", "/auth/mfa/webauthn/register/options")

    @endpoint("POST", "/auth/mfa/webauthn/register")
    def register_security_key(self, credential: dict[str, Any], name: str = "security key"
                              ) -> Any:
        return self._c("POST", "/auth/mfa/webauthn/register",
                       json_body={"credential": credential, "name": name})

    @endpoint("POST", "/auth/mfa/webauthn/options")
    def security_key_options(self) -> Any:
        return self._c("POST", "/auth/mfa/webauthn/options")

    @endpoint("POST", "/auth/mfa/webauthn/verify")
    def security_key_verify(self, credential: dict[str, Any]) -> Any:
        return self._c("POST", "/auth/mfa/webauthn/verify", json_body={"credential": credential})

    @endpoint("POST", "/auth/logout")
    def logout(self) -> Any:
        return self._c("POST", "/auth/logout")

    @endpoint("GET", "/auth/me")
    def me(self) -> Any:
        return self._c("GET", "/auth/me")

    @endpoint("POST", "/auth/password")
    def change_password(self, old_password: str, new_password: str) -> Any:
        return self._c("POST", "/auth/password", json_body={"old_password": old_password,
                                                            "new_password": new_password})

    @endpoint("GET", "/auth/api-keys")
    def api_keys(self, all: bool = False) -> Any:
        return self._c("GET", "/auth/api-keys", params={"all": all})

    @endpoint("POST", "/auth/api-keys")
    def create_api_key(self, name: str, **kw: Any) -> Any:
        return self._c("POST", "/auth/api-keys", json_body={"name": name, **kw})

    @endpoint("DELETE", "/auth/api-keys/{key_id}")
    def revoke_api_key(self, key_id: str) -> Any:
        return self._c("DELETE", f"/auth/api-keys/{seg(key_id)}")

    @endpoint("GET", "/auth/sessions")
    def sessions(self) -> Any:
        return self._c("GET", "/auth/sessions")

    @endpoint("DELETE", "/auth/sessions/{session_id}")
    def end_session(self, session_id: str) -> Any:
        return self._c("DELETE", f"/auth/sessions/{seg(session_id)}")


class Admin(_Resource):
    @endpoint("GET", "/users")
    def users(self) -> Any:
        return self._c("GET", "/users")

    @endpoint("POST", "/users")
    def create_user(self, username: str, **kw: Any) -> Any:
        return self._c("POST", "/users", json_body={"username": username, **kw})

    @endpoint("PATCH", "/users/{username}")
    def update_user(self, username: str, **changes: Any) -> Any:
        return self._c("PATCH", f"/users/{seg(username)}", json_body=changes)

    @endpoint("PUT", "/users/{username}/roles")
    def set_roles(self, username: str, roles: list[str]) -> Any:
        return self._c("PUT", f"/users/{seg(username)}/roles", json_body={"roles": roles})

    @endpoint("POST", "/users/{username}/password-reset")
    def reset_password(self, username: str, new_password: str) -> Any:
        return self._c("POST", f"/users/{seg(username)}/password-reset",
                       json_body={"new_password": new_password})

    @endpoint("POST", "/users/{username}/mfa-reset")
    def reset_mfa(self, username: str) -> Any:
        return self._c("POST", f"/users/{seg(username)}/mfa-reset")

    @endpoint("GET", "/roles")
    def roles(self) -> Any:
        return self._c("GET", "/roles")

    @endpoint("POST", "/roles")
    def create_role(self, name: str, capabilities: dict[str, str], description: str = "") -> Any:
        return self._c("POST", "/roles", json_body={"name": name, "capabilities": capabilities,
                                                    "description": description})

    @endpoint("GET", "/groups")
    def groups(self) -> Any:
        return self._c("GET", "/groups")

    @endpoint("POST", "/groups")
    def create_group(self, name: str, **kw: Any) -> Any:
        return self._c("POST", "/groups", json_body={"name": name, **kw})

    @endpoint("GET", "/audit")
    def audit(self, q: str | None = None, action: str | None = None, limit: int = 1000) -> Any:
        return self._c("GET", "/audit", params={"q": q, "action": action, "limit": limit})

    @endpoint("GET", "/audit/verify")
    def verify_audit(self) -> Any:
        return self._c("GET", "/audit/verify")

    @endpoint("GET", "/system/health")
    def health(self) -> Any:
        return self._c("GET", "/system/health")

    @endpoint("GET", "/system/config")
    def config(self) -> Any:
        return self._c("GET", "/system/config")

    @endpoint("GET", "/system/storage")
    def storage(self) -> Any:
        return self._c("GET", "/system/storage")

    @endpoint("POST", "/system/integrity")
    def verify_integrity(self) -> Any:
        return self._c("POST", "/system/integrity")

    @endpoint("GET", "/system/estate")
    def export_estate(self) -> Any:
        return self._c("GET", "/system/estate", raw=True)

    @endpoint("GET", "/blobs/{digest}")
    def blob(self, digest: str) -> Any:
        return self._c("GET", f"/blobs/{seg(digest)}", raw=True)


class Sources(_Resource):
    @endpoint("GET", "/sql-connections")
    def connections(self) -> Any:
        return self._c("GET", "/sql-connections")

    @endpoint("POST", "/sql-connections")
    def create_connection(self, name: str, url: str, password_env: str | None = None,
                          description: str = "") -> Any:
        return self._c("POST", "/sql-connections", json_body={
            "name": name, "url": url, "password_env": password_env, "description": description})

    @endpoint("DELETE", "/sql-connections/{name}")
    def delete_connection(self, name: str) -> Any:
        return self._c("DELETE", f"/sql-connections/{seg(name)}")

    @endpoint("POST", "/sql-connections/{name}/test")
    def test_connection(self, name: str) -> Any:
        return self._c("POST", f"/sql-connections/{seg(name)}/test")


class Namespaces(_Resource):
    @endpoint("GET", "/namespaces")
    def list(self) -> Any:
        return self._c("GET", "/namespaces")

    @endpoint("POST", "/namespaces")
    def create(self, name: str, **kw: Any) -> Any:
        return self._c("POST", "/namespaces", json_body={"name": name, **kw})

    @endpoint("PATCH", "/namespaces/{name}")
    def update(self, name: str, **changes: Any) -> Any:
        return self._c("PATCH", f"/namespaces/{seg(name)}", json_body=changes)


class Access(_Resource):
    @endpoint("GET", "/grants")
    def grants(self, kind: str, ref: str) -> Any:
        return self._c("GET", "/grants", params={"kind": kind, "ref": ref})

    @endpoint("POST", "/grants")
    def grant(self, kind: str, object_ref: str, principal_type: str, principal_id: str,
              level: str, **kw: Any) -> Any:
        return self._c("POST", "/grants", json_body={
            "kind": kind, "object_ref": object_ref, "principal_type": principal_type,
            "principal_id": principal_id, "level": level, **kw})

    @endpoint("DELETE", "/grants/{grant_id}")
    def revoke(self, grant_id: str) -> Any:
        return self._c("DELETE", f"/grants/{seg(grant_id)}")

    @endpoint("GET", "/access/recertification")
    def recertification(self) -> Any:
        return self._c("GET", "/access/recertification")

    @endpoint("GET", "/inbox")
    def inbox(self) -> Any:
        return self._c("GET", "/inbox")

    @endpoint("POST", "/inbox/read")
    def mark_read(self, ids: list[str] | None = None) -> Any:
        return self._c("POST", "/inbox/read", json_body={"ids": ids})

    @endpoint("GET", "/search")
    def search(self, q: str, limit: int = 50) -> Any:
        return self._c("GET", "/search", params={"q": q, "limit": limit})

    @endpoint("POST", "/search/reindex")
    def reindex_search(self) -> Any:
        return self._c("POST", "/search/reindex")

    @endpoint("GET", "/lineage")
    def lineage(self, root: str, direction: str = "both", depth: int = 3) -> Any:
        return self._c("GET", "/lineage", params={"root": root, "direction": direction,
                                                  "depth": depth})


class Features(_Resource):
    @endpoint("GET", "/features")
    def list(self, namespace: str | None = None, q: str | None = None,
             status: str | None = None) -> Any:
        return self._c("GET", "/features", params={"namespace": namespace, "q": q,
                                                   "status": status})

    @endpoint("POST", "/features")
    def create(self, namespace: str, name: str, definition: dict[str, Any], **kw: Any) -> Any:
        return self._c("POST", "/features", json_body={"namespace": namespace, "name": name,
                                                       "definition": definition, **kw})

    @endpoint("POST", "/features/infer")
    def infer(self, data: bytes, fmt: str = "csv", filename: str = "upload") -> Any:
        return self._c("POST", "/features/infer", files=_files(data, filename), data={"fmt": fmt})

    @endpoint("POST", "/features/quick")
    def quick(self, data: bytes, name: str, fmt: str = "csv") -> Any:
        return self._c("POST", "/features/quick", files=_files(data, f"{name}.{fmt}"),
                       data={"name": name, "fmt": fmt})

    @endpoint("GET", "/features/{namespace}/{name}")
    def get(self, ref: str) -> Any:
        return self._c("GET", f"/features/{_nn(ref, 'feature')}")

    @endpoint("PUT", "/features/{namespace}/{name}/draft")
    def update_draft(self, ref: str, definition: dict[str, Any], **kw: Any) -> Any:
        return self._c("PUT", f"/features/{_nn(ref, 'feature')}/draft",
                       json_body={"definition": definition, **kw})

    @endpoint("POST", "/features/{namespace}/{name}/drafts")
    def new_draft(self, ref: str) -> Any:
        return self._c("POST", f"/features/{_nn(ref, 'feature')}/drafts")

    @endpoint("POST", "/features/{namespace}/{name}/clone")
    def clone(self, ref: str, name: str, namespace: str | None = None, extend: bool = False) -> Any:
        return self._c("POST", f"/features/{_nn(ref, 'feature')}/clone",
                       json_body={"name": name, "namespace": namespace, "extend": extend})

    @endpoint("POST", "/features/{namespace}/{name}/ingest")
    def ingest(self, ref: str, data: bytes, fmt: str = "csv", filename: str = "upload",
               knowledge_time: str | None = None, note: str = "") -> Any:
        form = {"fmt": fmt, "note": note}
        if knowledge_time:
            form["knowledge_time"] = knowledge_time
        return self._c("POST", f"/features/{_nn(ref, 'feature')}/ingest",
                       files=_files(data, filename), data=form)

    @endpoint("POST", "/features/{namespace}/{name}/pull")
    def pull(self, ref: str, knowledge_time: str | None = None) -> Any:
        return self._c("POST", f"/features/{_nn(ref, 'feature')}/pull",
                       json_body={"knowledge_time": knowledge_time})

    @endpoint("POST", "/features/{namespace}/{name}/versions/{version_no}/transitions/{transition}")
    def transition(self, ref: str, version_no: int, transition: str, **kw: Any) -> Any:
        return self._c("POST", f"/features/{_nn(ref, 'feature')}/versions/{int(version_no)}"
                               f"/transitions/{seg(transition)}", json_body=kw)

    @endpoint("GET", "/features/{namespace}/{name}/compare")
    def compare(self, ref: str, v1: int, v2: int) -> Any:
        return self._c("GET", f"/features/{_nn(ref, 'feature')}/compare",
                       params={"v1": v1, "v2": v2})

    @endpoint("POST", "/features/{namespace}/{name}/draft-preview")
    def draft_preview(self, ref: str, as_of_known: str | None = None) -> Any:
        return self._c("POST", f"/features/{_nn(ref, 'feature')}/draft-preview",
                       params={"as_of_known": as_of_known})

    @endpoint("POST", "/features/{namespace}/{name}/pins")
    def pin(self, ref: str, version_no: int, pin_name: str, as_of: str,
            as_of_known: str | None = None, idempotency_key: str | None = None) -> Any:
        headers = {"Idempotency-Key": idempotency_key} if idempotency_key else {}
        return self._c("POST", f"/features/{_nn(ref, 'feature')}/pins", headers=headers,
                       json_body={"version_no": version_no, "pin_name": pin_name,
                                  "as_of": as_of, "as_of_known": as_of_known})

    @endpoint("POST", "/pins/{pin_id}/approve")
    def approve_pin(self, pin_id: str) -> Any:
        return self._c("POST", f"/pins/{seg(pin_id)}/approve")

    @endpoint("POST", "/pins/{pin_id}/retire")
    def retire_pin(self, pin_id: str, reason: str) -> Any:
        return self._c("POST", f"/pins/{seg(pin_id)}/retire", json_body={"reason": reason})

    @endpoint("GET", "/feature-data/preview")
    def preview(self, ref: str, as_of_known: str | None = None, start: str | None = None,
                end: str | None = None) -> Any:
        return self._c("GET", "/feature-data/preview", params={
            "ref": ref, "as_of_known": as_of_known, "start": start, "end": end})

    @endpoint("GET", "/feature-data")
    def download(self, ref: str, format: str = "parquet", csv_encoding: str | None = None,
                 as_of_known: str | None = None) -> Any:
        return self._c("GET", "/feature-data", raw=True, params={
            "ref": ref, "format": format, "csv_encoding": csv_encoding,
            "as_of_known": as_of_known})


class FeatureSets(_Resource):
    @endpoint("GET", "/featuresets")
    def list(self, namespace: str | None = None, q: str | None = None) -> Any:
        return self._c("GET", "/featuresets", params={"namespace": namespace, "q": q})

    @endpoint("POST", "/featuresets")
    def create(self, namespace: str, name: str, definition: dict[str, Any], **kw: Any) -> Any:
        return self._c("POST", "/featuresets", json_body={"namespace": namespace, "name": name,
                                                          "definition": definition, **kw})

    @endpoint("GET", "/featuresets/{namespace}/{name}")
    def get(self, ref: str) -> Any:
        return self._c("GET", f"/featuresets/{_nn(ref, 'featureset')}")

    @endpoint("PUT", "/featuresets/{namespace}/{name}/draft")
    def update_draft(self, ref: str, definition: dict[str, Any], **kw: Any) -> Any:
        return self._c("PUT", f"/featuresets/{_nn(ref, 'featureset')}/draft",
                       json_body={"definition": definition, **kw})

    @endpoint("POST", "/featuresets/{namespace}/{name}/drafts")
    def new_draft(self, ref: str) -> Any:
        return self._c("POST", f"/featuresets/{_nn(ref, 'featureset')}/drafts")

    @endpoint("POST",
              "/featuresets/{namespace}/{name}/versions/{version_no}/transitions/{transition}")
    def transition(self, ref: str, version_no: int, transition: str, **kw: Any) -> Any:
        return self._c("POST", f"/featuresets/{_nn(ref, 'featureset')}/versions/"
                               f"{int(version_no)}/transitions/{seg(transition)}", json_body=kw)

    @endpoint("POST", "/featuresets/{namespace}/{name}/draft-preview")
    def draft_preview(self, ref: str) -> Any:
        return self._c("POST", f"/featuresets/{_nn(ref, 'featureset')}/draft-preview")

    @endpoint("POST", "/featuresets/{namespace}/{name}/pins")
    def pin(self, ref: str, version_no: int, pin_name: str, as_of: str, cascade: bool = False,
            as_of_known: str | None = None, idempotency_key: str | None = None) -> Any:
        headers = {"Idempotency-Key": idempotency_key} if idempotency_key else {}
        return self._c("POST", f"/featuresets/{_nn(ref, 'featureset')}/pins", headers=headers,
                       json_body={"version_no": version_no, "pin_name": pin_name,
                                  "as_of": as_of, "as_of_known": as_of_known,
                                  "cascade": cascade})

    @endpoint("GET", "/featureset-data/preview")
    def preview(self, ref: str, as_of_known: str | None = None) -> Any:
        return self._c("GET", "/featureset-data/preview",
                       params={"ref": ref, "as_of_known": as_of_known})

    @endpoint("GET", "/featureset-data")
    def download(self, ref: str, format: str = "parquet", shape: str = "tabular",
                 csv_encoding: str | None = None) -> Any:
        return self._c("GET", "/featureset-data", raw=True, params={
            "ref": ref, "format": format, "shape": shape, "csv_encoding": csv_encoding})


class Models(_Resource):
    @endpoint("GET", "/models")
    def list(self, namespace: str | None = None, q: str | None = None) -> Any:
        return self._c("GET", "/models", params={"namespace": namespace, "q": q})

    @endpoint("POST", "/models")
    def create(self, namespace: str, name: str, **kw: Any) -> Any:
        return self._c("POST", "/models", json_body={"namespace": namespace, "name": name, **kw})

    @endpoint("GET", "/models/{namespace}/{name}")
    def get(self, ref: str) -> Any:
        return self._c("GET", f"/models/{_nn(ref, 'model')}")

    @endpoint("PUT", "/models/{namespace}/{name}/draft")
    def update_draft(self, ref: str, **kw: Any) -> Any:
        return self._c("PUT", f"/models/{_nn(ref, 'model')}/draft", json_body=kw)

    @endpoint("POST", "/models/{namespace}/{name}/drafts")
    def new_draft(self, ref: str) -> Any:
        return self._c("POST", f"/models/{_nn(ref, 'model')}/drafts")

    @endpoint("POST", "/models/{namespace}/{name}/artifact")
    def upload_artifact(self, ref: str, source: str, sample: dict[str, Any] | None = None,
                        params: dict[str, Any] | None = None) -> Any:
        return self._c("POST", f"/models/{_nn(ref, 'model')}/artifact",
                       json_body={"source": source, "sample": sample, "params": params})

    @endpoint("POST", "/models/workbook/lift")
    def lift_workbook(self, data: bytes, output: str | None = None,
                      roles: dict[str, str] | None = None,
                      filename: str = "workbook.xlsx") -> Any:
        """Preview the IR an .xlsx lifts to, with its check against the workbook's results."""
        return self._c("POST", "/models/workbook/lift", files=_files(data, filename),
                       data={"output": output or "", "roles": json.dumps(roles or {})})

    @endpoint("POST", "/models/{namespace}/{name}/workbook")
    def import_workbook(self, ref: str, data: bytes, output: str | None = None,
                        roles: dict[str, str] | None = None,
                        filename: str = "workbook.xlsx") -> Any:
        return self._c("POST", f"/models/{_nn(ref, 'model')}/workbook",
                       files=_files(data, filename),
                       data={"output": output or "", "roles": json.dumps(roles or {})})

    @endpoint("GET", "/models/{namespace}/{name}/versions/{version_no}/workbook.xlsx")
    def workbook(self, ref: str, version_no: int) -> Any:
        return self._c("GET", f"/models/{_nn(ref, 'model')}/versions/{int(version_no)}"
                              "/workbook.xlsx", raw=True)

    @endpoint("POST", "/models/{namespace}/{name}/versions/{version_no}/render")
    def render_spec(self, ref: str, version_no: int) -> Any:
        return self._c("POST", f"/models/{_nn(ref, 'model')}/versions/{int(version_no)}/render")

    @endpoint("GET", "/models/{namespace}/{name}/versions/{version_no}/spec.pdf")
    def spec_pdf(self, ref: str, version_no: int) -> Any:
        return self._c("GET", f"/models/{_nn(ref, 'model')}/versions/{int(version_no)}/spec.pdf",
                       raw=True)

    @endpoint("POST", "/models/{namespace}/{name}/versions/{version_no}/transitions/{transition}")
    def transition(self, ref: str, version_no: int, transition: str, **kw: Any) -> Any:
        return self._c("POST", f"/models/{_nn(ref, 'model')}/versions/{int(version_no)}"
                               f"/transitions/{seg(transition)}", json_body=kw)

    @endpoint("GET", "/models/{namespace}/{name}/diff")
    def diff(self, ref: str, v1: int, v2: int) -> Any:
        return self._c("GET", f"/models/{_nn(ref, 'model')}/diff", params={"v1": v1, "v2": v2})

    @endpoint("GET", "/models/{namespace}/{name}/versions/{version_no}/reference")
    def reference_code(self, ref: str, version_no: int) -> Any:
        return self._c("GET", f"/models/{_nn(ref, 'model')}/versions/{int(version_no)}/reference")

    @endpoint("POST", "/models/{namespace}/{name}/versions/{version_no}/conformance")
    def conformance(self, ref: str, version_no: int, n: int = 500) -> Any:
        return self._c("POST", f"/models/{_nn(ref, 'model')}/versions/{int(version_no)}"
                               "/conformance", params={"n": n})


class TrainingWarrants(_Resource):
    @endpoint("GET", "/warrants/training")
    def list(self) -> Any:
        return self._c("GET", "/warrants/training")

    @endpoint("POST", "/warrants/training")
    def create(self, namespace: str, name: str, model: str, featureset: str,
               spec: dict[str, Any] | None = None) -> Any:
        return self._c("POST", "/warrants/training", json_body={
            "namespace": namespace, "name": name, "model": model, "featureset": featureset,
            "spec": spec or {}})

    @endpoint("GET", "/warrants/training/{warrant_id}")
    def get(self, warrant_id: str) -> Any:
        return self._c("GET", f"/warrants/training/{seg(warrant_id)}")

    @endpoint("GET", "/warrants/training/{warrant_id}/data")
    def data(self, warrant_id: str) -> Any:
        return self._c("GET", f"/warrants/training/{seg(warrant_id)}/data", raw=True)

    @endpoint("POST", "/warrants/training/{warrant_id}/parameters")
    def upload_parameters(self, warrant_id: str, values: dict[str, Any], **kw: Any) -> Any:
        return self._c("POST", f"/warrants/training/{seg(warrant_id)}/parameters",
                       json_body={"values": values, **kw})

    @endpoint("POST", "/warrants/training/{warrant_id}/transitions/{transition}")
    def transition(self, warrant_id: str, transition: str, **kw: Any) -> Any:
        return self._c("POST", f"/warrants/training/{seg(warrant_id)}/transitions/"
                               f"{seg(transition)}", json_body=kw)

    @endpoint("POST", "/warrants/training/{warrant_id}/seal")
    def seal(self, warrant_id: str) -> Any:
        return self._c("POST", f"/warrants/training/{seg(warrant_id)}/seal")

    @endpoint("POST", "/warrants/training/{warrant_id}/revoke")
    def revoke(self, warrant_id: str, reason: str) -> Any:
        return self._c("POST", f"/warrants/training/{seg(warrant_id)}/revoke",
                       json_body={"reason": reason})

    @endpoint("POST", "/warrants/training/{warrant_id}/clone")
    def clone(self, warrant_id: str, **changes: Any) -> Any:
        return self._c("POST", f"/warrants/training/{seg(warrant_id)}/clone", json_body=changes)

    @endpoint("POST", "/warrants/training/{warrant_id}/score")
    def score_holdout(self, warrant_id: str, parameter_set_id: str | None = None,
                      values: dict[str, Any] | None = None) -> Any:
        return self._c("POST", f"/warrants/training/{seg(warrant_id)}/score",
                       json_body={"parameter_set_id": parameter_set_id, "values": values})

    @endpoint("POST", "/warrants/training/{warrant_id}/bundle")
    def export_bundle(self, warrant_id: str) -> Any:
        return self._c("POST", f"/warrants/training/{seg(warrant_id)}/bundle")

    @endpoint("POST", "/parameters/{parameter_set_id}/transitions/{transition}")
    def parameter_transition(self, parameter_set_id: str, transition: str, **kw: Any) -> Any:
        return self._c("POST", f"/parameters/{seg(parameter_set_id)}/transitions/"
                               f"{seg(transition)}", json_body=kw)

    @endpoint("POST", "/bundles/verify")
    def verify_bundle(self, data: bytes) -> Any:
        return self._c("POST", "/bundles/verify", files=_files(data, "bundle.zip"))


class ExecutionWarrants(_Resource):
    @endpoint("GET", "/warrants/execution")
    def list(self) -> Any:
        return self._c("GET", "/warrants/execution")

    @endpoint("POST", "/warrants/execution")
    def create(self, namespace: str, name: str, **kw: Any) -> Any:
        return self._c("POST", "/warrants/execution", json_body={"namespace": namespace,
                                                                 "name": name, **kw})

    @endpoint("GET", "/warrants/execution/{ew_id}")
    def get(self, ew_id: str) -> Any:
        return self._c("GET", f"/warrants/execution/{seg(ew_id)}")

    @endpoint("POST", "/warrants/execution/{ew_id}/transitions/{transition}")
    def transition(self, ew_id: str, transition: str, **kw: Any) -> Any:
        return self._c("POST", f"/warrants/execution/{seg(ew_id)}/transitions/{seg(transition)}",
                       json_body=kw)

    @endpoint("POST", "/warrants/execution/{ew_id}/seal")
    def seal(self, ew_id: str) -> Any:
        return self._c("POST", f"/warrants/execution/{seg(ew_id)}/seal")

    @endpoint("POST", "/warrants/execution/{ew_id}/token")
    def token(self, ew_id: str, environment: str) -> Any:
        return self._c("POST", f"/warrants/execution/{seg(ew_id)}/token",
                       params={"environment": environment})

    @endpoint("GET", "/warrants/execution/{ew_id}/bundle")
    def bundle(self, ew_id: str, environment: str) -> Any:
        return self._c("GET", f"/warrants/execution/{seg(ew_id)}/bundle",
                       params={"environment": environment})

    @endpoint("POST", "/warrants/execution/{ew_id}/report")
    def report(self, ew_id: str, environment: str, rows: int,
               input_stats: dict[str, Any] | None = None,
               output_stats: dict[str, Any] | None = None) -> Any:
        return self._c("POST", f"/warrants/execution/{seg(ew_id)}/report", json_body={
            "environment": environment, "rows": rows, "input_stats": input_stats or {},
            "output_stats": output_stats or {}})

    @endpoint("POST", "/warrants/execution/{ew_id}/reinstate")
    def reinstate(self, ew_id: str, reason: str) -> Any:
        return self._c("POST", f"/warrants/execution/{seg(ew_id)}/reinstate",
                       json_body={"reason": reason})

    @endpoint("POST", "/warrants/execution/{ew_id}/revoke")
    def revoke(self, ew_id: str, reason: str) -> Any:
        return self._c("POST", f"/warrants/execution/{seg(ew_id)}/revoke",
                       json_body={"reason": reason})


class Workflow(_Resource):
    @endpoint("GET", "/workflow/queue")
    def queue(self) -> Any:
        return self._c("GET", "/workflow/queue")

    @endpoint("GET", "/workflow/aging")
    def aging(self) -> Any:
        return self._c("GET", "/workflow/aging")

    @endpoint("GET", "/workflow/break-glass")
    def break_glass(self, days: int = 31) -> Any:
        return self._c("GET", "/workflow/break-glass", params={"days": days})

    @endpoint("GET", "/workflow/policies")
    def policies(self) -> Any:
        return self._c("GET", "/workflow/policies")

    @endpoint("GET", "/workflow/policies/{policy_id}")
    def policy(self, policy_id: str) -> Any:
        return self._c("GET", f"/workflow/policies/{seg(policy_id)}")

    @endpoint("GET", "/workflow/policies/{policy_id}/yaml")
    def policy_yaml(self, policy_id: str) -> Any:
        return self._c("GET", f"/workflow/policies/{seg(policy_id)}/yaml")

    @endpoint("POST", "/workflow/policies")
    def draft_policy(self, object_type: str, policy: dict[str, Any], scope: str = "*",
                     note: str = "") -> Any:
        return self._c("POST", "/workflow/policies", json_body={
            "object_type": object_type, "policy": policy, "scope": scope, "note": note})

    @endpoint("POST", "/workflow/policies/import")
    def import_policy(self, object_type: str, yaml: str, scope: str = "*") -> Any:
        return self._c("POST", "/workflow/policies/import", json_body={
            "object_type": object_type, "yaml": yaml, "scope": scope})

    @endpoint("POST", "/workflow/policies/validate")
    def validate_policy(self, object_type: str, policy: dict[str, Any]) -> Any:
        return self._c("POST", "/workflow/policies/validate",
                       json_body={"object_type": object_type, "policy": policy})

    @endpoint("POST", "/workflow/policies/{policy_id}/activate")
    def activate_policy(self, policy_id: str) -> Any:
        return self._c("POST", f"/workflow/policies/{seg(policy_id)}/activate")

    @endpoint("GET", "/workflow/population/{object_type}")
    def population(self, object_type: str) -> Any:
        return self._c("GET", f"/workflow/population/{seg(object_type)}")

    @endpoint("GET", "/workflow/history")
    def history(self, object_type: str, object_id: str) -> Any:
        return self._c("GET", "/workflow/history", params={"object_type": object_type,
                                                           "object_id": object_id})

    @endpoint("GET", "/workflow/comments")
    def comments(self, object_type: str, object_id: str) -> Any:
        return self._c("GET", "/workflow/comments", params={"object_type": object_type,
                                                            "object_id": object_id})

    @endpoint("POST", "/workflow/comments")
    def comment(self, object_type: str, object_id: str, body: str, blocking: bool = False,
                anchor: str | None = None) -> Any:
        return self._c("POST", "/workflow/comments", json_body={
            "object_type": object_type, "object_id": object_id, "body": body,
            "blocking": blocking, "anchor": anchor})

    @endpoint("POST", "/workflow/comments/{comment_id}/resolve")
    def resolve_comment(self, comment_id: str) -> Any:
        return self._c("POST", f"/workflow/comments/{seg(comment_id)}/resolve")

    @endpoint("POST", "/workflow/transitions")
    def transition(self, object_type: str, object_id: str, transition: str,
                   rationale: str | None = None, force: bool = False) -> Any:
        return self._c("POST", "/workflow/transitions", json_body={
            "object_type": object_type, "object_id": object_id, "transition": transition,
            "rationale": rationale, "force": force})

    @endpoint("GET", "/workflow/delegations")
    def delegations(self) -> Any:
        return self._c("GET", "/workflow/delegations")

    @endpoint("POST", "/workflow/delegations")
    def delegate(self, to: str, starts_on: str, ends_on: str,
                 object_types: list[str] | None = None, reason: str = "") -> Any:
        return self._c("POST", "/workflow/delegations", json_body={
            "to": to, "starts_on": starts_on, "ends_on": ends_on,
            "object_types": object_types or [], "reason": reason})

    @endpoint("DELETE", "/workflow/delegations/{delegation_id}")
    def revoke_delegation(self, delegation_id: str) -> Any:
        return self._c("DELETE", f"/workflow/delegations/{seg(delegation_id)}")

    @endpoint("GET", "/workflow/campaigns")
    def campaigns(self) -> Any:
        return self._c("GET", "/workflow/campaigns")

    @endpoint("POST", "/workflow/campaigns")
    def run_campaign(self, name: str, transition: str, items: list[dict[str, Any]],
                     rationale: str = "") -> Any:
        return self._c("POST", "/workflow/campaigns", json_body={
            "name": name, "transition": transition, "items": items, "rationale": rationale})


class Workspaces(_Resource):
    @endpoint("GET", "/workspaces")
    def list(self) -> Any:
        return self._c("GET", "/workspaces")

    @endpoint("POST", "/workspaces")
    def create(self, name: str, description: str = "") -> Any:
        return self._c("POST", "/workspaces", json_body={"name": name,
                                                         "description": description})

    @endpoint("GET", "/workspaces/{ws_id}")
    def get(self, ws_id: str) -> Any:
        return self._c("GET", f"/workspaces/{seg(ws_id)}")

    @endpoint("PUT", "/workspaces/{ws_id}/changes")
    def stage(self, ws_id: str, kind: str, ref: str, definition: dict[str, Any],
              note: str = "") -> Any:
        return self._c("PUT", f"/workspaces/{seg(ws_id)}/changes", json_body={
            "kind": kind, "ref": ref, "definition": definition, "note": note})

    @endpoint("DELETE", "/workspaces/{ws_id}/changes/{change_id}")
    def unstage(self, ws_id: str, change_id: str) -> Any:
        return self._c("DELETE", f"/workspaces/{seg(ws_id)}/changes/{seg(change_id)}")

    @endpoint("GET", "/workspaces/{ws_id}/preview")
    def preview(self, ws_id: str, ref: str) -> Any:
        return self._c("GET", f"/workspaces/{seg(ws_id)}/preview", params={"ref": ref})

    @endpoint("GET", "/workspaces/{ws_id}/impact")
    def impact(self, ws_id: str) -> Any:
        return self._c("GET", f"/workspaces/{seg(ws_id)}/impact")

    @endpoint("POST", "/workspaces/{ws_id}/replay")
    def shadow_replay(self, ws_id: str) -> Any:
        return self._c("POST", f"/workspaces/{seg(ws_id)}/replay")

    @endpoint("POST", "/workspaces/{ws_id}/submit")
    def submit(self, ws_id: str) -> Any:
        return self._c("POST", f"/workspaces/{seg(ws_id)}/submit")

    @endpoint("POST", "/workspaces/{ws_id}/abandon")
    def abandon(self, ws_id: str) -> Any:
        return self._c("POST", f"/workspaces/{seg(ws_id)}/abandon")


class Events(_Resource):
    @endpoint("GET", "/events")
    def list(self, after: int = 0, limit: int = 500, type: str | None = None) -> Any:
        return self._c("GET", "/events", params={"after": after, "limit": limit, "type": type})

    @endpoint("GET", "/events/stream")
    def stream(self, after: int = 0) -> Any:
        return self._c("GET", "/events/stream", params={"after": after})

    @endpoint("GET", "/webhooks")
    def webhooks(self) -> Any:
        return self._c("GET", "/webhooks")

    @endpoint("POST", "/webhooks")
    def create_webhook(self, name: str, url: str, event_types: list[str] | None = None,
                       description: str = "") -> Any:
        return self._c("POST", "/webhooks", json_body={
            "name": name, "url": url, "event_types": event_types or [],
            "description": description})

    @endpoint("DELETE", "/webhooks/{webhook_id}")
    def delete_webhook(self, webhook_id: str) -> Any:
        return self._c("DELETE", f"/webhooks/{seg(webhook_id)}")

    @endpoint("GET", "/webhooks/{webhook_id}/deliveries")
    def deliveries(self, webhook_id: str) -> Any:
        return self._c("GET", f"/webhooks/{seg(webhook_id)}/deliveries")

    @endpoint("POST", "/webhooks/{webhook_id}/ping")
    def ping(self, webhook_id: str) -> Any:
        return self._c("POST", f"/webhooks/{seg(webhook_id)}/ping")


class Custody(_Resource):
    """Anchoring the audit chain outside MAYA, and effective licences (§29.6)."""

    @endpoint("GET", "/custody/anchors")
    def anchors(self) -> Any:
        return self._c("GET", "/custody/anchors")

    @endpoint("POST", "/custody/anchor")
    def anchor(self) -> Any:
        return self._c("POST", "/custody/anchor")

    @endpoint("GET", "/custody/verify")
    def verify(self) -> Any:
        return self._c("GET", "/custody/verify")

    @endpoint("GET", "/licences")
    def licence(self, kind: str, ref: str) -> Any:
        return self._c("GET", "/licences", params={"kind": kind, "ref": ref})


class Jobs(_Resource):
    @endpoint("GET", "/jobs")
    def list(self, all: bool = False) -> Any:
        return self._c("GET", "/jobs", params={"all": all})

    @endpoint("GET", "/jobs/{job_id}")
    def get(self, job_id: str) -> Any:
        return self._c("GET", f"/jobs/{seg(job_id)}")

    @endpoint("POST", "/jobs/{job_id}/cancel")
    def cancel(self, job_id: str) -> Any:
        return self._c("POST", f"/jobs/{seg(job_id)}/cancel")

    @endpoint("POST", "/jobs/{job_id}/retry")
    def retry(self, job_id: str) -> Any:
        return self._c("POST", f"/jobs/{seg(job_id)}/retry")

    @endpoint("GET", "/jobs/{job_id}/events")
    def events(self, job_id: str) -> Any:
        return self._c("GET", f"/jobs/{seg(job_id)}/events")
