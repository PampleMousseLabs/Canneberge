"""
Replaces Excel's GPC_BS sheet.

For each GPC ticker, pulls BEV (Enterprise Value) from the Ratios
statement and every catalogued metric from GPC_METRICS, then computes
BEV / metric for each. Output is one row per ticker, keyed by ticker,
with a nested dict of {display_name: multiple_or_None}.

This module does NOT touch the UI. It is pure calculation, callable
from gpc_page.py or from tests directly.
"""

from typing import Dict, Optional

from Canneberge.Calculations.gpc_metrics import GPC_METRICS

# Confirmed against live Source Data → Ratios view: StockAnalysis's
# scraped Line Item for Enterprise Value is literally "Enterprise Value"
# (lowercased/stripped to "enterprise value" per the app's lookup convention).
BEV_LINE_KEY = "enterprise value"


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
        return float(str(raw).replace(",", ""))
    except (ValueError, TypeError):
        return None


def get_ticker_bev(ratio_rows: list, ticker: str) -> Optional[float]:
    """
    BEV for a single ticker, pulled from the Ratios statement's
    scraped rows (sa_results.get("Ratios", [])).

    NOTE: BEV is scraped for every period (TTM, LFY, LFY-1...LFY-4),
    confirmed against the live Ratios view — not just TTM. This
    function only reads TTM/Current because every GPC_METRICS entry
    today uses TTM-period BEV as the numerator. If a future metric
    needs a non-TTM BEV (e.g. an LFY-1 multiple), this function needs
    a period parameter — don't assume TTM BEV is correct for every case.
    """
    lookup = _build_lookup(ratio_rows, ticker)
    row_data = lookup.get(BEV_LINE_KEY, {})
    raw = row_data.get("TTM") or row_data.get("Current")
    return _to_float(raw)


def get_ticker_metric(is_rows: list, ticker: str, period: str, line_key: str) -> Optional[float]:
    """Single metric value for one ticker at one period, from IS scraped rows."""
    lookup = _build_lookup(is_rows, ticker)
    row_data = lookup.get(line_key, {})
    raw = row_data.get(period)
    return _to_float(raw)


def compute_ticker_multiples(
    is_rows: list,
    ratio_rows: list,
    ticker: str,
) -> Dict[str, Optional[float]]:
    """
    Returns {display_name: multiple_or_None} for every entry in
    GPC_METRICS, for a single ticker.
    """
    bev = get_ticker_bev(ratio_rows, ticker)
    results: Dict[str, Optional[float]] = {}

    for metric in GPC_METRICS:
        if bev is None:
            results[metric.display_name] = None
            continue
        value = get_ticker_metric(is_rows, ticker, metric.period, metric.line_key)
        if value is None or value == 0:
            results[metric.display_name] = None
        else:
            results[metric.display_name] = bev / value

    return results


def compute_all_gpc_multiples(
    is_rows: list,
    ratio_rows: list,
    tickers: list,
) -> Dict[str, Dict[str, Optional[float]]]:
    """
    Returns {ticker: {display_name: multiple_or_None}} for the full
    GPC comp set. This is the main entry point gpc_page.py should call.
    """
    return {
        ticker: compute_ticker_multiples(is_rows, ratio_rows, ticker)
        for ticker in tickers
    }


def get_ticker_bevs(ratio_rows: list, tickers: list) -> Dict[str, Optional[float]]:
    """BEV per ticker, exposed separately since the page needs raw BEV
    displayed/used independent of the multiples (e.g. for Indicated BEV math)."""
    return {ticker: get_ticker_bev(ratio_rows, ticker) for ticker in tickers}