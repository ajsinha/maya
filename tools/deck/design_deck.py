"""
The system design deck: how MAYA 0.3.0 is built, one level below the
specification, with the module and the test behind each claim.

It replaces four decks of the previous build — System Design, Model and
Feature Management, Feature Platform, and Model and Feature Engineering.
Under specification revision 2.3 features, feature sets, models and warrants
are one spine; four decks were four places to keep one system current.

Parts 1–3 are here; parts 4–6 are in ``design_deck_2``.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.
"""
from __future__ import annotations

from design_deck_2 import SLIDES as LATER

CHAPTER = "MAYA · System Design"
TITLE = "MAYA — System Design"
SUBJECT = "How MAYA 0.3.0 is built: features, feature sets, models, warrants, and the platform"

EARLY = [
    {"kind": "title", "kicker": "SYSTEM DESIGN  ·  VERSION 0.3.0",
     "title": ["Features, feature sets, models", "and the warrants that bind them"],
     "sub": "MAYA — Model & AI Lifecycle Assurance.  How it is built, and what proves it.",
     "agenda": ["The shape of the thing", "Features and feature sets",
                "Storage and the hash", "Models", "Warrants and evidence",
                "Governance, platform and what is not built"]},

    {"kind": "divider", "num": "1", "title": "The shape of the thing",
     "sub": "Three kinds of object, one spine, and eight principles that decide every design choice after them.",
     "points": ["Definition, version, pin", "The spine end to end", "Eight principles"]},

    {"kind": "table", "kicker": "Domain model", "title": "Every object is a definition, a version or a pin",
     "rows": [["Kind", "What it is", "Addressed as"],
              ["Definition", "A named, mutable-in-draft description of how something is produced", "maya://feature/adj_close_yhoo"],
              ["Version", "An immutable snapshot of a definition, minted when its definition hash changes; classified breaking, behavioral or additive", "maya://feature/adj_close_yhoo@v3"],
              ["Pin", "An immutable materialization of a version: values computed, written to the lake, sealed, never recomputed", "maya://feature/adj_close_yhoo#eom_2026_03"]],
     "col_w": [1.6, 6.4, 3.7],
     "note": "A version freezes how; a pin freezes what. A bare name resolves to the latest approved version, and MAYA logs that resolution, so “latest” never hides in an audit trail (specification §4)."},

    {"kind": "flow", "kicker": "The spine", "title": "Source to bundle, through every surface",
     "steps": [("Source", "Files, read-only SQL, a sandboxed Python producer, or derived"),
               ("Feature", "Definition and versions; pinned into the lake"),
               ("Feature set", "Attribute mapping and alignment; pinned with every member"),
               ("Model", "Formula IR, code, parameters, LaTeX specification"),
               ("Warrants", "Training, then parameter set, then execution"),
               ("Bundle", "Signed; verifies and re-executes offline")],
     "box_h": 1.9,
     "items": ["The whole spine runs through the web UI, the REST API, the Python SDK and the CLI — and the UI is itself an SDK client.",
               "Features and feature sets are closed under their operators: a derived object is an ordinary object and re-enters the same flow.",
               "A composite model is an ordinary model: one warrant over one feature set, however many members it has."]},

    {"kind": "cards", "kicker": "Principles", "title": "Eight rules that bind every design choice",
     "cols": 4,
     "cards": [("1", "Definitions are code", "Data is a consequence, materialized only when asked."),
               ("2", "Immutability is earned by pinning", "Anything pinned is frozen; nothing else claims to be reproducible."),
               ("3", "Everything meaningful is versioned", "Features, sets, models, parameters, warrants, policies, documents."),
               ("4", "Resolution is deterministic", "Byte-identical output, or MAYA reports why it cannot."),
               ("5", "Authorization is on objects", "A role opens a door; an ACL decides which rooms."),
               ("6", "One door to the database", "No SQLAlchemy outside maya.persistence; a gate fails the build."),
               ("7", "Small, replaceable parts", "No non-UI file over 1,500 code lines."),
               ("8", "The platform never silently guesses", "Missing data, ambiguous joins and drift raise typed, explainable errors.")],
     "note": "Specification §1. Principles 6 and 7 are enforced by gates in tools/ci/, not by review."},

    {"kind": "divider", "num": "2", "title": "Features and feature sets",
     "sub": "A feature is a governed, bitemporal dataset from one source. A feature set is a view over features that stores no data of its own until it is pinned.",
     "points": ["Anatomy and the two clocks", "Sources", "Resolution rules and the fill report",
                "The feature algebra", "Feature sets: mapping, alignment, precedence",
                "Pinning, cascade and materialization"]},

    {"kind": "split", "kicker": "Features", "title": "A feature version, and its two clocks",
     "left": {"head": "Anatomy",
              "items": [("Identity", "Name, namespace, owner, tags, description."),
                        ("Schema and index", "Typed attributes, units and semantic tags; the index is required and immutable within a lineage."),
                        ("Source binding, resolution policy, transformation", "How rows arrive and how gaps are filled."),
                        ("Quality contract", "Checks that run on every resolution and always on pin; a failure blocks the pin.")]},
     "right": {"head": "Bitemporal by construction",
               "items": [("Event time", "The date a value is about; part of the index."),
                         ("Knowledge time", "The instant MAYA could first have known it."),
                         ("A restatement is a new row", "Never an overwrite, so “what did we know on 31 March” is a filter."),
                         ("Proved", "tests/test_features.py::test_sc11_point_in_time_after_restatement; tests/test_properties.py::test_a_restatement_never_overwrites.")]},
     "note": "maya/resolution/resolver.py applies the knowledge-time cut first, then the latest knowledge per key, then the grid, then the rules."},

    {"kind": "table", "kicker": "Sources", "title": "Where a feature's rows come from",
     "rows": [["Source", "In 0.3.0", "Proved by"],
              ["csv, parquet, json", "Uploaded files, content-addressed; the inferred schema is a proposal", "tests/test_features.py, tests/test_cli.py::test_quick_upload_and_restatement"],
              ["sql", "A read-only query on an admin-managed connection, typed parameters bound, never interpolated", "tests/test_sql_source.py"],
              ["python", "A producer run in the sandbox; escape hatch that needs approval", "tests/test_python_source.py"],
              ["derived", "An algebra expression over other feature versions or pins, kept in lineage", "tests/test_features.py::test_derived_union_and_inheritance"],
              ["unsupported", "Anything else is refused by name, never approximated", "tests/test_features.py::test_unsupported_source_is_refused_by_name"]],
     "col_w": [1.7, 5.5, 4.5],
     "note": "maya/services/sources.py and maya/services/feature_data.py. Uploads and pulls land in the bitemporal ingest log with a knowledge time. The catalog also accepts a delta source, read through at resolution and stamped with the current time; no test in the suite exercises it."},

    {"kind": "split", "kicker": "Resolution", "title": "Declarative gap filling, bounded and reported",
     "left": {"head": "Grid and rules",
              "items": [("Grid", "as_is, or a shipped calendar: NYSE, LSE, TARGET, ISO business days, natural days."),
                        ("Rules per attribute", "none, forward_fill, backward_fill, linear_interp, spline_interp, constant, mean_of_window, last_known_as_of, zero, previous_period."),
                        ("Bounded", "forward_fill takes a limit and a max_age; beyond either the value stays null."),
                        ("Non-causal rules are marked", "backward_fill and the interpolations consume the future; inside a training set they need a written justification.")]},
     "right": {"head": "What every run emits",
               "items": [("A fill report", "Rows filled per rule and the longest fill run, stored with the pin."),
                         ("Grouped, vectorised rules", "maya/resolution/grouped.py; equal to the per-group rules on 96 randomised cases (tests/test_resolution_grouped.py)."),
                         ("Quality contracts that block", "tests/test_features.py::test_quality_contract_blocks_the_pin."),
                         ("SC-5", "Warm p95 0.98 s without rules, 6.1 s with forward fill on all 50 attributes (docs/BENCHMARKS.md).")]}},

    {"kind": "table", "kicker": "The feature algebra", "title": "Twelve operators, each yielding a definition rather than a result",
     "rows": [["Operator", "Produces", "Operator", "Produces"],
              ["project π", "A subset of attributes", "compose ⋈", "Attributes of both, aligned on the index"],
              ["rename ρ", "Same data, renamed attributes", "coalesce ⊕", "First non-null across ordered inputs"],
              ["transform τ", "A derived feature by pipeline", "aggregate γ", "A coarser index"],
              ["union ∪", "Rows of both, collisions by policy", "lag", "Values shifted by n periods"],
              ["intersect ∩", "Rows whose index is in both", "resample", "A new frequency"],
              ["difference ∖", "Rows of the first absent from the second", "case σ", "Row-wise selection between inputs"]],
     "col_w": [1.6, 4.25, 1.6, 4.25],
     "note": "maya/resolution/algebra.py. Typed at definition time; non-causality propagates; a canonical derivation hash lets MAYA refuse an algebraically identical near-copy. Inheritance (extends) stores a diff, not a copy; the default parent binding is pinned."},

    {"kind": "split", "kicker": "Feature sets", "title": "A view: attributes mapped from members, on one grid",
     "left": {"head": "Mapping and alignment",
              "items": [("Attribute mapping", "Each attribute names its member, the source attribute, an optional cast and overrides."),
                        ("Alignment", "inner, outer, left(member), or asof with a tolerance and direction."),
                        ("Broadcast, stated", "A narrower member index is broadcast and the plan says so."),
                        ("Refused", "A member index with columns the set lacks, unless an aggregation is declared.")]},
     "right": {"head": "Precedence, shown per attribute",
               "items": ["1  Attribute-level override", "2  Member-group override",
                         "3  The set's global policy", "4  Inherited policy, nearest ancestor first",
                         "5  The member feature's own policy", "6  System default: leave null"]},
     "note": "maya/resolution/featureset.py; tests/test_resolution_algebra.py::test_featureset_precedence_layers_and_broadcast and ::test_featureset_refuses_unaggregated_extra_index."},

    {"kind": "bullets", "kicker": "Pinning a feature set", "title": "Every member pinned, or none of them",
     "items": [("A set refuses to pin unless every member is pinned",
                "Cascade pin pins each unpinned member under one name and date, in one transaction; any quality failure rolls the whole cascade back (tests/test_featureset_proofs.py, forty members)."),
               ("Materialization is the namespace's materialize_policy",
                "always (the default) writes the resolved frame; on_demand and never seal the pin by the hash of its output and replay it from the member pins, serving it only if the replay reproduces that hash (tests/test_materialization.py)."),
               ("Withheld, never dropped",
                "A set resolved by someone who cannot read a member returns that attribute named and null."),
               ("Equivalence detected",
                "project(extend(S)) and the directly written set hash identically, and the second is refused as a near-copy.")],
     "note": "Under on_demand or never, a pin is only as readable as its replay: a later MAYA that resolved its inputs differently by one byte would fail the read with integrity_error rather than serve other numbers (README, “Not yet”)."},

    {"kind": "divider", "num": "3", "title": "Storage and the hash",
     "sub": "Three stores, each with one job. The content hash is computed over MAYA's own canonical form, so it means the same thing on every machine that computes it.",
     "points": ["Content-addressed fragments", "The canonical hash", "maya_delta and its two backends",
                "Dependency seams: three polarities"]},

    {"kind": "split", "kicker": "Content-addressed materialization", "title": "A pin is a manifest of fragments, not a copy",
     "left": {"head": "Fragments",
              "items": [("Boundaries by content", "A rolling hash over the rows, so one inserted row leaves every earlier fragment untouched (maya/core/chunker.py)."),
                        ("Shared across pins", "Pinning writes only fragments the store has never seen."),
                        ("SC-12", "An unchanged month costs its delta, under 5% of a full pin (tests/test_features.py::test_sc12_unchanged_month_costs_under_five_percent).")]},
     "right": {"head": "The canonical hash",
               "items": [("Over canonical Arrow values, not file bytes", "Column order ignored; any changed value noticed (tests/test_properties.py)."),
                         ("MAYA's own encoder is authoritative", "maya/core/canonical.py defines the hash; canonical_fast.py computes it a column at a time and is tested equal (tests/test_canonical_fast.py)."),
                         ("SC-1", "A re-pin is byte-identical and changed data is not (tests/test_features.py).")]}},

    {"kind": "table", "kicker": "Lakehouse and seams", "title": "maya_delta, and the rule it is the first instance of",
     "rows": [["Polarity", "Rule", "Examples in 0.3.0"],
              ["Type A: native preferred, pure fallback", "Absence costs throughput, not capability; both sides tested against one contract", "maya_delta (deltalake, or MAYA's own Delta protocol subset), JSON, frames, pushdown, compression, tz database"],
              ["Type B: MAYA's implementation authoritative", "An accelerator that disagrees by one byte is a defect in the accelerator", "The canonical encoder and the fragment chunker"],
              ["Type C: substitutable, never downgraded", "Absence is a refusal with a named reason, never a quiet substitution", "Signing, the sandbox, SSO (SAML without xmlsec fails at startup), object store, job queue"]],
     "col_w": [3.0, 4.0, 4.7],
     "note": "One resolver, maya/core/backends.py, settles every seam at startup; the resolved set is reported and written into every pin's provenance. maya_delta: one conformance suite on both backends, cross-backend reads, unsupported protocol features refused by name (tests/test_maya_delta.py, SC-16)."},
]

SLIDES = EARLY + LATER
