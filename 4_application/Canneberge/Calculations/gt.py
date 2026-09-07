"""
gt.py
Canneberge — Guideline Transactions Calculation Engine.

Pure calculation layer. No Qt, no Dash, no page imports.
"""

import math
import statistics
from typing import Optional, List, Dict, Any

METRICS = ["TTM Revenue", "TTM EBITDA", "TTM EBIT"]
STAT_NAMES = ["Maximum", "Third Quartile", "Average", "Median", "First Quartile", "Minimum"]


def _quartile(sorted_vals: List[float], q: float) -> Optional[float]:
    if not sorted_vals:
        return None
    n = len(sorted_vals)
    if n == 1:
        return sorted_vals[0]
    pos = q * (n - 1)
    lo = int(pos)
    hi = min(lo + 1, n - 1)
    frac = pos - lo
    return sorted_vals[lo] + frac * (sorted_vals[hi] - sorted_vals[lo])


def calculate_implied_multiple(transaction: dict, metric_name: str) -> Optional[float]:
    """Calculate implied multiple for one transaction row and metric."""
    bev = transaction.get("bev")
    if bev is None or bev == 0:
        return None

    denom = None
    if metric_name == "TTM Revenue":
        denom = transaction.get("ttm_revenue")
    elif metric_name == "TTM EBITDA":
        denom = transaction.get("ttm_ebitda")
    elif metric_name == "TTM EBIT":
        denom = transaction.get("ttm_ebit")

    if denom is None or denom == 0:
        return None

    return bev / denom


def calculate_gt(
    transactions: List[Dict[str, Any]],
    metrics: List[str],
    excluded_rows: List[bool],
    selected_low: List[Any],
    selected_high: List[Any],
    weights: List[Any],
    subject_metric_getter,
    subject_debt: Optional[float],
    dloc: Optional[float],
) -> Dict[str, Any]:
    n_cols = len(metrics)

    # 1. Evaluate transaction multiples
    processed_tx: List[Dict[str, Any]] = []
    multiples_per_col: List[List[float]] = [[] for _ in range(n_cols)]

    for idx, tx in enumerate(transactions):
        is_excluded = excluded_rows[idx] if idx < len(excluded_rows) else False
        row_multiples = []

        for c_idx, metric_name in enumerate(metrics):
            if is_excluded:
                row_multiples.append(None)
            else:
                m = calculate_implied_multiple(tx, metric_name)
                row_multiples.append(m)
                if m is not None:
                    multiples_per_col[c_idx].append(m)

        tx_entry = dict(tx)
        tx_entry["excluded"] = is_excluded
        tx_entry["multiples"] = row_multiples
        processed_tx.append(tx_entry)

    # 2. Statistics
    stat_funcs = {
        "Maximum": lambda v: max(v),
        "Third Quartile": lambda v: _quartile(v, 0.75),
        "Average": lambda v: sum(v) / len(v),
        "Median": lambda v: statistics.median(v),
        "First Quartile": lambda v: _quartile(v, 0.25),
        "Minimum": lambda v: min(v),
    }

    stats: Dict[str, List[Optional[float]]] = {name: [] for name in STAT_NAMES}
    chart_data = {"max": [], "q3": [], "q1": [], "min": []}

    for c_idx in range(n_cols):
        vals = multiples_per_col[c_idx]
        for name, func in stat_funcs.items():
            if vals:
                try:
                    res = func(vals)
                    stats[name].append(res)
                    if name == "Maximum":
                        chart_data["max"].append(res)
                    elif name == "Third Quartile":
                        chart_data["q3"].append(res)
                    elif name == "First Quartile":
                        chart_data["q1"].append(res)
                    elif name == "Minimum":
                        chart_data["min"].append(res)
                except Exception:
                    stats[name].append(None)
            else:
                stats[name].append(None)

    # 3. Subject Metrics
    metric_line_keys = {
        "TTM Revenue": "revenue",
        "TTM EBITDA": "ebitda",
        "TTM EBIT": "ebit",
    }
    subject_metrics: List[Optional[float]] = []
    for metric_name in metrics:
        key = metric_line_keys.get(metric_name)
        v = subject_metric_getter(key, "TTM") if key and callable(subject_metric_getter) else None
        subject_metrics.append(v)

    # 4. Indicated BEV (Low / High)
    indicated_low: List[Optional[float]] = []
    indicated_high: List[Optional[float]] = []

    def _parse_num(val):
        if val is None or str(val).strip() in ("", "-", "NA"):
            return None
        try:
            return float(str(val).replace(",", "").replace("x", "").strip())
        except (ValueError, TypeError):
            return None

    def _parse_pct(val):
        if val is None or str(val).strip() in ("", "-", "NA"):
            return None
        raw = str(val).replace("%", "").replace(",", "").strip()
        try:
            v = float(raw)
            return v / 100.0 if abs(v) > 1 else v
        except (ValueError, TypeError):
            return None

    parsed_lows = [_parse_num(v) for v in selected_low[:n_cols]]
    parsed_highs = [_parse_num(v) for v in selected_high[:n_cols]]
    parsed_weights = [_parse_pct(v) for v in weights[:n_cols]]

    for c_idx in range(n_cols):
        subj = subject_metrics[c_idx]
        s_low = parsed_lows[c_idx] if c_idx < len(parsed_lows) else None
        s_high = parsed_highs[c_idx] if c_idx < len(parsed_highs) else None

        indicated_low.append(subj * s_low if (subj is not None and s_low is not None) else None)
        indicated_high.append(subj * s_high if (subj is not None and s_high is not None) else None)

    # 5. Weighted FMV BEV
    fmv_low, fmv_high = None, None
    sum_low, sum_high, total_w = 0.0, 0.0, 0.0
    any_low, any_high = False, False

    for c_idx in range(n_cols):
        w = parsed_weights[c_idx] if (c_idx < len(parsed_weights) and parsed_weights[c_idx] is not None) else (1.0 / n_cols)
        if indicated_low[c_idx] is not None:
            sum_low += indicated_low[c_idx] * w
            any_low = True
        if indicated_high[c_idx] is not None:
            sum_high += indicated_high[c_idx] * w
            any_high = True

    if any_low:
        fmv_low = sum_low
    if any_high:
        fmv_high = sum_high

    # 6. Bridge to Equity
    debt = subject_debt or 0.0
    dloc_val = dloc or 0.0

    eq_ctrl_low = fmv_low - debt if fmv_low is not None else None
    eq_ctrl_high = fmv_high - debt if fmv_high is not None else None

    eq_nctrl_low = eq_ctrl_low * (1.0 - dloc_val) if eq_ctrl_low is not None else None
    eq_nctrl_high = eq_ctrl_high * (1.0 - dloc_val) if eq_ctrl_high is not None else None

    bev_nctrl_low = eq_nctrl_low + debt if eq_nctrl_low is not None else None
    bev_nctrl_high = eq_nctrl_high + debt if eq_nctrl_high is not None else None

    return {
        "transactions": processed_tx,
        "metrics": metrics,
        "stats": stats,
        "chart": chart_data,
        "subject_metrics": subject_metrics,
        "indicated_low": indicated_low,
        "indicated_high": indicated_high,
        "weights": parsed_weights,
        "fmv_low": fmv_low,
        "fmv_high": fmv_high,
        "bridge": {
            "total_debt": debt,
            "dloc": dloc_val,
            "equity_controlling_low": eq_ctrl_low,
            "equity_controlling_high": eq_ctrl_high,
            "equity_noncontrolling_low": eq_nctrl_low,
            "equity_noncontrolling_high": eq_nctrl_high,
            "bev_noncontrolling_low": bev_nctrl_low,
            "bev_noncontrolling_high": bev_nctrl_high,
        },
    }