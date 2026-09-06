"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Documentation.

Documents are compiled from the register and the evidence graph. Split by
responsibility: the vocabulary, the lenses (one section each, and what it
reads), the templates (which lenses make which document), and the compiler.
"""
from core.docs.common import (ALL_KINDS, ANNEX_IV, KINDS, MODEL_CARD,
                              MODEL_DEVELOPMENT, TRAINING_RECORD,
                              TITLES, VALIDATION_REPORT, DocumentError)
from core.docs.compiler import DocumentCompiler
from core.docs.context import ContextBuilder
from core.docs.lenses import Lens
from core.docs.templates import TEMPLATES

from core.docs.dossier import Dossier
from core.docs.subjects import SUBJECTS, SUBJECT_MEANING
from core.docs.training import TrainingRecordCompiler

__all__ = [
                              "ALL_KINDS",
                              "ANNEX_IV",
                              "KINDS",
                              "MODEL_CARD",
                              "MODEL_DEVELOPMENT",
                              "SUBJECTS",
                              "SUBJECT_MEANING",
                              "TEMPLATES",
                              "TITLES",
                              "TRAINING_RECORD",
                              "VALIDATION_REPORT",
                              "ContextBuilder",
                              "DocumentCompiler",
                              "DocumentError",
                              "Dossier",
                              "Lens",
                              "TrainingRecordCompiler",
]
