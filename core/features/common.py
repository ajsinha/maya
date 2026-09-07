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

from typing import Tuple

VALID_TIME = "event_ts"      # when the fact was true
INGEST_TIME = "ingest_ts"    # when we learned it
ENTITY = "entity_id"

RESERVED = (ENTITY, VALID_TIME, INGEST_TIME)


class FeatureError(RuntimeError):
    """A feature operation was refused. The message always says why.

    `remediation` is optional and usually absent, because most of these are
    about a definition and the generic line fits. It exists for the ones where
    it does not: `routes/base.py` maps every uncaught FeatureError to "correct
    the feature definition or the view version and retry", so asking "why can I
    not delete this featureset?" was answered with an instruction about a
    different object entirely.
    """

    def __init__(self, detail: str, remediation: str = ""):
        super().__init__(detail)
        self.detail, self.remediation = detail, remediation


#: The dtypes a form should OFFER. Not a constraint — `feature_author_define`
#: says so on the page, and the register accepts anything a bank calls a type.
#:
#: Published here because two forms carried their own list and they disagreed:
#: `/features` offered `boolean` and `/features/new` did not, so whether a
#: feature could be boolean depended on which screen you happened to open. A
#: suggestion is still a vocabulary, and two of them is two vocabularies.
#:
#: Ordered by how often a model actually reads one.
SUGGESTED_DTYPES: Tuple[str, ...] = (
    "numeric", "integer", "categorical", "boolean", "string", "date", "datetime",
)


def payload(record: dict) -> dict:
    """A record's feature columns — everything that is not a key or a clock."""
    return {k: v for k, v in record.items() if k not in RESERVED}


# The point-in-time tie-break, re-exported rather than reimplemented. It lives
# in `db.delta_store` because `db` may not import `core`, and the store's own
# as-of read has to apply the identical order — two copies of this rule is
# exactly how the two paths came to disagree in the first place.
from db.delta_store import pit_order_key  # noqa: F401
