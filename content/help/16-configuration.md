---
title: Configuration
slug: configuration
section: Reference
order: 160
icon: gear
summary: One YAML file, a git-ignored overlay for secrets, and the precedence order. Switching to PostgreSQL is a one-line change.
audience: Operators
---

# Configuration

Everything is in `config/application.yaml`. There is one file, it is tracked,
and secrets do not go in it.

## Precedence

```
command line  >  environment  >  config/application.local.yaml  >  config/application.yaml
```

The `.local.yaml` overlay is **git-ignored** and sets only the keys it names. That
is where a password, a signing key or a production database URL belongs. A
committed secret is a public secret.

```bash
python run_maya_web.py --server.port=8080 --database.url=postgresql://...
```

## Substitution

`${VAR}` and `${VAR:default}` resolve against other keys in the file, environment
variables, and command-line overrides:

```yaml
server:
  port: "${PORT:5006}"
database:
  url: "sqlite:///${data.sqlite.dir}/maya.db"
```

Values are read as strings and coerced on access, so `port: 5006` and
`port: "${PORT:5006}"` behave identically.

> **Careful with YAML booleans.** Bare `yes`, `no`, `on`, `off` are coerced to
> booleans by YAML itself. If you mean the string, quote it.

## Switching to PostgreSQL

```yaml
database:
  url: "postgresql://maya:...@db.internal:5432/maya"
```

That is the entire change. There are **no migrations**: the schema is two
hand-written files under `db/schema/`, applied idempotently with
`CREATE TABLE IF NOT EXISTS`. Only column types with the same meaning in both
dialects are used — `TEXT`, `INTEGER`, `REAL`/`DOUBLE PRECISION` — and timestamps
are epoch seconds, because SQLite has no date type and the two dialects disagree
about time zones.

## Storage layout

```yaml
data:
  dir: ./data
  sqlite: {dir: "${data.dir}/sqlite"}
  delta:
    dir: "${data.dir}/delta"
    features:   "${data.delta.dir}/features"
    snapshots:  "${data.delta.dir}/snapshots"
    retention_days: 400
```

Nothing under `data/` is committed. It holds the development database, the Delta
lake, and any artifacts.

## Warrant timing

```yaml
warrants:
  ttl_seconds:   {1: 60, 2: 300, 3: 3600, 4: 3600}
  grace_seconds: {1: 0,  2: 0,   3: 900,  4: 900}
  jitter_pct: 20
```

Keyed by risk tier. Tier 1 gets a 60-second life and **zero grace** — a Tier 1
model must never run on stale authorisation. Tier 3 and 4 get grace so a
transient control-plane outage does not stop the business.

`jitter_pct` spreads expiry across a band so a fleet issued warrants at deploy
time does not expire in lockstep and stampede the resolver.

## Content

```yaml
content:
  dir: ./content
```

Help and about pages are markdown files under this directory, rendered at
request time and cached on modification time. Edit a topic and the next request
shows it — no restart.

## Logging

```yaml
logging:
  level: INFO
```

One logger hierarchy, one format, installed at startup. Every module logs
through `core.log.get_logger(__name__)`, and **no exception anywhere is ignored
or swallowed** — a handler may recover, but it may not do so silently. A test
walks the AST of every source file to enforce that.
