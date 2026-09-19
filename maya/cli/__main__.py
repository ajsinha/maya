"""
``python -m maya.cli <group> <command> …`` — see ``maya.cli`` for the rules.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import argparse
import re
import json
import os
import sys
from pathlib import Path
from typing import Any, Callable

from maya.core import parameters
from maya.core.errors import MayaError

EXIT_OK, EXIT_REFUSED, EXIT_USAGE, EXIT_NETWORK = 0, 1, 2, 3


# -- plumbing -------------------------------------------------------------------------
def _client(args: argparse.Namespace) -> Any:
    from maya.sdk import Client, connect

    if args.local:
        from maya.config import load_settings
        from maya.server import build_app
        from maya.services.platform import Platform

        # job workers only: a CLI run must not deliver webhooks or run the scheduler —
        # on a restored copy of production that would reach production's receivers
        platform = Platform.build(load_settings(args.config), start_workers="jobs")
        anon = Client(app=build_app(platform), channel="cli")
        user = os.environ.get("MAYA_USER", "admin")
        pw = os.environ.get("MAYA_PASSWORD")
        if not pw:
            raise MayaError("--local needs MAYA_USER and MAYA_PASSWORD in the environment")
        token = anon.auth.login(user, pw)["token"]
        return Client(app=anon._http.app, token=token, channel="cli")
    return connect(args.profile) if args.profile else connect()


def _out(args: argparse.Namespace, data: Any, human: Callable[[Any], str] | None = None) -> None:
    if args.json or human is None:
        print(json.dumps(data, indent=2, default=str))
    else:
        print(human(data))


def _rows(rows: list[dict[str, Any]], cols: list[str]) -> str:
    if not rows:
        return "(none)"
    widths = [max(len(c), *(len(str(r.get(c, ""))) for r in rows)) for c in cols]
    lines = ["  ".join(c.upper().ljust(w) for c, w in zip(cols, widths))]
    lines += ["  ".join(str(r.get(c, "")).ljust(w) for c, w in zip(cols, widths)) for r in rows]
    return "\n".join(lines)


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
    platform = _local_platform(args, seed=False)
    result = platform.ops.import_estate(Path(args.input).read_bytes(), allow_drop=args.allow_drop)
    print(json.dumps(result, indent=2, default=str))
    return EXIT_OK


def admin_verify_integrity(args: argparse.Namespace) -> int:
    c = _client(args)
    result = c.admin.verify_integrity()
    _out(
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
    platform, principal = _local_ops(args)
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
    _out(
        args,
        row,
        lambda r: (
            f"recorded restore drill {r['id']}: {r['outcome']}, "
            f"{r['pins_checked']} pin(s), drift {r['drift']}, {r['duration_seconds']:g}s"
        ),
    )
    return EXIT_OK


def admin_drills(args: argparse.Namespace) -> int:
    platform, principal = _local_ops(args)
    status = platform.ops.restore_drill_status(principal)
    rows = platform.ops.restore_drills(principal)
    _out(
        args,
        {"status": status, "drills": rows},
        lambda r: (
            _rows(
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


def _local_ops(args: argparse.Namespace) -> tuple[Any, Any]:
    """A platform opened beside the database, and the principal naming who is acting."""
    from maya.config import load_settings
    from maya.services.platform import Platform

    platform = Platform.build(load_settings(args.config), start_workers=False)
    username = os.environ.get("MAYA_USER", "admin")
    with platform.uow() as uow:
        user = uow.repo("users").find_one(username=username)
        if user is None:
            raise MayaError(f"No such user '{username}'; set MAYA_USER")
        return platform, platform.auth.build_principal(uow, user["id"], channel="cli")


def _local_platform(args: argparse.Namespace, seed: bool = True) -> Any:
    from maya.config import load_settings
    from maya.services.platform import Platform
    from maya.services import registry

    settings = load_settings(args.config)
    if seed:
        return Platform.build(settings, start_workers=False)
    from maya.persistence.engine import database_from_settings

    db = database_from_settings(settings)
    db.verify_schema()
    platform = Platform(settings, db)
    registry.wire(platform)
    return platform


# -- catalog --------------------------------------------------------------------------------
def feature_list(args: argparse.Namespace) -> int:
    rows = _client(args).features.list(namespace=args.namespace, q=args.q)
    _out(args, rows, lambda r: _rows(r, ["ref", "latest_version", "latest_state", "pins", "owner"]))
    return EXIT_OK


def feature_show(args: argparse.Namespace) -> int:
    _out(args, _client(args).features.get(args.ref))
    return EXIT_OK


def feature_quick(args: argparse.Namespace) -> int:
    path = Path(args.file)
    result = _client(args).features.quick(
        path.read_bytes(), name=args.name or path.stem, fmt=path.suffix.lstrip(".") or "csv"
    )
    _out(
        args,
        result,
        lambda r: (
            f"{r['ref']}@v{r['version']}: {r['rows']} rows, ungoverned "
            f"scratch. Warnings: {r['warnings'] or 'none'}"
        ),
    )
    return EXIT_OK


def feature_upload(args: argparse.Namespace) -> int:
    path = Path(args.file)
    result = _client(args).features.ingest(
        args.ref,
        path.read_bytes(),
        fmt=path.suffix.lstrip("."),
        filename=path.name,
        knowledge_time=args.knowledge_time,
    )
    _out(
        args,
        result,
        lambda r: f"ingested {r['rows']} rows" + (" (a restatement)" if r["restatement"] else ""),
    )
    return EXIT_OK


def feature_pin(args: argparse.Namespace) -> int:
    c = _client(args)
    result = c.features.pin(
        args.ref,
        version_no=args.version,
        pin_name=args.name,
        as_of=args.as_of,
        as_of_known=args.as_of_known,
    )
    if result.get("job"):
        job = c.wait(
            result["job"], progress=lambda j: print(f"  {j['progress']:3d}% {j['message']}")
        )
        _out(
            args,
            job["result"],
            lambda r: f"sealed {r['content_hash']} ({r['rows']} rows, {r['bytes_new']} new bytes)",
        )
    else:
        print("Pin requested; it awaits approval by a pin authorizer.")
    return EXIT_OK


def feature_download(args: argparse.Namespace) -> int:
    result = _client(args).features.download(
        args.ref, format=args.format, csv_encoding=args.csv_encoding
    )
    Path(args.out).write_bytes(result["data"])
    print(
        f"{args.out}: {result['manifest'].get('rows')} rows, content hash "
        f"{result['manifest'].get('content_hash')}"
    )
    return EXIT_OK


def feature_diff(args: argparse.Namespace) -> int:
    _out(args, _client(args).features.compare(args.ref, args.v1, args.v2))
    return EXIT_OK


def featureset_pin(args: argparse.Namespace) -> int:
    c = _client(args)
    result = c.featuresets.pin(
        args.ref,
        version_no=args.version,
        pin_name=args.name,
        as_of=args.as_of,
        cascade=args.cascade,
    )
    job = c.wait(result["job"], progress=lambda j: print(f"  {j['progress']:3d}% {j['message']}"))
    _out(args, job["result"])
    return EXIT_OK


def featureset_download(args: argparse.Namespace) -> int:
    result = _client(args).featuresets.download(
        args.ref, format=args.format, shape=args.shape, csv_encoding=args.csv_encoding
    )
    Path(args.out).write_bytes(result["data"])
    print(f"{args.out}: {result['manifest'].get('rows')} rows")
    return EXIT_OK


def model_push(args: argparse.Namespace) -> int:
    c = _client(args)
    source = Path(args.file).read_text(encoding="utf-8")
    _out(args, c.models.upload_artifact(args.ref, source))
    return EXIT_OK


def model_import_workbook(args: argparse.Namespace) -> int:
    """Lift an Excel workbook into the model's draft (or only preview the lift)."""
    roles = {}
    for pair in args.role or []:
        name, _, role = pair.partition("=")
        roles[name.strip()] = role.strip() or "feature"
    data = Path(args.file).read_bytes()
    c = _client(args)
    if args.preview:
        result = c.models.lift_workbook(
            data, output=args.output, roles=roles, filename=Path(args.file).name
        )
        report = result["lifted_from"]["workbook"]
    else:
        result = c.models.import_workbook(
            args.ref, data, output=args.output, roles=roles, filename=Path(args.file).name
        )
        report = result["workbook"]

    def human(_: Any) -> str:
        lines = [
            f"output {report['output']}; {len(report['cells'])} cells named",
            report["check"]["statement"],
        ]
        lines += [f"warning: {w}" for w in report["warnings"]]
        return "\n".join(lines)

    _out(args, result, human)
    return EXIT_OK if report["check"]["status"] != "disagreed" else EXIT_REFUSED


def model_diff(args: argparse.Namespace) -> int:
    result = _client(args).models.diff(args.ref, args.v1, args.v2)
    _out(args, result, lambda r: "\n".join(f"- {s}" for s in r["statements"]) or "no change")
    return EXIT_OK


def warrant_fetch(args: argparse.Namespace) -> int:
    c = _client(args)
    table, manifest = c.training_data(args.id)
    import pyarrow.parquet as pq

    pq.write_table(table, args.out)
    print(f"{args.out}: {table.num_rows} rows; checksum verified {manifest['checksum']}")
    return EXIT_OK


def warrant_upload_params(args: argparse.Namespace) -> int:
    """Upload fitted parameters. A `.json` file may carry metrics, a checksum and notes
    beside the values; an `.npz`, a scanned pickle or an ONNX graph carries values only
    (§9.3), so give --data-checksum and --notes on the command line for those."""
    raw = Path(args.file).read_bytes()
    fmt = args.format or _format_of(args.file)
    if fmt == "json":
        body = json.loads(raw.decode("utf-8"))
        values = body["values"] if "values" in body else parameters.read(raw, "json")
        metrics = body.get("metrics", {}) if isinstance(body, dict) else {}
        checksum = args.data_checksum or (
            body.get("data_checksum") if isinstance(body, dict) else None
        )
        notes = args.notes or (body.get("notes", "") if isinstance(body, dict) else "")
    else:
        values = parameters.read(raw, fmt)
        metrics, checksum, notes = {}, args.data_checksum, args.notes or ""
    result = _client(args).training.upload_parameters(
        args.id,
        values,
        metrics=metrics,
        data_checksum=checksum,
        notes=notes,
        **({"member_alias": args.member_alias} if args.member_alias else {}),
    )
    _out(
        args,
        result,
        lambda r: (
            f"parameter set {r['id']} uploaded; "
            f"{'verified data' if r['verified_data'] else 'UNVERIFIED DATA'}"
        ),
    )
    return EXIT_OK


def warrant_seal(args: argparse.Namespace) -> int:
    _out(args, _client(args).training.seal(args.id))
    return EXIT_OK


def admin_cold(args: argparse.Namespace) -> int:
    """Which pins have gone unread long enough to be called cold (§7.3)."""
    report = _client(args).admin.cold_pins(days=args.days)
    _out(
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
    out = _client(args).admin.archive_pin(args.pin_id, table=args.table)
    _out(
        args,
        out,
        lambda r: (
            f"archived {r['rows']} row(s) as blob {r['blob'][:16]}… "
            f"({r['bytes'] / 1e6:.2f} MB)\n{r.get('note', '')}"
        ),
    )
    return EXIT_OK


def admin_restore_pin(args: argparse.Namespace) -> int:
    out = _client(args).admin.restore_pin(args.pin_id, table=args.table)
    _out(
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


def _format_of(path: str) -> str:
    """The parameter format a file name implies (§9.3)."""
    for fmt, suffixes in (
        ("npz", (".npz",)),
        ("pickle", (".pkl", ".pickle")),
        ("onnx", (".onnx",)),
        ("json", (".json",)),
    ):
        if path.endswith(suffixes):
            return fmt
    raise MayaError(
        f"Cannot tell the parameter format of '{path}'; pass --format "
        f"({', '.join(parameters.FORMATS)})"
    )


def job_watch(args: argparse.Namespace) -> int:
    c = _client(args)
    job = c.wait(args.id, progress=lambda j: print(f"  {j['progress']:3d}% {j['message']}"))
    _out(args, job)
    return EXIT_OK


def job_cancel(args: argparse.Namespace) -> int:
    _out(args, _client(args).jobs.cancel(args.id))
    return EXIT_OK


def export_bundle(args: argparse.Namespace) -> int:
    c = _client(args)
    result = c.training.export_bundle(args.id)
    Path(args.out).write_bytes(c.admin.blob(result["blob"])["data"])
    print(f"{args.out}: signed bundle, {result['size']} bytes")
    return EXIT_OK


def export_verify(args: argparse.Namespace) -> int:
    """Offline: runs the bundle's own verify.py, needing no MAYA at all."""
    from maya.services.bundle import BundleService

    report = BundleService.verify_offline(Path(args.file).read_bytes())
    _out(
        args,
        report,
        lambda r: (
            "\n".join(
                f"  [{'ok' if c['ok'] else 'n/a' if c['ok'] is None else 'FAIL'}] {c['check']}"
                for c in r.get("checks", [])
            )
            + f"\nverified: {r.get('verified')}"
        ),
    )
    return EXIT_OK if report.get("verified") else EXIT_REFUSED


# -- argument parsing -------------------------------------------------------------------------

# -- admin, featureset build, model validate, warrant create (§18.3) ---------------------


def _definition(path: str) -> dict[str, Any]:
    """A definition read from JSON or YAML, whichever the file is."""
    text = Path(path).read_text(encoding="utf-8")
    if path.endswith((".yaml", ".yml")):
        import yaml

        return dict(yaml.safe_load(text))
    return dict(json.loads(text))


def admin_user_list(args: argparse.Namespace) -> int:
    rows = _client(args).admin.users()
    _out(args, rows, lambda r: _rows(r, ["username", "status", "roles", "last_login_at"]))
    return EXIT_OK


def admin_user_create(args: argparse.Namespace) -> int:
    password = args.password or os.environ.get("MAYA_NEW_PASSWORD")
    if not password:
        raise MayaError("Give --password, or put it in MAYA_NEW_PASSWORD")
    extra = {"email": args.email} if args.email else {}
    out = _client(args).admin.create_user(
        args.username, password=password, roles=args.role or [], **extra
    )
    roles = ", ".join(args.role or []) or "no roles"
    _out(args, out, lambda r: f"created {r['username']} with {roles}")
    return EXIT_OK


def admin_user_roles(args: argparse.Namespace) -> int:
    out = _client(args).admin.set_roles(args.username, args.role or [])
    held = ", ".join(out.get("roles") or args.role or []) or "no roles"
    _out(args, out, lambda r: f"{args.username} now holds {held}")
    return EXIT_OK


def admin_role_list(args: argparse.Namespace) -> int:
    rows = _client(args).admin.roles()
    _out(args, rows, lambda r: _rows(r, ["name", "description", "builtin"]))
    return EXIT_OK


def admin_role_create(args: argparse.Namespace) -> int:
    capabilities = {}
    for pair in args.capability or []:
        kind, _, letters = pair.partition("=")
        capabilities[kind.strip()] = letters.strip()
    out = _client(args).admin.create_role(args.name, capabilities, args.description or "")
    _out(args, out, lambda r: f"created role {r['name']}")
    return EXIT_OK


def admin_namespace_list(args: argparse.Namespace) -> int:
    rows = _client(args).namespaces.list()
    _out(
        args,
        rows,
        lambda r: _rows(r, ["name", "preset", "default_visibility", "production", "quota_bytes"]),
    )
    return EXIT_OK


def admin_namespace_create(args: argparse.Namespace) -> int:
    extra = {"quota_bytes": args.quota_bytes} if args.quota_bytes else {}
    out = _client(args).namespaces.create(
        args.name,
        preset=args.preset,
        production=args.production,
        default_visibility=args.visibility,
        **extra,
    )
    _out(args, out, lambda r: f"created namespace {r['name']} ({r['preset']})")
    return EXIT_OK


def admin_grant_list(args: argparse.Namespace) -> int:
    rows = _client(args).access.grants(args.kind, args.ref)
    _out(args, rows, lambda r: _rows(r, ["principal_type", "principal_id", "level", "expires_at"]))
    return EXIT_OK


def admin_grant_add(args: argparse.Namespace) -> int:
    out = _client(args).access.grant(
        args.kind,
        args.ref,
        args.principal_type,
        args.principal,
        args.level,
        days=args.days,
        deny=args.deny,
    )
    _out(args, out, lambda r: f"granted {r['level']} on {args.ref} to {args.principal}")
    return EXIT_OK


def admin_policy_list(args: argparse.Namespace) -> int:
    rows = _client(args).workflow.policies()
    _out(args, rows, lambda r: _rows(r, ["object_type", "scope", "version_no", "state"]))
    return EXIT_OK


def admin_policy_show(args: argparse.Namespace) -> int:
    print(_client(args).workflow.policy_yaml(args.id))
    return EXIT_OK


def admin_policy_import(args: argparse.Namespace) -> int:
    body = Path(args.file).read_text(encoding="utf-8")
    out = _client(args).workflow.import_policy(args.object_type, body, scope=args.scope)
    _out(args, out, lambda r: f"drafted policy {r['id']} for {r['object_type']} ({r['scope']})")
    return EXIT_OK


def admin_policy_activate(args: argparse.Namespace) -> int:
    out = _client(args).workflow.activate_policy(args.id)
    _out(args, out, lambda r: f"policy {r['id']} is {r['state']}")
    return EXIT_OK


def featureset_build(args: argparse.Namespace) -> int:
    """Create a feature set from a definition file, and optionally submit it for review."""
    namespace, _, name = args.ref.partition("/")
    if not name:
        raise MayaError("Name the set as namespace/name")
    c = _client(args)
    out = c.featuresets.create(namespace, name, _definition(args.file))
    if args.submit:
        out = c.featuresets.transition(args.ref, out.get("version_no", 1), "submit")
    _out(args, out, lambda r: f"{args.ref} is {r.get('state', 'draft')}")
    return EXIT_OK


def model_validate(args: argparse.Namespace) -> int:
    """What the server can say about a draft before it is submitted: how its formula
    conforms, and what the workflow would still ask for."""
    c = _client(args)
    model = c.models.get(args.ref)
    version = args.version or model.get("latest_version") or 1
    try:
        conformance = c.models.conformance(args.ref, version)
    except MayaError as exc:
        # a draft with no uploaded artifact cannot be conformance-tested; that is a thing
        # to report, not a reason for the command to fall over
        conformance = {"status": "not run", "reason": exc.message}
    problems = [str(x) for x in (conformance or {}).get("problems", [])]
    if conformance.get("status") == "not run":
        problems.append(conformance["reason"])
    report = {
        "ref": args.ref,
        "latest_version": model.get("latest_version"),
        "state": model.get("latest_state"),
        "conformance": conformance,
        "transitions": model.get("transitions"),
    }
    _out(
        args,
        report,
        lambda r: "\n".join(
            [f"{args.ref} v{r['latest_version']} is {r['state']}"]
            + ([f"  problem: {p}" for p in problems] or ["  nothing refused it"])
        ),
    )
    return EXIT_REFUSED if problems else EXIT_OK


def warrant_create(args: argparse.Namespace) -> int:
    namespace, _, name = args.ref.partition("/")
    if not name:
        raise MayaError("Name the warrant as namespace/name")
    spec = _definition(args.spec) if args.spec else {"target": args.target}
    out = _client(args).training.create(
        namespace, name, model=args.model, featureset=args.featureset, spec=spec
    )
    _out(
        args,
        out,
        lambda r: (
            f"{args.ref} v{r['version_no']} drawn on {r['featureset_ref']}; "
            f"leakage certificate: {r['leakage_certificate']['status']}"
        ),
    )
    return EXIT_OK


def _admin_commands(cmd: Callable[..., None], a: Any) -> None:
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


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="maya", description="MAYA command line")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    p.add_argument("--profile", help="profile in ~/.maya/config.toml")
    p.add_argument("--local", action="store_true", help="in-process platform, not a server")
    p.add_argument("--config", default="config/application.yaml")
    groups = p.add_subparsers(dest="group", required=True)

    def cmd(group: Any, name: str, fn: Callable[..., int], *arguments: tuple[Any, ...]) -> None:
        sp = group.add_parser(name)
        for spec in arguments:
            sp.add_argument(*spec[0], **spec[1])
        sp.set_defaults(fn=fn)

    a = groups.add_parser("admin").add_subparsers(dest="cmd", required=True)
    _admin_commands(cmd, a)

    f = groups.add_parser("feature").add_subparsers(dest="cmd", required=True)
    cmd(f, "list", feature_list, (("--namespace",), {}), (("-q",), {"dest": "q"}))
    cmd(f, "show", feature_show, (("ref",), {}))
    cmd(f, "quick", feature_quick, (("file",), {}), (("--name",), {}))
    cmd(
        f,
        "upload",
        feature_upload,
        (("ref",), {}),
        (("file",), {}),
        (("--knowledge-time",), {"dest": "knowledge_time"}),
    )
    cmd(
        f,
        "pin",
        feature_pin,
        (("ref",), {}),
        (("--version",), {"type": int, "required": True}),
        (("--name",), {"required": True}),
        (("--as-of",), {"dest": "as_of", "required": True}),
        (("--as-of-known",), {"dest": "as_of_known"}),
    )
    cmd(
        f,
        "download",
        feature_download,
        (("ref",), {}),
        (("--out",), {"required": True}),
        (("--format",), {"default": "parquet"}),
        (("--csv-encoding",), {"dest": "csv_encoding"}),
    )
    cmd(f, "diff", feature_diff, (("ref",), {}), (("v1",), {"type": int}), (("v2",), {"type": int}))

    fs = groups.add_parser("featureset").add_subparsers(dest="cmd", required=True)
    cmd(
        fs,
        "pin",
        featureset_pin,
        (("ref",), {}),
        (("--version",), {"type": int, "required": True}),
        (("--name",), {"required": True}),
        (("--as-of",), {"dest": "as_of", "required": True}),
        (("--cascade",), {"action": "store_true"}),
    )
    cmd(
        fs,
        "download",
        featureset_download,
        (("ref",), {}),
        (("--out",), {"required": True}),
        (("--format",), {"default": "parquet"}),
        (("--shape",), {"default": "tabular"}),
        (("--csv-encoding",), {"dest": "csv_encoding"}),
    )

    cmd(
        fs,
        "build",
        featureset_build,
        (("ref",), {}),
        (("file",), {"help": "definition as JSON or YAML"}),
        (("--submit",), {"action": "store_true"}),
    )

    m = groups.add_parser("model").add_subparsers(dest="cmd", required=True)
    cmd(m, "push", model_push, (("ref",), {}), (("file",), {}))
    cmd(
        m,
        "import-workbook",
        model_import_workbook,
        (("ref",), {}),
        (("file",), {}),
        (("--output",), {}),
        (("--role",), {"action": "append"}),
        (("--preview",), {"action": "store_true"}),
    )
    cmd(m, "diff", model_diff, (("ref",), {}), (("v1",), {"type": int}), (("v2",), {"type": int}))
    cmd(m, "validate", model_validate, (("ref",), {}), (("--version",), {"type": int}))

    w = groups.add_parser("warrant").add_subparsers(dest="cmd", required=True)
    cmd(
        w,
        "create",
        warrant_create,
        (("ref",), {}),
        (("--model",), {"required": True}),
        (("--featureset",), {"required": True}),
        (("--target",), {}),
        (("--spec",), {"help": "spec as JSON or YAML; overrides --target"}),
    )
    cmd(w, "fetch", warrant_fetch, (("id",), {}), (("--out",), {"required": True}))
    cmd(
        w,
        "upload-params",
        warrant_upload_params,
        (("id",), {}),
        (("file",), {}),
        (("--format",), {"choices": list(parameters.FORMATS), "help": "default: by file name"}),
        (("--data-checksum",), {"dest": "data_checksum"}),
        (("--notes",), {}),
        (("--member-alias",), {"dest": "member_alias", "help": "for one member of a composite"}),
    )
    cmd(w, "seal", warrant_seal, (("id",), {}))

    j = groups.add_parser("job").add_subparsers(dest="cmd", required=True)
    cmd(j, "watch", job_watch, (("id",), {}))
    cmd(j, "cancel", job_cancel, (("id",), {}))

    e = groups.add_parser("export").add_subparsers(dest="cmd", required=True)
    cmd(e, "bundle", export_bundle, (("id",), {}), (("--out",), {"required": True}))
    cmd(e, "verify", export_verify, (("file",), {}))
    return p


# ``--section.key=value`` overrides a setting (spec §24.2); the configuration reads them
# from the command line itself, so the parser only has to let them through.
_SETTING = re.compile(r"^--[A-Za-z_][\w-]*(\.[\w-]+)+=")


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args, extra = parser.parse_known_args(argv)
    unknown = [a for a in extra if not _SETTING.match(a)]
    if unknown:
        parser.error(f"unrecognized arguments: {' '.join(unknown)}")
    try:
        return args.fn(args)
    except MayaError as exc:
        code = getattr(exc, "code", "maya_error")
        print(f"maya: {type(exc).__name__}: {exc.message}", file=sys.stderr)
        if getattr(exc, "context", None):
            print("maya: " + json.dumps(exc.context, default=str, sort_keys=True), file=sys.stderr)
        return EXIT_NETWORK if code == "transport_error" else EXIT_REFUSED


if __name__ == "__main__":
    sys.exit(main())
