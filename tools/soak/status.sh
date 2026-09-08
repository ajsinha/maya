#!/usr/bin/env bash
# A one-line answer to "how is the soak going". A script, for the same reason
# stop.sh is one: a pattern in a command line matches the command line.
cd /home/ashutosh/PycharmProjects/maya
alive=$(ps aux | grep -c "[r]un.py --hours")
.venv/bin/python - "$alive" <<'PY'
import json, sys
try:
    rows = [json.loads(l) for l in open("docs/soak/soak-journal.jsonl")]
except Exception as exc:
    print("no journal:", exc); raise SystemExit
checks = [r for r in rows if r.get("kind") == "check"]
fails = [r for r in checks if not r["ok"]]
cycles = [r for r in rows if r.get("what") == "cycle_finished"]
windows = [r for r in rows if r.get("what") == "load_window"]
samples = [r for r in rows if r.get("kind") == "sample"]
done = [r for r in rows if r.get("what") == "run_finished"]
elapsed = rows[-1]["at"] / 60 if rows else 0
print(f"runner alive: {sys.argv[1]}   {'FINISHED' if done else 'running'}")
print(f"  elapsed   {elapsed:6.1f} min of 360")
print(f"  cycles    {len(cycles)}")
print(f"  checks    {len(checks)} of 3000   failures {len(fails)}")
if windows:
    print(f"  requests  {windows[-1]['detail']['background_calls']:,} in the "
          f"background, {windows[-1]['detail']['total_calls']:,} in all")
if len(samples) > 1:
    first, last = samples[0], samples[-1]
    print(f"  rss       {first['rss_kb']//1024} -> {last['rss_kb']//1024} MB"
          f"   fds {first.get('fds')} -> {last.get('fds')}"
          f"   db {last.get('db_bytes', 0)//1024} kB")
for f in fails[:5]:
    print(f"  FAILED [{f['family']}] {f['name']}: {str(f['got'])[:90]}")
PY
