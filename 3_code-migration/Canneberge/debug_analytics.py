"""
debug_analytics.py
Standalone CLI harness for analytics_math.py — validates the Capital
Structure Analytics ratio pack without launching the full PyQt app.

Ratio definitions here are exploratory (see analytics_math.py module
docstring). Batch-mode across a large ticker universe (e.g., S&P 500)
is a planned future extension — loop this same math using real
sourced inputs per ticker to build an empirical baseline dataset for
analytics_page.py's percentile overlay (see
analytics_math.load_empirical_baseline() — SAVE FOR LATER stub).
That loop isn't built yet; this script currently takes manual/CLI
inputs so the math itself can be validated first.

Prints results to console and a timestamped CSV in the current
directory. NOTE: debug/tool CSV output should eventually move to a
shared debug/tool location (matching prototypes/drift_tool's
pattern) — not done yet, kept consistent with other root-level debug
scripts for now.
"""

import argparse
import csv
from datetime import datetime
from pathlib import Path

from Canneberge.Calculations.analytics_math import (
    compute_analytics_ratios,
    interpret_regime,
    shock_leverage,
)


def parse_args():
    p = argparse.ArgumentParser(description="Test Capital Structure Analytics ratios.")
    p.add_argument("--bev", type=float, default=148790.0)
    p.add_argument("--equity-fcfe", type=float, default=117871.0)
    p.add_argument("--book-debt", type=float, default=6657.0)
    p.add_argument("--cash", type=float, default=5626.0)
    p.add_argument("--market-cap", type=float, default=115000.0)
    p.add_argument("--wacc", type=float, default=0.1222)
    p.add_argument("--ke", type=float, default=0.1250)
    p.add_argument("--kd-after-tax", type=float, default=0.0380)
    p.add_argument("--wd-book", type=float, default=0.3806)
    p.add_argument("--tax-rate", type=float, default=0.25)
    p.add_argument("--avg-fcff", type=float, default=8500.0)
    p.add_argument("--avg-interest", type=float, default=250.0)
    p.add_argument("--rc", type=float, default=0.045)
    p.add_argument("--fv-debt", type=float, default=None,
                    help="Fair Value of Debt override (defaults to Book Debt)")
    p.add_argument("--no-csv", action="store_true")
    return p.parse_args()


def main():
    args = parse_args()
    equity_fcff = args.bev - args.book_debt + args.cash

    inputs = dict(
        bev_fcff=args.bev,
        equity_fcfe=args.equity_fcfe,
        equity_fcff=equity_fcff,
        book_debt=args.book_debt,
        cash=args.cash,
        market_cap=args.market_cap,
        wacc=args.wacc,
        ke=args.ke,
        kd_after_tax=args.kd_after_tax,
        wd_book=args.wd_book,
        tax_rate=args.tax_rate,
        avg_fcff=args.avg_fcff,
        avg_interest=args.avg_interest,
        rc=args.rc,
        fv_debt_override=args.fv_debt,
    )

    ratios = compute_analytics_ratios(**inputs)
    regime = interpret_regime(ratios)

    print("=" * 60)
    print("CAPITAL STRUCTURE ANALYTICS — RATIO PACK")
    print("=" * 60)
    for k, v in ratios.items():
        print(f"  {k:15s}: {v:,.4f}" if isinstance(v, float) else f"  {k:15s}: {v}")
    print("-" * 60)
    print(f"Regime: {regime['regime']}")
    if regime["alerts"]:
        print("Alerts:")
        for a in regime["alerts"]:
            print(f"  - {a}")
    print(f"\nNotes:\n{regime['notes']}")
    print("=" * 60)

    shock = shock_leverage(inputs)
    print(f"\nShock sweep computed across {len(shock['x_lam'])} leverage points (0%-60%).")

    if not args.no_csv:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = Path(f"analytics_debug_{ts}.csv")
        with open(out_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["metric", "value"])
            for k, v in ratios.items():
                writer.writerow([k, v])
            writer.writerow([])
            writer.writerow(["lam_shock", "equity_fcff", "equity_fcfe", "pct_residual"])
            for lam, ef, ee, pr in zip(
                shock["x_lam"], shock["y_equity_fcff"],
                shock["y_equity_fcfe"], shock["y_pct_residual"]
            ):
                writer.writerow([lam, ef, ee, pr])
        print(f"CSV written to: {out_path.resolve()}")


if __name__ == "__main__":
    main()