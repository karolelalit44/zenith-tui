"""Arithmetic helpers demonstrating a clean module style.

Exposes a single pure function for sum/product calculation plus a thin
reporting wrapper. Pure computation is separated from I/O so it can be unit
tested without stdout capture.
"""

from __future__ import annotations

from typing import Optional


def calculate_sum_and_product(a: Optional[int] = 0, b: Optional[int] = 0) -> dict[str, int]:
    """Return the sum and product of two integers, treating None as zero.

    Args:
        a: First operand; ``None`` is treated as 0.
        b: Second operand; ``None`` is treated as 0.

    Returns:
        ``{"sum": a + b, "product": a * b}``.

    Examples:
        >>> calculate_sum_and_product(3, 4)
        {'sum': 7, 'product': 12}
        >>> calculate_sum_and_product(None, 4)
        {'sum': 4, 'product': 0}
    """
    left = a or 0
    right = b or 0
    return {"sum": left + right, "product": left * right}


def report(a: int, b: int) -> dict[str, int]:
    """Compute the result and print a human-readable summary.

    Args:
        a: First operand.
        b: Second operand.

    Returns:
        The computed result, for callers that want to reuse it.
    """
    result = calculate_sum_and_product(a, b)
    print(f"sum: {result['sum']}")
    print(f"product: {result['product']}")
    return result
