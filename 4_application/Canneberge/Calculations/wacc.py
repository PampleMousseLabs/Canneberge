"""
wacc.py
Canneberge — Weighted Average Cost of Capital calculation engine.

Pure calculation layer. No Qt, no Dash, no page imports.

Extracted from Ui/wacc_page.py so desktop and web share one definition.
Ui/wacc_page.py is deliberately left untouched — it works. Once the web
page is proven at parity, desktop can be refactored to import from here.

The comp-set ratios (Debt/TIC, Debt/Equity, effective tax rate) already
lived in Calculations/ratio_catalogue.py and are re-exported through
here so callers have one import surface for "everything WACC".

DELIBERATE BEHAVIORS PRESERVED — do not "fix" these:

  * parse_pct_input treats a magnitude > 1 as already-percent and
    divides by 100; a magnitude <= 1 is taken as already-decimal.
    So "5" -> 0.05, but "0.5" -> 0.50. This is NOT the NWC page's
    always-divide-by-100 rule. Two different fields, two different
    conventions, both intentional.

  * Debt/TIC changes BASIS with the Capital Structure dropdown:
      "As of Valuation Date"  -> BOOK basis, Debt / (Debt + Book Equity)
      "Historical N Yr..."    -> MARKET basis, avg of Debt / MVIC
    These are genuinely different ratios, not two ways of averaging
    the same one. Confirmed intentional.

  * Effective tax rate priority: 3-yr average of LFY/LFY-1/LFY-2
    (all three required, TTM deliberately excluded), else LFY alone,
    else the Home page's Tax Rate.

  * WACC is ROUNDED to 4 decimals (== 2 decimal places as a percent)
    and that rounded value is what downstream PV math consumes. This
    is not a display-only rounding; it mirrors Excel's own rounded
    WACC cell.

  * Re-Levered Beta on each comp row uses the SELECTED target capital
    structure, not that comp's own. The Selected row's Re-Levered Beta
    is a separate user-typed figure and is what feeds Ke.
"""

import math
import statistics as _stats
from typing import Optional, Dict, List

from Canneberge.Calculations.ratio_catalogue import (
    compute_debt_to_tic_book,
    compute_historic_capital_structure,
    debt_to_equity_from_debt_to_tic,
    compute_effective_tax_rate,
)

__all__ = [
    "BETA_TYPE_OPTIONS", "BETA_FREQUENCY_OPTIONS", "CAPITAL_STRUCTURE_OPTIONS",
    "CAPITAL_STRUCTURE_HEADER_MAP", "CORPORATE_RATE_SERIES", "BETA_COLUMN_MAP",
    "RISK_FREE_SERIES_ID", "DATA_COLS", "BETA_COLS", "STAT_NAMES",
    "parse_pct_input", "to_float", "fred_pct", "fmt_beta", "fmt_pct",
    "quartile", "unlevered_beta", "relevered_beta",
    "observed_beta", "historical_periods_for_structure",
    "comp_row_metrics", "comp_table", "column_statistics",
    "risk_free_rate", "pretax_cost_of_debt",
    "cost_of_equity", "after_tax_cost_of_debt", "wacc_summary",
    "compute_debt_to_tic_book", "compute_historic_capital_structure",
    "debt_to_equity_from_debt_to_tic", "compute_effective_tax_rate",
]


# ---------------------------------------------------------------------------
# Option sets
# ---------------------------------------------------------------------------

BETA_TYPE_OPTIONS = ["Raw Betas", "Adjusted Betas"]
BETA_FREQUENCY_OPTIONS = ["5-Year Monthly", "2-Year Weekly"]
CAPITAL_STRUCTURE_OPTIONS = [
    "As of Valuation Date",
    "Historical 2 Yr. Average",
    "Historical 5 Year Average",
]

CAPITAL_STRUCTURE_HEADER_MAP = {
    "As of Valuation Date":      "Debt (Book) as a % of TIC",
    "Historical 2 Yr. Average":  "2 Yr. Historic Capital Structure",
    "Historical 5 Year Average": "5 Yr. Historic Capital Structure",
}

# Beta Type + Beta Frequency -> column in the Beta/Vol (Yahoo) source rows.
# Capital Structure is deliberately NOT part of this map.
BETA_COLUMN_MAP = {
    ("Raw Betas",      "2-Year Weekly"):  "2yr Raw",
    ("Adjusted Betas", "2-Year Weekly"):  "2yr Adj",
    ("Raw Betas",      "5-Year Monthly"): "5yr Raw",
    ("Adjusted Betas", "5-Year Monthly"): "5yr Adj",
}

CORPORATE_RATE_SERIES = {
    "ICE BofA US Corporate Master": "BAMLC0A0CMEY",
    "ICE BofA AAA US Corporate":    "BAMLC0A1CAAAEY",
    "ICE BofA AA US Corporate":     "BAMLC0A2CAAEY",
    "ICE BofA A US Corporate":      "BAMLC0A3CAEY",
    "ICE BofA BBB US Corporate":    "BAMLC0A4CBBBEY",
}

RISK_FREE_SERIES_ID = "DGS20"

DATA_COLS = [
    "beta", "debt_equity", "debt_tic",
    "tax_rate", "unlevered_beta", "relevered_beta",
]
BETA_COLS = {"beta", "unlevered_beta", "relevered_beta"}

STAT_NAMES = [
    "Maximum", "Third Quartile", "Average",
    "Median", "First Quartile", "Minimum",
]


# ---------------------------------------------------------------------------
# Parsing / formatting
# ---------------------------------------------------------------------------

def to_float(raw) -> Optional[float]:
    if raw is None:
        return None
    try:
        val = float(str(raw).replace(",", ""))
    except (ValueError, TypeError):
        return None
    if math.isnan(val) or math.isinf(val):
        return None
    return val


def parse_pct_input(text) -> Optional[float]:
    """'5.0%' or '5' -> 0.05 ; '0.5' -> 0.50.

    Magnitude > 1 is assumed to be a percent figure; <= 1 is assumed to
    already be a decimal. Verbatim desktop behavior.
    """
    if text is None:
        return None
    raw = str(text).strip().replace(",", "").replace("%", "")
    if not raw:
        return None
    try:
        val = float(raw)
    except (ValueError, TypeError):
        return None
    if math.isnan(val) or math.isinf(val):
        return None
    return val / 100.0 if abs(val) > 1 else val


def fred_pct(raw) -> Optional[float]:
    """FRED LatestValue is a bare number meaning a percent ('4.98' == 4.98%).

    Different shape than StockAnalysis's '%'-suffixed strings, which is
    why this is separate from ratio_catalogue._to_pct_float.
    """
    val = to_float(raw)
    return val / 100.0 if val is not None else None


def fmt_beta(value: Optional[float]) -> str:
    return "NA" if value is None else f"{value:.2f}"


def fmt_pct(value: Optional[float]) -> str:
    return "NA" if value is None else f"{value * 100:.1f}%"


def quartile(values: List[float], q: float) -> Optional[float]:
    if not values:
        return None
    vals = sorted(values)
    n = len(vals)
    if n == 1:
        return vals[0]
    idx = q * (n - 1)
    lo = int(idx)
    hi = lo + 1
    if hi >= n:
        return vals[-1]
    return vals[lo] + (idx - lo) * (vals[hi] - vals[lo])


# ---------------------------------------------------------------------------
# Beta math
# ---------------------------------------------------------------------------

def unlevered_beta(
    observed: Optional[float],
    debt_pct_equity: Optional[float],
    tax_rate: Optional[float],
) -> Optional[float]:
    """Ba = Be / [ 1 + (D/E)(1 - T) ]"""
    if observed is None or debt_pct_equity is None or tax_rate is None:
        return None
    denom = 1 + debt_pct_equity * (1 - tax_rate)
    if denom == 0:
        return None
    return observed / denom


def relevered_beta(
    unlevered: Optional[float],
    selected_debt_pct_tic: Optional[float],
    selected_tax_rate: Optional[float],
) -> Optional[float]:
    """Be = Ba x [ 1 + (Wd / We)(1 - T) ], with We = 1 - Wd."""
    if unlevered is None or selected_debt_pct_tic is None or selected_tax_rate is None:
        return None
    if selected_debt_pct_tic == 1:
        return None
    factor = 1 + (
        selected_debt_pct_tic / (1 - selected_debt_pct_tic)
    ) * (1 - selected_tax_rate)
    return unlevered * factor


def observed_beta(
    beta_vol_rows: list,
    ticker: str,
    beta_type: str,
    beta_frequency: str,
) -> Optional[float]:
    col = BETA_COLUMN_MAP.get((beta_type, beta_frequency))
    if not col:
        return None
    target = str(ticker or "").strip().upper()
    for row in beta_vol_rows or []:
        if str(row.get("Ticker", "")).strip().upper() == target:
            return to_float(row.get(col))
    return None


# ---------------------------------------------------------------------------
# Comp table
# ---------------------------------------------------------------------------

def historical_periods_for_structure(
    capital_structure: str,
    historical_period_columns: List[str],
) -> List[str]:
    """Period list feeding the historical (market-basis) averages.

    2 Yr uses the last three period labels, 5 Yr uses all of them —
    verbatim desktop slicing.
    """
    hist = list(historical_period_columns) + ["TTM"]
    if capital_structure == "Historical 2 Yr. Average":
        return hist[-3:] if len(hist) >= 3 else hist
    return hist


def comp_row_metrics(
    ticker: str,
    beta_vol_rows: list,
    bs_rows: list,
    ratio_rows: list,
    is_rows: list,
    beta_type: str,
    beta_frequency: str,
    capital_structure: str,
    historical_period_columns: List[str],
    selected_debt_tic: Optional[float],
    selected_tax_rate: Optional[float],
    fallback_tax_rate: Optional[float],
) -> Dict[str, Optional[float]]:
    """All six data columns for one comparable."""
    beta = observed_beta(beta_vol_rows, ticker, beta_type, beta_frequency)

    if capital_structure in (
        "Historical 2 Yr. Average", "Historical 5 Year Average",
    ):
        periods = historical_periods_for_structure(
            capital_structure, historical_period_columns
        )
        debt_tic = compute_historic_capital_structure(
            bs_rows, ratio_rows, ticker, periods
        )
    else:
        debt_tic = compute_debt_to_tic_book(bs_rows, ticker, "TTM")

    debt_equity = debt_to_equity_from_debt_to_tic(debt_tic)
    tax_rate = compute_effective_tax_rate(
        is_rows, ticker, fallback_rate=fallback_tax_rate
    )
    unlev = unlevered_beta(beta, debt_equity, tax_rate)
    relev = relevered_beta(unlev, selected_debt_tic, selected_tax_rate)

    return {
        "beta": beta,
        "debt_equity": debt_equity,
        "debt_tic": debt_tic,
        "tax_rate": tax_rate,
        "unlevered_beta": unlev,
        "relevered_beta": relev,
    }


def comp_table(
    tickers: List[str],
    beta_vol_rows: list,
    bs_rows: list,
    ratio_rows: list,
    is_rows: list,
    beta_type: str,
    beta_frequency: str,
    capital_structure: str,
    historical_period_columns: List[str],
    selected_debt_tic: Optional[float],
    selected_tax_rate: Optional[float],
    fallback_tax_rate: Optional[float],
) -> Dict[str, Dict[str, Optional[float]]]:
    """{ticker: {col: value}} for every comp, exclusions ignored here."""
    return {
        t: comp_row_metrics(
            t, beta_vol_rows, bs_rows, ratio_rows, is_rows,
            beta_type, beta_frequency, capital_structure,
            historical_period_columns,
            selected_debt_tic, selected_tax_rate, fallback_tax_rate,
        )
        for t in tickers
    }


def column_statistics(
    rows: Dict[str, Dict[str, Optional[float]]],
    excluded: Dict[str, bool],
) -> Dict[str, Dict[str, Optional[float]]]:
    """{stat_name: {col: value_or_None}} over INCLUDED comps only."""
    funcs = {
        "Maximum":        lambda v: max(v),
        "Third Quartile": lambda v: quartile(v, 0.75),
        "Average":        lambda v: sum(v) / len(v),
        "Median":         lambda v: _stats.median(v),
        "First Quartile": lambda v: quartile(v, 0.25),
        "Minimum":        lambda v: min(v),
    }

    pooled: Dict[str, List[float]] = {c: [] for c in DATA_COLS}
    for ticker, metrics in rows.items():
        if excluded.get(ticker):
            continue
        for col in DATA_COLS:
            val = metrics.get(col)
            if val is not None:
                pooled[col].append(val)

    out: Dict[str, Dict[str, Optional[float]]] = {n: {} for n in STAT_NAMES}
    for name in STAT_NAMES:
        for col in DATA_COLS:
            vals = pooled[col]
            if not vals:
                out[name][col] = None
                continue
            try:
                out[name][col] = funcs[name](vals)
            except Exception:
                out[name][col] = None
    return out


# ---------------------------------------------------------------------------
# FRED lookups
# ---------------------------------------------------------------------------

def _fred_value(fred_rows: list, series_id: Optional[str]) -> Optional[float]:
    if not series_id:
        return None
    target = str(series_id).strip().upper()
    for row in fred_rows or []:
        if str(row.get("SeriesID", "")).strip().upper() == target:
            return fred_pct(row.get("LatestValue"))
    return None


def risk_free_rate(fred_rows: list) -> Optional[float]:
    """20-year constant maturity Treasury (DGS20)."""
    return _fred_value(fred_rows, RISK_FREE_SERIES_ID)


def pretax_cost_of_debt(fred_rows: list, series_label: str) -> Optional[float]:
    return _fred_value(fred_rows, CORPORATE_RATE_SERIES.get(series_label))


# ---------------------------------------------------------------------------
# Ke / Kd / WACC
# ---------------------------------------------------------------------------

def cost_of_equity(
    rf: Optional[float],
    selected_relevered_beta: Optional[float],
    erp: Optional[float],
    size_premium: Optional[float],
    csrp: Optional[float],
) -> Dict[str, Optional[float]]:
    """Ke = Rf + Be(Rm - Rf) + SP + CSRP

    Every term is required. A blank Size Premium is NOT treated as 0 —
    desktop leaves Ke as NA until all four are populated.
    """
    adjusted_erp = (
        selected_relevered_beta * erp
        if selected_relevered_beta is not None and erp is not None
        else None
    )
    ke = None
    if None not in (rf, adjusted_erp, size_premium, csrp):
        ke = rf + adjusted_erp + size_premium + csrp
    return {"adjusted_erp": adjusted_erp, "cost_of_equity": ke}


def after_tax_cost_of_debt(
    pretax_kd: Optional[float],
    tax_rate: Optional[float],
) -> Optional[float]:
    """Kd = Kd(1 - T)"""
    if pretax_kd is None or tax_rate is None:
        return None
    return pretax_kd * (1 - tax_rate)


def wacc_summary(
    selected_debt_tic: Optional[float],
    ke: Optional[float],
    after_tax_kd: Optional[float],
) -> Dict[str, Optional[float]]:
    """We/Wd weights, weighted components, and the rounded WACC.

    WACC is rounded to 4 decimals (2 dp as a percent) and that rounded
    figure is the one downstream PV math must use.
    """
    we = 1 - selected_debt_tic if selected_debt_tic is not None else None
    wd = selected_debt_tic

    weighted_ke = we * ke if we is not None and ke is not None else None
    weighted_kd = (
        wd * after_tax_kd
        if wd is not None and after_tax_kd is not None
        else None
    )

    wacc = None
    if weighted_ke is not None and weighted_kd is not None:
        wacc = round(weighted_ke + weighted_kd, 4)

    return {
        "we": we,
        "wd": wd,
        "weighted_cost_of_equity": weighted_ke,
        "weighted_cost_of_debt": weighted_kd,
        "wacc": wacc,
    }