"""Cross-currency pass (MC-FX-02, MC-FX-04).

Each currency is netted first. A member's position in a currency other than its settlement
currency is then taken over by the FX pseudo-party and converted at the snapshot rate:
the member gets +conv(p) in its settlement currency and the FX party gets -conv(p), using
the same half-even-rounded integer on both sides, so every currency stays exactly zero-sum.
"""

from collections.abc import Mapping
from decimal import Decimal, localcontext

from app.core.money import convert_minor
from app.modules.netting.types import FX_PARTY, FxLeg, PartyKey


class MissingRate(LookupError):
    pass


def lookup_rate(rates: Mapping[tuple[str, str], Decimal], base: str, quote: str) -> Decimal:
    """Direct rate if the table has it, otherwise the inverse of the reverse pair."""
    if (base, quote) in rates:
        return rates[(base, quote)]
    if (quote, base) in rates:
        with localcontext() as ctx:
            ctx.prec = 28
            return Decimal(1) / rates[(quote, base)]
    raise MissingRate(f"{base}->{quote}")


def has_rate(rates: Mapping[tuple[str, str], Decimal], base: str, quote: str) -> bool:
    return base == quote or (base, quote) in rates or (quote, base) in rates


def convert_positions(
    positions: dict[str, dict[PartyKey, int]],
    member_ids: Mapping[PartyKey, object],
    settlement_currency: Mapping[PartyKey, str],
    rates: Mapping[tuple[str, str], Decimal],
    exponents: Mapping[str, int],
) -> list[FxLeg]:
    """Mutates `positions` (currency -> party -> signed minor) in place; returns the legs."""
    legs: list[FxLeg] = []
    for currency in sorted(positions):
        for party in sorted(positions[currency]):
            if party not in member_ids:
                continue
            target = settlement_currency[party]
            amount = positions[currency][party]
            if currency == target or amount == 0:
                continue
            rate = lookup_rate(rates, currency, target)
            converted = convert_minor(
                amount, rate, exponents.get(currency, 2), exponents.get(target, 2)
            )
            positions[currency][party] = 0
            positions[currency][FX_PARTY] = positions[currency].get(FX_PARTY, 0) + amount
            positions.setdefault(target, {})
            positions[target][party] = positions[target].get(party, 0) + converted
            positions[target][FX_PARTY] = positions[target].get(FX_PARTY, 0) - converted
            legs.append(
                FxLeg(
                    member_id=member_ids[party],  # type: ignore[arg-type]
                    from_currency=currency,
                    from_amount_minor=amount,
                    to_currency=target,
                    to_amount_minor=converted,
                    rate=rate,
                )
            )
    return legs
