#!/usr/bin/env bash
# Stop a soak: the runner, its wrapper, its watcher and the server it spawned.
#
# A SCRIPT, because every attempt to do this from a one-liner matched the
# one-liner's own command line and killed the shell running it. The patterns
# live in a file; the shell's command line is just `bash tools/soak/stop.sh`.
set +e
for pattern in "await\.sh" "launch\.sh" "run\.py --hours"; do
  for pid in $(pgrep -f "$pattern"); do
    [ "$pid" = "$$" ] && continue
    kill "$pid" 2>/dev/null
  done
done
sleep 3
# The server is a CHILD the runner spawned; killing the runner orphans it
# rather than stopping it, which is how port 5006 stayed busy after the soak
# had already died.
for pid in $(ss -ltnp 2>/dev/null | grep ':5006' | grep -oP 'pid=\K[0-9]+'); do
  kill -9 "$pid" 2>/dev/null
done
sleep 2
ss -ltn 2>/dev/null | grep -q ':5006' && echo "5006 STILL BUSY" || echo "stopped; 5006 free"
