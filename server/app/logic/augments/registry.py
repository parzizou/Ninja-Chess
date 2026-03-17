from __future__ import annotations

import random
from app.logic.augments.base import BaseAugment
from app.logic.augments.passive import PASSIVE_AUGMENTS
from app.logic.augments.activable import ACTIVABLE_AUGMENTS

ALL_AUGMENTS: list[BaseAugment] = PASSIVE_AUGMENTS + ACTIVABLE_AUGMENTS

_AUGMENT_MAP: dict[str, BaseAugment] = {a.id: a for a in ALL_AUGMENTS}


def get_augment_by_id(augment_id: str) -> BaseAugment | None:
    return _AUGMENT_MAP.get(augment_id)


def get_random_augments(
    count: int,
    exclude_ids: set[str] | None = None,
    incompatible_ids: set[str] | None = None,
) -> list[BaseAugment]:
    """Pick `count` random augments, excluding already-chosen ones and incompatible ones."""
    exclude_ids = exclude_ids or set()
    incompatible_ids = incompatible_ids or set()

    # Build the set of IDs that can't be proposed
    blocked = set(exclude_ids)
    for aug in ALL_AUGMENTS:
        if aug.id in incompatible_ids:
            # This augment is already owned — block its incompatible list
            for incompat in aug.incompatible_with:
                blocked.add(incompat)

    pool = [a for a in ALL_AUGMENTS if a.id not in blocked]
    if len(pool) <= count:
        return pool[:]
    return random.sample(pool, count)
