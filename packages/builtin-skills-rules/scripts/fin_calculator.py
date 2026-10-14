"""NPV, IRR, and payback for a cashflow series. Implements: REQ-015."""

import argparse
import json
import sys


def net_present_value(cashflows: list[float], rate: float) -> float:
    return sum(amount / ((1 + rate) ** period) for period, amount in enumerate(cashflows))


def internal_rate_of_return(cashflows: list[float]) -> float | None:
    low = -0.99
    high = 10.0
    if net_present_value(cashflows, low) * net_present_value(cashflows, high) > 0:
        return None
    for _ in range(80):
        mid = (low + high) / 2
        if net_present_value(cashflows, mid) > 0:
            low = mid
        else:
            high = mid
    return (low + high) / 2


def payback_periods(cashflows: list[float]) -> float | None:
    cumulative = 0.0
    for period, amount in enumerate(cashflows):
        previous = cumulative
        cumulative += amount
        if period > 0 and previous < 0 <= cumulative and amount != 0:
            return (period - 1) + (-previous / amount)
        if cumulative >= 0 and period > 0 and previous < 0:
            return float(period)
    if cumulative >= 0:
        return 0.0
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Compute NPV, IRR, and payback")
    parser.add_argument("--cashflows", required=True, help="Comma-separated amounts, period 0 first")
    parser.add_argument("--rate", required=True, type=float, help="Discount rate as a decimal, e.g. 0.08")
    args = parser.parse_args()
    cashflows = [float(part) for part in args.cashflows.split(",") if part.strip()]
    if len(cashflows) < 2:
        print(json.dumps({"error": "at least two cashflow periods are required"}, ensure_ascii=False))
        return 2
    irr = internal_rate_of_return(cashflows)
    payback = payback_periods(cashflows)
    print(
        json.dumps(
            {
                "npv": round(net_present_value(cashflows, args.rate), 2),
                "irr": None if irr is None else round(irr, 6),
                "payback_periods": None if payback is None else round(payback, 4),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
