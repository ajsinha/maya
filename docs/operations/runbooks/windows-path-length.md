# A write fails on Windows naming the file

For anybody running MAYA or its case studies on Windows and meeting an error that names a
data file rather than a length.

**Read this first, because the error misdescribes itself.** Windows refuses a path longer
than 260 characters unless long paths have been enabled, and the error it raises names the
file — `[WinError 3] The system cannot find the path specified` or a `FileNotFoundError` on
a file the writer has just created. It reads as a corrupt name, a permissions problem or a
broken lake. It is none of those: the path is too long, and everything about the diagnosis
follows from knowing that.

MAYA's deepest paths are in the lake, because a pin's fragments are partitioned by a
64-character content hash — that one directory is 73 characters before anything else. The
rest is the lake root, the namespace, the feature name and the data file.

## What MAYA does about it

Two things, both measured by `tests/test_path_budget.py`, which fails the build if what
MAYA generates grows past its budget.

- The pure backend names a data file in 22 characters (`p-<16 hex>.parquet`) rather than the
  67 of the Delta convention. A Delta reader finds its files through the log rather than by
  their names, so the convention was costing 45 characters to say nothing.
- On Windows, `lake.backend: auto` therefore chooses the **pure** backend. The native
  writer's file names are the library's to choose, not MAYA's, and they are the long ones.

Measured, with a feature named `servicing_monthly` in a namespace named `eq`: 127 characters
under the lake root on the pure backend, 168 on the native one.

## What you choose

**Keep the lake root short.** It is configurable and the single biggest lever you hold:

```yaml
lake:
  root: "C:/maya-lake"     # 13 characters, against 63 for a path under Documents
```

Every character here is a character off every path in the lake. A lake at
`C:\Users\Alexandra\Documents\projects\maya\data\maya-deltalake` spends 63 before MAYA
writes anything.

**Or turn long paths on**, which lifts the ceiling to about 32,767 characters and lets you
pin the faster backend:

```powershell
# As administrator. Takes effect for processes started afterwards.
New-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem" `
  -Name "LongPathsEnabled" -Value 1 -PropertyType DWORD -Force
```

Python honours it from 3.6 on a manifested interpreter; the official installer's is. With it
enabled, `lake.backend: native` is safe and is the faster of the two.

**Do not** shorten a namespace or a feature name to fit. Those names are how people find
things, and a lake that is legible only because its contents are called `f1` and `n2` has
solved the wrong problem.

## Checking before you demonstrate

```bat
.venv\Scripts\python -c "from pathlib import Path; from maya.config import project_root; r=project_root()/'data'/'maya-deltalake'; f=[p for p in r.rglob('*') if p.is_file()]; print(max((len(str(p)),str(p)) for p in f) if f else 'lake is empty')"
```

If the longest is near 260, move the lake root before you need it rather than after.

---

Copyright © 2026 Ashutosh Sinha. All rights reserved.
