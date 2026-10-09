"""Shared API shapes: strict request models, the Money object and cursor pages."""

from pydantic import BaseModel, ConfigDict


class StrictModel(BaseModel):
    """Base for request bodies: no type coercion and no unknown fields."""

    model_config = ConfigDict(strict=True, extra="forbid")


class ApiModel(BaseModel):
    """Base for responses."""

    model_config = ConfigDict(from_attributes=True)


class Money(ApiModel):
    amount_minor: int
    currency: str


def money(amount_minor: int, currency: str) -> Money:
    return Money(amount_minor=amount_minor, currency=currency)


class Page[T](ApiModel):
    items: list[T]
    next_cursor: str | None = None
