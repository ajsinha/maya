"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Sending the same request twice, and two people changing one thing at once.
"""
from core.concurrency.etags import (ETAG_HEADER, IF_MATCH, IF_NONE_MATCH,
                                    PreconditionError, etag_of, matches,
                                    require_match)
from core.concurrency.idempotency import (HEADER, REPLAYED, IdempotencyError,
                                          IdempotencyStore)

__all__ = ["ETAG_HEADER", "HEADER", "IF_MATCH", "IF_NONE_MATCH", "REPLAYED",
           "IdempotencyError", "IdempotencyStore", "PreconditionError",
           "etag_of", "matches", "require_match"]
