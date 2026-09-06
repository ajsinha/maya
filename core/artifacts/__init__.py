"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Where a serialised model lives, addressed by what it is rather than where it was put.
"""
from core.artifacts.common import (EXECUTES_ON_LOAD, FORMAT_MEANING, FORMATS,
                                   MAX_BYTES, ArtifactError,
                                   is_content_address)
from core.artifacts.store import ArtifactStore

__all__ = [
                                   "EXECUTES_ON_LOAD",
                                   "FORMATS",
                                   "FORMAT_MEANING",
                                   "MAX_BYTES",
                                   "ArtifactError",
                                   "ArtifactStore",
                                   "is_content_address",
]
