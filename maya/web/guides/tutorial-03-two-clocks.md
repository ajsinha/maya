# Tutorial 3 · Two clocks and restatements

Data vendors correct themselves. A price published on Friday is restated on
Monday, and a model trained on Friday's number must still be explainable on
Tuesday. MAYA keeps two clocks on every value so it can answer both "what is
true?" and "what did we know then?". In this tutorial you restate a price,
read the feature as it was known before the correction, see that a sealed pin
does not move, capture the correction in a new pin, and try a fill rule that
quietly reads the future.

## Time to complete

20 minutes.

## Before you start

- [Tutorial 1 · Your first 15 minutes](/help/guides/tutorial-01-first-15-minutes)
  and [Tutorial 2 · A governed feature](/help/guides/tutorial-02-a-governed-feature):
  the approved feature `eq/prices`, its eight prices published at 18:00 UTC on
  9 January, and the sealed pin `maya://feature/eq/prices#eom/2026-01-09`.

## What you will learn

- The difference between **event time** (when a value was true) and
  **knowledge time** (when MAYA learned it).
- That a restatement is appended, never written over the old value.
- How to read a feature "as known on" a date, with `as_of_known`.
- Why a sealed pin is unchanged by a restatement, and how to re-pin to capture
  a correction, or to reproduce the original exactly.
- What a non-causal fill rule is, and what MAYA says about one.
- Where the restatement shows in the feature's history.

## Step 1 · Reconnect and read the second clock

Each row of `eq/prices` has a `date`, its event time: the day the close was the
close. Each also has a `_knowledge_time`: the moment the value became known,
which you gave at ingest. Ask MAYA what it knew at noon on 9 January, and again
at 18:00:

```python
# reconnect, then read the feature at two moments on 9 January
import os

import maya.sdk as maya

URL = os.environ.get("MAYA_URL", "http://127.0.0.1:8600")
PW = "Tutorial-pass-1"


def connect_as(user, password=PW):
    """Sign in, create an API key, and return a client acting as that person."""
    token = maya.Client(URL).auth.login(user, password)["token"]
    key = maya.Client(URL, token=token).auth.create_api_key("tutorial")["api_key"]
    return maya.connect(base_url=URL, api_key=key)


dana, mick = connect_as("dana"), connect_as("mick")

ref = "maya://feature/eq/prices@v1"
noon = dana.features.preview(ref, as_of_known="2026-01-09T12:00:00Z")
evening = dana.features.preview(ref, as_of_known="2026-01-09T18:00:00Z")
print("known at noon:", noon["total_rows"], "rows")
print("known at 18:00:", evening["total_rows"], "rows")
```

You should see nothing known at noon, and all ten rows at 18:00:

```text
known at noon: 0 rows
known at 18:00: 10 rows
```

At noon on 9 January the prices for 5 to 8 January were all true, but MAYA did
not know them yet. A backtest that used them at noon would be using information
nobody had. Knowledge time is what lets MAYA refuse that.

## Step 2 · A restatement is appended

On Monday 12 January, at 09:00, the vendor corrects AAA's close for 6 January
from 101.5 to 101.7. Ingest the correction with its own knowledge time:

```python
# the vendor's correction, ingested with the time it was published
out = dana.features.ingest(
    "eq/prices",
    b"date,symbol,close\n2026-01-06,AAA,101.7\n",
    fmt="csv",
    filename="correction.csv",
    knowledge_time="2026-01-12T09:00:00Z",
    note="vendor correction",
)
print(out["rows"], out["restatement"], out["knowledge_time"])
```

You should see one row, recognised as a restatement:

```text
1 True 2026-01-12T09:00:00+00:00
```

MAYA saw that a value for this date and symbol was already known, and marked
the ingest a restatement. Nothing was overwritten: 101.5 is still there, with
its knowledge time of 9 January. 101.7 sits beside it, with its own.

## Step 3 · Read it as known on a date

Read 6 and 7 January now, and as known at midnight on 10 January, before the
correction:

```python
# the same days, read with two different knowledge-time cuts
def show(rows):
    for r in rows:
        print(" ", r["date"][:10], r["symbol"], r["close"], r["_knowledge_time"][:10])


now = dana.features.preview(ref, start="2026-01-06", end="2026-01-07")["rows"]
then = dana.features.preview(
    ref, as_of_known="2026-01-10T00:00:00Z", start="2026-01-06", end="2026-01-07"
)["rows"]
print("now:")
show(now)
print("as known on 10 January:")
show(then)
```

You should see the corrected price now, the original as known on 10 January,
and in both the filled 7 January following whichever 6 January it was given:

```text
now:
  2026-01-06 AAA 101.7 2026-01-12
  2026-01-06 BBB 50.5 2026-01-09
  2026-01-07 AAA 101.7 NaT
  2026-01-07 BBB 50.5 NaT
as known on 10 January:
  2026-01-06 AAA 101.5 2026-01-09
  2026-01-06 BBB 50.5 2026-01-09
  2026-01-07 AAA 101.5 NaT
  2026-01-07 BBB 50.5 NaT
```

Every read takes a knowledge-time cut. Without `as_of_known` the cut is now,
and the latest knowledge of each value wins. With it, MAYA answers as it would
have on that date. The fill is applied after the cut, so the filled value moves
with the value it was filled from.

## Step 4 · The sealed pin does not move

The pin from tutorial 2 was sealed before the correction. Download it again:

```python
# the pin sealed in tutorial 2, read after the restatement
d = mick.features.download("maya://feature/eq/prices#eom/2026-01-09", format="csv")
print(d["manifest"]["content_hash"])
print([line for line in d["data"].decode().splitlines() if line.startswith("2026-01-06,AAA")])
```

You should see the same content hash as in tutorial 2, and the original price:

```text
5d6539b3ad9d9a96585cadd95e9c0228a78528968c3a731e2626f471cac16bb2
['2026-01-06,AAA,101.5,2026-01-09 18:00:00+00:00']
```

A pin is sealed: its rows and their hash are fixed for good. Anything trained
on it can be reproduced exactly, whatever the vendor does next. Live reads move
with corrections; pins never do.

## Step 5 · Re-pin to capture the correction, or reproduce the original

To use the corrected price, pin again, under a new series. And because every
pin takes a knowledge-time cut too, you can also seal exactly what was known on
10 January, after the fact:

```python
# a new pin with the correction, and one replaying what was known on 10 January
out = mick.features.pin("eq/prices", version_no=1, pin_name="restated", as_of="2026-01-09")
restated = mick.wait(out["job"])["result"]
out = mick.features.pin(
    "eq/prices",
    version_no=1,
    pin_name="replay",
    as_of="2026-01-09",
    as_of_known="2026-01-10T00:00:00Z",
)
replay = mick.wait(out["job"])["result"]
print("restated:", restated["content_hash"])
print("replay:  ", replay["content_hash"], replay["bytes_new"], "new bytes")
```

You should see a new hash for the restated pin, and for the replay the very hash
of the original pin, with nothing new to store:

```text
restated: b1a62c69a236b0e8e63effb618c655678646072d5da27ce68712c35bc00680d8
replay:   5d6539b3ad9d9a96585cadd95e9c0228a78528968c3a731e2626f471cac16bb2 0 new bytes
```

The replay pin was made after the correction, yet it holds exactly what was
known on 10 January, so it hashes the same as the pin made before it. That is
what makes an old result checkable: anyone can rebuild the data it stood on
and compare hashes.

## Step 6 · A fill rule that reads the future

Suppose dana thinks a straight line between neighbours is a better fill for
7 January than carrying 6 January forward. She opens version 2 of the
definition with `linear_interp`:

```python
# version 2: interpolate the gap instead of filling forward
dana.features.new_draft("eq/prices")
v1 = dana.features.get("eq/prices")["versions"][-1]["definition"]
v2 = dict(
    v1,
    resolution={
        "grid": {"calendar": "ISO_business_days"},
        "rules": {"close": "linear_interp(limit=3)"},
    },
)
dana.features.update_draft("eq/prices", v2)

pv = dana.features.draft_preview("eq/prices")
for row in pv["rows"][4:6]:
    print(row["date"][:10], row["symbol"], row["close"])
print(pv["fill_report"]["attributes"]["close"])
print("non-causal attributes:", pv["fill_report"]["non_causal"])
```

You should see 7 January filled halfway between 6 and 8 January, and the rule
reported as non-causal:

```text
2026-01-07 AAA 101.85
2026-01-07 BBB 50.75
{'rule': 'linear_interp(limit=3)', 'filled': 2, 'longest_run': 1, 'non_causal': True}
non-causal attributes: ['close']
```

101.85 is the midpoint of 101.7 and 102.0, and 102.0 is the close of 8 January.
On the evening of 7 January nobody knew it. A model trained on this series
would have seen tomorrow's price in today's row, and would look better in a
backtest than it can ever be live. `backward_fill`, `linear_interp` and
`spline_interp` all read the future, and MAYA marks them so.

MAYA does not forbid the rule; interpolation is fine for a chart. It records
it. Submit the version and look at what is stored:

```python
# submit, then read what MAYA recorded about version 2
r = dana.features.transition("eq/prices", 2, "submit")
v = dana.features.get("eq/prices")["versions"][0]
print(r["state"], "non_causal:", v["non_causal"], "change:", v["change_class"])
print(dana.features.compare("eq/prices", 1, 2)["diff"][0]["what"])

# mick sends it back: the series is meant for training
r = mick.features.transition(
    "eq/prices", 2, "request_changes", rationale="linear_interp reads the next day's close"
)
print(r["state"])
```

You should see the version in review, flagged non-causal and classed as a
behavioural change to the resolution, then sent back by mick:

```text
in_review non_causal: True change: behavioral
resolution
changes_requested
```

The flag travels with the version. A training warrant's leakage certificate is
refused for a non-causal feature unless the warrant says `allow_non_causal` and
gives a written justification, and even then the certificate records the
exception. Here the
reviewer caught it first.

## Step 7 · The restatement in the feature's history

```python
# every ingest, newest first, with its knowledge time
f = dana.features.get("eq/prices")
for i in f["ingests"]:
    print(
        i["knowledge_time"],
        i["rows"],
        "restatement" if i["restatement"] else "original",
        i["note"] or "-",
        i["created_by"],
    )
```

You should see both ingests, the correction marked as a restatement:

```text
2026-01-12T09:00:00+00:00 1 restatement vendor correction dana
2026-01-09T18:00:00+00:00 8 original - dana
```

The feature's page in the catalog shows the same history, and each ingest's
file is kept by hash. When a model is live, a restatement under data it was
scored on is also raised against its execution warrant, for someone to
acknowledge.

## Next steps

- [Tutorial 4 · Feature sets and pins](/help/guides/tutorial-04-feature-sets-and-pins)
  combines features into the panel a model reads, and pins it.
- [Data](/help/data#bitemporal) explains the two clocks and the lake in depth.
- [Features](/help/features) lists every fill rule, causal and not.

## If something goes wrong

| What you see | Why | What to do |
|---|---|---|
| `restatement` is `False` for the correction | The row's date and symbol do not match a known row | Check the date format and the symbol; a new key is a new row, not a correction |
| The as-known read already shows 101.7 | The `as_of_known` you gave is after the correction's knowledge time | Use a cut before 2026-01-12T09:00:00Z |
| `Conflict` on the `restated` or `replay` pin | You ran step 5 before | Use another series name |
| `NotApproved: There is no editable draft` in step 6 | Version 2 already exists from an earlier run | Carry on from `transition`, or start from a fresh estate |
