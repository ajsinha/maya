"""
MAYA SDK — who may act, and the credentials they act with.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Administering people, roles and API keys was reachable from the SDK only by
constructing raw calls — which reads to a new joiner as *the SDK cannot do
this* rather than *nobody wired it up*, and is the same gap that once left ten
governance subjects unattached.

Every act here goes through the same API the admin screens call, with the same
authorisation, the same incompatible-roles check and the same evidence. There
is no privileged path.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


class Principals:
    """People and services: who exists, what they may do, and who they are not.

    A role is a NAME for a set of permissions, and two roles that together hold
    both halves of a separated duty cannot be given to one person — the refusal
    names the pair and the reason, because "incompatible roles" without the
    pair is a wall rather than a conversation.
    """

    def __init__(self, maya):
        self._maya = maya

    # ------------------------------------------------------------- people
    def list(self) -> Dict[str, Any]:
        """Everyone who may act, and what each one holds."""
        return self._maya.call("GET", "/principals")

    def get(self, username: str) -> Dict[str, Any]:
        return self._maya.call("GET", f"/principals/{username}")

    def create(self, *, username: str, display_name: str,
               roles: List[str], password: str = "",
               kind: str = "person",
               legal_entities: Optional[List[str]] = None,
               domains: Optional[List[str]] = None) -> Dict[str, Any]:
        """Add somebody, or something.

        `kind="service"` for a non-human principal, which signs in to nothing
        and authenticates with an API key — a password names a person and
        carries everything they hold.

        A password is checked against the platform's floor HERE, at creation,
        not only when it is later changed. The moment a weak password is most
        likely to be chosen is the moment the account is made.

        `legal_entities` and `domains` SCOPE what this principal can see. Left
        empty they mean "everything", which is right for an administrator and
        wrong for most people.
        """
        body: Dict[str, Any] = {"username": username,
                                "display_name": display_name,
                                "roles": roles, "kind": kind}
        if password:
            body["password"] = password
        if legal_entities is not None:
            body["legal_entities"] = legal_entities
        if domains is not None:
            body["domains"] = domains
        return self._maya.call("POST", "/principals", json=body)

    def permissions(self, username: str) -> Dict[str, Any]:
        """What this principal can actually do — the UNION of their roles.

        Asked of the platform rather than assembled from the role list, because
        somebody may hold two roles and the union is what decides.
        """
        return self._maya.call("GET", f"/principals/{username}/permissions")

    def set_roles(self, username: str, *, roles: List[str]) -> Dict[str, Any]:
        """Replace what somebody holds. Refused if the result is incompatible."""
        return self._maya.call("POST", f"/principals/{username}/roles",
                               json={"roles": roles})

    def set_password(self, username: str, *, password: str) -> Dict[str, Any]:
        return self._maya.call("POST", f"/principals/{username}/password",
                               json={"password": password})

    # ----------------------------------------------------------- break-glass
    def recertification(self) -> Dict[str, Any]:
        """What an access review decides, and how many accounts nobody has
        looked at.

        The one thing to know before relying on any of it: **it does not time
        out.** An item nobody answered stays `unreviewed`, closing a campaign
        decides nothing about it, and `confirmed` and `unreviewed` are never
        added together — the access nobody looked at is the access most likely
        to be wrong, because the reviewer did not answer for the same reason
        the access is stale.
        """
        return self._maya.call("GET", "/recertification")

    def review(self, reference: str) -> Dict[str, Any]:
        """Where one campaign stands, with `unreviewed` as its own number."""
        return self._maya.call("GET", f"/recertification/{reference}")

    def open_review(self, reference: str, *, reviewer: str, title: str = "",
                    population: Optional[List[str]] = None) -> Dict[str, Any]:
        """Open an access review. A blank population reviews everybody active.

        `reviewer` is named rather than derived: MAYA holds no reporting line,
        and inferring one from roles would put the second line in charge of
        recertifying the first line's managers.
        """
        return self._maya.call("POST", "/recertification", json={
            "reference": reference, "reviewer": reviewer, "title": title,
            "population": list(population or [])})

    def recertify(self, reference: str, principal: str, *, state: str,
                  reason: str = "") -> Dict[str, Any]:
        """Confirm or revoke one person's access. There is no third answer.

        **Revoking removes roles in MAYA's register and nothing else** — not a
        directory, not a database grant, not anybody's job. A revocation needs
        a reason, because a role removed with no reason cannot be told apart
        afterwards from an administrative mistake.
        """
        return self._maya.call("POST",
                               f"/recertification/{reference}/{principal}",
                               json={"state": state, "reason": reason})

    def reassign_review(self, reference: str, *, to: str,
                        reason: str) -> Dict[str, Any]:
        """Hand a campaign to a different reviewer, with a reason.

        Only the named reviewer may answer a campaign, so this is how it moves.
        Reviewers leave, go on secondment, and turn out to be in the population
        they were asked to review; a campaign that cannot be handed over is one
        somebody answers under the previous reviewer's account.
        """
        return self._maya.call("POST",
                               f"/recertification/{reference}/reassign",
                               json={"to": to, "reason": reason})

    def close_review(self, reference: str) -> Dict[str, Any]:
        """Close a campaign. This decides nothing about what was unreviewed,
        and the answer says how many that was."""
        return self._maya.call("POST", f"/recertification/{reference}/close")

    def break_glass(self) -> Dict[str, Any]:
        """Every emergency elevation, and the number that matters.

        Read `unglassed` first. You cannot find break-glass abuse by watching
        break-glass — anybody misusing emergency access would simply not open a
        grant for it — so the figure worth reading is privileged acts that
        happened under **no** grant, derived from the evidence chain rather than
        reported by the people it is about.
        """
        return self._maya.call("GET", "/break-glass")

    def request_break_glass(self, *, reason: str,
                            principal: str = "") -> Dict[str, Any]:
        """Ask for elevation. Nothing is granted by asking.

        Refused with `review_outstanding` if this principal has a closed grant
        nobody has reviewed, which is what makes the mandatory review mandatory:
        a review that can be skipped is a to-do list.
        """
        return self._maya.call("POST", "/break-glass",
                               json={"reason": reason,
                                     "principal": principal})

    def authorise_break_glass(self, reference: str, *,
                              unilateral: bool = False) -> Dict[str, Any]:
        """The second signature, which cannot be the first.

        `unilateral=True` opens it anyway with a shorter window and a flag. Not
        a loophole: refusing outright at three in the morning is how an
        institution ends up with a shared password in a safe, which has no name,
        no reason, no window and no review.
        """
        return self._maya.call("POST",
                               f"/break-glass/{reference}/authorise",
                               json={"unilateral": unilateral})

    def close_break_glass(self, reference: str, *,
                          reason: str = "") -> Dict[str, Any]:
        """End it early. It would have ended anyway."""
        return self._maya.call("POST", f"/break-glass/{reference}/close",
                               json={"reason": reason})

    def under_break_glass(self, reference: str) -> Dict[str, Any]:
        """What was done under it, folded from the evidence chain rather than
        kept in a second log that could disagree with the first."""
        return self._maya.call("GET", f"/break-glass/{reference}/under")

    def review_break_glass(self, reference: str, *, outcome: str,
                           note: str) -> Dict[str, Any]:
        """Somebody reads what was done. Never the person who used it.

        `outcome` is one of `appropriate`, `excessive` or `unwarranted`. The
        list is closed because *looked at it* is not a conclusion, and a review
        with no verdict reads exactly like one nobody did.
        """
        return self._maya.call("POST", f"/break-glass/{reference}/review",
                               json={"outcome": outcome, "note": note})

    def suspend(self, username: str, *, reason: str = "") -> Dict[str, Any]:
        """Switch somebody off. Refused for the last administrator, and for
        yourself — reinstating needs a permission a suspended account no longer
        holds, so a single-administrator instance would have no way back."""
        return self._maya.call("POST", f"/principals/{username}/suspend",
                               json={"reason": reason})

    def reinstate(self, username: str) -> Dict[str, Any]:
        return self._maya.call("POST", f"/principals/{username}/reinstate")

    # -------------------------------------------------------------- roles
    def roles(self) -> Dict[str, Any]:
        """Every role, what it grants, and how many people hold it."""
        return self._maya.call("GET", "/roles")

    def define_role(self, *, name: str, description: str,
                    permissions: List[str]) -> Dict[str, Any]:
        """A role a bank defines for itself.

        Refused if the permissions include both halves of a separated duty —
        the check is on the PERMISSIONS rather than on the role names, so a
        bespoke role cannot reassemble a separation the built-in ones keep
        apart.
        """
        return self._maya.call("POST", "/roles", json={
            "name": name, "description": description,
            "permissions": permissions})

    def amend_role(self, name: str, *, description: Optional[str] = None,
                   permissions: Optional[List[str]] = None) -> Dict[str, Any]:
        body: Dict[str, Any] = {}
        if description is not None:
            body["description"] = description
        if permissions is not None:
            body["permissions"] = permissions
        return self._maya.call("POST", f"/roles/{name}/amend", json=body)

    def vocabulary(self) -> Dict[str, Any]:
        """Every permission that exists. A closed vocabulary: a role naming one
        outside it is refused rather than silently granting nothing."""
        return self._maya.call("GET", "/permissions")


class ApiKeys:
    """How a service authenticates.

    A key names a credential rather than a person: it expires, it can be
    narrowed to a subset of what its principal holds, and it can be revoked
    without touching the account. The secret is in the issuing response and
    nowhere else — not in a log, not on the row, not in the evidence chain,
    which records that a key was issued, to whom, with what scope and until
    when.
    """

    def __init__(self, maya):
        self._maya = maya

    def list(self, *, username: str = "") -> Dict[str, Any]:
        return self._maya.call("GET", "/api-keys",
                               params={"username": username} if username else None)

    def issue(self, *, username: str, name: str,
              scopes: Optional[List[str]] = None,
              lifetime_days: int = 90) -> Dict[str, Any]:
        """Mint one. **The `secret` in the reply is the only copy.**

        Empty `scopes` means everything the principal holds — stated rather
        than implied, because a key replacing a password legitimately needs
        that and a reader should not have to infer it from a blank field.
        """
        return self._maya.call("POST", "/api-keys", json={
            "username": username, "name": name,
            "scopes": scopes or [], "lifetime_days": lifetime_days})

    def revoke(self, key_id: str, *, reason: str) -> Dict[str, Any]:
        """Withdraw it. A revoked key is refused with `key_revoked` rather than
        a generic 401, so a caller can tell "withdrawn" from "expired" from
        "wrong"."""
        return self._maya.call("POST", f"/api-keys/{key_id}/revoke",
                               json={"reason": reason})


__all__ = ["ApiKeys", "Principals"]
