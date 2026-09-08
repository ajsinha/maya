#!/usr/bin/env bash
# Wait for the run to finish, then render the report.
#
# Polls the LIVE journal for the `run_finished` event the run writes itself,
# rather than watching for a process: `pgrep -f` matches any command line
# containing the pattern — including the shell doing the matching — so earlier
# attempts either killed themselves or would never have exited. A record the
# subject wrote is unambiguous.
#
# The live journal, not the published one: the published copy does not exist
# until the run has finished writing it, which is the whole point of publishing
# at the end.
cd /home/ashutosh/PycharmProjects/maya
LIVE=.soak/run/journal.jsonl
for _ in $(seq 1 400); do
  if grep -q '"what": "run_finished"' "$LIVE" 2>/dev/null; then
    echo "SOAK FINISHED"
    sleep 5                    # let the publish copy land
    .venv/bin/python tools/soak/report.py docs/soak/soak-journal.jsonl \
      -o docs/soak/SOAK-REPORT.md
    .venv/bin/python - <<'PY'
import json
rows = [json.loads(line) for line in open("docs/soak/soak-journal.jsonl")]
checks = [r for r in rows if r.get("kind") == "check"]
done = [r for r in rows if r.get("what") == "run_finished"]
print("FINAL:", len(checks), "checks,",
      sum(1 for r in checks if not r["ok"]), "failures")
if done:
    print("detail:", json.dumps(done[-1]["detail"]))
PY
    exit 0
  fi
  sleep 120
done
echo "SOAK WATCHER GAVE UP — no run_finished after 400 polls"
