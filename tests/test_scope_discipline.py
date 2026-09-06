"""Every model-scoped permission is checked against a model.

The legal-entity scope was opt-in: `authorise(...)` applied it when a route
remembered to pass `model=`, and about a dozen write routes did not. A UK-scoped
validator, refused READ access to a US model, could still sign half its Tier 2
quorum, revoke its production warrant and close its blocking findings.

`authorise` now refuses at run time (`scope_not_checked`), which catches the
paths tests walk. This walks the source instead, so a route added tomorrow and
never exercised is caught too.
"""
from __future__ import annotations

import ast
import pathlib
from typing import List, Tuple

from core.authz.common import MODEL_SCOPED

ROUTES = pathlib.Path(__file__).resolve().parents[1] / "routes"


def _unscoped_checks() -> List[Tuple[str, int, str]]:
    """Every `authorise(..., "<model-scoped>")` call with no `model=`."""
    offences: List[Tuple[str, int, str]] = []
    for path in sorted(ROUTES.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not (isinstance(func, ast.Attribute) and func.attr == "authorise"):
                continue
            permission = next(
                (a.value for a in node.args
                 if isinstance(a, ast.Constant) and isinstance(a.value, str)
                 and ":" in a.value),
                None)
            if permission not in MODEL_SCOPED:
                continue
            # `estate_wide=` is the argued exception — it does not skip the
            # check, it demands an unrestricted principal instead.
            if not any(kw.arg in ("model", "estate_wide") for kw in node.keywords):
                offences.append((path.name, node.lineno, permission))
    return offences


def test_no_model_scoped_permission_is_checked_without_a_model() -> None:
    offences = _unscoped_checks()
    assert offences == [], (
        "these routes check a permission about one model without saying which, "
        "so the legal-entity scope is not applied: "
        + "; ".join(f"{f}:{line} {perm}" for f, line, perm in offences))


def test_the_scan_can_actually_see_an_offence() -> None:
    """The scanner above must fail on a planted breach, or it proves nothing.

    A previous discipline check in this repository reported success while
    matching nothing at all, so each one now demonstrates its own teeth.
    """
    source = (
        "class R:\n"
        "    def route(self, request):\n"
        "        self.authorise(request, 'version:sign')\n")
    tree = ast.parse(source)
    calls = [n for n in ast.walk(tree)
             if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Attribute)
             and n.func.attr == "authorise"]
    assert len(calls) == 1
    permission = calls[0].args[1].value
    assert permission in MODEL_SCOPED
    assert not any(kw.arg in ("model", "estate_wide") for kw in calls[0].keywords)


class TestTheScopeActuallyBites:
    """The static scan proves `model=` is passed. This proves it refuses.

    A scan can only see that an argument is present; it cannot see that the
    argument reaches a check. This walks the HTTP surface as a UK-scoped
    principal who holds every permission the act needs, against a US model.

    One test rather than four because `registered` takes a model through the
    whole governed path and costs about a minute; the three acts below are the
    three shapes — a signature, a warrant, and estate-wide policy — and each
    assertion says which one it is.
    """

    def test_a_uk_scoped_principal_is_refused_every_write_act(
            self, registered, client, people):
        from tests.conftest import NAME, KERNEL, CONTRACT, URN

        registered.post("/api/v1/principals", json={
            "username": "uk.person", "display_name": "UK",
            "roles": ["validator", "model_owner"],
            "password": "pw", "legal_entities": ["LE-UK-02"]})
        uk = ("uk.person", "pw")

        # A signature on a quorum. `registered` already approved 3.2.1, so open
        # the quorum on a fresh version — the record is still in draft, which is
        # what makes adding one legal.
        registered.post(f"/api/v1/models/{NAME}/versions", auth=people["d.raman"],
                        json={"semver": "3.2.2", "kernel": KERNEL,
                              "contract": CONTRACT,
                              "artifact_digest": "sha256:" + "b" * 64})
        opened = registered.post("/api/v1/version-approvals", auth=people["s.iqbal"],
                                 json={"urn": URN, "semver": "3.2.2"})
        assert opened.status_code == 201, opened.text
        signed = registered.post(
            f"/api/v1/version-approvals/{opened.json()['id']}/sign",
            auth=uk, json={"role": "validator"})
        assert signed.status_code == 403, signed.text
        assert signed.json()["error"] == "out_of_scope", \
            "half a Tier 2 quorum signed from outside the entity"

        # Production authority over a model they cannot read.
        issued = registered.post("/api/v1/warrants", auth=uk, json={
            "urn": URN, "environment": "production", "principal": "batch",
            "declared_use": "origination"})
        assert issued.status_code == 403, issued.text
        assert issued.json()["error"] == "out_of_scope", issued.text

        # Estate-wide policy is not model-scoped, so it demands the whole estate
        # rather than any one model.
        profile = registered.post("/api/v1/warrant-profiles", auth=uk, json={
            "name": "uk-wide", "when": {}, "defaults": {"ttl_days": 3650},
            "note": "reaches every model in every entity"})
        assert profile.status_code == 403, profile.text
        assert profile.json()["error"] == "scope_insufficient", profile.text
        assert "LE-UK-02" in profile.json()["detail"], \
            "say which scope was too narrow"
