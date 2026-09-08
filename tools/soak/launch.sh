#!/usr/bin/env bash
cd /home/ashutosh/PycharmProjects/maya
exec .venv/bin/python tools/soak/run.py \
  --hours ${SOAK_HOURS:-4} --max-checks ${SOAK_CHECKS:-3000} --port 5006 \
  --workdir /home/ashutosh/PycharmProjects/maya/.soak/run \
  --publish /home/ashutosh/PycharmProjects/maya/docs/soak/soak-journal.jsonl \
  ${SOAK_DELTA_BACKEND:+--delta-backend $SOAK_DELTA_BACKEND} \
  > /home/ashutosh/PycharmProjects/maya/.soak/run.out 2>&1
