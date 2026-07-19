"""Query parameters for storefront product APIs."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from marketplace_taxonomy import MARKETPLACE_CATEGORY_IDS

_LISTING_SLUG = "landings"
_ALLOWED = frozenset(MARKETPLACE_CATEGORY_IDS) | {_LISTING_SLUG}


class ProductListQuery(BaseModel):
    category: Optional[str] = Field(
        None,
        max_length=64,
        description="Filter by marketplace category or 'landings'",
    )

    def normalized_category(self) -> Optional[str]:
        if self.category is None:
            return None
        c = self.category.strip().lower()
        if not c:
            return None
        if c not in _ALLOWED:
            raise ValueError(f"Unknown category: {c}")
        return c
