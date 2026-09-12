# The four spikes

Every performance figure in [`docs/03 §7`](../../docs/03-requirements.md) is a
**target**, and says so. A target is what somebody wrote down before building;
a result is what a machine did. This directory is the difference.

Four measurements, named in [`docs/10 §2.3`](../../docs/10-roadmap.md) since
the first release and never run:

| | What it measures | `python -m` |
|---|---|---|
| **Resolution latency** | warrant resolution p50/p95/p99, cold and warm | `tools.spikes.resolution` |
| **Point-in-time join** | training-set assembly throughput, and what it extrapolates to at a billion rows | `tools.spikes.pit_join` |
| **Sandbox escape** | what the sandbox actually stops, one attempt at a time | `tools.spikes.sandbox_escape` |
| **The estate** | the reader's path at 10,000 and 50,000 models, and the **slope** between them | `tools.spikes.estate` |

The fourth is the odd one and the reason is worth stating. The other three
answer *how fast is this*. `tools.spikes.estate` answers *what shape is this*,
because `list_models` filters in process: a number from one estate size is a
number, two are a slope, and a read whose cost grows with the estate is one that
works until it does not. No amount of headroom at today's size says where that
is.

**What it found**, in `docs/spikes/estate.json`: the paged reads hold the
`NFR-PERF-001` budget at fifty thousand models (list 441 ms against 500 ms) and
are sublinear in practice, because a fixed per-request cost dominates below about
forty thousand.

**And the fold over the whole estate is the part worth reading twice, because
this file got it wrong first.** The spike reported that `/portfolio` *did not
return inside thirty minutes* at fifty thousand models. Measured directly
afterwards it returns in **33.4 seconds**, linear at 0.67 ms per model — the
spike was competing with other work on a shared machine, and the number it
produced was about the machine. It is now **7.6 s**, after the fold stopped
asking nine questions per model ([10 §2.4a](../../docs/10-roadmap.md)).

That sequence is the argument for everything below: a number measured carelessly
is worse than a target honestly labelled, because the target does not claim to be
evidence.

Two things the spike learned about itself, both kept in its docstring because
they are the kind of mistake a benchmark makes quietly. It **timed a login page**
— `/dashboard` answers `200` to HTTP Basic because the interface takes a session
cookie, so a status check does not catch it and a read has to assert it got the
page it asked for. And a sample budget checked *between* calls bounds nothing
when one call outlasts it; neither `setitimer` (the handler cannot run inside
SQLite's C code) nor a thread nor a fork (the test client's event loop lives on a
background thread) can stop these reads from inside, so the ceiling has to be an
external `timeout` and `--only`.

## What a number from here is, and is not

**It is a measurement on the machine it ran on.** These write the hardware, the
Python version, the store and the row count into the result, because a latency
figure without them is a number somebody will quote in a different context and
be wrong. `docs/03 §7` stays a table of *targets*; a result belongs beside the
conditions that produced it.

**It is not a capacity plan.** A single-process measurement on a laptop
extrapolated to a bank's estate is arithmetic, not evidence, and
`tools.spikes.pit_join` prints the extrapolation *labelled as one* rather than
hiding that it did the multiplication.

**And what it did not measure travels worse than the number does.**
`tools.spikes.estate` seeds rows rather than registering models, which makes the
read path real and the write path unmeasured — so the seeded register has no
evidence chain, and chain verification at 50,000 models is *not* in that result
and remains a target. It says so in the result, under `not_measured`, rather
than in a footnote here.

**And a spike that passes is not a guarantee.** `tools.spikes.sandbox_escape`
reports what it **tried** as prominently as what held, because a security
control that stopped everything somebody thought to attempt has been tested
against that person's imagination.

## Running them

    .venv/bin/python -m tools.spikes.resolution --requests 2000
    .venv/bin/python -m tools.spikes.pit_join --rows 200000 --features 50
    .venv/bin/python -m tools.spikes.sandbox_escape
    .venv/bin/python -m tools.spikes.estate --sizes 10000 50000

Each prints JSON on stdout and a human-readable summary on stderr, so a CI job
can keep the first and a person can read the second.
