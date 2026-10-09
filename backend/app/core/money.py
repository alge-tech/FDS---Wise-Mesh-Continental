"""Money helpers. Amounts are int minor units end to end; rates are Decimal; float never appears."""

import re
from collections.abc import Mapping, Sequence
from decimal import ROUND_HALF_EVEN, Decimal, localcontext

_AMOUNT_RE = re.compile(r"^(?P<sign>-)?(?P<int>\d+)(?:\.(?P<frac>\d+))?$")


class MoneyParseError(ValueError):
    pass


def parse_minor(text: str, exponent: int, *, allow_negative: bool = False) -> int:
    """Parse a plain decimal string ("1234.50") straight to minor units.

    Rejects exponents, thousands separators, signs (unless allowed) and more
    decimal places than the currency has, so no rounding ever happens on input.
    """
    raw = text.strip()
    m = _AMOUNT_RE.match(raw)
    if not m:
        raise MoneyParseError("must be a plain decimal number such as 1234.50")
    if m.group("sign") and not allow_negative:
        raise MoneyParseError("must not be negative")
    frac = m.group("frac") or ""
    if len(frac) > exponent:
        raise MoneyParseError(f"has more than {exponent} decimal places")
    scale: int = 10**exponent
    minor = int(m.group("int")) * scale + int(frac.ljust(exponent, "0") or "0")
    return -minor if m.group("sign") else minor


def format_minor(amount_minor: int, exponent: int) -> str:
    """Integer minor units to a plain decimal string, for CSV templates and logs."""
    sign = "-" if amount_minor < 0 else ""
    digits = str(abs(amount_minor)).rjust(exponent + 1, "0")
    if exponent == 0:
        return f"{sign}{digits}"
    return f"{sign}{digits[:-exponent]}.{digits[-exponent:]}"


def round_half_even(value: Decimal) -> int:
    """Round a Decimal amount of minor units to an int, half-even (the one rounding rule)."""
    with localcontext() as ctx:
        ctx.prec = 50
        return int(value.quantize(Decimal(1), rounding=ROUND_HALF_EVEN))


def convert_minor(amount_minor: int, rate: Decimal, from_exponent: int, to_exponent: int) -> int:
    """Convert minor units of one currency into another at `rate` (quote per base), half-even."""
    with localcontext() as ctx:
        ctx.prec = 50
        scaled = Decimal(amount_minor) * rate * (Decimal(10) ** (to_exponent - from_exponent))
        return round_half_even(scaled)


def apply_bps(amount_minor: int, bps: int) -> Decimal:
    """Exact (unrounded) basis-point share of an amount, as a Decimal of minor units."""
    with localcontext() as ctx:
        ctx.prec = 50
        return Decimal(amount_minor) * Decimal(bps) / Decimal(10_000)


def allocate_largest_remainder[K](
    total: int, weights: Mapping[K, int], order: Sequence[K] | None = None
) -> dict[K, int]:
    """Split `total` in proportion to non-negative integer weights so the parts sum to `total`.

    Each part is floor(total * w / W); the leftover units go one each to the largest
    remainders, ties broken by `order` (or by the mapping's iteration order). A part never
    exceeds ceil(total * w / W), so no part exceeds its weight when total <= sum(weights).
    """
    if total < 0:
        raise ValueError("total must be non-negative")
    keys = list(order) if order is not None else list(weights)
    weight_sum = sum(weights[k] for k in keys)
    if weight_sum == 0:
        if total:
            raise ValueError("cannot allocate a positive total over zero weights")
        return dict.fromkeys(keys, 0)
    parts: dict[K, int] = {}
    remainders: list[tuple[int, int, K]] = []
    for idx, k in enumerate(keys):
        w = weights[k]
        if w < 0:
            raise ValueError("weights must be non-negative")
        q, r = divmod(total * w, weight_sum)
        parts[k] = q
        remainders.append((-r, idx, k))
    leftover = total - sum(parts.values())
    for _, _, k in sorted(remainders)[:leftover]:
        parts[k] += 1
    return parts
