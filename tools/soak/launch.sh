#!/usr/bin/env bash
cd /home/ashutosh/PycharmProjects/maya
exec .venv/bin/python tools/soak/run.py \
  --hours 6 --max-checks 3000 --port 5006 \
  --workdir /home/ashutosh/PycharmProjects/maya/.soak/run \
  --journal /home/ashutosh/PycharmProjects/maya/docs/soak/soak-journal.jsonl \
  > /home/ashutosh/PycharmProjects/maya/.soak/run.out 2>&1
