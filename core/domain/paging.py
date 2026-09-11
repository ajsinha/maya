"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

One shape for every list the API returns.

No endpoint paginated. `GET /models` returned the whole inventory, and the
architecture document targets estates of a hundred thousand models — so the
first honest deployment would have handed a browser a response it could not
render and a client a page it could not stream.

Three decisions worth stating, because each of them is a trade:

  * **A cap that cannot be raised past a maximum.** A caller asking for
    everything gets the maximum and is *told* they did, in `returned` and
    `total`. Silently truncating is how a client concludes there are 200 models
    when there are 12,000.
  * **The filter runs before the page.** Scope filtering must never be applied
    to a page, because then page two of a filtered list is page two of the
    unfiltered one with holes in it — and a model out of scope becomes
    discoverable by a count that does not add up.
  * **Offsets here, cursors where the list grows at the head.** A governance
    register is mostly read by people who want page four, and an offset is what
    says "page four". That argument holds for every listing this module covers
    and stops exactly where the list is being **written to while somebody walks
    it** — the discovery queue, where a scanner posts candidates while a triager
    works down them. There an offset silently skips a row: the insert shifts
    everything down, page two starts one past where page one ended, and the
    caller receives a complete-looking queue with a hole in it. `core/http/
    conventions.py` holds the keyset cursor for those, and bulk feature
    transfer already had one.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

DEFAULT_LIMIT = 50
MAX_LIMIT = 500


@dataclass(frozen=True)
class Page:
    """A slice of a list, and enough for a caller to ask for the next one."""
    rows: List[Any]
    total: int
    limit: int
    offset: int

    @property
    def has_more(self) -> bool:
        return self.offset + len(self.rows) < self.total

    def as_dict(self, key: str = "rows") -> Dict[str, Any]:
        return {
            key: self.rows,
            "total": self.total,
            "returned": len(self.rows),
            "limit": self.limit,
            "offset": self.offset,
            "has_more": self.has_more,
            "detail": self._detail(),
        }

    def _detail(self) -> str:
        if self.total == 0:
            return "nothing matched"
        first = self.offset + 1 if self.rows else self.offset
        return (f"{first:,}–{self.offset + len(self.rows):,} of {self.total:,}"
                + ("; ask for the next page with "
                   f"offset={self.offset + self.limit}" if self.has_more else ""))


def page(rows: Sequence[Any], limit: Optional[int] = None,
         offset: Optional[int] = None) -> Page:
    """Slice a list that has already been filtered.

    Already filtered, because the alternative is a page of the wrong list.
    """
    size = DEFAULT_LIMIT if limit is None else max(1, min(int(limit), MAX_LIMIT))
    start = max(0, int(offset or 0))
    return Page(list(rows[start:start + size]), len(rows), size, start)
