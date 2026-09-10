"""
MAYA — Governance over HTTP: challenge, approval, findings and the record.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.

The second and third lines' half of the platform -- validation, findings and
the year between raising one and closing it, lifecycle, quorum approval,
overlays, baselined debt, regimes and attached documents.

The application, the four principals and a registered model come from
``conftest``; ``quorum_approve`` and ``login`` from ``api_helpers``. Everything
here runs against the real app over HTTP, because an interface tested through a
shortcut is an interface nobody has tested.
"""
import time

import pytest
from fastapi.testclient import TestClient

from tests.api_helpers import login as _login
from tests.conftest import CONTRACT, KERNEL, NAME, URN


# A scored population with a known Gini, so a threshold test has something real
# to be right or wrong about.
SCORED = {"left": [0, 0, 0, 0, 0, 1, 0, 1, 1, 1, 0, 1, 1, 1, 1, 1],
          "right": [0.02, 0.05, 0.09, 0.12, 0.18, 0.21, 0.24, 0.33,
                    0.41, 0.48, 0.52, 0.61, 0.70, 0.78, 0.85, 0.94]}


class TestValidationApi:
    def test_the_test_catalogue_is_published(self, client):
        body = client.get("/api/v1/tests").json()
        keys = {t["key"] for t in body["tests"]}
        assert "discrimination.gini" in keys and "stability.psi" in keys

    def test_open_record_and_conclude(self, registered):
        v = registered.post("/api/v1/validations", json={
            "urn": URN, "semver": "3.2.1", "validators": ["person/a.mehta"],
            "scope": ["discrimination"]})
        assert v.status_code == 201
        vid = v.json()["id"]

        r = registered.post(f"/api/v1/validations/{vid}/results",
                            json={"test_key": "discrimination.gini",
                                  "threshold": {"min": 0.3}, **SCORED})
        assert r.status_code == 201 and r.json()["passed"] is True

        done = registered.post(f"/api/v1/validations/{vid}/conclude",
                               json={"outcome": "approved",
                                     "tier_verdict": "remains_appropriate"})
        assert done.status_code == 200 and done.json()["outcome"] == "approved"

    def test_the_builder_cannot_validate_their_own_version(self, registered, people):
        """The version was created by d.raman, so naming them as validator fails."""
        r = registered.post("/api/v1/validations", auth=people["a.mehta"], json={
            "urn": URN, "semver": "3.2.1", "validators": ["d.raman"]})
        assert r.status_code == 409
        assert "independence failed" in r.json()["detail"]
        assert "d.raman built this version" in r.json()["detail"]

    def test_approval_over_a_failed_test_is_refused_with_the_route_out(self, registered):
        vid = registered.post("/api/v1/validations", json={
            "urn": URN, "semver": "3.2.1", "validators": ["person/a.mehta"]}).json()["id"]
        registered.post(f"/api/v1/validations/{vid}/results",
                        json={"test_key": "discrimination.gini",
                              "threshold": {"min": 0.99}, **SCORED})
        r = registered.post(f"/api/v1/validations/{vid}/conclude",
                            json={"outcome": "approved",
                                     "tier_verdict": "remains_appropriate"})
        assert r.status_code == 409
        assert "approved_with_conditions" in r.json()["detail"]

    def test_a_validation_reads_back_with_its_results_and_summary(self, registered):
        vid = registered.post("/api/v1/validations", json={
            "urn": URN, "semver": "3.2.1", "validators": ["person/a.mehta"]}).json()["id"]
        registered.post(f"/api/v1/validations/{vid}/results",
                        json={"test_key": "calibration.brier",
                              "threshold": {"max": 1.0}, **SCORED})
        body = registered.get(f"/api/v1/validations/{vid}").json()
        assert body["summary"]["tests_run"] == 1
        assert body["results"][0]["test_key"] == "calibration.brier"

    def test_an_unknown_validation_is_404(self, client):
        assert client.get("/api/v1/validations/nope").status_code == 404

    def test_replay_reproduces_over_the_api(self, registered):
        vid = registered.post("/api/v1/validations", json={
            "urn": URN, "semver": "3.2.1", "validators": ["person/a.mehta"]}).json()["id"]
        registered.post(f"/api/v1/validations/{vid}/results",
                        json={"test_key": "discrimination.gini",
                              "threshold": {"min": 0.3}, **SCORED})
        report = registered.post(
            f"/api/v1/validations/{vid}/replay",
            json={"data": {"discrimination.gini": [SCORED["left"], SCORED["right"]]}}).json()
        assert report["reproducible"] is True and report["reproduced"] == 1

    def test_replay_without_data_reports_skipped_not_reproduced(self, registered):
        vid = registered.post("/api/v1/validations", json={
            "urn": URN, "semver": "3.2.1", "validators": ["person/a.mehta"]}).json()["id"]
        registered.post(f"/api/v1/validations/{vid}/results",
                        json={"test_key": "discrimination.gini",
                              "threshold": {"min": 0.3}, **SCORED})
        report = registered.post(f"/api/v1/validations/{vid}/replay",
                                 json={"data": {}}).json()
        assert report["reproducible"] is False and len(report["skipped"]) == 1

class TestFindingsApi:
    def test_raise_and_read_back_a_finding(self, registered):
        r = registered.post("/api/v1/findings", json={
            "urn": URN, "severity": "Critical", "title": "Leakage in training set",
            "owner": "person/j.okafor"})
        assert r.status_code == 201 and r.json()["blocking"] is True

        body = registered.get("/api/v1/findings", params={"urn": URN}).json()
        assert body["summary"]["blocking"] == 1
        assert body["blocking"][0]["title"] == "Leakage in training set"

    def test_a_blocking_finding_refuses_warrant_resolution(self, registered):
        registered.post("/api/v1/findings", json={
            "urn": URN, "severity": "Critical", "title": "Leakage",
            "owner": "person/j.okafor"})
        r = registered.post("/api/v1/resolve", json={
            "urn": f"{URN}#champion", "environment": "prod",
            "principal": "svc/origination", "declared_use": "origination_decision"})
        assert r.status_code == 423
        assert r.json()["error"] == "blocked"
        assert r.json()["remediation"]

    def test_closing_the_finding_restores_service(self, in_service, people):
        """`in_service`, because resolving now also requires that somebody
        approved the model record — this test is about the finding, and a
        refusal for the other reason would make it pass or fail for the wrong
        one."""
        fid = in_service.post("/api/v1/findings", auth=people["s.iqbal"], json={
            "urn": URN, "severity": "Critical", "title": "Leakage",
            "owner": "person/j.okafor"}).json()["id"]
        closed = in_service.post(
            f"/api/v1/findings/{fid}/close", auth=people["a.mehta"],
            json={"evidence": {"pr": "1420"}})
        assert closed.status_code == 200, closed.text
        r = in_service.post("/api/v1/resolve", json={
            "urn": f"{URN}#champion", "environment": "prod",
            "principal": "svc/origination", "declared_use": "origination_decision"})
        assert r.status_code == 200, r.text

    def test_the_owner_cannot_verify_their_own_closure_over_the_api(
            self, registered, people):
        """A different rule from segregation: this one is about the finding's
        OWNER attesting their own remediation, and it lives in the register
        rather than in the authorisation layer. Raised and closed by different
        principals so the segregation gate does not answer first."""
        mrm, val = people["s.iqbal"], people["a.mehta"]
        # Owned by the validator, so that when the validator closes it the
        # register's owner check is what answers. The verifier is now the
        # authenticated caller, so owning it and closing it are the same act.
        fid = registered.post("/api/v1/findings", auth=mrm, json={
            "urn": URN, "severity": "High", "title": "Docs stale",
            "owner": "person/a.mehta"}).json()["id"]
        r = registered.post(f"/api/v1/findings/{fid}/close", auth=val,
                            json={"evidence": {"pr": "1"}})
        assert r.status_code == 409 and "own closure" in r.json()["detail"]

    def test_a_closure_cannot_be_attributed_to_somebody_else(self, registered,
                                                             people):
        """`verified_by` used to be a request field, so the owner of a blocking
        finding could close their own by naming somebody else -- and the forged
        attribution went into the permanent evidence chain."""
        mrm, val = people["s.iqbal"], people["a.mehta"]
        fid = registered.post("/api/v1/findings", auth=mrm, json={
            "urn": URN, "severity": "High", "title": "Docs stale",
            "owner": "person/j.okafor"}).json()["id"]
        r = registered.post(f"/api/v1/findings/{fid}/close", auth=val,
                            json={"verified_by": "person/somebody.else",
                                  "evidence": {"pr": "1"}})
        assert r.status_code == 403
        assert r.json()["error"] == "verifier_not_self"

    def test_a_closure_naming_the_caller_is_accepted(self, registered, people):
        """Passing it is allowed; passing somebody else is not."""
        mrm, val = people["s.iqbal"], people["a.mehta"]
        fid = registered.post("/api/v1/findings", auth=mrm, json={
            "urn": URN, "severity": "High", "title": "Docs stale",
            "owner": "person/j.okafor"}).json()["id"]
        r = registered.post(f"/api/v1/findings/{fid}/close", auth=val,
                            json={"verified_by": "a.mehta",
                                  "evidence": {"pr": "1"}})
        assert r.status_code == 200, r.text

    def test_the_raiser_cannot_close_it_over_the_api(self, registered, people):
        """This is the rule that was inert: the route searched for evidence
        under the finding's id while the register writes it under the model's,
        so the lookup always came back empty and the check always passed."""
        mrm = people["s.iqbal"]
        fid = registered.post("/api/v1/findings", auth=mrm, json={
            "urn": URN, "severity": "High", "title": "Docs stale",
            "owner": "person/j.okafor"}).json()["id"]
        r = registered.post(f"/api/v1/findings/{fid}/close", auth=mrm,
                            json={"evidence": {"pr": "1"}})
        assert r.status_code == 403
        assert r.json()["error"] == "segregation_of_duties"
        assert "may not close it" in r.json()["detail"]
        assert "finding_raised" in r.json()["detail"]

    def test_raising_one_finding_does_not_block_closing_another(self, registered,
                                                                people):
        """The narrowing is by finding, not by model — otherwise a validator who
        raised anything on a model could close nothing on it."""
        mrm, val = people["s.iqbal"], people["a.mehta"]
        registered.post("/api/v1/findings", auth=mrm, json={
            "urn": URN, "severity": "Low", "title": "Typo", "owner": "person/j.okafor"})
        other = registered.post("/api/v1/findings", auth=val, json={
            "urn": URN, "severity": "High", "title": "Drift",
            "owner": "person/j.okafor"}).json()["id"]
        r = registered.post(f"/api/v1/findings/{other}/close", auth=mrm,
                            json={"evidence": {"pr": "2"}})
        assert r.status_code == 200, r.text

    def test_an_unknown_severity_is_refused(self, registered):
        r = registered.post("/api/v1/findings", json={
            "urn": URN, "severity": "Catastrophic", "title": "x", "owner": "person/o"})
        assert r.status_code == 409

class TestFindingWorkflowOverTheApi:
    """Everything between raising a finding and closing it.

    The register was already a control; this is the year in the middle, where a
    finding could previously be handed round, never accepted, and given a later
    date by the one person with a reason to want one.
    """

    def _raise(self, client, people, severity="High", title="Segment drift"):
        return client.post("/api/v1/findings", auth=people["s.iqbal"], json={
            "urn": URN, "severity": severity, "title": title,
            "owner": "person/j.okafor"}).json()["id"]

    def test_a_finding_reads_back_with_everything_derived_from_its_acts(
            self, registered, people):
        fid = self._raise(registered, people)
        body = registered.get(f"/api/v1/findings/{fid}").json()
        assert body["acknowledgement"]["acknowledged"] is False
        assert body["extensions"]["count"] == 0
        assert body["escalation"]["escalate"] is False
        assert body["age_bucket"] == "0-30 days"

    def test_the_owner_accepts_it_with_a_plan(self, registered, people):
        fid = self._raise(registered, people)
        r = registered.post(f"/api/v1/findings/{fid}/acknowledge",
                            auth=people["j.okafor"],
                            json={"plan": "Re-fit on the 2026 sample by 30 June"})
        assert r.status_code == 200, r.text
        assert r.json()["acknowledgement"]["acknowledged"] is True
        assert r.json()["status"] == "in_remediation"

    def test_nobody_may_accept_it_for_the_owner(self, registered, people):
        """An acknowledgement somebody else recorded for you is the paperwork of
        a commitment without the commitment."""
        fid = self._raise(registered, people)
        r = registered.post(f"/api/v1/findings/{fid}/acknowledge",
                            auth=people["a.mehta"], json={"plan": "a plan"})
        assert r.status_code == 403
        assert r.json()["error"] == "not_the_owner"
        assert r.json()["remediation"]

    def test_accepting_without_a_plan_is_refused_with_what_to_do(
            self, registered, people):
        fid = self._raise(registered, people)
        r = registered.post(f"/api/v1/findings/{fid}/acknowledge",
                            auth=people["j.okafor"], json={})
        assert r.status_code == 422 and r.json()["error"] == "plan_required"
        assert "receipt, not a commitment" in r.json()["detail"]

    def test_a_handover_is_recorded_with_its_reason(self, registered, people):
        fid = self._raise(registered, people)
        r = registered.post(f"/api/v1/findings/{fid}/assign",
                            auth=people["j.okafor"],
                            json={"to": "person/d.raman",
                                  "reason": "the re-fit is development work"})
        assert r.status_code == 200 and r.json()["owner"] == "person/d.raman"
        reading = registered.get(f"/api/v1/findings/{fid}").json()
        assert reading["handovers"][0]["from"] == "person/j.okafor"
        assert reading["handovers"][0]["by"] == "j.okafor"

    def test_a_handover_without_a_reason_is_refused(self, registered, people):
        fid = self._raise(registered, people)
        r = registered.post(f"/api/v1/findings/{fid}/assign",
                            auth=people["j.okafor"],
                            json={"to": "person/d.raman", "reason": " "})
        assert r.status_code == 422 and r.json()["error"] == "reason_required"

    def test_the_owner_cannot_extend_their_own_deadline(self, registered, people):
        """Refused twice over: the first line does not hold the permission, and
        the register would refuse the owner even if it did."""
        fid = self._raise(registered, people)
        registered.post(f"/api/v1/findings/{fid}/acknowledge",
                        auth=people["j.okafor"], json={"plan": "a plan"})
        r = registered.post(f"/api/v1/findings/{fid}/extend",
                            auth=people["j.okafor"],
                            json={"reason": "need more time", "days": 30})
        assert r.status_code == 403 and r.json()["error"] == "forbidden"

    def test_the_second_line_extends_it_with_a_reason(self, registered, people):
        fid = self._raise(registered, people)
        registered.post(f"/api/v1/findings/{fid}/acknowledge",
                        auth=people["j.okafor"], json={"plan": "a plan"})
        r = registered.post(f"/api/v1/findings/{fid}/extend",
                            auth=people["s.iqbal"],
                            json={"reason": "the 2026 sample closes in Q3",
                                  "days": 30})
        assert r.status_code == 200, r.text
        assert r.json()["extensions"]["count"] == 1
        assert r.json()["extensions"]["history"][0]["by"] == "s.iqbal"

    def test_extending_something_nobody_accepted_is_refused(self, registered,
                                                            people):
        fid = self._raise(registered, people)
        r = registered.post(f"/api/v1/findings/{fid}/extend",
                            auth=people["s.iqbal"],
                            json={"reason": "more time", "days": 30})
        assert r.status_code == 409 and r.json()["error"] == "not_acknowledged"
        assert "acknowledge it with a plan first" in r.json()["remediation"]

    def test_whoever_accepted_it_may_not_then_extend_it(self, registered, people):
        """A validator who owns a finding holds both permissions; the evidence
        chain still refuses them, which is the point of checking there."""
        fid = registered.post("/api/v1/findings", auth=people["s.iqbal"], json={
            "urn": URN, "severity": "High", "title": "Validation docs stale",
            "owner": "person/a.mehta"}).json()["id"]
        registered.post(f"/api/v1/findings/{fid}/acknowledge",
                        auth=people["a.mehta"], json={"plan": "rewrite them"})
        r = registered.post(f"/api/v1/findings/{fid}/extend",
                            auth=people["a.mehta"],
                            json={"reason": "busy", "days": 10})
        assert r.status_code == 403
        assert r.json()["error"] == "segregation_of_duties"
        assert "may not move the date they accepted" in r.json()["detail"]

    def test_extending_past_the_limit_raises_a_finding_of_its_own(
            self, registered, people):
        fid = self._raise(registered, people)
        registered.post(f"/api/v1/findings/{fid}/acknowledge",
                        auth=people["j.okafor"], json={"plan": "a plan"})
        for i in range(3):
            registered.post(f"/api/v1/findings/{fid}/extend",
                            auth=people["s.iqbal"],
                            json={"reason": f"reason {i}", "days": 10})
        opened = registered.get("/api/v1/findings", params={"urn": URN}).json()
        escalations = [f for f in opened["open"]
                       if f["category"] == "remediation_extension"]
        assert len(escalations) == 1
        assert "moved repeatedly" in escalations[0]["title"]

    def test_the_ageing_profile_is_what_a_committee_asks_for(self, registered,
                                                             people):
        self._raise(registered, people, "Critical", "Leakage")
        fid = self._raise(registered, people, "Low", "Typo")
        registered.post(f"/api/v1/findings/{fid}/acknowledge",
                        auth=people["j.okafor"], json={"plan": "fix the typo"})
        body = registered.get("/api/v1/findings/ageing",
                              params={"urn": URN}).json()
        assert body["open"] == 2 and body["blocking"] == 1
        assert body["by_severity"]["Critical"]["open"] == 1
        assert body["unacknowledged"] == 1
        assert body["by_age"]["0-30 days"] == 2

    def test_the_estate_profile_needs_no_model(self, registered, people):
        self._raise(registered, people)
        body = registered.get("/api/v1/findings/ageing").json()
        assert body["model"] is None and body["open"] == 1
        assert body["scope"] >= 1

    def test_the_escalated_list_names_a_role(self, registered, people):
        fid = self._raise(registered, people, "Critical", "Leakage")
        registered.post(f"/api/v1/findings/{fid}/acknowledge",
                        auth=people["j.okafor"], json={"plan": "rebuild"})
        # Reach past the remediation date the way time would.
        registered.app.state.ctx["findings"].findings.set({"due_at": 1.0}, id=fid)
        body = registered.get(f"/api/v1/findings/{fid}/escalation").json()
        assert body["escalate"] is True
        assert body["to_role"] == "model_risk_manager"
        listed = registered.get("/api/v1/findings/escalated",
                                params={"urn": URN}).json()
        assert len(listed["escalated"]) == 1
        assert "past what their owner alone" in listed["detail"]

    def test_a_missing_finding_is_a_404_and_not_a_bare_400(self, registered):
        r = registered.get("/api/v1/findings/no-such-finding")
        assert r.status_code == 404 and r.json()["error"] == "no_finding"
        assert r.json()["remediation"]

    def test_a_closed_findings_workflow_has_ended(self, registered, people):
        fid = self._raise(registered, people)
        registered.post(f"/api/v1/findings/{fid}/close", auth=people["a.mehta"],
                        json={
                              "evidence": {"pr": "1420"}})
        r = registered.post(f"/api/v1/findings/{fid}/plan",
                            auth=people["j.okafor"], json={"plan": "too late"})
        assert r.status_code == 409 and r.json()["error"] == "finding_closed"

    def test_the_acts_are_published_with_what_each_means(self, registered):
        body = registered.get("/api/v1/finding-acts").json()
        acts = {a["act"]: a["means"] for a in body["acts"]}
        assert set(acts) == {"assigned", "acknowledged", "planned", "extended"}
        assert all(acts.values())

    def test_an_unaccepted_finding_reaches_its_owner_on_the_dashboard(
            self, registered, people):
        """The reminder cycle: derived like everything else, so it clears itself
        when the owner accepts rather than when somebody ticks a task."""
        fid = self._raise(registered, people)
        registered.app.state.ctx["findings"].findings.set(
            {"raised_at": time.time() - 30 * 86400.0}, id=fid)
        owner = people["j.okafor"]
        client = TestClient(registered.app)
        client.post("/login", data={"username": owner[0], "password": owner[1],
                                    "next": "/dashboard"})
        body = client.get("/dashboard").text
        assert "Finding not accepted: Segment drift" in body
        assert "Accept it with a plan" in body

    def test_the_scheduler_records_a_finding_nobody_ever_accepted(
            self, registered, people):
        fid = self._raise(registered, people)
        registered.app.state.ctx["findings"].findings.set(
            {"raised_at": time.time() - 30 * 86400.0}, id=fid)
        out = registered.post("/api/v1/scheduler/run",
                              json={"jobs": ["findings.unacknowledged"]}).json()
        assert out["ran"] == 1 and out["failed"] == 0
        assert out["results"][0]["outcome"]["count"] == 1

class TestLifecycleApi:
    def test_the_state_machine_is_published(self, client, people):
        body = client.get("/api/v1/lifecycle", auth=people["d.raman"]).json()
        assert {t["name"] for t in body["transitions"]} == {
            "submit", "return", "approve", "attest", "amend", "retire"}

    def test_the_whole_path_over_the_api(self, registered, people):
        owner, mrm = people["j.okafor"], people["s.iqbal"]
        assert registered.post(f"/api/v1/models/{NAME}/submit", auth=owner,
                               json={"note": "ready"}).status_code == 200
        assert registered.post(f"/api/v1/models/{NAME}/approve", auth=mrm,
                               json={"note": "sound"}).status_code == 200

        state = registered.get(f"/api/v1/models/{NAME}",
                               auth=owner).json()["lifecycle"]
        assert state["state"] == "approved" and not state["mutable"]
        assert state["open_attestation"]["outstanding_roles"] == [
            "model_owner", "model_risk_manager"]

        registered.post(f"/api/v1/models/{NAME}/attest", auth=owner,
                        json={"role": "model_owner", "statement": "controls operating"})
        r = registered.post(f"/api/v1/models/{NAME}/attest", auth=mrm,
                            json={"role": "model_risk_manager"})
        assert r.json()["state"] == "attested"

    def test_a_developer_cannot_approve_the_record(self, registered, people):
        registered.post(f"/api/v1/models/{NAME}/submit", auth=people["j.okafor"], json={})
        r = registered.post(f"/api/v1/models/{NAME}/approve", auth=people["d.raman"],
                            json={})
        assert r.status_code == 403

    def test_an_attested_model_refuses_a_new_version(self, registered, people):
        owner, mrm, dev = people["j.okafor"], people["s.iqbal"], people["d.raman"]
        registered.post(f"/api/v1/models/{NAME}/submit", auth=owner, json={})
        registered.post(f"/api/v1/models/{NAME}/approve", auth=mrm, json={})
        registered.post(f"/api/v1/models/{NAME}/attest", auth=owner,
                        json={"role": "model_owner"})
        registered.post(f"/api/v1/models/{NAME}/attest", auth=mrm,
                        json={"role": "model_risk_manager"})
        r = registered.post(f"/api/v1/models/{NAME}/versions", auth=dev,
                            json={"semver": "4.0.0", "kernel": KERNEL})
        assert r.status_code == 409
        assert "immutable" in r.json()["detail"]
        assert "amendment" in r.json()["detail"]

    def test_deletion_is_refused_for_everyone_but_an_administrator(self, registered,
                                                                   people):
        for who in (people["j.okafor"], people["s.iqbal"], people["d.raman"]):
            r = registered.request("DELETE", f"/api/v1/models/{NAME}",
                                   auth=who, params={"reason": "cleanup"})
            assert r.status_code == 403, f"{who[0]} must not be able to delete"

    def test_a_model_something_refers_to_is_not_deleted(self, registered):
        """`registered` has a version, an alias and a live warrant.

        Nineteen tables carry a `model_id`. Deleting this used to succeed and
        leave every one of those rows pointing at an identifier that no longer
        resolves — and the evidence chain, which survives the deletion by
        design, then described acts against a model nobody could look up.
        """
        r = registered.request("DELETE", f"/api/v1/models/{NAME}",
                               params={"reason": "registered in error"})
        assert r.status_code == 409, r.text
        assert r.json()["error"] == "still_referenced"
        detail = r.json()["detail"]
        assert "version 3.2.1" in detail, "name what refers to it"
        assert "retire this instead" in r.json()["remediation"]

    def test_an_administrator_may_delete_what_nothing_refers_to(self, client):
        """Registered in error, two minutes old, nothing hanging off it — which
        is the case deletion exists for."""
        before = client.get("/api/v1/evidence/chain").json()["length"]
        client.post("/api/v1/models", json={
            "urn": "maya://model/typo.mistake", "name": "Typo",
            "model_class": "c", "domain": "credit", "owner": "person/j.okafor",
            "legal_entity": "LE-US-01", "purpose": "registered by mistake"})
        r = client.request("DELETE", "/api/v1/models/typo.mistake",
                           params={"reason": "registered in error"})
        assert r.status_code == 200 and r.json()["deleted"] is True, r.text
        chain = client.get("/api/v1/evidence/chain").json()
        assert chain["valid"] is True and chain["length"] > before

    def test_the_workflow_renders_in_the_interface(self, registered, people):
        registered.post(f"/api/v1/models/{NAME}/submit", auth=people["j.okafor"], json={})
        registered.post("/login", data={"username": "admin", "password": "maya-admin-dev",
                                        "next": "/dashboard"})
        body = registered.get(f"/model/{NAME}").text
        assert "Approval &amp; attestation" in body
        assert 'class="flow"' in body, "the stepper should render"
        assert "FROZEN" in body, "a submitted record is not open to change"

    def test_a_lifecycle_refusal_renders_in_the_standard_shape(self, registered, people):
        """Every refusal in the platform has the same three fields."""
        r = registered.post(f"/api/v1/models/{NAME}/approve", auth=people["s.iqbal"],
                            json={})
        assert r.status_code == 409
        body = r.json()
        assert body["error"] == "illegal_transition"
        assert "from here you may" in body["detail"]
        assert body["remediation"]

    def test_amending_reopens_an_attested_record(self, registered, people):
        owner, mrm, dev = people["j.okafor"], people["s.iqbal"], people["d.raman"]
        registered.post(f"/api/v1/models/{NAME}/submit", auth=owner, json={})
        registered.post(f"/api/v1/models/{NAME}/approve", auth=mrm, json={})
        registered.post(f"/api/v1/models/{NAME}/attest", auth=owner,
                        json={"role": "model_owner"})
        registered.post(f"/api/v1/models/{NAME}/attest", auth=mrm,
                        json={"role": "model_risk_manager"})

        r = registered.post(f"/api/v1/models/{NAME}/amend", auth=owner,
                            json={"reason": "recalibrate for the 2026 cycle",
                                  "scope": ["kernel"]})
        assert r.status_code == 200 and r.json()["status"] == "amending"
        assert registered.post(f"/api/v1/models/{NAME}/versions", auth=dev,
                               json={"semver": "4.0.0", "kernel": KERNEL}).status_code == 201

class TestVersionApprovalIsAQuorum:
    """The model record was attested by several people while the version — the
    thing that actually runs — was approved by one. This closes that."""

    def _version(self, client, people, semver="4.0.0"):
        """A real content address, because a digest is now validated.

        This sent `sha256:e`, which the register accepted and nothing could ever
        resolve. The helper swallowed the response, so when the digest started
        being checked the version simply did not exist and five tests failed on
        a 404 about something else entirely.
        """
        created = client.post(
            f"/api/v1/models/{NAME}/versions", auth=people["d.raman"],
            json={"semver": semver, "kernel": KERNEL, "contract": CONTRACT,
                  "artifact_digest": "sha256:" + "e" * 64})
        assert created.status_code == 201, created.text
        return semver

    def test_the_quorum_table_is_published(self, registered):
        by_tier = {r["tier"]: r["signatures"]
                   for r in registered.get(
                       "/api/v1/version-approval-quorum").json()["quorum"]}
        assert by_tier[1] == 2 and by_tier[4] == 1

    def test_a_single_signature_is_refused_and_names_the_route(self, registered,
                                                               people):
        semver = self._version(registered, people)
        r = registered.post(f"/api/v1/models/{NAME}/versions/{semver}/approve",
                            auth=people["s.iqbal"])
        assert r.status_code == 409 and r.json()["error"] == "quorum_required"
        assert "not by one signature" in r.json()["detail"]
        # And the route it names has to be one a caller can actually POST to.
        remediation = r.json()["remediation"]
        assert "/api/v1/version-approvals" in remediation and "/sign" in remediation
        opened = registered.post("/api/v1/version-approvals", auth=people["s.iqbal"],
                                 json={"urn": URN, "semver": semver})
        assert opened.status_code == 201, "the refusal must name a real endpoint"

    def test_two_signatures_approve_it(self, registered, people):
        semver = self._version(registered, people)
        opened = registered.post("/api/v1/version-approvals",
                                 auth=people["s.iqbal"],
                                 json={"urn": URN, "semver": semver})
        assert opened.status_code == 201, opened.text
        aid = opened.json()["id"]

        first = registered.post(f"/api/v1/version-approvals/{aid}/sign",
                                auth=people["s.iqbal"],
                                json={"role": "model_risk_manager"})
        assert first.json()["status"] == "open"
        assert first.json()["outstanding_roles"] == ["validator"]

        second = registered.post(f"/api/v1/version-approvals/{aid}/sign",
                                 auth=people["a.mehta"], json={"role": "validator"})
        assert second.json()["status"] == "approved"
        listed = registered.get(f"/api/v1/models/{NAME}").json()["versions"]
        by_semver = {v["semver"]: v["status"] for v in listed}
        assert by_semver[semver] == "approved"

    def test_a_decline_returns_the_version_to_its_author(self, registered, people):
        semver = self._version(registered, people)
        aid = registered.post("/api/v1/version-approvals", auth=people["s.iqbal"],
                              json={"urn": URN, "semver": semver}).json()["id"]
        registered.post(f"/api/v1/version-approvals/{aid}/sign",
                        auth=people["s.iqbal"], json={"role": "model_risk_manager"})
        out = registered.post(f"/api/v1/version-approvals/{aid}/sign",
                              auth=people["a.mehta"],
                              json={"role": "validator", "decision": "decline",
                                    "statement": "back-testing is thin"})
        assert out.json()["status"] == "declined"
        assert "returns the version to its author" in out.json()["detail"]

    def test_a_developer_may_neither_open_nor_sign(self, registered, people):
        semver = self._version(registered, people)
        opened = registered.post("/api/v1/version-approvals",
                                 auth=people["d.raman"],
                                 json={"urn": URN, "semver": semver})
        assert opened.status_code == 403
        aid = registered.post("/api/v1/version-approvals", auth=people["s.iqbal"],
                              json={"urn": URN, "semver": semver}).json()["id"]
        r = registered.post(f"/api/v1/version-approvals/{aid}/sign",
                            auth=people["d.raman"],
                            json={"role": "model_risk_manager"})
        assert r.status_code == 403

    def test_it_says_what_this_version_needs(self, registered, people):
        semver = self._version(registered, people)
        body = registered.get("/api/v1/version-approvals",
                              params={"urn": URN, "semver": semver}).json()
        assert body["quorum_required"] and body["tier"] in (1, 2)
        assert body["required_roles"] == ["model_risk_manager", "validator"]

class TestOverlayApi:
    def test_the_overlay_kinds_are_published(self, client, people):
        body = client.get("/api/v1/overlay-kinds", auth=people["j.okafor"]).json()
        assert {k["kind"] for k in body["kinds"]} == {
            "parameter", "output", "exclusion", "judgemental"}

    def test_propose_approve_measure_and_read(self, registered, people):
        owner, mrm = people["j.okafor"], people["s.iqbal"]
        r = registered.post("/api/v1/overlays", auth=owner, json={
            "urn": URN, "name": "SME sector uplift", "kind": "output",
            "rationale": "The model under-predicts hospitality default post-2025.",
            "owner": "person/j.okafor"})
        assert r.status_code == 201
        oid = r.json()["id"]

        assert registered.post(f"/api/v1/overlays/{oid}/approve",
                               auth=mrm).status_code == 200
        assert registered.post(f"/api/v1/overlays/{oid}/measure", auth=owner, json={
            "period": "2026-Q1", "base_value": 1000000.0,
            "adjusted_value": 1180000.0}).status_code == 201

        reading = registered.get(f"/api/v1/overlays/{oid}", auth=owner).json()
        assert reading["assessment"]["materiality"]["pct_of_base"] == pytest.approx(0.18)

    def test_the_proposer_cannot_approve_over_the_api(self, registered):
        """Admin holds both permissions and is still refused: the rule is about
        the person, not the role."""
        created = registered.post("/api/v1/overlays", json={
            "urn": URN, "name": "x", "kind": "output", "rationale": "because",
            "owner": "person/o"})
        assert created.status_code == 201, created.text
        r = registered.post(f"/api/v1/overlays/{created.json()['id']}/approve")
        assert r.status_code == 403 and r.json()["error"] == "self_approval"


    def test_renewal_without_a_measurement_is_refused(self, registered, people):
        oid = registered.post("/api/v1/overlays", auth=people["j.okafor"], json={
            "urn": URN, "name": "x", "kind": "output", "rationale": "because",
            "owner": "person/o"}).json()["id"]
        registered.post(f"/api/v1/overlays/{oid}/approve", auth=people["s.iqbal"])
        r = registered.post(f"/api/v1/overlays/{oid}/renew", auth=people["s.iqbal"])
        assert r.status_code == 409 and r.json()["error"] == "unmeasured"

    def test_a_persistent_overlay_raises_a_finding(self, registered, people):
        owner, mrm = people["j.okafor"], people["s.iqbal"]
        oid = registered.post("/api/v1/overlays", auth=owner, json={
            "urn": URN, "name": "SME uplift", "kind": "output",
            "rationale": "model under-predicts", "owner": "person/o"}).json()["id"]
        registered.post(f"/api/v1/overlays/{oid}/approve", auth=mrm)
        for period in ("2026-Q1", "2026-Q2", "2026-Q3"):
            registered.post(f"/api/v1/overlays/{oid}/measure", auth=owner, json={
                "period": period, "base_value": 1000.0, "adjusted_value": 1150.0})
            registered.post(f"/api/v1/overlays/{oid}/renew", auth=mrm,
                            params={"period": period})
        found = registered.get("/api/v1/findings", params={"urn": URN}).json()
        assert any("Persistent overlay" in f["title"] for f in found["open"])

    def test_the_portfolio_answers_how_much_is_the_model(self, registered, people):
        owner, mrm = people["j.okafor"], people["s.iqbal"]
        oid = registered.post("/api/v1/overlays", auth=owner, json={
            "urn": URN, "name": "uplift", "kind": "output", "rationale": "r",
            "owner": "person/o"}).json()["id"]
        registered.post(f"/api/v1/overlays/{oid}/approve", auth=mrm)
        registered.post(f"/api/v1/overlays/{oid}/measure", auth=owner, json={
            "period": "2026-Q1", "base_value": 1000000.0, "adjusted_value": 1180000.0})
        body = registered.get("/api/v1/overlays", params={"urn": URN},
                              auth=owner).json()
        assert body["aggregate_magnitude"] == pytest.approx(180000.0)
        assert "in aggregate" in body["detail"]

    def test_overlays_render_on_the_model_page(self, registered, people):
        registered.post("/api/v1/overlays", auth=people["j.okafor"], json={
            "urn": URN, "name": "SME sector uplift", "kind": "output",
            "rationale": "r", "owner": "person/o"})
        registered.post("/login", data={"username": "admin", "password": "maya-admin-dev",
                                        "next": "/dashboard"})
        body = registered.get(f"/model/{NAME}").text
        assert "Post-model adjustments" in body and "SME sector uplift" in body

    def test_overlays_appear_in_a_compiled_document(self, registered, people):
        owner, mrm = people["j.okafor"], people["s.iqbal"]
        oid = registered.post("/api/v1/overlays", auth=owner, json={
            "urn": URN, "name": "SME uplift", "kind": "output", "rationale": "r",
            "owner": "person/o"}).json()["id"]
        registered.post(f"/api/v1/overlays/{oid}/approve", auth=mrm)
        doc = registered.post("/api/v1/documents", auth=people["a.mehta"],
                              params={"urn": URN,
                                      "kind": "model_development_document"}).json()
        text = registered.get(f"/api/v1/documents/{doc['id']}/markdown",
                              auth=people["a.mehta"]).text
        assert "## Post-model adjustments" in text
        assert "describes a model nobody runs" in text

class TestBaselineApi:
    BATCH = [{"urn": "maya://model/legacy.pd.corporate", "name": "Corporate PD",
              "owner": "person/j.okafor", "legal_entity": "LE-US-01",
              "purpose": "PD for corporate lending", "domain": "credit", "tier": 1}]

    def test_the_gap_catalogue_is_published(self, client, people):
        body = client.get("/api/v1/baseline/gaps", auth=people["d.raman"]).json()
        keys = {g["key"] for g in body["gaps"]}
        assert {"owner", "version", "tier", "validation", "monitoring"} <= keys

    def test_import_a_batch_and_read_its_debt(self, client, people):
        mrm = people["s.iqbal"]
        r = client.post("/api/v1/baseline/imports", auth=mrm, json={
            "source": "legacy-inventory.csv", "models": self.BATCH})
        assert r.status_code == 201
        assert r.json()["models"] == 1 and r.json()["debt_items"] > 0
        assert "existing use is not blocked" in r.json()["detail"]

        debt = client.get("/api/v1/baseline/debt", auth=mrm,
                          params={"urn": self.BATCH[0]["urn"]}).json()
        assert debt["baselined"] is True and debt["debt_open"] > 0
        assert debt["breached"] == 0, "debt is not breach"

    def test_a_baselined_model_is_in_the_inventory(self, client, people):
        client.post("/api/v1/baseline/imports", auth=people["s.iqbal"], json={
            "source": "csv", "models": self.BATCH})
        listed = client.get("/api/v1/models", auth=people["s.iqbal"]).json()["models"]
        found = next(m for m in listed if m["urn"] == self.BATCH[0]["urn"])
        assert found["status"] == "baselined"

    def test_reconcile_closes_debt_when_the_evidence_arrives(self, client, people):
        mrm, dev = people["s.iqbal"], people["d.raman"]
        client.post("/api/v1/baseline/imports", auth=mrm, json={
            "source": "csv", "models": self.BATCH})
        urn = self.BATCH[0]["urn"]
        name = urn.rsplit("/", 1)[-1]
        before = client.get("/api/v1/baseline/debt", auth=mrm,
                            params={"urn": urn}).json()["debt_open"]

        client.post(f"/api/v1/models/{name}/versions", auth=dev, json={
            "semver": "1.0.0", "kernel": KERNEL, "contract": CONTRACT,
            "artifact_digest": "sha256:" + "a" * 64})
        r = client.post("/api/v1/baseline/reconcile", auth=mrm, params={"urn": urn})
        assert r.status_code == 200 and r.json()["closed"]
        after = client.get("/api/v1/baseline/debt", auth=mrm,
                           params={"urn": urn}).json()["debt_open"]
        assert after < before

    def test_the_portfolio_reports_the_burn_down(self, client, people):
        client.post("/api/v1/baseline/imports", auth=people["s.iqbal"], json={
            "source": "csv", "models": self.BATCH})
        body = client.get("/api/v1/baseline", auth=people["s.iqbal"]).json()
        assert body["models_baselined"] == 1 and "burn_down" in body

    def test_a_developer_cannot_import(self, client, people):
        r = client.post("/api/v1/baseline/imports", auth=people["d.raman"], json={
            "source": "csv", "models": self.BATCH})
        assert r.status_code == 403

class TestRegimeApi:
    def test_the_regime_catalogue_is_published(self, client, people):
        body = client.get("/api/v1/regimes", auth=people["d.raman"]).json()
        keys = {r["key"] for r in body["regimes"]}
        assert {"sr-26-2", "ss1-23", "eu-ai-act"} <= keys
        sr = next(r for r in body["regimes"] if r["key"] == "sr-26-2")
        assert sr["active"] is True
        assert all(o["citation"] for o in sr["obligations"])

    def test_each_regime_publishes_its_own_vocabulary(self, client, people):
        body = client.get("/api/v1/regimes", auth=people["d.raman"]).json()
        by_key = {r["key"]: set(r["vocabulary"]) for r in body["regimes"]}
        assert "affects_natural_persons" in by_key["eu-ai-act"]
        assert "affects_natural_persons" not in by_key["sr-26-2"]

    def test_the_satisfaction_condition_is_checkable_over_the_api(self, client,
                                                                  people):
        r = client.get("/api/v1/regimes/sr-26-2/satisfaction",
                       auth=people["d.raman"]).json()
        assert r["holds"] is True and r["checked"] > 0
        assert "invariant under translation" in r["detail"]

    def test_an_unknown_regime_is_404(self, client, people):
        r = client.get("/api/v1/regimes/atlantis/satisfaction",
                       auth=people["d.raman"])
        assert r.status_code == 404 and r.json()["error"] == "no_regime"

    def test_determinations_are_returned_per_regime_with_their_derivation(
            self, registered, people):
        body = registered.get("/api/v1/regimes/determinations",
                              params={"urn": URN}, auth=people["d.raman"]).json()
        assert body["regimes"], "activated regimes should produce verdicts"
        first = body["regimes"][0]
        assert first["read_as"], "the regime-eye view of the model must be shown"
        assert all("citation" in o for o in first["obligations"])
        assert body["core_state"]["has_version"] is True

    def test_a_developer_cannot_activate_a_regime(self, client, people):
        r = client.post("/api/v1/regimes/ss1-23/activate", auth=people["d.raman"])
        assert r.status_code == 403

    def test_regimes_render_on_the_model_page(self, registered):
        registered.post("/login", data={"username": "admin", "password": "maya-admin-dev",
                                        "next": "/dashboard"})
        body = registered.get(f"/model/{NAME}").text
        assert "Supervisory regimes" in body
        assert "sr-26-2" in body or "eu-ai-act" in body

class TestDocumentApi:
    def test_the_document_kinds_are_published(self, client, people):
        body = client.get("/api/v1/document-kinds", auth=people["d.raman"]).json()
        kinds = {k["kind"] for k in body["kinds"]}
        assert {"model_development_document", "validation_report", "model_card",
                "annex_iv"} == kinds
        assert all(k["purpose"] for k in body["kinds"])

    def test_compile_and_read_back(self, registered, people):
        r = registered.post("/api/v1/documents", auth=people["a.mehta"],
                            params={"urn": URN, "kind": "model_development_document"})
        assert r.status_code == 201
        doc = r.json()
        assert doc["citations"] and doc["sections"]

        full = registered.get(f"/api/v1/documents/{doc['id']}",
                              auth=people["a.mehta"]).json()
        assert full["citations_verified"]["sound"] is True
        assert full["staleness"]["stale"] is False

    def test_it_renders_as_markdown(self, registered, people):
        doc = registered.post("/api/v1/documents", auth=people["a.mehta"],
                              params={"urn": URN, "kind": "model_card"}).json()
        text = registered.get(f"/api/v1/documents/{doc['id']}/markdown",
                              auth=people["a.mehta"]).text
        assert text.startswith("# Model Card")
        assert "## Identity and ownership" in text

    def test_a_governance_event_makes_it_stale(self, registered, people):
        doc = registered.post("/api/v1/documents", auth=people["a.mehta"],
                              params={"urn": URN,
                                      "kind": "model_development_document"}).json()
        registered.post("/api/v1/findings", auth=people["a.mehta"], json={
            "urn": URN, "severity": "Medium", "title": "Docs stale",
            "owner": "person/j.okafor"})
        stale = registered.get(f"/api/v1/documents/{doc['id']}",
                               auth=people["a.mehta"]).json()["staleness"]
        assert stale["stale"] is True and "finding_raised" in stale["kinds_since"]

    def test_a_developer_cannot_compile(self, registered, people):
        r = registered.post("/api/v1/documents", auth=people["d.raman"],
                            params={"urn": URN, "kind": "model_card"})
        assert r.status_code == 403

    def test_an_unknown_kind_is_refused(self, registered, people):
        r = registered.post("/api/v1/documents", auth=people["a.mehta"],
                            params={"urn": URN, "kind": "poem"})
        assert r.status_code == 422 and r.json()["error"] == "unknown_document_kind"

    def test_the_document_renders_in_the_interface(self, registered, people):
        doc = registered.post("/api/v1/documents", auth=people["a.mehta"],
                              params={"urn": URN,
                                      "kind": "model_development_document"}).json()
        registered.post("/login", data={"username": "admin", "password": "maya-admin-dev",
                                        "next": "/dashboard"})
        body = registered.get(f"/document/{doc['id']}").text
        assert "Model Development Document" in body
        assert "<h2" in body, "the markdown should be rendered, not escaped"
        assert "Required sections not filled" in body or "sections" in body

    def test_the_model_page_lists_documents(self, registered, people):
        registered.post("/api/v1/documents", auth=people["a.mehta"],
                        params={"urn": URN, "kind": "model_card"})
        registered.post("/login", data={"username": "admin", "password": "maya-admin-dev",
                                        "next": "/dashboard"})
        body = registered.get(f"/model/{NAME}").text
        assert "Documentation" in body and "Model Card" in body
        assert 'id="compile-doc"' in body

class TestAttachedDocuments:
    """Uploading a document is the one place the API takes bytes rather than
    JSON, and the one place a second person's signature is on a file."""

    MDD = "# SB PD — Model Development Document\n\nLogistic regression.\n".encode()

    def _upload(self, client, auth, data=None, **fields):
        form = {"urn": URN, "kind": "model_development_document",
                "title": "SB PD MDD", **fields}
        return client.post("/api/v1/attachments", auth=auth, data=form,
                           files={"file": ("mdd.md", data or self.MDD,
                                           "text/markdown")})

    def test_an_owner_can_file_a_document(self, registered, people):
        r = self._upload(registered, people["j.okafor"])
        assert r.status_code == 201, r.text
        assert r.json()["state"] == "attached"
        assert r.json()["digest"].startswith("sha256:")

    def test_a_validator_may_not_file_one(self, registered, people):
        """Filing and accepting are different duties, held by different people."""
        assert self._upload(registered, people["a.mehta"]).status_code == 403

    def test_the_author_cannot_accept_their_own(self, registered, people):
        """Two independent lines. The role check already stops an owner, who
        holds no review permission; this asserts the register refuses even a
        principal whose role would otherwise let them through."""
        admin = ("admin", "maya-admin-dev")
        attachment = self._upload(registered, admin).json()
        r = registered.post(f"/api/v1/attachments/{attachment['id']}/review",
                            auth=admin, json={"accept": True})
        assert r.status_code == 403 and r.json()["error"] == "self_review"

    def test_an_owner_holds_no_review_permission_at_all(self, registered, people):
        attachment = self._upload(registered, people["j.okafor"]).json()
        r = registered.post(f"/api/v1/attachments/{attachment['id']}/review",
                            auth=people["j.okafor"], json={"accept": True})
        assert r.status_code == 403 and r.json()["error"] == "forbidden"

    def test_a_reviewer_can_accept_it(self, registered, people):
        attachment = self._upload(registered, people["j.okafor"]).json()
        r = registered.post(f"/api/v1/attachments/{attachment['id']}/review",
                            auth=people["a.mehta"],
                            json={"accept": True, "note": "complete"})
        assert r.status_code == 200 and r.json()["state"] == "accepted"

    def test_rejecting_without_a_reason_is_refused(self, registered, people):
        attachment = self._upload(registered, people["j.okafor"]).json()
        r = registered.post(f"/api/v1/attachments/{attachment['id']}/review",
                            auth=people["a.mehta"], json={"accept": False})
        assert r.status_code == 422 and r.json()["error"] == "reason_required"

    def test_the_bytes_come_back_unchanged(self, registered, people):
        attachment = self._upload(registered, people["j.okafor"]).json()
        r = registered.get(f"/api/v1/attachments/{attachment['id']}/content")
        assert r.status_code == 200 and r.content == self.MDD
        assert "mdd.md" in r.headers["content-disposition"]

    def test_the_register_reports_what_is_on_file(self, registered, people):
        self._upload(registered, people["j.okafor"])
        body = registered.get(f"/api/v1/attachments?urn={URN}").json()
        assert body["attached"] == 1 and body["awaiting_review"] == 1
        assert body["attachments"][0]["title"] == "SB PD MDD"

    def test_an_unknown_kind_is_refused_with_the_list(self, registered, people):
        r = self._upload(registered, people["j.okafor"], kind="vibes")
        assert r.status_code == 422 and r.json()["error"] == "unknown_kind"

    def test_the_kinds_are_published_with_what_they_mean(self, registered):
        kinds = registered.get("/api/v1/attachment-kinds").json()["kinds"]
        assert any(k["kind"] == "validation_report" and k["means"] for k in kinds)

    def test_a_rejected_document_is_still_in_the_history(self, registered, people):
        attachment = self._upload(registered, people["j.okafor"]).json()
        registered.post(f"/api/v1/attachments/{attachment['id']}/review",
                        auth=people["a.mehta"],
                        json={"accept": False, "note": "no back-testing"})
        history = registered.get(
            f"/api/v1/attachments?urn={URN}&history=true").json()["attachments"]
        assert [a["state"] for a in history] == ["rejected"]

    def test_the_model_page_shows_the_register(self, registered, people):
        self._upload(registered, people["j.okafor"])
        _login(registered)
        page = registered.get(f"/model/{NAME}").text
        assert "SB PD MDD" in page and "awaiting review" in page


class TestRaisingTheTierReconsidersWhatWasApprovedBeneathIt:
    """The first line sets the tier, and raising it used to unwind nothing.

    A tier is not a label on a model; it is the size of the quorum every
    version of it has to pass. So a model assessed Tier 4, approved on one
    signature, and then honestly reassessed to Tier 1 went on serving from
    `prod/champion` while the platform simultaneously reported
    `quorum_required: true, required_roles: [model_risk_manager, validator]`.
    No finding, no reopening — the record said the control applied and the
    version had never been through it.

    Recorded as a BLOCKING finding rather than by tearing up the approval:
    unwinding it silently would strand a live model with no trace, and the
    people who granted it are the ones who have to be told. Blocking is what
    makes it stop an alias move to production.
    """

    LOW = {"exposure": 1_000, "purpose_class": "commercial", "feature_count": 3,
           "uses_alternative_data": False, "interpretable": True}
    HIGH = {"exposure": 2e9, "purpose_class": "regulatory_capital",
            "feature_count": 300, "uses_alternative_data": True,
            "interpretable": False}

    def _model_at_tier_four(self, client, people):
        owner, dev = people["j.okafor"], people["d.raman"]
        client.post("/api/v1/models", auth=owner, json={
            "urn": URN, "name": "SB PD", "model_class": "credit.pd.scorecard",
            "domain": "credit", "owner": "person/j.okafor",
            "legal_entity": "LE-US-01", "purpose": "12-month PD"})
        # The version first: the tier reads the trainability class off it, and
        # an assessment with no version to read is refused rather than tiered
        # as T0.
        client.post(f"/api/v1/models/{NAME}/versions", auth=dev,
                    json={"semver": "1.0.0", "kernel": KERNEL,
                          "contract": CONTRACT,
                          "artifact_digest": "sha256:" + "a" * 64})
        low = client.post(f"/api/v1/models/{NAME}/assess", auth=owner,
                          json=self.LOW)
        assert low.json()["tier"] == 4, low.text
        # Tier 4 needs no quorum: one authorised person approves it.
        approved = client.post(
            f"/api/v1/models/{NAME}/versions/1.0.0/approve",
            auth=people["s.iqbal"])
        assert approved.status_code == 200, approved.text
        return client

    def test_the_rise_names_the_versions_approved_beneath_it(self, client, people):
        self._model_at_tier_four(client, people)
        risen = client.post(f"/api/v1/models/{NAME}/assess",
                            auth=people["j.okafor"], json=self.HIGH)
        assert risen.status_code == 200, risen.text
        body = risen.json()
        assert body["tier"] < 4 and body["previous_tier"] == 4
        assert body["approvals_below_quorum"] == ["1.0.0"], \
            "a version approved on one signature does not meet a tier 1 quorum"

    def test_the_rise_raises_a_blocking_finding(self, client, people):
        self._model_at_tier_four(client, people)
        client.post(f"/api/v1/models/{NAME}/assess", auth=people["j.okafor"],
                    json=self.HIGH)
        body = client.get("/api/v1/findings", params={"urn": URN}).json()
        raised = [f for f in body["open"] if "tier raised" in f["title"]]
        assert raised, f"no finding was raised: {body['open']}"
        assert raised[0]["blocking"], \
            "a non-blocking finding would let the alias move go through"
        assert "1.0.0" in raised[0]["description"]
        # And it must be in the BLOCKING set, which is what stops an alias move.
        assert any("tier raised" in f["title"] for f in body["blocking"])

    def test_a_tier_that_does_not_rise_raises_nothing(self, client, people):
        """The guard must not fire on a reassessment that changes nothing."""
        self._model_at_tier_four(client, people)
        # Same facts as the first assessment, so the reassessment has to say
        # what was examined — re-running the formula on unchanged facts moves
        # the review date without anything having been reviewed.
        again = client.post(f"/api/v1/models/{NAME}/assess",
                            auth=people["j.okafor"],
                            json={**self.LOW,
                                  "review_note": "periodic review; nothing "
                                                 "about the model or its "
                                                 "exposure has moved"})
        assert again.status_code == 200, again.text
        assert again.json()["approvals_below_quorum"] == []
