# `maya_delta` backend fallback: native ↔ pure

For the administrator whose lake is running on a backend they did not expect, who needs to
pin one, or whose lake has refused a table by naming a Delta feature. `maya_delta` has two
interchangeable backends ([ADR-009](../adr/ADR-009-maya-delta-lakehouse-engine.md)):
`native` (delta-rs, through the `deltalake` wheel) and `pure` (MAYA's own implementation of a
declared subset of the Delta protocol). `lake.backend: auto` prefers native and falls back to
pure; both read and write the same tables, so switching moves no data.

## Symptoms

- The banner reads `maya_delta    pure  — fallback: <why>`, for instance
  `fallback: deltalake does not import (ModuleNotFoundError: …)` or
  `fallback: deltalake <version> failed the self-check (<error>)`.
- Startup refuses because the backend is pinned to native and native is unusable:

  ```text
  MayaDeltaError: lake backend pinned to 'native' but deltalake does not import (<error>)
  ```

- A pin, download or maintenance run fails naming a Delta feature:

  ```text
  Delta table requires unsupported protocol feature '<feature>': <detail>
  ```

  where `<feature>` is, for example, `deletionVectors`, `v2Checkpoint`, a column-mapping mode,
  `invariants`, `appendOnly` on an overwrite, or `readerVersion<n>` / `writerVersion<n>`.
- Lake operations are slower than they were.

## Diagnosis

**Trust the health page's `lake` section, not its seam list.** The `lake` section reports what
`maya_delta` actually selected and why. The `seams` list and the `degraded` list check only
whether `deltalake` imports, so when it imports but fails its self-check they still say
`native` while the lake runs on pure (a defect; see *What this does not reach*).

```bash
# What the lake is really running on, and why
curl -s "$MAYA_URL/api/v1/system/health" -H "Authorization: Bearer $MAYA_API_KEY" \
  | python -c "import json,sys; print(json.load(sys.stdin)['lake'])"
# {'backend': 'native', 'detail': 'deltalake imports and passed the self-check', 'root': '…/lake'}
curl -s "$MAYA_URL/readyz"          # "lake": "<backend>" — unauthenticated

# On the server: would native work here, and if not, why not?
python -c "import maya_delta; print(maya_delta.select_backend('native'))"
# LakeBackendInfo(name='native', detail='deltalake 1.6.3', reason='pinned by configuration')
# or: maya_delta.errors.MayaDeltaError: lake backend pinned to 'native' but <reason>

# For an UnsupportedFeature refusal: the table's protocol, read with the backend that refused
python -c "import sys; from maya_delta import DeltaLake; lake = DeltaLake('pure'); t = sys.argv[1]; print(lake.version(t), lake.protocol(t))" "$MAYA_HOME/lake/pins/<namespace>/<name>"
# 0 {'minReaderVersion': 1, 'minWriterVersion': 2, 'readerFeatures': None, 'writerFeatures': None}
```

Pinned data lives under `<storage.root>/lake/pins/<namespace>/<name>`; ingested data under
`<storage.root>/lake/raw/<namespace>/<name>/`. The health page (`/admin/health`) shows the same
`lake` section in the browser.

## Steps

**Native fell back and you want it back.** Reinstall the pinned wheel into MAYA's environment
(`pip install -r requirements.txt`), run the diagnosis command above until it answers
`name='native'`, and restart MAYA. If native passes the import but fails the self-check, the
self-check's error is in the banner and in `lake.detail`; a wheel built for another platform
or Python is the usual cause.

**Choose what a broken native should do.** With `lake.backend: auto` a broken wheel costs
speed and MAYA keeps serving. With `lake.backend: native`, a broken wheel refuses to start.
Pin `native` where you would rather be down than slow; leave `auto` where availability
matters more. Either way, set it in `config/application.local.yaml` or pass
`--lake.backend=<value>` to `run_maya_web.py`.

**Run on pure deliberately** — an air-gapped host without the wheel, a platform with no
build: set `lake.backend: pure` and restart. The banner then says
`maya_delta    pure  — pinned by configuration`, and the seam line shows `lake=pure*`.

**An `UnsupportedFeature` refusal.** The pure backend refuses rather than approximates. MAYA's
own writes, on either backend, do not use the features it lacks; a table that needs one was
written or upgraded by something else — another Delta tool pointed at the lake, or a newer
`deltalake` that turned a feature on.

1. Find what touched the table. Each commit in `<table>/_delta_log/<version>.json` starts with
   a `commitInfo` line; MAYA's native writes carry `"engineInfo":"delta-rs:py-<version>"`
   and its pure writes `"engineInfo":"maya_delta-pure"`.
   `grep -h '"protocol"\|engineInfo' <table>/_delta_log/*.json` shows which commit raised
   the protocol and what made it. (`lake.history(path)` gives versions, times and operations,
   but not the engine.)
2. If native is available, pin `lake.backend: native`, which reads the feature, and restart.
3. Stop the other tool writing to MAYA's lake. The lake is MAYA's; nothing else should
   commit to it. There is no MAYA command to take a table's protocol back down.

## Verification

- The banner and the health page's `lake` section name the backend you intended, with the
  reason you expect.
- `python -m maya.cli admin verify-integrity` exits 0. It re-reads every sealed pin through the
  backend now running and recomputes its content hash, which is the proof that the switch
  read the same bytes.

## What this does not reach

- **The seam report can contradict the lake.** `maya/core/backends.py` probes the `lake` seam by
  import alone; `maya_delta` also runs a self-check. When `deltalake` imports but fails the
  self-check, the lake runs on pure while the health page's `seams` and `degraded` lists, the
  banner's `Seams` line and every pin's recorded `provenance.backends.lake` say `native` — and
  the same provenance's `lake_backend` says `pure`. The disagreement between the seam report
  and `maya_delta` was reproduced by forcing the self-check to fail; the provenance
  consequence follows from the code (`maya/services/feature_data.py`, `provenance`). Until it
  is fixed, read `lake` on the health page and `lake_backend` in provenance.
- **How much slower pure is has not been measured.**
- The equivalence rests on `maya_delta`'s conformance suite, run on both backends and across
  them, and on the fallback matrix — the whole suite with the lake pinned to pure and every
  other Type A seam on its fallback, `python tools/ci/gates.py --fallback` (plan §7, rung 11b).
  The matrix is on demand, not in the pre-commit hook.
