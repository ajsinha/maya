"""
Documents generated from a model's record: a model card, a validation report, the model's
documentation -- each a Jinja2 Markdown template over a snapshot of the facts MAYA holds,
with any section the template asks for drafted by a language model and labelled as such.

A firm changes a document by placing its own template in ``documents.template_dir``: a file
named like a built-in replaces it, and any other ``*.md.j2`` file there becomes a template
of its own. See ``maya.documents.render``.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

KINDS = ("model_card", "validation_report", "model_documentation")

__all__ = ["KINDS"]
