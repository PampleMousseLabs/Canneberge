"""
Replaces Excel's GPC_BS sheet.

For each GPC ticker, pulls BEV (Enterprise Value) from the Ratios
statement and every catalogued metric from GPC_METRICS, then computes
BEV / metric for each. Output is one row per ticker, keyed by ticker,
with a nested dict of {display_name: multiple_or_None}.

This module does NOT touch the UI. It is pure calculation, callable
from gpc_page.py or from tests directly.
"""

import math
from typing import Dict, Optional

from Canneberge.Calculations.gpc_metrics import GPC_METRICS

# Confirmed against live Source Data → Ratios view (screenshot,
# 8/14/2026: Line Item reads "Market Capitalization", not "Market
# Cap" — the old value here was a guess that never matched the real
# scrape, silently nulling BEV -> every GPC multiple -> NA for every
# ticker, every column, since get_ticker_bev() hard-returns None on a
# missed lookup here with no fallback). "Market Cap" is the starting
# point for BEV now — we build BEV ourselves instead of trusting
# StockAnalysis's own precomputed "Enterprise Value" line, because that
# line bakes in Short-Term Investments in its net debt calc, which this
# pass intentionally excludes.
MARKET_CAP_LINE_KEY = "market capitalization"

# BS line keys, reusing the exact SA_KEY_MAP vocabulary from
# subject_financials_page.py — same strings, not re-invented here.
_DEBT_COMPONENT_KEYS = [
    "current_ltd", "st_debt", "current_leases", "lt_debt", "lt_leases",
]
_CASH_KEY = "cash"
_PREFERRED_KEY = "preferred_stock"
_MINORITY_KEY = "minority_interest"

# SA_KEY_MAP's line-item strings for the BS keys above (kept local here
# rather than importing SA_KEY_MAP directly, since that dict also
# contains Custom Multiple/placeholder entries irrelevant to this
# calculation and importing it would create a UI->calc dependency).
_BS_LINE_ITEMS = {
    "current_ltd":      "current portion of long-term debt",
    "st_debt":           "short-term debt",
    "current_leases":    "current portion of leases",
    "lt_debt":            "long-term debt",
    "lt_leases":          "long-term leases",
    "cash":                "cash & equivalents",
    "preferred_stock":     "preferred stock",
    "minority_interest":  "minority interest",
}


def _build_lookup(rows: list, ticker: str) -> Dict[str, Dict[str, str]]:
    """
    Same pattern as subject_financials_page.py's _build_public_view:
    filters rows to one ticker, keys by lowercased Line Item, values
    are {period: raw_string}.
    """
    ticker_lower = ticker.strip().lower()
    lookup: Dict[str, Dict[str, str]] = {}
    for row in rows:
        if str(row.get("Ticker", "")).strip().lower() != ticker_lower:
            continue
        key = str(row.get("Line Item", "")).strip().lower()
        lookup[key] = {
            k: v for k, v in row.items()
            if k not in ("Ticker", "Key", "Line Item")
        }
    return lookup


def _to_float(raw) -> Optional[float]:
    if raw is None:
        return None
    try:
        val = float(str(raw).replace(",", ""))
    except (ValueError, TypeError):
        return None
    # float() parses "nan"/"inf"/"-inf" strings successfully without
    # raising — if scraped data ever contains one of these (e.g. a
    # source-side ratio computed as x/0), it would silently poison
    # every downstream sum and division with NaN instead of failing
    # visibly as None/NA. Reject explicitly rather than trust the
    # scrape never produces these strings.
    if math.isnan(val) or math.isinf(val):
        return None
    return val


def get_ticker_bev(ratio_rows: list, bs_rows: list, ticker: str) -> Optional[float]:
    """
    BEV computed from scratch, per the model's formula:
        BEV = Market Cap (MV of Equity)
              + Net Debt
              + Preferred Stock
              + Minority Interest
        Net Debt = (Current Portion LTD + ST Debt + Current Portion
                    Leases + LT Debt + LT Leases) - Cash

    Deliberately NOT StockAnalysis's own "Enterprise Value" line —
    that figure bakes in Short-Term Investments in its net debt calc,
    which this pass intentionally excludes. Market Cap comes from
    Ratios; every debt/cash/preferred/minority component comes from BS.

    Uses TTM for every component. If a future need arises for BEV at
    a non-TTM period, this needs a period parameter — don't assume
    TTM is correct for every case (same caveat as the prior version).
    """
    ratio_lookup = _build_lookup(ratio_rows, ticker)
    bs_lookup = _build_lookup(bs_rows, ticker)

    market_cap = _to_float(ratio_lookup.get(MARKET_CAP_LINE_KEY, {}).get("TTM"))
    if market_cap is None:
        return None

    total_debt = 0.0
    for key in _DEBT_COMPONENT_KEYS:
        line_item = _BS_LINE_ITEMS[key]
        val = _to_float(bs_lookup.get(line_item, {}).get("TTM"))
        if val is not None:
            total_debt += val

    cash = _to_float(bs_lookup.get(_BS_LINE_ITEMS[_CASH_KEY], {}).get("TTM")) or 0.0
    net_debt = total_debt - cash

    preferred = _to_float(bs_lookup.get(_BS_LINE_ITEMS[_PREFERRED_KEY], {}).get("TTM")) or 0.0
    minority = _to_float(bs_lookup.get(_BS_LINE_ITEMS[_MINORITY_KEY], {}).get("TTM")) or 0.0

    return market_cap + net_debt + preferred + minority


def get_subject_cash(bs_rows: list, ticker: str) -> Optional[float]:
    """
    Cash & Equivalents for a single ticker, from BS scraped rows.
    Same "cash & equivalents" line item and TTM period already used
    inside get_ticker_bev's net debt calc — exposed here separately
    so the subject company's Cash (for the Bridge section) doesn't
    need its own new data path.
    """
    lookup = _build_lookup(bs_rows, ticker)
    raw = lookup.get(_BS_LINE_ITEMS[_CASH_KEY], {}).get("TTM")
    return _to_float(raw)


# Periods sourced from MarketScreener only. Anything not in this set
# is assumed to come from StockAnalysis's IS scrape. This is a hard
# split, not a fallback — if a period's real source has no data for
# a ticker, this returns None rather than trying the other source.
# A wrong result here should surface as a visible NA, not get quietly
# papered over by pulling from whichever source happens to answer.
_MARKETSCREENER_PERIODS = {"NFY", "NFY+1", "NFY+2"}


def get_ticker_metric(
    is_rows: list,
    ms_rows: list,
    ticker: str,
    period: str,
    line_key: str,
) -> Optional[float]:
    """
    Single metric value for one ticker at one period.

    Historical/TTM periods -> StockAnalysis IS scraped rows.
    NFY/NFY+1/NFY+2         -> MarketScreener scraped rows.

    Hard split, no fallback: if the period's designated source has
    no value, this returns None. It will NOT try the other source.
    """
    if period in _MARKETSCREENER_PERIODS:
        lookup = _build_lookup(ms_rows, ticker)
    else:
        lookup = _build_lookup(is_rows, ticker)

    row_data = lookup.get(line_key, {})
    raw = row_data.get(period)
    return _to_float(raw)


def compute_ticker_multiples(
    is_rows: list,
    ms_rows: list,
    ratio_rows: list,
    bs_rows: list,
    ticker: str,
) -> Dict[str, Optional[float]]:
    """
    Returns {display_name: multiple_or_None} for every entry in
    GPC_METRICS, for a single ticker.
    """
    bev = get_ticker_bev(ratio_rows, bs_rows, ticker)
    results: Dict[str, Optional[float]] = {}

    for metric in GPC_METRICS:
        if bev is None:
            results[metric.display_name] = None
            continue
        value = get_ticker_metric(is_rows, ms_rows, ticker, metric.period, metric.line_key)
        if value is None or value == 0:
            results[metric.display_name] = None
        else:
            results[metric.display_name] = bev / value

    return results


def compute_all_gpc_multiples(
    is_rows: list,
    ms_rows: list,
    ratio_rows: list,
    bs_rows: list,
    tickers: list,
) -> Dict[str, Dict[str, Optional[float]]]:
    """
    Returns {ticker: {display_name: multiple_or_None}} for the full
    GPC comp set. This is the main entry point gpc_page.py should call.
    """
    return {
        ticker: compute_ticker_multiples(is_rows, ms_rows, ratio_rows, bs_rows, ticker)
        for ticker in tickers
    }


def get_ticker_bevs(ratio_rows: list, bs_rows: list, tickers: list) -> Dict[str, Optional[float]]:
    """BEV per ticker, exposed separately since the page needs raw BEV
    displayed/used independent of the multiples (e.g. for Indicated BEV math)."""
    return {ticker: get_ticker_bev(ratio_rows, bs_rows, ticker) for ticker in tickers}