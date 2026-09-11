# MAYA — Model & AI Lifecycle Assurance
# Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
# Proprietary and confidential. See LICENSE and NOTICE at the repository root.
#
# A container that can be built with no network, and that runs as nobody.
#
# Two stages, and the split is not about image size. The build stage is where a
# wheel is compiled and a cache is written; the runtime stage copies the
# installed tree and nothing else, so a compiler, a package index client and a
# pip cache full of URLs never reach the image that runs in production. The
# smaller image is a side effect of the smaller attack surface.

# ---------------------------------------------------------------- build
FROM python:3.13-slim AS build

# `--mount=type=cache` is deliberately NOT used. It makes a local build faster
# and a CI build non-reproducible, and a governance platform whose image cannot
# be rebuilt byte-for-byte from a tag is one whose SBOM describes something
# nobody can reproduce.
WORKDIR /build
COPY requirements.txt ./
RUN python -m venv /opt/maya \
 && /opt/maya/bin/pip install --no-cache-dir --upgrade pip \
 && /opt/maya/bin/pip install --no-cache-dir -r requirements.txt

# ---------------------------------------------------------------- runtime
FROM python:3.13-slim AS runtime

# A fixed uid, because a Kubernetes `runAsUser` has to name a number and an
# image that only has a name forces the deployment to guess. 10001 is outside
# every distribution's system range.
RUN groupadd --gid 10001 maya \
 && useradd --uid 10001 --gid 10001 --home-dir /app --no-create-home maya

COPY --from=build /opt/maya /opt/maya
WORKDIR /app
COPY --chown=10001:10001 . /app

# The data directory is a VOLUME and the image is read-only otherwise. The WORM
# anchor store lives under it, and an anchor written to a container filesystem
# that disappears on restart is an anchor that never existed — which is worse
# than no anchor, because the readiness report would have said the chain was
# anchored.
#
# It is created AND CHOWNED before the VOLUME declaration, which is not a
# stylistic ordering. Docker seeds a fresh anonymous volume from whatever is at
# the mount point in the image, ownership included — so a directory that does
# not exist yet produces a volume owned by root, and the process running as
# 10001 cannot write into it. Found by running the image rather than by reading
# it: the container started, failed at `mkdir /app/data/artifacts`, and the only
# symptom was a health check that never went green.
RUN mkdir -p /app/data/artifacts /app/data/attachments /app/data/worm              /app/data/delta /app/data/sqlite  && chown -R 10001:10001 /app/data
VOLUME ["/app/data"]

ENV PATH="/opt/maya/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    MAYA_DATA_DIR=/app/data

USER 10001:10001
EXPOSE 5006

# The readiness probe, in the image, so a `docker run` without an orchestrator
# still has one. It checks the evidence chain — which is the right liveness
# question for this platform and not merely whether the port answers.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,sys; \
      sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:5006/health/ready', timeout=4).status == 200 else 1)"

ENTRYPOINT ["python", "run_maya_web.py"]
