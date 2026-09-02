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

def debug_ticker_all_periods(ticker):
    from Canneberge.Calculations.ratio_catalogue import (
        total_debt, market_value_invested_capital, debt_to_mvic, historic_average,
    )

    print("=" * 70)
    print(f"TICKER: {ticker}   — ALL PERIODS (Historic Capital Structure trace)")
    print("=" * 70)

    client = StockAnalysisClient()
    bs_records = fetch_records(client, ticker, "BS")
    ratio_records = fetch_records(client, ticker, "Ratios")

    bs_lookup = _build_lookup(bs_records, ticker)
    ratio_lookup = _build_lookup(ratio_records, ticker)

    all_bs_periods = set()
    for row_data in bs_lookup.values():
        all_bs_periods.update(row_data.keys())
    all_ratio_periods = set()
    for row_data in ratio_lookup.values():
        all_ratio_periods.update(row_data.keys())

    print(f"Periods present in BS scrape:     {sorted(all_bs_periods)}")
    print(f"Periods present in Ratios scrape: {sorted(all_ratio_periods)}")

    periods_to_check = ["TTM", "LFY", "LFY-1", "LFY-2", "LFY-3", "LFY-4"]
    per_period_ratio = {}

    print(f"\n{'Period':10s} {'TotalDebt':>12s} {'MktCap':>12s} {'MVIC':>12s} {'Debt/MVIC':>12s}")
    for period in periods_to_check:
        raw_bs = {}
        for key, label in _CAPSTRUCT_BS_LINE_ITEMS.items():
            raw_bs[key] = _to_float(bs_lookup.get(label, {}).get(period))
        debt = total_debt(raw_bs)
        market_cap = _to_float(ratio_lookup.get(_MARKET_CAP_LINE_ITEM, {}).get(period))
        mvic = market_value_invested_capital(market_cap, debt)
        ratio = debt_to_mvic(debt, mvic)
        per_period_ratio[period] = ratio
        print(f"{period:10s} {str(debt):>12s} {str(market_cap):>12s} {str(mvic):>12s} {str(ratio):>12s}")

    two_yr = periods_to_check[:3]   # TTM, LFY, LFY-1
    five_yr = periods_to_check      # TTM through LFY-4

    two_yr_avg = historic_average(per_period_ratio, two_yr)
    five_yr_avg = historic_average(per_period_ratio, five_yr)

    print(f"\n2yr periods used: {two_yr}")
    print(f"2yr average = {two_yr_avg}")
    print(f"\n5yr periods used: {five_yr}")
    print(f"5yr average = {five_yr_avg}")

if __name__ == "__main__":
    tickers = sys.argv[1:] if len(sys.argv) > 1 else TICKERS
    for t in tickers:
        debug_ticker(t)
        debug_ticker_all_periods(t)