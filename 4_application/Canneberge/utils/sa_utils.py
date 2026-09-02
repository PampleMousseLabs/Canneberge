"""
sa_utils.py
Canneberge — utils

Shared StockAnalysis data utility functions.
Centralizes row-filtering and numeric parsing logic across all calculation modules.
"""

import math
from typing import Optional, Dict


def build_lookup(rows: list, ticker: str) -> Dict[str, Dict[str, str]]:
    """
    Filter a list of SA scraped rows to one ticker, then key each
    row by its lowercased Line Item string.

    Returns:
        {sa_label_lowercased: {period_label: raw_string}}
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


def to_float(raw) -> Optional[float]:
    """
    Parse a raw SA cell value to float. Handles commas and rejects NaN/Inf.
    """
    if raw is None:
        return None
    try:
        val = float(str(raw).replace(",", ""))
    except (ValueError, TypeError):
        return None
    if math.isnan(val) or math.isinf(val):
        return None
    return val