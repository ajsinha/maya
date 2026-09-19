"""
Licence algebra and custody anchoring (§29.6).

Licences: the most restrictive combination of everything an object is built
from, enforced at every exit — download, derivation, grant, read — with the
refusal naming the term and the source that imposed it.

Anchors: an attacker with database access who rewrites history *and recomputes
the whole chain* passes ``verify_chain``; the anchors pinned outside the
database still catch it.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import copy
import json

import httpx
import pytest
from sqlalchemy import select, text

from maya.core.errors import LicenceBreach, ValidationFailed
from maya.security import licence as lic
from maya.services.custody import CustodyService, _der, check_timestamp_response
from tests.conftest import PX_DEF, approved_feature, price_csv


def _licensed(**terms):
    d = copy.deepcopy(PX_DEF)
    d["licence"] = {"vendor": "Acme Data", **terms}
    return d


def _derived(*operands):
    return {"index": ["date", "symbol"], "index_types": PX_DEF["index_types"],
            "schema": PX_DEF["schema"],
            "source": {"type": "derived", "derivation": {
                "operator": "union", "operands": [f"maya://feature/{o}@v1" for o in operands],
                "options": {"collision": "error"}}},
            "resolution": {"grid": "as_is", "rules": {}}, "transform": [], "quality": []}


# -- the algebra ----------------------------------------------------------------------
def test_combination_is_the_most_restrictive_and_remembers_who_imposed_it():
    eff = lic.combine([
        ("a", {"vendor": "V1", "redistribution": "external", "population": ["g1", "g2"],
               "retention_days": 90}),
        ("b", {"vendor": "V2", "redistribution": "internal", "derived_works": "attribution",
               "population": ["g2", "g3"], "retention_days": 30}),
        ("c", None)])
    assert eff["redistribution"] == "internal" and eff["clauses"]["redistribution"] == "V2 via b"
    assert eff["derived_works"] == "attribution"
    assert eff["population"] == ["g2"] and eff["retention_days"] == 30
    assert eff["vendors"] == ["V1", "V2"]
    with pytest.raises(LicenceBreach, match="imposed by V2 via b"):
        lic.check_export(eff, "external")
    lic.check_export(eff, "internal")
    assert lic.combine([])["redistribution"] == "public"
    assert lic.validate({"redistribution": "sometimes", "colour": 1})


def test_a_bad_licence_block_fails_validation_at_submit(world):
    world.p.features.create(world.dana, namespace="eq", name="badlic",
                            definition=_licensed(redistribution="whenever"))
    with pytest.raises(ValidationFailed, match="licence"):
        world.p.features.transition(world.dana, "eq/badlic", 1, "submit")


# -- enforcement ----------------------------------------------------------------------
def test_no_redistribution_blocks_download_but_not_preview_and_is_audited(world):
    w = world
    ref = approved_feature(w, "lic_none", price_csv(5), _licensed(redistribution="none"))
    v1 = f"maya://feature/{ref}@v1"
    assert w.p.features.preview(w.dana, v1)["total_rows"] == 10
    with pytest.raises(LicenceBreach, match="may not leave MAYA.*Acme Data"):
        w.p.features.download(w.dana, v1)
    with w.p.uow() as uow:
        refused = uow.repo("audit_events").list(action="licence.refused")
    assert refused and refused[-1]["detail"]["term"] == "redistribution"
    shown = w.p.licences.show(w.dana, "feature", ref)
    assert shown["redistribution"] == "none" and shown["you_may_receive"]


def test_derived_works_forbidden_propagates_through_the_algebra(world):
    w = world
    approved_feature(w, "lic_nod", price_csv(5), _licensed(derived_works="forbidden"))
    approved_feature(w, "lic_free", price_csv(5, symbols=("CCC",)))
    w.p.features.create(w.dana, namespace="eq", name="lic_union",
                        definition=_derived("eq/lic_nod", "eq/lic_free"))
    with pytest.raises(LicenceBreach, match="forbids derived works"):
        w.p.features.transition(w.dana, "eq/lic_union", 1, "submit")
        w.p.features.transition(w.mick, "eq/lic_union", 1, "approve")


def test_terms_follow_a_derivation_and_a_population_limits_readers_and_grants(world):
    w = world
    approved_feature(w, "lic_ext", price_csv(5), _licensed(redistribution="internal"))
    approved_feature(w, "lic_pop", price_csv(5, symbols=("DDD",)),
                     _licensed(population=["desk:rates"]))
    eff = w.p.licences.effective("feature", "maya://feature/eq/lic_ext@v1")
    assert eff["redistribution"] == "internal"
    ref = approved_feature(w, "lic_derived", definition=_derived("eq/lic_ext", "eq/lic_free"))
    eff = w.p.licences.effective("feature", f"maya://feature/{ref}@v1")
    assert eff["redistribution"] == "internal" and "eq/lic_ext" in eff["clauses"]["redistribution"]
    with pytest.raises(LicenceBreach, match="outside the population"):
        w.p.features.preview(w.dana, "maya://feature/eq/lic_pop@v1")
    obj = w.p.access.resolve_object("feature", "eq/lic_pop")
    with pytest.raises(LicenceBreach, match="population"):
        w.p.access.grant(w.admin, kind="feature", obj=obj, principal_type="everyone",
                         principal_id="*", level="read")
    assert w.p.licences.show(w.dana, "feature", "eq/lic_pop")["you_may_receive"] is False


# -- custody anchors ------------------------------------------------------------------
def _rewrite_history(p, seq: int) -> None:
    """What an attacker with database access does: edit an entry, re-chain everything."""
    from maya.persistence.models import operations
    from maya.persistence.repositories.special import GENESIS, audit_digest
    with p.uow("attacker") as uow:
        s = uow.session
        pg = s.get_bind().dialect.name == "postgresql"
        s.execute(text("ALTER TABLE audit_events DISABLE TRIGGER audit_events_no_update") if pg
                  else text("DROP TRIGGER audit_events_no_update"))
        prev = GENESIS
        for row in s.scalars(select(operations.AuditEvent).order_by(operations.AuditEvent.seq)):
            if row.seq == seq:
                row.detail = {**(row.detail or {}), "rewritten": True}
            d = row.to_dict()
            row.prev_hash, row.hash = prev, audit_digest(prev, d)
            prev = row.hash
            s.flush()
        s.execute(text("ALTER TABLE audit_events ENABLE TRIGGER audit_events_no_update") if pg
                  else text("CREATE TRIGGER audit_events_no_update BEFORE UPDATE ON audit_events "
                            "BEGIN SELECT RAISE(ABORT, 'audit_events is append-only'); END"))


def test_an_anchor_catches_a_rechained_rewrite(world):
    w = world
    first = w.p.custody.anchor()
    assert first["methods"] == ["signature", "file", "event"]
    with w.p.uow() as uow:
        assert uow.repo("events").list(type="audit.anchored")
    line = json.loads(w.p.custody.path.read_text().splitlines()[-1])
    assert (line["seq"], line["head"]) == (first["seq"], first["head_hash"])
    approved_feature(w, "after_anchor", price_csv(3))
    w.p.custody.anchor()
    assert w.p.custody.verify(w.admin)["ok"]

    _rewrite_history(w.p, first["seq"] - 3)
    with w.p.uow() as uow:
        assert uow.repo("audit_events").verify_chain()["ok"]        # the chain alone is fooled
    report = w.p.custody.verify(w.admin)
    assert not report["ok"] and report["verdict"].startswith("TAMPERING")
    assert all("rewritten" in b["problems"][0] for b in report["broken"])
    assert len(report["broken"]) >= 2
    with pytest.raises(Exception):
        w.p.custody.verify(w.dana)


def _fake_tsa(status: int = 0):
    def handler(request: httpx.Request) -> httpx.Response:
        body = request.content
        i = body.index(b"\x04\x20")
        digest = body[i + 2:i + 34]
        token = _der(0x30, _der(0x06, b"\x2a\x86\x48\x86\xf7\x0d\x01\x07\x02")
                     + _der(0x04, digest))
        resp = _der(0x30, _der(0x30, bytes([0x02, 0x01, status])) + token)
        return httpx.Response(200, content=resp,
                              headers={"Content-Type": "application/timestamp-reply"})
    return httpx.MockTransport(handler)


def test_rfc3161_timestamp_is_requested_and_its_imprint_checked(world, tmp_path):
    w = world
    svc = CustodyService(w.p)
    svc.methods, svc.tsa_url = ["rfc3161"], "https://tsa.example.test/"
    svc.path = tmp_path / "a.jsonl"
    svc.transport = _fake_tsa()
    row = svc.anchor()
    assert row["tsa_token"] and row["detail"]["tsa"]["ok"] and row["methods"] == ["rfc3161"]
    svc.transport = _fake_tsa(status=2)
    refused = svc.anchor()
    assert refused["tsa_token"] is None and "refused" in refused["detail"]["tsa"]["detail"]
    assert not check_timestamp_response(b"\x30\x03\x02\x01\x00", b"\x00" * 32)["ok"]
