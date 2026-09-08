"""
maya_deltalake — the Delta Lake subset MAYA uses, in pure Python.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

**Why this exists.** `deltalake` ships as a compiled Rust extension, and some
deployments forbid binary wheels outright — no amount of vendoring helps, since
there is nothing to vendor that is allowed to run. Those estates could not
install MAYA at all.

**What this is NOT.** It is not a reimplementation of Delta Lake. Delta is a
protocol with deletion vectors, column mapping, change data feed, Z-ordering,
liquid clustering, MERGE, and multi-writer coordination over object stores.
Reproducing that would be years of work against a moving specification, and a
half-built version of it would be worse than none.

**What it is.** MAYA calls six things, and this implements those six:

    DeltaTable(path)          .version()   .load_as_version(n)
                              .to_pandas() .to_pyarrow_dataset()
    write_deltalake(path, frame, mode="append"|"overwrite", schema_mode=...)

That is the whole surface — verified by reading the codebase, not assumed.
There is no merge, no upsert, no vacuum, no partitioning and no object store,
because MAYA asks for none of them. Anything outside the subset raises
`NotImplementedError` naming itself. A fallback that quietly does less than the
thing it stands in for is the failure this is written to avoid.

**It writes real Delta.** Not a private format that merely works. The
transaction log is the actual protocol — `_delta_log/NNN…NNN.json` carrying
`protocol`, `metaData`, `add`, `remove` and `commitInfo` — so a table written
here opens in Spark, in Databricks and in `deltalake` itself, and a table
written by any of those opens here. For a platform whose promise is that the
evidence can be handed to somebody else, a format only MAYA can read would
quietly cost exactly that. `tests/test_maya_deltalake.py` writes with each
implementation and reads with the other.

**Single writer.** Commits are created with `O_EXCL`, which is the protocol's
own concurrency primitive on a POSIX filesystem: two writers racing for version
*N* means one of them fails and retries rather than both believing they won.
That is enough here because MAYA serialises Delta writes above this layer. It
is NOT enough on NFS or on an object store, and this refuses to pretend
otherwise — see `_commit`.

**Depends on pyarrow, deliberately.** MAYA already requires it — the feature
sources, the transfer layer and the assembly all use it directly — so this adds
no dependency. It is also a binary wheel, which means an estate that forbids
those cannot run MAYA at all; that is a larger problem than this package, and
naming it here is better than discovering it later.
"""
from maya_deltalake.table import DeltaTable, write_deltalake
from maya_deltalake.protocol import (DeltaProtocolError, MIN_READER, MIN_WRITER,
                                     schema_string, delta_type)

__version__ = "0.1.0"

#: What `db/delta_backend.py` reports when it has fallen back to this.
IMPLEMENTATION = "maya_deltalake"

__all__ = [
                                     "IMPLEMENTATION",
                                     "MIN_READER",
                                     "MIN_WRITER",
                                     "DeltaProtocolError",
                                     "DeltaTable",
                                     "delta_type",
                                     "schema_string",
                                     "write_deltalake",
]
