"""
MAYA — Features, featuresets and the parameter object over HTTP.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.

Two of the three letters in f : P x X -> D(Y), and the path between them:
composition and its policies, bulk transfer at a size worth measuring, the
fit warrant's schema check, and the fit itself.

The application, the four principals and a registered model come from
``conftest``; ``quorum_approve`` and ``login`` from ``api_helpers``. Everything
here runs against the real app over HTTP, because an interface tested through a
shortcut is an interface nobody has tested.
"""
import json

import pytest

from tests.api_helpers import login as _login, quorum_approve as _quorum_approve
from tests.conftest import CONTRACT, KERNEL, NAME, URN


class TestFeaturesetsAndParameters:
    """The cycle: name a presentation of X, fit under a warrant, take delivery
    of a point in P, and have somebody else approve it before anything runs."""

    def _catalogue(self, client, auth):
        for name, dtype in [("living_area_sqft", "numeric"),
                            ("bedrooms", "integer"), ("sale_price", "numeric")]:
            client.post("/api/v1/features", auth=auth, json={
                "name": name, "entity": "property_id", "dtype": dtype,
                "description": f"NJ {name}", "owner": "person/j.okafor"})

    def _derived(self, client, auth, name="log_living_area",
                 expression="log(living_area_sqft)"):
        return client.post("/api/v1/derived-features", auth=auth, json={
            "name": name, "expression": expression, "dtype": "numeric",
            "description": "log of heated floor area"})

    def test_the_expression_language_is_published(self, registered):
        body = registered.get("/api/v1/expression-language").json()
        assert any(f["name"] == "log" for f in body["functions"])
        assert "external" in body["excluded"]

    def test_a_developer_can_declare_a_derived_feature(self, registered, people):
        self._catalogue(registered, people["d.raman"])
        r = self._derived(registered, people["d.raman"])
        assert r.status_code == 201, r.text
        assert r.json()["inputs"] == ["living_area_sqft"]

    def test_an_expression_outside_the_language_is_refused(self, registered, people):
        self._catalogue(registered, people["d.raman"])
        r = self._derived(registered, people["d.raman"], "evil",
                          "__import__('os').system('ls')")
        assert r.status_code == 409 and r.json()["error"] == "feature_refused"
        assert "not one of the functions" in r.json()["detail"]

    def test_lineage_answers_both_directions(self, registered, people):
        self._catalogue(registered, people["d.raman"])
        self._derived(registered, people["d.raman"])
        body = registered.get(
            "/api/v1/derived-features/log_living_area/lineage").json()
        assert body["rests_on"] == ["living_area_sqft"]
        assert registered.get(
            "/api/v1/derived-features/living_area_sqft/lineage"
        ).json()["depended_on_by"] == ["log_living_area"]

    def _featureset(self, client, auth):
        self._catalogue(client, auth)
        client.post("/api/v1/feature-views", auth=auth, json={
            "name": "nj_characteristics", "entity": "property_id",
            "owner": "person/j.okafor",
            "features": ["living_area_sqft", "bedrooms"]})
        client.post("/api/v1/feature-views/nj_characteristics/materialise",
                    auth=auth, json={"rows": [
                        {"entity_id": "P1", "event_ts": 1717200000.0,
                         "ingest_ts": 1717200000.0,
                         "living_area_sqft": 1800.0, "bedrooms": 3}]})
        return client.post("/api/v1/featuresets", auth=auth, json={
            "name": "nj_home_core", "entity": "property_id",
            "slots": {"living_area_sqft": "numeric", "bedrooms": "integer"}})

    def test_a_featureset_declares_a_schema_and_a_version_fills_it(
            self, registered, people):
        dev = people["d.raman"]
        assert self._featureset(registered, dev).status_code == 201
        r = registered.post("/api/v1/featuresets/nj_home_core/versions",
                            auth=dev, json={"bindings": {
                                "living_area_sqft": "living_area_sqft",
                                "bedrooms": "bedrooms"}})
        assert r.status_code == 201, r.text
        assert r.json()["version"] == 1
        assert r.json()["bindings"]["bedrooms"]["view_version"] == 1

    def test_a_binding_naming_no_slot_is_refused(self, registered, people):
        dev = people["d.raman"]
        self._featureset(registered, dev)
        r = registered.post("/api/v1/featuresets/nj_home_core/versions",
                            auth=dev, json={"bindings": {
                                "living_area_sqft": "living_area_sqft",
                                "bedrooms": "bedrooms",
                                "sale_price": "sale_price"}})
        assert r.status_code == 409
        assert "no declared slot" in r.json()["detail"]

    def test_the_plan_carries_the_namespaces_an_engine_reads(self, registered,
                                                             people):
        dev = people["d.raman"]
        self._featureset(registered, dev)
        registered.post("/api/v1/featuresets/nj_home_core/versions", auth=dev,
                        json={"bindings": {"living_area_sqft": "living_area_sqft",
                                           "bedrooms": "bedrooms"}})
        plan = registered.get("/api/v1/featuresets/nj_home_core/versions/1").json()
        assert plan["namespaces"] == ["features/property_id/nj_characteristics/v1"]
        assert plan["pit_rule"].endswith("ingest_ts <= min(label_ts, as_of)")

    def test_a_validator_may_not_publish_a_featureset(self, registered, people):
        self._featureset(registered, people["d.raman"])
        r = registered.post("/api/v1/featuresets/nj_home_core/versions",
                            auth=people["a.mehta"], json={"bindings": {}})
        assert r.status_code == 403

    # ------------------------------------------------------------- parameters
    def _warrant(self, client, auth):
        return client.post("/api/v1/warrants", auth=auth, json={
            "urn": URN, "environment": "lab", "principal": "svc/model-lab",
            "declared_use": "model_development"}).json()

    def _record(self, client, auth, **kw):
        body = {"urn": URN, "semver": "3.2.1", "name": "sb-pd-2025q1",
                "kind": "estimated_coefficients",
                "values": {"intercept": -1.4, "turnover": 0.31},
                "provenance": "declared"}
        body.update(kw)
        return client.post("/api/v1/parameters", auth=auth, json=body)

    def test_the_provenance_routes_are_published(self, registered):
        kinds = registered.get("/api/v1/parameter-provenance").json()["provenance"]
        assert {k["kind"] for k in kinds} == {"fitted", "calibrated", "declared"}

    def test_declared_parameters_are_recorded(self, registered, people):
        r = self._record(registered, people["d.raman"])
        assert r.status_code == 201, r.text
        assert r.json()["state"] == "proposed" and r.json()["cardinality"] == 2

    def test_a_fitted_set_without_a_warrant_is_refused(self, registered, people):
        r = self._record(registered, people["d.raman"], provenance="fitted")
        assert r.status_code == 422 and r.json()["error"] == "warrant_required"

    def test_a_fitted_set_names_the_warrant_and_the_featureset(self, registered,
                                                               people):
        dev = people["d.raman"]
        self._featureset(registered, dev)
        registered.post("/api/v1/featuresets/nj_home_core/versions", auth=dev,
                        json={"bindings": {"living_area_sqft": "living_area_sqft",
                                           "bedrooms": "bedrooms"}})
        grant = self._warrant(registered, people["j.okafor"])
        r = self._record(registered, dev, provenance="fitted",
                         warrant_id=grant["id"], featureset="nj_home_core",
                         featureset_version=1, as_of=1736899200.0)
        assert r.status_code == 201, r.text
        assert r.json()["featureset_version_id"]

    def test_whoever_recorded_them_cannot_approve_them(self, registered, people):
        """Two independent lines: the role grant stops a developer, who holds no
        approval permission, and the register stops even a principal whose role
        would let them through."""
        admin = ("admin", "admin123")
        recorded = self._record(registered, admin).json()
        r = registered.post(f"/api/v1/parameter-sets/{recorded['id']}/review",
                            auth=admin, json={"accept": True})
        assert r.status_code == 403 and r.json()["error"] == "self_approval"

    def test_a_validator_can_approve_them(self, registered, people):
        recorded = self._record(registered, people["d.raman"]).json()
        r = registered.post(f"/api/v1/parameter-sets/{recorded['id']}/review",
                            auth=people["a.mehta"],
                            json={"accept": True, "note": "residuals reviewed"})
        assert r.status_code == 200 and r.json()["state"] == "approved"

    def test_an_owner_holds_no_approval_permission(self, registered, people):
        recorded = self._record(registered, people["d.raman"]).json()
        r = registered.post(f"/api/v1/parameter-sets/{recorded['id']}/review",
                            auth=people["j.okafor"], json={"accept": True})
        assert r.status_code == 403 and r.json()["error"] == "forbidden"

    def test_the_status_says_whether_the_kernel_is_ready(self, registered, people):
        body = registered.get(
            f"/api/v1/parameters?urn={URN}&semver=3.2.1").json()
        assert body["ready"] is False
        assert "cannot be run until" in body["detail"]

        recorded = self._record(registered, people["d.raman"]).json()
        registered.post(f"/api/v1/parameter-sets/{recorded['id']}/review",
                        auth=people["a.mehta"], json={"accept": True})
        after = registered.get(
            f"/api/v1/parameters?urn={URN}&semver=3.2.1").json()
        assert after["ready"] and after["approved"] == 1

    def test_the_model_page_shows_what_it_runs_on(self, registered, people):
        recorded = self._record(registered, people["d.raman"]).json()
        registered.post(f"/api/v1/parameter-sets/{recorded['id']}/review",
                        auth=people["a.mehta"], json={"accept": True})
        _login(registered)
        page = registered.get(f"/model/{NAME}").text
        assert "sb-pd-2025q1" in page and "declared" in page

class TestCompositionAndPolicyOverTheApi:
    """A feature is not always a number, is not always defined in one place, and
    does not always outlive the request that made it."""

    TENORS = ["1m", "3m", "1y", "5y", "10y"]

    def _curve(self, client, auth, name="usd_curve"):
        return client.post("/api/v1/features", auth=auth, json={
            "name": name, "entity": "book_id", "dtype": "numeric",
            "description": "USD zero curve", "owner": "person/j.okafor",
            "shape": [5], "components": self.TENORS})

    def test_a_vector_feature_reports_its_own_dimensionality(self, registered,
                                                             people):
        assert self._curve(registered, people["d.raman"]).status_code == 201
        body = registered.get("/api/v1/features/usd_curve/resolved").json()
        assert body["dimensionality"]["kind"] == "vector"
        assert body["components"] == self.TENORS, "the axis order is the order"

    def test_a_composed_feature_resolves_through_its_parents(self, registered,
                                                             people):
        dev = people["d.raman"]
        self._curve(registered, dev)
        r = registered.post("/api/v1/features", auth=dev, json={
            "name": "usd_extended", "entity": "book_id", "dtype": "numeric",
            "description": "with a 30y point", "owner": "person/j.okafor",
            "composes": [{"name": "usd_curve"}],
            "operations": [{"op": "add", "name": "30y",
                            "value": {"dtype": "numeric"}},
                           {"op": "drop", "name": "1m"}]})
        assert r.status_code == 201, r.text
        body = registered.get("/api/v1/features/usd_extended/resolved").json()
        assert "30y" in body["components"] and "1m" not in body["components"]
        assert body["lineage"][0]["name"] == "usd_curve"

    def test_an_operation_that_would_do_nothing_is_refused(self, registered,
                                                           people):
        dev = people["d.raman"]
        self._curve(registered, dev)
        r = registered.post("/api/v1/features", auth=dev, json={
            "name": "bad", "entity": "book_id", "dtype": "numeric",
            "description": "x", "owner": "person/o",
            "composes": [{"name": "usd_curve"}],
            "operations": [{"op": "drop", "name": "99y"}]})
        assert r.status_code == 409 and "cannot drop" in r.json()["detail"]

    def test_sealing_makes_it_final_and_still_composable(self, registered,
                                                         people):
        dev, mrm = people["d.raman"], people["s.iqbal"]
        self._curve(registered, dev)
        sealed = registered.post("/api/v1/features/usd_curve/seal", auth=mrm,
                                 json={"note": "signed off"})
        assert sealed.status_code == 200 and sealed.json()["sealed_by"]

        amended = registered.post("/api/v1/features/usd_curve/amend", auth=dev,
                                  json={"fields": {"description": "changed"}})
        assert amended.status_code == 409
        assert "compose a new feature from it" in amended.json()["detail"]

        child = registered.post("/api/v1/features", auth=dev, json={
            "name": "child", "entity": "book_id", "dtype": "numeric",
            "description": "x", "owner": "person/o",
            "composes": [{"name": "usd_curve"}]})
        assert child.status_code == 201, "a sealed parent is the point"

    def test_a_developer_may_not_seal(self, registered, people):
        self._curve(registered, people["d.raman"])
        r = registered.post("/api/v1/features/usd_curve/seal",
                            auth=people["d.raman"], json={})
        assert r.status_code == 403

    def test_an_ephemeral_feature_reports_its_lifetime_and_can_be_destroyed(
            self, registered, people):
        dev = people["d.raman"]
        registered.post("/api/v1/features", auth=dev, json={
            "name": "scratch", "entity": "book_id", "dtype": "numeric",
            "description": "one-off", "owner": "person/o",
            "ephemeral": True, "ttl_days": 0.5})
        body = registered.get("/api/v1/features/scratch/resolved").json()
        assert body["lifetime"]["ephemeral"]
        assert registered.delete("/api/v1/features/scratch",
                                 auth=dev).status_code == 200
        assert registered.get(
            "/api/v1/features/scratch/resolved").status_code == 409

    def test_ownership_is_two_facts_not_one(self, registered, people):
        dev = people["d.raman"]
        self._curve(registered, dev)
        registered.post("/api/v1/features/usd_curve/transfer", auth=dev,
                        json={"to": "person/a.mehta", "reason": "team move"})
        own = registered.get("/api/v1/features/usd_curve/resolved"
                             ).json()["ownership"]
        assert own["created_by"] == "d.raman" and own["owner"] == "person/a.mehta"
        assert own["transferred"]

    def test_a_featureset_inherits_slots_and_policy(self, registered, people):
        dev = people["d.raman"]
        self._curve(registered, dev)
        registered.post("/api/v1/featuresets", auth=dev, json={
            "name": "rates_core", "entity": "book_id",
            "slots": {"usd_curve": "numeric"},
            "defaults": {"normalise": {"usd_curve": "zscore"}}})
        registered.post("/api/v1/featuresets", auth=dev, json={
            "name": "rates_plus", "entity": "book_id", "slots": {},
            "composes": [{"name": "rates_core"}]})
        body = registered.get("/api/v1/featuresets/rates_plus/resolved").json()
        assert body["inherited_slots"] == ["usd_curve"]
        assert body["policy"]["policy"]["normalise"] == {"usd_curve": "zscore"}
        assert body["policy"]["decided_by"]["normalise"]["usd_curve"] == "rates_core"

    def test_the_retrieval_rules_are_published(self, registered):
        body = registered.get("/api/v1/retrieval").json()
        assert body["preparation"]["as_of_required_for"]
        assert any(r["rule"] == "flat_backward" and not r["point_in_time_safe"]
                   for r in body["alignment"]["rules"])
        assert "monoid" in body["composition"]["why"]

    def test_the_features_page_shows_shape_lineage_and_state(self, registered,
                                                             people):
        dev, mrm = people["d.raman"], people["s.iqbal"]
        self._curve(registered, dev)
        registered.post("/api/v1/features", auth=dev, json={
            "name": "usd_extended", "entity": "book_id", "dtype": "numeric",
            "description": "x", "owner": "person/o",
            "composes": [{"name": "usd_curve"}]})
        registered.post("/api/v1/features/usd_curve/seal", auth=mrm, json={})
        _login(registered)
        page = registered.get("/features").text
        assert "vector" in page and "composed" in page and "sealed" in page

class TestBulkTransfer:
    """Feature values are the one thing here that is not small."""

    def _view(self, client, auth, rows=500):
        client.post("/api/v1/features", auth=auth, json={
            "name": "dscr", "entity": "borrower_id", "dtype": "numeric",
            "description": "d", "owner": "person/j.okafor"})
        client.post("/api/v1/feature-views", auth=auth, json={
            "name": "sb_credit", "entity": "borrower_id",
            "owner": "person/j.okafor", "features": ["dscr"]})
        client.post("/api/v1/feature-views/sb_credit/materialise", auth=auth,
                    json={"rows": [{"entity_id": f"B{i}", "event_ts": float(i),
                                    "ingest_ts": float(i), "dscr": 1.0 + i}
                                   for i in range(rows)]})

    def test_the_formats_are_published(self, registered):
        body = registered.get("/api/v1/transfer").json()
        assert {f["format"] for f in body["formats"]} == {
            "arrow", "parquet", "ndjson", "json"}
        assert body["required_columns"] == ["entity_id", "event_ts", "ingest_ts"]
        assert "one batch rather than one dataset" in body["note"]

    def test_a_view_version_streams_as_parquet(self, registered, people):
        self._view(registered, people["d.raman"])
        r = registered.get(
            "/api/v1/feature-views/sb_credit/versions/1/data?format=parquet")
        assert r.status_code == 200
        assert r.headers["content-type"] == "application/vnd.apache.parquet"
        assert r.content[:4] == b"PAR1", "that is not a parquet file"
        assert "sb_credit-v1.parquet" in r.headers["content-disposition"]

    def test_it_streams_as_arrow_and_as_ndjson(self, registered, people):
        self._view(registered, people["d.raman"])
        arrow = registered.get(
            "/api/v1/feature-views/sb_credit/versions/1/data?format=arrow")
        assert arrow.status_code == 200 and len(arrow.content) > 0
        lines = registered.get(
            "/api/v1/feature-views/sb_credit/versions/1/data?format=ndjson"
        ).text.strip().splitlines()
        assert len(lines) == 500
        assert json.loads(lines[0])["entity_id"].startswith("B")

    def test_json_is_capped_and_says_so(self, registered, people):
        self._view(registered, people["d.raman"])
        body = registered.get(
            "/api/v1/feature-views/sb_credit/versions/1/data"
            "?format=json&limit=25").json()
        assert body["returned"] == 25 and body["total"] == 500
        assert body["truncated"]
        assert "ask for arrow or parquet" in body["detail"]

    def test_a_column_that_is_not_there_is_refused(self, registered, people):
        """Asking for an absent column is a different request from asking for an
        empty one, and answering the second would hide the first."""
        self._view(registered, people["d.raman"])
        r = registered.get("/api/v1/feature-views/sb_credit/versions/1/data"
                           "?format=ndjson&columns=dscr,nonexistent")
        assert r.status_code == 409

    def test_a_round_trip_preserves_every_row(self, registered, people):
        """Out as parquet, back in as parquet, and the count survives."""
        dev = people["d.raman"]
        self._view(registered, dev)
        blob = registered.get(
            "/api/v1/feature-views/sb_credit/versions/1/data?format=parquet"
        ).content
        r = registered.post("/api/v1/feature-views/sb_credit/data", auth=dev,
                            content=blob,
                            headers={"Content-Type":
                                     "application/vnd.apache.parquet"})
        assert r.status_code == 201, r.text
        assert r.json()["uploaded_rows"] == 500 and r.json()["version"] == 2

    def test_an_upload_without_both_clocks_is_refused(self, registered, people):
        """Accepting it here would move the failure two layers away from the
        upload that caused it, which is where it stops being fixable."""
        self._view(registered, people["d.raman"])
        body = json.dumps([{"entity_id": "B1", "dscr": 2.0}]).encode()
        r = registered.post("/api/v1/feature-views/sb_credit/data",
                            auth=people["d.raman"], content=body,
                            headers={"Content-Type": "application/json"})
        assert r.status_code == 409
        assert "two clocks" in r.json()["detail"]

    def test_a_body_that_is_not_what_it_claims_is_refused(self, registered,
                                                          people):
        self._view(registered, people["d.raman"])
        r = registered.post("/api/v1/feature-views/sb_credit/data",
                            auth=people["d.raman"], content=b"not parquet",
                            headers={"Content-Type":
                                     "application/vnd.apache.parquet"})
        assert r.status_code == 409
        assert "does not parse" in r.json()["detail"]

    def test_a_featureset_reports_its_parts_for_a_parallel_pull(self, registered,
                                                                people):
        dev = people["d.raman"]
        self._view(registered, dev)
        registered.post("/api/v1/featuresets", auth=dev, json={
            "name": "sb_core", "entity": "borrower_id",
            "slots": {"dscr": "numeric"}})
        registered.post("/api/v1/featuresets/sb_core/versions", auth=dev,
                        json={"bindings": {"dscr": "dscr"}})
        parts = registered.get(
            "/api/v1/featuresets/sb_core/versions/1/parts").json()
        assert parts["parts"][0]["namespace"] == \
            "features/borrower_id/sb_credit/v1"
        assert parts["parts"][0]["delta_version"] is not None
        assert "in parallel" in parts["detail"]

    def test_a_featureset_version_streams_joined(self, registered, people):
        dev = people["d.raman"]
        self._view(registered, dev)
        registered.post("/api/v1/featuresets", auth=dev, json={
            "name": "sb_core", "entity": "borrower_id",
            "slots": {"dscr": "numeric"}})
        registered.post("/api/v1/featuresets/sb_core/versions", auth=dev,
                        json={"bindings": {"dscr": "dscr"}})
        r = registered.get("/api/v1/featuresets/sb_core/versions/1/data"
                           "?format=parquet&as_of=1767139200")
        assert r.status_code == 200 and r.content[:4] == b"PAR1"

    def test_an_export_without_a_moment_is_refused(self, registered, people):
        """The join reduces each part to what was true and known at `as_of`
        before joining. Without one it paired every feature's whole history
        against every other feature's — 200 entities over 24 monthly
        observations produced 115,200 rows where 4,800 were expected."""
        dev = people["d.raman"]
        self._view(registered, dev)
        registered.post("/api/v1/featuresets", auth=dev, json={
            "name": "sb_nomoment", "entity": "borrower_id",
            "slots": {"dscr": "numeric"}})
        registered.post("/api/v1/featuresets/sb_nomoment/versions", auth=dev,
                        json={"bindings": {"dscr": "dscr"}})
        r = registered.get("/api/v1/featuresets/sb_nomoment/versions/1/data")
        assert r.status_code == 409
        assert "what moment it speaks for" in r.json()["detail"]

class TestTheFitWarrantChecksTheSchema:
    """L-W10. A featureset a warrant names must provide what the kernel reads.
    Left unchecked this is a claim, and the model is fitted over a different X
    than the one its version declares."""

    def _fittable_version(self, client, people):
        """A version MAYA can locate. L-W6 refuses to fit a descriptor-only
        model, and the shared fixture registers one — correctly."""
        # The runtime is what makes a version locatable; without one the
        # builder emits descriptor_only and L-W6 refuses to fit it, correctly.
        kernel = {**KERNEL, "runtime": "python.callable",
                  "entry": {"module": "sb.estimators", "attr": "ols_fit"}}
        client.post(f"/api/v1/models/{NAME}/versions", auth=people["d.raman"],
                    json={"semver": "3.3.0", "kernel": kernel,
                          "contract": CONTRACT,
                          "artifact_digest": "sha256:" + "d" * 64,
                          "artifact_uri": "file://sb_pd_3.3.0.onnx"})
        _quorum_approve(client, people, "3.3.0")
        client.put(f"/api/v1/models/{NAME}/aliases", auth=people["s.iqbal"],
                   json={"environment": "prod", "alias": "champion",
                         "semver": "3.3.0"})

    def _setup(self, client, auth, slots, bindings):
        for name, dtype in [("dscr", "float"), ("turnover", "float")]:
            client.post("/api/v1/features", auth=auth, json={
                "name": name, "entity": "borrower_id", "dtype": dtype,
                "description": name, "owner": "person/j.okafor"})
        client.post("/api/v1/feature-views", auth=auth, json={
            "name": "sb_credit", "entity": "borrower_id",
            "owner": "person/j.okafor", "features": ["dscr", "turnover"]})
        client.post("/api/v1/feature-views/sb_credit/materialise", auth=auth,
                    json={"rows": [{"entity_id": "B1", "event_ts": 1717200000.0,
                                    "ingest_ts": 1717200000.0,
                                    "dscr": 1.4, "turnover": 250000.0}]})
        client.post("/api/v1/featuresets", auth=auth, json={
            "name": "sb_set", "entity": "borrower_id", "slots": slots})
        return client.post("/api/v1/featuresets/sb_set/versions", auth=auth,
                           json={"bindings": bindings})

    def _fit(self, client, auth):
        # resolve_fit reads a standing grant, exactly as resolve() does: a fit is
        # an entitlement like any other, not a side door around one.
        client.post("/api/v1/warrants", auth=auth, json={
            "urn": URN, "environment": "prod", "principal": "svc/model-lab",
            "declared_use": "model_development"})
        return client.post("/api/v1/fit-warrants", auth=auth, json={
            "urn": URN, "environment": "prod", "principal": "svc/model-lab",
            "featureset": "sb_set", "featureset_version": 1,
            "window": {"from": 1546300800.0, "to": 1735603200.0},
            "as_of": 1736899200.0})

    def test_a_covering_featureset_yields_a_signed_descriptor(self, registered,
                                                              people):
        """The fixture kernel declares it reads dscr."""
        dev, owner = people["d.raman"], people["j.okafor"]
        self._fittable_version(registered, people)
        self._setup(registered, dev, {"dscr": "float"}, {"dscr": "dscr"})
        r = self._fit(registered, owner)
        assert r.status_code == 201, r.text
        doc = r.json()
        assert doc["operation"]["verb"] == "fit"
        assert doc["parameters"]["source"]["binding"] == "to_be_fitted"
        assert doc["data"]["inputs"][0]["featureset"] == "sb_set"
        assert doc["data"]["outputs"][0]["sink"] == "parameter_object"

    def test_a_featureset_missing_what_the_kernel_reads_is_refused(
            self, registered, people):
        dev, owner = people["d.raman"], people["j.okafor"]
        self._setup(registered, dev, {"turnover": "float"},
                    {"turnover": "turnover"})
        r = self._fit(registered, owner)
        assert r.status_code == 409, r.text
        assert r.json()["error"] == "schema_not_satisfied"
        assert "dscr" in r.json()["detail"]
        assert "model change, not a data change" in r.json()["remediation"]

    def test_the_descriptor_carries_the_pinned_namespaces(self, registered,
                                                          people):
        dev, owner = people["d.raman"], people["j.okafor"]
        self._fittable_version(registered, people)
        self._setup(registered, dev, {"dscr": "float"}, {"dscr": "dscr"})
        binding = self._fit(registered, owner).json()["data"]["inputs"][0]
        assert binding["namespaces"] == ["features/borrower_id/sb_credit/v1"]
        assert binding["pit_rule"].endswith("ingest_ts <= min(label_ts, as_of)")

class TestFittingOverTheApi:
    """The path a person actually walks: features, a featureset, a training set,
    a fit, and an approval by somebody else.

    Every step of this existed before and none of them had been run in sequence
    over HTTP, because the middle one did not exist. A control that only works
    when somebody hands it a hand-written dictionary is a control nobody has
    tested.
    """

    AS_OF = 1736899200.0
    EVENT = 1717200000.0
    WINDOW = {"from": 1546300800.0, "to": 1735603200.0}
    # Its own model rather than a version of the shared one. Promoting a version
    # whose input schema differs is refused by L-12, and correctly -- a fit set
    # up as a new champion of an unrelated scorecard would be testing the
    # variance rule rather than the fit.
    FIT_URN = "maya://model/credit.spend.linear"
    FIT_NAME = "credit.spend.linear"

    def _estimator_version(self, client, people):
        owner, dev, mrm = people["j.okafor"], people["d.raman"], people["s.iqbal"]
        client.post("/api/v1/models", auth=owner, json={
            "urn": self.FIT_URN, "name": "Spend linear", "domain": "credit",
            "model_class": "credit.spend.linear", "owner": "person/j.okafor",
            "legal_entity": "LE-US-01", "purpose": "expected spend"})
        client.post(f"/api/v1/models/{self.FIT_NAME}/assess", auth=owner,
                    json={"exposure": 2e9, "purpose_class": "regulatory_capital"})
        kernel = {"parameter_kind": "estimated_coefficients",
                  "fit_procedure": "estimate", "runtime": "estimator",
                  "entry": {"family": "ols", "target": "spend",
                            "regressors": ["dscr", "turnover"]},
                  "input_schema": [{"name": "dscr", "dtype": "numeric"},
                                   {"name": "turnover", "dtype": "numeric"}],
                  "output_schema": [{"name": "spend", "dtype": "numeric"}]}
        r = client.post(f"/api/v1/models/{self.FIT_NAME}/versions", auth=dev,
                        json={"semver": "1.0.0", "kernel": kernel})
        assert r.status_code == 201, r.text
        _quorum_approve(client, people, "1.0.0", urn=self.FIT_URN)
        moved = client.put(f"/api/v1/models/{self.FIT_NAME}/aliases", auth=mrm,
                           json={"environment": "prod", "alias": "champion",
                                 "semver": "1.0.0"})
        assert moved.status_code == 200, moved.text

    def _snapshot(self, client, auth):
        """spend = 5 + 2*dscr - 0.5*turnover, exactly."""
        for name in ("dscr", "turnover", "spend"):
            client.post("/api/v1/features", auth=auth, json={
                "name": name, "entity": "borrower_id", "dtype": "numeric",
                "description": name, "owner": "person/j.okafor"})
        client.post("/api/v1/feature-views", auth=auth, json={
            "name": "sb_credit", "entity": "borrower_id",
            "owner": "person/j.okafor",
            "features": ["dscr", "turnover", "spend"]})
        rows = []
        for i in range(60):
            dscr, turnover = 1.0 + i * 0.05, 100.0 + (i % 7) * 3.0
            rows.append({"entity_id": f"B{i}", "event_ts": self.EVENT,
                         "ingest_ts": self.EVENT, "dscr": dscr,
                         "turnover": turnover,
                         "spend": 5.0 + 2.0 * dscr - 0.5 * turnover})
        client.post("/api/v1/feature-views/sb_credit/materialise", auth=auth,
                    json={"rows": rows})
        client.post("/api/v1/featuresets", auth=auth, json={
            "name": "sb_fit_set", "entity": "borrower_id",
            "slots": {"dscr": "numeric", "turnover": "numeric",
                      "spend": "numeric"}})
        client.post("/api/v1/featuresets/sb_fit_set/versions", auth=auth, json={
            "bindings": {"dscr": "dscr", "turnover": "turnover",
                         "spend": "spend"}})
        return client.post("/api/v1/featuresets/sb_fit_set/training-sets",
                           auth=auth, json={
                               "version": 1, "as_of": self.AS_OF,
                               "spine": [{"entity_id": f"B{i}",
                                          "label_ts": self.AS_OF}
                                         for i in range(60)]})

    def _fit(self, client, people, **overrides):
        owner = people["j.okafor"]
        client.post("/api/v1/warrants", auth=owner, json={
            "urn": self.FIT_URN, "environment": "prod",
            "principal": "svc/model-lab", "declared_use": "model_development"})
        snapshot = self._snapshot(client, people["d.raman"]).json()
        body = {"urn": self.FIT_URN, "snapshot_id": snapshot["id"],
                "environment": "prod",
                "principal": "svc/model-lab", "window": self.WINDOW,
                "name": "ols_v1"}
        body.update(overrides)
        return client.post("/api/v1/parameter-fits", auth=people["d.raman"],
                           json=body)

    def test_a_fit_over_http_recovers_the_relationship_in_the_data(
            self, registered, people):
        self._estimator_version(registered, people)
        r = self._fit(registered, people)
        assert r.status_code == 201, r.text
        values = r.json()["values_inline"]
        assert values["intercept"] == pytest.approx(5.0, abs=1e-6)
        assert values["dscr"] == pytest.approx(2.0, abs=1e-6)
        assert values["turnover"] == pytest.approx(-0.5, abs=1e-6)

    def test_the_fit_is_proposed_and_needs_a_second_person(self, registered,
                                                           people):
        """The whole reason a fit is not allowed to be its own approval."""
        self._estimator_version(registered, people)
        fitted = self._fit(registered, people).json()
        assert fitted["state"] == "proposed"
        # The person who fitted it cannot approve it.
        same = registered.post(
            f"/api/v1/parameter-sets/{fitted['id']}/review",
            auth=people["d.raman"],
            json={"accept": True, "note": "looks fine to me"})
        assert same.status_code in (403, 422), same.text
        other = registered.post(
            f"/api/v1/parameter-sets/{fitted['id']}/review",
            auth=people["s.iqbal"],
            json={"accept": True, "note": "diagnostics reviewed"})
        assert other.status_code == 200, other.text
        assert other.json()["state"] == "approved"

    def test_the_diagnostics_reach_the_caller(self, registered, people):
        self._estimator_version(registered, people)
        d = self._fit(registered, people).json()["diagnostics"]
        assert d["family"] == "ols" and d["rows"] == 60
        assert d["r_squared"] == pytest.approx(1.0)
        assert "condition_number" in d and "standard_errors" in d

    def test_a_fit_without_a_window_is_refused_by_name(self, registered, people):
        self._estimator_version(registered, people)
        r = self._fit(registered, people, window={})
        assert r.status_code == 422
        assert r.json()["error"] == "window_required"

    def test_an_unknown_snapshot_is_a_404_and_not_a_500(self, registered, people):
        self._estimator_version(registered, people)
        r = self._fit(registered, people, snapshot_id="nope")
        assert r.status_code == 404
        assert r.json()["error"] == "no_snapshot"

class TestReplayFromStorageOverTheApi:
    def test_an_episode_with_no_snapshot_reports_every_test_as_skipped(
            self, registered, people):
        episode = registered.post("/api/v1/validations", auth=people["a.mehta"],
                                  json={"urn": URN, "semver": "3.2.1",
                                        "kind": "periodic",
                                        "validators": ["person/a.mehta"]}).json()
        r = registered.post(
            f"/api/v1/validations/{episode['id']}/replay-from-storage")
        assert r.status_code == 200
        assert r.json()["source"] == "storage"
        assert r.json()["data"]["readable"] is False

    def test_replayability_is_reported_before_it_is_attempted(self, registered,
                                                              people):
        episode = registered.post("/api/v1/validations", auth=people["a.mehta"],
                                  json={"urn": URN, "semver": "3.2.1",
                                        "kind": "periodic",
                                        "validators": ["person/a.mehta"]}).json()
        body = registered.get(
            f"/api/v1/validations/{episode['id']}/replayable").json()
        assert body["readable"] is False
        assert "pins no dataset snapshot" in body["detail"]


class TestLoadingFeatureValuesFromAFile:
    """A person defining a feature has a file, not an Arrow stream.

    The endpoint an execution engine posts to already took Arrow, Parquet and
    NDJSON; CSV was missing, which is the one format somebody actually has —
    and refusing it means they convert by hand, and the conversion is where the
    mistakes live. The interface posts to the SAME endpoint, so the browser
    exercises the contract rather than a convenience beside it.
    """

    CSV = (b"entity_id,event_ts,ingest_ts,dscr\n"
           b"B1,1717200000.0,1717200000.0,1.4\n"
           b"B2,1717200000.0,1717200000.0,2.1\n")

    def _view(self, client, auth, name="upload_view"):
        client.post("/api/v1/features", auth=auth, json={
            "name": "dscr", "entity": "borrower_id", "dtype": "numeric",
            "description": "d", "owner": "person/j.okafor"})
        client.post("/api/v1/feature-views", auth=auth, json={
            "name": name, "entity": "borrower_id", "owner": "person/j.okafor",
            "features": ["dscr"]})
        return name

    def test_a_csv_becomes_a_feature_view_version(self, registered, people):
        view = self._view(registered, people["d.raman"])
        r = registered.post(f"/api/v1/feature-views/{view}/data",
                            auth=people["d.raman"], content=self.CSV,
                            headers={"Content-Type": "text/csv"})
        assert r.status_code == 201, r.text
        assert r.json()["row_count"] == 2 and r.json()["version"] == 1

    def test_the_values_read_back_typed(self, registered, people):
        """A CSV carries no types, so they are inferred — and a column that read
        as text rather than a number would be a silent defect in a training
        set."""
        view = self._view(registered, people["d.raman"], "typed_view")
        registered.post(f"/api/v1/feature-views/{view}/data",
                        auth=people["d.raman"], content=self.CSV,
                        headers={"Content-Type": "text/csv"})
        rows = registered.get(f"/api/v1/feature-views/{view}/versions/1/data",
                              auth=people["d.raman"]).json()["rows"]
        assert rows[0]["dscr"] == 1.4, "a number, not the string '1.4'"

    def test_a_file_missing_the_second_clock_is_refused(self, registered, people):
        """A file with no `ingest_ts` cannot be read point-in-time, and guessing
        it is how the future gets into a training set."""
        view = self._view(registered, people["d.raman"], "clockless_view")
        r = registered.post(
            f"/api/v1/feature-views/{view}/data", auth=people["d.raman"],
            content=b"entity_id,event_ts,dscr\nB1,1717200000.0,1.4\n",
            headers={"Content-Type": "text/csv"})
        assert r.status_code == 409
        assert "ingest_ts" in r.text

    def test_a_format_maya_does_not_read_is_refused_by_name(self, registered,
                                                            people):
        view = self._view(registered, people["d.raman"], "xls_view")
        r = registered.post(f"/api/v1/feature-views/{view}/data",
                            auth=people["d.raman"], content=b"\x00\x01",
                            headers={"Content-Type": "application/vnd.ms-excel"})
        assert r.status_code == 409
        assert "not a format this accepts" in r.text


class TestTheUploadFormIsOnThePage:
    def test_the_features_page_offers_a_file_upload(self, registered):
        from tests.api_helpers import login
        login(registered)
        body = registered.get("/features").text
        assert 'id="load-values"' in body
        assert ".csv,.jsonl,.ndjson,.parquet,.arrow" in body

    def test_it_posts_to_the_same_endpoint_an_engine_uses(self, registered):
        """Not a second upload path beside the contract."""
        from tests.api_helpers import login
        login(registered)
        body = registered.get("/features").text
        assert '"/api/v1/feature-views/" + encodeURIComponent(view) + "/data"' in body


class TestComposingAFeaturesetFromTheInterface:
    """Composition, inheritance and overrides are the centre of this design, and
    the form offered a comma-separated box for parents and a JSON textarea for
    slots — with no way to express an operation at all. The two things the
    design is *for* were the two hardest things to do in the interface.
    """

    def _parent(self, client, auth, name="core_set"):
        for slot in ("dscr", "turnover"):
            client.post("/api/v1/features", auth=auth, json={
                "name": slot, "entity": "borrower_id", "dtype": "numeric",
                "description": slot, "owner": "person/j.okafor"})
        client.post("/api/v1/featuresets", auth=auth, json={
            "name": name, "entity": "borrower_id",
            "slots": {"dscr": "numeric", "turnover": "numeric"}})
        return name

    def test_a_preview_resolves_without_declaring_anything(self, registered,
                                                           people):
        dev = people["d.raman"]
        parent = self._parent(registered, dev)
        r = registered.post("/api/v1/featuresets/preview", auth=dev, json={
            "slots": {"spend": "numeric"}, "composes": [{"name": parent}]})
        assert r.status_code == 200, r.text
        body = r.json()
        assert set(body["slots"]) == {"dscr", "turnover", "spend"}
        assert body["declared_slots"] == ["spend"]
        assert body["inherited_slots"] == ["dscr", "turnover"]
        # and nothing was created
        assert registered.get("/api/v1/featuresets", auth=dev).json()

    def test_a_preview_shows_what_an_override_changes(self, registered, people):
        dev = people["d.raman"]
        parent = self._parent(registered, dev, "override_parent")
        r = registered.post("/api/v1/featuresets/preview", auth=dev, json={
            "composes": [{"name": parent}],
            "operations": [{"op": "override", "name": "dscr",
                            "value": {"dtype": "integer"}}]})
        body = r.json()
        assert body["slots"]["dscr"]["dtype"] == "integer"
        assert "dscr" in body["declared_slots"], (
            "an overridden slot is this set's own decision, not the parent's")

    def test_a_preview_shows_what_a_drop_removes(self, registered, people):
        dev = people["d.raman"]
        parent = self._parent(registered, dev, "drop_parent")
        body = registered.post("/api/v1/featuresets/preview", auth=dev, json={
            "composes": [{"name": parent}],
            "operations": [{"op": "drop", "name": "turnover"}]}).json()
        assert set(body["slots"]) == {"dscr"}

    def test_a_preview_refuses_exactly_what_declaring_would(self, registered,
                                                            people):
        """A preview that accepted more than the real thing would be worse than
        none: somebody would design against it and be refused at the last step."""
        dev = people["d.raman"]
        parent = self._parent(registered, dev, "strict_parent")
        r = registered.post("/api/v1/featuresets/preview", auth=dev, json={
            "composes": [{"name": parent}],
            "operations": [{"op": "drop", "name": "not_a_slot"}]})
        assert r.status_code == 409, "dropping what is not there is a no-op, refused"

    def test_an_unknown_parent_is_refused_in_the_preview_too(self, registered,
                                                             people):
        r = registered.post("/api/v1/featuresets/preview",
                            auth=people["d.raman"],
                            json={"composes": [{"name": "no_such_set"}]})
        assert r.status_code == 409
        assert "no such featureset" in r.text

    def test_the_form_offers_slots_parents_and_operations(self, registered):
        from tests.api_helpers import login
        login(registered)
        body = registered.get("/featuresets").text
        assert 'id="slot-rows"' in body
        assert 'id="parent-rows"' in body
        assert 'id="op-rows"' in body
        assert 'id="preview-set"' in body
        for word in ("add", "drop", "override"):
            assert word in body, word


class TestAFitWarrantIsSelfDescribing:
    """An engine receiving a fit warrant should not need a second call to learn
    what columns it is being asked to train on.

    The warrant named a featureset and its digest and said nothing about what
    was in it — so the digest was the only thing standing between "the right
    columns" and "some columns", which is a check nobody can perform by reading.
    """

    def test_the_warrant_carries_the_slots_and_what_fills_them(
            self, registered, people):
        dev, owner = people["d.raman"], people["j.okafor"]
        self._fittable_version(registered, people)
        self._setup(registered, dev, {"dscr": "float"}, {"dscr": "dscr"})
        doc = self._fit(registered, owner).json()
        binding = doc["data"]["inputs"][0]
        assert binding["featureset"] == "sb_set"
        slots = {s["slot"]: s for s in binding["slots"]}
        assert "dscr" in slots
        assert slots["dscr"]["feature"] == "dscr"
        assert slots["dscr"]["view"] and slots["dscr"]["view_version"]

    def test_it_carries_the_grain_and_the_entity(self, registered, people):
        """What one row means. Without it an engine knows the columns and not
        what they are a row of."""
        dev, owner = people["d.raman"], people["j.okafor"]
        self._fittable_version(registered, people)
        self._setup(registered, dev, {"dscr": "float"}, {"dscr": "dscr"})
        binding = self._fit(registered, owner).json()["data"]["inputs"][0]
        assert binding["entity"] == "borrower_id"
        assert binding["grain"]

    def test_it_does_not_carry_the_values(self, registered, people):
        """Names and types, never data. A signed credential is not a wire format
        for a dataset, and the transfer API is how the rows are fetched."""
        import json
        dev, owner = people["d.raman"], people["j.okafor"]
        self._fittable_version(registered, people)
        self._setup(registered, dev, {"dscr": "float"}, {"dscr": "dscr"})
        doc = self._fit(registered, owner).json()
        assert len(json.dumps(doc)) < 20_000, "a warrant is a credential, not a payload"

    # the helpers this class needs, borrowed from the schema-check suite
    _fittable_version = TestTheFitWarrantChecksTheSchema._fittable_version
    _setup = TestTheFitWarrantChecksTheSchema._setup
    _fit = TestTheFitWarrantChecksTheSchema._fit
