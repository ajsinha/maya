"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section I — backup and restore.

These run the CLI, not the API, because the CLI is what a recovery script
runs — and the thing a recovery script reads is the **exit code**. A tool that
prints a warning and returns 0 has told a human something and told the script
nothing, and the script's next step is usually "start serving".
"""
from __future__ import annotations

import json
import pathlib
import shutil
import tempfile

from tools.qa.scenarios.common import BLOCKED, FAIL, PASS, Ctx, Result, case
from tools.qa.harness import CONFIG


def _instance(root: pathlib.Path) -> pathlib.Path:
    """A configured, populated instance under `root`. Returns its config."""
    from fastapi.testclient import TestClient

    from core.config import PropertiesConfigurator
    from run_maya_web import create_app

    root.mkdir(parents=True, exist_ok=True)
    cfg = root / "application.yaml"
    cfg.write_text(CONFIG.format(root=root), encoding="utf-8")
    PropertiesConfigurator.reset()
    app = create_app(PropertiesConfigurator(str(cfg), reload_interval=0))
    held = None
    with TestClient(app, raise_server_exceptions=False) as client:
        held = (getattr(app.state, "ctx", {}) or {}).get("db")
        client.auth = ("admin", "maya-admin-dev")
        for n in range(3):
            name = f"ops{n}"
            client.post("/api/v1/models", json={
                "urn": f"maya://model/{name}", "name": name, "owner": "admin",
                "model_class": "logistic", "domain": "credit",
                "legal_entity": "LE-US-01", "purpose": "credit_decision"})
    # Let go of the database before anybody copies it. A live SQLite handle
    # makes `VACUUM INTO` answer "database is locked" — the backup tool being
    # right about a fixture that was wrong.
    if held is not None:
        held.engine.dispose()
    PropertiesConfigurator.reset()
    return cfg


def _exit_code(call) -> int:
    """Run a CLI entry point and return what a shell would see.

    `main()` returns an int on the ordinary paths and raises `SystemExit` on
    the refusals — which is a BaseException, so a case that only catches
    `Exception` lets it end the entire run. It ended this one at the first
    tool that behaved correctly.
    """
    try:
        return int(call() or 0)
    except SystemExit as exited:
        # `sys.exit("a sentence")` is the ordinary way a CLI refuses, and the
        # code is then the message, not a number. A shell reports 1 for it.
        code = exited.code
        if code is None:
            return 0
        return code if isinstance(code, int) else 1


def _backup(cfg: pathlib.Path, out: pathlib.Path) -> int:
    from tools.ops import backup
    return _exit_code(lambda: backup.main(
        ["--config", str(cfg), "--out", str(out), "--json"]))


def _restore(cfg: pathlib.Path, src: pathlib.Path, force: bool = False) -> int:
    from tools.ops import restore
    argv = ["--from", str(src), "--config", str(cfg), "--json"]
    if force:
        argv.append("--force")
    return _exit_code(lambda: restore.main(argv))


@case("QA-PLT-218", "A backup round-trips and the chain arrives intact",
      isolated=True)
def plt_218(ctx: Ctx) -> Result:
    work = pathlib.Path(tempfile.mkdtemp(prefix="qa-ops-"))
    try:
        cfg = _instance(work / "live")
        out = work / "backup"
        if _backup(cfg, out) != 0:
            return FAIL, "the backup itself failed"
        target = _instance(work / "target")
        code = _restore(target, out, force=True)
        if code != 0:
            return FAIL, f"a clean restore exited {code}"
        return PASS, "backed up and restored, exit 0"
    finally:
        shutil.rmtree(work, ignore_errors=True)


@case("QA-PLT-220", "Back up into a directory that already holds something",
      isolated=True)
def plt_220(ctx: Ctx) -> Result:
    work = pathlib.Path(tempfile.mkdtemp(prefix="qa-ops-"))
    try:
        cfg = _instance(work / "live")
        out = work / "backup"
        out.mkdir(parents=True)
        (out / "something").write_text("in the way", encoding="utf-8")
        try:
            code = _backup(cfg, out)
        except Exception as refused:
            return PASS, f"refused: {str(refused)[:130]}"
        if code == 0:
            return FAIL, ("a backup was written into a directory that already "
                          "held something; two backups in one directory is a "
                          "restore of neither")
        return PASS, f"exited {code}"
    finally:
        shutil.rmtree(work, ignore_errors=True)


@case("QA-PLT-224", "Restore over an instance that holds evidence",
      isolated=True)
def plt_224(ctx: Ctx) -> Result:
    """Two chains do not interleave. Without `--force` this must refuse."""
    work = pathlib.Path(tempfile.mkdtemp(prefix="qa-ops-"))
    try:
        cfg = _instance(work / "live")
        out = work / "backup"
        _backup(cfg, out)
        target = _instance(work / "target")
        try:
            code = _restore(target, out, force=False)
        except Exception as refused:
            return PASS, f"refused: {str(refused)[:130]}"
        if code == 0:
            return FAIL, ("a restore over a populated instance succeeded "
                          "without --force")
        return PASS, f"exited {code}"
    finally:
        shutil.rmtree(work, ignore_errors=True)


@case("QA-PLT-228", "A store's digest differs from the manifest",
      isolated=True)
def plt_228(ctx: Ctx) -> Result:
    """The exit code is what a recovery script reads.

    `DIGEST DIFFERS` was printed and the tool exited 0, so the script's next
    step — start serving — ran over artifacts that are not the ones backed up.
    """
    work = pathlib.Path(tempfile.mkdtemp(prefix="qa-ops-"))
    try:
        cfg = _instance(work / "live")
        out = work / "backup"
        _backup(cfg, out)
        from tools.ops.common import MANIFEST
        manifest_path = out / MANIFEST
        if not manifest_path.is_file():
            return BLOCKED, "no manifest written"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        stores = manifest.get("stores") or {}
        target_store = next((n for n, s in stores.items() if s.get("present")),
                            None)
        if target_store is None:
            return BLOCKED, "no present store to tamper with"
        stores[target_store]["digest"] = "sha256:" + "0" * 64
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        target = _instance(work / "target")
        code = _restore(target, out, force=True)
        if code == 0:
            return FAIL, ("a store's digest did not match the manifest and "
                          "the tool exited 0 — the recovery script proceeds "
                          "to serve artifacts that are not the ones backed up")
        return PASS, f"exited {code}"
    finally:
        shutil.rmtree(work, ignore_errors=True)


@case("QA-PLT-230", "A manifest missing a required section", isolated=True)
def plt_230(ctx: Ctx) -> Result:
    """A bare KeyError tells an operator in the middle of a recovery nothing
    about which file is wrong or what to do next."""
    work = pathlib.Path(tempfile.mkdtemp(prefix="qa-ops-"))
    try:
        cfg = _instance(work / "live")
        out = work / "backup"
        _backup(cfg, out)
        from tools.ops.common import MANIFEST
        manifest_path = out / MANIFEST
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest.pop("chain", None)
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        target = _instance(work / "target")
        try:
            code = _restore(target, out, force=True)
        except KeyError as bare:
            return FAIL, (f"a truncated manifest raised a bare KeyError "
                          f"({bare}) — an operator mid-recovery is told a "
                          f"dictionary key and nothing else")
        except Exception as refused:
            said = str(refused)
            if len(said) < 30:
                return FAIL, f"refused with too little to act on: {said!r}"
            return PASS, f"refused with a sentence: {said[:130]}"
        if code == 0:
            return FAIL, "a truncated manifest restored and exited 0"
        return PASS, f"exited {code}"
    finally:
        shutil.rmtree(work, ignore_errors=True)
