from datetime import UTC, datetime
from uuid import UUID

import uuid6


def new_id() -> UUID:
    """UUIDv7, generated in the app so IDs sort by creation time."""
    return UUID(int=uuid6.uuid7().int)


def utcnow() -> datetime:
    return datetime.now(UTC)
