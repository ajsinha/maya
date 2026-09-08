#!/usr/bin/env bash
# Stop whatever is there, clear the scratch, start a fresh run, arm the watcher.
#
# One script, because doing this from the shell kept killing the shell: the
# patterns `stop.sh` greps for appear in the command line of any invocation
# that mentions them, and `pgrep -f` does not care which process it is looking
# at. Invoking a file keeps the patterns out of the caller's command line.
#
#   SOAK_HOURS=4 SOAK_DELTA_BACKEND=maya_deltalake tools/soak/restart.sh
set -u
cd /home/ashutosh/PycharmProjects/maya
bash tools/soak/stop.sh
rm -rf .soak
mkdir -p .soak docs/soak
rm -f docs/soak/soak-journal.jsonl docs/soak/SOAK-REPORT.md
nohup bash tools/soak/launch.sh > /dev/null 2>&1 &
sleep 12
nohup bash tools/soak/await.sh > .soak/await.out 2>&1 &
sleep 25
echo "commit:  $(git rev-parse --short HEAD)"
echo "runner:  $(ps aux | grep -c '[r]un\.py')"
echo "watcher: $(ps aux | grep -c '[a]wait\.sh')"
curl -s --max-time 5 http://127.0.0.1:5006/health || echo "(server not answering yet)"
echo
