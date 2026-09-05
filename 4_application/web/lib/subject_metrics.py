"""
web/lib/subject_metrics.py

Pure Python resolver for subject company financial data. Zero Dash, zero PyQt.

Data flow mirrors the desktop SubjectFinancialsPage:
  - Public + Historical/TTM → StockAnalysis rows in source_data_results["stockanalysis"]
  - Private + Historical/TTM → session_data["private_is_data"] / ["private_bs_data"]
  - Projections (public OR private) → session_data["projection_page_state"]

Single entry point downstream pages should call:
    get_subject_metric_value(session_data, source_results, line_key, period)

Everything else in this module is either a helper or a "just this piece" accessor
(get_historical_line_values, get_subject_debt) used by pages that need bulk reads.
"""

from typing import Optional, Dict
import math

from Canneberge.app_state import (
    ProjectInputs, PrivateFinancials, ProjectionData, IS_LINES, BS_LINES
)
from Canneberge.Transforms.sa_key import get_sa_labels, get_sa_source, get_sign_flip
from Canneberge.utils.sa_utils import build_lookup, to_float
from Canneberge.Calculations.subject_is_bs_calc import (
    compute_is_calculated,
    compute_bs_calculated,
    BS_DIRECT_PULL_KEYS,
)
from Canneberge.Calculations.projection_resolve import resolve_projection_waterfall
from web.lib.session_io import dict_to_project_inputs

# =====================================================================
# HELPERS — dict → dataclass conversion
# =====================================================================

def dict_to_private_financials(session_data: dict) -> PrivateFinancials:
    """Rehydrate PrivateFinancials from session-store dict.

    Session-store stores raw is_data/bs_data as flat nested dicts.
    Empty dicts are fine — PrivateFinancials.get_is/get_bs return None
    for missing keys, which is what all downstream code expects.
    """
    return PrivateFinancials(
        is_data=(session_data or {}).get("private_is_data", {}),
        bs_data=(session_data or {}).get("private_bs_data", {}),
    )


def dict_to_projection_data(session_data: dict) -> ProjectionData:
    """Rehydrate ProjectionData from session-store's projection_page_state.

    Values are stored as raw floats keyed by period label ("NFY", "NFY+1", ...).
    Empty state → returns a ProjectionData with all-empty dicts, which behaves
    correctly (every .get() returns None).
    """
    state = (session_data or {}).get("projection_page_state", {})
    pd = ProjectionData()
    if not state:
        return pd

    def _load(field_name):
        raw = state.get(field_name, {})
        return {k: _parse_val(v) for k, v in raw.items()}

    pd.revenue = _load("revenue")
    pd.revenue_growth = _load("revenue_growth")
    pd.gross_profit = _load("gross_profit")
    pd.gp_improvement = _load("gp_improvement")
    pd.ebitda = _load("ebitda")
    pd.ebitda_improvement = _load("ebitda_improvement")
    pd.da = _load("da")
    pd.da_pct = _load("da_pct")
    pd.sbc = _load("sbc")
    pd.sbc_pct = _load("sbc_pct")
    pd.other_amort = _load("other_amort")
    pd.other_amort_pct = _load("other_amort_pct")
    pd.net_income = _load("net_income")
    pd.net_income_margin = _load("net_income_margin")
    pd.capex = _load("capex")
    pd.capex_pct = _load("capex_pct")
    if hasattr(pd, "other_adj"):
        pd.other_adj = _load("other_adj")
    # These two are non-numeric strings ("revenue" / "growth"), don't _parse_val them
    pd.last_edited_revenue = dict(state.get("last_edited_revenue", {}) or {})
    pd.last_edited_ni = dict(state.get("last_edited_ni", {}) or {})
    return pd


def _parse_val(value) -> Optional[float]:
    """Same forgiving parser used across the Canneberge codebase — handles
    None, empty string, '-', 'nan', comma-formatted numbers, and rejects NaN/Inf."""
    if value is None or str(value).strip().lower() in ("", "-", "nan", "none"):
        return None
    try:
        v = float(str(value).replace(",", ""))
        if math.isnan(v) or math.isinf(v):
            return None
        return v
    except (ValueError, TypeError):
        return None


def _get_projected_interest_expense(session_data: dict, period: str) -> Optional[float]:
    """Return the Debt Schedule's POSITIVE interest-expense amount for a period."""
    debt_state = (session_data or {}).get("debt_page_state", {}) or {}
    projected_interest = debt_state.get("interest_expense_by_period", {}) or {}
    if not projected_interest:
        projected_interest = debt_state.get("projected_interest", {}) or {}
    return _parse_val(projected_interest.get(period))


def _normalise_rate(value) -> Optional[float]:
    """Accept 0.21, 21, '21%', '0.21' → 0.21."""
    if value is None:
        return None
    raw = str(value).strip()
    has_pct = "%" in raw
    raw = raw.replace("%", "").replace(",", "").strip()
    try:
        rate = float(raw)
    except (TypeError, ValueError):
        return None
    if math.isnan(rate) or math.isinf(rate):
        return None
    return rate / 100.0 if (has_pct or abs(rate) > 1.0) else rate

# =====================================================================
# StockAnalysis row lookups (public path only)
# =====================================================================

def _build_stmt_lookup(source_results: dict, statement: str, ticker: str) -> Dict[str, Dict[str, str]]:
    """Build a {sa_label_lower: {period: raw_value}} lookup for one statement + ticker.

    Uses the shared build_lookup from sa_utils so its behavior matches every other
    consumer of StockAnalysis rows (desktop + web).
    """
    rows = (source_results or {}).get("stockanalysis", {}).get(statement, []) or []
    return build_lookup(rows, ticker)


def _resolve_sa_row(source_lookup: Dict[str, Dict], sa_labels: list) -> Dict[str, str]:
    """Given the priority-ordered list of SA labels for one internal key,
    return the first matching row's period→value dict. Empty dict if none match.
    """
    for label in sa_labels:
        row = source_lookup.get(label, {})
        if row:
            return row
    return {}


# =====================================================================
# PUBLIC API — bulk historical reads
# =====================================================================

def get_historical_line_values(
    session_data: dict,
    source_results: dict,
    key: str,
    statement: str = "IS",
) -> Dict[str, Optional[float]]:
    """Return {period: float_or_None} for one line-item key across historicals + TTM.

    Public: reads from StockAnalysis rows in source_results.
    Private: reads from PrivateFinancials in session_data.

    Calculated rows (is_calc=True in IS_LINES/BS_LINES) get computed on the fly
    from raw components via compute_is_calculated / compute_bs_calculated —
    EXCEPT the four in BS_DIRECT_PULL_KEYS, which get direct-pulled from SA
    because their components don't scrape reliably enough to sum locally.
    """
    inputs = dict_to_project_inputs(session_data)
    periods = inputs.historical_period_columns + ["TTM"]
    lines = IS_LINES if statement == "IS" else BS_LINES

    is_calc = next((c for k, l, c, b in lines if k == key), False)

    # Assemble raw-value dict per period, from either public or private source.
    raw_by_period: Dict[str, Dict[str, Optional[float]]] = {p: {} for p in periods}

    # CFS add-backs that are NOT standalone rows in IS_LINES but that the
    # calculated EBITDA / Adjusted EBITDA rows require.
    _CFS_ADDBACK_KEYS = ("stock_based_compensation", "other_amortization")

    if inputs.is_publicly_traded:
        ticker = inputs.subject_ticker.lower()
        stmt_lookup = _build_stmt_lookup(source_results, statement, ticker)
        # CFS lookup needed for IS keys whose SA source is "CFS"
        # (capex, acquisitions, SBC, other amortization).
        cfs_lookup = _build_stmt_lookup(source_results, "CFS", ticker) if statement == "IS" else {}

        for k2, _label, c2, _bold in lines:
            # Skip pure calc rows (we'll compute them below), EXCEPT the four
            # direct-pull BS keys which SA publishes but we mark is_calc for bolding.
            if c2 and not (statement == "BS" and k2 in BS_DIRECT_PULL_KEYS):
                continue

            sa_source = get_sa_source(k2)
            sa_labels = get_sa_labels(k2)
            sign_flip = get_sign_flip(k2)
            source_lookup = cfs_lookup if sa_source == "CFS" else stmt_lookup

            row_data = _resolve_sa_row(source_lookup, sa_labels)
            for period in periods:
                v = _parse_val(row_data.get(period, ""))
                if v is not None and sign_flip:
                    v = -v
                raw_by_period[period][k2] = v

        if statement == "IS":
            for extra_key in _CFS_ADDBACK_KEYS:
                row_data = _resolve_sa_row(cfs_lookup, get_sa_labels(extra_key))
                for period in periods:
                    raw_by_period[period][extra_key] = _parse_val(row_data.get(period, ""))
    else:
        pf = dict_to_private_financials(session_data)
        for k2, _label, c2, _bold in lines:
            if c2 and not (statement == "BS" and k2 in BS_DIRECT_PULL_KEYS):
                continue
            for period in periods:
                if statement == "IS":
                    raw_by_period[period][k2] = pf.get_is(k2, period)
                else:
                    raw_by_period[period][k2] = pf.get_bs(k2, period)

        if statement == "IS":
            for extra_key in _CFS_ADDBACK_KEYS:
                for period in periods:
                    raw_by_period[period][extra_key] = pf.get_is(extra_key, period)

    # Compute calc rows once per period, then resolve the requested key.
    compute_fn = compute_is_calculated if statement == "IS" else compute_bs_calculated
    result: Dict[str, Optional[float]] = {}
    for period in periods:
        if is_calc and statement == "BS" and key in BS_DIRECT_PULL_KEYS:
            result[period] = raw_by_period[period].get(key)
        elif is_calc:
            result[period] = compute_fn(raw_by_period[period]).get(key)
        else:
            result[period] = raw_by_period[period].get(key)

    # Alias-only fallback: keys like "depreciation" alias into "d&a_for_ebitda" via
    # sa_key's _EXPLICIT_ALIASES but don't appear as their own row in IS_LINES.
    # If nothing resolved above AND we're public, try a direct SA lookup by the
    # requested key. Historical parity with desktop's get_historical_line_values.
    if statement == "IS" and inputs.is_publicly_traded and not any(v is not None for v in result.values()):
        ticker = inputs.subject_ticker.lower()
        sa_source = get_sa_source(key)
        sa_labels = get_sa_labels(key)
        sign_flip = get_sign_flip(key)
        source_lookup = (
            _build_stmt_lookup(source_results, "CFS", ticker)
            if sa_source == "CFS"
            else _build_stmt_lookup(source_results, "IS", ticker)
        )
        row_data = _resolve_sa_row(source_lookup, sa_labels)
        for period in periods:
            v = _parse_val(row_data.get(period, ""))
            if v is not None and sign_flip:
                v = -v
            result[period] = v

    return result


# =====================================================================
# PUBLIC API — total debt (BS aggregate)
# =====================================================================

def get_subject_debt(session_data: dict, source_results: dict) -> float:
    """Sum of ST debt + current portion of LTD + LT debt at TTM.
    Mirrors desktop SubjectFinancialsPage.get_subject_debt() exactly.
    Returns 0.0 (not None) when no debt data — matches desktop behavior.
    """
    inputs = dict_to_project_inputs(session_data)
    res = 0.0
    keys = ["st_debt", "current_ltd", "lt_debt"]

    if inputs.is_private:
        pf = dict_to_private_financials(session_data)
        for k in keys:
            v = pf.get_bs(k, "TTM")
            if v is not None:
                res += v
    else:
        bs_rows = (source_results or {}).get("stockanalysis", {}).get("BS", []) or []
        bs_lookup = build_lookup(bs_rows, inputs.subject_ticker)
        for k in keys:
            for sa_label in get_sa_labels(k):
                row_data = bs_lookup.get(sa_label, {})
                if row_data:
                    v = to_float(row_data.get("TTM"))
                    if v is not None:
                        res += v
                    break

    return res


# =====================================================================
# PUBLIC API — single metric lookup (the one downstream pages call)
# =====================================================================

def get_subject_metric_value(
    session_data: dict,
    source_results: dict,
    key: str,
    period: str,
) -> Optional[float]:
    """Single entry point: return one canonical subject-company metric at one period.

    Historical/TTM: delegates to get_historical_line_values with auto IS/BS routing.
                    Every calculated row (EBIT, EBITDA, Adjusted EBITDA, Net Interest,
                    Pretax, NI, ...) comes from compute_is_calculated.
    Projection:     ProjectionData drivers + the SAME waterfall function the
                    Projection Module uses (resolve_projection_waterfall), so this
                    resolver, the modal, GPC and DCF agree on every projected line.
    """
    inputs = dict_to_project_inputs(session_data)

    # ---- Historical / TTM branch ----
    if period in inputs.historical_period_columns + ["TTM"]:
        statement = "BS" if any(k == key for k, *_r in BS_LINES) else "IS"

        # D&A schema drift: caller asks for "depreciation" but current SA schema
        # uses "d&a for ebitda". Try modern → legacy names.
        if key == "depreciation" and statement == "IS":
            for try_key in ("d&a_for_ebitda", "depreciation_amortization", "depreciation"):
                val = get_historical_line_values(session_data, source_results, try_key, "IS").get(period)
                if val is not None:
                    return val
            return None

        return get_historical_line_values(session_data, source_results, key, statement).get(period)

    # ---- Projection branch (NFY, NFY+1, ...) ----
    if period in inputs.projection_period_columns:
        pd = dict_to_projection_data(session_data)

        revenue = pd.revenue.get(period)
        gross_profit = pd.gross_profit.get(period)
        adjusted_ebitda = pd.ebitda.get(period)   # Projection Module stores ADJUSTED EBITDA here
        da = pd.da.get(period)
        other_amort = pd.other_amort.get(period)
        sbc = pd.sbc.get(period)
        capex = pd.capex.get(period)

        # Debt Schedule interest is a positive cost; the IS shows SIGNED net interest.
        # No projected interest income is modelled yet, so net = -expense.
        interest_expense = _get_projected_interest_expense(session_data, period)
        net_interest = -abs(interest_expense) if interest_expense is not None else None

        tax_rate = _normalise_rate(getattr(inputs, "subject_tax_rate", None))

        # Public NFY..NFY+2: the modal saved analyst NI into pd.net_income and the
        # pre-tax plug into pd.other_adj. Re-solve the plug here only when analyst
        # NI is actually present; otherwise use the saved plug as-is.
        is_ms_period = inputs.is_publicly_traded and period in {"NFY", "NFY+1", "NFY+2"}
        analyst_ni = pd.net_income.get(period) if is_ms_period else None
        solve_plug = is_ms_period and analyst_ni is not None

        waterfall = resolve_projection_waterfall(
            adjusted_ebitda=adjusted_ebitda,
            da=da,
            other_amort=other_amort,
            sbc=sbc,
            net_interest=net_interest,
            other_adj=pd.other_adj.get(period),
            tax_rate=tax_rate,
            analyst_net_income=analyst_ni,
            solve_other_adjustment=solve_plug,
        )

        conventional_ebitda = (
            adjusted_ebitda - (sbc or 0.0) if adjusted_ebitda is not None else None
        )
        cogs = (
            revenue - gross_profit
            if revenue is not None and gross_profit is not None else None
        )
        operating_expenses = (
            gross_profit - waterfall["ebit"]
            if gross_profit is not None and waterfall["ebit"] is not None else None
        )

        net_income = waterfall["net_income"]

        interest_after_tax = None
        if interest_expense is not None:
            interest_after_tax = (
                interest_expense * (1.0 - tax_rate) if tax_rate is not None else interest_expense
            )

        debt_free_net_income = None
        if net_income is not None or interest_after_tax is not None:
            debt_free_net_income = (net_income or 0.0) + (interest_after_tax or 0.0)

        projected: Dict[str, Optional[float]] = {
            "revenue": revenue,
            "cogs": cogs,
            "cost_of_goods_sold": cogs,
            "gross_profit": gross_profit,
            "operating_expenses": operating_expenses,

            # Conventional vs adjusted EBITDA are distinct keys.
            "ebitda": conventional_ebitda,
            "adj_ebitda": adjusted_ebitda,

            "d&a_for_ebitda": da,
            "depreciation": da,
            "amortization": other_amort,
            "other_amortization": other_amort,
            "stock_based_compensation": sbc,

            "ebit": waterfall["ebit"],

            # Dedicated expense row shows a positive cost; net interest is signed.
            "interest_expense": abs(interest_expense) if interest_expense is not None else None,
            "interest_income": None,
            "net_interest": waterfall["net_interest"],

            # The Projection Module's residual (pre-tax) non-operating plug.
            "other_income": waterfall["other_adj"],
            "other_adj": waterfall["other_adj"],

            "ebt_excluding_unusual_items": waterfall["pretax_income"],
            "pretax_income": waterfall["pretax_income"],
            "taxes": waterfall["taxes"],
            "income_before_nonrecurring": net_income,
            "nonrecurring": None,
            "net_income": net_income,
            "interest_expense_after_tax": interest_after_tax,
            "debt_free_net_income": debt_free_net_income,

            "capex": capex,
        }
        return projected.get(key)

    # Unknown period
    return None