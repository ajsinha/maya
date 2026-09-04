"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Feature dimensionality.

A feature is not always a number. A yield curve is a vector, a correlation
structure is a matrix, an embedding is a vector nobody can read, and a scenario
grid is a tensor. Storing all of them as "numeric" and hoping the consumer knows
better is how a model receives ten tenors where it expected eleven and produces
an answer rather than an error.

So a feature carries a **shape** and, along its first axis, optional
**component names**.

    ()            a scalar          dscr
    (10,)         a vector          the curve at ten tenors
    (10, 10)      a matrix          the correlation between them
    (5, 10, 10)   a tensor          that matrix under five scenarios

The component names are what make composition mean something. "Add a tenor",
"drop the 50-year point", "override the 3-month with an OIS-based one" are
operations on *named* things; on an anonymous array they are operations on an
index, and an index is not a meaning.

A shape is checked against the values that arrive, because a declared shape
nobody verifies is a comment.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

from core.features.common import FeatureError
from core.log import get_logger

logger = get_logger(__name__)

SCALAR: Tuple[int, ...] = ()

# Beyond this a "feature" is a dataset with a name, and the platform is better
# off saying so than pretending the catalogue is the right home for it.
MAX_RANK = 4
MAX_AXIS = 100_000


def parse(shape: Any) -> Tuple[int, ...]:
    """A shape from whatever a caller supplied. None and () are both scalar."""
    if shape is None or shape == "" or shape == []:
        return SCALAR
    if isinstance(shape, int):
        shape = (shape,)
    if isinstance(shape, str):
        try:
            shape = tuple(int(part) for part in shape.replace(" ", "").split(",")
                          if part)
        except ValueError as exc:
            logger.info("rejected '%s' as a shape: %s", shape, exc)
            raise FeatureError(
                f"'{shape}' is not a shape; a shape is a comma-separated list of "
                f"positive integers, and an empty one means a scalar") from exc
    dims = tuple(int(d) for d in shape)
    if len(dims) > MAX_RANK:
        raise FeatureError(
            f"a rank-{len(dims)} feature is a dataset with a name; the catalogue "
            f"holds up to rank {MAX_RANK}, and beyond that a feature view of its "
            f"own is the honest home")
    for axis, size in enumerate(dims):
        if size <= 0:
            raise FeatureError(
                f"axis {axis} has size {size}; a dimension with no extent is not "
                f"a dimension, and a scalar is spelled as the empty shape")
        if size > MAX_AXIS:
            raise FeatureError(f"axis {axis} has {size:,} entries; the limit is "
                               f"{MAX_AXIS:,} per axis")
    return dims


def rank(shape: Sequence[int]) -> int:
    return len(tuple(shape))


def cells(shape: Sequence[int]) -> int:
    """How many numbers one row of this feature holds."""
    total = 1
    for size in shape:
        total *= size
    return total


def kind(shape: Sequence[int]) -> str:
    """What to call it, for a person reading a page."""
    return {0: "scalar", 1: "vector", 2: "matrix"}.get(len(tuple(shape)), "tensor")


def describe(shape: Sequence[int], components: Optional[Sequence[str]] = None
             ) -> Dict[str, Any]:
    dims = tuple(shape)
    return {"shape": list(dims), "rank": len(dims), "kind": kind(dims),
            "cells": cells(dims), "components": list(components or []),
            "detail": _detail(dims, components)}


def _detail(dims: Tuple[int, ...], components: Optional[Sequence[str]]) -> str:
    if not dims:
        return "a scalar: one number per row"
    shape = " × ".join(str(d) for d in dims)
    named = (f", the first axis named {', '.join(components[:4])}"
             + ("…" if len(components) > 4 else "")) if components else ""
    return f"a {kind(dims)} of {shape} — {cells(dims):,} numbers per row{named}"


def check_components(shape: Sequence[int],
                     components: Optional[Sequence[str]]) -> List[str]:
    """Component names must name the first axis, exactly once each."""
    dims = tuple(shape)
    names = list(components or [])
    if not names:
        return []
    if not dims:
        raise FeatureError(
            "a scalar has no axis to name; components describe the first "
            "dimension, and a scalar does not have one")
    if len(names) != dims[0]:
        raise FeatureError(
            f"{len(names)} component names for an axis of {dims[0]}; naming some "
            f"entries and not others leaves the rest identified only by "
            f"position, which is what the names exist to avoid")
    if len(set(names)) != len(names):
        duplicated = sorted({n for n in names if names.count(n) > 1})
        raise FeatureError(
            f"these component names appear twice: {', '.join(duplicated)}; an "
            f"operation naming one of them would be ambiguous")
    return names


def conforms(value: Any, shape: Sequence[int]) -> Tuple[bool, str]:
    """Does one value have the declared shape? Reported, not assumed."""
    dims = tuple(shape)
    if not dims:
        if isinstance(value, (list, tuple)):
            return False, "the feature is a scalar and the value is a sequence"
        return True, "scalar"
    found = _measure(value)
    if found is None:
        return False, (f"the feature is a {kind(dims)} of "
                       f"{' × '.join(str(d) for d in dims)} and the value is not "
                       f"a sequence")
    if found != dims:
        return False, (f"expected {' × '.join(str(d) for d in dims)}, got "
                       f"{' × '.join(str(d) for d in found)}")
    return True, kind(dims)


def _measure(value: Any) -> Optional[Tuple[int, ...]]:
    """The shape of a nested sequence, or None if it is ragged or not one."""
    if not isinstance(value, (list, tuple)):
        return None
    dims: List[int] = [len(value)]
    if not value:
        return tuple(dims)
    first = value[0]
    if isinstance(first, (list, tuple)):
        inner = _measure(first)
        if inner is None:
            return None
        for other in value[1:]:
            if _measure(other) != inner:
                return None                    # ragged: not a tensor at all
            
        dims.extend(inner)
    else:
        if any(isinstance(other, (list, tuple)) for other in value):
            return None
    return tuple(dims)


def check_rows(rows: Sequence[Dict[str, Any]], name: str,
               shape: Sequence[int], sample: int = 100) -> None:
    """Refuse values that do not have the shape the feature declares.

    Sampled rather than exhaustive, because a declared shape that is right for
    the first hundred rows and wrong for the millionth is a data problem the
    quality report will surface; what this catches is the systematic case, where
    somebody is loading a different thing under the same name.
    """
    dims = tuple(shape)
    for index, row in enumerate(rows[:sample]):
        if name not in row or row[name] is None:
            continue
        ok, why = conforms(row[name], dims)
        if not ok:
            raise FeatureError(
                f"row {index}: '{name}' does not have its declared shape — {why}. "
                f"a shape nobody checks is a comment, and a model given ten "
                f"tenors where it expected eleven produces an answer rather than "
                f"an error")
