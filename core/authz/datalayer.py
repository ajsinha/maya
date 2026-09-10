"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The same authorisation, twice, from one definition.

`Scope` already decides which models a principal may act on, and every route
applies it. The requirement asks for the same rule **in the data layer as well**
— and the reason a firm asks is not distrust of the application: it is that an
analyst with a read-only database credential, a reporting tool, a backup restored
into a test environment and a support engineer running a query are four ways to
read rows the API would have refused.

**Two enforcement points written twice will disagree.** That is the whole design
here. The row-level policies are **generated from `Scope`**, so the SQL a
database enforces and the check a route applies are the same rule expressed
twice rather than two rules that happen to look alike. The first time somebody
adds a scope dimension, both move; if the policies were hand-written, only one
would, and the one that did not would be the one silently permitting more.

**Field-level authorisation is redaction, not omission — and it says so.** A
response that quietly drops a field a reader may not see is a response that
reader cannot tell from one where the field is empty. So a redacted field is
replaced by a marker naming the permission that would reveal it: *there is
something here, and this is what it would take*. Silence would let somebody
conclude a model has no exposure recorded when what they actually lack is
`report:read`.

**MAYA does not encrypt the database, and says so rather than implying it.**
At-rest and in-transit encryption are the deployment's — a platform that shipped
its own would be shipping a key-management decision nobody asked it to make.
What it *can* do is refuse to run pretending otherwise: the posture below reports
what is actually configured, and an instance serving over plain HTTP with a
published cookie secret is told so at every boot rather than reassured by a
checkbox.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Sequence

#: What a redacted field is replaced with. A marker rather than a removal,
#: because a dropped field is indistinguishable from an absent one and a reader
#: who cannot tell has been misled by silence.
REDACTED = "«redacted»"

#: Fields that carry more than the object's identity, and the permission that
#: reveals each. Deliberately short: field-level authorisation over a hundred
#: fields is a policy nobody can reason about, and the ones here are the ones
#: where reading the value tells you something the object's existence does not.
SENSITIVE_FIELDS: Dict[str, Dict[str, str]] = {
    "exposure": {
        "permission": "report:read",
        "why": "what rides on a model being right is the number an outsider "
               "most wants and the one least connected to operating it",
    },
    "attributes": {
        "permission": "model:register",
        "why": "the free-form block, which is where anything nobody found a "
               "column for ends up — including things somebody assumed only "
               "the owner would read",
    },
    "secret": {
        "permission": "principal:manage",
        "why": "never returned at all in practice; listed so that a new "
               "surface returning one is caught by the test rather than by an "
               "incident",
    },
}

#: The tables a row-level policy is generated for, and the column each scopes
#: on. Only the tables that carry the scope directly: a policy on a child table
#: would have to join, and a join inside a security policy is a performance
#: cliff that gets the policy disabled.
SCOPED_TABLES: Dict[str, Sequence[str]] = {
    "model": ("legal_entity", "domain"),
}


def redact(row: Dict[str, Any], granted: Iterable[str]) -> Dict[str, Any]:
    """A row with the fields this reader may not see marked rather than dropped.

    Marked, because a response that quietly omits a field is one the reader
    cannot tell from a response where the field is empty — and concluding a
    model has no exposure recorded when what you actually lack is `report:read`
    is exactly the wrong conclusion to let somebody reach in silence.
    """
    held = set(granted or ())
    out = dict(row)
    for field, spec in SENSITIVE_FIELDS.items():
        if field in out and out[field] is not None \
                and spec["permission"] not in held:
            out[field] = REDACTED
    return out


def redactions(granted: Iterable[str]) -> Dict[str, Any]:
    """What this reader would not be shown, and what would show it."""
    held = set(granted or ())
    hidden = [{"field": f, **spec} for f, spec in SENSITIVE_FIELDS.items()
              if spec["permission"] not in held]
    return {
        "redacted_fields": [h["field"] for h in hidden],
        "detail": ([{"field": h["field"], "needs": h["permission"],
                     "why": h["why"]} for h in hidden]
                   if hidden else []),
        "marker": REDACTED,
        "why_marked": (
            "a redacted field is replaced rather than removed: a response that "
            "quietly drops a field is one the reader cannot tell from a "
            "response where the field is empty, and silence would let somebody "
            "conclude a model has no exposure recorded when what they lack is "
            "a permission"),
    }


def policies(role_column: str = "maya_legal_entities",
             domain_column: str = "maya_domains") -> Dict[str, Any]:
    """Row-level security policies, generated from the scope model.

    **Generated rather than written**, and that is the point. Two enforcement
    points written twice will disagree, and the one that disagrees permissively
    is the one nobody notices. These express exactly what `Scope.permits` does:
    an empty setting means unrestricted, which is how a scope with no entities
    and no domains behaves in the application.

    Emitted rather than executed. Applying them is a migration, and a platform
    that silently turned on row-level security against a running database would
    be making an availability decision for somebody else.
    """
    statements: List[str] = []
    for table, columns in SCOPED_TABLES.items():
        statements.append(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
        clauses = []
        for column in columns:
            setting = (role_column if column == "legal_entity"
                       else domain_column)
            # An empty setting is unrestricted, matching `Scope.unrestricted`.
            # Written as `= ''` rather than `IS NULL` because a session setting
            # that was never set reads as the empty string in PostgreSQL, and
            # the two spellings are not the same test.
            clauses.append(
                f"(current_setting('maya.{setting}', true) IS NULL "
                f"OR current_setting('maya.{setting}', true) = '' "
                f"OR {column} = ANY(string_to_array("
                f"current_setting('maya.{setting}', true), ',')))")
        statements.append(
            f"CREATE POLICY {table}_scope ON {table} USING (\n    "
            + "\n    AND ".join(clauses) + "\n);")
    return {
        "statements": statements,
        "tables": sorted(SCOPED_TABLES),
        "session_settings": [f"maya.{role_column}", f"maya.{domain_column}"],
        "generated_from": "core.authz.scope.Scope",
        "detail": (
            "generated from the same `Scope` the routes apply, so the SQL a "
            "database enforces and the check a route makes are one rule "
            "expressed twice rather than two rules that happen to look alike. "
            "The first time somebody adds a scope dimension both move; "
            "hand-written policies would leave one behind, and it would be the "
            "one silently permitting more. Emitted rather than executed: "
            "applying them is a migration, and a platform that turned on "
            "row-level security against a running database would be making an "
            "availability decision for somebody else"),
    }


def encryption_posture(*, https: bool, cookie_secure: bool,
                       database_url: str = "",
                       session_secret_is_default: bool = False) -> Dict[str, Any]:
    """What is actually encrypted, as opposed to what a checkbox would claim.

    MAYA does not encrypt the database and does not pretend to: at-rest and
    in-transit encryption are the deployment's, and a platform shipping its own
    would be shipping a key-management decision nobody asked it to make. What it
    can do is refuse to imply otherwise.
    """
    tls_to_database = any(token in (database_url or "").lower()
                          for token in ("sslmode=require", "sslmode=verify",
                                        "ssl=true"))
    findings = []
    if not https:
        findings.append({
            "what": "traffic to this instance",
            "state": "not encrypted",
            "why": "the instance is not configured to require HTTPS. Every "
                   "credential, every model record and every session cookie "
                   "crosses the network in the clear",
        })
    if not cookie_secure:
        findings.append({
            "what": "the session cookie",
            "state": "sent over plain HTTP",
            "why": "without `Secure` the cookie is sent on any request to this "
                   "host, so one plain-HTTP request hands over a signed "
                   "session",
        })
    if database_url and not tls_to_database:
        findings.append({
            "what": "the connection to the database",
            "state": "not verifiably encrypted",
            "why": "the connection string does not require TLS, so whether the "
                   "traffic is encrypted depends on a server default nobody "
                   "here can see",
        })
    if session_secret_is_default:
        findings.append({
            "what": "the session signing secret",
            "state": "the published default",
            "why": "anybody with a copy of this repository can forge a signed "
                   "session as any user, with no password",
        })
    return {
        "https": https, "cookie_secure": cookie_secure,
        "database_tls": tls_to_database if database_url else None,
        "findings": findings, "sound": not findings,
        "at_rest": (
            "not this platform's. Disk and volume encryption are the "
            "deployment's, and a platform shipping its own would be shipping a "
            "key-management decision nobody asked it to make. What is NOT "
            "delegated is the inference log's retention, which deletes rather "
            "than relying on the disk being unreadable one day"),
        "field_level": (
            "the feature store holds what the firm loaded into it, and the "
            "classification lattice already says which of it is restricted. "
            "Encrypting designated columns is a data-plane change with a key "
            "rotation story, and shipping half of one — encryption with no "
            "rotation — is worse than none, because it reads as solved"),
        "detail": (
            "nothing about the transport is misconfigured on this instance"
            if not findings else
            f"{len(findings)} transport or credential setting(s) are not what "
            f"a production instance should have: "
            + "; ".join(f["what"] for f in findings)
            + ". These are reported rather than refused at boot, because an "
              "instance somebody is trying out on a laptop is a legitimate "
              "thing and refusing it would teach people to set the flags "
              "without meaning them — but an instance reachable by anybody "
              "else with these findings is one whose assurances do not hold"),
    }
