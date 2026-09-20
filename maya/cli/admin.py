"""
``maya admin …`` (§18.3): the database lifecycle beside the server, then users, roles,
namespaces, grants, workflow policies, restore drills and the retention commands.

Its own module because the command line is one file per group: ``__main__`` builds the
parser and holds the catalog, model, warrant, job and export commands, and the
administrative half is large enough — and separate enough — that carrying it there made
one file that did two jobs.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Callable

from maya.core.errors import MayaError
from maya.cli import common
from maya.cli.common import (
    EXIT_OK,
    EXIT_REFUSED,
    local_ops,
    local_platform,
    emit,
    rows_table,
)


# -- admin: the database lifecycle, beside the server (§14.3) ---------------------------
def admin_init_db(args: argparse.Namespace) -> int:
    from maya.config import load_settings
    from maya.persistence.engine import database_from_settings

    db = database_from_settings(load_settings(args.config))
    if db.is_initialized() and not args.force:
        print("The database already has a MAYA schema; pass --force to drop and recreate it.")
        return EXIT_REFUSED
    digest = db.init_schema(force=args.force)
    print(
        f"Created the {db.dialect} schema from maya/persistence/schema/{db.dialect}.sql "
        f"(schema-hash {digest[:16]}…)"
    )
    return EXIT_OK


def admin_export_estate(args: argparse.Namespace) -> int:
    """Straight from the database, with no platform: this is the way out of a database
    whose schema the running code no longer accepts, so it must not need that check."""
    from maya.config import load_settings
    from maya.core.version import VERSION
    from maya.persistence import estate
    from maya.persistence.engine import database_from_settings

    db = database_from_settings(load_settings(args.config))
    Path(args.out).write_bytes(estate.export(db, VERSION))
    print(f"Estate written to {args.out}")
    return EXIT_OK


def admin_import_estate(args: argparse.Namespace) -> int:
    from maya.config import load_settings
    from maya.persistence.engine import database_from_settings

    settings = load_settings(args.config)
    db = database_from_settings(settings)
    if not db.is_initialized():
        db.init_schema()
    platform = local_platform(args, seed=False)
    result = platform.ops.import_estate(Path(args.input).read_bytes(), allow_drop=args.allow_drop)
    print(json.dumps(result, indent=2, default=str))
    return EXIT_OK


def admin_verify_integrity(args: argparse.Namespace) -> int:
    c = common.client(args)
    result = c.admin.verify_integrity()
    emit(
        args,
        result,
        lambda r: (
            f"{r['checked']} pin(s) checked; drift: {len(r['drift'])}; "
            f"audit chain ok: {r['audit_chain']['ok']}"
        ),
    )
    return EXIT_OK if not result["drift"] and result["audit_chain"]["ok"] else EXIT_REFUSED


def admin_record_drill(args: argparse.Namespace) -> int:
    """Write the result of a restore drill onto the production instance (§20).

    Beside the database, like the other estate commands: the drill is performed on a
    scratch copy which is then deleted, and the record belongs to the instance that was
    backed up, not to the copy. ``MAYA_USER`` names the person recording it.
    """
    platform, principal = local_ops(args)
    row = platform.ops.record_restore_drill(
        principal,
        dialect=args.dialect,
        outcome="failed" if args.failed else "passed",
        pins_checked=args.pins,
        drift=args.drift,
        audit_chain_ok=not args.chain_broken,
        anchors_ok=not args.anchors_broken,
        duration_seconds=args.duration,
        notes=args.notes,
    )
    emit(
        args,
        row,
        lambda r: (
            f"recorded restore drill {r['id']}: {r['outcome']}, "
            f"{r['pins_checked']} pin(s), drift {r['drift']}, {r['duration_seconds']:g}s"
        ),
    )
    return EXIT_OK


def admin_drills(args: argparse.Namespace) -> int:
    platform, principal = local_ops(args)
    status = platform.ops.restore_drill_status(principal)
    rows = platform.ops.restore_drills(principal)
    emit(
        args,
        {"status": status, "drills": rows},
        lambda r: (
            rows_table(
                [
                    {
                        "performed": str(d["performed_at"])[:19],
                        "dialect": d["dialect"],
                        "outcome": d["outcome"],
                        "pins": d["pins_checked"],
                        "drift": d["drift"],
                        "by": d["verified_by"],
                    }
                    for d in r["drills"]
                ],
                ["performed", "dialect", "outcome", "pins", "drift", "by"],
            )
            + f"\n\n{r['status']['detail']}"
            + ("  (overdue: §20 asks for one a quarter)" if r["status"]["overdue"] else "")
        ),
    )
    return EXIT_REFUSED if status["overdue"] else EXIT_OK


def admin_cold(args: argparse.Namespace) -> int:
    """Which pins have gone unread long enough to be called cold (§7.3)."""
    report = common.client(args).admin.cold_pins(days=args.days)
    emit(
        args,
        report,
        lambda r: (
            f"{r['cold_pins']} cold pin(s) holding {r['cold_bytes'] / 1e6:.1f} MB, "
            f"unread for {r['cold_after_days']} day(s); {r['warm_pins']} warm "
            f"({r['warm_bytes'] / 1e6:.1f} MB)\n{r['note']}"
        ),
    )
    return EXIT_OK


def admin_archive_pin(args: argparse.Namespace) -> int:
    out = common.client(args).admin.archive_pin(args.pin_id, table=args.table)
    emit(
        args,
        out,
        lambda r: (
            f"archived {r['rows']} row(s) as blob {r['blob'][:16]}… "
            f"({r['bytes'] / 1e6:.2f} MB)\n{r.get('note', '')}"
        ),
    )
    return EXIT_OK


def admin_restore_pin(args: argparse.Namespace) -> int:
    out = common.client(args).admin.restore_pin(args.pin_id, table=args.table)
    emit(
        args,
        out,
        lambda r: (
            f"{r['manifest']['pin_name']}/{r['manifest']['as_of_date']}: "
            f"{r['manifest']['row_count']} row(s), content hash "
            f"{r['manifest']['content_hash'][:16]}… "
            + ("verified against the archive" if r["verified"] else "manifest only")
        ),
    )
    return EXIT_OK


def admin_collect(args: argparse.Namespace) -> int:
    """Remove fragments no pin references (§29.3). A dry run unless --apply."""
    out = common.client(args).admin.collect_fragments(dry_run=not args.apply)
    emit(
        args,
        out,
        lambda r: (
            r.get("refused")
            or (
                f"{r['orphans']} orphan(s), {r['bytes'] / 1e6:.2f} MB across "
                f"{len(r['plan'])} table(s); nothing removed"
                if r.get("dry_run")
                else f"collected {r['collected']} fragment(s), {r['files_removed']} file(s), "
                f"{r['bytes_removed'] / 1e6:.2f} MB\n{r['note']}"
            )
        ),
    )
    return EXIT_OK


def admin_user_list(args: argparse.Namespace) -> int:
    rows = common.client(args).admin.users()
    emit(args, rows, lambda r: rows_table(r, ["username", "status", "roles", "last_login_at"]))
    return EXIT_OK


def admin_user_create(args: argparse.Namespace) -> int:
    password = args.password or os.environ.get("MAYA_NEW_PASSWORD")
    if not password:
        raise MayaError("Give --password, or put it in MAYA_NEW_PASSWORD")
    extra = {"email": args.email} if args.email else {}
    out = common.client(args).admin.create_user(
        args.username, password=password, roles=args.role or [], **extra
    )
    roles = ", ".join(args.role or []) or "no roles"
    emit(args, out, lambda r: f"created {r['username']} with {roles}")
    return EXIT_OK


def admin_user_roles(args: argparse.Namespace) -> int:
    out = common.client(args).admin.set_roles(args.username, args.role or [])
    held = ", ".join(out.get("roles") or args.role or []) or "no roles"
    emit(args, out, lambda r: f"{args.username} now holds {held}")
    return EXIT_OK


def admin_role_list(args: argparse.Namespace) -> int:
    rows = common.client(args).admin.roles()
    emit(args, rows, lambda r: rows_table(r, ["name", "description", "builtin"]))
    return EXIT_OK


def admin_role_create(args: argparse.Namespace) -> int:
    capabilities = {}
    for pair in args.capability or []:
        kind, _, letters = pair.partition("=")
        capabilities[kind.strip()] = letters.strip()
    out = common.client(args).admin.create_role(args.name, capabilities, args.description or "")
    emit(args, out, lambda r: f"created role {r['name']}")
    return EXIT_OK


def admin_namespace_list(args: argparse.Namespace) -> int:
    rows = common.client(args).namespaces.list()
    emit(
        args,
        rows,
        lambda r: rows_table(
            r, ["name", "preset", "default_visibility", "production", "quota_bytes"]
        ),
    )
    return EXIT_OK


def admin_namespace_create(args: argparse.Namespace) -> int:
    extra = {"quota_bytes": args.quota_bytes} if args.quota_bytes else {}
    out = common.client(args).namespaces.create(
        args.name,
        preset=args.preset,
        production=args.production,
        default_visibility=args.visibility,
        **extra,
    )
    emit(args, out, lambda r: f"created namespace {r['name']} ({r['preset']})")
    return EXIT_OK


def admin_grant_list(args: argparse.Namespace) -> int:
    rows = common.client(args).access.grants(args.kind, args.ref)
    emit(
        args,
        rows,
        lambda r: rows_table(r, ["principal_type", "principal_id", "level", "expires_at"]),
    )
    return EXIT_OK


def admin_grant_add(args: argparse.Namespace) -> int:
    out = common.client(args).access.grant(
        args.kind,
        args.ref,
        args.principal_type,
        args.principal,
        args.level,
        days=args.days,
        deny=args.deny,
    )
    emit(args, out, lambda r: f"granted {r['level']} on {args.ref} to {args.principal}")
    return EXIT_OK


def admin_policy_list(args: argparse.Namespace) -> int:
    rows = common.client(args).workflow.policies()
    emit(args, rows, lambda r: rows_table(r, ["object_type", "scope", "version_no", "state"]))
    return EXIT_OK


def admin_policy_show(args: argparse.Namespace) -> int:
    print(common.client(args).workflow.policy_yaml(args.id))
    return EXIT_OK


def admin_policy_import(args: argparse.Namespace) -> int:
    body = Path(args.file).read_text(encoding="utf-8")
    out = common.client(args).workflow.import_policy(args.object_type, body, scope=args.scope)
    emit(args, out, lambda r: f"drafted policy {r['id']} for {r['object_type']} ({r['scope']})")
    return EXIT_OK


def admin_policy_activate(args: argparse.Namespace) -> int:
    out = common.client(args).workflow.activate_policy(args.id)
    emit(args, out, lambda r: f"policy {r['id']} is {r['state']}")
    return EXIT_OK


def admin_commands(cmd: Callable[..., None], a: Any) -> None:
    """The `maya admin ...` group: the database lifecycle, then users, roles, namespaces,
    grants and workflow policies (§18.3)."""
    cmd(a, "init-db", admin_init_db, (("--force",), {"action": "store_true"}))
    cmd(a, "export-estate", admin_export_estate, (("--out",), {"required": True}))
    cmd(
        a,
        "import-estate",
        admin_import_estate,
        (("--in",), {"dest": "input", "required": True}),
        (
            ("--allow-drop",),
            {
                "action": "store_true",
                "help": "load even though data this version does not know "
                "would be dropped (named in the output)",
            },
        ),
    )
    cmd(a, "verify-integrity", admin_verify_integrity)
    cmd(a, "user-list", admin_user_list)
    cmd(
        a,
        "user-create",
        admin_user_create,
        (("username",), {}),
        (("--password",), {"help": "or MAYA_NEW_PASSWORD"}),
        (("--role",), {"action": "append"}),
        (("--email",), {}),
    )
    cmd(a, "user-roles", admin_user_roles, (("username",), {}), (("--role",), {"action": "append"}))
    cmd(a, "role-list", admin_role_list)
    cmd(
        a,
        "role-create",
        admin_role_create,
        (("name",), {}),
        (("--capability",), {"action": "append", "help": "kind=LETTERS, e.g. feature=CRU"}),
        (("--description",), {}),
    )
    cmd(a, "namespace-list", admin_namespace_list)
    cmd(
        a,
        "namespace-create",
        admin_namespace_create,
        (("name",), {}),
        (("--preset",), {"default": "standard"}),
        (("--production",), {"action": "store_true"}),
        (("--quota-bytes",), {"dest": "quota_bytes", "type": int}),
        (("--visibility",), {"dest": "visibility", "default": "namespace_read"}),
    )
    cmd(a, "grant-list", admin_grant_list, (("kind",), {}), (("ref",), {}))
    cmd(
        a,
        "grant-add",
        admin_grant_add,
        (("kind",), {}),
        (("ref",), {}),
        (("level",), {}),
        (("--principal-type",), {"dest": "principal_type", "default": "user"}),
        (("--principal",), {"required": True}),
        (("--days",), {"type": int, "default": 90}),
        (("--deny",), {"action": "store_true"}),
    )
    cmd(a, "policy-list", admin_policy_list)
    cmd(a, "policy-show", admin_policy_show, (("id",), {}))
    cmd(
        a,
        "policy-import",
        admin_policy_import,
        (("object_type",), {}),
        (("file",), {}),
        (("--scope",), {"default": "*"}),
    )
    cmd(a, "policy-activate", admin_policy_activate, (("id",), {}))
    cmd(
        a,
        "record-drill",
        admin_record_drill,
        (("--dialect",), {"default": None, "help": "the dialect the drill restored"}),
        (("--pins",), {"type": int, "default": 0, "help": "sealed pins verified"}),
        (("--drift",), {"type": int, "default": 0, "help": "pins that failed to verify"}),
        (("--duration",), {"type": float, "default": 0.0, "help": "seconds, restore to green"}),
        (("--failed",), {"action": "store_true", "help": "the drill did not pass"}),
        (("--chain-broken",), {"action": "store_true", "dest": "chain_broken"}),
        (("--anchors-broken",), {"action": "store_true", "dest": "anchors_broken"}),
        (("--notes",), {"default": None, "help": "what was restored, and anything unusual"}),
    )
    cmd(a, "drills", admin_drills)
    cmd(a, "cold-pins", admin_cold, (("--days",), {"type": int, "help": "default: configured"}))
    cmd(a, "collect-fragments", admin_collect, (("--apply",), {"action": "store_true"}))
    cmd(
        a,
        "archive-pin",
        admin_archive_pin,
        (("pin_id",), {}),
        (
            ("--table",),
            {"choices": ["feature_pins", "feature_set_pins"], "default": "feature_pins"},
        ),
    )
    cmd(
        a,
        "restore-pin",
        admin_restore_pin,
        (("pin_id",), {}),
        (
            ("--table",),
            {"choices": ["feature_pins", "feature_set_pins"], "default": "feature_pins"},
        ),
    )


__all__ = ["admin_commands"]
