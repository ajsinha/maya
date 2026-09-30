"""
``python -m maya.cli <group> <command> …`` — see ``maya.cli`` for the rules.

This file builds the parser and holds the catalog, model, warrant, job and export
commands. The administrative group lives in ``maya.cli.admin`` and the credential group
in ``maya.cli.keys``; the plumbing all three share is in ``maya.cli.common``.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import argparse
import re
import json
import sys
from pathlib import Path
from typing import Any, Callable

from maya.cli.admin import admin_commands
from maya.cli import common
from maya.cli.common import (
    EXIT_NETWORK,
    EXIT_OK,
    EXIT_REFUSED,
    definition_file,
    emit,
    rows_table,
)
from maya.cli.keys import key_commands
from maya.core import parameters
from maya.core.errors import MayaError


# -- catalog --------------------------------------------------------------------------------
def feature_list(args: argparse.Namespace) -> int:
    rows = common.client(args).features.list(namespace=args.namespace, q=args.q)
    emit(
        args,
        rows,
        lambda r: rows_table(r, ["ref", "latest_version", "latest_state", "pins", "owner"]),
    )
    return EXIT_OK


def feature_show(args: argparse.Namespace) -> int:
    emit(args, common.client(args).features.get(args.ref))
    return EXIT_OK


def feature_quick(args: argparse.Namespace) -> int:
    path = Path(args.file)
    result = common.client(args).features.quick(
        path.read_bytes(), name=args.name or path.stem, fmt=path.suffix.lstrip(".") or "csv"
    )
    emit(
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
    result = common.client(args).features.ingest(
        args.ref,
        path.read_bytes(),
        fmt=path.suffix.lstrip("."),
        filename=path.name,
        knowledge_time=args.knowledge_time,
    )
    emit(
        args,
        result,
        lambda r: f"ingested {r['rows']} rows" + (" (a restatement)" if r["restatement"] else ""),
    )
    return EXIT_OK


def feature_pin(args: argparse.Namespace) -> int:
    c = common.client(args)
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
        emit(
            args,
            job["result"],
            lambda r: f"sealed {r['content_hash']} ({r['rows']} rows, {r['bytes_new']} new bytes)",
        )
    else:
        print("Pin requested; it awaits approval by a pin authorizer.")
    return EXIT_OK


def feature_download(args: argparse.Namespace) -> int:
    result = common.client(args).features.download(
        args.ref, format=args.format, csv_encoding=args.csv_encoding
    )
    Path(args.out).write_bytes(result["data"])
    print(
        f"{args.out}: {result['manifest'].get('rows')} rows, content hash "
        f"{result['manifest'].get('content_hash')}"
    )
    return EXIT_OK


def feature_diff(args: argparse.Namespace) -> int:
    emit(args, common.client(args).features.compare(args.ref, args.v1, args.v2))
    return EXIT_OK


def featureset_pin(args: argparse.Namespace) -> int:
    c = common.client(args)
    result = c.featuresets.pin(
        args.ref,
        version_no=args.version,
        pin_name=args.name,
        as_of=args.as_of,
        cascade=args.cascade,
    )
    job = c.wait(result["job"], progress=lambda j: print(f"  {j['progress']:3d}% {j['message']}"))
    emit(args, job["result"])
    return EXIT_OK


def featureset_download(args: argparse.Namespace) -> int:
    result = common.client(args).featuresets.download(
        args.ref, format=args.format, shape=args.shape, csv_encoding=args.csv_encoding
    )
    Path(args.out).write_bytes(result["data"])
    print(f"{args.out}: {result['manifest'].get('rows')} rows")
    return EXIT_OK


def model_push(args: argparse.Namespace) -> int:
    c = common.client(args)
    source = Path(args.file).read_text(encoding="utf-8")
    emit(args, c.models.upload_artifact(args.ref, source))
    return EXIT_OK


def model_import_workbook(args: argparse.Namespace) -> int:
    """Lift an Excel workbook into the model's draft (or only preview the lift)."""
    roles = {}
    for pair in args.role or []:
        name, _, role = pair.partition("=")
        roles[name.strip()] = role.strip() or "feature"
    data = Path(args.file).read_bytes()
    c = common.client(args)
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

    emit(args, result, human)
    return EXIT_OK if report["check"]["status"] != "disagreed" else EXIT_REFUSED


def model_diff(args: argparse.Namespace) -> int:
    result = common.client(args).models.diff(args.ref, args.v1, args.v2)
    emit(args, result, lambda r: "\n".join(f"- {s}" for s in r["statements"]) or "no change")
    return EXIT_OK


def warrant_fetch(args: argparse.Namespace) -> int:
    c = common.client(args)
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
    result = common.client(args).training.upload_parameters(
        args.id,
        values,
        metrics=metrics,
        data_checksum=checksum,
        notes=notes,
        **({"member_alias": args.member_alias} if args.member_alias else {}),
    )
    emit(
        args,
        result,
        lambda r: (
            f"parameter set {r['id']} uploaded; "
            f"{'verified data' if r['verified_data'] else 'UNVERIFIED DATA'}"
        ),
    )
    return EXIT_OK


def warrant_seal(args: argparse.Namespace) -> int:
    emit(args, common.client(args).training.seal(args.id))
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
    c = common.client(args)
    job = c.wait(args.id, progress=lambda j: print(f"  {j['progress']:3d}% {j['message']}"))
    emit(args, job)
    return EXIT_OK


def job_cancel(args: argparse.Namespace) -> int:
    emit(args, common.client(args).jobs.cancel(args.id))
    return EXIT_OK


def export_bundle(args: argparse.Namespace) -> int:
    c = common.client(args)
    result = c.training.export_bundle(args.id)
    Path(args.out).write_bytes(c.admin.blob(result["blob"])["data"])
    print(f"{args.out}: signed bundle, {result['size']} bytes")
    return EXIT_OK


def export_verify(args: argparse.Namespace) -> int:
    """Offline: runs the bundle's own verify.py, needing no MAYA at all."""
    from maya.services.bundle import BundleService

    report = BundleService.verify_offline(Path(args.file).read_bytes())
    emit(
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


# -- featureset build, model validate, warrant create (§18.3) ----------------------------
def featureset_build(args: argparse.Namespace) -> int:
    """Create a feature set from a definition file, and optionally submit it for review."""
    namespace, _, name = args.ref.partition("/")
    if not name:
        raise MayaError("Name the set as namespace/name")
    c = common.client(args)
    out = c.featuresets.create(namespace, name, definition_file(args.file))
    if args.submit:
        out = c.featuresets.transition(args.ref, out.get("version_no", 1), "submit")
    emit(args, out, lambda r: f"{args.ref} is {r.get('state', 'draft')}")
    return EXIT_OK


def model_validate(args: argparse.Namespace) -> int:
    """What the server can say about a draft before it is submitted: how its formula
    conforms, and what the workflow would still ask for."""
    c = common.client(args)
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
    emit(
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
    spec = definition_file(args.spec) if args.spec else {"target": args.target}
    out = common.client(args).training.create(
        namespace, name, model=args.model, featureset=args.featureset, spec=spec
    )
    emit(
        args,
        out,
        lambda r: (
            f"{args.ref} v{r['version_no']} drawn on {r['featureset_ref']}; "
            f"leakage certificate: {r['leakage_certificate']['status']}"
        ),
    )
    return EXIT_OK


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="maya", description="MAYA command line")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    p.add_argument("--profile", help="profile in ~/.maya/config.yaml")
    p.add_argument("--local", action="store_true", help="in-process platform, not a server")
    p.add_argument("--config", default="config/application.yaml")
    groups = p.add_subparsers(dest="group", required=True)

    def cmd(group: Any, name: str, fn: Callable[..., int], *arguments: tuple[Any, ...]) -> None:
        sp = group.add_parser(name)
        for spec in arguments:
            sp.add_argument(*spec[0], **spec[1])
        sp.set_defaults(fn=fn)

    a = groups.add_parser("admin").add_subparsers(dest="cmd", required=True)
    admin_commands(cmd, a)
    key_commands(cmd, groups)

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
