"""
nwc.py
Canneberge — Net Working Capital calculation engine.

Pure calculation layer. No Qt, no Dash, no page imports.

Extracted from Ui/nwc_page.py so the desktop and web NWC surfaces can
share one definition of every formula. Ui/nwc_page.py is deliberately
left untouched for now — it works, and rewiring it is unnecessary risk.
Once the web page is proven at parity, the desktop page can be
refactored to import from here instead of keeping its own copy.

DELIBERATE BEHAVIORS PRESERVED FROM DESKTOP — do not "fix" these:

  * NWC Cash Treatment affects the GPC peer calculations ONLY. The
    subject schedule is always the literal sum of whichever CA/CL rows
    the user selected. If the user wants subject NWC excluding cash,
    they deselect the cash row themselves. This is intentional: it
    keeps the basis explicit and lets the user drop the subject ticker
    into the GPC list to verify both sides agree.

  * Subject NWC is CA - CL. Nothing is netted out automatically.

  * Turnover Ratios basis produces no projected NWC, because the
    balance sheet is never projected anywhere in this app. Data
    limitation, not a bug.

  * Peer statistics ignore excluded tickers; the chart does not.
    Exclusion is a peer-stats concept, not "hide this company".

  * TTM is a real column (desktop DCF has none). Change in NWC at NFY
    is explicitly NFY - TTM, so TTM must exist as a column, not an
    off-grid scalar.
"""

import statistics
from typing import Optional, Dict, List, Tuple

from Canneberge.app_state import BS_LINES
from Canneberge.Transforms.sa_key import get_sa_label
from Canneberge.utils.sa_utils import build_lookup


# ---------------------------------------------------------------------------
# Row-selector configuration
# ---------------------------------------------------------------------------

CA_CANDIDATES = [
    "cash", "st_investments", "trading_asset_securities",
    "cash_short_term_investments", "accounts_receivable", "other_receivables",
    "receivables", "finance_div_loans_and_leases", "inventory",
    "finance_div_other_current_assets", "prepaid_expenses",
    "loans_receivable_current", "restricted_cash", "other_current_assets",
]

CL_CANDIDATES = [
    "accounts_payable", "accrued_expenses", "st_debt", "current_ltd",
    "current_leases", "finance_div_debt_current",
    "finance_div_other_current_liabilities", "current_income_taxes_payable",
    "unearned_revenue", "other_current_liab",
]

CA_MAX_ROWS = len(CA_CANDIDATES)
CL_MAX_ROWS = len(CL_CANDIDATES)

CA_DEFAULT_SELECTIONS = [
    "cash", "accounts_receivable", "inventory", "other_current_assets",
    "", "", "",
]
CL_DEFAULT_SELECTIONS = [
    "accounts_payable", "other_current_liab", "", "", "", "", "",
]

CA_DEFAULT_ROWS = 7
CL_DEFAULT_ROWS = 7

# GPC NWC formula inputs expressed as internal keys so the actual
# StockAnalysis label strings come from sa_key (single source of truth).
GPC_NWC_KEYS = {
    "tca":       "total_current_assets",
    "tcl":       "total_current_liab",
    "cpltd":     "current_ltd",
    "std":       "st_debt",
    "cpl":       "current_leases",
    "cash":      "cash",
    "st_inv":    "st_investments",
    "cash_sti":  "cash_short_term_investments",
    "rev":       "revenue",
}

STAT_NAMES = [
    "Maximum", "Third Quartile", "Average",
    "Median", "First Quartile", "Minimum",
]

_BS_LABEL_BY_KEY = {k: label for k, label, *_r in BS_LINES}


def format_ca_cl_option(key: str) -> str:
    """Display label for a CA/CL selector entry."""
    app_label = _BS_LABEL_BY_KEY.get(key)
    if app_label:
        return app_label
    sa_label = get_sa_label(key)
    if sa_label:
        return sa_label.title()
    return key.replace("_", " ").title()


# ---------------------------------------------------------------------------
# Arithmetic helpers
# ---------------------------------------------------------------------------

def _sub(a: Optional[float], b: Optional[float]) -> Optional[float]:
    """Strict subtraction: None if either operand is missing.

    Mirrors dcf_page._sub_strict, which Ui/nwc_page.py imports as _sub.
    If that function turns out to be permissive (None only when BOTH
    operands are missing), change this single line — every caller in
    this module routes through here.
    """
    if a is None or b is None:
        return None
    return a - b


def _mul(a: Optional[float], b: Optional[float]) -> Optional[float]:
    """Strict multiplication: None if either operand is missing."""
    if a is None or b is None:
        return None
    return a * b


def safe_div(a: Optional[float], b: Optional[float]) -> Optional[float]:
    if a is None or b is None or b == 0:
        return None
    return a / b


def parse_number(text) -> Optional[float]:
    """Forgiving numeric parse: handles commas, %, $, blank."""
    if text is None:
        return None
    raw = str(text).strip().replace(",", "").replace("%", "").replace("$", "")
    if not raw:
        return None
    try:
        val = float(raw)
    except (TypeError, ValueError):
        return None
    if val != val or val in (float("inf"), float("-inf")):
        return None
    return val


def parse_pct_text(text) -> Optional[float]:
    """'15.0%' -> 0.15 ; '-26.6' -> -0.266.

    Matches desktop exactly: _parse_label_as_float(text) / 100.0.
    Note this always divides by 100 — a bare '0.15' becomes 0.0015.
    """
    val = parse_number(text)
    return None if val is None else val / 100.0


def quartile(values: List[float], q: float) -> Optional[float]:
    """Linear-interpolated quartile. Sorts internally."""
    if not values:
        return None
    vals = sorted(values)
    n = len(vals)
    if n == 1:
        return vals[0]
    pos = q * (n - 1)
    lo = int(pos)
    hi = min(lo + 1, n - 1)
    frac = pos - lo
    return vals[lo] + (vals[hi] - vals[lo]) * frac


# ---------------------------------------------------------------------------
# Column construction
# ---------------------------------------------------------------------------

def period_columns(
    historical_years: int,
    projection_period_columns: List[str],
) -> Tuple[List[str], List[bool]]:
    """Return (headers, is_historical) for the NWC schedule.

    Historical block is LFY-(N-1) ... LFY, then TTM. TTM counts as
    historical. Projection block comes from the GLOBAL projection
    period columns. A Residual column is always appended last.
    """
    hist_labels: List[str] = []
    for i in range(max(1, historical_years) - 1, 0, -1):
        hist_labels.append(f"LFY-{i}")
    hist_labels.append("LFY")
    hist_labels.append("TTM")

    proj_labels = list(projection_period_columns or [])

    headers = hist_labels + proj_labels + ["Residual"]
    is_historical = (
        [True] * len(hist_labels)
        + [False] * len(proj_labels)
        + [False]
    )
    return headers, is_historical


def historical_columns(headers: List[str], is_historical: List[bool]) -> List[str]:
    return [h for h, hist in zip(headers, is_historical) if hist]


def fye_years(
    headers: List[str],
    lfy_year: Optional[int],
    nfy_year: Optional[int],
) -> Dict[str, str]:
    """Fiscal-year-end label per column. Verbatim desktop logic."""
    result: Dict[str, str] = {}

    hist_labels = (
        [h for h in headers if h.startswith("LFY-")]
        + (["LFY"] if "LFY" in headers else [])
    )
    if lfy_year is not None:
        n = len(hist_labels)
        for i, label in enumerate(hist_labels):
            result[label] = str(lfy_year - (n - 1 - i))

    if "TTM" in headers:
        result["TTM"] = str(lfy_year) if lfy_year is not None else ""

    if nfy_year is not None:
        proj_labels = [h for h in headers if h == "NFY" or h.startswith("NFY+")]
        for i, label in enumerate(proj_labels):
            result[label] = str(nfy_year + i)
        if proj_labels:
            result["Residual"] = str(nfy_year + len(proj_labels))

    return result


# ---------------------------------------------------------------------------
# Subject schedule
# ---------------------------------------------------------------------------

def sum_selected_rows(
    selections: List[str],
    headers: List[str],
    value_getter,
) -> Tuple[Dict[str, Dict[str, Optional[float]]], Dict[str, Optional[float]]]:
    """Resolve each selected CA/CL row and produce the column sums.

    value_getter(key, period) -> Optional[float]

    Returns:
        (per_row_values, sums_by_period)

        per_row_values is keyed by slot index (as str) then period, so
        callers can render individual rows without re-fetching.

    The sum stays None for a period where NO selected row produced a
    value — it does not collapse to 0.0. Desktop behavior.
    """
    per_row: Dict[str, Dict[str, Optional[float]]] = {}
    sums: Dict[str, Optional[float]] = {p: None for p in headers}

    for slot, key in enumerate(selections):
        row_vals: Dict[str, Optional[float]] = {}
        for period in headers:
            val = value_getter(key, period) if key else None
            row_vals[period] = val
            if val is not None:
                sums[period] = (sums[period] or 0.0) + val
        per_row[str(slot)] = row_vals

    return per_row, sums


def subject_nwc_by_period(
    headers: List[str],
    is_historical: List[bool],
    revenue_by_period: Dict[str, Optional[float]],
    ca_sums: Dict[str, Optional[float]],
    cl_sums: Dict[str, Optional[float]],
    selected_pct: Optional[float],
    pct_basis: bool,
) -> Dict[str, Optional[float]]:
    """Subject NWC per column.

    Historical / TTM : CA - CL
    Projected, % basis        : Revenue x Selected NWC %
    Projected, turnover basis : CA - CL  (blank until BS is projected)
    Residual                  : Revenue x Selected NWC %
    """
    out: Dict[str, Optional[float]] = {}

    for idx, period in enumerate(headers):
        is_hist = is_historical[idx]
        ca = ca_sums.get(period)
        cl = cl_sums.get(period)
        rev = revenue_by_period.get(period)

        if period == "Residual":
            nwc = _mul(rev, selected_pct)
        elif is_hist:
            nwc = _sub(ca, cl) if (ca is not None or cl is not None) else None
        else:
            if pct_basis:
                nwc = _mul(rev, selected_pct)
            else:
                nwc = _sub(ca, cl) if (ca is not None or cl is not None) else None

        out[period] = nwc

    return out


def changes_in_nwc(
    headers: List[str],
    nwc_by_period: Dict[str, Optional[float]],
) -> Dict[str, Optional[float]]:
    """Period-over-period change, using the immediately preceding column.

    Because TTM sits directly before NFY, this makes the NFY change
    exactly NFY - TTM, which is the specified formula.
    """
    out: Dict[str, Optional[float]] = {}
    for idx, period in enumerate(headers):
        prior_period = headers[idx - 1] if idx > 0 else None
        this_nwc = nwc_by_period.get(period)
        prior_nwc = nwc_by_period.get(prior_period) if prior_period else None
        out[period] = (
            _sub(this_nwc, prior_nwc)
            if prior_period and this_nwc is not None and prior_nwc is not None
            else None
        )
    return out


# ---------------------------------------------------------------------------
# GPC peer NWC
# ---------------------------------------------------------------------------

def peer_nwc_parts(
    bs_rows: list,
    is_rows: list,
    ticker: str,
    period: str,
    exclude_cash: bool,
) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    """Return (nwc_dollars, revenue, nwc_pct) for one peer / period.

        DFNWC   = TCA - [TCL - CPLTD - STD - CPL]
        DFCFNWC = (TCA - cash bucket) - [TCL - CPLTD - STD - CPL]

    Cash bucket prefers the published "Cash & Short-Term Investments"
    subtotal; only if that row is absent does it sum Cash + ST
    Investments (adding both would double-count).
    """
    bs = build_lookup(bs_rows or [], ticker)
    is_ = build_lookup(is_rows or [], ticker)

    def bs_val(field_key: str) -> Optional[float]:
        sa_label = get_sa_label(GPC_NWC_KEYS[field_key])
        return parse_number(bs.get(sa_label, {}).get(period, ""))

    def is_val(field_key: str) -> Optional[float]:
        sa_label = get_sa_label(GPC_NWC_KEYS[field_key])
        return parse_number(is_.get(sa_label, {}).get(period, ""))

    tca = bs_val("tca")
    tcl = bs_val("tcl")
    rev = is_val("rev")

    if tca is None or tcl is None or not rev:
        return None, None, None

    debt_free_cl = (
        tcl
        - (bs_val("cpltd") or 0.0)
        - (bs_val("std") or 0.0)
        - (bs_val("cpl") or 0.0)
    )

    if exclude_cash:
        cash_sti = bs_val("cash_sti")
        if cash_sti is not None:
            cash_bucket = cash_sti
        else:
            cash_bucket = (bs_val("cash") or 0.0) + (bs_val("st_inv") or 0.0)
        nwc = (tca - cash_bucket) - debt_free_cl
    else:
        nwc = tca - debt_free_cl

    return nwc, rev, nwc / rev


def peer_series(
    bs_rows: list,
    is_rows: list,
    tickers: List[str],
    periods: List[str],
    exclude_cash: bool,
) -> Dict[str, Dict[str, Dict[str, Optional[float]]]]:
    """{ticker: {"nwc": {period: v}, "rev": {...}, "pct": {...}}}

    Computed for EVERY ticker regardless of exclusion — exclusion only
    affects the statistic rows, never the chart.
    """
    out: Dict[str, Dict[str, Dict[str, Optional[float]]]] = {}
    for ticker in tickers:
        series = {"nwc": {}, "rev": {}, "pct": {}}
        for period in periods:
            nwc_d, rev_d, pct = peer_nwc_parts(
                bs_rows, is_rows, ticker, period, exclude_cash
            )
            series["nwc"][period] = nwc_d
            series["rev"][period] = rev_d
            series["pct"][period] = pct
        out[ticker] = series
    return out


def peer_statistics(
    peer_pct: Dict[str, Dict[str, Optional[float]]],
    periods: List[str],
    excluded: Dict[str, bool],
) -> Dict[str, Dict[str, Optional[float]]]:
    """{stat_name: {period: value_or_None}}

    Excluded tickers contribute nothing. A period with no usable
    values yields None for every statistic (rendered as "NA").
    """
    stat_funcs = {
        "Maximum":        lambda v: max(v),
        "Third Quartile": lambda v: quartile(v, 0.75),
        "Average":        lambda v: sum(v) / len(v),
        "Median":         lambda v: statistics.median(v),
        "First Quartile": lambda v: quartile(v, 0.25),
        "Minimum":        lambda v: min(v),
    }

    out: Dict[str, Dict[str, Optional[float]]] = {
        name: {} for name in STAT_NAMES
    }

    for period in periods:
        vals: List[float] = []
        for ticker, by_period in peer_pct.items():
            if excluded.get(ticker):
                continue
            v = by_period.get(period)
            if v is not None:
                vals.append(v)

        for name in STAT_NAMES:
            if not vals:
                out[name][period] = None
                continue
            try:
                out[name][period] = stat_funcs[name](vals)
            except Exception:
                out[name][period] = None

    return out


# ---------------------------------------------------------------------------
# Bridge
# ---------------------------------------------------------------------------

def nwc_bridge(
    ttm_revenue: Optional[float],
    ttm_nwc: Optional[float],
    selected_pct: Optional[float],
) -> Dict[str, Optional[float]]:
    """Normalized vs. actual NWC at TTM, and the resulting surplus."""
    normalized = _mul(ttm_revenue, selected_pct)
    surplus = (
        _sub(ttm_nwc, normalized)
        if (normalized is not None or ttm_nwc is not None)
        else None
    )
    return {
        "normalized_nwc": normalized,
        "actual_nwc": ttm_nwc,
        "surplus_deficit": surplus,
    }