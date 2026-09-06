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

from fastapi import Request
from pydantic import Field

from core.authz import DESCRIPTIONS, INCOMPATIBLE_ROLES, ROLES
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


class PrincipalRoutes(Routes):
    def register(self) -> None:
        people, authz = self.ctx["principals"], self.ctx["authz"]
        api = self.api

        @self.app.get(f"{api}/me", tags=["authorisation"])
        def me(request: Request):
            """Who am I, and what may I do? Open to any authenticated caller."""
            return authz.explain(self.principal(request))

        @self.app.get(f"{api}/roles", tags=["authorisation"])
        def roles(request: Request):
            """The role catalogue, with the pairs nobody should hold together."""
            self.principal(request)
            return {
                "roles": [{"name": name, "description": DESCRIPTIONS.get(name, ""),
                           "permissions": sorted(permissions)}
                          for name, permissions in sorted(ROLES.items())],
                "incompatible": [{"roles": [a, b], "reason": reason}
                                 for a, b, reason in INCOMPATIBLE_ROLES],
                "segregation": self.ctx["authz"].segregation.describe()
                if self.ctx["authz"].segregation else [],
            }

        @self.app.get(f"{api}/principals", tags=["authorisation"])
        def list_principals(request: Request):
            self.authorise(request, "principal:read")
            return {"principals": people.list()}

        @self.app.post(f"{api}/principals", status_code=201, tags=["authorisation"])
        def create_principal(request: Request, body: PrincipalIn):
            who = self.authorise(request, "principal:manage")
            return self.guard(lambda: people.create(
                body.username, body.display_name, body.roles, body.password,
                body.kind, body.email, body.legal_entities, body.domains,
                actor=self.actor(who), allow_conflicts=body.allow_conflicts))

        @self.app.put(f"{api}/principals/{{username}}/roles", tags=["authorisation"])
        def set_roles(request: Request, username: str, body: RolesIn):
            who = self.authorise(request, "principal:manage")
            return self.guard(lambda: people.set_roles(
                username, body.roles, actor=self.actor(who),
                allow_conflicts=body.allow_conflicts))

        @self.app.post(f"{api}/principals/{{username}}/suspend", tags=["authorisation"])
        def suspend(request: Request, username: str):
            who = self.authorise(request, "principal:manage")
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
            who = self.authorise(request, "principal:manage")
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
            who = self.authorise(request, "principal:manage")
            return self.guard(lambda: people.set_password(
                username, body.password, actor=self.actor(who)))
