"""
``maya.testing`` — a ready, in-process MAYA for your own tests.

Your code talks to MAYA through ``maya.sdk.Client``. To test it you need a MAYA
that is real (every layer runs: API, permissions, workflow, lake, signer) but
throwaway (a temporary directory, SQLite, no server, no network). This package
gives you one in about two seconds::

    import datetime as dt
    from maya.testing import Maya, market

    with Maya.start() as maya:                     # namespace "test", seeded users
        dana = maya.client("dana")                 # feature designer, logged in
        dana.features.list(namespace="test")       # the ordinary SDK

        data = market.generate(seed=7)             # the shared synthetic dataset
        prices = maya.approved_feature("prices", data.prices_csv(), market.PRICES_DEF)
        funds = maya.approved_feature("fundamentals", data.fundamentals_csv(),
                                      market.FUNDAMENTALS_DEF)
        # pin as known just before the first restatement: a restated value is, by
        # design, known after its event date, and the leakage certificate says so
        known = data.events["restatements"][0]["restated_kt"] - dt.timedelta(seconds=1)
        pin = maya.approved_featureset(
            "panel", {"close": prices, "eps": funds, "revenue": funds},
            alignment={"mode": "asof", "tolerance_days": 120},
            pin=("pit", known.date()), as_of_known=known)
        model = maya.approved_model("eps_linear", "eps_hat = a*sales + b",
                                    {"a": "parameter", "b": "parameter"})
        warrant = maya.training_warrant("fit", model, pin,
                                        {"target": "eps", "bindings": {"sales": "revenue"}})
        assert warrant["leakage_certificate"]["status"] == "certified"

        your_pipeline(maya.client("devi"))         # the code under test, on the SDK
    # closed: platform stopped, temporary directory deleted

With pytest, load the plugin once (in ``conftest.py``)::

    pytest_plugins = ["maya.testing.pytest_plugin"]

    def test_my_pipeline(maya_test):               # one Maya per test module
        client = maya_test.client("dana")
        ...

    def test_with_settings(maya_factory):          # a fresh Maya, your settings
        maya = maya_factory(settings={"workflow.allow_self_approval": "true"})

What you get
------------
``Maya.start(users=DEFAULT_USERS, namespace="test", preset="standard",
settings=None, config=None, keep=False)`` builds and seeds the platform:

* users, one per built-in role, password ``PASSWORD``: ``dana`` feature_designer,
  ``mick`` feature_manager, ``mona`` model_designer, ``devi`` model_developer,
  ``mgr`` model_manager, ``owen`` model_owner, ``tess`` techops; plus the bootstrap
  ``admin`` (``ADMIN_PASSWORD``);
* ``client(username)`` — an in-process ``maya.sdk.Client`` logged in as that user,
  cached per user; refusals raise the SDK's typed errors (``PermissionDenied``...);
* ``drain()`` — runs queued jobs inline (job workers are off; pins are jobs);
* ``platform`` — the service container, for what the SDK does not reach;
* ``close()`` — idempotent; also on leaving the ``with`` block.

The helpers go through the SDK, as the named users, exactly as your code would:
``approved_feature`` (create → ingest → submit → approve),
``approved_featureset`` (create → submit → approve → optional cascade pin, run
by ``drain()``), ``approved_model`` (create → complete specification document →
submit → approve) and ``training_warrant`` (draw one on a feature set or pin).
Only ``drain()`` and ``platform`` reach past the SDK.

Settings are passed to MAYA's configurator as ``--key=value`` flags while the
platform builds; ``sys.argv`` is restored straight after and ``os.environ`` is never
changed. Defaults: ``app.environment=dev``, ``db.dialect=sqlite``, storage and the
database inside the temporary directory. For PostgreSQL pass ``settings`` naming
``db.dialect`` and an empty ``db.postgresql.*`` database; MAYA creates the schema.

``maya.testing.market`` is the synthetic market dataset of §23: seeded, calendar
aware, with gaps, a split, restatements, a volatility surface and a messy CSV.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

from maya.testing.kit import (
    ADMIN,
    ADMIN_PASSWORD,
    DEFAULT_USERS,
    PASSWORD,
    Maya,
    complete_spec,
    infer_definition,
    load_test_settings,
)

__all__ = [
    "ADMIN",
    "ADMIN_PASSWORD",
    "DEFAULT_USERS",
    "PASSWORD",
    "Maya",
    "complete_spec",
    "infer_definition",
    "load_test_settings",
]
