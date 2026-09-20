"""
The system design deck: how MAYA is built, one level below the specification,
with the module and the test behind each claim.

It is written for whoever has to build on the platform or operate it, so every
slide names the code. Parts 1–3 — the shape of the thing, features and feature
sets, storage and the hash — are here; parts 4–6 are in ``design_deck_2``.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.
"""

from __future__ import annotations

from design_deck_2 import SLIDES as LATER

CHAPTER = "MAYA · System Design"
TITLE = "MAYA — System Design"
SUBJECT = "How MAYA is built: features, feature sets, models, warrants, and the platform"

EARLY = [
    {
        "kind": "title",
        "kicker": "SYSTEM DESIGN  ·  FOR WHOEVER BUILDS OR OPERATES IT",
        "title": ["Features, feature sets, models", "and the warrants that bind them"],
        "sub": "MAYA — Model & AI Lifecycle Assurance.  How it is built, and what proves it.",
        "agenda": [
            "The shape of the thing",
            "Features and feature sets",
            "Storage and the hash",
            "Models",
            "Warrants and evidence",
            "Governance, platform and what is not built",
        ],
    },
    {
        "kind": "divider",
        "num": "1",
        "title": "The shape of the thing",
        "sub": "Three kinds of object, one spine, and eight rules that decide every design choice after them.",
        "points": ["Definition, version, pin", "The spine end to end", "Eight principles"],
    },
    {
        "kind": "table",
        "kicker": "Domain model",
        "title": "Every object is a definition, a version or a pin",
        "rows": [
            ["Kind", "What it is", "Addressed as"],
            [
                "Definition",
                "A named description of how something is produced, editable while it is in draft",
                "maya://feature/adj_close_yhoo",
            ],
            [
                "Version",
                "An immutable snapshot, minted when the definition hash changes, and classified breaking, behavioral or additive",
                "maya://feature/adj_close_yhoo@v3",
            ],
            [
                "Pin",
                "An immutable materialization of a version: values computed, sealed by a content hash, never recomputed",
                "maya://feature/adj_close_yhoo#eom_2026_03",
            ],
        ],
        "col_w": [1.6, 6.4, 3.7],
        "note": "Specification §4. A version freezes how; a pin freezes what. A bare name resolves to the latest approved version and MAYA records that resolution, so “latest” never hides inside an audit trail.",
    },
    {
        "kind": "flow",
        "kicker": "The spine",
        "title": "Source to bundle, and every surface walks all of it",
        "steps": [
            ("Source", "Files, read-only SQL, a reviewed Python producer, or derived"),
            ("Feature", "A definition, its versions, and pins in the lake"),
            ("Feature set", "Attributes mapped from members onto one grid"),
            ("Model", "Formula IR, code artifact, parameters, document"),
            ("Warrants", "Training, then parameter set, then execution"),
            ("Bundle", "Signed; verifies and re-executes offline"),
        ],
        "box_h": 1.9,
        "items": [
            "Four surfaces, one spine: maya/web (itself an SDK client), maya/api, maya/sdk and maya/cli. Nothing under maya.web imports anything but maya.sdk, and a gate fails the build if it does.",
            "Features and feature sets are closed under their operators, so a derived object re-enters the flow as an ordinary object rather than as a special case.",
            "A composite model is an ordinary model: one warrant over one feature set, however many members it holds.",
        ],
        "note": "README, “The shape of the thing”; tests/test_web.py::test_web_imports_only_the_sdk and tools/ci/import_boundaries.py.",
    },
    {
        "kind": "cards",
        "kicker": "Principles",
        "title": "Eight rules that bind every design choice",
        "cols": 4,
        "cards": [
            ("1", "Definitions are code", "Data is a consequence, materialized only when asked."),
            (
                "2",
                "Immutability is earned by pinning",
                "Anything pinned is frozen; nothing else claims to be reproducible.",
            ),
            (
                "3",
                "Everything meaningful is versioned",
                "Features, sets, models, parameters, warrants, policies, documents.",
            ),
            (
                "4",
                "Resolution is deterministic",
                "Byte-identical output, or MAYA reports why it cannot produce one.",
            ),
            (
                "5",
                "Authorization is on objects",
                "A role opens a door; an access list decides which rooms.",
            ),
            (
                "6",
                "One door to the database",
                "No SQLAlchemy import outside maya.persistence; a gate fails the build.",
            ),
            ("7", "Small, replaceable parts", "No non-UI source file over 1,500 code lines."),
            (
                "8",
                "The platform never silently guesses",
                "Missing data, ambiguous joins and drift raise typed, explainable errors.",
            ),
        ],
        "note": "Specification §1. Principles 6 and 7 are held by gates in tools/ci/ rather than by review, because a rule that is merely written down holds until the first deadline.",
    },
    {
        "kind": "divider",
        "num": "2",
        "title": "Features and feature sets",
        "sub": "A feature is a governed bitemporal dataset from one source. A feature set is a view over features that stores nothing of its own until it is pinned.",
        "points": [
            "Anatomy and the two clocks",
            "Sources",
            "Resolution rules and the fill report",
            "The feature algebra",
            "Feature sets: mapping, alignment, precedence",
            "Pinning, cascade and materialization",
            "Grant conditions on every path",
        ],
    },
    {
        "kind": "split",
        "kicker": "Features",
        "title": "A feature version, and its two clocks",
        "left": {
            "head": "Anatomy",
            "items": [
                ("Identity", "Name, namespace, owner, tags, description."),
                (
                    "Schema and index",
                    "Typed attributes with units and semantic tags; the index is required and immutable within a lineage.",
                ),
                (
                    "Source binding, resolution policy, transformation",
                    "How rows arrive, how gaps are filled, what is computed on top.",
                ),
                (
                    "Quality contract",
                    "Checks that run on every resolution and always on pin; a failure blocks the pin rather than warning.",
                ),
            ],
        },
        "right": {
            "head": "Bitemporal by construction",
            "items": [
                ("Event time", "The date a value is about — the first column of the index."),
                (
                    "Knowledge time",
                    "The instant MAYA could first have known it, carried as _knowledge_time.",
                ),
                (
                    "A restatement is an append",
                    "Never an overwrite, so “what did we know on 31 March” is a filter rather than an archaeology project.",
                ),
                (
                    "Proved",
                    "tests/test_features.py::test_sc11_point_in_time_after_restatement; tests/test_properties.py::test_a_restatement_never_overwrites.",
                ),
            ],
        },
        "note": "maya/resolution/resolver.py: bitemporal_cut drops rows known after the cutoff, then keeps the latest knowledge per index key, then builds the grid, then applies the rules. The ingest log is the append-only lake table raw/<namespace>/<name> (maya/storage/lake.py).",
    },
    {
        "kind": "table",
        "kicker": "Sources",
        "title": "Where a feature's rows come from",
        "rows": [
            ["Source", "How it behaves", "Proved by"],
            [
                "csv, parquet, json",
                "Uploaded files, content-addressed; the inferred schema is a proposal the designer confirms",
                "tests/test_features.py, tests/test_cli.py::test_quick_upload_and_restatement",
            ],
            [
                "sql",
                "A read-only query on an admin-managed connection, with typed parameters bound rather than interpolated",
                "tests/test_sql_source.py",
            ],
            [
                "python",
                "A reviewed producer function run in the sandbox on every pull: the escape hatch, and it needs approval",
                "tests/test_python_source.py",
            ],
            [
                "derived",
                "An algebra expression over other feature versions or pins, kept in lineage rather than flattened",
                "tests/test_features.py::test_derived_union_and_inheritance",
            ],
            [
                "unsupported",
                "Anything else is refused by name, never approximated with the nearest thing that parses",
                "tests/test_features.py::test_unsupported_source_is_refused_by_name",
            ],
        ],
        "col_w": [1.6, 5.6, 4.4],
        "note": "maya/services/sources.py and maya/services/feature_data.py. Uploads and pulls land in the bitemporal ingest log with a knowledge time. A delta source is also accepted, read through at resolution time; no test in the suite exercises it, and the README says so.",
    },
    {
        "kind": "split",
        "kicker": "Resolution",
        "title": "Declarative gap filling, bounded and reported",
        "left": {
            "head": "Grid and rules",
            "items": [
                (
                    "Grid",
                    "as_is, or a shipped calendar: NYSE, LSE, TARGET, ISO business days, natural days.",
                ),
                (
                    "Ten rules per attribute",
                    "none, forward_fill, backward_fill, linear_interp, spline_interp, constant, mean_of_window, last_known_as_of, zero, previous_period.",
                ),
                (
                    "Bounded, and refused when unbounded is meant",
                    "forward_fill takes limit and max_age; beyond either the value stays null. A negative lag is rejected as look-ahead.",
                ),
                (
                    "Non-causal rules are named",
                    "backward_fill and both interpolations consume the future; inside a training set they need a written justification.",
                ),
            ],
        },
        "right": {
            "head": "What every run emits",
            "items": [
                (
                    "A fill report",
                    "Rows filled per rule and the longest fill run, stored with the pin so nobody has to guess later.",
                ),
                (
                    "Grouped rules, vectorised",
                    "maya/resolution/grouped.py, shown equal to the per-group path on randomised cases (tests/test_resolution_grouped.py).",
                ),
                (
                    "A blocked pin on a contract failure",
                    "tests/test_features.py::test_quality_contract_blocks_the_pin.",
                ),
                (
                    "Measured",
                    "Warm p95 0.98 s with no rules; 6.1 s with forward_fill(limit=3) on all fifty attributes (docs/BENCHMARKS.md).",
                ),
            ],
        },
        "note": "maya/resolution/rules.py. custom(fn) is in the grammar and refused in this build — no sandboxed rule function is registered — which is the platform's habit: a name it cannot honour is a refusal, not a silent no-op.",
    },
    {
        "kind": "table",
        "kicker": "The feature algebra",
        "title": "Fifteen operators, each yielding a definition rather than a result",
        "rows": [
            ["Operator", "Produces", "Operator", "Produces"],
            ["project  π", "A subset of attributes", "aggregate  γ", "A coarser index"],
            ["rename  ρ", "The same data, renamed", "lag", "Values shifted by n periods"],
            [
                "transform  τ",
                "A derived feature by pipeline",
                "resample",
                "A new frequency: W, M or Q",
            ],
            [
                "union  ∪",
                "Rows of both, collisions by policy",
                "case  σ",
                "Row-wise choice between inputs",
            ],
            [
                "intersect  ∩",
                "Rows whose index is in both",
                "pivot",
                "Long to wide, a breaking change",
            ],
            [
                "difference  ∖",
                "Rows of the first absent from the second",
                "unpivot",
                "Wide to long, a breaking change",
            ],
            [
                "compose  ⋈",
                "Attributes of both, aligned on the index",
                "sample",
                "A deterministic seeded subset",
            ],
            ["coalesce  ⊕", "First non-null across ordered inputs", "", ""],
        ],
        "col_w": [1.7, 4.15, 1.7, 4.15],
        "note": "maya/resolution/algebra.py: typed at definition time with no data read, each operator declaring its change class; non-causality propagates, and a canonical derivation hash lets MAYA refuse an algebraically identical near-copy. Inheritance stores a diff, not a copy, so a fix to a parent reaches every child.",
    },
    {
        "kind": "split",
        "kicker": "Feature sets",
        "title": "A view: attributes mapped from members, on one grid",
        "left": {
            "head": "Mapping and alignment",
            "items": [
                (
                    "Attribute mapping",
                    "Each attribute names its member, the source attribute, an optional cast and its overrides.",
                ),
                (
                    "Alignment",
                    "inner, outer, left(member), or asof with a tolerance and a direction.",
                ),
                ("Broadcast, stated", "A narrower member index is broadcast and the plan says so."),
                (
                    "Refused",
                    "A member index carrying columns the set lacks, unless an aggregation is declared for them.",
                ),
                (
                    "Set operators",
                    "union, intersect, difference, join, project, override, pivot, unpivot, sample; nesting capped at eight.",
                ),
            ],
        },
        "right": {
            "head": "Precedence, shown per attribute",
            "items": [
                "1  The attribute's own override",
                "2  A member-group override",
                "3  The set's global policy",
                "4  Inherited policy, nearest ancestor first",
                "5  The member feature's own policy",
                "6  System default: leave it null",
            ],
        },
        "note": "maya/resolution/featureset.py (choose_rule) and maya/services/featuresets.py; tests/test_resolution_algebra.py::test_featureset_precedence_layers_and_broadcast and ::test_featureset_refuses_unaggregated_extra_index. Which layer decided an attribute is shown in the plan, not inferred by the reader.",
    },
    {
        "kind": "bullets",
        "kicker": "Pinning a feature set",
        "title": "Every member pinned, or none of them",
        "items": [
            (
                "A set refuses to pin while any member is unpinned",
                "Cascade pin pins each unpinned member under one shared name and as-of date in one job, and rolls the whole cascade back if any member fails its quality contract (tests/test_warrants.py::test_cascade_rolls_back_entirely_on_a_member_failure).",
            ),
            (
                "Materialization is the namespace's choice of three",
                "always, the default, writes the resolved frame. on_demand and never seal the pin by the hash of its output and replay it from the member pins; under on_demand the first replay is written back, so later reads come from the lake. All three seal by the same hash (tests/test_materialization.py).",
            ),
            (
                "Withheld, never quietly dropped",
                "A set resolved by somebody who cannot read a member returns that attribute named and null, so the shape of the answer does not depend on who asked.",
            ),
            (
                "An algebraically identical set is detected",
                "project(extend(S)) and the same set written directly hash alike, and the second is refused as a near-copy rather than accepted as a second truth.",
            ),
        ],
        "note": "maya/services/featuresets.py. Under on_demand or never a pin is only as readable as its replay: a later MAYA that resolved the inputs differently by one byte would fail the read with integrity_error rather than serve different numbers — safe, but unavailable (README, “Not yet”).",
    },
    {
        "kind": "split",
        "kicker": "Grant conditions",
        "title": "Three conditions, applied on live and pinned data alike",
        "left": {
            "head": "What a grant may carry",
            "items": [
                (
                    "row_filter",
                    "An expression over the row, with the asking principal substituted, so one grant serves a desk.",
                ),
                (
                    "column_mask",
                    "null, or hash — the SHA-256 of the value's text, so a join still works and the value does not leave.",
                ),
                (
                    "time_bound",
                    "A cutoff date; any row whose event date is later is dropped before the caller sees it.",
                ),
            ],
        },
        "right": {
            "head": "When several grants apply",
            "items": [
                ("Row filters", "Combined with AND: the narrowest wins."),
                ("Column masks", "Unioned, and null beats hash on a conflict."),
                ("Time bounds", "The earliest cutoff wins."),
                (
                    "Applied everywhere",
                    "Member-level and set-level conditions are applied inside feature-set resolution, so no read path escapes a mask.",
                ),
            ],
        },
        "note": "maya/security/conditions.py and maya/services/featuresets.py; tests/test_conditions.py. Conditions narrow a grant; they are never a way to widen one.",
    },
    {
        "kind": "divider",
        "num": "3",
        "title": "Storage and the hash",
        "sub": "Three stores, each with one job, and a content hash computed over MAYA's own canonical form so that it means the same thing on every machine that computes it.",
        "points": [
            "Content-defined fragments",
            "The canonical hash",
            "Pinning as a saga",
            "The lakehouse layer and its two backends",
            "Dependency seams: three polarities",
        ],
    },
    {
        "kind": "split",
        "kicker": "Content-addressed materialization",
        "title": "A pin is a manifest of fragments, not a copy",
        "left": {
            "head": "Fragments",
            "items": [
                (
                    "Boundaries chosen by content",
                    "A row ends a fragment when its canonical digest, read as an integer, divides by the target — so one inserted row leaves every earlier fragment untouched.",
                ),
                (
                    "In rows, not bytes",
                    "Target 512 rows, never fewer than 32 and never more than 8,192 (maya/core/chunker.py).",
                ),
                (
                    "Shared across pins",
                    "Pinning writes only the fragments the store has never seen; an unchanged month costs under 5% of a full pin.",
                ),
            ],
        },
        "right": {
            "head": "The canonical hash",
            "items": [
                (
                    "Over values, never over file bytes",
                    "Column order is ignored, every changed value is noticed, and two pins of the same data agree across engine versions.",
                ),
                (
                    "SHA-256, domain-separated",
                    "Row digests, then a fragment hash over the run, then the content hash over the schema digest and the fragment hashes in order.",
                ),
                (
                    "MAYA's encoder is authoritative",
                    "maya/core/canonical.py is the specification of the hash; canonical_fast.py computes it a column at a time and is tested equal to it.",
                ),
            ],
        },
        "note": "tests/test_features.py::test_sc1_repin_is_byte_identical_and_changed_data_is_not and ::test_sc12_unchanged_month_costs_under_five_percent; tests/test_canonical_fast.py; tests/test_properties.py.",
    },
    {
        "kind": "flow",
        "kicker": "Pinning",
        "title": "A saga, because two stores cannot commit together",
        "steps": [
            ("Write fragments", "Only those the store has never seen, into the pin's Delta table"),
            ("Re-read and verify", "The content hash is recomputed from what was actually written"),
            ("Commit metadata", "Only now is the pin sealed and usable"),
        ],
        "box_h": 1.7,
        "items": [
            "Nothing is usable until the metadata commit succeeds: a pin moves materializing → sealed, or materializing → failed, and a reaper makes a half-written pin invisible.",
            "Impossible is not claimed, only invisible: two-store consistency on pin is one of the four accepted risks, stated in the specification rather than waved away (§28.11).",
            "The resolved backend set and the chunk parameters are written into every pin's provenance, so a pin says what produced it.",
        ],
        "note": "maya/services/feature_data.py (materialize) and maya/storage/lake.py (write_pin, verify_pin); specification §15.3.",
    },
    {
        "kind": "table",
        "kicker": "The lakehouse layer",
        "title": "One API over two interchangeable backends",
        "rows": [
            ["", "native", "pure"],
            [
                "What it is",
                "delta-rs through the deltalake wheel",
                "MAYA's own implementation of a declared subset of the Delta transaction-log protocol over pyarrow",
            ],
            [
                "Chosen by",
                'select_backend("auto") prefers it when the wheel imports',
                "The fallback: absence costs throughput, not capability",
            ],
            [
                "Proved equal",
                "One conformance suite run once per backend, plus cross-backend round trips: a table written by one is read by the other",
                "The same suite, the same cases, no exemptions",
            ],
            [
                "Refusals",
                "A protocol feature outside the declared subset is refused by name",
                "The same, and vacuum below the 168-hour retention floor is refused unless explicitly overridden",
            ],
        ],
        "col_w": [1.7, 4.5, 5.4],
        "note": "maya_delta/ sits beside maya/ with no MAYA domain knowledge: conformance/suite.py, native.py, pure/. tests/test_maya_delta.py (test_conformance over both backends, test_cross_backend_round_trip, test_backend_selection_is_reported); the active backend is reported on the health page and recorded in every pin's provenance.",
    },
    {
        "kind": "table",
        "kicker": "Dependency seams",
        "title": "Three polarities, so an absent library is never a surprise",
        "rows": [
            ["Polarity", "Rule", "Examples"],
            [
                "Type A — native preferred, pure fallback",
                "Absence costs throughput, not capability; both sides are tested against one contract",
                "The lakehouse layer, JSON, frames, predicate pushdown, compression, the time-zone database",
            ],
            [
                "Type B — MAYA's implementation authoritative",
                "An accelerator that disagrees by one byte is a defect in the accelerator, not a variant",
                "The canonical encoder and the fragment chunker",
            ],
            [
                "Type C — substitutable, never downgraded",
                "Absence is a refusal with a named reason, never a quiet substitution",
                "Signing, the sandbox, single sign-on (SAML without xmlsec fails at startup), object store, job queue",
            ],
        ],
        "col_w": [3.0, 4.0, 4.7],
        "note": "maya/core/backends.py settles every seam once at startup and reports the resolved set. The gate ladder's --fallback run has passed the whole suite with every Type A seam pinned to its fallback, so the fallback is a tested path rather than a hope.",
    },
]

SLIDES = EARLY + LATER
