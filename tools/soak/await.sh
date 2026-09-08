#!/usr/bin/env bash
# Wait for the run to finish, then render the report. A FILE, so that the
# pattern it greps for does not appear in the command line of the shell doing
# the grepping — which is how three attempts killed themselves.
cd /home/ashutosh/PycharmProjects/maya
while pgrep -f "soak/run.py" | grep -qv "^$$\$"; do
  pgrep -f "soak/run.py" >/dev/null || break
  sleep 120
done
echo "SOAK FINISHED"
.venv/bin/python tools/soak/report.py
.venv/bin/python - <<'PY'
import json
rows = [json.loads(l) for l in open("docs/soak/soak-journal.jsonl")]
checks = [r for r in rows if r.get("kind") == "check"]
print("FINAL:", len(checks), "checks,",
      sum(1 for r in checks if not r["ok"]), "failures")
PY
