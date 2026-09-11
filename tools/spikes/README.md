# The three spikes

Every performance figure in [`docs/03 §7`](../../docs/03-requirements.md) is a
**target**, and says so. A target is what somebody wrote down before building;
a result is what a machine did. This directory is the difference.

Three measurements, named in [`docs/10 §2.3`](../../docs/10-roadmap.md) since
the first release and never run:

| | What it measures | `python -m` |
|---|---|---|
| **Resolution latency** | warrant resolution p50/p95/p99, cold and warm | `tools.spikes.resolution` |
| **Point-in-time join** | training-set assembly throughput, and what it extrapolates to at a billion rows | `tools.spikes.pit_join` |
| **Sandbox escape** | what the sandbox actually stops, one attempt at a time | `tools.spikes.sandbox_escape` |

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

**And a spike that passes is not a guarantee.** `tools.spikes.sandbox_escape`
reports what it **tried** as prominently as what held, because a security
control that stopped everything somebody thought to attempt has been tested
against that person's imagination.

## Running them

    .venv/bin/python -m tools.spikes.resolution --requests 2000
    .venv/bin/python -m tools.spikes.pit_join --rows 200000 --features 50
    .venv/bin/python -m tools.spikes.sandbox_escape

Each prints JSON on stdout and a human-readable summary on stderr, so a CI job
can keep the first and a person can read the second.
