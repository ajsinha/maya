"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The deployment artefacts, checked by the suite that actually runs.

`NFR-OPS-002` asked for containerisation and IaC, and the roadmap put both under
*somebody's operational work, not code*. That was true of the operating and
false of the artefacts: a firm cannot deploy MAYA safely from a README, and
every unstated default in a chart is a deployment that runs and is quietly
wrong.

Neither `docker build` nor `helm template` runs here — no Helm on this machine,
and a container build in a unit suite is a twenty-minute test nobody keeps. So
these check the properties that would be wrong *before* either tool is
involved, and each of them is a real failure somebody has shipped:

- a chart that renders with a placeholder signing key, because a deployment that
  runs is one nobody goes back and fix;
- a container running as root, or writable, or with the anchor store on a
  filesystem that disappears on restart;
- a liveness probe pointed at the readiness endpoint, which restarts the whole
  fleet the moment the evidence chain fails verification — turning one detected
  problem into an outage and destroying the instance that could have been read;
- an in-process scheduler loop with several replicas, which is not merely
  wasteful but N notifications for one lapse, and the fourth is the one somebody
  mutes.
"""
from __future__ import annotations

import os
import pathlib
import re
import subprocess
import time

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
DOCKERFILE = (ROOT / "Dockerfile").read_text()
DOCKERIGNORE = (ROOT / ".dockerignore").read_text()
COMPOSE = (ROOT / "deploy" / "compose.yaml").read_text()
HELM = ROOT / "deploy" / "helm"
HELPERS = (HELM / "templates" / "_helpers.tpl").read_text()
DEPLOYMENT = (HELM / "templates" / "deployment.yaml").read_text()
VALUES = (HELM / "values.yaml").read_text()


class TestTheImageRunsAsNobody:
    def test_it_names_a_numeric_uid(self):
        """A Kubernetes `runAsUser` has to name a number, and an image that
        only has a name forces the deployment to guess."""
        assert "USER 10001:10001" in DOCKERFILE
        assert "--uid 10001" in DOCKERFILE

    def test_the_build_tools_do_not_reach_the_runtime_image(self):
        """The split is not about size. A compiler, a package index client and
        a pip cache full of URLs never reach the image that runs."""
        assert "AS build" in DOCKERFILE and "AS runtime" in DOCKERFILE
        runtime = DOCKERFILE[DOCKERFILE.index("AS runtime"):]
        assert "pip install" not in runtime

    def test_the_data_directory_is_a_volume(self):
        """An anchor written to a container filesystem that disappears on
        restart is an anchor that never existed — worse than no anchor, because
        the readiness report would have said the chain was anchored."""
        assert 'VOLUME ["/app/data"]' in DOCKERFILE

    def test_the_healthcheck_asks_about_the_evidence_chain(self):
        assert "/health/ready" in DOCKERFILE

    def test_a_local_configuration_overlay_cannot_be_baked_in(self):
        """`application.local.yaml` is where a developer puts a real
        credential."""
        assert "config/*.local.yaml" in DOCKERIGNORE
        assert "data/" in DOCKERIGNORE and ".venv" in DOCKERIGNORE

    def test_no_build_cache_mount(self):
        """It makes a local build faster and a CI build non-reproducible, and
        an image that cannot be rebuilt byte-for-byte from a tag has an SBOM
        describing something nobody can reproduce."""
        instructions = "\n".join(line for line in DOCKERFILE.splitlines()
                                 if not line.lstrip().startswith("#"))
        assert "--mount=type=cache" not in instructions


class TestComposeGivesTheShapeOfARealDeployment:
    def test_it_uses_postgres_rather_than_sqlite(self):
        assert "postgres:16" in COMPOSE
        assert "postgresql+psycopg" in COMPOSE

    def test_the_application_connects_as_a_non_owner_role(self):
        """Connecting as the owner makes every row-level security policy
        decorative, and nothing about the configuration looks wrong."""
        assert "maya_app_login" in COMPOSE
        assert "maya_owner" in COMPOSE
        assert re.search(r"MAYA_DATABASE_URL:.*maya_app_login", COMPOSE)

    def test_the_role_bootstrap_grants_no_ownership(self):
        sql = (ROOT / "deploy" / "postgres-init.sql").read_text()
        assert "CREATE ROLE maya_app NOLOGIN" in sql
        assert "Deliberately NOT granted" in sql
        assert "GRANT CREATE" not in sql

    def test_the_container_is_read_only_with_no_capabilities(self):
        assert "read_only: true" in COMPOSE
        assert "no-new-privileges:true" in COMPOSE
        assert "cap_drop" in COMPOSE

    def test_the_anchor_store_is_on_a_named_volume(self):
        assert "data:/app/data" in COMPOSE


class TestTheChartRefusesRatherThanRenders:
    """A chart that renders is a chart somebody installs, so the place to
    refuse a configuration that cannot be safe is before it reaches a
    cluster."""

    @pytest.mark.parametrize("required", [
        "secrets.databaseUrlSecret", "secrets.sessionSecret",
        "secrets.warrantSigningKeySecret"])
    def test_the_three_secrets_have_no_default(self, required):
        field = required.split(".")[-1]
        assert re.search(rf"{field}: \"\"", VALUES), \
            f"{required} has a default, so a deployment runs without it"
        assert f"fail \"{required} is required" in HELPERS

    def test_each_refusal_says_what_it_prevents(self):
        """A `fail` that only names the field teaches nobody why."""
        assert "forge a signed-in session as any user" in HELPERS
        assert "every engine's key at once" in HELPERS
        assert "owns nothing and is not a superuser" in HELPERS

    def test_read_write_once_with_several_replicas_is_refused(self):
        """One pod holds the anchor volume and the others cannot anchor.
        Anchoring then happens intermittently on one pod out of three while the
        readiness report says the chain is anchored."""
        assert "ReadWriteOnce" in HELPERS
        assert "replicaCount > 1" in HELPERS
        assert "worse than not anchoring" in HELPERS

    def test_disabling_the_anchor_store_is_refused(self):
        assert "worm.enabled is false" in HELPERS

    def test_both_guards_are_actually_invoked(self):
        """A helper nobody calls is a refusal that never happens."""
        assert 'include "maya.requireSecrets"' in DEPLOYMENT
        assert 'include "maya.requireWorm"' in DEPLOYMENT

    def test_no_secret_is_templated_as_a_literal(self):
        """A literal ends up in `helm get values`, in the release history, and
        in whatever ships the values file into the cluster."""
        for name in ("MAYA_DATABASE_URL", "MAYA_SESSION_SECRET",
                     "MAYA_WARRANTS_SIGNING_KEY"):
            block = DEPLOYMENT[DEPLOYMENT.index(name):]
            assert "secretKeyRef" in block[:400], f"{name} is not a reference"


class TestTheProbesAskDifferentQuestions:
    def test_readiness_asks_about_the_chain(self):
        """A pod serving a broken chain should not take traffic, and a TCP
        probe cannot tell the difference."""
        assert "readinessProbe" in DEPLOYMENT
        readiness = DEPLOYMENT[DEPLOYMENT.index("readinessProbe"):]
        assert "/health/ready" in readiness[:200]

    def test_liveness_does_not(self):
        """Pointing liveness at /health/ready restarts every pod in the fleet
        the moment the chain fails verification — turning one detected problem
        into an outage, and destroying the instance that could have been read
        to find out what happened."""
        liveness = DEPLOYMENT[DEPLOYMENT.index("livenessProbe"):]
        assert "/health/live" in liveness[:200]
        assert "/health/ready" not in liveness[:200]

    def test_both_endpoints_exist(self, client):
        assert client.get("/health/live").status_code == 200
        assert client.get("/health/ready").status_code in (200, 503)


class TestTheBatchRunsExactlyOnce:
    def test_the_in_process_loop_is_off_in_the_chart(self):
        assert "MAYA_SCHEDULER_LOOP_ENABLED" in DEPLOYMENT
        block = DEPLOYMENT[DEPLOYMENT.index("MAYA_SCHEDULER_LOOP_ENABLED"):]
        assert 'value: "false"' in block[:200]

    def test_a_cronjob_drives_it_instead(self):
        cron = (HELM / "templates" / "cronjob.yaml").read_text()
        assert "kind: CronJob" in cron
        assert "/api/v1/scheduler/run" in cron

    def test_two_runs_never_overlap(self):
        cron = (HELM / "templates" / "cronjob.yaml").read_text()
        assert "concurrencyPolicy: Forbid" in cron

    def test_a_refused_batch_fails_the_job(self):
        """A batch that reports success while refusing is how an estate goes a
        month with nothing running."""
        cron = (HELM / "templates" / "cronjob.yaml").read_text()
        assert "sys.exit(0 if answer.status == 200 else 1)" in cron

    def test_the_reason_for_a_cronjob_is_written_down(self):
        cron = (HELM / "templates" / "cronjob.yaml").read_text()
        assert "N notifications for one lapse" in cron


class TestTheChartDoesNotOwnTheDatabase:
    def test_there_is_no_statefulset(self):
        names = {p.name for p in (HELM / "templates").glob("*.yaml")}
        assert "statefulset.yaml" not in names

    def test_the_chart_says_why(self):
        chart = (HELM / "Chart.yaml").read_text()
        assert "does NOT deploy a database" in chart
        assert "helm uninstall" in chart

    def test_the_anchor_volume_survives_an_uninstall(self):
        """A chart that deleted it on uninstall would make an accident
        indistinguishable from a cover-up."""
        pvc = (HELM / "templates" / "pvc.yaml").read_text()
        assert "helm.sh/resource-policy: keep" in pvc


@pytest.mark.skipif(not os.environ.get("MAYA_TEST_DOCKER"),
                    reason=("set MAYA_TEST_DOCKER=1 to build the image and run "
                            "it. Off by default: a container build is a "
                            "twenty-minute test nobody keeps in a unit suite, "
                            "and a slow suite is one people stop running"))
class TestTheImageActuallyRuns:
    """Verified by running it, which is how the one real defect here was found.

    `VOLUME ["/app/data"]` seeds a fresh anonymous volume from whatever is at
    the mount point in the image — ownership included. With the directory not
    yet created, the volume came up owned by root, the process running as 10001
    could not `mkdir /app/data/artifacts`, and the only symptom was a health
    check that never went green. No amount of reading the Dockerfile finds
    that.
    """

    IMAGE = "maya:pytest"

    @pytest.fixture(scope="class")
    def image(self):
        subprocess.run(["docker", "build", "-t", self.IMAGE, "."],
                       cwd=ROOT, check=True, capture_output=True, timeout=1800)
        return self.IMAGE

    def _run(self, image, name, extra):
        subprocess.run(["docker", "rm", "-f", name], capture_output=True)
        subprocess.run(["docker", "run", "-d", "--name", name, *extra, image],
                       check=True, capture_output=True, timeout=120)
        for _ in range(60):
            status = subprocess.run(
                ["docker", "inspect", name, "--format",
                 "{{.State.Health.Status}}"],
                capture_output=True, text=True).stdout.strip()
            if status == "healthy":
                return
            if status == "unhealthy":
                break
            time.sleep(2)
        logs = subprocess.run(["docker", "logs", name], capture_output=True,
                              text=True)
        pytest.fail(f"{name} never became healthy:\n{logs.stdout[-3000:]}"
                    f"\n{logs.stderr[-3000:]}")

    def test_it_starts_and_its_health_check_goes_green(self, image):
        try:
            self._run(image, "maya-pytest-plain", [])
        finally:
            subprocess.run(["docker", "rm", "-f", "maya-pytest-plain"],
                           capture_output=True)

    def test_it_runs_as_uid_10001(self, image):
        try:
            self._run(image, "maya-pytest-uid", [])
            out = subprocess.run(["docker", "exec", "maya-pytest-uid", "id"],
                                 capture_output=True, text=True).stdout
            assert "uid=10001" in out and "gid=10001" in out
        finally:
            subprocess.run(["docker", "rm", "-f", "maya-pytest-uid"],
                           capture_output=True)

    def test_it_runs_with_a_read_only_root_and_no_capabilities(self, image):
        """The posture `deploy/compose.yaml` declares, actually exercised. A
        compose file asserting `read_only: true` over an image that cannot run
        that way is a claim nobody checked."""
        try:
            self._run(image, "maya-pytest-ro", [
                "--read-only", "--tmpfs", "/tmp",
                "-v", "maya-pytest-data:/app/data",
                "--cap-drop", "ALL",
                "--security-opt", "no-new-privileges:true"])
        finally:
            subprocess.run(["docker", "rm", "-f", "maya-pytest-ro"],
                           capture_output=True)
            subprocess.run(["docker", "volume", "rm", "maya-pytest-data"],
                           capture_output=True)
