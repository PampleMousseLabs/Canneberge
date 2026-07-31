"""
debug_capital_structure.py
Standalone diagnostic — pulls FRESH StockAnalysis BS + Ratios data
directly (bypasses the running app entirely, no session/cache
involved) and prints every step of the Debt (Book) as % of TIC
calculation for one or more tickers.

Run from 3_code-migration/:
    python -m Canneberge.debug_capital_structure RKLB FLY SOUN

Or with no arguments, uses the TICKERS list below.
"""

import sys

from Canneberge.Sources.stockanalysis import StockAnalysisClient
from Canneberge.Calculations.ratio_catalogue import (
    _build_lookup,
    _CAPSTRUCT_BS_LINE_ITEMS,
    _MARKET_CAP_LINE_ITEM,
    _to_float,
    total_debt,
    tic_book_value,
    total_debt_to_tic,
    market_value_invested_capital,
    debt_to_mvic,
)

TICKERS = ["RKLB", "FLY", "SOUN", "ADBE", "ASTS"]
PERIOD = "TTM"


def fetch_records(client, ticker, statement):
    df = client.fetch_statement(ticker, statement)
    if df is None or df.empty:
        return []
    return df.to_dict("records")


def debug_ticker(ticker, period=PERIOD):
    print("=" * 70)
    print(f"TICKER: {ticker}   PERIOD: {period}")
    print("=" * 70)

    client = StockAnalysisClient()
    bs_records = fetch_records(client, ticker, "BS")
    ratio_records = fetch_records(client, ticker, "Ratios")

    if not bs_records:
        print("  !! No BS records returned at all for this ticker.")
        return
    if not ratio_records:
        print("  !! No Ratios records returned at all for this ticker.")

    bs_lookup = _build_lookup(bs_records, ticker)
    ratio_lookup = _build_lookup(ratio_records, ticker)

    all_bs_periods = set()
    for row_data in bs_lookup.values():
        all_bs_periods.update(row_data.keys())
    print(f"Periods present in BS scrape for {ticker}: {sorted(all_bs_periods)}")

    print("\n--- Raw line items pulled for this period ---")
    raw_bs = {}
    for key, label in _CAPSTRUCT_BS_LINE_ITEMS.items():
        row_data = bs_lookup.get(label, {})
        raw_val = row_data.get(period)
        parsed = _to_float(raw_val)
        raw_bs[key] = parsed
        found = "FOUND" if label in bs_lookup else "MISSING FROM SCRAPE ENTIRELY"
        print(f"  {key:15s} <- SA label '{label}': raw={raw_val!r}  parsed={parsed}  [{found}]")

    market_cap_row = ratio_lookup.get(_MARKET_CAP_LINE_ITEM, {})
    market_cap_raw = market_cap_row.get(period)
    market_cap = _to_float(market_cap_raw)
    mc_found = "FOUND" if _MARKET_CAP_LINE_ITEM in ratio_lookup else "MISSING FROM SCRAPE ENTIRELY"
    print(f"  {'market_cap':15s} <- Ratios label '{_MARKET_CAP_LINE_ITEM}': raw={market_cap_raw!r}  parsed={market_cap}  [{mc_found}]")

    print("\n--- Book-basis calculation (Debt (Book) as a % of TIC) ---")
    debt = total_debt(raw_bs)
    equity = raw_bs.get("total_equity")
    tic = tic_book_value(debt, equity)
    ratio = total_debt_to_tic(debt, tic)
    print(f"  Total Debt = current_ltd + st_debt + current_leases + lt_debt + lt_leases")
    print(f"             = {raw_bs.get('current_ltd')} + {raw_bs.get('st_debt')} + "
          f"{raw_bs.get('current_leases')} + {raw_bs.get('lt_debt')} + {raw_bs.get('lt_leases')}")
    print(f"             = {debt}")
    print(f"  Total Equity (shareholders' equity) = {equity}")
    print(f"  TIC (Book Value) = Debt + Equity = {debt} + {equity} = {tic}")
    print(f"  Debt / TIC (Book) = {debt} / {tic} = {ratio}")

    print("\n--- Market-basis calculation (Debt/MVIC, for reference) ---")
    mvic = market_value_invested_capital(market_cap, debt)
    mvic_ratio = debt_to_mvic(debt, mvic)
    print(f"  MVIC = Market Cap + Total Debt = {market_cap} + {debt} = {mvic}")
    print(f"  Debt / MVIC = {debt} / {mvic} = {mvic_ratio}")
    print()


if __name__ == "__main__":
    tickers = sys.argv[1:] if len(sys.argv) > 1 else TICKERS
    for t in tickers:
        debug_ticker(t)