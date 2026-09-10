"""The assumption register over HTTP, and the document section it feeds.

`FR-INV-007` calls this the gap that most directly weakens the compiled model
development document, and the reason is specific: the Assumptions lens read only
the version contract's numeric bounds. A model with no numeric contract rendered
the section as **nothing** — so the document about the model whose limitations
matter most said least about them.
"""
from __future__ import annotations

from tests.conftest import CONTRACT, KERNEL, NAME, URN


def _model_with_a_version(client, people, urn=URN, name=NAME, contract=None):
    client.post("/api/v1/models", auth=people["j.okafor"], json={
        "urn": urn, "name": "SB PD", "model_class": "credit.pd.scorecard",
        "domain": "credit", "owner": "person/j.okafor",
        "legal_entity": "LE-US-01", "purpose": "12-month PD"})
    client.post(f"/api/v1/models/{name}/versions", auth=people["d.raman"],
                json={"semver": "3.2.1", "kernel": KERNEL,
                      "contract": CONTRACT if contract is None else contract,
                      "artifact_digest": "sha256:" + "a" * 64})
    return name


class TestTheRoute:
    def test_the_kinds_are_served_with_what_each_is_for(self, client, people):
        r = client.get("/api/v1/assumption-kinds", auth=people["d.raman"])
        assert r.status_code == 200, r.text
        body = r.json()
        kinds = {k["kind"] for k in body["kinds"]}
        assert kinds == {"data", "behavioural", "market", "structural",
                         "operational"}
        assert all(k["means"] for k in body["kinds"]), "say what each is for"
        assert body["materialities"] == ["low", "moderate", "material",
                                         "critical"]

    def test_one_is_recorded_and_read_back(self, client, people):
        _model_with_a_version(client, people)
        made = client.post("/api/v1/assumptions", auth=people["d.raman"], json={
            "urn": URN, "semver": "3.2.1", "kind": "behavioural",
            "statement": "borrowers prepay when it is rational to",
            "materiality": "material", "owner": "person/j.okafor"})
        assert made.status_code == 201, made.text
        assert made.json()["reference"] == "ASM-0001"

        got = client.get("/api/v1/assumptions", auth=people["d.raman"],
                         params={"urn": URN, "semver": "3.2.1"})
        assert got.status_code == 200, got.text
        assert got.json()["unmonitored_material"] == 1

    def test_a_urn_without_a_semver_is_refused_by_name(self, client, people):
        _model_with_a_version(client, people)
        r = client.get("/api/v1/assumptions", auth=people["d.raman"],
                       params={"urn": URN})
        assert r.status_code == 422, r.text
        assert r.json()["error"] == "semver_required"

    def test_no_urn_reads_the_whole_estate(self, client, people):
        _model_with_a_version(client, people)
        client.post("/api/v1/assumptions", auth=people["d.raman"], json={
            "urn": URN, "semver": "3.2.1", "kind": "data",
            "statement": "the sector mix is stable"})
        r = client.get("/api/v1/assumptions", auth=people["s.iqbal"])
        assert r.status_code == 200, r.text
        assert r.json()["standing"] == 1

    def test_a_monitor_that_does_not_exist_is_refused(self, client, people):
        _model_with_a_version(client, people)
        r = client.post("/api/v1/assumptions", auth=people["d.raman"], json={
            "urn": URN, "semver": "3.2.1", "kind": "data",
            "statement": "the mix is stable", "monitor_id": "nope"})
        assert r.status_code >= 400, r.text
        assert "no such monitor exists" in r.text

    def test_withdrawing_is_the_second_lines_act(self, client, people):
        _model_with_a_version(client, people)
        made = client.post("/api/v1/assumptions", auth=people["d.raman"], json={
            "urn": URN, "semver": "3.2.1", "kind": "data",
            "statement": "the sector mix is stable"}).json()
        # The developer who stated it may not remove it: withdrawing makes the
        # register say less than it did about an immutable version.
        denied = client.post(f"/api/v1/assumptions/{made['id']}/withdraw",
                             auth=people["d.raman"],
                             json={"reason": "refitted"})
        assert denied.status_code == 403, denied.text
        allowed = client.post(f"/api/v1/assumptions/{made['id']}/withdraw",
                              auth=people["s.iqbal"],
                              json={"reason": "the model was refitted on a "
                                              "sample that spans the new mix"})
        assert allowed.status_code == 200, allowed.text


class TestTheDocumentSectionItFeeds:
    def test_the_registers_reach_the_compiled_document(self, client, people):
        _model_with_a_version(client, people)
        client.post("/api/v1/assumptions", auth=people["d.raman"], json={
            "urn": URN, "semver": "3.2.1", "kind": "market",
            "statement": "the swap curve is arbitrage-free",
            "materiality": "critical"})
        client.post("/api/v1/limitations", auth=people["d.raman"], json={
            "urn": URN, "semver": "3.2.1", "kind": "data",
            "statement": "calibrated on 2019-2024, never through a 400bp shock"})

        r = client.post("/api/v1/documents", auth=people["s.iqbal"],
                        params={"urn": URN, "kind": "model_development_document"})
        assert r.status_code == 201, r.text
        body = next(s for s in r.json()["sections"]
                    if s["key"] == "assumptions")["body"]
        assert "ASM-0001" in body, "the assumption reaches the document"
        assert "LIM-0001" in body, "and so does the limitation"
        assert "arbitrage-free" in body
        assert "400bp" in body
        # The unmonitored, unmitigated, material one earns its own sentence.
        assert "decision nobody has taken" in body

    def test_a_model_with_no_numeric_contract_still_renders_the_section(
            self, client, people):
        """The defect this fixes. With no contract the lens returned nothing,
        so a vendor score or a generative assembly documented none of what
        somebody had recorded about it."""
        _model_with_a_version(client, people, contract={})
        client.post("/api/v1/assumptions", auth=people["d.raman"], json={
            "urn": URN, "semver": "3.2.1", "kind": "operational",
            "statement": "the input at serving time is as accurate as the one "
                         "it was fitted on"})
        r = client.post("/api/v1/documents", auth=people["s.iqbal"],
                        params={"urn": URN, "kind": "model_development_document"})
        assert r.status_code == 201, r.text
        body = next(s for s in r.json()["sections"]
                    if s["key"] == "assumptions")["body"]
        assert body, "the section is no longer empty"
        assert "serving time" in body
        # And it says WHY there are no bounds, rather than omitting them.
        assert "Nothing here is enforced at call time" in body
