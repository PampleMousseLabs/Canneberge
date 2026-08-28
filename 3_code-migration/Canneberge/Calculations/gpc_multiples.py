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

from Canneberge.Transforms.sa_key import get_sa_label, get_sa_labels
from Canneberge.utils.sa_utils import build_lookup, to_float
from Canneberge.Calculations.gpc_metrics import GPC_METRICS

def get_ticker_bev(ratio_rows: list, bs_rows: list, ticker: str) -> Optional[float]:
    ratio_lookup = build_lookup(ratio_rows, ticker)
    bs_lookup = build_lookup(bs_rows, ticker)

    market_cap = to_float(ratio_lookup.get(get_sa_label("market_cap"), {}).get("TTM"))
    if market_cap is None:
        return None

    debt_keys = ["current_ltd", "st_debt", "current_leases", "lt_debt", "lt_leases"]
    total_debt = 0.0
    for key in debt_keys:
        for sa_label in get_sa_labels(key):
            row = bs_lookup.get(sa_label, {})
            if row:
                val = to_float(row.get("TTM"))
                if val is not None:
                    total_debt += val
                break

    cash = to_float(bs_lookup.get(get_sa_label("cash"), {}).get("TTM")) or 0.0
    net_debt = total_debt - cash

    preferred = to_float(bs_lookup.get(get_sa_label("preferred_stock"), {}).get("TTM")) or 0.0
    minority = to_float(bs_lookup.get(get_sa_label("minority_interest"), {}).get("TTM")) or 0.0

    return market_cap + net_debt + preferred + minority


def get_subject_cash(bs_rows: list, ticker: str) -> Optional[float]:
    """
    Cash & Equivalents for a single ticker, from BS scraped rows.
    Same "cash & equivalents" line item and TTM period already used
    inside get_ticker_bev's net debt calc — exposed here separately
    so the subject company's Cash (for the Bridge section) doesn't
    need its own new data path.
    """
    lookup = build_lookup(bs_rows, ticker)
    raw = lookup.get(get_sa_label("cash"), {}).get("TTM")
    return to_float(raw)


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
        lookup = build_lookup(ms_rows, ticker)
    else:
        lookup = build_lookup(is_rows, ticker)

    sa_label = get_sa_label(line_key)
    row_data = lookup.get(sa_label, {})
    raw = row_data.get(period)
    return to_float(raw)


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