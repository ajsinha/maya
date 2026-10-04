"""
Real screenshots of MAYA for the documentation, taken from a live instance.

Builds a scratch estate (never the project's ``data/``) by running case studies against it,
starts MAYA on a spare port over that estate, signs in, finds real objects through the SDK,
and photographs each page with headless Chrome. Every screenshot in ``docs/`` comes from
here, so they can be retaken whenever the UI changes:

    python tools/docs/screenshots.py                 # into docs/architecture/img/screens
    python tools/docs/screenshots.py --only model    # retake some

The names are stable; documents refer to them by name.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs" / "architecture" / "img" / "screens"
STUDIES = (
    "01-retail-credit-pd-scorecard",
    "09-basel-irb-capital",
    "19-vendor-bureau-score",
    "49-llm-complaint-triage",
)
PASSWORD = "maya-dev-admin"
WORK = Path("/nonexistent")  # the scratch estate's home, masked in every picture


def _estate(work: Path) -> dict[str, str]:
    env = dict(
        os.environ,
        MAYA_HOME=str(work / "home"),
        MAYA_LAKE=str(work / "lake"),
        PYTHONPATH=os.pathsep.join([str(ROOT), str(ROOT / "sdk")]),
    )
    if (work / "home").exists():  # an estate this tool built before: reuse it
        return env
    for study in STUDIES:
        print(f"  populating: {study}")
        subprocess.run(
            [sys.executable, str(ROOT / "case_studies" / study / "run.py"), "--quiet"],
            env=env,
            cwd=ROOT,
            check=True,
            capture_output=True,
        )
    return env


def _serve(env: dict[str, str], port: int) -> subprocess.Popen[bytes]:
    proc = subprocess.Popen(
        [sys.executable, str(ROOT / "run_maya_web.py"), f"--server.port={port}"],
        env=env,
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    for _ in range(120):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/healthz", timeout=1)
            return proc
        except OSError:
            time.sleep(0.5)
    proc.terminate()
    raise SystemExit("MAYA did not start")


def _targets(base: str) -> list[tuple[str, str]]:
    """(name, path) for every page photographed, with real objects from the estate."""
    from maya.sdk import Client

    token = Client(base).auth.login("admin", PASSWORD)["token"]
    my = Client(base, token=token)
    models = my.models.list()
    model = next((m for m in models if "probability_of_default" in m["name"]), models[0])
    mref = f"{model['namespace']}/{model['name']}"
    feature = my.features.list()[0]
    fset = my.featuresets.list()[0]
    executions = my.execution.list()
    live = next((e for e in executions if e.get("status") == "live"), executions[0])
    training = my.training.list()[0]
    # lineage is recorded between versions and pins, so the canvas starts from a training
    # warrant: its feature set pin, the model version and what it licensed hang off it
    lineage_root = (
        training.get("uri") or f"maya://warrant/train/{training['namespace']}/{training['name']}@v1"
    )
    apps = my.llm.apps()
    out = [
        ("dashboard", "/"),
        ("catalog", "/catalog"),
        ("feature", f"/catalog/features/{feature['namespace']}/{feature['name']}"),
        ("featureset", f"/catalog/featuresets/{fset['namespace']}/{fset['name']}"),
        ("lineage", f"/lineage?root={lineage_root}&depth=3"),
        ("feature-designer", "/workbench/features/new"),
        ("model", f"/models/{mref}"),
        ("model-definition", f"/models/{mref}?tab=definition"),
        ("model-code", f"/models/{mref}?tab=code"),
        ("model-documents", f"/models/{mref}?tab=documents"),
        ("compute-kernel", "/models/kernel"),
        ("training-warrant", f"/warrants/training/{training['id']}"),
        ("execution-warrant", f"/warrants/execution/{live['id']}"),
        ("workflow-queue", "/workflow"),
        ("workflow-policies", "/workflow/policies"),
        ("governance", "/governance"),
        ("monitoring", "/monitoring"),
        ("integrations", "/integrations"),
        ("llm-apps", "/llm"),
        ("admin-ai", "/admin/ai"),
        ("admin-sources", "/admin/sources"),
        ("admin-extensions", "/admin/extensions"),
        ("admin-health", "/admin/health"),
        ("admin-jobs", "/admin/jobs"),
        ("admin-audit", "/admin/audit"),
        ("help", "/help"),
    ]
    if apps:
        out.append(("llm-app", f"/llm/{apps[0]['namespace']}/{apps[0]['name']}"))
    return out


def _shoot(base: str, targets: list[tuple[str, str]], out: Path, only: set[str]) -> None:
    from playwright.sync_api import sync_playwright

    out.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": 1400, "height": 900})
        page.emulate_media(color_scheme="light")
        if not only or "landing" in only:
            page.goto(base + "/", wait_until="networkidle")
            page.screenshot(path=str(out / "landing.png"))
        page.goto(base + "/login", wait_until="networkidle")
        page.fill("input[name=username]", "admin")
        page.fill("input[name=password]", PASSWORD)
        page.click("button[type=submit]")
        page.wait_for_load_state("networkidle")
        for name, path in targets:
            if only and name not in only:
                continue
            page.goto(base + path, wait_until="networkidle")
            page.wait_for_timeout(2500 if name == "lineage" else 400)  # graphs and maths settle
            # the scratch estate's own path says nothing about MAYA and something about the
            # machine the pictures were taken on
            page.evaluate(
                """m => { const t = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
                   for (let n; (n = t.nextNode());)
                     for (const [from, to] of m) n.nodeValue = n.nodeValue.split(from).join(to); }""",
                [
                    [str(WORK / "lake"), "$MAYA_LAKE"],
                    [str(WORK / "home"), "$MAYA_HOME"],
                    [str(WORK), "$MAYA_WORK"],
                    [str(Path.home()), "~"],
                ],
            )
            page.screenshot(path=str(out / f"{name}.png"))
            print(f"  {name:22s} {path}")
        browser.close()


def main() -> None:
    ap = argparse.ArgumentParser(description="Retake the documentation's screenshots.")
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--port", type=int, default=8791)
    ap.add_argument("--only", nargs="*", default=[])
    ap.add_argument("--work", help="a scratch directory to keep (default: a temporary one)")
    a = ap.parse_args()
    global WORK
    work = Path(a.work) if a.work else Path(tempfile.mkdtemp(prefix="maya-shots-"))
    WORK = work
    try:
        print("building a scratch estate")
        env = _estate(work)
        proc = _serve(env, a.port)
        try:
            base = f"http://127.0.0.1:{a.port}"
            _shoot(base, _targets(base), Path(a.out), set(a.only))
        finally:
            proc.terminate()
            proc.wait(timeout=30)
    finally:
        if not a.work:
            shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
