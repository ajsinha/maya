"""
MAYA — helpers shared by the HTTP and page suites.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.

Two things that are not fixtures because they take arguments: a quorum approval
at a chosen version, and a browser login as a chosen person. They live here
rather than in one of the API test modules because the suite is split by subject
and several of the parts need both.
"""
from __future__ import annotations

URN = "maya://model/credit.pd.smallbiz"


def quorum_approve(client, people, semver="3.2.1", urn=None):
    """Take a version through the quorum its tier requires.

    Assessment comes first on purpose: the tier decides how many signatures the
    version needs, so approving before assessing would be choosing your own
    control depth, and the register refuses it.
    """
    opened = client.post("/api/v1/version-approvals", auth=people["s.iqbal"],
                         json={"urn": urn or URN, "semver": semver})
    assert opened.status_code == 201, opened.text
    approval = opened.json()["id"]
    for who, role in ((people["s.iqbal"], "model_risk_manager"),
                      (people["a.mehta"], "validator")):
        r = client.post(f"/api/v1/version-approvals/{approval}/sign", auth=who,
                        json={"role": role})
        assert r.status_code == 200, r.text
    return r.json()


def login(client, username="admin", password="admin123"):
    """Sign in through the form, as a browser does, without following the
    redirect — several tests assert on the redirect itself."""
    return client.post("/login", data={"username": username, "password": password,
                                       "next": "/dashboard"},
                       follow_redirects=False)


def approve_record(client, people, name=None):
    """Take the model RECORD through the register: submitted, then approved.

    Two acts, by two different people, and they are not the same thing as
    approving a *version*. Resolving a warrant requires this — until a review
    walked the path by hand, the whole suite resolved against records still
    sitting in `draft`, and no gate read the record's own state.

    Do the version work FIRST. An approved record is frozen (`MUTABLE` is
    draft, baselined and amending), so adding a version afterwards is refused
    with `this model is 'approved' … and is frozen`. That refusal is the
    register working: a new version IS a change to the model.
    """
    from tests.conftest import NAME

    model = name or NAME
    submitted = client.post(f"/api/v1/models/{model}/submit",
                            auth=people["j.okafor"],
                            json={"note": "ready for second-line review"})
    assert submitted.status_code in (200, 201), submitted.text
    approved = client.post(f"/api/v1/models/{model}/approve",
                           auth=people["s.iqbal"],
                           json={"note": "reviewed and approved"})
    assert approved.status_code in (200, 201), approved.text
    return approved.json()
