"""
debug_reverse_dcf.py
Run: python -m Canneberge.debug_reverse_dcf PLTR
"""

import sys
from Canneberge.Sources.stockanalysis import StockAnalysisClient
from Canneberge.Sources.fred import FREDClient
from Canneberge.Sources.beta_vol import BetaVolClient
from Canneberge.Services.source_data_service import SourceDataService
from Canneberge import config
from Canneberge.Calculations.gpc_multiples import _build_lookup, _to_float, get_ticker_metric
from Canneberge.Calculations.ratio_catalogue import debt_free_nwc_excl_cash, debt_free_nwc_incl_cash
from Canneberge.Ui.wacc_page import BETA_COLUMN_MAP
from Canneberge.Calculations.reverse_dcf import compute_cost_of_equity, build_fcfe_schedule, compute_reconciliation_a, solve_gordon_growth_ltgr, solve_h_model

TICKERS = ["ADBE"]
NFY_YEAR = 2026
NWC_EXCLUDE_CASH = True
BETA_TYPE = "Raw Betas"
BETA_FREQUENCY = "5-Year Monthly"
EQUITY_RISK_PREMIUM = 0.05
BETA_HISTORY_YEARS = 5.0
VOL_TERM_YEARS = 3.0
VALUATION_DATE = "8/21/2026"
INDEX_TICKER = "^GSPC"
MARKET_CAP_LINE_ITEM = "market capitalization"
NET_INCOME_LINE_ITEM = "net income"
REVENUE_LINE_ITEM = "revenue"
DA_CFS_LINE_ITEM = "depreciation & amortization"
CAPEX_LINE_ITEM = "capital expenditures"
FORCE_TERMINAL_CAPEX_EQUALS_DA = True
H_MODEL_GA = 0.15
H_MODEL_GN = 0.03
H_MODEL_H = 6.0
H_IS_FULL_PERIOD = True

def _fmt_currency(v): return f"{v:,.2f}" if v is not None else "-"
def _fmt_pct(v): return f"{v * 100:.2f}%" if v is not None else "-"
def _fmt_beta(v): return f"{v:.4f}" if v is not None else "-"
def _fmt_growth(v): return f"{v * 100:.2f}%" if v is not None else "-"
def _fmt_years(v): return f"{v:.2f}" if v is not None else "-"

def fetch_records(client, ticker, statement):
    df = client.fetch_statement(ticker, statement)
    if df is None or df.empty:
        return []
    return df.to_dict("records")

def get_risk_free_rate(fred_rows):
    for row in fred_rows:
        if str(row.get("SeriesID", "")).strip().upper() == "DGS20":
            val = _to_float(row.get("LatestValue"))
            return val / 100.0 if val is not None else None
    return None

def get_observed_beta(ticker, beta_vol_rows):
    beta_col = BETA_COLUMN_MAP.get((BETA_TYPE, BETA_FREQUENCY))
    if beta_col is None:
        return None
    beta_lookup = {}
    for row in beta_vol_rows:
        t = str(row.get("Ticker", "")).strip().upper()
        if t:
            beta_lookup[t] = row
    return _to_float(beta_lookup.get(ticker.upper(), {}).get(beta_col))

def debug_ticker(ticker):
    print("=" * 76)
    print(f"REVERSE DCF BLUE INPUTS — {ticker.upper()}  [H full={H_IS_FULL_PERIOD}]")
    print("=" * 76)
    flags = []
    sa_client = StockAnalysisClient()
    is_rows = fetch_records(sa_client, ticker, "IS")
    bs_rows = fetch_records(sa_client, ticker, "BS")
    cfs_rows = fetch_records(sa_client, ticker, "CFS")
    ratio_rows = fetch_records(sa_client, ticker, "Ratios")
    is_lookup = _build_lookup(is_rows, ticker)
    bs_lookup = _build_lookup(bs_rows, ticker)
    cfs_lookup = _build_lookup(cfs_rows, ticker)
    ratio_lookup = _build_lookup(ratio_rows, ticker)
    market_cap = _to_float(ratio_lookup.get(MARKET_CAP_LINE_ITEM, {}).get("TTM"))
    if market_cap is None:
        flags.append("Market Cap missing")
    print(f"Market Cap:                           {_fmt_currency(market_cap)}\n")
    print("N Cash Flow Years:                    3")
    print(f"H Short Term Years (assumed):          {_fmt_years(H_MODEL_H)}  h_eff={_fmt_years(H_MODEL_H/2 if H_IS_FULL_PERIOD else H_MODEL_H)}")
    print(f"Ga Short Term Growth (assumed):        {_fmt_growth(H_MODEL_GA)}")
    print(f"Gn Long Term Growth (assumed):         {_fmt_growth(H_MODEL_GN)}")
    print(f"Terminal CapEx = Depr:                 {FORCE_TERMINAL_CAPEX_EQUALS_DA}\n")
    class _FakeInputs:
        active_public_tickers = [ticker]
        next_fiscal_year_year = NFY_YEAR
    ms_service = SourceDataService(_FakeInputs())
    ms_rows = ms_service.refresh_marketscreener()
    revenue_lfy = _to_float(is_lookup.get(REVENUE_LINE_ITEM, {}).get("LFY"))
    revenue_ttm = _to_float(is_lookup.get(REVENUE_LINE_ITEM, {}).get("TTM"))
    revenue_nfy = get_ticker_metric(is_rows, ms_rows, ticker, "NFY", REVENUE_LINE_ITEM)
    revenue_nfy1 = get_ticker_metric(is_rows, ms_rows, ticker, "NFY+1", REVENUE_LINE_ITEM)
    revenue_nfy2 = get_ticker_metric(is_rows, ms_rows, ticker, "NFY+2", REVENUE_LINE_ITEM)
    print("GPC Revenue")
    print(f"  LFY:                                {_fmt_currency(revenue_lfy)}")
    print(f"  TTM:                                {_fmt_currency(revenue_ttm)}  <- Rev_0 anchor")
    print(f"  Year 1 / NFY:                       {_fmt_currency(revenue_nfy)}")
    print(f"  Year 2 / NFY+1:                     {_fmt_currency(revenue_nfy1)}")
    print(f"  Year 3 / NFY+2:                     {_fmt_currency(revenue_nfy2)}\n")
    net_income_ttm = _to_float(is_lookup.get(NET_INCOME_LINE_ITEM, {}).get("TTM"))
    net_income_nfy = get_ticker_metric(is_rows, ms_rows, ticker, "NFY", NET_INCOME_LINE_ITEM)
    net_income_nfy1 = get_ticker_metric(is_rows, ms_rows, ticker, "NFY+1", NET_INCOME_LINE_ITEM)
    net_income_nfy2 = get_ticker_metric(is_rows, ms_rows, ticker, "NFY+2", NET_INCOME_LINE_ITEM)
    print("GPC Net Income")
    print(f"  TTM:                                {_fmt_currency(net_income_ttm)}")
    print(f"  Year 1 / NFY:                       {_fmt_currency(net_income_nfy)}")
    print(f"  Year 2 / NFY+1:                     {_fmt_currency(net_income_nfy1)}")
    print(f"  Year 3 / NFY+2:                     {_fmt_currency(net_income_nfy2)}\n")
    da_ttm_raw = _to_float(cfs_lookup.get(DA_CFS_LINE_ITEM, {}).get("TTM"))
    da_ttm = abs(da_ttm_raw) if da_ttm_raw is not None else None
    depr_pct = (da_ttm / revenue_ttm) if (da_ttm is not None and revenue_ttm) else None
    capex_ttm_raw = _to_float(cfs_lookup.get(CAPEX_LINE_ITEM, {}).get("TTM"))
    capex_ttm = abs(capex_ttm_raw) if capex_ttm_raw is not None else None
    capex_pct = (capex_ttm / revenue_ttm) if (capex_ttm is not None and revenue_ttm) else None
    bs_nwc_line_items = {
        "total_current_assets": "total current assets",
        "total_current_liab": "total current liabilities",
        "current_ltd": "current portion of long-term debt",
        "st_debt": "short-term debt",
        "current_leases": "current portion of leases",
        "cash": "cash & equivalents",
    }
    raw_bs_ttm = {k: _to_float(bs_lookup.get(v, {}).get("TTM")) for k, v in bs_nwc_line_items.items()}
    nwc_val = debt_free_nwc_excl_cash(raw_bs_ttm) if NWC_EXCLUDE_CASH else debt_free_nwc_incl_cash(raw_bs_ttm)
    nwc_pct = (nwc_val / revenue_ttm) if (nwc_val is not None and revenue_ttm) else None
    print("TTM Ratios")
    print(f"  Depreciation % of Revenue:          {_fmt_pct(depr_pct)}")
    print(f"  NWC % of Revenue:                   {_fmt_pct(nwc_pct)}")
    print(f"  NWC Cash Treatment:                 {'Excluding Cash' if NWC_EXCLUDE_CASH else 'Including Cash'}")
    print(f"  CapEx % of Revenue:                 {_fmt_pct(capex_pct)}\n")
    try:
        api_key = config.get_fred_api_key()
        series_map = config.get_fred_series()
        fred_client = FREDClient(api_key=api_key, label_map=series_map)
        fred_rows = []
        for series_id in series_map.keys():
            result = fred_client.fetch_series(series_id)
            if result:
                fred_rows.append(result)
    except Exception as e:
        fred_rows = []
        flags.append(f"FRED fetch failed: {e}")
    risk_free_rate = get_risk_free_rate(fred_rows)
    if risk_free_rate is None:
        flags.append("Risk-Free Rate (Rf) missing")
    try:
        beta_client = BetaVolClient(tickers=[ticker], index_ticker=INDEX_TICKER, valuation_date=VALUATION_DATE, beta_history=BETA_HISTORY_YEARS, vol_term=VOL_TERM_YEARS)
        beta_vol_rows = beta_client.pull_and_calculate()
    except Exception as e:
        beta_vol_rows = []
        flags.append(f"Beta/Vol fetch failed: {e}")
    observed_beta = get_observed_beta(ticker, beta_vol_rows)
    if observed_beta is None:
        flags.append("Observed Beta could not be computed")
    print("Cost of Equity Inputs")
    print(f"  Risk-Free Rate (Rf):                {_fmt_pct(risk_free_rate)}")
    print(f"  Beta (Observed):                     {_fmt_beta(observed_beta)}")
    print(f"  Equity Risk Premium (Rm - Rf):       {_fmt_pct(EQUITY_RISK_PREMIUM)}\n")
    print("-" * 76)
    print("DOWNSTREAM CALCULATIONS (reverse_dcf.py)")
    print("-" * 76)
    ke = compute_cost_of_equity(risk_free_rate, observed_beta, EQUITY_RISK_PREMIUM)
    print(f"Ke (Cost of Equity):                  {_fmt_pct(ke)}")
    if ke is None:
        flags.append("Ke missing — cannot proceed")
        print(f"\nFLAGS: {', '.join(flags)}")
        print("=" * 76 + "\n")
        return
    print()
    fcfe_schedule = build_fcfe_schedule(revenue_prior=revenue_ttm, revenue_explicit=[revenue_nfy, revenue_nfy1, revenue_nfy2], net_income_explicit=[net_income_nfy, net_income_nfy1, net_income_nfy2], depr_pct=depr_pct, capex_pct=capex_pct, nwc_pct=nwc_pct, force_terminal_capex_equals_da=FORCE_TERMINAL_CAPEX_EQUALS_DA)
    pv_sum_manual = None
    if fcfe_schedule is None:
        flags.append("FCFE schedule could not be built")
        print("FCFE Bridge:                          UNAVAILABLE\n")
    else:
        print(f"FCFE Bridge (Year 1 = NFY) [Rev_0=TTM] [TermCapEx=Depr={FORCE_TERMINAL_CAPEX_EQUALS_DA}]:")
        print(f"  {'Yr':<4}{'Revenue':>16}{'NetIncome':>16}{'Depr':>14}{'CapEx':>14}{'ΔNWC':>14}{'FCFE':>16}{'PV(FCFE)':>16}")
        pv_sum_manual = 0.0
        for yr in fcfe_schedule:
            pv = yr["fcfe"] / ((1 + ke) ** yr["year_index"])
            pv_sum_manual += pv
            print(f"  {yr['year_index']:<4}{yr['revenue']:>16,.2f}{yr['net_income']:>16,.2f}{yr['depreciation']:>14,.2f}{yr['capex']:>14,.2f}{yr['delta_nwc']:>14,.2f}{yr['fcfe']:>16,.2f}{pv:>16,.2f}")
        print(f"  {'':<4}{'':>16}{'':>16}{'':>14}{'':>14}{'':>14}{'ΣPV:':>16}{pv_sum_manual:>16,.2f}\n")
    a = compute_reconciliation_a(market_cap, fcfe_schedule, ke)
    print(f"A (terminal value reconciliation):    {_fmt_currency(a)}")
    if a is None:
        flags.append("A could not be computed")
    print()
    fcfe_n = fcfe_schedule[-1]["fcfe"] if fcfe_schedule else None
    print(f"FCFE_N (terminal-year FCFE):           {_fmt_currency(fcfe_n)}\n")
    gordon = solve_gordon_growth_ltgr(a, ke, fcfe_n)
    print("Gordon Growth — Implied LTGR:")
    print(f"  Value:                               {_fmt_growth(gordon['value'])}")
    print(f"  Valid:                                {gordon['is_valid']}")
    print(f"  Flags:                                {', '.join(gordon['flags']) if gordon['flags'] else 'None'}\n")
    print("H-Model — all three solve scenarios:")
    print(f"  Assumed Ga: {_fmt_growth(H_MODEL_GA)}   Assumed Gn: {_fmt_growth(H_MODEL_GN)}   Assumed H: {_fmt_years(H_MODEL_H)}  h_eff={_fmt_years(H_MODEL_H/2 if H_IS_FULL_PERIOD else H_MODEL_H)}\n")
    h_solve_h = solve_h_model(a, ke, fcfe_n, ga=H_MODEL_GA, gn=H_MODEL_GN, h=None, solve_for="H", full_fade_convention=H_IS_FULL_PERIOD)
    if h_solve_h["value"] is not None:
        h_full = h_solve_h["value"]
        h_half = h_full / 2 if H_IS_FULL_PERIOD else h_full
        print(f"  Solving for H  (given Ga, Gn): H full={_fmt_years(h_full)}  (h half: {_fmt_years(h_half)}) Valid={h_solve_h['is_valid']} Flags={h_solve_h['flags']}")
    else:
        print(f"  Solving for H failed: {h_solve_h['flags']}")
    h_solve_ga = solve_h_model(a, ke, fcfe_n, ga=None, gn=H_MODEL_GN, h=H_MODEL_H, solve_for="Ga", full_fade_convention=H_IS_FULL_PERIOD)
    print(f"  Solving for Ga (given Gn, H): {_fmt_growth(h_solve_ga['value'])} Valid={h_solve_ga['is_valid']} Flags={h_solve_ga['flags']}")
    h_solve_gn = solve_h_model(a, ke, fcfe_n, ga=H_MODEL_GA, gn=None, h=H_MODEL_H, solve_for="Gn", full_fade_convention=H_IS_FULL_PERIOD)
    print(f"  Solving for Gn (given Ga, H): {_fmt_growth(h_solve_gn['value'])} Valid={h_solve_gn['is_valid']} Flags={h_solve_gn['flags']}\n")
    print(f"FLAGS: {', '.join(flags) if flags else 'None'}")
    print("=" * 76 + "\n")

if __name__ == "__main__":
    tickers = sys.argv[1:] if len(sys.argv) > 1 else TICKERS
    for t in tickers:
        debug_ticker(t)