"""
MAYA — Running the platform: monitoring, schedule, notification and gates.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.

What happens without anybody logging in -- monitors evaluated, jobs run,
digests delivered -- plus the versioned policy gates that decide whether a
governance act is allowed, and the machine assistance that is always
gated by one.

The application, the four principals and a registered model come from
``conftest``; ``quorum_approve`` and ``login`` from ``api_helpers``. Everything
here runs against the real app over HTTP, because an interface tested through a
shortcut is an interface nobody has tested.
"""


from tests.conftest import NAME, URN


class TestMonitoringApi:
    def test_the_monitor_kinds_are_published_with_their_tests(self, client, people):
        body = client.get("/api/v1/monitor-kinds", auth=people["d.raman"]).json()
        kinds = {k["kind"]: k for k in body["kinds"]}
        assert kinds["input_drift"]["tests"] == ["stability.psi"]
        assert kinds["performance"]["needs_labels"] is True
        assert kinds["score_drift"]["needs_labels"] is False

    def test_define_and_evaluate_a_drift_monitor(self, registered, people):
        owner = people["j.okafor"]
        r = registered.post("/api/v1/monitors", auth=owner, json={
            "urn": URN, "name": "score drift", "kind": "score_drift",
            "test_key": "stability.psi", "threshold": {"max": 0.25},
            "owner": "person/j.okafor"})
        assert r.status_code == 201
        mid = r.json()["id"]

        reference = [i / 100 for i in range(100)]
        rows = [{"scored_at": 1.8e9, "score": i / 100} for i in range(100)]
        out = registered.post(f"/api/v1/monitors/{mid}/evaluate", auth=owner,
                              json={"rows": rows, "reference": reference,
                                    "now": 1.8e9}).json()
        assert out["observation"]["passed"] is True and out["breach"] is None

    def test_a_performance_monitor_refuses_an_immature_cohort(self, registered, people):
        owner = people["j.okafor"]
        mid = registered.post("/api/v1/monitors", auth=owner, json={
            "urn": URN, "name": "gini", "kind": "performance",
            "test_key": "discrimination.gini", "threshold": {"min": 0.4},
            "owner": "person/j.okafor", "label_delay_days": 365}).json()["id"]
        rows = [{"scored_at": 1.8e9, "score": i / 20, "label": i % 2}
                for i in range(20)]
        r = registered.post(f"/api/v1/monitors/{mid}/evaluate", auth=owner,
                            json={"rows": rows, "now": 1.8e9 + 86400})
        assert r.status_code == 409
        assert r.json()["error"] == "cohort_immature"
        assert "wait for the outcome window" in r.json()["remediation"]

    def test_a_breach_becomes_a_finding_visible_on_the_model(self, registered, people):
        owner = people["j.okafor"]
        mid = registered.post("/api/v1/monitors", auth=owner, json={
            "urn": URN, "name": "score drift", "kind": "score_drift",
            "test_key": "stability.psi", "threshold": {"max": 0.1},
            "owner": "person/j.okafor", "breach_severity": "Critical"}).json()["id"]
        registered.post(f"/api/v1/monitors/{mid}/evaluate", auth=owner, json={
            "rows": [{"scored_at": 1.8e9, "score": 0.99} for _ in range(100)],
            "reference": [i / 100 for i in range(100)], "now": 1.8e9})

        findings = registered.get("/api/v1/findings", params={"urn": URN}).json()
        assert findings["summary"]["blocking"] == 1
        assert findings["blocking"][0]["source"] == "monitoring"

        # ...and the model is now unservable.
        r = registered.post("/api/v1/resolve", json={
            "urn": f"{URN}#champion", "environment": "prod",
            "principal": "svc/origination", "declared_use": "origination_decision"})
        assert r.status_code == 423 and r.json()["error"] == "blocked"

    def test_a_developer_cannot_define_a_monitor(self, registered, people):
        r = registered.post("/api/v1/monitors", auth=people["d.raman"], json={
            "urn": URN, "name": "x", "kind": "score_drift",
            "test_key": "stability.psi", "threshold": {"max": 0.25}, "owner": "o"})
        assert r.status_code == 403

    def test_an_inadmissible_test_is_refused_at_definition(self, registered, people):
        r = registered.post("/api/v1/monitors", auth=people["j.okafor"], json={
            "urn": URN, "name": "x", "kind": "input_drift",
            "test_key": "discrimination.gini", "threshold": {"min": 0.4},
            "owner": "o"})
        assert r.status_code == 422
        assert r.json()["error"] == "test_not_admissible"

    def test_monitoring_renders_on_the_model_page(self, registered, people):
        registered.post("/api/v1/monitors", auth=people["j.okafor"], json={
            "urn": URN, "name": "score drift", "kind": "score_drift",
            "test_key": "stability.psi", "threshold": {"max": 0.25}, "owner": "o"})
        registered.post("/login", data={"username": "admin", "password": "maya-admin-dev",
                                        "next": "/dashboard"})
        body = registered.get(f"/model/{NAME}").text
        assert "Monitoring" in body and "score drift" in body
        assert "stability.psi" in body

class TestSchedulerApi:
    def test_the_job_catalogue_is_published_with_reasons(self, client, people):
        body = client.get("/api/v1/scheduler", auth=people["d.raman"]).json()
        keys = {j["job"] for j in body["jobs"]}
        assert {"attestation.lapsed", "monitoring.stalled", "overlays.expire",
                # A waiver that expired and that nothing marked expired reads
                # on every screen exactly like one still in force, so
                # mandatory expiry needs something that acts on the date.
                "waivers.expire",
                # Off-label use is a PATTERN of individually authorised
                # calls, so nothing sees it at the moment any one of
                # them is made.
                "uses.reconcile",
                # Every other monitor points at a model's scores, which
                # is the last place a data problem shows up.
                "pipelines.check",
                # Materiality was declared once, and a declaration goes
                # stale quietly.
                "immaterial.conditions",
                # No other control here watches the clock on a governance
                # queue: the submission succeeded and every gate passed, so a
                # record sitting submitted for four months appears nowhere.
                "lifecycle.stalled",
                # Detection that only ran when somebody asked for a draft
                # would miss the row nobody has drafted about yet, which is
                # exactly the row an attacker would choose.
                "assist.injection",
                # A hosted model is rolled forward while the string it answers
                # to stays the same, and nobody is told.
                "assist.canaries",
                # Expiry is derived on every read, but a row still saying open
                # three weeks later reads like an elevation somebody left on.
                "break_glass.expire",
                # Otherwise the table becomes a permanent copy of every
                # successful response somebody asked to be able to retry.
                "idempotency.sweep",
                # The one place where deleting is correct: this table holds
                # somebody else's personal data.
                "inference.expire",
                # A governance act must not fail because somebody's webhook
                # receiver is down.
                "events.deliver",
                # A T4 has no version bump, so every other control here — all
                # of which fire on a version — is blind to it moving.
                "adaptive.change",
                # A sweep that runs and is never triaged is worse than no
                # sweep: the estate believes it has a discovery programme.
                "discovery.backlog",
                "debt.reconcile", "findings.overdue", "findings.unacknowledged",
                "notify.outstanding",
                # Readiness only checks what arrived since the last full walk,
                # so the full walk has to be something that happens.
                "evidence.verify",
                # And the full walk compares the chain against itself, which is
                # what a rewritten chain passes — so the head is also written
                # somewhere the database cannot reach.
                "evidence.anchor",
                # `next_review_due` was computed from the tier onto every
                # assessment and read by nothing at all — no job, no screen, no
                # endpoint — so a Tier 1 model could go four years unreviewed
                # with every other control green.
                "review.overdue"} == keys
        assert all(j["what"] and j["why"] for j in body["jobs"])
        assert body["health"]["ever_run"] == 0

    def test_a_run_is_an_ordinary_authenticated_call(self, registered):
        """Cron, a CronJob, or a person — all the same endpoint."""
        r = registered.post("/api/v1/scheduler/run", json={})
        assert r.status_code == 200
        from core.scheduler.jobs import JOBS
        assert r.json()["ran"] == len(JOBS) and r.json()["failed"] == 0

    def test_running_the_same_job_twice_changes_nothing_more(self, registered):
        first = registered.post("/api/v1/scheduler/run",
                                json={"jobs": ["overlays.expire"]}).json()
        second = registered.post("/api/v1/scheduler/run",
                                 json={"jobs": ["overlays.expire"]}).json()
        assert first["results"][0]["outcome"] == second["results"][0]["outcome"]

    def test_an_unknown_job_is_refused(self, registered):
        r = registered.post("/api/v1/scheduler/run", json={"jobs": ["nonsense"]})
        assert r.status_code == 422 and r.json()["error"] == "unknown_job"

    def test_a_developer_cannot_run_the_schedule(self, registered, people):
        r = registered.post("/api/v1/scheduler/run", auth=people["d.raman"],
                            json={})
        assert r.status_code == 403

    def test_history_records_what_ran(self, registered):
        registered.post("/api/v1/scheduler/run", json={})
        from core.scheduler.jobs import JOBS
        runs = registered.get("/api/v1/scheduler/history").json()["runs"]
        assert len(runs) == len(JOBS) and all(r["ok"] for r in runs)

    def test_readiness_reports_the_scheduler_without_failing_on_it(self, client):
        """A stopped scheduler is worth knowing about and is not a reason to
        take the node out of service."""
        body = client.get("/health/ready")
        assert body.status_code == 200
        assert "scheduler" in body.json()
        assert body.json()["scheduler"]["detail"]

    def test_the_loop_is_off_unless_configured_on(self, client, people):
        body = client.get("/api/v1/scheduler", auth=people["d.raman"]).json()
        assert body["loop_running"] is False

class TestNotificationOverTheApi:
    def test_the_channels_are_published_with_what_they_need(self, registered):
        body = registered.get("/api/v1/notifications").json()
        by_channel = {c["channel"]: c for c in body["channels"]}
        assert by_channel["log"]["usable"], "the log channel is always available"
        assert not by_channel["email"]["usable"]
        assert "notifications.email.host" in by_channel["email"]["unavailable_because"]

    def test_a_preview_shows_what_you_would_receive(self, registered, people):
        registered.post("/api/v1/findings", auth=people["s.iqbal"], json={
            "urn": URN, "severity": "Critical", "title": "Leakage",
            "owner": "person/j.okafor"})
        body = registered.get("/api/v1/notifications/preview",
                              auth=people["a.mehta"]).json()
        assert body["principal"] == "a.mehta"
        assert body["footer"]

    def test_a_dry_run_sends_nothing(self, registered):
        out = registered.post("/api/v1/notifications/run",
                              json={"dry_run": True}).json()
        assert out["dry_run"] and out["sent"] == 0
        assert registered.get("/api/v1/notifications/history"
                              ).json()["deliveries"] == []

    def test_a_run_notifies_and_then_goes_quiet(self, registered, people):
        registered.post("/api/v1/findings", auth=people["s.iqbal"], json={
            "urn": URN, "severity": "Critical", "title": "Leakage",
            "owner": "person/j.okafor"})
        first = registered.post("/api/v1/notifications/run", json={}).json()
        assert first["sent"] >= 1
        again = registered.post("/api/v1/notifications/run", json={}).json()
        assert again["sent"] == 0 and again["suppressed"] >= 1

    def test_an_unknown_channel_is_refused(self, registered):
        r = registered.post("/api/v1/notifications/run",
                            json={"channel": "smoke_signal"})
        assert r.status_code == 422 and r.json()["error"] == "unknown_channel"

    def test_a_developer_cannot_notify_the_estate(self, registered, people):
        r = registered.post("/api/v1/notifications/run", auth=people["d.raman"],
                            json={})
        assert r.status_code == 403

    def test_the_scheduler_runs_it(self, registered):
        out = registered.post("/api/v1/scheduler/run",
                              json={"jobs": ["notify.outstanding"]}).json()
        assert out["ran"] == 1 and out["failed"] == 0
        assert "detail" in out["results"][0]["outcome"]

class TestVersionedGatesOverTheApi:
    CASES = [{"name": "no blocking findings", "expect": "allow",
              "facts": {"blocking_findings": 0, "tier": 1}},
             {"name": "a blocking finding stops it", "expect": "refuse",
              "facts": {"blocking_findings": 1, "tier": 1}}]

    def test_the_gates_are_published_with_their_facts(self, registered):
        body = registered.get("/api/v1/policies").json()
        gates = {g["gate"]: g for g in body["gates"]}
        assert set(gates) == {"version:approve", "alias:move", "model:mutate",
                              "warrant:resolve"}
        assert all(g["source"] == "built-in" for g in gates.values())
        assert "never instead of them" in body["applies"]
        assert "predicate, not a program" in body["language"]["excluded"]

    def test_the_facts_a_gate_publishes_are_listed(self, registered):
        body = registered.get("/api/v1/policies/facts/alias:move").json()
        assert "refinement_holds" in body["vocabulary"]
        assert all(f["means"] for f in body["facts"])

    def test_a_rule_reading_an_unpublished_fact_is_refused_when_written(
            self, registered, people):
        r = registered.post("/api/v1/policies", auth=people["a.mehta"], json={
            "gate": "version:approve", "rule": "phase_of_the_moon == 'full'",
            "reason": "x", "cases": self.CASES})
        assert r.status_code == 422 and r.json()["error"] == "unknown_fact"

    def test_a_policy_that_refuses_nothing_is_refused(self, registered, people):
        r = registered.post("/api/v1/policies", auth=people["a.mehta"], json={
            "gate": "version:approve", "rule": "True", "reason": "x",
            "cases": [{"name": "a", "expect": "allow", "facts": {}},
                      {"name": "b", "expect": "allow", "facts": {"tier": 1}}]})
        assert r.status_code == 422 and r.json()["error"] == "no_refusing_case"

    def test_authoring_and_publishing_are_separate_duties(self, registered,
                                                          people):
        """A rule authored and enacted by one person is a rule nobody reviewed."""
        drafted = registered.post("/api/v1/policies", auth=people["a.mehta"],
                                  json={"gate": "version:approve",
                                        "rule": "blocking_findings == 0",
                                        "reason": "as shipped",
                                        "cases": self.CASES})
        assert drafted.status_code == 201, drafted.text
        refused = registered.post(
            f"/api/v1/policies/{drafted.json()['id']}/publish",
            auth=people["a.mehta"])
        assert refused.status_code == 403, "a validator drafts and does not publish"
        published = registered.post(
            f"/api/v1/policies/{drafted.json()['id']}/publish",
            auth=people["s.iqbal"])
        assert published.status_code == 200

    def test_a_published_policy_tightens_a_real_gate(self, registered, people):
        """Wired where the application wires it, refusing the way it does."""
        drafted = registered.post("/api/v1/policies", auth=people["a.mehta"],
                                  json={
            "gate": "warrant:resolve", "rule": "environment != 'prod'",
            "reason": "prod is frozen during the change freeze",
            "cases": [{"name": "lab is fine", "expect": "allow",
                       "facts": {"environment": "lab"}},
                      {"name": "prod is not", "expect": "refuse",
                       "facts": {"environment": "prod"}}]}).json()
        registered.post(f"/api/v1/policies/{drafted['id']}/publish",
                        auth=people["s.iqbal"])
        r = registered.post("/api/v1/resolve", json={
            "urn": f"{URN}#champion", "environment": "prod",
            "principal": "svc/origination",
            "declared_use": "origination_decision"})
        assert r.status_code == 403
        assert "change freeze" in r.json()["detail"]

    def test_loosening_is_reported_case_by_case(self, registered, people):
        first = registered.post("/api/v1/policies", auth=people["a.mehta"],
                                json={"gate": "version:approve",
                                      "rule": "blocking_findings == 0",
                                      "reason": "as shipped",
                                      "cases": self.CASES}).json()
        registered.post(f"/api/v1/policies/{first['id']}/publish",
                        auth=people["s.iqbal"])
        second = registered.post("/api/v1/policies", auth=people["a.mehta"],
                                 json={
            "gate": "version:approve", "rule": "tier is not None",
            "reason": "deliberately looser",
            "cases": [{"name": "tiered", "expect": "allow", "facts": {"tier": 1}},
                      {"name": "untiered", "expect": "refuse",
                       "facts": {"tier": None}}]}).json()
        out = registered.post(f"/api/v1/policies/{second['id']}/publish",
                              auth=people["s.iqbal"]).json()
        assert out["drift"]["loosened"]
        assert "are now permitted" in out["drift"]["detail"]

    def test_a_verdict_can_be_asked_for_without_making_a_decision(self,
                                                                  registered):
        body = registered.post("/api/v1/policies/try", json={
            "gate": "model:mutate", "facts": {"attested": True}}).json()
        assert body["decision"] == "refuse"
        assert body["policy_source"] == "built-in"
        assert body["facts_read"] == {"attested": True, "amending": False}

    def test_a_developer_may_not_author_a_gate(self, registered, people):
        r = registered.post("/api/v1/policies", auth=people["d.raman"], json={
            "gate": "version:approve", "rule": "blocking_findings == 0",
            "reason": "x", "cases": self.CASES})
        assert r.status_code == 403

class TestAssistApi:
    def test_the_tiers_and_oracles_are_published(self, client, people):
        body = client.get("/api/v1/assist/tiers", auth=people["d.raman"]).json()
        assert {t["tier"] for t in body["tiers"]} == {"A", "B"}
        assert body["oracles"] and "chat window" in body["note"]

    def test_register_a_grounded_capability_and_generate(self, registered, people):
        mrm, val = people["s.iqbal"], people["a.mehta"]
        r = registered.post("/api/v1/assist/capabilities", auth=mrm, json={
            "capability_key": "doc.draft", "description": "drafts doc sections",
            "tier": "B", "base_model": "claude-opus-5",
            "prompt_digest": "sha256:p", "owner": "person/a.mehta"})
        assert r.status_code == 201

        chain = registered.get("/api/v1/models/" + NAME).json()
        ids = [n["id"] for n in chain["evidence"]][:2]
        g = registered.post("/api/v1/assist/generations", auth=val, json={
            "capability_key": "doc.draft", "subject_type": "model",
            "subject_id": chain["model"]["id"],
            "claims": [{"id": "c1", "text": "Registered in 2026.",
                        "citations": ids[:1]},
                       {"id": "c2", "text": "Invented.", "citations": ["ghost"]}],
            "known_evidence": ids})
        assert g.status_code == 201
        body = g.json()
        assert body["output"]["grounding"]["rejected"] == 1
        assert "Invented." not in body["output"]["text"], \
            "an ungrounded claim must not reach the output"

    def test_tier_c_is_refused_over_the_api(self, registered, people):
        r = registered.post("/api/v1/assist/capabilities", auth=people["s.iqbal"],
                            json={"capability_key": "hunch", "description": "d",
                                  "tier": "C", "base_model": "m",
                                  "prompt_digest": "p", "owner": "o"})
        assert r.status_code == 422
        assert r.json()["error"] == "advisory_not_registrable"

    def test_tier_a_without_an_oracle_is_refused(self, registered, people):
        r = registered.post("/api/v1/assist/capabilities", auth=people["s.iqbal"],
                            json={"capability_key": "x", "description": "d",
                                  "tier": "A", "base_model": "m",
                                  "prompt_digest": "p", "owner": "o"})
        assert r.status_code == 422 and r.json()["error"] == "oracle_required"

    def test_the_requester_cannot_attest_their_own_generation(self, registered,
                                                              people):
        mrm, val = people["s.iqbal"], people["a.mehta"]
        registered.post("/api/v1/assist/capabilities", auth=mrm, json={
            "capability_key": "doc.draft", "description": "d", "tier": "B",
            "base_model": "m", "prompt_digest": "p", "owner": "o"})
        model = registered.get("/api/v1/models/" + NAME).json()
        ids = [n["id"] for n in model["evidence"]][:1]
        gid = registered.post("/api/v1/assist/generations", auth=val, json={
            "capability_key": "doc.draft", "subject_type": "model",
            "subject_id": model["model"]["id"],
            "claims": [{"id": "c", "text": "Registered.", "citations": ids}],
            "known_evidence": ids}).json()["id"]

        r = registered.post(f"/api/v1/assist/generations/{gid}/attest", auth=val,
                            json={"accept": True})
        assert r.status_code == 403 and r.json()["error"] == "self_attestation"

        ok = registered.post(f"/api/v1/assist/generations/{gid}/attest", auth=mrm,
                             json={"accept": True, "final_text": "Registered."})
        assert ok.status_code == 200 and ok.json()["state"] == "attested"

    def test_there_is_no_endpoint_that_decides_from_a_generation(self, client):
        """The absence is the control: a draft becomes consequential only when a
        person attests it."""
        paths = client.get("/api/v1/openapi.json").json()["paths"]
        assist = [p for p in paths if "/assist/" in p]
        assert assist, "the assistance surface should exist"
        for path in assist:
            assert "approve" not in path and "conclude" not in path


class TestDraftingOverTheApi:
    """MAYA can now ask a model, and still does not believe what it says.

    The generation log could always gate a draft; nothing ever asked for one, so
    every control around it had only been exercised against claims a test wrote
    by hand.
    """

    def _capability(self, client, people, key="validation_summary"):
        return client.post("/api/v1/assist/capabilities", auth=people["s.iqbal"],
                           json={"capability_key": key, "tier": "B",
                                 "description": "Draft a summary from the record",
                                 "base_model": "mock-1",
                                 "prompt_digest": "sha256:prompt",
                                 "owner": "person/a.mehta", "review_sample": 0.0})

    def test_the_page_says_which_provider_can_be_asked_and_why_not_the_rest(
            self, registered, people):
        body = registered.get("/api/v1/assist/providers",
                              auth=people["a.mehta"]).json()
        rows = {r["provider"]: r for r in body["providers"]}
        assert rows["mock"]["usable"] is True
        assert rows["anthropic"]["usable"] is False and rows["anthropic"]["why_not"]
        assert body["in_force"]["provider"] == "mock"

    def test_a_draft_is_grounded_in_the_record_and_needs_attesting(
            self, registered, people):
        assert self._capability(registered, people).status_code == 201
        r = registered.post("/api/v1/assist/drafts", auth=people["a.mehta"],
                            json={"capability_key": "validation_summary",
                                  "subject_type": "model",
                                  "subject_id": registered.get(
                                      f"/api/v1/models/{NAME}",
                                      auth=people["a.mehta"]).json()["model"]["id"]})
        assert r.status_code == 201, r.text
        drafted = r.json()
        assert drafted["state"] == "drafted"
        assert drafted["claims"], "a draft with no grounded claim is not a draft"
        assert drafted["output"]["grounding"]["rejected"] == 0

    def test_drafting_about_a_subject_with_no_record_is_refused_by_name(
            self, registered, people):
        self._capability(registered, people)
        r = registered.post("/api/v1/assist/drafts", auth=people["a.mehta"],
                            json={"capability_key": "validation_summary",
                                  "subject_type": "model",
                                  "subject_id": "never-heard-of-it"})
        assert r.status_code == 422
        assert r.json()["error"] == "nothing_to_ground"
