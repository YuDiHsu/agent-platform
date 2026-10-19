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


SCENARIOS = (("保守", 0.8), ("基準", 1.0), ("樂觀", 1.2))


def scaled_inflows(cashflows: list[float], factor: float) -> list[float]:
    """Scale every inflow after period 0; the initial outlay stays fixed."""

    return [cashflows[0], *[amount * factor for amount in cashflows[1:]]]


def summarize(cashflows: list[float], rate: float) -> dict[str, float | None]:
    irr = internal_rate_of_return(cashflows)
    payback = payback_periods(cashflows)
    return {
        "npv": round(net_present_value(cashflows, rate), 2) + 0.0,
        "irr": None if irr is None else round(irr, 6),
        "payback_periods": None if payback is None else round(payback, 4),
    }


def scenario_table(scenarios: list[dict[str, object]]) -> str:
    lines = ["| 情境 | NPV | IRR | 回收期 |", "| --- | --- | --- | --- |"]
    for row in scenarios:
        irr = row["irr"]
        payback = row["payback_periods"]
        irr_text = "無解" if irr is None else f"{float(irr) * 100:.2f}%"  # type: ignore[arg-type]
        payback_text = "未回收" if payback is None else f"{float(payback):.2f}"  # type: ignore[arg-type]
        lines.append(f"| {row['name']} | {float(row['npv']):.2f} | {irr_text} | {payback_text} |")  # type: ignore[arg-type]
    return "\n".join(lines)


def glue_option_values(argv: list[str]) -> list[str]:
    """Turn `--cashflows -100,110` into `--cashflows=-100,110` so a negative period 0 is read as a value."""

    glued: list[str] = []
    index = 0
    while index < len(argv):
        if argv[index] in {"--cashflows", "--rate"} and index + 1 < len(argv):
            glued.append(f"{argv[index]}={argv[index + 1]}")
            index += 2
            continue
        glued.append(argv[index])
        index += 1
    return glued


def main() -> int:
    parser = argparse.ArgumentParser(description="Compute NPV, IRR, and payback")
    parser.add_argument("--cashflows", required=True, help="Comma-separated amounts, period 0 first")
    parser.add_argument("--rate", required=True, type=float, help="Discount rate as a decimal, e.g. 0.08")
    args = parser.parse_args(glue_option_values(sys.argv[1:]))
    cashflows = [float(part) for part in args.cashflows.split(",") if part.strip()]
    if len(cashflows) < 2:
        print(json.dumps({"error": "at least two cashflow periods are required"}, ensure_ascii=False))
        return 2
    scenarios: list[dict[str, object]] = [
        {"name": name, **summarize(scaled_inflows(cashflows, factor), args.rate)} for name, factor in SCENARIOS
    ]
    print(
        json.dumps(
            {
                **summarize(cashflows, args.rate),
                "scenarios": scenarios,
                "scenario_table": scenario_table(scenarios),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
