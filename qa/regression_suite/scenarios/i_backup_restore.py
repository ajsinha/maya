"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section I — taking a copy, and putting one back.

A backup is read by somebody who did not take it, months later, in the middle
of something going wrong. So the manifest carries what it holds AND what it
does not, the chain head is recorded so a restore has something to be checked
against, and every way the restore can be wrong has to reach the exit code —
because this runs in a recovery script whose next step is *start serving*.

Two things here were learned by the tool catching itself on its first round
trip. The database is copied LAST and consistently, and the write-ahead log is
removed with the old handle: a stale `-wal` replayed over a restored database
gave a chain at seq 0 with every byte correct and the digest matching, which is
the quietest way to lose an audit trail there is.
"""
from __future__ import annotations

import json
import pathlib
import shutil
import tempfile

from qa.regression_suite.scenarios.common import (BLOCKED, FAIL, PASS, Ctx,
                                                  Result, case)

M = "/api/v1/models"
SHAPE = {"model_class": "logistic", "domain": "credit",
         "legal_entity": "LE-US-01", "purpose": "credit_decision"}
CONFIG = """
app: {{name: MAYA, version: "0.1.0"}}
server: {{host: 0.0.0.0, port: 5006}}
database: {{url: "sqlite:///{root}/data/sqlite/maya.db"}}
data: {{dir: "{root}/data", artifacts: "{root}/data/artifacts",
        attachments: "{root}/data/attachments",
        delta: {{dir: "{root}/data/delta"}}}}
logging: {{level: ERROR}}
"""


def _instance(acts: int = 3):
    """A small instance on disk, with a chain in it."""
    from core.config import PropertiesConfigurator
    from db.database import Database
    from db.repositories import EvidenceRepository
    from core.evidence.engine import EvidenceEngine
    root = pathlib.Path(tempfile.mkdtemp(prefix="maya-ops-"))
    (root / "data" / "sqlite").mkdir(parents=True)
    for store in ("artifacts", "attachments", "worm", "delta"):
        (root / "data" / store).mkdir(parents=True, exist_ok=True)
        (root / "data" / store / "a-file").write_bytes(b"content")
    config = root / "application.yaml"
    config.write_text(CONFIG.format(root=root), encoding="utf-8")
    PropertiesConfigurator.reset()
    cfg = PropertiesConfigurator(str(config), reload_interval=0)
    db = Database(cfg.get("database.url"))
    db.apply_schema()
    engine = EvidenceEngine(EvidenceRepository(db))
    for n in range(acts):
        with engine.recording():
            engine.append("qa_act", "model", f"subject-{n}",
                          {"n": n}, actor="qa")
    db.engine.dispose()
    return root, str(config)


def _backup(config: str, out: str, **kw):
    from tools.ops import backup
    return backup.run(config, out, **kw)


def _restore(source: str, config: str, **kw):
    from tools.ops import restore
    return restore.run(source, config, **kw)


@case("QA-PLT-235", "Back up, restore, and verify the chain end to end",
      isolated=True)
def plt_235(ctx: Ctx) -> Result:
    """The round trip. Chain valid, head agreeing, every store digest
    matching — and the `-wal` handled, which is the half that once produced
    a perfect-looking restore with an empty audit trail."""
    root, config = _instance(4)
    out = str(root / "backup")
    try:
        manifest = _backup(config, out)
        if not manifest["chain"]["verifies"]:
            return BLOCKED, "the fresh instance's chain does not verify"
        head = manifest["chain"]["seq"]
        target_root, target_config = _instance(0)
        result = _restore(out, target_config)
    except SystemExit as exc:
        return BLOCKED, f"the round trip refused: {str(exc)[:200]}"
    if not result["chain"]["head_agrees"]:
        return FAIL, (f"the restored head is {result['chain']['seq']} against "
                      f"{result['chain']['expected_seq']} in the manifest")
    if not result["chain"]["verifies"]:
        return FAIL, f"the restored chain does not verify: {result['detail'][:140]}"
    if not result["database_digest_matches"]:
        return FAIL, "the restored database does not hash to the manifest"
    differing = [name for name, s in result["stores"].items()
                 if s.get("present") and not s.get("matches")]
    if differing:
        return FAIL, f"these store digests differ after the restore: {differing}"
    if result["chain"]["seq"] != head:
        return FAIL, "the restored sequence is not the one backed up"
    shutil.rmtree(root, ignore_errors=True)
    shutil.rmtree(target_root, ignore_errors=True)
    return PASS, (f"{head} node(s) backed up and restored; head agrees, chain "
                  f"verifies, every store digest matches")


@case("QA-PLT-219", "A backup of a broken chain, with and without the flag",
      isolated=True)
def plt_219(ctx: Ctx) -> Result:
    """Refused by default. A backup of a broken chain is restored months
    later and is indistinguishable from a chain that broke during the
    restore, so the investigation starts on the wrong day. With the flag it
    is a forensic copy that says so in its manifest."""
    root, config = _instance(3)
    from db.database import Database
    from core.config import PropertiesConfigurator
    PropertiesConfigurator.reset()
    cfg = PropertiesConfigurator(config, reload_interval=0)
    db = Database(cfg.get("database.url"))
    last = db.query("SELECT seq FROM evidence_node ORDER BY seq DESC LIMIT 1")
    db.execute(
        "INSERT INTO evidence_node (id, seq, kind, subject_type, subject_id, "
        "payload, parents, contains_personal_data, content_hash, prev_hash, "
        "chain_hash, trust, recorded_at, recorded_by) VALUES "
        "(:i, :s, 'qa_break', 'model', 'qa', '{}', '[]', 0, :c, :p, :c, 1.0, "
        "0.0, 'qa')",
        {"i": "qa-ops-break", "s": last[0]["seq"] + 1,
         "c": "sha256:" + "0" * 64, "p": "sha256:" + "1" * 64})
    db.engine.dispose()
    refused = None
    try:
        _backup(config, str(root / "plain"))
    except SystemExit as exc:
        refused = str(exc)
    if refused is None:
        return FAIL, "a backup of a broken chain was taken without the flag"
    if "--even-if-broken" not in refused:
        return FAIL, f"the refusal does not name the flag: {refused[:170]}"
    if "wrong day" not in refused and "indistinguishable" not in refused:
        return FAIL, f"the refusal does not say why it matters: {refused[:170]}"
    try:
        manifest = _backup(config, str(root / "forensic"), even_if_broken=True)
    except SystemExit as exc:
        return FAIL, f"the forensic copy was refused too: {str(exc)[:170]}"
    if manifest["chain"]["verifies"]:
        return FAIL, "the forensic manifest claims the chain verifies"
    if not manifest.get("chain_reason") and not manifest["chain"].get("broken_at"):
        return FAIL, (f"the manifest records a broken chain and neither where "
                      f"nor why: {manifest['chain']}")
    shutil.rmtree(root, ignore_errors=True)
    return PASS, (f"refused by default naming the flag; the forensic copy "
                  f"records verifies=False at seq "
                  f"{manifest['chain'].get('broken_at')}")


@case("QA-PLT-223", "Back up an instance with `data/worm/` missing",
      isolated=True)
def plt_223(ctx: Ctx) -> Result:
    """Recorded as ABSENT rather than skipped. A store missing from a backup
    and a store that was empty read the same on the way back in, and only
    one of them means the anchors are gone."""
    root, config = _instance(2)
    shutil.rmtree(root / "data" / "worm")
    try:
        manifest = _backup(config, str(root / "backup"))
    except SystemExit as exc:
        return PASS, f"refused loudly: {str(exc)[:130]}"
    worm = (manifest.get("stores") or {}).get("worm")
    if worm is None:
        return FAIL, (f"the missing store is not in the manifest at all: "
                      f"{sorted(manifest.get('stores') or {})}")
    if worm.get("present") is not False:
        return FAIL, f"a missing store is recorded as present: {worm}"
    if worm.get("digest") is not None:
        return FAIL, f"an absent store carries a digest: {worm}"
    if not worm.get("source"):
        return FAIL, "the manifest does not say where it looked"
    target_root, target_config = _instance(0)
    try:
        result = _restore(str(root / "backup"), target_config)
    except SystemExit as exc:
        return BLOCKED, f"the restore refused: {str(exc)[:150]}"
    if (result["stores"].get("worm") or {}).get("present") is not False:
        return FAIL, "the restore reports a store the backup did not hold"
    shutil.rmtree(root, ignore_errors=True)
    shutil.rmtree(target_root, ignore_errors=True)
    return PASS, ("absent in the manifest with the path it looked at, and "
                  "absent again after the restore — not silently skipped")


@case("QA-PLT-225", "A restore over an instance holding evidence, with --force",
      isolated=True)
def plt_225(ctx: Ctx) -> Result:
    """Refused without the flag, because two chains do not interleave and
    there is no merge. With it, the target is destroyed deliberately — and
    the chain that comes back has to be the backup's, not a blend."""
    root, config = _instance(4)
    out = str(root / "backup")
    try:
        manifest = _backup(config, out)
    except SystemExit as exc:
        return BLOCKED, f"the backup refused: {str(exc)[:150]}"
    target_root, target_config = _instance(7)
    refused = None
    try:
        _restore(out, target_config)
    except SystemExit as exc:
        refused = str(exc)
    if refused is None:
        return FAIL, ("a restore ran over an instance holding evidence with "
                      "no --force")
    if "--force" not in refused:
        return FAIL, f"the refusal does not name the flag: {refused[:170]}"
    if "interleave" not in refused and "irreversible" not in refused:
        return FAIL, f"the refusal does not say why: {refused[:170]}"
    # Deterministic, before the retry: does the refusal path let go of the
    # target? Whether a stale SQLite handle actually BLOCKS the next open
    # depends on pressure, so a case that only reported the lock would pass
    # and fail by timing.
    import inspect

    from tools.ops import restore as module
    body = inspect.getsource(module.run)
    opened = body.index("db = open_database(cfg)")
    refusal = body.index("refusing to restore over a database holding")
    disposed = body.find("dispose()", opened, refusal)
    if disposed == -1:
        return FAIL, (
            "the refusal is right and the tool does not let go. "
            "`restore.run` opens the target with `open_database(cfg)` and "
            "then raises SystemExit for the evidence it found, with no "
            "`dispose()` between the two — so the connection outlives the "
            "refusal. Retrying with `--force` IN THE SAME PROCESS, which is "
            "what the refusal's own remediation tells somebody to do, then "
            "meets a database this process is still holding. Harmless from a "
            "shell, where the process exits between the two; not harmless "
            "from a recovery script that catches the refusal and retries, "
            "which is the way a restore is actually driven")
    try:
        result = _restore(out, target_config, force=True)
    except SystemExit as exc:
        return FAIL, f"--force was refused too: {str(exc)[:170]}"
    if result["chain"]["seq"] != manifest["chain"]["seq"]:
        return FAIL, (f"after --force the chain is at "
                      f"{result['chain']['seq']} against the backup's "
                      f"{manifest['chain']['seq']} — the two interleaved")
    if not result["chain"]["head_agrees"] or not result["chain"]["verifies"]:
        return FAIL, f"the forced restore left a chain that is wrong: {result}"
    shutil.rmtree(root, ignore_errors=True)
    shutil.rmtree(target_root, ignore_errors=True)
    return PASS, (f"refused naming --force; with it the target's 7 acts are "
                  f"replaced by the backup's {manifest['chain']['seq']} and "
                  f"the chain verifies")


@case("QA-PLT-226", "A restore whose head disagrees with the manifest",
      isolated=True)
def plt_226(ctx: Ctx) -> Result:
    """`head_agrees: false`, a non-zero exit, and a detail that says it is a
    restore of a different instance. A recovery script reads the exit code
    and its next step is to start serving."""
    from tools.ops import restore as module
    root, config = _instance(4)
    out = str(root / "backup")
    try:
        _backup(config, out)
    except SystemExit as exc:
        return BLOCKED, f"the backup refused: {str(exc)[:150]}"
    manifest_path = pathlib.Path(out) / "maya-backup.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["chain"]["seq"] = manifest["chain"]["seq"] + 99
    manifest["chain"]["chain_hash"] = "sha256:" + "d" * 64
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    target_root, target_config = _instance(0)
    try:
        result = _restore(out, target_config)
    except SystemExit as exc:
        return BLOCKED, f"the restore refused outright: {str(exc)[:150]}"
    if result["chain"]["head_agrees"]:
        return FAIL, "a head 99 ahead of the database agrees with it"
    # A FRESH target for the CLI run: the restore above already filled the
    # first one, and a second restore over it is refused for holding
    # evidence rather than for the head disagreeing.
    cli_root, cli_config = _instance(0)
    code = module.main(["--from", out, "--config", cli_config])
    shutil.rmtree(cli_root, ignore_errors=True)
    if code == 0:
        return FAIL, ("the head disagrees and the tool exits 0; a recovery "
                      "script's next step is to start serving")
    detail = result["detail"]
    if "different" not in detail and "disagree" not in detail:
        return FAIL, f"the detail does not say what is wrong: {detail[:150]}"
    shutil.rmtree(root, ignore_errors=True)
    shutil.rmtree(target_root, ignore_errors=True)
    return PASS, f"head_agrees false, exit {code}: {detail[:110]}"


@case("QA-PLT-229", "A manifest from a different build",
      isolated=True)
def plt_229(ctx: Ctx) -> Result:
    """A manifest is the only thing a restore has to check itself against.
    One this build cannot read has to be refused rather than read
    optimistically — a section that moved between versions is a section the
    restore silently skips."""
    from tools.ops.common import MANIFEST_VERSION
    root, config = _instance(3)
    out = str(root / "backup")
    try:
        _backup(config, out)
    except SystemExit as exc:
        return BLOCKED, f"the backup refused: {str(exc)[:150]}"
    manifest_path = pathlib.Path(out) / "maya-backup.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["manifest_version"] = 99
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    _, target_config = _instance(0)
    try:
        _restore(out, target_config)
    except SystemExit as exc:
        said = str(exc)
        if "99" not in said and "version" not in said.lower():
            return FAIL, f"refused for another reason: {said[:170]}"
        shutil.rmtree(root, ignore_errors=True)
        return PASS, f"refused a manifest from another build: {said[:120]}"
    truncated = dict(manifest)
    truncated.pop("stores")
    manifest_path.write_text(json.dumps(truncated), encoding="utf-8")
    _, second_config = _instance(0)
    try:
        _restore(out, second_config)
    except SystemExit as exc:
        said = str(exc)
        if "Nothing has been restored" not in said:
            return FAIL, (f"a truncated manifest is refused without saying "
                          f"nothing was touched: {said[:150]}")
        return FAIL, (
            f"a manifest declaring `manifest_version: 99` — a version this "
            f"build does not write (it writes {MANIFEST_VERSION}) — was "
            f"restored without a word, while a manifest missing a SECTION is "
            f"refused by name. The version field is written into every "
            f"manifest and read by nothing, so a backup from a future build "
            f"whose sections have moved is restored optimistically and the "
            f"parts this build cannot see are silently skipped")
    return FAIL, ("neither a wrong manifest version nor a missing section is "
                  "refused")


@case("QA-PLT-232", "Restore run from a different working directory",
      isolated=True)
def plt_232(ctx: Ctx) -> Result:
    """The same target either way. A tool that resolved a path against the
    process's working directory would restore into a different place
    depending on where somebody stood when they ran it."""
    import os
    root, config = _instance(3)
    out = str(root / "backup")
    try:
        manifest = _backup(config, out)
    except SystemExit as exc:
        return BLOCKED, f"the backup refused: {str(exc)[:150]}"
    was = os.getcwd()
    results = {}
    for where in (was, tempfile.gettempdir()):
        target_root, target_config = _instance(0)
        os.chdir(where)
        try:
            results[where] = _restore(out, target_config)
        except SystemExit as exc:
            os.chdir(was)
            return BLOCKED, f"the restore refused from {where}: {str(exc)[:130]}"
        finally:
            os.chdir(was)
        shutil.rmtree(target_root, ignore_errors=True)
    heads = {r["chain"]["seq"] for r in results.values()}
    if len(heads) != 1:
        return FAIL, f"two working directories gave two chains: {heads}"
    if not all(r["chain"]["head_agrees"] for r in results.values()):
        return FAIL, f"a restore from one directory disagreed: {results}"
    shutil.rmtree(root, ignore_errors=True)
    return PASS, (f"identical restores from two working directories, head "
                  f"{heads.pop()} against the manifest's "
                  f"{manifest['chain']['seq']}")


@case("QA-PLT-233", "The two ways the restore exits 1",
      isolated=True)
def plt_233(ctx: Ctx) -> Result:
    """"Refused before doing anything" and "restored, and the chain is
    wrong" are the same exit code and must not be the same message. The
    first leaves the target untouched; the second leaves an instance
    somebody must not put in front of anybody."""
    from tools.ops import restore as module
    root, config = _instance(3)
    out = str(root / "backup")
    try:
        _backup(config, out)
    except SystemExit as exc:
        return BLOCKED, f"the backup refused: {str(exc)[:150]}"
    # (1) refused before touching anything: a manifest that is not there.
    empty = pathlib.Path(tempfile.mkdtemp(prefix="maya-nomanifest-"))
    target_root, target_config = _instance(0)
    before = None
    try:
        _restore(str(empty), target_config)
    except SystemExit as exc:
        before = str(exc)
    if before is None:
        return FAIL, "a directory with no manifest was restored"
    if "Without the manifest" not in before and "not a MAYA backup" not in before:
        return FAIL, f"the refusal does not say what is wrong: {before[:150]}"
    # (2) restored, and wrong.
    manifest_path = pathlib.Path(out) / "maya-backup.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["chain"]["chain_hash"] = "sha256:" + "e" * 64
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    cli_root, cli_config = _instance(0)
    code = module.main(["--from", out, "--config", cli_config])
    shutil.rmtree(cli_root, ignore_errors=True)
    if code == 0:
        return FAIL, "a restore whose head disagrees exits 0"
    shutil.rmtree(root, ignore_errors=True)
    shutil.rmtree(target_root, ignore_errors=True)
    shutil.rmtree(empty, ignore_errors=True)
    return PASS, (f"refused before touching anything with its own message, "
                  f"and exit {code} after restoring with a head that "
                  f"disagrees — two states, one code, two sentences")


@case("QA-PLT-222", "Back up an instance on a dialect that is neither")
def plt_222(ctx: Ctx) -> Result:
    """The message must not say PostgreSQL to somebody on MySQL. A
    remediation naming the wrong tool is worse than none, because it reads
    as though somebody checked."""
    from tools.ops import backup as module
    import inspect
    source = inspect.getsource(module.run)
    if "pg_dump" not in source:
        return BLOCKED, "the PostgreSQL branch is gone"
    branches = [ln for ln in source.splitlines() if "startswith(\"sqlite\")" in ln]
    if not branches:
        return FAIL, "nothing narrows the backup to SQLite"
    if "dialect ==" in source and "postgres" in source.lower():
        return PASS, "each dialect has its own branch"
    return FAIL, (
        "the tool branches on `not dialect.startswith('sqlite')` and every "
        "non-SQLite dialect is told about `pg_dump` and `pg_basebackup`. An "
        "operator on MySQL, Oracle or a typo in the URL is handed PostgreSQL "
        "instructions — the remediation is confident and wrong, which reads "
        "as though somebody checked the dialect and did not. The refusal is "
        "right; only its addressee is assumed")
