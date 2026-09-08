"""
MAYA — the soak harness.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

A long run against a LIVE server, through the interfaces a bank would use.

The unit suite answers "does each part behave". This answers a different
question, and it is the one a soak exists for: **does the platform still tell
the truth after hours of use.** Those come apart in specific ways, and every
one of them has bitten this codebase already —

  * a control that reports success while doing nothing, which passes on the
    first call and every call after it;
  * a hash chain that verifies at the end of a test and not after ten thousand
    appends from four writers;
  * a sequence that skips, a counter that drifts, a lock quietly not taken;
  * a resource that grows — memory, file handles, a ring that was supposed to
    be bounded;
  * a refusal that stops refusing once some other state has moved on.

So the shape here is: drive real work through the HTTP API on a real uvicorn
process, and between batches assert the INVARIANTS — the things that must be
true at every instant regardless of what has happened. A scenario that passes
tells you a path works. An invariant that holds after six hours tells you the
platform is still the thing it claims to be.

Every check is recorded with its timestamp, its outcome, what was expected and
what came back, into a JSONL that `report.py` renders. Nothing is summarised
away: a soak whose log says "all good" is a soak nobody can audit.
"""
from __future__ import annotations

import http.cookiejar
import json
import os
import pathlib
import re
import signal
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

BASE = os.environ.get("MAYA_SOAK_URL", "http://127.0.0.1:5099")
API = BASE + "/api/v1"
ADMIN = ("admin", "maya-admin-dev")

#: The cap the run must not exceed, and the reason it is a cap rather than a
#: target: a soak that spends its budget in the first ten minutes has measured
#: throughput, not endurance. The pacing below spreads whatever budget it has
#: across the whole duration.
MAX_CHECKS = 3000


# ---------------------------------------------------------------- recording
class Journal:
    """Every check, in order, with enough to reconstruct it.

    Written as it goes rather than at the end. A six-hour run that dies at
    hour five must still leave five hours of evidence — and "the process died"
    is itself the most important thing such a log can record.
    """

    def __init__(self, path: pathlib.Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = self.path.open("w", encoding="utf-8")
        self.checks = 0
        self.failures = 0
        self.started = time.time()

    def record(self, **row) -> None:
        row["n"] = self.checks
        row["at"] = round(time.time() - self.started, 3)
        # Truncated HERE rather than at the point of reading a response: a
        # whole HTML page in every journal line makes a file nobody can open,
        # and truncating on the way IN made three checks search a fragment of
        # the page they were asked about.
        line = json.dumps(row, default=str)
        if len(line) > 4000:
            line = json.dumps({**{k: (v if len(json.dumps(v, default=str)) < 1500
                                     else json.dumps(v, default=str)[:1500] + "…")
                                 for k, v in row.items()}}, default=str)
        self.handle.write(line + "\n")
        self.handle.flush()

    def check(self, family: str, name: str, ok: bool, expected: Any,
              got: Any, note: str = "") -> bool:
        self.checks += 1
        if not ok:
            self.failures += 1
        self.record(kind="check", family=family, name=name,
                    ok=bool(ok), expected=expected, got=got, note=note)
        return bool(ok)

    def event(self, what: str, **detail) -> None:
        self.record(kind="event", what=what, detail=detail)

    def sample(self, **metrics) -> None:
        self.record(kind="sample", **metrics)

    def close(self) -> None:
        self.handle.close()


# ------------------------------------------------------------------- client
class Client:
    """Plain urllib against a real server. No test client, on purpose.

    A TestClient runs the app in-process and skips uvicorn, the middleware
    stack as it is actually assembled, the connection pool under concurrency,
    and every question about the process's own resource use. Those are most of
    what a soak is for.
    """

    def __init__(self, journal: Journal):
        self.journal = journal
        self.calls = 0
        self.server_errors: List[Dict[str, Any]] = []
        self.latencies: List[float] = []
        # One cookie jar per persona. A SCREEN is not an API call: the pages
        # resolve who you are from the session, so HTTP Basic gets you a
        # redirect to /login — which urllib follows, so the check then examines
        # the sign-in page and finds it 200 and empty of everything it was
        # looking for. Thirty-three screen assertions per cycle were passing
        # against the login page.
        self._sessions: Dict[str, Any] = {}
        self._lock = threading.Lock()

    def call(self, method: str, path: str, body: Any = None,
             auth=ADMIN, headers: Optional[Dict[str, str]] = None,
             timeout: float = 30.0):
        url = path if path.startswith("http") else API + path
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(url, data=data, method=method)
        request.add_header("content-type", "application/json")
        if auth:
            import base64
            token = base64.b64encode(
                f"{auth[0]}:{auth[1]}".encode()).decode()
            request.add_header("Authorization", "Basic " + token)
        for key, value in (headers or {}).items():
            request.add_header(key, value)
        began = time.time()
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                took = time.time() - began
                raw = response.read().decode("utf-8", "replace")
                status = response.status
        except urllib.error.HTTPError as exc:
            took = time.time() - began
            raw = exc.read().decode("utf-8", "replace")
            status = exc.code
        except Exception as exc:                     # connection refused, etc.
            took = time.time() - began
            self.calls += 1
            self.latencies.append(took)
            self.journal.event("transport_error", method=method, path=path,
                               error=f"{type(exc).__name__}: {exc}")
            return 0, {"error": "transport", "detail": str(exc)}
        self.calls += 1
        self.latencies.append(took)
        try:
            parsed = json.loads(raw) if raw else {}
        except ValueError:
            # HTML. Kept WHOLE: this was truncated to two thousand characters
            # to keep the journal small, and the journal is not where it goes —
            # so three checks that looked for a link partway down a page
            # reported "NOT LINKED" about a page that linked perfectly well.
            # Truncation belongs at the point of RECORDING, which is where it
            # is now.
            parsed = {"_raw": raw}
        if status >= 500:
            # Tracked separately and never as an ordinary outcome. MAYA's whole
            # argument is that a refusal is a considered answer with a code and
            # a remediation; a 500 is the absence of an answer.
            self.server_errors.append({"method": method, "path": path,
                                       "status": status, "body": parsed})
            self.journal.event("server_error", method=method, path=path,
                               status=status, body=parsed)
        return status, parsed

    def session_for(self, auth) -> Any:
        """A signed-in browser session for this persona, made once.

        Through the real sign-in form, with its CSRF token, because that is the
        door a person uses and a soak that skipped it would not be exercising
        it.
        """
        key = auth[0] if auth else "-"
        with self._lock:
            if key in self._sessions:
                return self._sessions[key]
        jar = http.cookiejar.CookieJar()
        opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(jar))
        try:
            page = opener.open(BASE + "/login", timeout=20).read().decode(
                "utf-8", "replace")
            form = {"username": auth[0], "password": auth[1], "next": "/dashboard"}
            if (token := re.search(r'name="csrf_token"\s+value="([^"]+)"', page)):
                form["csrf_token"] = token.group(1)
            opener.open(BASE + "/login",
                        urllib.parse.urlencode(form).encode(), timeout=20).read()
        except Exception as exc:
            self.journal.event("session_failed", who=key,
                               error=f"{type(exc).__name__}: {exc}")
            return None
        with self._lock:
            self._sessions[key] = opener
        return opener

    def page(self, path: str, auth, timeout: float = 30.0):
        """Fetch a SCREEN, as a signed-in browser. Returns (status, html)."""
        opener = self.session_for(auth)
        if opener is None:
            return 0, ""
        url = path if path.startswith("http") else BASE + path
        began = time.time()
        try:
            with opener.open(url, timeout=timeout) as response:
                body = response.read().decode("utf-8", "replace")
                status = response.status
        except urllib.error.HTTPError as exc:
            body, status = exc.read().decode("utf-8", "replace"), exc.code
        except Exception as exc:
            self.journal.event("transport_error", method="GET", path=path,
                               error=f"{type(exc).__name__}: {exc}")
            return 0, ""
        finally:
            self.calls += 1
            self.latencies.append(time.time() - began)
        if status >= 500:
            self.server_errors.append({"method": "GET", "path": path,
                                       "status": status, "body": body[:400]})
            self.journal.event("server_error", method="GET", path=path,
                               status=status, body=body[:400])
        return status, body

    @staticmethod
    def is_sign_in(html: str) -> bool:
        """Whether this is the sign-in form rather than the page asked for.

        urllib follows the redirect, so an unauthenticated screen request ends
        at 200 with a login form — which is how thirty-three screen assertions
        per cycle passed while examining the wrong page entirely. A screen
        check has to rule this out explicitly or it is asserting that /login
        renders.
        """
        return 'name="csrf_token"' in html and 'name="password"' in html

    def get(self, path, **kw):
        return self.call("GET", path, **kw)

    def post(self, path, body=None, **kw):
        return self.call("POST", path, body if body is not None else {}, **kw)

    def put(self, path, body=None, **kw):
        return self.call("PUT", path, body if body is not None else {}, **kw)


# ------------------------------------------------------------------- server
class Server:
    """The process under test, and the measurements only its owner can take."""

    def __init__(self, workdir: pathlib.Path, port: int, journal: Journal,
                 delta_backend: Optional[str] = None):
        self.workdir = workdir
        self.port = port
        self.journal = journal
        self.delta_backend = delta_backend
        self.process: Optional[subprocess.Popen] = None
        self.config = workdir / "application.yaml"
        self.restarts = 0

    def start(self) -> None:
        self.workdir.mkdir(parents=True, exist_ok=True)
        raw = (ROOT / "config" / "application.yaml").read_text()
        raw = raw.replace("sqlite:///${data.sqlite.dir}/maya.db",
                          f"sqlite:///{self.workdir}/maya.db")
        raw = raw.replace("${data.dir}", str(self.workdir))
        self.config.write_text(raw)
        log = (self.workdir / "server.log").open("a")
        environment = {**os.environ, "PYTHONPATH": str(ROOT)}
        if self.delta_backend:
            # The soak says which Delta implementation it ran on, and forces
            # it. A run whose result depends on what happened to be installed
            # is a run nobody can repeat.
            environment["MAYA_DELTA_BACKEND"] = self.delta_backend
        self.process = subprocess.Popen(
            [sys.executable, "-c",
             "import uvicorn;"
             "from run_maya_web import create_app, PropertiesConfigurator;"
             "PropertiesConfigurator.reset();"
             f"app = create_app(PropertiesConfigurator({str(self.config)!r},"
             " reload_interval=0));"
             f"uvicorn.run(app, host='127.0.0.1', port={self.port},"
             " log_level='warning')"],
            cwd=str(ROOT), stdout=log, stderr=subprocess.STDOUT,
            env=environment)
        self.journal.event("server_started", pid=self.process.pid,
                           port=self.port, workdir=str(self.workdir),
                           delta_backend=self.delta_backend or "whatever is installed")

    def wait_until_ready(self, seconds: float = 90.0) -> bool:
        deadline = time.time() + seconds
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(BASE + "/login", timeout=5):
                    return True
            except Exception:
                time.sleep(1.0)
        return False

    def alive(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def health(self) -> Dict[str, Any]:
        """RSS, file handles, threads and database size.

        A soak that does not measure these is a functional test that took six
        hours. A leak is invisible in a unit suite by construction: the process
        exits before it matters.
        """
        out: Dict[str, Any] = {}
        if not self.alive():
            return out
        pid = self.process.pid

        def measured(name, fn):
            try:
                out[name] = fn()
            except Exception as exc:            # a reading, not the run
                self.journal.event("measurement_failed", metric=name,
                                   error=f"{type(exc).__name__}: {exc}")

        def rss():
            for line in pathlib.Path(f"/proc/{pid}/status").read_text().splitlines():
                if line.startswith("VmRSS:"):
                    return int(line.split()[1])
            raise ValueError("VmRSS not in /proc/{pid}/status")

        def threads():
            for line in pathlib.Path(f"/proc/{pid}/status").read_text().splitlines():
                if line.startswith("Threads:"):
                    return int(line.split()[1])
            raise ValueError("Threads not in /proc/{pid}/status")

        measured("rss_kb", rss)
        measured("threads", threads)
        measured("fds", lambda: len(list(pathlib.Path(f"/proc/{pid}/fd").iterdir())))
        measured("db_bytes",
                 lambda: (self.workdir / "maya.db").stat().st_size
                 if (self.workdir / "maya.db").is_file() else 0)
        return out

    def stop(self) -> None:
        if self.process and self.process.poll() is None:
            self.process.send_signal(signal.SIGTERM)
            try:
                self.process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                self.process.kill()
        self.journal.event("server_stopped")
