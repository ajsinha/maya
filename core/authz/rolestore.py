"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Roles, in the register rather than in the source.

They were a Python dictionary. That is fine for the eight this platform ships
and wrong for everything a bank actually has: a *Model Validation Team Lead*, a
*Regional MRM*, a *Quant Developer with production read* — each of which meant
editing `core/authz/roles.py` and redeploying. **Administration that requires a
release is not administration.**

Three things had to be got right, and the third is the one that matters.

**The eight built-in roles stay, and stay unchanged.** They are seeded from the
definitions that used to be the whole story and marked `built_in`. They may be
read; they may not be edited or removed. Every document, tutorial and test in
this repository refers to them by name, and a platform whose vocabulary can be
renamed underneath its own documentation is one where the documentation is
wrong.

**A role may only grant permissions the platform checks.** The permission set is
closed and validated on the way in. A role granting `model:bless` reads as
authority and is not.

**The incompatible-roles check had to stop being about role NAMES.** It compared
the *names* a principal holds against six known-bad pairs — which works exactly
as long as the only roles are the ones that were named. The moment somebody can
define a role, they can define one holding `version:create` and `version:approve`
together, and the pair check sees a single unfamiliar name and passes it. That
is the same defect the pairs exist to prevent, wearing a new name.

So the check is over **permissions**. The six pairs are expressed as the pairs of
permissions that make them dangerous, and a principal is refused when their
effective set contains both halves of one — however many roles it took to get
there, and whatever those roles are called.
"""
from __future__ import annotations

import time
from typing import Any, Dict, FrozenSet, Iterable, List, Optional, Tuple

from core.authz.common import AuthzError, require_known
from core.authz.roles import DESCRIPTIONS, ROLES

#: Conflicts expressed as PERMISSIONS, which is what a custom role can smuggle
#: past a check over role names.
#:
#: These do not replace the role pairs in `roles.py` — running both against
#: every pair of shipped roles showed why. Two conflicts are caught by name and
#: by nothing else: `auditor + model_developer` and `auditor + model_owner`, the
#: third line building or owning what it audits. There is no permission
#: collision there at all — an auditor holds reads and `finding:raise` — because
#: the conflict is about which LINE a person is in, and a line is not a
#: capability. A permission check cannot see it.
#:
#: The reverse is also true, which is the reason for this list: a role somebody
#: defines can hold `version:create` and `version:approve` together, and a name
#: check sees one unfamiliar name and passes it.
#:
#: So both run. Written out rather than derived from the role pairs, because
#: deriving them would inherit exactly the assumption being fixed.
#:
#: `finding:raise` + `finding:close` was in this list and was wrong. A validator
#: and a model risk manager both legitimately raise findings and close them —
#: that is the second line's job. The third line's constraint is about building
#: what it audits, and it is a role pair.
INCOMPATIBLE_PERMISSIONS: Tuple[Tuple[str, str, str], ...] = (
    ("version:create", "version:approve",
     "creating a version and approving one is a first line approving its own "
     "work"),
    ("version:create", "version:sign",
     "the person who built a version may not sign its approval quorum"),
    ("version:create", "validation:conclude",
     "effective challenge is not effective when the builder concludes it"),
    ("model:register", "version:approve",
     "an owner who can also approve versions of their own models defeats "
     "second-line challenge"),
    ("model:register", "version:sign",
     "an owner signing the quorum on their own model is signing for themselves"),
    ("model:register", "validation:conclude",
     "an owner concluding their own model's validation is signing off their "
     "own challenge"),
)


class RoleStore:
    """The roles a principal may hold, and what each grants."""

    def __init__(self, repo, evidence=None):
        self.repo, self.evidence = repo, evidence
        self._seed()

    # ------------------------------------------------------------------- seed
    def _seed(self) -> None:
        """Put the shipped roles in the register, once.

        Idempotent by name, and it UPDATES a built-in whose permissions have
        moved — a permission added to `model_developer` in the source with the
        row left behind would be a role that means one thing in the code and
        another in the database, which is the two-records problem this whole
        platform argues against.
        """
        for name, permissions in ROLES.items():
            wanted = sorted(permissions)
            row = self.repo.one(name=name)
            if row is None:
                self.repo.add({"name": name,
                               "description": DESCRIPTIONS.get(name, ""),
                               "permissions": wanted, "built_in": 1,
                               "created_at": time.time(),
                               "created_by": "system"})
            elif row.get("built_in") and sorted(row.get("permissions") or []) != wanted:
                self.repo.set({"permissions": wanted,
                               "description": DESCRIPTIONS.get(name, ""),
                               "updated_at": time.time(),
                               "updated_by": "system"}, id=row["id"])

    # ------------------------------------------------------------------ query
    def all(self) -> List[Dict[str, Any]]:
        return sorted(self.repo.many(), key=lambda r: (not r["built_in"],
                                                       r["name"]))

    def get(self, name: str) -> Optional[Dict[str, Any]]:
        return self.repo.one(name=name)

    def require(self, name: str) -> Dict[str, Any]:
        row = self.get(name)
        if row is None:
            known = ", ".join(sorted(r["name"] for r in self.repo.many()))
            raise AuthzError("unknown_role", f"'{name}' is not a recognised role",
                             f"known roles are {known}")
        return row

    def permissions_for(self, roles: Iterable[str]) -> FrozenSet[str]:
        """The union of a principal's roles. An unknown role is refused."""
        granted: set = set()
        for name in roles:
            granted |= set(self.require(name).get("permissions") or [])
        return frozenset(granted)

    # -------------------------------------------------------------- conflicts
    def conflicts(self, roles: Iterable[str]) -> List[str]:
        """Every incompatible pair this set of roles produces between them.

        **Both checks run**, because neither catches what the other does.

        The role pairs are about *independence* — which line somebody is in —
        and `auditor + model_developer` has no permission collision at all,
        since an auditor holds reads and `finding:raise`. A permission check
        cannot see it, because a line is not a capability.

        The permission pairs are about *capability*, and they are the ones a
        role somebody defines can otherwise smuggle past: define one holding
        `version:create` and `version:approve` and a name check sees a single
        unfamiliar name and passes it.
        """
        from core.authz.roles import conflicts as by_role_name

        held = list(roles)
        if "admin" in held:
            return []          # break-glass is a conscious exception
        found = list(by_role_name(held))
        granted = self.permissions_for(held)
        found += [f"{reason} ({a} + {b})"
                  for a, b, reason in INCOMPATIBLE_PERMISSIONS
                  if a in granted and b in granted]
        return found

    # ------------------------------------------------------------------ write
    def create(self, name: str, description: str, permissions: List[str],
               actor: str = "system") -> Dict[str, Any]:
        """Define a role. Every permission is checked against the closed set."""
        name = (name or "").strip()
        if not name:
            raise AuthzError("role_name_required",
                             "a role needs a name", "name it after the job")
        if self.get(name):
            raise AuthzError("role_exists", f"there is already a role '{name}'",
                             "edit that one, or choose another name")
        if not (description or "").strip():
            raise AuthzError(
                "role_description_required",
                "a role needs a description saying what job it is for; a list "
                "of permissions is not an explanation of who should hold them",
                "say what this role is for in one sentence")
        wanted = self._checked(permissions, name)
        row = self.repo.add({
            "name": name, "description": description.strip(),
            "permissions": wanted, "built_in": 0,
            "created_at": time.time(), "created_by": actor})
        self._record("role_created", row, {"permissions": wanted}, actor)
        return row

    def amend(self, name: str, *, description: Optional[str] = None,
              permissions: Optional[List[str]] = None,
              actor: str = "system") -> Dict[str, Any]:
        """Change a role. Not a built-in one."""
        row = self.require(name)
        if row.get("built_in"):
            raise AuthzError(
                "built_in_role",
                f"'{name}' is one of the roles this platform ships, and every "
                f"document, tutorial and test refers to it by name; changing "
                f"what it grants would make all of them wrong without touching "
                f"any of them",
                "create a role of your own with the permissions you want")
        changes: Dict[str, Any] = {"updated_at": time.time(),
                                   "updated_by": actor}
        if description is not None:
            changes["description"] = description.strip()
        if permissions is not None:
            changes["permissions"] = self._checked(permissions, name)
        self.repo.set(changes, id=row["id"])
        after = self.require(name)
        self._record("role_amended", after,
                     {"permissions": after.get("permissions")}, actor)
        return after

    def remove(self, name: str, actor: str = "system",
               holders: Optional[List[str]] = None) -> Dict[str, Any]:
        """Delete a role nobody holds.

        The reference rule, one layer up: a role somebody holds cannot simply
        stop existing, or their next request resolves permissions against a name
        that is not there.
        """
        row = self.require(name)
        if row.get("built_in"):
            raise AuthzError(
                "built_in_role",
                f"'{name}' is one of the roles this platform ships and cannot "
                f"be removed",
                "remove it from the principals who hold it instead")
        if holders:
            raise AuthzError(
                "role_in_use",
                f"'{name}' is held by {', '.join(sorted(holders))}, and a role "
                f"that stops existing while somebody holds it makes their next "
                f"request resolve against a name that is not there",
                "change those principals' roles first")
        self.repo.remove(id=row["id"])
        self._record("role_removed", row, {}, actor)
        return {"name": name, "removed": True}

    # ------------------------------------------------------------------ inner
    @staticmethod
    def _checked(permissions: Iterable[str], role: str) -> List[str]:
        wanted = sorted({p for p in permissions})
        if not wanted:
            raise AuthzError(
                "role_grants_nothing",
                f"'{role}' would grant no permissions; somebody holding it "
                f"could sign in and do nothing, which reads as a fault rather "
                f"than as the empty grant it is",
                "grant at least one permission, or do not define the role")
        for permission in wanted:
            require_known(permission)
        return wanted

    def _record(self, kind: str, row: Dict[str, Any], payload: Dict[str, Any],
                actor: str) -> None:
        if self.evidence is None:
            return
        self.evidence.append(kind, "role", row["id"],
                             {"name": row["name"], **payload}, actor=actor)
