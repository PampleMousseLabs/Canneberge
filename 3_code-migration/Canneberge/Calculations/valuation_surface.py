"""
valuation_surface.py
Canneberge — Valuation Surface Data Engine.

Computes a 2D grid of Fair Values across WACC and LTGR coordinates
for the Gordon Growth model surface chart. Pure data layer — no Qt,
no matplotlib, no UI state.

Consumed by:
    Ui/valuation_surface_chart.py  (3D matplotlib widget)
    Ui/dcf_page.py                 (passes _compute_fv_for_assumptions callback)
"""

from typing import Optional, List, Dict, Callable, Any
import math


def _compute_surface_grid(
    fv_func: Callable[[float, float], Optional[float]],
    wacc_values: List[float],
    ltgr_values: List[float],
) -> Dict[str, Any]:
    """
    Core grid computation shared by both surface functions.
    wacc_values and ltgr_values are explicit sorted lists.
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
                    high_point = {"wacc": wacc, "ltgr": ltgr, "fv": fv,
                                  "i": i, "j": j}
                if low_point["fv"] is None or fv < low_point["fv"]:
                    low_point  = {"wacc": wacc, "ltgr": ltgr, "fv": fv,
                                  "i": i, "j": j}
                if i == center_w and j == center_l:
                    center_fv = fv
            else:
                fv = None

            row.append(fv)
        fv_grid.append(row)

    # High/Low conclusion points — one step in from corners,
    # matching sensitivity table high_coord=(3,1) low_coord=(1,3)
    # high = lowest WACC one step in (idx 1) x highest LTGR one step in (idx -2)
    # low  = highest WACC one step in (idx -2) x lowest LTGR one step in (idx 1)
    def _pt(i, j):
        w = wacc_values[i]
        l = ltgr_values[j]
        v = None
        if i < len(fv_grid) and j < len(fv_grid[i]):
            v = fv_grid[i][j]
        return {"wacc": w, "ltgr": l, "fv": v, "i": i, "j": j}

    conclusion_high = _pt(1, -2)   # low WACC, high LTGR — one step in
    conclusion_low  = _pt(-2, 1)   # high WACC, low LTGR — one step in

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
    }


def compute_gg_surface_data(
    fv_func: Callable[[float, float], Optional[float]],
    wacc_center: float,
    ltgr_center: float,
    grid_size: int = 10,
    wacc_step: float = 0.005,
    ltgr_step: float = 0.005,
) -> Dict[str, Any]:
    """
    Parametric version — generates grid from center + step size.
    Used when the sensitivity table is not available (future use).
    """
    half = grid_size // 2
    wacc_values = [round(wacc_center + (i - half) * wacc_step, 6)
                   for i in range(grid_size)]
    ltgr_values = [round(ltgr_center + (j - half) * ltgr_step, 6)
                   for j in range(grid_size)]
    return _compute_surface_grid(fv_func, wacc_values, ltgr_values)


def compute_gg_surface_data_from_explicit(
    fv_func: Callable[[float, float], Optional[float]],
    wacc_values: List[float],
    ltgr_values: List[float],
) -> Dict[str, Any]:
    """
    Explicit version — uses exact WACC and LTGR lists from the
    sensitivity table inputs. Guarantees surface corners match
    the table corners exactly.
    """
    wacc_sorted = sorted(wacc_values)
    ltgr_sorted = sorted(ltgr_values)
    return _compute_surface_grid(fv_func, wacc_sorted, ltgr_sorted)