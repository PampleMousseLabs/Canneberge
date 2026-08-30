"""
valuation_surface.py
Canneberge — Valuation Surface Data Engine.

Computes a 2D grid of Fair Values across WACC and LTGR coordinates
for both Gordon Growth and H-Model terminal value approaches.
Pure data layer — no Qt, no matplotlib, no UI state.
"""

from typing import Optional, List, Dict, Callable, Any
import math


def evaluate_dcf_fv(
    wacc: float,
    ltgr: float,
    sum_pv_explicit_fcf: Optional[float],
    final_pvp: Optional[float],
    final_fcf: Optional[float],
    final_revenue: Optional[float],
    final_capex: Optional[float],
    dep_pct_of_capex: Optional[float],
    tax_rate: Optional[float],
    dfcfnwc_residual: Optional[float],
    other_adj_residual: float,
    other_adj_bridge: float,
    is_fcfe: bool,
    final_net_interest: Optional[float],
    model: str = "Gordon Growth",
    h_num_years: Optional[float] = 5.0,
    h_short_growth: Optional[float] = 0.20,
    ebitda_mult: Optional[float] = None,
    revenue_mult: Optional[float] = None,
) -> Optional[float]:
    """
    Pure mathematical DCF evaluator. Runs in microseconds with zero UI mutation.
    """
    if wacc is None or wacc <= 0 or ltgr is None:
        return None

    cap_rate = wacc - ltgr
    if cap_rate <= 0:
        return None

    # 1. Compute Residual Year FCF
    growth_factor = 1.0 + ltgr
    residual_fcf = None

    if final_revenue is not None and final_fcf is not None and final_revenue > 0:
        capex_ratio = (final_capex / final_revenue) if final_capex is not None else 0.0
        res_revenue = final_revenue * growth_factor
        res_capex = res_revenue * capex_ratio
        res_dep = res_capex * (dep_pct_of_capex or 1.0)

        if is_fcfe and final_net_interest is not None:
            res_nopat = (final_fcf + (final_capex or 0.0) - res_dep) * growth_factor
            residual_fcf = res_nopat + res_dep - res_capex - (dfcfnwc_residual or 0.0) - other_adj_residual
        else:
            residual_fcf = final_fcf * growth_factor

    # 2. Residual Value & Discounting
    pv_factor = (1.0 / ((1.0 + wacc) ** final_pvp)) if (final_pvp is not None) else None
    if pv_factor is None:
        return None

    pv_residual_value = None

    if model == "H-Model":
        if (final_fcf is not None and h_num_years is not None and h_short_growth is not None):
            gg_res = (residual_fcf / cap_rate) if residual_fcf is not None else 0.0
            h_res = (((final_fcf * h_num_years) / 2.0) * (h_short_growth - ltgr) / cap_rate) + gg_res
            pv_residual_value = h_res * pv_factor
    elif model == "EBITDA Multiple" and ebitda_mult is not None:
        pv_factor_m = 1.0 / ((1.0 + wacc) ** (final_pvp + 0.5))
        pv_residual_value = (final_fcf * ebitda_mult) * pv_factor_m
    elif model == "Revenue Multiple" and revenue_mult is not None:
        pv_factor_m = 1.0 / ((1.0 + wacc) ** (final_pvp + 0.5))
        pv_residual_value = (final_revenue * revenue_mult) * pv_factor_m
    else:
        # Gordon Growth (Default)
        if residual_fcf is not None:
            residual_value = residual_fcf / cap_rate
            pv_residual_value = residual_value * pv_factor

    if sum_pv_explicit_fcf is None and pv_residual_value is None:
        return None

    return (sum_pv_explicit_fcf or 0.0) + (pv_residual_value or 0.0) + other_adj_bridge


def _compute_surface_grid(
    fv_func: Callable[[float, float], Optional[float]],
    wacc_values: List[float],
    ltgr_values: List[float],
    model_name: str = "Gordon Growth",
) -> Dict[str, Any]:
    """
    Core grid computation shared by surface functions.
    """
    grid_size_w = len(wacc_values)
    grid_size_l = len(ltgr_values)
    center_w    = grid_size_w // 2
    center_l    = grid_size_l // 2

    fv_grid: List[List[Optional[float]]] = []
    high_point  = {"wacc": None, "ltgr": None, "fv": None, "i": None, "j": None}
    low_point   = {"wacc": None, "ltgr": None, "fv": None, "i": None, "j": None}
    valid_count = 0
    center_fv   = None

    for i, wacc in enumerate(wacc_values):
        row: List[Optional[float]] = []
        for j, ltgr in enumerate(ltgr_values):
            if wacc <= ltgr:
                row.append(None)
                continue
            try:
                fv = fv_func(wacc, ltgr)
            except Exception:
                fv = None

            if fv is not None and not math.isnan(fv) and not math.isinf(fv):
                valid_count += 1
                if high_point["fv"] is None or fv > high_point["fv"]:
                    high_point = {"wacc": wacc, "ltgr": ltgr, "fv": fv, "i": i, "j": j}
                if low_point["fv"] is None or fv < low_point["fv"]:
                    low_point  = {"wacc": wacc, "ltgr": ltgr, "fv": fv, "i": i, "j": j}
                if i == center_w and j == center_l:
                    center_fv = fv
            else:
                fv = None

            row.append(fv)
        fv_grid.append(row)

    def _pt(i, j):
        w = wacc_values[i]
        l = ltgr_values[j]
        v = None
        if i < len(fv_grid) and j < len(fv_grid[i]):
            v = fv_grid[i][j]
        return {"wacc": w, "ltgr": l, "fv": v, "i": i, "j": j}

    conclusion_high = _pt(1, -2)
    conclusion_low  = _pt(-2, 1)

    return {
        "wacc_values":      wacc_values,
        "ltgr_values":      ltgr_values,
        "fv_grid":          fv_grid,
        "high_point":       high_point,
        "low_point":        low_point,
        "conclusion_high":  conclusion_high,
        "conclusion_low":   conclusion_low,
        "center_fv":        center_fv,
        "valid_count":      valid_count,
        "grid_size":        max(grid_size_w, grid_size_l),
        "model_name":       model_name,
    }


def compute_gg_surface_data(
    fv_func: Callable[[float, float], Optional[float]],
    wacc_center: float,
    ltgr_center: float,
    grid_size: int = 10,
    wacc_step: float = 0.005,
    ltgr_step: float = 0.005,
    model_name: str = "Gordon Growth",
) -> Dict[str, Any]:
    """
    Parametric version — generates grid from center + step size.
    """
    half = grid_size // 2
    wacc_values = [round(wacc_center + (i - half) * wacc_step, 6)
                   for i in range(grid_size)]
    ltgr_values = [round(ltgr_center + (j - half) * ltgr_step, 6)
                   for j in range(grid_size)]
    return _compute_surface_grid(fv_func, wacc_values, ltgr_values, model_name=model_name)


def compute_gg_surface_data_from_explicit(
    fv_func: Callable[[float, float], Optional[float]],
    wacc_values: List[float],
    ltgr_values: List[float],
    model_name: str = "Gordon Growth",
) -> Dict[str, Any]:
    """
    Explicit version — uses exact WACC and LTGR lists from sensitivity table.
    """
    wacc_sorted = sorted(wacc_values)
    ltgr_sorted = sorted(ltgr_values)
    return _compute_surface_grid(fv_func, wacc_sorted, ltgr_sorted, model_name=model_name)