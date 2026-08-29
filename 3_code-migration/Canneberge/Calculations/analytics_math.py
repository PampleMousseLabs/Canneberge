"""
analytics_math.py
Pure math for the Capital Structure Analytics page. Zero PyQt
dependencies — every function here takes raw floats/dicts and
returns raw floats/dicts, so this is CLI-testable (see
debug_analytics.py) and portable to a future web/tablet client.

Framework status: EXPLORATORY. Ratio definitions (lambda, theta,
gamma, mu, wd_gap, psi) were derived analytically, not yet validated
against an empirical cross-section. If these definitions change,
anything downstream (analytics_page.py, debug_analytics.py, any
saved empirical baseline CSV) needs to be regenerated to match.
"""

from typing import Optional, List, Dict


def _safe_div(a: Optional[float], b: Optional[float]) -> Optional[float]:
    if a is None or b is None or b == 0:
        return None
    return a / b


def compute_analytics_ratios(
    bev_fcff: Optional[float],
    equity_fcfe: Optional[float],
    equity_fcff: Optional[float],
    book_debt: Optional[float],
    cash: Optional[float],
    market_cap: Optional[float],
    wacc: Optional[float],
    ke: Optional[float],
    kd_after_tax: Optional[float],
    wd_book: Optional[float],
    tax_rate: Optional[float],
    avg_fcff: Optional[float],
    avg_interest: Optional[float],
    rc: float = 0.045,
    fv_debt_override: Optional[float] = None,
    k_mu: float = 1.0,
    k_theta: float = 1.0,
    k_gamma: float = 1.0,
    k_wdgap: float = 1.0,
) -> Dict[str, Optional[float]]:
    """
    Single-snapshot ratio pack comparing FCFF-bridge vs FCFE equity
    conclusions and the financing frictions that could explain any gap.

    fv_debt_override: if None, mu (BV/FV debt) defaults to 1.0 by
    treating Book Debt as its own Fair Value proxy. This is a
    deliberate placeholder — a real Fair Value of Debt calc (mark-to-
    market off the debt schedule's coupons vs a current yield curve)
    is being deferred to a dedicated Debt & Derivatives build. Until
    then, mu == 1.0 by construction, not by an actual finding of "no
    mark divergence."
    """
    net_debt = None
    if book_debt is not None and cash is not None:
        net_debt = book_debt - cash

    avg_equity = None
    if equity_fcfe is not None and equity_fcff is not None:
        avg_equity = (equity_fcfe + equity_fcff) / 2.0

    lam = _safe_div(net_debt, bev_fcff)

    residual = None
    if equity_fcff is not None and equity_fcfe is not None:
        residual = equity_fcff - equity_fcfe
    pct_residual = _safe_div(residual, avg_equity)

    market_tic = None
    if book_debt is not None and market_cap is not None:
        market_tic = book_debt + market_cap
    wd_market = _safe_div(book_debt, market_tic)

    wd_gap = None
    if wd_book is not None and wd_market is not None:
        wd_gap = abs(wd_book - wd_market)

    s_actual = None
    if ke is not None and wacc is not None and wd_book:
        s_actual = (ke - wacc) / wd_book
    s_expected = None
    if ke is not None and kd_after_tax is not None:
        s_expected = ke - kd_after_tax
    mm_gap = None
    if s_actual is not None and s_expected is not None:
        mm_gap = abs(s_actual - s_expected)

    theta = _safe_div(avg_interest, avg_fcff)

    gamma = None
    if avg_equity and ke is not None and cash is not None:
        gamma = (cash / avg_equity) * (ke - rc)

    fv_debt = fv_debt_override if fv_debt_override else book_debt
    mu = _safe_div(book_debt, fv_debt)
    if mu is None:
        mu = 1.0

    psi = None
    if lam is not None:
        psi = abs(lam) * (
            1
            + k_mu * abs(mu - 1)
            + k_theta * abs(theta or 0.0)
            + k_gamma * abs(gamma or 0.0)
            + k_wdgap * abs(wd_gap or 0.0)
        )

    return {
        "net_debt": net_debt,
        "avg_equity": avg_equity,
        "lam": lam,
        "residual": residual,
        "pct_residual": pct_residual,
        "wd_book": wd_book,
        "wd_market": wd_market,
        "wd_gap": wd_gap,
        "s_actual": s_actual,
        "s_expected": s_expected,
        "mm_gap": mm_gap,
        "theta": theta,
        "gamma": gamma,
        "mu": mu,
        "psi": psi,
    }


def interpret_regime(ratios: Dict[str, Optional[float]]) -> Dict:
    """Rule-based classifier. Thresholds are first-pass guesses —
    intended to be recalibrated once an empirical baseline exists."""
    lam = ratios.get("lam")
    mm_gap = ratios.get("mm_gap")
    wd_gap = ratios.get("wd_gap")
    theta = ratios.get("theta")
    mu = ratios.get("mu")
    pct_residual = ratios.get("pct_residual")

    if lam is None:
        return {
            "regime": "Insufficient Data",
            "alerts": [],
            "notes": "Not enough inputs computed yet — check that "
                     "'Compute Both Methods' has been run and WACC/"
                     "Subject Financials pages have data.",
        }

    if abs(lam) < 0.10:
        regime = "Low Leverage / Dilution Regime"
    elif abs(lam) < 0.40:
        regime = "Moderate Leverage / Balanced Regime"
    else:
        regime = "High Leverage / Structural Sensitivity Regime"

    alerts: List[str] = []
    if mm_gap is not None and mm_gap > 0.03:
        alerts.append(
            f"MM Spread Gap of {mm_gap*100:.2f}% — actual (Ke−WACC)/Wd "
            "diverges from Ke−Kd(1−T). Capital structure inputs may be "
            "internally inconsistent."
        )
    if wd_gap is not None and wd_gap > 0.15:
        alerts.append(
            f"Book Wd vs Market Wd differ by {wd_gap*100:.1f} pts — "
            "book leverage may be overstating/understating true "
            "market risk used in beta re-levering."
        )
    if theta is not None and theta > 0.20:
        alerts.append(
            f"Debt Service Intensity (θ) at {theta*100:.1f}% of FCFF — "
            "interest expense is a material share of operating cash "
            "flow; static WACC vs explicit schedule timing may matter."
        )
    if mu is not None and abs(mu - 1) > 0.10:
        alerts.append(
            f"Debt Mark Ratio (μ) at {mu:.2f} — Book vs Fair Value of "
            "debt diverge; consider a market-value debt bridge."
        )
    if pct_residual is not None and abs(pct_residual) > 0.03:
        alerts.append(
            f"Method residual is {pct_residual*100:.2f}% of equity value — "
            "above typical institutional tolerance (~1-3%); verify Debt "
            "Schedule / discount rate wiring."
        )

    if alerts:
        notes = f"{regime}. " + " ".join(alerts)
    else:
        notes = (
            f"{regime}. No material alerts triggered — FCFF and FCFE "
            "conclusions are internally consistent given current inputs."
        )

    return {"regime": regime, "alerts": alerts, "notes": notes}


def shock_leverage(
    base_inputs: Dict[str, Optional[float]],
    lam_range: Optional[List[float]] = None,
) -> Dict[str, List[float]]:
    """
    Sweeps net-leverage (lambda = Net Debt / BEV) across lam_range and
    approximates how both equity-value methods would respond.

    APPROXIMATION, not a full DCF re-run: at each shocked lambda, this
    re-derives Ke/WACC via MM Proposition II using current WACC as an
    unlevered-cost-of-capital proxy (Ku), then re-discounts the CURRENT
    BEV and CURRENT FCFE equity value using a simple perpetuity-style
    scaling (V_new = V_current * discount_rate_current / discount_rate_new).
    This isolates the discount-rate effect of a leverage shock without
    needing a full multi-year FCFF/FCFE re-projection. Treat the shape
    as directionally informative, not a precise re-valuation.
    """
    if lam_range is None:
        lam_range = [i / 1000 for i in range(0, 601, 25)]  # 0%-60%, 2.5% steps

    bev = base_inputs.get("bev_fcff")
    equity_fcfe_base = base_inputs.get("equity_fcfe")
    cash = base_inputs.get("cash") or 0.0
    market_cap = base_inputs.get("market_cap")
    wacc_current = base_inputs.get("wacc")
    ke_current = base_inputs.get("ke")
    kd_after_tax = base_inputs.get("kd_after_tax")

    x_lam: List[float] = []
    y_equity_fcff: List[float] = []
    y_equity_fcfe: List[float] = []
    y_pct_residual: List[Optional[float]] = []

    if None in (bev, equity_fcfe_base, wacc_current, ke_current, kd_after_tax):
        return {
            "x_lam": [], "y_equity_fcff": [], "y_equity_fcfe": [],
            "y_pct_residual": [],
        }

    ku_proxy = wacc_current  # APPROXIMATION — see docstring.

    for lam in lam_range:
        shocked_net_debt = lam * bev
        shocked_debt = shocked_net_debt + cash
        equity_proxy = market_cap if market_cap else max(bev - shocked_debt, 1.0)
        denom = shocked_debt + equity_proxy
        if denom <= 0:
            continue
        shocked_wd = shocked_debt / denom
        if shocked_wd >= 1.0:
            continue
        we = 1.0 - shocked_wd

        ke_shocked = ku_proxy + (ku_proxy - kd_after_tax) * (shocked_wd / we)
        wacc_shocked = ke_shocked * we + kd_after_tax * shocked_wd
        if wacc_shocked <= 0 or ke_shocked <= 0:
            continue

        bev_shocked = bev * (wacc_current / wacc_shocked)
        equity_fcff_shocked = bev_shocked - shocked_debt + cash
        equity_fcfe_shocked = equity_fcfe_base * (ke_current / ke_shocked)

        avg_eq = (equity_fcff_shocked + equity_fcfe_shocked) / 2.0
        pct_res = (
            abs(equity_fcff_shocked - equity_fcfe_shocked) / avg_eq
            if avg_eq else None
        )

        x_lam.append(lam)
        y_equity_fcff.append(equity_fcff_shocked)
        y_equity_fcfe.append(equity_fcfe_shocked)
        y_pct_residual.append(pct_res)

    return {
        "x_lam": x_lam,
        "y_equity_fcff": y_equity_fcff,
        "y_equity_fcfe": y_equity_fcfe,
        "y_pct_residual": y_pct_residual,
    }


def generate_mm_curve_data(ke_current: float, kd_after_tax: float, wd_current: float) -> Dict:
    """
    DEMOTED — kept for optional/illustrative viewing only (Advanced
    panel). This is textbook MM Proposition II on cost of capital
    (Ke rises with leverage) — it does NOT plot firm value, and it is
    NOT derived from this model's actual FCFF/FCFE outputs beyond
    using current (Ke, Kd, Wd) as a single anchor point. Not the hero
    diagnostic — see shock_leverage() for the model-driven chart.
    """
    we_current = 1.0 - wd_current if wd_current is not None else 1.0
    if we_current <= 0:
        we_current = 0.001
    if wd_current is None:
        wd_current = 0.0

    ku = (ke_current * we_current) + (kd_after_tax * wd_current)

    x_wd, y_ke, y_wacc, y_kd = [], [], [], []
    for i in range(0, 95, 5):
        wd = i / 100.0
        we = 1.0 - wd
        if we <= 0:
            continue
        ke_sim = ku + (ku - kd_after_tax) * (wd / we)
        wacc_sim = (ke_sim * we) + (kd_after_tax * wd)
        x_wd.append(wd)
        y_ke.append(ke_sim)
        y_wacc.append(wacc_sim)
        y_kd.append(kd_after_tax)

    return {"ku": ku, "x_wd": x_wd, "y_ke": y_ke, "y_wacc": y_wacc, "y_kd": y_kd}


def load_empirical_baseline(csv_path: Optional[str] = None) -> Optional[Dict]:
    """
    SAVE FOR LATER: Loads a precomputed empirical dataset of these
    same ratios (lambda, theta, gamma, mu, wd_gap, mm_gap, psi,
    pct_residual) across a large ticker universe (e.g., S&P 500),
    intended to overlay percentile bands on analytics_page.py's hero
    chart ("your lambda sits at the 87th percentile" etc.).

    NOT YET POPULATED. Ratio definitions above are still exploratory
    and may change — regenerate any saved CSV if they do. Batch
    collection would loop this module's compute_analytics_ratios()
    across many tickers (see debug_analytics.py for the single-ticker
    CLI harness this would extend).

    Returns None if csv_path is None or doesn't exist. Return shape
    (dict of {ratio_name: sorted_list_of_values} vs a DataFrame) is
    still TBD pending how the percentile overlay gets implemented.
    """
    import os
    if not csv_path or not os.path.exists(csv_path):
        return None
    # TODO: implement once ratio framework is validated and a batch
    # script has generated a real dataset across a ticker universe.
    return None