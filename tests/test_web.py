"""
The web UI, end to end through a real platform (§16).

Every page is fetched with a seeded catalog and must answer 200 with no
traceback; login, forced password change and CSRF are exercised; the table
contract is checked twice — in the rendered HTML (every <table> carries the
macro's marker) and in the template sources (only the macro file contains a
table element).

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import datetime as dt
import os
import re
import sys
import tempfile
from pathlib import Path

import pytest

TEMPLATES = Path(__file__).resolve().parent.parent / "maya" / "web" / "templates"
CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')
ADMIN_PW = "Admin-pass-123"


def _csrf(client, path: str = "/") -> str:
    return CSRF_RE.search(client.get(path).text).group(1)


@pytest.fixture(scope="module")
def env():
    """A platform on a fresh storage root, the app, and a seeded catalog."""
    old_argv, old_home = sys.argv, os.environ.get("MAYA_HOME")
    sys.argv = ["pytest"]
    os.environ["MAYA_HOME"] = tempfile.mkdtemp(prefix="maya-web-")
    from maya.server import build_app
    from starlette.testclient import TestClient
    from tests.conftest import build_platform

    platform = build_platform()             # PostgreSQL too when MAYA_TEST_PG_URL is set
    app = build_app(platform)
    ids = _seed(platform)
    client = TestClient(app)
    yield platform, app, client, ids
    platform.shutdown()
    sys.argv = old_argv
    if old_home is None:
        os.environ.pop("MAYA_HOME", None)
    else:
        os.environ["MAYA_HOME"] = old_home


def _principal(platform, username):
    with platform.uow() as uow:
        user = uow.repo("users").find_one(username=username)
        return platform.auth.build_principal(uow, user["id"])


def _seed(p) -> dict:
    """A small but complete estate: feature → pin → set → model → warrants."""
    admin = _principal(p, "admin")
    p.access.create_user(admin, username="mick", password="Manager-pass-1",
                         roles=["feature_manager", "model_manager", "model_developer"])
    mick = _principal(p, "mick")
    p.access.create_namespace(admin, name="eq")
    d = {"index": ["date", "symbol"], "index_types": {"date": "date", "symbol": "string"},
         "schema": [{"name": "close", "type": "float64"}, {"name": "vol", "type": "float64"}],
         "source": {"type": "csv", "knowledge_time_column": "kt"},
         "resolution": {"grid": "as_is", "rules": {"close": "forward_fill(limit=3)"}},
         "quality": [{"check": "not_null", "attr": "close"}]}
    p.features.create(admin, namespace="eq", name="px", definition=d, description="closes")
    rows = ["date,symbol,close,vol,kt"]
    for i in range(1, 21):
        day = dt.date(2026, 3, 1) + dt.timedelta(days=i)
        for s, base in (("A", 10.0), ("B", 20.0)):
            rows.append(f"{day},{s},{base + i},{1000 + i},{day}T20:00:00Z")
    p.features.ingest(admin, "eq/px", ("\n".join(rows) + "\n").encode(), fmt="csv")
    p.features.transition(admin, "eq/px", 1, "submit")
    p.features.transition(mick, "eq/px", 1, "approve")
    p.features.pin(mick, "eq/px", version_no=1, pin_name="eom", as_of=dt.date(2026, 3, 21))
    p.jobs.drain()
    fs = {"index": ["date", "symbol"], "grid": "as_is", "alignment": {"mode": "inner"},
          "filters": {}, "global_policy": {"rules": {}}, "group_policies": [],
          "members": [{"attr": "S", "ref": "maya://feature/eq/px@v1", "source_attr": "close"},
                      {"attr": "V", "ref": "maya://feature/eq/px@v1", "source_attr": "vol"}]}
    p.featuresets.create(admin, namespace="eq", name="panel", definition=fs)
    p.featuresets.transition(admin, "eq/panel", 1, "submit")
    p.featuresets.transition(mick, "eq/panel", 1, "approve")
    p.featuresets.pin(mick, "eq/panel", version_no=1, pin_name="q1", as_of=dt.date(2026, 3, 21),
                      cascade=True)
    p.jobs.drain()
    p.models.create(admin, namespace="eq", name="lin", formula="y = a*S + b",
                    roles={"a": "parameter", "b": "parameter"})
    ids = {"fs_pin": "maya://featureset/eq/panel#q1/2026-03-21"}
    from maya.formula.specdoc import REQUIRED_SECTIONS
    spec = "\\documentclass{article}\n\\begin{document}\n" + "".join(
        f"\\section{{{name}}}\nText for {name}. $y = a S + b$\n\n" for name in REQUIRED_SECTIONS
    ) + "\\end{document}\n"
    p.models.update_draft(admin, "eq/lin", spec_latex=spec)
    try:
        p.models.transition(admin, "eq/lin", 1, "submit")
        p.models.transition(mick, "eq/lin", 1, "approve")
        w = p.warrants.create(mick, namespace="eq", name="tw", model="maya://model/eq/lin@v1",
                              featureset=ids["fs_pin"], spec={"target": "V"})
        ids["tw"] = w["id"]
        ps = p.warrants.upload_parameters(mick, w["id"], values={"a": 0.5, "b": 1.0})
        ids["ps"] = ps["id"]
        ew = p.execution.create(mick, namespace="eq", name="ew", training_warrant_id=w["id"],
                                parameter_set_id=ps["id"])
        ids["ew"] = ew["id"]
    except Exception as exc:  # noqa: BLE001 - pages still render without warrants
        ids["seed_error"] = repr(exc)
    return ids


def _login(client, username="admin", password="maya-dev-admin"):
    return client.post("/login", data={"username": username, "password": password,
                                       "csrf_token": _csrf(client, "/login")},
                       follow_redirects=False)


def test_login_rejects_bad_password(env):
    _, _, client, _ = env
    r = client.post("/login", data={"username": "admin", "password": "wrong",
                                    "csrf_token": _csrf(client, "/login")})
    assert r.status_code == 401
    assert "Invalid username or password" in r.text


def test_login_forces_password_change_then_dashboard(env):
    _, _, client, _ = env
    r = _login(client)
    assert r.status_code == 303 and r.headers["location"] == "/account/password"
    assert client.get("/catalog/features", follow_redirects=False).headers["location"] \
        == "/account/password"
    r = client.post("/account/password", data={
        "old_password": "maya-dev-admin", "new_password": ADMIN_PW, "confirm_password": ADMIN_PW,
        "csrf_token": _csrf(client, "/account/password")}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/"
    home = client.get("/")
    assert home.status_code == 200 and "Recently changed features" in home.text


def test_csrf_is_required(env):
    _, _, client, _ = env
    r = client.post("/admin/namespaces", data={"name": "nocsrf"}, follow_redirects=False)
    assert r.status_code == 403
    r = client.post("/admin/namespaces", data={"name": "nocsrf", "csrf_token": "forged"},
                    follow_redirects=False)
    assert r.status_code == 403


def test_seed_completed(env):
    _, _, _, ids = env
    assert "seed_error" not in ids, ids.get("seed_error")


def _pages(ids) -> list[str]:
    pages = [
        "/", "/search?q=px", "/inbox", "/about", "/help",
        "/lineage?root=maya://feature/eq/px@v1", "/lineage",
        "/catalog/features", "/catalog/features/eq/px",
        "/catalog/features/eq/px?tab=data&ref=maya://feature/eq/px%23eom/2026-03-21",
        "/catalog/features/eq/px/compare?v1=1&v2=1",
        "/catalog/featuresets", "/catalog/featuresets/eq/panel",
        "/catalog/featuresets/eq/panel?tab=data&ref=maya://featureset/eq/panel%23q1/2026-03-21",
        "/workbench", "/workbench/features/new", "/workbench/features/eq/px/edit",
        "/workbench/features/eq/px/ingest", "/workbench/features/eq/px/preview",
        "/workbench/upload", "/workbench/quick", "/workbench/featuresets/new",
        "/workbench/featuresets/eq/panel/edit", "/workbench/featuresets/eq/panel/preview",
        "/models", "/models/new", "/models/eq/lin", "/models/eq/lin/diff?v1=1&v2=1",
        "/warrants", "/warrants/training/new", "/warrants/execution/new", "/warrants/verify",
        "/workflow", "/workflow/policies", "/workflow/campaigns", "/workflow/aging",
        "/workflow/break-glass",
        "/admin/health", "/admin/users", "/admin/namespaces", "/admin/grants",
        "/admin/grants?kind=feature&ref=eq/px", "/admin/jobs", "/admin/audit", "/admin/config",
        "/admin/storage", "/admin/custody", "/admin/custody?verify=1", "/account/keys",
        "/account/password",
    ]
    if "tw" in ids:
        pages += [f"/warrants/training/{ids['tw']}", f"/warrants/execution/{ids['ew']}",
                  f"/workflow/review/training_warrant/{ids['tw']}"]
    return pages


def test_every_page_renders(env):
    platform, _, client, ids = env
    policies = platform.workflow_svc.policies()
    extra = [f"/workflow/policies/{policies[0]['id']}"]
    failures = []
    for path in _pages(ids) + extra:
        r = client.get(path)
        if r.status_code != 200 or "Traceback" in r.text or "<title>" not in r.text:
            failures.append((path, r.status_code, r.text[:300]))
            continue
        if r.url.path != path.split("?")[0]:
            failures.append((path, "redirected", str(r.url)))
            continue
        if "error.html" in r.text or "<h1>NotFound" in r.text or "<h1>ValidationFailed" in r.text:
            failures.append((path, "error page", r.text[:300]))
        tables = len(re.findall(r"<table\b", r.text))
        marked = len(re.findall(r'<table class="maya-table"', r.text))
        if tables != marked:
            failures.append((path, "unmarked table", tables, marked))
    assert not failures, failures


def test_pinned_feature_data_is_shown(env):
    _, _, client, _ = env
    r = client.get("/catalog/features/eq/px?tab=data&ref=maya://feature/eq/px%23eom/2026-03-21")
    assert r.status_code == 200
    assert "40 row(s) resolved" in r.text


def test_download_returns_file(env):
    _, _, client, _ = env
    r = client.get("/catalog/download?ref=maya://feature/eq/px@v1&format=csv")
    assert r.status_code == 200
    assert "attachment" in r.headers["content-disposition"]
    assert b"close" in r.content
    assert "x-maya-manifest" in r.headers


def test_forms_post_through_the_sdk(env):
    _, _, client, _ = env
    tok = _csrf(client, "/admin/namespaces")
    r = client.post("/admin/namespaces", data={"name": "credit.pd", "preset": "regulated",
                                               "csrf_token": tok})
    assert r.status_code == 200 and "credit.pd" in r.text
    r = client.post("/catalog/features/eq/px/transition",
                    data={"version_no": "1", "transition": "approve", "csrf_token": tok})
    assert r.status_code == 200  # refused as a flash, not a traceback
    assert "Cannot approve" in r.text or "NotApproved" in r.text


def test_policy_validation_endpoint(env):
    platform, _, client, _ = env
    pol = platform.workflow_svc.policies()[0]
    tok = _csrf(client, "/workflow/policies")
    r = client.post("/workflow/policies/validate", headers={"X-CSRF-Token": tok},
                    json={"object_type": pol["object_type"],
                          "policy": {"states": ["draft", "orphan"], "transitions": {}}})
    assert r.status_code == 200
    body = r.json()
    assert any("unreachable" in e for e in body["errors"])


def test_job_progress_json(env):
    platform, _, client, _ = env
    job = platform.ops.jobs(_principal(platform, "mick"))[0]
    r = client.get(f"/ui/jobs/{job['id']}")
    assert r.status_code == 200 and r.json()["state"] == "succeeded"


def test_static_vendor_assets_served(env):
    _, _, client, _ = env
    for path in ("/static/vendor/bootstrap/css/bootstrap.min.css",
                 "/static/vendor/jquery/jquery.min.js", "/static/vendor/katex/katex.min.js",
                 "/static/vendor/cytoscape/cytoscape.min.js",
                 "/static/vendor/codemirror/codemirror.js", "/static/css/tokens.css",
                 "/static/js/table.js"):
        assert client.get(path).status_code == 200, path


def test_logout(env):
    _, _, client, _ = env
    r = client.post("/logout", data={"csrf_token": _csrf(client)}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/login"
    assert client.get("/", follow_redirects=False).status_code == 303


def test_only_the_macro_emits_tables():
    """The table contract (§16.7): no <table> in any template but the macro."""
    offenders = []
    for path in TEMPLATES.rglob("*.html"):
        if path.relative_to(TEMPLATES).as_posix() == "_macros/table.html":
            continue
        if re.search(r"<table\b", path.read_text(encoding="utf-8"), re.IGNORECASE):
            offenders.append(path.relative_to(TEMPLATES).as_posix())
    assert not offenders, offenders


def test_web_imports_only_the_sdk():
    """The client boundary (§13): maya.web imports nothing deeper than maya.sdk."""
    allowed = ("maya.sdk", "maya.core.version", "maya.core.errors", "maya.web")
    web = TEMPLATES.parent
    bad = []
    for path in web.rglob("*.py"):
        for m in re.finditer(r"^\s*(?:from|import)\s+(maya[\w.]*)", path.read_text(), re.M):
            if not m.group(1).startswith(allowed):
                bad.append((path.name, m.group(1)))
    assert not bad, bad


def _post_ok(client, path, data, *, files=None, csrf_from="/"):
    """POST a form and require that no error flash comes back."""
    data = {**data, "csrf_token": _csrf(client, csrf_from)}
    r = client.post(path, data=data, files=files)
    assert r.status_code == 200, (path, r.status_code, r.text[:500])
    errors = re.findall(r'alert-danger[^>]*>([^<]+)', r.text)
    assert not errors, (path, errors)
    return r


def test_forms_drive_the_whole_journey(env):
    platform, _, client, ids = env
    _login(client, password=ADMIN_PW)
    csv = b"date,symbol,px\n2026-01-02,A,1.5\n2026-01-05,A,1.6\n2026-01-06,B,2.0\n"
    r = _post_ok(client, "/workbench/quick", {"name": "quickpx", "fmt": "csv"},
                 files={"file": ("q.csv", csv, "text/csv")})
    assert "ungoverned" in r.text
    r = _post_ok(client, "/workbench/features/new", {
        "namespace": "eq", "name": "designed", "mode": "source", "index_name": ["date", "symbol"],
        "index_type": ["date", "string"], "attr_name": ["px"], "attr_type": ["float64"],
        "attr_unit": ["USD"], "attr_tag": [""], "attr_rule": ["forward_fill(limit=2)"],
        "source_type": "csv", "grid": "NYSE", "transform": "[]",
        "quality": '[{"check": "not_null", "attr": "px"}]'})
    assert "Feature created as draft v1" in r.text
    _post_ok(client, "/workbench/features/eq/designed/ingest", {"fmt": "csv", "note": "first"},
             files={"file": ("d.csv", csv, "text/csv")})
    r = client.get("/workbench/features/eq/designed/preview")
    assert r.status_code == 200 and "Fill report" in r.text
    r = _post_ok(client, "/workbench/upload", {"fmt": "csv"},
                 files={"file": ("wiz-data.csv", csv, "text/csv")})
    key = re.search(r'name="key" value="([^"]+)"', r.text).group(1)
    _post_ok(client, "/workbench/upload/confirm", {
        "key": key, "namespace": "eq", "name": "wizard", "mode": "source", "source_type": "csv",
        "index_name": ["date", "symbol"], "index_type": ["date", "string"],
        "attr_name": ["px"], "attr_type": ["float64"], "attr_unit": [""], "attr_tag": [""],
        "attr_rule": [""], "grid": "as_is"})
    r = _post_ok(client, "/models/new", {"namespace": "eq", "name": "bs", "kind": "formula",
                                         "authoring": "formula", "formula": "y = k*S",
                                         "roles": "k: parameter"})
    assert "data-latex=" in r.text
    _post_ok(client, "/models/eq/bs/spec", {"spec_latex": "\\section{Purpose}\nx"})
    r = _post_ok(client, "/models/eq/bs/render/1", {})
    assert "DRAFT RENDER" in r.text or "true LaTeX build" in r.text
    assert client.get("/models/eq/bs/spec/1.pdf").content.startswith(b"%PDF")
    r = _post_ok(client, "/account/keys", {"name": "ci", "days": "30"}, csrf_from="/account/keys")
    assert "maya_dev_" in r.text
    _post_ok(client, "/admin/grants", {"kind": "feature", "ref": "eq/px", "principal_type": "role",
                                       "principal_id": "model_owner", "level": "read",
                                       "days": "30"})
    if "ew" in ids:
        mick = _principal(platform, "mick")
        platform.warrants.transition(mick, ids["tw"], "submit")
        r = _post_ok(client, f"/warrants/training/{ids['tw']}/score",
                     {"parameter_set_id": ids["ps"]})
        assert "Blind score, attempt 1" in r.text
        r = client.get(f"/warrants/training/{ids['tw']}/data")
        assert r.status_code == 200 and r.content[:4] == b"PAR1"


def test_policy_editor_saves_a_draft(env):
    platform, _, client, _ = env
    pol = next(p for p in platform.workflow_svc.policies() if p["object_type"] == "feature_version")
    tok = _csrf(client, f"/workflow/policies/{pol['id']}")
    r = client.post("/workflow/policies/save", headers={"X-CSRF-Token": tok},
                    json={"object_type": pol["object_type"], "policy": pol["policy"],
                          "scope": "*", "note": "round trip from the editor"})
    assert r.status_code == 200, r.text
    new_id = r.json()["id"]
    page = client.get(f"/workflow/policies/{new_id}")
    assert page.status_code == 200 and "Activate (second administrator)" in page.text


def test_help_catalog_and_topic_templates_agree():
    """Every declared topic has a page, and every page is declared (one source of truth)."""
    from maya.web.help_catalog import all_topics
    declared = {t["slug"] for t in all_topics()}
    on_disk = {p.stem for p in (TEMPLATES / "help" / "topics").glob("*.html")}
    assert declared == on_disk, (sorted(declared - on_disk), sorted(on_disk - declared))
    assert len(declared) == len(all_topics()), "a slug is declared twice"


def test_help_and_about_render_signed_in_and_anonymously(env):
    from starlette.testclient import TestClient
    from maya.web.help_catalog import all_topics
    _, app, client, _ = env
    anon = TestClient(app)
    paths = ["/help", "/about"] + [f"/help/{t['slug']}" for t in all_topics()]
    for c, who in ((client, "signed in"), (anon, "anonymous")):
        for path in paths:
            r = c.get(path, follow_redirects=False)
            assert r.status_code == 200, (who, path, r.status_code, r.text[:300])
            assert "maya-nav" in r.text and "Traceback" not in r.text, (who, path)
    assert "Sign in" in anon.get("/help").text
    r = anon.get("/help/no-such-topic", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/help"
