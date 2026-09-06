"""
dcf.py
Canneberge — Discounted Cash Flow calculation engine.

Pure calculation layer. No Qt, no Dash, no page imports.

Extracted from Ui/dcf_page.py. The desktop page is left untouched.

DELIBERATE DEVIATIONS from the current desktop, all approved:

  * EBITDA row sources adj_ebitda (Adjusted EBITDA). OpEx = GP - Adj EBITDA.
    EBIT = Adj EBITDA - D&A - Other Amort (pre-SBC). Historical Amortization
    uses other_amortization, not the IS "amortization" key which is 0.
    Desktop currently mixes conventional sf("ebitda") into the EBITDA row
    while building EBIT off pd.ebitda; that split appeared when EBITDA was
    redefined and makes the projected rows not foot, double-deducts SBC on
    historicals, and understates the FCFF residual. This restores internal
    consistency without changing projected EBIT / Taxes / NOPAT / FCF.

  * Full precision throughout. Desktop reads intermediates back from
    formatted labels (integer $, 2-dp PVP), so exact tie-out is impossible
    either way; parity tolerance is ~0.05%.

  * Sensitivity re-discounts the EXPLICIT period at each column's rate,
    not just the terminal value. Desktop holds the explicit PV sum fixed.

PRESERVED desktop behaviors:

  * PV period chain: NFY = PPA/2, NFY+1 = 2*PVP_NFY + 0.5, then +1 each.
  * NFY PV multiplies FCF by PPA (partial year) before the PV factor.
  * Multiple-based TV discounts at final_pvp + 0.5; Gordon/H at final_pvp.
  * FCFE residual NOPAT = final Net Income x (1 + g), not rebuilt bottom-up.
  * Multiple-based TV returns None when WACC <= LTGR (cap_rate guard).
"""

import math
from datetime import datetime
from typing import Optional, Dict, List, Tuple, Any

__all__ = [
    "ROW_SPECS", "ROWS_WITH_BORDER_ABOVE", "ROWS_WITH_SPACER_ABOVE",
    "HIST_BLANK_ROWS", "TV_MODELS", "PCT_ROWS", "FACTOR_ROWS",
    "parse_pct", "parse_number", "parse_multiple", "normalise_rate",
    "safe_div", "dcf_period_columns", "dcf_fye_years", "calculate_ppa",
    "build_dcf", "fv_for_assumptions", "sensitivity_grid",
    "residual_revenue",
]


# ---------------------------------------------------------------------------
# Row schema — (key, label, bold, indent, margin)
# ---------------------------------------------------------------------------

ROW_SPECS: List[Tuple[str, str, bool, bool, bool]] = [
    ("revenue",            "Revenue",                                  True,  False, False),
    ("revenue_growth",     "Revenue Growth",                           False, False, True),
    ("cogs",               "Cost of Goods Sold",                       False, False, False),
    ("gross_profit",       "Gross Profit",                             True,  False, False),
    ("gp_margin",          "Gross Profit Margin",                      False, False, True),
    ("operating_expenses", "Operating Expenses",                       True,  False, False),
    ("ebitda",             "Adjusted EBITDA",                          True,  False, False),
    ("ebitda_margin",      "EBITDA Margin",                            False, False, True),
    ("depreciation",       "Depreciation",                             False, False, False),
    ("amortization",       "Amortization",                             False, False, False),
    ("net_interest",       "Net Interest Expense",                     False, False, False),
    ("ebit",               "EBIT",                                     True,  False, False),
    ("ebit_margin",        "EBIT Margin",                              False, False, True),
    ("sbc",                "Stock-Based Compensation",                 False, False, False),
    ("other_adj",          "+Other Adjustments",                       False, False, False),
    ("taxes",              "Taxes",                                    False, False, False),
    ("nopat",              "Net Operating Profit After Tax (NOPAT)",   True,  False, False),
    ("plus_dep",           "Plus: Depreciation",                       False, True,  False),
    ("less_nwc",           "Less: Increase/(Decrease) in DFCFNWC",     False, True,  False),
    ("less_capex",         "Less: Capital Expenditures (CapEx)",       False, True,  False),
    ("less_other_adj",     "Less: Other Adjustments",                  False, True,  False),
    ("fcf",                "Free Cash Flow",                           True,  False, False),
    ("ppa",                "Partial Period Adjustment",                False, False, False),
    ("pvp",                "Present Value Period",                     False, False, False),
    ("pvf",                "Present Value Factor",                     False, False, False),
    ("pv_fcf",             "Present Value of Free Cash Flows",         True,  False, False),
]

ROWS_WITH_BORDER_ABOVE = {
    "gross_profit", "ebitda", "ebit", "nopat", "fcf", "pv_fcf",
}
ROWS_WITH_SPACER_ABOVE = {"operating_expenses", "nopat", "ppa"}
HIST_BLANK_ROWS = {"ppa", "pvp", "pvf", "pv_fcf"}

PCT_ROWS = {"revenue_growth", "gp_margin", "ebitda_margin", "ebit_margin"}
FACTOR_ROWS = {"ppa", "pvp", "pvf"}

TV_MODELS = ["Gordon Growth", "EBITDA Multiple", "Revenue Multiple", "H-Model"]


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def parse_number(text) -> Optional[float]:
    if text is None:
        return None
    raw = str(text).strip().replace(",", "").replace("$", "").replace("%", "")
    if not raw or raw in ("-", "NA"):
        return None
    try:
        val = float(raw)
    except (TypeError, ValueError):
        return None
    if math.isnan(val) or math.isinf(val):
        return None
    return val


def parse_pct(text) -> Optional[float]:
    """Always divide by 100. '3.0%' and '3' both -> 0.03."""
    val = parse_number(text)
    return None if val is None else val / 100.0


def parse_multiple(text) -> Optional[float]:
    if text is None:
        return None
    raw = str(text).strip().lower().replace("x", "")
    return parse_number(raw)


def normalise_rate(value) -> Optional[float]:
    """Tax rate: accepts 0.21, 21, '21%'."""
    if value is None:
        return None
    raw = str(value).strip()
    has_pct = "%" in raw
    val = parse_number(raw.replace("%", ""))
    if val is None:
        return None
    return val / 100.0 if (has_pct or abs(val) > 1.0) else val


def safe_div(a: Optional[float], b: Optional[float]) -> Optional[float]:
    if a is None or b is None or b == 0:
        return None
    return a / b


def _sub(a: Optional[float], b: Optional[float]) -> Optional[float]:
    if a is None or b is None:
        return None
    return a - b


def _add_present(*values: Optional[float]) -> Optional[float]:
    """Sum, treating None as absent. None only if every input is None."""
    total = 0.0
    seen = False
    for v in values:
        if v is not None:
            total += v
            seen = True
    return total if seen else None


# ---------------------------------------------------------------------------
# Columns
# ---------------------------------------------------------------------------

def dcf_period_columns(
    historical_period_columns: List[str],
    projection_period_columns: List[str],
) -> Tuple[List[str], List[bool]]:
    """DCF has NO TTM column — historicals run LFY-N ... LFY only."""
    hist = list(historical_period_columns or [])
    proj = list(projection_period_columns or [])
    headers = hist + proj + ["Residual"]
    is_hist = [True] * len(hist) + [False] * len(proj) + [False]
    return headers, is_hist


def dcf_fye_years(
    historical_period_columns: List[str],
    projection_period_columns: List[str],
    lfy_year: Optional[int],
    nfy_year: Optional[int],
    nfy1_year: Optional[int],
    nfy2_year: Optional[int],
) -> Dict[str, str]:
    result: Dict[str, str] = {}

    for label in historical_period_columns or []:
        if label == "LFY":
            result[label] = str(lfy_year) if lfy_year is not None else ""
        else:
            try:
                n = int(label.split("-")[1])
                result[label] = str(lfy_year - n) if lfy_year is not None else ""
            except (IndexError, ValueError, TypeError):
                result[label] = ""

    for label in projection_period_columns or []:
        if label == "NFY":
            result[label] = str(nfy_year) if nfy_year is not None else ""
        elif label == "NFY+1":
            result[label] = str(nfy1_year) if nfy1_year is not None else ""
        elif label == "NFY+2":
            result[label] = str(nfy2_year) if nfy2_year is not None else ""
        else:
            try:
                n = int(label.split("+")[1])
                result[label] = str(nfy2_year + (n - 2)) if nfy2_year is not None else ""
            except (IndexError, ValueError, TypeError):
                result[label] = ""

    final_proj = (projection_period_columns or [])[-1] if projection_period_columns else None
    final_year = result.get(final_proj) if final_proj else None
    try:
        result["Residual"] = str(int(final_year) + 1) if final_year else ""
    except (TypeError, ValueError):
        result["Residual"] = ""

    return result


def calculate_ppa(nfy_end: Optional[str], valuation_date: Optional[str]) -> Optional[float]:
    """(NFY fiscal year end - valuation date) / 365.25. None if not positive."""
    if not nfy_end or not valuation_date:
        return None
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m-%d-%Y"):
        try:
            nfy_dt = datetime.strptime(str(nfy_end).strip(), fmt)
            val_dt = datetime.strptime(str(valuation_date).strip(), fmt)
        except ValueError:
            continue
        ppa = (nfy_dt - val_dt).days / 365.25
        return ppa if ppa > 0 else None
    return None


def residual_revenue(
    final_projected_revenue: Optional[float],
    ltgr: Optional[float],
) -> Optional[float]:
    """Single source of truth for the Residual column's Revenue.

    NWC imports this so its Residual column can be filled without a
    circular dependency back into the DCF page.
    """
    if final_projected_revenue is None or ltgr is None:
        return None
    return final_projected_revenue * (1.0 + ltgr)


# ---------------------------------------------------------------------------
# Waterfall
# ---------------------------------------------------------------------------

def build_dcf(
    historical_period_columns: List[str],
    projection_period_columns: List[str],
    sf,                                   # (key, period) -> Optional[float]
    changes_in_nwc: Dict[str, Optional[float]],
    net_interest_by_period: Dict[str, Optional[float]],
    other_adj_inputs: Dict[str, Any],
    residual_amortization: Any,
    tax_rate: Optional[float],
    discount_rate: Optional[float],
    ltgr: Optional[float],
    dep_pct_of_capex: Optional[float],
    ppa: Optional[float],
    is_fcfe: bool,
    tv_model: str,
    tv_inputs: Dict[str, Dict[str, Any]],
    bridge_other_adj: Any,
) -> Dict[str, Any]:
    """Full DCF: rows dict keyed [row_key][period], plus TV and bridge."""
    headers, is_hist = dcf_period_columns(
        historical_period_columns, projection_period_columns
    )
    num_hist = len(historical_period_columns or [])
    num_proj = len(projection_period_columns or [])

    rows: Dict[str, Dict[str, Optional[float]]] = {
        key: {p: None for p in headers} for key, *_ in ROW_SPECS
    }

    # ---------------- explicit columns (historical + projection) ----------
    for idx, period in enumerate(headers):
        if period == "Residual":
            continue

        rev = sf("revenue", period)
        gp = sf("gross_profit", period)
        adj_ebitda = sf("adj_ebitda", period)
        sbc = sf("stock_based_compensation", period)
        capex = sf("capex", period)

        dep = sf("d&a_for_ebitda", period)
        if dep is None:
            dep = sf("depreciation", period)
        if dep is None:
            dep = sf("depreciation_amortization", period)

        amort = sf("other_amortization", period)
        if amort is None:
            amort = sf("amortization", period)

        net_int = net_interest_by_period.get(period)
        # Projection Module pre-tax plug (EBIT + NI reconciling items).
        # Historicals have no plug; actual taxes/NI are used as-reported.
        other_adj_pl = None if is_hist[idx] else sf("other_adj", period)

        # EBIT is pre-SBC: Adj EBITDA - D&A - Other Amort.
        ebit_pre_sbc = None
        if adj_ebitda is not None:
            ebit_pre_sbc = adj_ebitda - (dep or 0.0) - (amort or 0.0)

        # FCFE swaps the EBIT row for EBT (adds signed net interest).
        ebit_row = ebit_pre_sbc
        if is_fcfe and ebit_pre_sbc is not None:
            ebit_row = ebit_pre_sbc + (net_int or 0.0)

        # DCF is presented on an Adjusted EBITDA basis. SBC is shown
        # separately below and deducted before calculating Taxes/NOPAT.
        # Keeping Adjusted EBITDA here also matches MarketScreener
        # projections and the forward GPC multiple basis.
        opex = _sub(gp, adj_ebitda)

        if is_hist[idx]:
            taxes = sf("taxes", period)
            other_adj = sf("acquisitions", period)
        else:
            # FCFE tax base includes the P&L plug so EBT − SBC + OA − Tax = NI.
            # FCFF NOPAT stays unlevered: (EBIT − SBC) × (1 − t), plug excluded.
            base_for_tax = _sub(ebit_row, sbc or 0.0)
            if is_fcfe and base_for_tax is not None:
                base_for_tax = base_for_tax + (other_adj_pl or 0.0)
            taxes = None
            if base_for_tax is not None and tax_rate is not None:
                taxes = base_for_tax * tax_rate
            other_adj = parse_number(other_adj_inputs.get(period))
            if other_adj is None:
                other_adj = 0.0

        if is_fcfe:
            if is_hist[idx]:
                nopat = sf("net_income", period)
            else:
                nopat = _sub(base_for_tax, taxes)
                if nopat is None:
                    nopat = sf("net_income", period)
        else:
            fcff_base = _sub(ebit_row, sbc or 0.0)
            nopat = _sub(fcff_base, taxes)

        plus_dep = _add_present(dep, amort)
        nwc_change = changes_in_nwc.get(period)

        fcf = None
        if None not in (nopat, plus_dep, nwc_change, capex):
            fcf = nopat + plus_dep - nwc_change - capex - (other_adj or 0.0)

        rows["revenue"][period] = rev
        rows["cogs"][period] = _sub(rev, gp)
        rows["gross_profit"][period] = gp
        rows["gp_margin"][period] = safe_div(gp, rev)
        rows["operating_expenses"][period] = opex
        rows["ebitda"][period] = adj_ebitda
        rows["ebitda_margin"][period] = safe_div(adj_ebitda, rev)
        rows["depreciation"][period] = dep
        rows["amortization"][period] = amort
        rows["net_interest"][period] = net_int
        rows["ebit"][period] = ebit_row
        rows["ebit_margin"][period] = safe_div(ebit_row, rev)
        rows["sbc"][period] = sbc
        rows["other_adj"][period] = other_adj_pl
        rows["taxes"][period] = taxes
        rows["nopat"][period] = nopat
        rows["plus_dep"][period] = plus_dep
        rows["less_nwc"][period] = nwc_change
        rows["less_capex"][period] = capex
        rows["less_other_adj"][period] = other_adj
        rows["fcf"][period] = fcf

    # ---------------- revenue growth --------------------------------------
    for idx, period in enumerate(headers):
        if period == "Residual" or idx == 0:
            continue
        curr = rows["revenue"][period]
        prior = rows["revenue"][headers[idx - 1]]
        if curr is not None and prior:
            rows["revenue_growth"][period] = curr / prior - 1.0

    # ---------------- PV chain --------------------------------------------
    prior_pvp: Optional[float] = None
    sum_pv_fcf = 0.0
    any_pv = False

    for idx, period in enumerate(headers):
        if is_hist[idx] or period == "Residual":
            continue

        if period == "NFY":
            rows["ppa"][period] = ppa
            pvp = (ppa / 2.0) if ppa is not None else None
        elif period == "NFY+1":
            pvp = (prior_pvp * 2.0 + 0.5) if prior_pvp is not None else None
        else:
            pvp = (prior_pvp + 1.0) if prior_pvp is not None else None

        rows["pvp"][period] = pvp
        prior_pvp = pvp

        pvf = None
        if pvp is not None and discount_rate is not None and discount_rate > 0:
            pvf = 1.0 / ((1.0 + discount_rate) ** pvp)
        rows["pvf"][period] = pvf

        fcf = rows["fcf"][period]
        if fcf is not None and pvf is not None:
            pv = fcf * ppa * pvf if (period == "NFY" and ppa is not None) else fcf * pvf
            rows["pv_fcf"][period] = pv
            sum_pv_fcf += pv
            any_pv = True

    sum_pv_fcf = sum_pv_fcf if any_pv else None

    # ---------------- residual column -------------------------------------
    final_period = projection_period_columns[-1] if projection_period_columns else None
    final = {k: (rows[k][final_period] if final_period else None) for k, *_ in ROW_SPECS}

    g = (1.0 + ltgr) if ltgr is not None else None

    def grow(v: Optional[float]) -> Optional[float]:
        return v * g if (v is not None and g is not None) else None

    res_rev = residual_revenue(final["revenue"], ltgr)
    res_cogs = grow(final["cogs"])
    res_opex = grow(final["operating_expenses"])
    res_gp = _sub(res_rev, res_cogs)
    res_adj_ebitda = _sub(res_gp, res_opex)      # OpEx was built off Adj EBITDA
    res_sbc = grow(final["sbc"])

    capex_ratio = safe_div(final["less_capex"], final["revenue"])
    res_capex = res_rev * capex_ratio if (res_rev is not None and capex_ratio is not None) else None
    res_dep = res_capex * dep_pct_of_capex if (res_capex is not None and dep_pct_of_capex is not None) else None
    res_amort = parse_number(residual_amortization)

    res_net_int = grow(final["net_interest"]) if is_fcfe else None

    res_ebit_pre_sbc = None
    if res_adj_ebitda is not None and res_dep is not None:
        res_ebit_pre_sbc = res_adj_ebitda - res_dep - (res_amort or 0.0)

    res_ebit_row = res_ebit_pre_sbc
    if is_fcfe:
        res_ebit_row = (
            res_ebit_pre_sbc + res_net_int
            if (res_ebit_pre_sbc is not None and res_net_int is not None) else None
        )

    res_base_for_tax = _sub(res_ebit_row, res_sbc or 0.0)
    res_taxes = None
    if res_base_for_tax is not None and tax_rate is not None:
        res_taxes = res_base_for_tax * tax_rate

    if is_fcfe:
        res_nopat = grow(final["nopat"])
    else:
        res_nopat = _sub(res_base_for_tax, res_taxes)

    res_plus_dep = _add_present(res_dep, res_amort)
    res_nwc = changes_in_nwc.get("Residual")
    res_other_adj = parse_number(other_adj_inputs.get("Residual"))
    if res_other_adj is None:
        res_other_adj = 0.0

    res_fcf = None
    if res_nopat is not None and res_nwc is not None:
        res_fcf = (
            res_nopat + (res_plus_dep or 0.0) - res_nwc
            - (res_capex or 0.0) - res_other_adj
        )

    rows["revenue"]["Residual"] = res_rev
    rows["cogs"]["Residual"] = res_cogs
    rows["gross_profit"]["Residual"] = res_gp
    rows["gp_margin"]["Residual"] = safe_div(res_gp, res_rev)
    rows["operating_expenses"]["Residual"] = res_opex
    rows["ebitda"]["Residual"] = res_adj_ebitda
    rows["ebitda_margin"]["Residual"] = safe_div(res_adj_ebitda, res_rev)
    rows["depreciation"]["Residual"] = res_dep
    rows["amortization"]["Residual"] = res_amort
    rows["net_interest"]["Residual"] = res_net_int
    rows["ebit"]["Residual"] = res_ebit_row
    rows["ebit_margin"]["Residual"] = safe_div(res_ebit_row, res_rev)
    rows["sbc"]["Residual"] = res_sbc
    rows["taxes"]["Residual"] = res_taxes
    rows["nopat"]["Residual"] = res_nopat
    rows["plus_dep"]["Residual"] = res_plus_dep
    rows["less_nwc"]["Residual"] = res_nwc
    rows["less_capex"]["Residual"] = res_capex
    rows["less_other_adj"]["Residual"] = res_other_adj
    rows["fcf"]["Residual"] = res_fcf

    # ---------------- terminal value --------------------------------------
    final_pvp = rows["pvp"][final_period] if final_period else None
    tv = _terminal_values(
        discount_rate=discount_rate,
        ltgr=ltgr,
        residual_fcf=res_fcf,
        final_fcf=final["fcf"],
        final_ebitda=rows["ebitda"][final_period] if final_period else None,
        final_revenue=final["revenue"],
        final_pvp=final_pvp,
        tv_inputs=tv_inputs,
    )

    pv_residual = tv.get(tv_model, {}).get("pv_residual")

    other_adj_bridge = parse_number(bridge_other_adj) or 0.0
    fv_base = None
    if sum_pv_fcf is not None or pv_residual is not None:
        fv_base = (sum_pv_fcf or 0.0) + (pv_residual or 0.0) + other_adj_bridge

    return {
        "headers": headers,
        "is_hist": is_hist,
        "num_hist": num_hist,
        "num_proj": num_proj,
        "rows": rows,
        "final_period": final_period,
        "final_pvp": final_pvp,
        "ppa": ppa,
        "discount_rate": discount_rate,
        "ltgr": ltgr,
        "sum_pv_fcf": sum_pv_fcf,
        "tv": tv,
        "pv_residual": pv_residual,
        "other_adj_bridge": other_adj_bridge,
        "fv_base": fv_base,
        "is_fcfe": is_fcfe,
    }


def _terminal_values(
    discount_rate: Optional[float],
    ltgr: Optional[float],
    residual_fcf: Optional[float],
    final_fcf: Optional[float],
    final_ebitda: Optional[float],
    final_revenue: Optional[float],
    final_pvp: Optional[float],
    tv_inputs: Dict[str, Dict[str, Any]],
) -> Dict[str, Dict[str, Optional[float]]]:
    """All four TV models. Each returns its own panel outputs."""
    cap_rate = None
    if discount_rate is not None and ltgr is not None:
        cap_rate = discount_rate - ltgr

    pv_factor = None
    if final_pvp is not None and discount_rate is not None:
        pv_factor = 1.0 / ((1.0 + discount_rate) ** final_pvp)

    pv_factor_mult = None
    if final_pvp is not None and discount_rate is not None:
        pv_factor_mult = 1.0 / ((1.0 + discount_rate) ** (final_pvp + 0.5))

    out: Dict[str, Dict[str, Optional[float]]] = {}

    # Gordon Growth
    gg_rv = None
    if residual_fcf is not None and cap_rate not in (None, 0):
        gg_rv = residual_fcf / cap_rate
    out["Gordon Growth"] = {
        "cash_flow": residual_fcf,
        "cap_rate": cap_rate,
        "residual_value": gg_rv,
        "pv_factor": pv_factor,
        "pv_residual": gg_rv * pv_factor if (gg_rv is not None and pv_factor is not None) else None,
    }

    # EBITDA Multiple
    ebitda_mult = parse_multiple((tv_inputs.get("EBITDA Multiple") or {}).get("multiple"))
    ebitda_rv = (
        final_ebitda * ebitda_mult
        if (final_ebitda is not None and ebitda_mult is not None) else None
    )
    out["EBITDA Multiple"] = {
        "metric": final_ebitda,
        "multiple": ebitda_mult,
        "residual_value": ebitda_rv,
        "pv_factor": pv_factor_mult,
        "pv_residual": (
            ebitda_rv * pv_factor_mult
            if (ebitda_rv is not None and pv_factor_mult is not None) else None
        ),
    }

    # Revenue Multiple
    rev_mult = parse_multiple((tv_inputs.get("Revenue Multiple") or {}).get("multiple"))
    rev_rv = (
        final_revenue * rev_mult
        if (final_revenue is not None and rev_mult is not None) else None
    )
    out["Revenue Multiple"] = {
        "metric": final_revenue,
        "multiple": rev_mult,
        "residual_value": rev_rv,
        "pv_factor": pv_factor_mult,
        "pv_residual": (
            rev_rv * pv_factor_mult
            if (rev_rv is not None and pv_factor_mult is not None) else None
        ),
    }

    # H-Model
    h_cfg = tv_inputs.get("H-Model") or {}
    num_years = parse_number(h_cfg.get("num_years"))
    short_growth = parse_pct(h_cfg.get("short_term_growth"))
    h_rv = None
    if (
        final_fcf is not None and num_years is not None
        and short_growth is not None and ltgr is not None
        and cap_rate not in (None, 0)
    ):
        h_rv = (
            ((final_fcf * num_years) / 2.0) * (short_growth - ltgr) / cap_rate
        ) + (gg_rv if gg_rv is not None else 0.0)
    out["H-Model"] = {
        "cash_flow": final_fcf,
        "cap_rate": cap_rate,
        "residual_value": h_rv,
        "pv_factor": pv_factor,
        "pv_residual": h_rv * pv_factor if (h_rv is not None and pv_factor is not None) else None,
    }

    return out


# ---------------------------------------------------------------------------
# Sensitivity
# ---------------------------------------------------------------------------

def fv_for_assumptions(
    wacc: Optional[float],
    ltgr: Optional[float],
    base: Dict[str, Any],
) -> Optional[float]:
    """Fair value at an overridden rate / growth pair.

    Re-discounts EVERY explicit-period FCF at `wacc` (the desktop holds
    that sum fixed and only re-discounts the terminal value, which is why
    its heatmap is lopsided). Residual FCF is the real pipeline figure,
    proportionally rescaled from the base LTGR to the override.
    """
    if wacc is None or wacc <= 0 or ltgr is None:
        return None

    rows = base["rows"]
    headers = base["headers"]
    is_hist = base["is_hist"]
    ppa = base["ppa"]

    # 1. Re-discount the explicit period.
    sum_pv = 0.0
    any_pv = False
    for idx, period in enumerate(headers):
        if is_hist[idx] or period == "Residual":
            continue
        fcf = rows["fcf"][period]
        pvp = rows["pvp"][period]
        if fcf is None or pvp is None:
            continue
        pvf = 1.0 / ((1.0 + wacc) ** pvp)
        sum_pv += fcf * ppa * pvf if (period == "NFY" and ppa is not None) else fcf * pvf
        any_pv = True
    sum_pv_fcf = sum_pv if any_pv else None

    # 2. Rescale residual FCF from base LTGR to the override.
    residual_fcf = rows["fcf"]["Residual"]
    base_ltgr = base["ltgr"]
    if residual_fcf is not None and base_ltgr is not None and (1.0 + base_ltgr) != 0:
        residual_fcf = residual_fcf * (1.0 + ltgr) / (1.0 + base_ltgr)

    tv = _terminal_values(
        discount_rate=wacc,
        ltgr=ltgr,
        residual_fcf=residual_fcf,
        final_fcf=rows["fcf"][base["final_period"]] if base["final_period"] else None,
        final_ebitda=rows["ebitda"][base["final_period"]] if base["final_period"] else None,
        final_revenue=rows["revenue"][base["final_period"]] if base["final_period"] else None,
        final_pvp=base["final_pvp"],
        tv_inputs=base["tv_inputs"],
    )
    pv_residual = tv.get(base["tv_model"], {}).get("pv_residual")

    if sum_pv_fcf is None and pv_residual is None:
        return None
    return (sum_pv_fcf or 0.0) + (pv_residual or 0.0) + base["other_adj_bridge"]


SENS_OFFSETS = [0.02, 0.01, 0.0, -0.01, -0.02]
SENS_HIGH_COORD = (1, 3)
SENS_LOW_COORD = (3, 1)
SENS_CENTER_COORD = (2, 2)


def sensitivity_grid(
    wacc_values: List[Optional[float]],
    ltgr_values: List[Optional[float]],
    base: Dict[str, Any],
) -> Dict[str, Any]:
    """5x5 grid. rows = LTGR, cols = discount rate."""
    grid: Dict[Tuple[int, int], Optional[float]] = {}
    valid: List[float] = []

    for r, ltgr in enumerate(ltgr_values):
        for c, wacc in enumerate(wacc_values):
            fv = fv_for_assumptions(wacc, ltgr, base)
            grid[(r, c)] = fv
            if fv is not None and fv > 0:
                valid.append(fv)

    return {
        "grid": grid,
        "min_fv": min(valid) if valid else 0.0,
        "max_fv": max(valid) if valid else 0.0,
        "high": grid.get(SENS_HIGH_COORD),
        "low": grid.get(SENS_LOW_COORD),
        "center": grid.get(SENS_CENTER_COORD),
    }