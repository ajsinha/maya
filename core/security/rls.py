"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Row-level security: a backstop under the scope check, and an honest account of
what it is and is not.

## The finding this closes, and the part of it that was true

**H-5**, the oldest open finding in the adversarial review, in its own words: a
validator scoped to one legal entity looks for a listing endpoint whose author
forgot `Scope.filter`. The disposition said *not built*, and gave a reason that
was correct at the time — *there is one connection identity, so RLS would have
nothing to distinguish anyway*.

That reason was the real blocker, and it is what this fixes. PostgreSQL's
`current_setting` reads a session variable, and a session variable can be set
per request on the connection that request is using. So the acting principal's
entity scope travels with the connection, the policy reads it, and the database
can refuse a row the application forgot to filter.

## What makes it a backstop rather than a control

`core/authz/scope.py` remains the control. It is the thing that decides, it is
where the reasoning lives, and it produces the refusal a caller can act on. RLS
produces **no rows**, which is a much worse answer for anybody who is entitled
and hits a bug — so making it primary would trade a legible refusal for an empty
list, and an empty list is indistinguishable from *there is nothing*.

What it buys is the case the control cannot cover: the endpoint somebody wrote
last week and forgot to filter. There the application is wrong, and the honest
outcome is zero rows rather than another entity's models.

## Three things that make it real rather than decorative

**`FORCE ROW LEVEL SECURITY`.** Without it the table *owner* bypasses every
policy, and the owner is whoever ran the DDL — which in most deployments is the
same role the application connects as. A policy the application bypasses by
construction is a policy that exists only in a screenshot.

**And the role must not be a superuser**, which is the trap one level below
that. Verified against a real PostgreSQL 16 rather than reasoned about: with
`FORCE` in place and the session variable unset, a non-superuser owner reads
**zero rows** — the policy binds. A **superuser reads everything**, `FORCE` or
not, because superusers and roles with `BYPASSRLS` are exempt from row-level
security by design. So a deployment that applies every statement here perfectly
and then connects as `postgres` has a policy that does nothing, and nothing
about the configuration looks wrong. `in_force()` therefore reports the
connecting role's exemption alongside the table flags, because that is the fact
that decides whether any of the rest of it is true.

**A non-owner application role.** Follows from the above: the migration runs as
one role and the application connects as another, and the second owns nothing.
This is a deployment decision MAYA cannot make for a firm, so the statements are
*published* and the platform **reports whether they are in force** rather than
assuming they are.

**A default-deny policy.** The `USING` clause admits a row when the session's
entity list contains it, or when the session variable names the estate-wide
scope. The variable being *unset* admits nothing. That direction matters: a
policy that failed open on a missing setting would be a policy that does nothing
the moment a connection is recycled without one, which is exactly when it is
needed.

## And what it does not do

**It is PostgreSQL only.** SQLite has no row-level security and never will;
`posture()` says so rather than letting a development deployment believe it has
a backstop. This is the one control in MAYA whose availability depends on the
deployment, and it is reported rather than implied.

**It does not cover every table.** Only rows that *carry* an entity can be
filtered by one. A version's entity is its model's, a finding's is its model's,
and expressing that as a policy means a subquery per row on every read. The
tables that carry the column directly are covered; everything reached through
them is still the application's job, and `SCOPED_TABLES` is the list rather than
a claim of completeness.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

from core.log import get_logger

logger = get_logger(__name__)

#: The session variable the policies read. A custom GUC, so it cannot collide
#: with anything PostgreSQL owns, and `set_config(..., true)` scopes it to the
#: transaction — a pooled connection handed to the next request therefore
#: carries nothing, which is the direction that fails safe.
GUC = "maya.entities"

#: What a session sets when the principal is not scoped at all. Spelled out
#: rather than left as an empty value, because "unset" and "everything" are
#: different states and an empty string is how they get confused.
ESTATE_WIDE = "*"

#: Tables carrying a legal entity directly. Only these can be policed by one:
#: a version's entity is its model's, and expressing that as a policy is a
#: subquery per row on every read. What is reached through them stays the
#: application's job, and saying so is the point of this being a list.
SCOPED_TABLES: Tuple[Tuple[str, str], ...] = (
    ("model", "legal_entity"),
    ("risk_appetite_limit", "legal_entity"),
)


def policy_statements(role: str = "maya_app") -> List[str]:
    """The DDL a deployment applies, published rather than executed.

    MAYA does not run these itself, and that is deliberate: creating a role and
    granting it is a decision about a database somebody else operates, and a
    governance platform that silently created roles in a bank's cluster would
    be doing the thing it spends the rest of its time refusing to do.

    They are idempotent, so a deployment can apply them on every release
    without tracking whether it already did.
    """
    out = [
        f"-- The application connects as {role} and OWNS NOTHING. Without a",
        "-- non-owner role, FORCE ROW LEVEL SECURITY below has nothing to",
        "-- bind against: the owner bypasses every policy, and the owner is",
        "-- whoever ran the DDL.",
        "DO $$ BEGIN",
        f"  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}')",
        f"  THEN CREATE ROLE {role} NOLOGIN; END IF;",
        "END $$;",
    ]
    for table, column in SCOPED_TABLES:
        out += [
            "",
            f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;",
            # The line that makes it real. Without FORCE, the owner reads
            # everything and the policy is a screenshot.
            f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;",
            f"DROP POLICY IF EXISTS {table}_entity_scope ON {table};",
            # Default deny: an UNSET variable admits nothing. A policy that
            # failed open on a missing setting would do nothing the moment a
            # pooled connection is recycled without one — which is exactly
            # when it is needed.
            f"CREATE POLICY {table}_entity_scope ON {table}",
            "  USING (",
            f"    current_setting('{GUC}', true) = '{ESTATE_WIDE}'",
            f"    OR {column} = ANY (string_to_array(",
            f"         coalesce(current_setting('{GUC}', true), ''), ','))",
            "  );",
            f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO {role};",
        ]
    return out


class RowLevelSecurity:
    """Sets the session scope, and reports whether the backstop is in force."""

    def __init__(self, db: Any):
        self.db = db

    # ---------------------------------------------------------------- state
    @property
    def available(self) -> bool:
        """Whether this deployment can have a backstop at all.

        SQLite has no row-level security and never will. Reported rather than
        implied, because a development deployment believing it has a backstop
        is worse off than one that knows it does not.
        """
        return getattr(self.db, "dialect", "") == "postgresql"

    def in_force(self) -> Dict[str, Any]:
        """Which scoped tables actually have RLS enabled AND forced.

        Both flags, separately. `relrowsecurity` without `relforcerowsecurity`
        is the configuration that looks right in a screenshot and does nothing
        for the role the application connects as — and it is the ordinary
        result of somebody enabling RLS and stopping there.
        """
        if not self.available:
            return {
                "available": False, "tables": [], "forced": 0, "enabled": 0,
                "detail": ("row-level security is a PostgreSQL feature and "
                           "this deployment is on "
                           f"{getattr(self.db, 'dialect', 'an unknown store')}. "
                           "There is no database backstop here and there "
                           "cannot be: everything rests on the scope check in "
                           "`core/authz/scope.py` being called on every path"),
            }
        rows = self.db.query(
            "SELECT c.relname AS table_name, c.relrowsecurity AS enabled, "
            "       c.relforcerowsecurity AS forced "
            "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = current_schema() AND c.relname = ANY(:names)",
            {"names": [t for t, _ in SCOPED_TABLES]})
        by_name = {r["table_name"]: r for r in rows}
        tables = [{"table": t,
                   "enabled": bool(by_name.get(t, {}).get("enabled")),
                   "forced": bool(by_name.get(t, {}).get("forced"))}
                  for t, _ in SCOPED_TABLES]
        enabled = sum(1 for t in tables if t["enabled"])
        forced = sum(1 for t in tables if t["forced"])
        exempt = self._role_is_exempt()
        return {
            "available": True, "tables": tables,
            "enabled": enabled, "forced": forced,
            # The fact that decides whether any of the rest of this is true.
            "connecting_role_is_exempt": exempt["exempt"],
            "connecting_role": exempt["role"],
            "detail": (exempt["why"] + " " if exempt["exempt"] else "")
                      + self._detail(tables, enabled, forced),
        }

    def _role_is_exempt(self) -> Dict[str, Any]:
        """Whether the role this application connects as is outside RLS.

        Superusers and roles with `BYPASSRLS` are exempt by design, `FORCE` or
        not. A deployment that applies every policy perfectly and then connects
        as `postgres` has a backstop that does nothing, and nothing about the
        configuration looks wrong — which is why this is read rather than
        assumed.
        """
        try:
            row = self.db.query_one(
                "SELECT current_user AS role, "
                "       rolsuper AS is_superuser, rolbypassrls AS bypasses "
                "FROM pg_roles WHERE rolname = current_user")
        except Exception as exc:                 # pragma: no cover - defensive
            logger.warning("could not read the connecting role's RLS "
                           "exemption: %s", exc)
            return {"exempt": False, "role": "unknown",
                    "why": ""}
        if row is None:
            return {"exempt": False, "role": "unknown", "why": ""}
        exempt = bool(row.get("is_superuser") or row.get("bypasses"))
        return {
            "exempt": exempt, "role": row.get("role"),
            "why": (
                f"**this application connects as '{row.get('role')}', which is "
                f"{'a superuser' if row.get('is_superuser') else 'BYPASSRLS'} "
                f"and is therefore exempt from row-level security entirely.** "
                f"Every policy below is in place and none of them applies to "
                f"this connection. Connect as a role that owns nothing and is "
                f"neither."
                if exempt else ""),
        }

    @staticmethod
    def _detail(tables: Sequence[Dict[str, Any]], enabled: int,
                forced: int) -> str:
        total = len(tables)
        if forced == total:
            return (f"all {total} scoped table(s) have row-level security "
                    f"enabled and FORCED. Forced is the half that matters: "
                    f"without it the table owner bypasses every policy, and "
                    f"the owner is whoever ran the DDL")
        if enabled and forced < enabled:
            return (f"{enabled} of {total} scoped table(s) have row-level "
                    f"security enabled and only {forced} have it FORCED. The "
                    f"unforced ones are the configuration that looks right in "
                    f"a screenshot and does nothing for the role this "
                    f"application connects as, if that role owns the table")
        return (f"{enabled} of {total} scoped table(s) have row-level security. "
                f"The statements are published at "
                f"`GET /api/v1/row-level-security`; applying them is a "
                f"decision about a database MAYA does not operate, so it "
                f"reports what it finds rather than creating roles in "
                f"somebody's cluster")

    # ------------------------------------------------------------- the scope
    def apply(self, entities: Optional[Sequence[str]]) -> str:
        """Put this request's entity scope on the connection.

        Transaction-scoped (`set_config(..., true)`), so a pooled connection
        handed to the next request carries nothing. That direction is the
        whole safety of it: a leaked scope would be one request reading
        another's entities, which is a worse failure than the one this
        prevents.

        `None` means the principal is not entity-scoped and the value is the
        estate-wide marker rather than an empty string — "unset" and
        "everything" are different states, and an empty string is how they get
        confused.
        """
        value = ESTATE_WIDE if not entities else ",".join(sorted(entities))
        if self.available:
            self.db.execute("SELECT set_config(:name, :value, true)",
                            {"name": GUC, "value": value})
        return value

    # --------------------------------------------------------------- posture
    def posture(self) -> Dict[str, Any]:
        """What this is, what it is not, and what it does not reach."""
        state = self.in_force()
        return {
            **state,
            "is_the_control": False,
            "guc": GUC,
            "scoped_tables": [t for t, _ in SCOPED_TABLES],
            "why_not_the_control": (
                "`core/authz/scope.py` decides, and it produces a refusal "
                "somebody can act on. RLS produces NO ROWS, which is a much "
                "worse answer for anybody who is entitled and hits a bug — an "
                "empty list is indistinguishable from 'there is nothing'. "
                "What this covers is the case the control cannot: the endpoint "
                "somebody wrote last week and forgot to filter"),
            "does_not_reach": (
                "rows that do not CARRY an entity. A version's entity is its "
                "model's and a finding's is its model's, and expressing that "
                "as a policy is a subquery per row on every read. Those stay "
                "the application's job, and this list is the list rather than "
                "a claim of completeness"),
            "statements": policy_statements(),
        }
