"""
gpc_multiples.py
Canneberge — GPC Multiples Engine.

Calculates multiples strictly per metric and mode:
  - basis_mode = "EQUITY": Market Cap / Aggregate Metric ($) [P/S, P/E, P/B]
  - basis_mode = "BEV":    BEV / Aggregate Metric ($) [EV/Sales, EV/EBITDA, EV/EBIT]
"""

import math
from typing import Dict, Optional

from Canneberge.Transforms.sa_key import get_sa_label, get_sa_labels
from Canneberge.utils.sa_utils import build_lookup, to_float
from Canneberge.Calculations.gpc_metrics import GPC_METRICS


def get_ticker_equity(ratio_rows: list, ticker: str) -> Optional[float]:
    """Returns TTM Market Cap (Total Equity Value in Millions/Thousands) for a ticker."""
    ratio_lookup = build_lookup(ratio_rows, ticker)
    return to_float(ratio_lookup.get(get_sa_label("market_cap"), {}).get("TTM"))


def get_ticker_bev(ratio_rows: list, bs_rows: list, ticker: str) -> Optional[float]:
    """Returns Enterprise Value (BEV = Market Cap + Net Debt + Preferred + Minority)."""
    market_cap = get_ticker_equity(ratio_rows, ticker)
    if market_cap is None:
        return None

    bs_lookup = build_lookup(bs_rows, ticker)
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
    lookup = build_lookup(bs_rows, ticker)
    raw = lookup.get(get_sa_label("cash"), {}).get("TTM")
    return to_float(raw)


_MARKETSCREENER_PERIODS = {"NFY", "NFY+1", "NFY+2"}


def get_ticker_metric(
    is_rows: list,
    ms_rows: list,
    bs_rows: list,
    ticker: str,
    period: str,
    line_key: str,
) -> Optional[float]:
    """
    Sources aggregate metric value based on statement type:
      - line_key in BS-only keys ("total_equity", "cash", "total_assets") -> Balance Sheet
      - period in NFY/NFY+1/NFY+2                                         -> MarketScreener
      - otherwise                                                          -> Income Statement
    """
    if line_key in ("total_equity", "cash", "total_assets"):
        lookup = build_lookup(bs_rows, ticker)
    elif period in _MARKETSCREENER_PERIODS:
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
    basis_mode: str = "BEV",
) -> Dict[str, Optional[float]]:
    """
    Computes multiples for a single ticker.
    basis_mode "EQUITY" uses Market Cap as numerator (P/S, P/E, P/B).
    basis_mode "BEV" uses Enterprise Value as numerator (EV/Sales, EV/EBITDA).
    """
    equity = get_ticker_equity(ratio_rows, ticker)
    bev = get_ticker_bev(ratio_rows, bs_rows, ticker)
    results: Dict[str, Optional[float]] = {}

    numerator = equity if (basis_mode == "EQUITY") else bev

    for metric in GPC_METRICS:
        if numerator is None:
            results[metric.display_name] = None
            continue

        value = get_ticker_metric(is_rows, ms_rows, bs_rows, ticker, metric.period, metric.line_key)
        if value is None or value == 0:
            results[metric.display_name] = None
        else:
            results[metric.display_name] = numerator / value

    return results


def compute_all_gpc_multiples(
    is_rows: list,
    ms_rows: list,
    ratio_rows: list,
    bs_rows: list,
    tickers: list,
    basis_mode: str = "BEV",
) -> Dict[str, Dict[str, Optional[float]]]:
    return {
        ticker: compute_ticker_multiples(is_rows, ms_rows, ratio_rows, bs_rows, ticker, basis_mode=basis_mode)
        for ticker in tickers
    }


def get_ticker_bevs(ratio_rows: list, bs_rows: list, tickers: list) -> Dict[str, Optional[float]]:
    return {ticker: get_ticker_bev(ratio_rows, bs_rows, ticker) for ticker in tickers}