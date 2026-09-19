"""
``python -m maya.cli <group> <command> …`` — see ``maya.cli`` for the rules.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Callable

from maya.core.errors import MayaError

EXIT_OK, EXIT_REFUSED, EXIT_USAGE, EXIT_NETWORK = 0, 1, 2, 3


# -- plumbing -------------------------------------------------------------------------
def _client(args: argparse.Namespace) -> Any:
    from maya.sdk import Client, connect
    if args.local:
        from maya.config import load_settings
        from maya.server import build_app
        from maya.services.platform import Platform
        platform = Platform.build(load_settings(args.config), start_workers=True)
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
    print(f"Created the {db.dialect} schema from maya/persistence/schema/{db.dialect}.sql "
          f"(schema-hash {digest[:16]}…)")
    return EXIT_OK


def admin_export_estate(args: argparse.Namespace) -> int:
    platform = _local_platform(args)
    Path(args.out).write_bytes(platform.ops.export_estate())
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
    result = platform.ops.import_estate(Path(args.input).read_bytes())
    print(json.dumps(result, indent=2, default=str))
    return EXIT_OK


def admin_verify_integrity(args: argparse.Namespace) -> int:
    c = _client(args)
    result = c.admin.verify_integrity()
    _out(args, result, lambda r: f"{r['checked']} pin(s) checked; drift: {len(r['drift'])}; "
                                 f"audit chain ok: {r['audit_chain']['ok']}")
    return EXIT_OK if not result["drift"] and result["audit_chain"]["ok"] else EXIT_REFUSED


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
    result = _client(args).features.quick(path.read_bytes(), name=args.name or path.stem,
                                          fmt=path.suffix.lstrip(".") or "csv")
    _out(args, result, lambda r: f"{r['ref']}@v{r['version']}: {r['rows']} rows, ungoverned "
                                 f"scratch. Warnings: {r['warnings'] or 'none'}")
    return EXIT_OK


def feature_upload(args: argparse.Namespace) -> int:
    path = Path(args.file)
    result = _client(args).features.ingest(args.ref, path.read_bytes(),
                                           fmt=path.suffix.lstrip("."), filename=path.name,
                                           knowledge_time=args.knowledge_time)
    _out(args, result, lambda r: f"ingested {r['rows']} rows"
                                 + (" (a restatement)" if r["restatement"] else ""))
    return EXIT_OK


def feature_pin(args: argparse.Namespace) -> int:
    c = _client(args)
    result = c.features.pin(args.ref, version_no=args.version, pin_name=args.name,
                            as_of=args.as_of, as_of_known=args.as_of_known)
    if result.get("job"):
        job = c.wait(result["job"], progress=lambda j: print(f"  {j['progress']:3d}% {j['message']}"))
        _out(args, job["result"], lambda r: f"sealed {r['content_hash']} ({r['rows']} rows, "
                                            f"{r['bytes_new']} new bytes)")
    else:
        print("Pin requested; it awaits approval by a pin authorizer.")
    return EXIT_OK


def feature_download(args: argparse.Namespace) -> int:
    result = _client(args).features.download(args.ref, format=args.format,
                                             csv_encoding=args.csv_encoding)
    Path(args.out).write_bytes(result["data"])
    print(f"{args.out}: {result['manifest'].get('rows')} rows, content hash "
          f"{result['manifest'].get('content_hash')}")
    return EXIT_OK


def feature_diff(args: argparse.Namespace) -> int:
    _out(args, _client(args).features.compare(args.ref, args.v1, args.v2))
    return EXIT_OK


def featureset_pin(args: argparse.Namespace) -> int:
    c = _client(args)
    result = c.featuresets.pin(args.ref, version_no=args.version, pin_name=args.name,
                               as_of=args.as_of, cascade=args.cascade)
    job = c.wait(result["job"], progress=lambda j: print(f"  {j['progress']:3d}% {j['message']}"))
    _out(args, job["result"])
    return EXIT_OK


def featureset_download(args: argparse.Namespace) -> int:
    result = _client(args).featuresets.download(args.ref, format=args.format, shape=args.shape,
                                                csv_encoding=args.csv_encoding)
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
        result = c.models.lift_workbook(data, output=args.output, roles=roles,
                                        filename=Path(args.file).name)
        report = result["lifted_from"]["workbook"]
    else:
        result = c.models.import_workbook(args.ref, data, output=args.output, roles=roles,
                                          filename=Path(args.file).name)
        report = result["workbook"]

    def human(_: Any) -> str:
        lines = [f"output {report['output']}; {len(report['cells'])} cells named",
                 report["check"]["statement"]]
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
    body = json.loads(Path(args.file).read_text())
    result = _client(args).training.upload_parameters(
        args.id, body["values"], metrics=body.get("metrics", {}),
        data_checksum=body.get("data_checksum"), notes=body.get("notes", ""))
    _out(args, result, lambda r: f"parameter set {r['id']} uploaded; "
                                 f"{'verified data' if r['verified_data'] else 'UNVERIFIED DATA'}")
    return EXIT_OK


def warrant_seal(args: argparse.Namespace) -> int:
    _out(args, _client(args).training.seal(args.id))
    return EXIT_OK


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
    _out(args, report, lambda r: "\n".join(
        f"  [{'ok' if c['ok'] else 'n/a' if c['ok'] is None else 'FAIL'}] {c['check']}"
        for c in r.get("checks", [])) + f"\nverified: {r.get('verified')}")
    return EXIT_OK if report.get("verified") else EXIT_REFUSED


# -- argument parsing -------------------------------------------------------------------------
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
    cmd(a, "init-db", admin_init_db, (("--force",), {"action": "store_true"}))
    cmd(a, "export-estate", admin_export_estate, (("--out",), {"required": True}))
    cmd(a, "import-estate", admin_import_estate, (("--in",), {"dest": "input", "required": True}))
    cmd(a, "verify-integrity", admin_verify_integrity)

    f = groups.add_parser("feature").add_subparsers(dest="cmd", required=True)
    cmd(f, "list", feature_list, (("--namespace",), {}), (("-q",), {"dest": "q"}))
    cmd(f, "show", feature_show, (("ref",), {}))
    cmd(f, "quick", feature_quick, (("file",), {}), (("--name",), {}))
    cmd(f, "upload", feature_upload, (("ref",), {}), (("file",), {}),
        (("--knowledge-time",), {"dest": "knowledge_time"}))
    cmd(f, "pin", feature_pin, (("ref",), {}), (("--version",), {"type": int, "required": True}),
        (("--name",), {"required": True}), (("--as-of",), {"dest": "as_of", "required": True}),
        (("--as-of-known",), {"dest": "as_of_known"}))
    cmd(f, "download", feature_download, (("ref",), {}), (("--out",), {"required": True}),
        (("--format",), {"default": "parquet"}), (("--csv-encoding",), {"dest": "csv_encoding"}))
    cmd(f, "diff", feature_diff, (("ref",), {}), (("v1",), {"type": int}), (("v2",), {"type": int}))

    fs = groups.add_parser("featureset").add_subparsers(dest="cmd", required=True)
    cmd(fs, "pin", featureset_pin, (("ref",), {}), (("--version",), {"type": int, "required": True}),
        (("--name",), {"required": True}), (("--as-of",), {"dest": "as_of", "required": True}),
        (("--cascade",), {"action": "store_true"}))
    cmd(fs, "download", featureset_download, (("ref",), {}), (("--out",), {"required": True}),
        (("--format",), {"default": "parquet"}), (("--shape",), {"default": "tabular"}),
        (("--csv-encoding",), {"dest": "csv_encoding"}))

    m = groups.add_parser("model").add_subparsers(dest="cmd", required=True)
    cmd(m, "push", model_push, (("ref",), {}), (("file",), {}))
    cmd(m, "import-workbook", model_import_workbook, (("ref",), {}), (("file",), {}),
        (("--output",), {}), (("--role",), {"action": "append"}),
        (("--preview",), {"action": "store_true"}))
    cmd(m, "diff", model_diff, (("ref",), {}), (("v1",), {"type": int}), (("v2",), {"type": int}))

    w = groups.add_parser("warrant").add_subparsers(dest="cmd", required=True)
    cmd(w, "fetch", warrant_fetch, (("id",), {}), (("--out",), {"required": True}))
    cmd(w, "upload-params", warrant_upload_params, (("id",), {}), (("file",), {}))
    cmd(w, "seal", warrant_seal, (("id",), {}))

    j = groups.add_parser("job").add_subparsers(dest="cmd", required=True)
    cmd(j, "watch", job_watch, (("id",), {}))
    cmd(j, "cancel", job_cancel, (("id",), {}))

    e = groups.add_parser("export").add_subparsers(dest="cmd", required=True)
    cmd(e, "bundle", export_bundle, (("id",), {}), (("--out",), {"required": True}))
    cmd(e, "verify", export_verify, (("file",), {}))
    return p


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        return args.fn(args)
    except MayaError as exc:
        code = getattr(exc, "code", "maya_error")
        print(f"maya: {type(exc).__name__}: {exc.message}", file=sys.stderr)
        return EXIT_NETWORK if code == "transport_error" else EXIT_REFUSED


if __name__ == "__main__":
    sys.exit(main())
