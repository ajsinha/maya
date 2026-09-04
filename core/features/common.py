"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The vocabulary every feature module shares.

Two clocks, never one. event_ts is when a fact was true in the world;
ingest_ts is when the platform learned it. Keeping both is what makes a
point-in-time assembly answerable rather than plausible: "what did we know, and
when did we know it" is a different question from "what was true".
"""
from __future__ import annotations

VALID_TIME = "event_ts"      # when the fact was true
INGEST_TIME = "ingest_ts"    # when we learned it
ENTITY = "entity_id"

RESERVED = (ENTITY, VALID_TIME, INGEST_TIME)


class FeatureError(RuntimeError):
    """A feature operation was refused. The message always says why."""


def payload(record: dict) -> dict:
    """A record's feature columns — everything that is not a key or a clock."""
    return {k: v for k, v in record.items() if k not in RESERVED}
