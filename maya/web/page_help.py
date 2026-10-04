"""
"About this page": the short help at the foot of every page.

MAYA has grown rich enough that what a screen shows, and the idea behind it, is easy to miss
or forget. Each page therefore ends with a few lines: what the page is for, what you can do
there, the concept that makes sense of it, and where Help explains it in full. The words are
kept short on purpose -- the subject pages in Help are the full account, and this links to
them rather than repeating them.

One entry per page, keyed by the route's path template; ``tests/test_page_help.py`` fails when
a page has none, so a new screen cannot be added without saying what it is.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import re
from typing import Any

# path template -> (what it is, [points], help subject slug (with an optional #anchor) or None)
PAGES: dict[str, tuple[str, list[str], str | None]] = {
    # -- home and account ---------------------------------------------------------------
    "/": (
        "Your dashboard: what changed recently, what waits for your review, and your jobs.",
        [
            "The tiles count features, models, items in review and the system's health.",
            "<strong>My queue</strong> lists the reviews only you (or your role) can act on.",
            "Slow work — pins, validations, documents — runs as jobs; their progress is here.",
        ],
        "getting-started",
    ),
    "/inbox": (
        "Notifications: what MAYA owes you, whether or not you asked.",
        [
            "Covenant breaches, warrants near expiry, blocked pins, restatements under live "
            "models, and objects you follow.",
            "Each notice is sent once; marking it read does not change the thing it is about.",
        ],
        "workflow",
    ),
    "/search": (
        "Search across features, feature sets, models and warrants.",
        ["Only what you may read is found.", "Ctrl-K (⌘K) opens the search box from any page."],
        "getting-started",
    ),
    "/account/keys": (
        "Your API keys, for the SDK, the CLI and scripts.",
        [
            "A key is shown once, when it is created; keep it in an environment variable "
            "(MAYA_API_KEY), never in code.",
            "A key can be narrowed to some actions and namespaces, and expires.",
        ],
        "access",
    ),
    "/account/password": (
        "Change your password.",
        ["The policy (length, character kinds, history) is set by your administrator."],
        "security",
    ),
    "/account/mfa": (
        "Two-factor authentication: a code from an authenticator app, or a security key.",
        ["Your role may require it; then MAYA asks you to enrol before anything else."],
        "security",
    ),
    "/account/credentials": (
        "Service-account credentials and password resets an administrator issues.",
        ["A reset link is single-use and time-limited, and ends the account's sessions."],
        "security",
    ),
    "/login": (
        "Sign in to MAYA.",
        ["With single sign-on configured, use your organisation's button."],
        "security",
    ),
    "/login/forgot": (
        "Ask for a password reset.",
        [
            "Your administrators are told; MAYA sends no email, so they hand you the link. "
            "Nothing here says whether an account exists."
        ],
        "security",
    ),
    "/login/reset": ("Choose a new password with the reset link you were given.", [], "security"),
    "/mfa": ("Enter your second factor to finish signing in.", [], "security"),
    # -- catalog --------------------------------------------------------------------------
    "/catalog": (
        "The faceted catalog: every governed object you may read.",
        [
            "Filter by type, namespace, owner, status, tag and freshness.",
            "A <strong>feature</strong> is one governed series of numbers; a "
            "<strong>feature set</strong> assembles features into a model's inputs; a "
            "<strong>model</strong> is the mathematics that turns them into an output.",
        ],
        "features",
    ),
    "/catalog/features": (
        "Every feature you may read, with its latest version and state.",
        [
            "A feature's <strong>definition</strong> says how its numbers are produced; a "
            "<strong>version</strong> freezes the definition; a <strong>pin</strong> freezes the "
            "resolved data."
        ],
        "features",
    ),
    "/catalog/features/{ns}/{name}": (
        "One feature: its versions, definition, data, pins, lineage and history.",
        [
            "<strong>Data</strong> previews an approved version or a sealed pin, with the fill "
            "report saying what each rule did.",
            "Two clocks: <strong>event time</strong> is the date a value is about; "
            "<strong>knowledge time</strong> is when MAYA could first have known it, so a "
            "correction never overwrites the past.",
            "<strong>Pins</strong> are sealed, content-addressed snapshots a warrant can cite "
            "forever.",
        ],
        "features",
    ),
    "/catalog/features/{ns}/{name}/compare": (
        "Two versions of a feature, attribute by attribute.",
        ["The change class (cosmetic, additive, breaking) decides what review it needs."],
        "features",
    ),
    "/catalog/featuresets": (
        "Every feature set you may read.",
        ["A feature set maps feature attributes to a model's inputs, aligned on one index."],
        "featuresets",
    ),
    "/catalog/featuresets/{ns}/{name}": (
        "One feature set: its members, versions, pins and effective licence.",
        [
            "Its <strong>members</strong> are features (or pins of them); alignment and fill "
            "policy say how their rows are joined.",
            "A <strong>cascade pin</strong> pins every member at the same as-of date, so a "
            "training warrant can cite one frozen panel.",
            "The effective licence is the most restrictive of every member's.",
        ],
        "featuresets",
    ),
    "/catalog/featuresets/{ns}/{name}/diff": (
        "Two versions of a feature set, member by member.",
        [],
        "featuresets",
    ),
    "/catalog/subscriptions": (
        "The objects you follow, and what you are told about them.",
        ["You are notified when a new version is approved or a dependent pin is made."],
        "workflow",
    ),
    "/lineage": (
        "The lineage canvas: what an object was built from, and what uses it.",
        [
            "<strong>Upstream</strong> answers “what built this”; "
            "<strong>downstream</strong> answers “what breaks if I change this”; "
            "<em>both</em> shows the two, each walked in its own direction.",
            "Lineage is recorded between versions and pins; an object as the root is drawn "
            "through its versions and pins.",
            "Overlays recolour by freshness, approval, access or cost, and say so in words.",
        ],
        "algebra",
    ),
    # -- workbench ------------------------------------------------------------------------
    "/workbench": (
        "Your drafts in flight, and where to start new work.",
        ["Nothing is governed until it is submitted: a draft is yours to edit."],
        "features",
    ),
    "/workbench/features/new": (
        "The feature designer: index, schema, source, resolution rules and quality checks.",
        [
            "The <strong>index</strong> names a row (usually a date and an entity); the "
            "<strong>schema</strong> its attributes and types.",
            "<strong>Resolution rules</strong> fill gaps; a rule that reads the future is "
            "marked non-causal and must be justified.",
            "The panel above lists exactly what the definition needs.",
        ],
        "features",
    ),
    "/workbench/features/{ns}/{name}/edit": (
        "Edit a feature's draft definition.",
        ["Only a draft is edited; an approved version is immutable — open a new draft."],
        "features",
    ),
    "/workbench/features/{ns}/{name}/ingest": (
        "Upload a batch of data into the feature's bitemporal log.",
        [
            "Each batch is stamped with a knowledge time; a batch that changes values already "
            "known is a <strong>restatement</strong>, appended, never overwriting.",
            "A restatement under a live model's training pin raises an alert on its warrant.",
        ],
        "data",
    ),
    "/workbench/features/{ns}/{name}/preview": (
        "Resolve the draft on its data and see the fill report before you submit.",
        [],
        "features",
    ),
    "/workbench/featuresets/new": (
        "The feature set builder: map feature attributes to a model's inputs.",
        ["Choose members, alignment and the fill policy; members must be approved."],
        "featuresets",
    ),
    "/workbench/featuresets/{ns}/{name}/edit": ("Edit a feature set's draft.", [], "featuresets"),
    "/workbench/featuresets/{ns}/{name}/preview": (
        "Assemble the draft feature set on current data and see the result.",
        [],
        "featuresets",
    ),
    "/workbench/quick": (
        "Quick feature: one CSV to one governed feature, in a minute.",
        ["MAYA infers the definition; you review and submit it."],
        "getting-started",
    ),
    "/workbench/upload": (
        "The upload wizard: infer a schema from a file, then refine it.",
        [],
        "features",
    ),
    "/workbench/workspaces": (
        "Workspaces: stage changes and replay what they would have done before merging.",
        ["A workspace merges only on approval; until then nothing governed changes."],
        "workspaces",
    ),
    "/workbench/workspaces/{ws_id}": (
        "One workspace: its staged changes and the shadow replay of their numeric impact.",
        [],
        "workspaces",
    ),
    # -- models ---------------------------------------------------------------------------
    "/models": (
        "Every model you may read: formulas, black boxes and composites.",
        [
            "A model is mathematics with <strong>inputs</strong>; it becomes usable only "
            "through warrants: a training warrant to fit it, an execution warrant to run it."
        ],
        "models",
    ),
    "/models/new": (
        "Define a model: from LaTeX, from Python, or as a declared black box.",
        [
            "Give each input a role: a <strong>feature</strong> is read from data, one value per "
            "row; a <strong>parameter</strong> is one value for the whole model, fitted or set; "
            "a <strong>constant</strong> is fixed in the definition.",
            "MAYA writes the formula IR — the authority — from what you enter.",
        ],
        "models#features-parameters-constants",
    ),
    "/models/kernel": (
        "Design your compute kernel: write the mathematics, read back the typed tree and Python.",
        ["Nothing is created here; it is a place to get the formula right first."],
        "models",
    ),
    "/models/{ns}/{name}": (
        "One model: its definition, specification, code, parameters, lineage and documents.",
        [
            "<strong>Features</strong> are facts about each case, read from data row by row "
            "through a warrant's mapping (a loan's balance, an applicant's bureau score). "
            "<strong>Parameters</strong> are settings of the model itself — one value each "
            "for every row, fitted on training data or taken from an agreement (a weight, a "
            "fee) — and come from an approved parameter set. <strong>Constants</strong> are "
            "numbers fixed in the definition.",
            "The <strong>Definition</strong> (formula IR) is the authority; the generated code "
            "and the specification are checked against it.",
            "<strong>Parameters</strong> lists each fitted set with its values and the metrics "
            "the trainer reported; MAYA's own blind score is on the training warrant.",
        ],
        "models#features-parameters-constants",
    ),
    "/models/{ns}/{name}/diff": (
        "Two versions of a model, compared by their mathematics, not their text.",
        ["A cosmetic edit hashes the same; a change that alters the result is named."],
        "models",
    ),
    "/models/{ns}/{name}/spec/{version_no}/drafts": (
        "Drafts of the specification sections nobody has written yet.",
        ["A draft is a suggestion: nothing is written into the specification until you do."],
        "models",
    ),
    # -- warrants -------------------------------------------------------------------------
    "/warrants": (
        "Every training and execution warrant you may read.",
        [
            "A <strong>training warrant</strong> licenses fitting one model version on one "
            "feature set; an <strong>execution warrant</strong> licenses running the fitted "
            "model, where and until when."
        ],
        "warrants",
    ),
    "/warrants/training/new": (
        "Draw up a training warrant: the model version, the data, the split and the target.",
        [
            "The <strong>mapping</strong> binds each of the model's feature inputs to a column "
            "of the feature set.",
            "Prefer a pin: only a pin freezes the data the fit will be judged against.",
        ],
        "models#features-parameters-constants",
    ),
    "/warrants/training/{wid}": (
        "One training warrant: its terms, its data, its parameter sets and its blind scores.",
        [
            "Download the training data here; the checksum of the download is what a "
            "parameter set must quote.",
            "The test partition is <strong>escrowed</strong>: MAYA scores a parameter set on it "
            "blind and every attempt is counted.",
            "The leakage certificate proves no row used a value not yet known at its date.",
        ],
        "warrants",
    ),
    "/warrants/execution/new": (
        "Issue an execution warrant: license a fitted model to run.",
        ["Name the approved parameter set, the environments, the validity and the covenants."],
        "warrants",
    ),
    "/warrants/execution/{eid}": (
        "One execution warrant: what may run, where, until when, and how it has run.",
        [
            "<strong>Covenants</strong> bound what a run may see or produce; a breach suspends "
            "the warrant at once.",
            "<strong>Restated data</strong> shows corrections to the data under its training "
            "pin, and how far they would move the model.",
            "Revoking ends it for every consumer; a reason is required.",
        ],
        "warrants",
    ),
    "/warrants/verify": (
        "Verify a reproducibility bundle: file hashes, signature and re-execution, offline.",
        [],
        "warrants",
    ),
    # -- workflow -------------------------------------------------------------------------
    "/workflow": (
        "My queue: what waits for your review or approval.",
        [
            "Separation of duties: the person who submitted an object does not approve it.",
            "Each item shows its checks; a failing check blocks approval and says why.",
        ],
        "workflow",
    ),
    "/workflow/review/{object_type}/{object_id}": (
        "Review one submission: its checks, the recorded challenger's memo, and the decision.",
        ["The challenger's memo never approves or blocks; you record whether you agree."],
        "workflow",
    ),
    "/workflow/policies": (
        "The workflow policies: states, transitions and checks for each namespace and type.",
        ["A policy is changed by a draft and activated by a second administrator."],
        "workflow",
    ),
    "/workflow/policies/{policy_id}": (
        "One workflow policy, as text and as a diagram.",
        [],
        "workflow",
    ),
    "/workflow/delegations": (
        "Delegations: who acts for whom while someone is away.",
        [],
        "workflow",
    ),
    "/workflow/campaigns": (
        "Campaigns: one transition applied to many objects, each recorded.",
        [],
        "workflow",
    ),
    "/workflow/access-requests": (
        "Access requests: ask for access to an object, or decide others' requests.",
        [],
        "access",
    ),
    "/workflow/aging": (
        "SLA aging: reviews that have waited too long, and their escalation.",
        [],
        "workflow",
    ),
    "/workflow/break-glass": (
        "The break-glass report: every forced transition, with who and why.",
        ["Break-glass is audited loudly; this is where it is read back."],
        "workflow",
    ),
    # -- governance -----------------------------------------------------------------------
    "/governance": (
        "Findings and reviews: every model with its tier, next periodic review and findings.",
        [
            "The <strong>tier</strong> is how material a model is; it sets how often it is "
            "reviewed.",
            "An overdue review suspends the model's live execution warrants until a model "
            "manager, validator or administrator records one.",
        ],
        "model-risk",
    ),
    "/governance/inventory": (
        "The model inventory in a supervisory layout (SR 11-7, SS1/23).",
        [],
        "model-risk",
    ),
    "/governance/models/{namespace}/{name}": (
        "One model's governance: its profile and tier, reviews and findings.",
        [
            "Editing the profile changes only the fields you change.",
            "Its owner never records its periodic review.",
        ],
        "model-risk",
    ),
    "/governance/findings/{finding_id}": (
        "One validation finding: its severity, owner, due date and history.",
        [],
        "model-risk",
    ),
    "/governance/challenges": (
        "Champion and challenger: two models scored on the same escrowed holdout.",
        [],
        "model-risk",
    ),
    "/governance/challenges/{challenge_id}": (
        "One challenge: the two blind scores and the recorded decision.",
        [],
        "model-risk",
    ),
    "/monitoring": (
        "Live models, graded from what their executions report.",
        ["Silence is a signal: a live model that reports nothing is flagged."],
        "model-risk",
    ),
    "/monitoring/warrants/{ew_id}": (
        "One execution warrant's reports over time: inputs, outputs and breaches.",
        [],
        "model-risk",
    ),
    "/integrations": (
        "Import a model from MLflow or SageMaker, and send lineage out as OpenLineage.",
        ["An import is a registration, not an approval: it starts as a draft black box."],
        "integrations",
    ),
    "/llm": (
        "LLM applications: prompts and models, evaluated and approved like any model.",
        [],
        "llm-apps",
    ),
    "/llm/{ns}/{name}": (
        "One LLM application: its versions, evaluation sets and runs.",
        [
            "A version's provider, model, prompts and parameters are hashed; approval needs a "
            "clean run on exactly that hash."
        ],
        "llm-apps",
    ),
    "/llm/{ns}/{name}/runs/{run_id}": (
        "One evaluation run: each case, its checks and any guardrail violation.",
        [],
        "llm-apps",
    ),
    # -- admin ----------------------------------------------------------------------------
    "/admin": ("Administration.", [], "operations"),
    "/admin/users": (
        "Users and roles: who may do what.",
        ["Roles grant capabilities; access to one object is decided by its grants as well."],
        "access",
    ),
    "/admin/namespaces": (
        "Namespaces: the unit of permission, policy and quota.",
        ["In development, a namespace can be purged with everything in it."],
        "access",
    ),
    "/admin/grants": ("Grants: access to objects beyond what roles give.", [], "access"),
    "/admin/sources": (
        "Named SQL connections a feature's sql source can use.",
        [
            "A connection names the environment variable that holds its password, never the password."
        ],
        "features",
    ),
    "/admin/webhooks": (
        "Webhooks: signed event deliveries to other systems.",
        ["Outside development a webhook may not target a private or local address."],
        "integrations",
    ),
    "/admin/events": ("The event stream, as webhooks receive it.", [], "integrations"),
    "/admin/health": (
        "System health: the database, lake, sandbox, typesetting, jobs and process.",
        ["Degraded modes are stated in plain language rather than hidden."],
        "operations",
    ),
    "/admin/jobs": (
        "Jobs: slow work, queued and run by workers.",
        ["A failed job can be retried; one that keeps failing is dead-lettered."],
        "operations",
    ),
    "/admin/storage": ("The lake: tables, files, sizes and maintenance.", [], "operations"),
    "/admin/retention": (
        "Retention: cold pins, archives, and collecting fragments no pin uses.",
        [],
        "operations",
    ),
    "/admin/extensions": (
        "Extensions: every extension point, what is built in, and installed plugins.",
        ["A plugin is used only when named in plugins.allow, and never replaces a built-in."],
        "operations",
    ),
    "/admin/ai": (
        "AI models: the model profiles, which is the default, and the providers on offer.",
        ["Switching the default takes effect at once; every call is audited."],
        "documents",
    ),
    "/admin/config": (
        "The effective configuration, with where each value came from.",
        [],
        "operations",
    ),
    "/admin/estate": ("Export or import the whole estate.", [], "operations"),
    "/admin/audit": (
        "The audit log: every recorded act, hash-chained so a rewrite is caught.",
        [],
        "security",
    ),
    "/admin/custody": (
        "Chain of custody: warrants' custody events and the anchors of the audit chain.",
        [],
        "security",
    ),
}

# routes that are not pages (downloads, JSON, redirects, standalone documents) or are Help
EXEMPT = (
    re.compile(r"^/(help|about|static|ui|auth|api)(/|$)"),
    re.compile(
        r"\.(pdf|xml|json|yaml|xlsx)$|/download$|/data$|/output$|/bundle\.json$"
        r"|/documents/\{doc_id\}$|/bundles/\{digest\}$"
    ),
)


def _rx(template: str) -> re.Pattern[str]:
    return re.compile("^" + re.sub(r"\\\{[^}]+\\\}", "[^/]+", re.escape(template)) + "$")


_COMPILED = [(_rx(t), t) for t in sorted(PAGES, key=len, reverse=True)]


def for_path(path: str) -> dict[str, Any] | None:
    """The help for the page at ``path``, or None."""
    for rx, template in _COMPILED:
        if rx.match(path):
            what, points, subject = PAGES[template]
            return {"what": what, "points": points, "subject": subject}
    return None


def exempt(template: str) -> bool:
    return any(rx.search(template) for rx in EXEMPT)
