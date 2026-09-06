"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The fibration, made total.

`docs/00 §8` treats indexed families as fibrations, and `L-15` asserts the one
property that makes the extension claim mean anything: **no fibre is empty.**
Every class has an evidence schema, a lifecycle, a metric set and a template
set, so introducing a new kind of model is supplying a fibre and *nothing else*
— no migration, no new table, no new screen.

For twenty-one milestones that was structure without a gate. `docs/00 §12` said
so plainly — *"the structure is real and the totality gate is not, and those are
different claims"* — and it is the difference between an architecture that
admits a quantum optimiser and one that admits a typo.

## What the base is, and why it changed

`L-15` and `docs/00 §8` both say the base is the **model class**. It is not, and
the documents were reaching for the right structure through the wrong index.

`model_class` is a free-text column: a person types `rates`, or `credit`, or
`c`. Requiring a total fibre over free text leaves two options, and both are
bad. Close the vocabulary, and *"adding a class adds a fibre — no migration"*
becomes false, because adding one now needs a release. Leave it open, and the
totality gate can be defeated by typing a word nobody has registered — which is
a gate that reports success.

The base is the **trainability class**, `T0`…`T8`. It is *derived* from how `P`
is inhabited and never declared, so the index cannot be typed wrong, cannot be
extended by accident, and cannot disagree with the model it indexes. And the
fibre content already existed, written out class by class in `docs/02 §5` —
what conceptual soundness rests on, what outcomes analysis is, what monitoring
can answer — which is a good sign that this was the real base all along.
`docs/02` even labels the T-classes "typical fibre" in its bindings table.

`model_class` keeps its job: an organisational label, for grouping the estate
and reporting on it. It indexes nothing.
"""
from __future__ import annotations

from typing import Dict, Tuple


class FibreError(RuntimeError):
    """A fibre is incomplete, or a class has none. The message says which."""

    def __init__(self, code: str, detail: str, remediation: str = ""):
        super().__init__(detail)
        self.code, self.detail, self.remediation = code, detail, remediation

    def as_problem(self) -> Dict[str, str]:
        """The refusal body. Same shape as every other refusal in the platform.

        Required by `routes/base.py::guard`, and its absence is not a
        theoretical concern: an error class in the guard tuple without this
        method reaches the caller as a 500 raised *inside the error handler*,
        so the refusal and its remediation are both lost and the log says
        `AttributeError`.
        """
        return {"error": self.code, "detail": self.detail,
                "remediation": self.remediation}


#: The four facets `L-15` names. A fibre missing any one of them is partial, and
#: a partial fibre is what the startup gate refuses to boot on.
FACETS: Tuple[str, ...] = ("evidence", "lifecycle", "metrics", "templates")

#: The base of the fibration. Derived, never declared — see the module docstring.
BASE: Tuple[str, ...] = tuple(f"T{n}" for n in range(9))
