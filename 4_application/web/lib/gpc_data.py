"""
web/lib/gpc_data.py

Thin Dash-facing wrapper around Canneberge.Calculations.gpc_multiples.
Converts session-store / source-results-store dicts into the row-list
arguments that gpc_multiples.py's pure functions expect.

No math lives here — it all stays in Calculations/gpc_multiples.py.
This module only handles the dict-unpacking boundary.
"""

from typing import Dict, Optional

from Canneberge.Calculations.gpc_multiples import (
    compute_all_gpc_multiples,
    get_ticker_bevs,
    get_ticker_equity,
    get_subject_cash,
)
from web.lib.session_io import dict_to_project_inputs


def _unpack_sa(source_results: dict) -> tuple:
    """Pull IS/BS/Ratios row-lists out of the stockanalysis blob.
    Returns (is_rows, bs_rows, ratio_rows) — empty lists if missing."""
    sa = (source_results or {}).get("stockanalysis", {}) or {}
    return sa.get("IS", []) or [], sa.get("BS", []) or [], sa.get("Ratios", []) or []


def get_all_gpc_multiples(
    session_data: dict,
    source_results: dict,
    basis_mode: str = "BEV",
) -> Dict[str, Dict[str, Optional[float]]]:
    """Compute every GPC_METRICS multiple for every ticker in session's gpc_tickers.

    Returns {ticker: {metric_display_name: multiple_or_None}}.
    Empty dict if no tickers configured.
    """
    inputs = dict_to_project_inputs(session_data)
    tickers = inputs.gpc_tickers
    if not tickers:
        return {}

    is_rows, bs_rows, ratio_rows = _unpack_sa(source_results)
    ms_rows = (source_results or {}).get("marketscreener", []) or []

    return compute_all_gpc_multiples(
        is_rows=is_rows,
        ms_rows=ms_rows,
        ratio_rows=ratio_rows,
        bs_rows=bs_rows,
        tickers=tickers,
        basis_mode=basis_mode,
    )


def get_all_ticker_bevs(session_data: dict, source_results: dict) -> Dict[str, Optional[float]]:
    """BEV (Enterprise Value) per GPC ticker. Used by the chart / bridge sections."""
    inputs = dict_to_project_inputs(session_data)
    tickers = inputs.gpc_tickers
    if not tickers:
        return {}

    _, bs_rows, ratio_rows = _unpack_sa(source_results)
    return get_ticker_bevs(ratio_rows, bs_rows, tickers)


def get_all_ticker_equity(session_data: dict, source_results: dict) -> Dict[str, Optional[float]]:
    """Market Cap per GPC ticker. Used in Equity-mode bridge sections."""
    inputs = dict_to_project_inputs(session_data)
    tickers = inputs.gpc_tickers
    if not tickers:
        return {}

    _, _, ratio_rows = _unpack_sa(source_results)
    return {ticker: get_ticker_equity(ratio_rows, ticker) for ticker in tickers}


def get_gpc_subject_cash(session_data: dict, source_results: dict) -> Optional[float]:
    """Subject company's cash balance, for the BEV bridge section.

    Public: pulled from StockAnalysis BS. Private: pulled from PrivateFinancials
    via subject_metrics (avoids duplicating the private-lookup logic here).
    """
    inputs = dict_to_project_inputs(session_data)

    if inputs.is_publicly_traded:
        _, bs_rows, _ = _unpack_sa(source_results)
        return get_subject_cash(bs_rows, inputs.subject_ticker)

    # Private path: delegate to subject_metrics so there's exactly one
    # place that knows how to read PrivateFinancials.
    from web.lib.subject_metrics import get_subject_metric_value
    return get_subject_metric_value(session_data, source_results, "cash", "TTM")