from decimal import ROUND_HALF_UP, Decimal

MONEY_QUANTUM = Decimal("0.00000001")


def money(value: Decimal) -> Decimal:
    return value.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)
