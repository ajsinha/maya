"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Attached documents.

The other half of documentation: the ones somebody wrote, filed against the
version they describe, stored by digest so they cannot be edited in place, and
accepted by somebody other than whoever filed them.
"""
from core.attachments.common import (KIND_MEANING, KINDS, STATES, TEXT_MEDIA,
                                     AttachmentError)
from core.attachments.register import AttachmentRegister
from core.attachments.store import DocumentStore

__all__ = [
                                     "KINDS",
                                     "KIND_MEANING",
                                     "STATES",
                                     "TEXT_MEDIA",
                                     "AttachmentError",
                                     "AttachmentRegister",
                                     "DocumentStore",
]
