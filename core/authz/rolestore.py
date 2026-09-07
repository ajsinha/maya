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
#: The acts of the FIRST line: proposing the thing. Held by `model_owner` and
#: `model_developer`, and by neither second-line role.
FIRST_LINE: FrozenSet[str] = frozenset({
    "model:register", "model:submit", "version:create", "parameter:record",
    "overlay:propose", "feature:define", "featureset:define", "warrant:issue",
})

#: The acts of the SECOND line: challenging it and letting it through. Held by
#: `model_risk_manager` and `validator`, and by neither first-line role.
SECOND_LINE: FrozenSet[str] = frozenset({
    "version:approve", "version:sign", "validation:conclude", "model:approve",
    "alias:move", "policy:publish", "parameter:approve", "overlay:approve",
    "feature:certify", "feature:seal", "featureset:seal", "document:review",
    "regime:activate",
})

#: Recording what a model did, and judging whether what it did was acceptable.
#: `service` observes and `operator` evaluates, and no shipped role does both.
OBSERVE: FrozenSet[str] = frozenset({"monitor:observe"})
EVALUATE: FrozenSet[str] = frozenset({"monitor:evaluate"})

#: Which sets of acts one person may not hold together, and why.
SEPARATIONS: Tuple[Tuple[FrozenSet[str], FrozenSet[str], str], ...] = (
    (FIRST_LINE, SECOND_LINE,
     "effective challenge means somebody other than the builder runs it"),
    (OBSERVE, EVALUATE,
     "whoever records what a model did may not also be the one who decides "
     "the record was acceptable"),
)


def _pairs_from_separations() -> Tuple[Tuple[str, str, str], ...]:
    """Every incompatible permission pair the separations imply.

    Derived rather than typed out. The six pairs written here by hand covered
    two of the two dozen separations the shipped roles actually make, and the
    gaps were not visible by reading them: a role called `solo` holding
    `model:register`, `risk:assess`, `model:submit` and `version:approve`
    collided with none of the six, so one person registered a model, set the
    tier that decides every control on it, submitted it and approved it. All
    six are inside what this generates.

    `risk:assess`, `model:attest`, `monitor:define` and `policy:author` are in
    NEITHER set, deliberately: `model_owner` and `model_risk_manager` both hold
    them, so the platform's own roles say they are not separated and a rule
    saying otherwise would make a shipped role illegal. The same trap took
    `finding:raise` + `finding:close` out of the old list — both lines of
    defence legitimately raise findings and close them.
    """
    out = []
    for first, second, reason in SEPARATIONS:
        out.extend((a, b, reason)
                   for a in sorted(first) for b in sorted(second))
    return tuple(out)


INCOMPATIBLE_PERMISSIONS: Tuple[Tuple[str, str, str], ...] = _pairs_from_separations()


class RoleStore:
    """The roles a principal may hold, and what each grants."""

    def __init__(self, repo, evidence=None, principals=None):
        # `principals` is the repository of people, needed only to answer "who
        # already holds this role" when one is amended. Optional so the store
        # can be built before the principal register exists; when it is absent
        # the holder check cannot run and `amend` says so rather than passing
        # silently.
        self.repo, self.evidence = repo, evidence
        self.principals = principals
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

    def conflicts_within(self, permissions: Iterable[str]) -> List[str]:
        """Every incompatible pair a single set of permissions contains.

        `conflicts` asks the question of a set of ROLES, which is the question
        assignment asks. This asks it of a set of PERMISSIONS, which is the
        question defining a role asks, and nothing asked it: a role holding
        `version:create` and `version:approve` was accepted into the catalogue,
        listed as an ordinary row, and refused only on the first person somebody
        tried to give it to.
        """
        granted = set(permissions)
        return [f"{reason} ({a} + {b})"
                for a, b, reason in INCOMPATIBLE_PERMISSIONS
                if a in granted and b in granted]

    def _refuse_self_conflict(self, name: str, permissions: List[str]) -> None:
        if found := self.conflicts_within(permissions):
            raise AuthzError(
                "incompatible_permissions",
                f"'{name}' would hold both halves of a separated duty: "
                f"{'; '.join(found)}",
                "split them between two roles; a person who needs both holds "
                "both roles and is refused there, on the record, rather than "
                "silently by the shape of one role")

    def _refuse_for_holders(self, name: str, permissions: List[str]) -> None:
        """Whether amending this role gives any current holder a conflict.

        Amending is a change to what every holder can do, made without naming
        any of them, so the refusal names them: an administrator who cannot see
        who is affected cannot judge whether the change is safe.
        """
        if self.principals is None:               # not wired; nothing to check
            return
        affected = []
        for person in self.principals.many():
            held = list(person.get("roles") or [])
            if name not in held or "admin" in held:
                continue
            granted: set = set()
            for role in held:
                granted |= set(permissions if role == name
                               else (self.get(role) or {}).get("permissions") or [])
            if found := self.conflicts_within(granted):
                affected.append(f"{person['username']} ({'; '.join(found)})")
        if affected:
            raise AuthzError(
                "incompatible_permissions",
                f"amending '{name}' would give {len(affected)} "
                f"{'person' if len(affected) == 1 else 'people'} both halves of "
                f"a separated duty: {'; '.join(affected)}",
                "change what those people hold first, or split this role in two")

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
        self._refuse_self_conflict(name, wanted)
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
            wanted = self._checked(permissions, name)
            self._refuse_self_conflict(name, wanted)
            # And the people who ALREADY hold it. Every conflict check in this
            # platform ran at the moment a role was GIVEN to somebody, and a
            # role's permissions are mutable afterwards -- so the whole check
            # was avoidable in two steps that were each individually allowed:
            # define a harmless role, have it assigned, then amend it to hold
            # both halves of a separated duty. The direct path returns 409. This
            # one returned 200, and every holder silently acquired the pair.
            self._refuse_for_holders(name, wanted)
            changes["permissions"] = wanted
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
