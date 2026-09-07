"""
MAYA — principals, roles and the authorisation surface.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Managing who may do what is itself a governed act, so every change here is
recorded on the evidence chain like any other. `/me` is deliberately open to any
authenticated principal: a person should always be able to see what they are
allowed to do without asking an administrator, and a permission system nobody
can inspect is one people work around.
"""
from __future__ import annotations

from typing import List, Optional

from fastapi import Query, Request
from pydantic import Field

from core.authz.common import PERMISSIONS
from core.authz import INCOMPATIBLE_ROLES
from routes.base import Body, Routes


class PrincipalIn(Body):
    username: str
    display_name: str
    roles: List[str]
    password: Optional[str] = None
    kind: str = "person"
    email: Optional[str] = None
    legal_entities: List[str] = Field(default_factory=list)
    domains: List[str] = Field(default_factory=list)
    allow_conflicts: bool = False


class PasswordIn(Body):
    password: str


class RolesIn(Body):
    roles: List[str]
    allow_conflicts: bool = False


class RoleIn(Body):
    name: str
    description: str
    permissions: List[str]


class RoleAmendIn(Body):
    description: Optional[str] = None
    permissions: Optional[List[str]] = None


class ApiKeyIn(Body):
    username: str
    name: str
    #: Empty means everything the principal holds — stated rather than implied,
    #: because a key replacing a password legitimately needs that and a reader
    #: should not have to infer it from a blank field.
    scopes: List[str] = Field(default_factory=list)
    lifetime_days: int = 90


class RevokeKeyIn(Body):
    reason: str


class PrincipalRoutes(Routes):
    def register(self) -> None:
        people, authz = self.ctx["principals"], self.ctx["authz"]
        api = self.api

        # ----------------------------------------------------------- roles
        @self.app.post(f"{api}/roles", status_code=201, tags=["authorisation"])
        def create_role(request: Request, body: RoleIn):
            """Define a role.

            Roles were a Python dictionary, which is fine for the eight this
            platform ships and wrong for everything a bank has — a *Model
            Validation Team Lead*, a *Regional MRM* — each of which meant
            editing source and redeploying. Administration that requires a
            release is not administration.

            Every permission is checked against the closed set: a role granting
            something nothing checks reads as authority and is not.
            """
            who = self.authorise(
                request, "principal:manage",
                # Administering principals is not about one model, and
                # nothing checked scope for it: `principal:manage` is not
                # in MODEL_SCOPED, so ten call sites passed no model and no
                # `estate_wide` and the scope gate never ran. A principal
                # restricted to one legal entity could create accounts,
                # grant roles, suspend people and reset the password of the
                # global administrator. Whoever may decide who can act on
                # the register may act on all of it, so this requires an
                # unrestricted scope.
                estate_wide="administering principals decides who may act "
                            "anywhere on the register")
            return self.guard(lambda: self.ctx["roles"].create(
                body.name, body.description, body.permissions,
                actor=self.actor(who)))

        @self.app.put(f"{api}/roles/{{name}}", tags=["authorisation"])
        def amend_role(request: Request, name: str, body: RoleAmendIn):
            """Change a role somebody here defined. Not one that ships."""
            who = self.authorise(
                request, "principal:manage",
                # Administering principals is not about one model, and
                # nothing checked scope for it: `principal:manage` is not
                # in MODEL_SCOPED, so ten call sites passed no model and no
                # `estate_wide` and the scope gate never ran. A principal
                # restricted to one legal entity could create accounts,
                # grant roles, suspend people and reset the password of the
                # global administrator. Whoever may decide who can act on
                # the register may act on all of it, so this requires an
                # unrestricted scope.
                estate_wide="administering principals decides who may act "
                            "anywhere on the register")
            return self.guard(lambda: self.ctx["roles"].amend(
                name, description=body.description,
                permissions=body.permissions, actor=self.actor(who)))

        @self.app.delete(f"{api}/roles/{{name}}", tags=["authorisation"])
        def remove_role(request: Request, name: str):
            """Remove a role nobody holds — the reference rule, one layer up."""
            who = self.authorise(
                request, "principal:manage",
                # Administering principals is not about one model, and
                # nothing checked scope for it: `principal:manage` is not
                # in MODEL_SCOPED, so ten call sites passed no model and no
                # `estate_wide` and the scope gate never ran. A principal
                # restricted to one legal entity could create accounts,
                # grant roles, suspend people and reset the password of the
                # global administrator. Whoever may decide who can act on
                # the register may act on all of it, so this requires an
                # unrestricted scope.
                estate_wide="administering principals decides who may act "
                            "anywhere on the register")
            holders = [p["username"] for p in people.list()
                       if name in (p.get("roles") or [])]
            return self.guard(lambda: self.ctx["roles"].remove(
                name, actor=self.actor(who), holders=holders))

        # -------------------------------------------------------- API keys
        @self.app.get(f"{api}/api-keys", tags=["authorisation"])
        def list_keys(request: Request, username: str = Query(None)):
            """Every key, or one principal's, with what needs looking at.

            No secret is here and none can be: what is stored is a hash. The
            `prefix` is enough to match a key to a leaked string without
            holding either.
            """
            self.authorise(request, "principal:read")
            keys = self.ctx["api_keys"]
            if username:
                return {"username": username,
                        "keys": self.guard(lambda: keys.for_principal(username))}
            return self.guard(keys.report)

        @self.app.post(f"{api}/api-keys", status_code=201,
                       tags=["authorisation"])
        def issue_key(request: Request, body: ApiKeyIn):
            """Mint a key. The secret is in this response and nowhere else.

            Not in a log, not in the evidence chain, not on the row. The
            evidence records that a key was issued, to whom, with what scope and
            until when — which is everything a reviewer needs and nothing an
            attacker can use.
            """
            who = self.authorise(
                request, "principal:manage",
                # Administering principals is not about one model, and
                # nothing checked scope for it: `principal:manage` is not
                # in MODEL_SCOPED, so ten call sites passed no model and no
                # `estate_wide` and the scope gate never ran. A principal
                # restricted to one legal entity could create accounts,
                # grant roles, suspend people and reset the password of the
                # global administrator. Whoever may decide who can act on
                # the register may act on all of it, so this requires an
                # unrestricted scope.
                estate_wide="administering principals decides who may act "
                            "anywhere on the register")
            return self.guard(lambda: self.ctx["api_keys"].issue(
                body.username, body.name, scopes=body.scopes,
                lifetime_days=body.lifetime_days, actor=self.actor(who)))

        @self.app.post(f"{api}/api-keys/{{key_id}}/revoke",
                       tags=["authorisation"])
        def revoke_key(request: Request, key_id: str, body: RevokeKeyIn):
            """Withdraw one. The row stays — it is what says the key existed."""
            who = self.authorise(
                request, "principal:manage",
                # Administering principals is not about one model, and
                # nothing checked scope for it: `principal:manage` is not
                # in MODEL_SCOPED, so ten call sites passed no model and no
                # `estate_wide` and the scope gate never ran. A principal
                # restricted to one legal entity could create accounts,
                # grant roles, suspend people and reset the password of the
                # global administrator. Whoever may decide who can act on
                # the register may act on all of it, so this requires an
                # unrestricted scope.
                estate_wide="administering principals decides who may act "
                            "anywhere on the register")
            return self.guard(lambda: self.ctx["api_keys"].revoke(
                key_id, body.reason, actor=self.actor(who)))

        @self.app.get(f"{api}/me", tags=["authorisation"])
        def me(request: Request):
            """Who am I, and what may I do? Open to any authenticated caller."""
            return authz.explain(self.principal(request))

        @self.app.get(f"{api}/roles", tags=["authorisation"])
        def roles(request: Request):
            """The role catalogue, read from the register.

            Two kinds of conflict are published, because neither catches what
            the other does. **Role pairs** are about independence — which line
            somebody is in — and `auditor + model_developer` has no permission
            collision at all, since an auditor holds reads and `finding:raise`.
            **Permission pairs** are about capability, and they are the ones a
            role somebody defines could otherwise smuggle past a name check.
            """
            # Two documents behind one path, because the two halves are not
            # equally sensitive. Which roles EXIST and what each is for is
            # ordinary product information — a developer reading "who should I
            # ask for this?" needs it. What each role GRANTS, the whole
            # permission vocabulary, and which duties are separated is a map of
            # where the controls are and which pairs are the escalation paths,
            # and it went to any authenticated caller, including a service key
            # scoped to a single permission.
            who = self.principal(request)
            detailed = self.ctx["authz"].permits(who, "principal:read")
            from core.authz.rolestore import INCOMPATIBLE_PERMISSIONS

            store = self.ctx["roles"]
            catalogue = {
                "roles": [{"name": r["name"], "description": r["description"],
                           "built_in": bool(r.get("built_in")),
                           **({"permissions": sorted(r.get("permissions") or [])}
                              if detailed else {})}
                          for r in store.all()],
                "detailed": detailed,
            }
            if not detailed:
                catalogue["detail"] = (
                    "role names and what each is for. What each GRANTS, and "
                    "which duties may not be held together, needs "
                    "'principal:read'.")
                return catalogue
            return {
                **catalogue,
                "incompatible": [{"roles": [a, b], "reason": reason}
                                 for a, b, reason in INCOMPATIBLE_ROLES],
                "incompatible_permissions": [
                    {"permissions": [a, b], "reason": reason}
                    for a, b, reason in INCOMPATIBLE_PERMISSIONS],
                "permissions": sorted(PERMISSIONS),
                "segregation": self.ctx["authz"].segregation.describe()
                if self.ctx["authz"].segregation else [],
                "detail": "roles live in the register; the eight marked "
                          "built_in ship with the platform and every document "
                          "here names them, so they may be read and not edited",
            }

        @self.app.get(f"{api}/principals", tags=["authorisation"])
        def list_principals(request: Request):
            self.authorise(request, "principal:read")
            return {"principals": people.list()}

        @self.app.post(f"{api}/principals", status_code=201, tags=["authorisation"])
        def create_principal(request: Request, body: PrincipalIn):
            who = self.authorise(
                request, "principal:manage",
                # Administering principals is not about one model, and
                # nothing checked scope for it: `principal:manage` is not
                # in MODEL_SCOPED, so ten call sites passed no model and no
                # `estate_wide` and the scope gate never ran. A principal
                # restricted to one legal entity could create accounts,
                # grant roles, suspend people and reset the password of the
                # global administrator. Whoever may decide who can act on
                # the register may act on all of it, so this requires an
                # unrestricted scope.
                estate_wide="administering principals decides who may act "
                            "anywhere on the register")
            return self.guard(lambda: people.create(
                body.username, body.display_name, body.roles, body.password,
                body.kind, body.email, body.legal_entities, body.domains,
                actor=self.actor(who), allow_conflicts=body.allow_conflicts))

        @self.app.put(f"{api}/principals/{{username}}/roles", tags=["authorisation"])
        def set_roles(request: Request, username: str, body: RolesIn):
            who = self.authorise(
                request, "principal:manage",
                # Administering principals is not about one model, and
                # nothing checked scope for it: `principal:manage` is not
                # in MODEL_SCOPED, so ten call sites passed no model and no
                # `estate_wide` and the scope gate never ran. A principal
                # restricted to one legal entity could create accounts,
                # grant roles, suspend people and reset the password of the
                # global administrator. Whoever may decide who can act on
                # the register may act on all of it, so this requires an
                # unrestricted scope.
                estate_wide="administering principals decides who may act "
                            "anywhere on the register")
            return self.guard(lambda: people.set_roles(
                username, body.roles, actor=self.actor(who),
                allow_conflicts=body.allow_conflicts))

        @self.app.post(f"{api}/principals/{{username}}/suspend", tags=["authorisation"])
        def suspend(request: Request, username: str):
            who = self.authorise(
                request, "principal:manage",
                # Administering principals is not about one model, and
                # nothing checked scope for it: `principal:manage` is not
                # in MODEL_SCOPED, so ten call sites passed no model and no
                # `estate_wide` and the scope gate never ran. A principal
                # restricted to one legal entity could create accounts,
                # grant roles, suspend people and reset the password of the
                # global administrator. Whoever may decide who can act on
                # the register may act on all of it, so this requires an
                # unrestricted scope.
                estate_wide="administering principals decides who may act "
                            "anywhere on the register")
            return self.guard(lambda: people.suspend(username, actor=self.actor(who)))

        # Administration was one-way — create, set roles, suspend — so a
        # suspension made in error, or for a fortnight's leave, could only be
        # undone with an UPDATE against the database, and a forgotten password
        # meant a new account and an evidence chain naming two people who are
        # one person.
        @self.app.post(f"{api}/principals/{{username}}/reinstate",
                       tags=["authorisation"])
        def reinstate(request: Request, username: str):
            """Return a suspended principal to service. Recorded, like the
            suspension it undoes."""
            who = self.authorise(
                request, "principal:manage",
                # Administering principals is not about one model, and
                # nothing checked scope for it: `principal:manage` is not
                # in MODEL_SCOPED, so ten call sites passed no model and no
                # `estate_wide` and the scope gate never ran. A principal
                # restricted to one legal entity could create accounts,
                # grant roles, suspend people and reset the password of the
                # global administrator. Whoever may decide who can act on
                # the register may act on all of it, so this requires an
                # unrestricted scope.
                estate_wide="administering principals decides who may act "
                            "anywhere on the register")
            return self.guard(lambda: people.reinstate(username,
                                                       actor=self.actor(who)))

        @self.app.post(f"{api}/principals/{{username}}/password",
                       tags=["authorisation"])
        def set_password(request: Request, username: str, body: PasswordIn):
            """Set a principal's password.

            The password is never logged and never lands on the evidence chain.
            The fact that an administrator set it does, because somebody who can
            silently take over an account is somebody nobody can audit.
            """
            who = self.authorise(
                request, "principal:manage",
                # Administering principals is not about one model, and
                # nothing checked scope for it: `principal:manage` is not
                # in MODEL_SCOPED, so ten call sites passed no model and no
                # `estate_wide` and the scope gate never ran. A principal
                # restricted to one legal entity could create accounts,
                # grant roles, suspend people and reset the password of the
                # global administrator. Whoever may decide who can act on
                # the register may act on all of it, so this requires an
                # unrestricted scope.
                estate_wide="administering principals decides who may act "
                            "anywhere on the register")
            return self.guard(lambda: people.set_password(
                username, body.password, actor=self.actor(who)))
