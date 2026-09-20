"""
``maya`` — the command line (§18.3). It wraps the SDK for scripting and CI:
human-readable output by default, ``--json`` for pipelines, and meaningful
exit codes (0 ok, 1 refused by MAYA, 2 usage, 3 network).

Remote by default: ``MAYA_URL`` and ``MAYA_API_KEY`` (or ``--profile``).
``--local`` starts an in-process platform from ``config/application.yaml``
instead — for a laptop or for the ``admin`` commands that rebuild a database,
which by nature run beside it rather than through it (§14.3).

One module per group: ``__main__`` builds the parser and holds the catalog,
model, warrant, job and export commands, ``admin`` the administrative ones,
``keys`` the credential ones (``maya key``, ``maya credential``), and ``common``
the plumbing all three share — the client, the printer and the exit codes.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
