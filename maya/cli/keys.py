"""
``maya key …`` and ``maya credential …`` (§12, §18.3).

§12 says plainly that "creating, rotating, scoping and revoking keys is itself an SDK
capability", and §18.3 that the command line is how MAYA is scripted. Rotation in
particular has to be scriptable: a key is rotated on a schedule, from a job that has no
browser and no person watching, and the whole point of the overlap window is that the
rotation and the switch-over are two separate steps some hours apart.

The secret is printed once, here as everywhere, because MAYA keeps only its hash. The
commands say so rather than letting somebody discover it after closing the terminal.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import argparse
from typing import Any, Callable

from maya.cli import common
from maya.cli.common import EXIT_OK, EXIT_REFUSED, emit, rows_table

KEY_COLUMNS = ["key_id", "name", "kind", "created_at", "last_used_at", "expires_at"]


def key_list(args: argparse.Namespace) -> int:
    rows = common.client(args).auth.api_keys(all=args.all)
    emit(args, rows, lambda r: rows_table(r, KEY_COLUMNS))
    return EXIT_OK


def key_create(args: argparse.Namespace) -> int:
    extra: dict[str, Any] = {}
    if args.for_user:
        extra["for_user"] = args.for_user
    made = common.client(args).auth.create_api_key(
        args.name,
        roles=args.role or [],
        namespaces=args.namespace or [],
        actions=args.action or [],
        cidrs=args.cidr or [],
        days=args.days,
        rate_per_minute=args.rate_per_minute,
        **extra,
    )
    emit(
        args,
        made,
        lambda r: (
            f"{r['key_id']} expires {str(r['expires_at'])[:10]}\n{r['api_key']}\n"
            "That is the only time the secret is shown: MAYA stores its hash."
        ),
    )
    return EXIT_OK


def key_rotate(args: argparse.Namespace) -> int:
    """Issue a successor and let both work until the overlap window ends (§12)."""
    made = common.client(args).auth.rotate_api_key(
        args.key_id, overlap_days=args.overlap_days, days=args.days
    )
    emit(
        args,
        made,
        lambda r: (
            f"{args.key_id} is replaced by {r['key_id']}; the old key works until "
            f"{str(r['retires_at'])[:19]}\n{r['api_key']}\n"
            "Deploy the new key before then; the secret is shown only now."
        ),
    )
    return EXIT_OK


def key_revoke(args: argparse.Namespace) -> int:
    emit(
        args,
        common.client(args).auth.revoke_api_key(args.key_id),
        lambda r: f"revoked {args.key_id}",
    )
    return EXIT_OK


def key_report(args: argparse.Namespace) -> int:
    """Keys wanting attention, each with its reason. A non-zero exit when there are any,
    so a scheduled run can simply fail and be noticed."""
    rows = common.client(args).auth.api_key_report(all=args.all)
    emit(
        args,
        rows,
        lambda r: rows_table(
            [{**row, "reasons": "; ".join(row["reasons"])} for row in r],
            ["key_id", "name", "username", "expires_at", "reasons"],
        ),
    )
    return EXIT_REFUSED if rows else EXIT_OK


def credential_list(args: argparse.Namespace) -> int:
    rows = common.client(args).auth.client_credentials()
    emit(args, rows, lambda r: rows_table(r, ["key_id", "name", "username", "expires_at"]))
    return EXIT_OK


def credential_create(args: argparse.Namespace) -> int:
    """A client credential for a service account: §11.5 asks service accounts to be
    principals with credentials, and one cannot create its own — it never signs in."""
    made = common.client(args).auth.create_client_credential(
        args.username,
        name=args.name,
        roles=args.role or [],
        namespaces=args.namespace or [],
        actions=args.action or [],
        days=args.days,
        rate_per_minute=args.rate_per_minute,
    )
    emit(
        args,
        made,
        lambda r: (
            f"client_id {r['client_id']}\nclient_secret {r['client_secret']}\n"
            f"expires {str(r['expires_at'])[:10]}; exchange them at POST /auth/token for a "
            "token no wider than the credential. The secret is shown only now."
        ),
    )
    return EXIT_OK


def _scope_arguments() -> tuple[tuple[Any, ...], ...]:
    """The scoping flags every credential shares (§12: roles, namespaces, actions)."""
    return (
        (("--role",), {"action": "append", "help": "a role the credential may use"}),
        (("--namespace",), {"action": "append", "help": "restrict it to this namespace"}),
        (("--action",), {"action": "append", "help": "restrict it to this action"}),
        (("--days",), {"type": int, "default": 90, "help": "life in days; expiry is mandatory"}),
        (
            ("--rate-per-minute",),
            {"dest": "rate_per_minute", "type": int, "default": 0, "help": "0: the global budget"},
        ),
    )


def key_commands(cmd: Callable[..., None], groups: Any) -> None:
    """``maya key …`` and ``maya credential …`` on the parser."""
    k = groups.add_parser("key").add_subparsers(dest="cmd", required=True)
    cmd(k, "list", key_list, (("--all",), {"action": "store_true", "help": "every user's (admin)"}))
    cmd(
        k,
        "create",
        key_create,
        (("name",), {}),
        *_scope_arguments(),
        (("--cidr",), {"action": "append", "help": "allow only this CIDR block"}),
        (("--for-user",), {"dest": "for_user", "help": "issue it for a service account"}),
    )
    cmd(
        k,
        "rotate",
        key_rotate,
        (("key_id",), {}),
        (
            ("--overlap-days",),
            {"dest": "overlap_days", "type": int, "help": "default: configured"},
        ),
        (("--days",), {"type": int, "help": "life of the successor; default: the same"}),
    )
    cmd(k, "revoke", key_revoke, (("key_id",), {}))
    cmd(
        k,
        "report",
        key_report,
        (("--all",), {"action": "store_true", "help": "every user's (admin)"}),
    )

    c = groups.add_parser("credential").add_subparsers(dest="cmd", required=True)
    cmd(c, "list", credential_list)
    cmd(
        c,
        "create",
        credential_create,
        (("username",), {"help": "the service account it is for"}),
        (("--name",), {"default": "client credential"}),
        *_scope_arguments(),
    )


__all__ = ["key_commands"]
