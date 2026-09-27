"""
The throwaway MAYA behind ``maya.testing``: one platform, one SDK client per user.

``Maya.start()`` builds a complete platform — database, blob store, lake,
signer, every service — under a fresh temporary directory, seeds one user per
built-in role and a namespace, and hands out in-process SDK clients logged in
as those users. ``close()`` shuts it down and deletes the directory.

Configuration is passed to MAYA's configurator as ``--key=value`` flags (the
highest-precedence source). ``sys.argv`` is swapped only while the settings
load and restored at once; the environment is never touched. The storage root
and the SQLite file are pinned inside the temporary directory by flags, so a
``MAYA_HOME`` or ``data/`` of a developer's own is never read or written.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import datetime as dt
import io
import shutil
import sys
import tempfile
import threading
from pathlib import Path
from typing import Any, Mapping

from maya.core.errors import MayaError, NotAuthenticated, ValidationFailed
from maya.sdk import Client

ADMIN = "admin"
ADMIN_PASSWORD = "maya-dev-admin"  # the bootstrap admin's dev password
PASSWORD = "Maya-testing-pass-1"  # every seeded user's password
DEFAULT_USERS: dict[str, list[str]] = {
    "dana": ["feature_designer"],
    "mick": ["feature_manager"],
    "mona": ["model_designer"],
    "devi": ["model_developer"],
    "mgr": ["model_manager"],
    "owen": ["model_owner"],
    "tess": ["techops"],
}
_BUILD_LOCK = threading.Lock()  # sys.argv is process-wide while settings load


def default_config() -> Path:
    """``config/application.yaml`` of the checkout this package was imported from."""
    return Path(__file__).resolve().parents[2] / "config" / "application.yaml"


def complete_spec(name: str) -> str:
    """A LaTeX specification document with every required section filled (§8.3).

    A model version cannot be submitted until its document is complete; this is
    the smallest document that passes, for tests that are not about the document."""
    from maya.formula.specdoc import REQUIRED_SECTIONS

    body = "\n".join(
        f"\\section{{{s}}}\n{s} for {name}: stated in full.\n" for s in REQUIRED_SECTIONS
    )
    return f"\\documentclass{{article}}\n\\begin{{document}}\n{body}\n\\end{{document}}\n"


def load_test_settings(
    home: Path, overrides: Mapping[str, Any] | None = None, config: Path | None = None
) -> Any:
    """MAYA settings rooted at ``home``: dev, SQLite, pinned paths, then ``overrides``."""
    from maya.config import load_settings

    flags = {
        "app.environment": "dev",
        "db.dialect": "sqlite",
        "storage.root": str(home),
        "lake.root": str(home / "lake"),
        "db.sqlite.path": str(home / "maya.db"),
        "logging.file": str(home / "maya.log"),
        **{k: str(v) for k, v in (overrides or {}).items()},
    }
    with _BUILD_LOCK:
        saved = sys.argv
        sys.argv = ["maya.testing"] + [f"--{k}={v}" for k, v in flags.items()]
        try:
            return load_settings(config or default_config(), fresh=True)
        finally:
            sys.argv = saved


def _csv(data: Any) -> bytes:
    """CSV bytes from bytes, text or a pandas DataFrame (written without its index)."""
    if isinstance(data, bytes):
        return data
    if isinstance(data, str):
        return data.encode()
    buf = io.StringIO()
    data.to_csv(buf, index=False, lineterminator="\n")
    return buf.getvalue().encode()


def infer_definition(data: Any) -> dict[str, Any]:
    """A plain feature definition for a CSV: good enough for a test, never a decision.

    Index: every column that parses as ISO dates, then every text column. A ``kt``
    column becomes the knowledge-time column. Other columns: int64, float64,
    date or string, as the values allow. No fill rules, no quality checks."""
    import pandas as pd

    frame = pd.read_csv(io.BytesIO(_csv(data)))
    index, types, schema = [], {}, []
    for col in frame.columns:
        s = frame[col]
        if col == "kt":
            continue
        if pd.api.types.is_integer_dtype(s):
            kind = "int64"
        elif pd.api.types.is_numeric_dtype(s):
            kind = "float64"
        else:
            parsed = pd.to_datetime(s, errors="coerce", format="ISO8601")
            kind = "date" if parsed.notna().all() else "string"
        if kind in ("date", "string") and s.notna().all():
            index.append(col)
            types[col] = kind
        else:
            schema.append({"name": col, "type": kind})
    index.sort(key=lambda c: types[c] != "date")
    source = {"type": "csv", **({"knowledge_time_column": "kt"} if "kt" in frame else {})}
    return {
        "index": index,
        "index_types": types,
        "schema": schema,
        "source": source,
        "resolution": {"grid": "as_is", "rules": {}},
        "transform": [],
        "quality": [],
    }


class Maya:
    """A running, throwaway MAYA with seeded users. Use as a context manager.

    ``platform`` is the service container for power users; everything else goes
    through ``client(username)``, the same SDK your code uses in production."""

    def __init__(
        self,
        platform: Any,
        home: Path,
        namespace: str,
        users: Mapping[str, list[str]],
        keep: bool = False,
    ) -> None:
        self.platform = platform
        self.home = home
        self.namespace = namespace
        self.users = dict(users)
        self.keep = keep
        self._app: Any = None
        self._clients: dict[str, Client] = {}
        self.closed = False
        self._opened = dt.datetime.now(dt.timezone.utc)

    # -- lifecycle --------------------------------------------------------------------
    @classmethod
    def start(
        cls,
        *,
        users: Mapping[str, list[str]] | None = None,
        namespace: str = "test",
        preset: str = "standard",
        settings: Mapping[str, Any] | None = None,
        config: str | Path | None = None,
        keep: bool = False,
    ) -> "Maya":
        """Build a platform in a new temporary directory and seed it.

        ``users`` maps username → roles (default: one per built-in role, see
        ``DEFAULT_USERS``; each gets ``PASSWORD``). ``settings`` are extra
        configuration keys, e.g. ``{"workflow.allow_self_approval": "true"}``.
        ``keep=True`` leaves the directory on disk after ``close()``. Job workers do
        not run: queued jobs (pins, for one) run when you call ``drain()``."""
        from maya.services.platform import Platform

        home = Path(tempfile.mkdtemp(prefix="maya-testing-"))
        try:
            s = load_test_settings(home, settings, Path(config) if config else None)
            platform = Platform.build(s, start_workers=False)
        except BaseException:
            shutil.rmtree(home, ignore_errors=True)
            raise
        maya = cls(platform, home, namespace, DEFAULT_USERS if users is None else users, keep)
        try:
            maya._seed(preset)
        except BaseException:
            maya.close()
            raise
        return maya

    def _seed(self, preset: str) -> None:
        admin = self.client(ADMIN)
        for username, roles in self.users.items():
            admin.admin.create_user(username, password=PASSWORD, roles=list(roles))
        if self.namespace:
            admin.namespaces.create(self.namespace, preset=preset)

    def close(self) -> None:
        """Log out every client, stop the platform and delete the directory. Idempotent."""
        if self.closed:
            return
        self.closed = True
        for c in self._clients.values():
            c.close()
        self._clients.clear()
        try:
            self.platform.shutdown()
        finally:
            if not self.keep:
                shutil.rmtree(self.home, ignore_errors=True)

    def __enter__(self) -> "Maya":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    # -- clients ----------------------------------------------------------------------
    @property
    def app(self) -> Any:
        """The ASGI application (the public API) over this platform."""
        if self._app is None:
            from maya.api.app import create_api

            self._app = create_api(self.platform)
        return self._app

    def client(self, username: str = ADMIN, password: str | None = None) -> Client:
        """An in-process SDK ``Client`` logged in as ``username`` (cached per user)."""
        if self.closed:
            raise MayaError("This Maya is closed")
        if username not in self._clients:
            pw = password or (ADMIN_PASSWORD if username == ADMIN else PASSWORD)
            with Client(app=self.app) as anonymous:
                try:
                    token = anonymous.auth.login(username, pw)["token"]
                except NotAuthenticated:
                    if username != ADMIN or password is not None:
                        raise
                    token = self._operator_session()
            self._clients[username] = Client(app=self.app, token=token)
        return self._clients[username]

    def _operator_session(self) -> str:
        """An administrator session opened in-process, when the bootstrap password is gone.

        The quick start tells a new user to change the administrator's published password
        at first sign-in, which is right -- and which used to break every case study, since
        they sign in as ``admin`` with that password. This kit runs inside the platform's own
        process, with the access an operator at the server's shell already has, so it opens
        the session directly rather than asking for a password it was never given. It is
        recorded in the audit chain as exactly that; the password itself is not touched."""
        with self.platform.uow("maya-testing") as uow:
            user = uow.repo("users").find_one(username=ADMIN)
            if user is None:
                raise NotAuthenticated("There is no 'admin' user in this estate")
            token = self.platform.auth._open_session(
                uow, user, None, "maya.testing", "api", auth_method="operator"
            )
            uow.audit(
                "auth.operator_session",
                object_type="user",
                object_ref=ADMIN,
                detail={"by": "maya.testing", "why": "the bootstrap password was changed"},
                principal_type="system",
            )
            return token

    def drain(self, wait_seconds: float = 600) -> None:
        """Run every queued job to completion, inline (pins, renders, scans).

        Another process can share this database -- a web server started on the same MAYA
        home, whose job workers claim a queued job first. Draining inline then finds nothing
        to run and returns while that job is still running elsewhere, and the caller reads a
        pin that does not exist yet. So this also waits for jobs claimed since this kit
        opened to finish, whoever runs them; one left running by a process that died
        earlier is not waited for."""
        import time

        deadline = time.monotonic() + wait_seconds
        while True:
            self.platform.jobs.drain()
            with self.platform.uow() as uow:
                jobs = uow.repo("jobs")
                busy = jobs.list(state="queued") + [
                    j
                    for j in jobs.list(state="running")
                    if j.get("started_at") is not None and _aware(j["started_at"]) >= self._opened
                ]
            if not busy:
                return
            if time.monotonic() > deadline:
                names = ", ".join(f"{j['job_type']} ({j['state']})" for j in busy[:5])
                raise MayaError(f"Jobs still unfinished after {wait_seconds:.0f}s: {names}")
            time.sleep(0.25)

    def ref(self, name: str) -> str:
        """``ns/name`` in this kit's namespace, unless ``name`` already names one."""
        return name if "/" in name else f"{self.namespace}/{name}"

    # -- helpers: approved objects, through the SDK -------------------------------------
    def approved_feature(
        self,
        name: str,
        data: Any = None,
        definition: dict[str, Any] | None = None,
        *,
        designer: str = "dana",
        manager: str = "mick",
        knowledge_time: str | dt.datetime | None = None,
    ) -> str:
        """Create, ingest, submit and approve a feature; returns ``ns/name``.

        ``data`` is CSV bytes/text or a DataFrame (sent as CSV). Without a
        ``definition`` one is inferred by ``infer_definition``. All through the SDK."""
        ref = self.ref(name)
        ns, short = ref.split("/", 1)
        des = self.client(designer)
        body = _csv(data) if data is not None else None
        if definition is None:
            if body is None:
                raise ValidationFailed("approved_feature needs data or a definition")
            definition = infer_definition(body)
        des.features.create(ns, short, definition)
        version = 1
        if body is not None:
            kt = (
                knowledge_time.isoformat()
                if isinstance(knowledge_time, dt.datetime)
                else knowledge_time
            )
            des.features.ingest(ref, body, fmt="csv", filename=f"{short}.csv", knowledge_time=kt)
        des.features.transition(ref, version, "submit")
        self.client(manager).features.transition(ref, version, "approve")
        return ref

    def approved_featureset(
        self,
        name: str,
        members: Mapping[str, Any] | None = None,
        *,
        definition: dict[str, Any] | None = None,
        index: tuple[str, ...] = ("date", "symbol"),
        alignment: dict[str, Any] | None = None,
        pin: tuple[str, str | dt.date] | None = None,
        as_of_known: str | dt.datetime | None = None,
        developer: str = "devi",
        manager: str = "mick",
    ) -> str:
        """Create, submit and approve a feature set; optionally cascade-pin it.

        ``members`` maps attribute → ``"ns/feature"`` (same attribute name) or
        ``("ns/feature", "source_attr")``; each reference is taken at the feature's
        latest version. Or pass a whole ``definition``. With ``pin=(name, as_of)``
        the manager cascade-pins it (optionally ``as_of_known``), the job runs, and
        the pin reference ``maya://featureset/ns/name#pin/date`` is returned;
        otherwise ``maya://featureset/ns/name@vN``. All through the SDK."""
        ref = self.ref(name)
        ns, short = ref.split("/", 1)
        dev = self.client(developer)
        if definition is None:
            definition = {"index": list(index), "members": self._member_list(members or {})}
            if alignment:
                definition["alignment"] = alignment
        dev.featuresets.create(ns, short, definition)
        version = 1
        dev.featuresets.transition(ref, version, "submit")
        mgr = self.client(manager)
        mgr.featuresets.transition(ref, version, "approve")
        if pin is None:
            return f"maya://featureset/{ref}@v{version}"
        pin_name, as_of = pin[0], str(pin[1])
        known = as_of_known.isoformat() if isinstance(as_of_known, dt.datetime) else as_of_known
        out = mgr.featuresets.pin(ref, version, pin_name, as_of, cascade=True, as_of_known=known)
        self.drain()
        state = mgr.jobs.get(out["job"]["id"])
        if state["state"] != "succeeded":
            raise MayaError(
                f"Pinning {ref} {state['state']}: {state.get('error')}", job=state["id"]
            )
        return f"maya://featureset/{ref}#{pin_name}/{as_of}"

    def _member_list(self, members: Mapping[str, Any]) -> list[dict[str, Any]]:
        out, versions = [], {}
        for attr, spec in members.items():
            feature, source = (spec, attr) if isinstance(spec, str) else spec
            if "://" in feature or "@" in feature or "#" in feature:
                member_ref = feature
            else:
                fref = self.ref(feature)
                if fref not in versions:
                    got = self.client(ADMIN).features.get(fref)["versions"]
                    versions[fref] = max(
                        v["version_no"] for v in got if v["state"] in ("approved", "published")
                    )
                member_ref = f"maya://feature/{fref}@v{versions[fref]}"
            out.append({"attr": attr, "ref": member_ref, "source_attr": source})
        return out

    def approved_model(
        self,
        name: str,
        formula: str,
        roles: Mapping[str, str] | None = None,
        *,
        spec_latex: str | None = None,
        designer: str = "mona",
        manager: str = "mgr",
    ) -> str:
        """Create a formula model, fill a complete specification document, submit and
        approve it; returns ``ns/name@vN``. ``roles`` marks symbols, e.g.
        ``{"a": "parameter"}``; unmarked symbols are feature inputs. All through the SDK."""
        ref = self.ref(name)
        ns, short = ref.split("/", 1)
        des = self.client(designer)
        des.models.create(ns, short, formula=formula, roles=dict(roles or {}))
        version = 1
        des.models.update_draft(ref, spec_latex=spec_latex or complete_spec(short))
        des.models.transition(ref, version, "submit")
        self.client(manager).models.transition(ref, version, "approve")
        return f"{ref}@v{version}"

    def training_warrant(
        self,
        name: str,
        model: str,
        featureset: str,
        spec: dict[str, Any] | None = None,
        *,
        developer: str = "devi",
    ) -> dict[str, Any]:
        """Draw a training warrant (a draft) of ``model`` on ``featureset``; returns it
        with its contract report and leakage certificate. Through the SDK."""
        ref = self.ref(name)
        ns, short = ref.split("/", 1)
        return dict(
            self.client(developer).training.create(ns, short, model, featureset, spec=spec or {})
        )


def _aware(value: dt.datetime) -> dt.datetime:
    """A stored timestamp as UTC-aware; SQLite hands some back naive."""
    return value if value.tzinfo else value.replace(tzinfo=dt.timezone.utc)
