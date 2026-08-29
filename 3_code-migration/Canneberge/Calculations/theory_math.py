"""
theory_math.py
Pure mathematical calculations for academic valuation dynamics.
Isolated from UI for testability and portability.
"""

def compute_theory_diagnostics(
    bev_fcff: float,
    equity_fcfe: float,
    equity_fcff: float,
    book_debt: float,
    cash: float,
    market_cap: float,
    wacc: float,
    ke: float,
    kd_after_tax: float,
    wd_book: float,
    tax_rate: float,
    avg_fcff: float,
    avg_interest: float,
    rc: float = 0.045,  # Default cash yield (4.5%)
    fv_debt_override: float = None
) -> dict:
    
    net_debt = max(0.0, book_debt - cash)
    avg_equity = (equity_fcfe + equity_fcff) / 2.0 if (equity_fcfe and equity_fcff) else 1.0
    
    # Ratios
    lam = net_debt / bev_fcff if bev_fcff else 0.0
    residual = equity_fcff - equity_fcfe
    pct_residual = residual / avg_equity if avg_equity else 0.0
    
    # Market Wd
    market_tic = book_debt + market_cap
    wd_market = book_debt / market_tic if market_tic else 0.0
    
    # MM Consistency (S vs Expected)
    # WACC = Ke*We + Kd*Wd  =>  Ke - WACC = Wd * (Ke - Kd)
    s_actual = (ke - wacc) / wd_book if wd_book > 0 else 0.0
    s_expected = ke - kd_after_tax
    mm_spread_gap = abs(s_actual - s_expected)
    
    # Friction terms
    theta = avg_interest / avg_fcff if avg_fcff else 0.0
    gamma = (cash / avg_equity) * (ke - rc) if avg_equity else 0.0
    
    fv_debt = fv_debt_override if fv_debt_override else book_debt
    mu = book_debt / fv_debt if fv_debt else 1.0
    
    # Composite Alarm (Psi)
    psi = lam * (1 + abs(mu - 1) + theta + gamma)
    
    return {
        "net_debt": net_debt,
        "wd_market": wd_market,
        "lam": lam,
        "residual": residual,
        "pct_residual": pct_residual,
        "s_actual": s_actual,
        "s_expected": s_expected,
        "mm_spread_gap": mm_spread_gap,
        "theta": theta,
        "gamma": gamma,
        "mu": mu,
        "psi": psi,
    }

def generate_mm_curve_data(ke_current: float, kd_after_tax: float, wd_current: float):
    """
    Reverse-engineers the Unlevered Cost of Equity (Ku) from current inputs,
    then generates the curve of Ke and WACC across 0% to 90% debt loads.
    """
    # Ku = Ke - (Ke - Kd)(Wd/We) -> implies Ku is the unlevered base.
    we_current = 1.0 - wd_current
    if we_current <= 0:
        we_current = 0.001
        
    ku = (ke_current * we_current) + (kd_after_tax * wd_current)
    
    x_wd = []
    y_ke = []
    y_wacc = []
    y_kd = []
    
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
        
    return {
        "ku": ku,
        "x_wd": x_wd,
        "y_ke": y_ke,
        "y_wacc": y_wacc,
        "y_kd": y_kd
    }