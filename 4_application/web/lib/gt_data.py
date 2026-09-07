"""
web/lib/gt_data.py

Headless GT calculation/state adapter.

The UI layer lives in web/pages/gt.py.
The transaction math lives in Canneberge.Calculations.gt.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from Canneberge.Calculations.gt import (
    METRICS,
    STAT_NAMES,
    calculate_gt,
)
from web.lib.session_io import dict_to_project_inputs
from web.lib.subject_metrics import (
    get_subject_debt,
    get_subject_metric_value,
)


MAX_COLS = 3
MAX_ROWS = 5

DEFAULT_METRICS = [
    "TTM Revenue",
    "TTM EBITDA",
    "TTM EBIT",
]


def _fmt_multiple(value: Optional[float]) -> str:
    if value is None:
        return "NA"
    return f"{value:.2f}x"


def _fmt_currency(value: Optional[float]) -> str:
    if value is None:
        return "NA"
    return f"{value:,.0f}"


def _fmt_pct(value: Optional[float]) -> str:
    if value is None:
        return "NA"
    return f"{value * 100:.1f}%"


def _safe_list(value, default=None) -> list:
    if isinstance(value, list):
        return list(value)
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, dict):
        def sort_key(item):
            try:
                return int(item[0])
            except (TypeError, ValueError):
                return 999999

        return [v for _key, v in sorted(value.items(), key=sort_key)]
    return list(default or [])


def _normalise_transaction(transaction: Any) -> dict:
    if isinstance(transaction, dict):
        return {
            "closing_date": transaction.get("closing_date", "") or "",
            "target": transaction.get("target", "") or "",
            "acquirer": transaction.get("acquirer", "") or "",
            "bev": _parse_val(transaction.get("bev")),
            "ttm_revenue": _parse_val(transaction.get("ttm_revenue")),
            "ttm_ebitda": _parse_val(transaction.get("ttm_ebitda")),
            "ttm_ebit": _parse_val(transaction.get("ttm_ebit")),
        }

    return {
        "closing_date": getattr(transaction, "closing_date", "") or "",
        "target": getattr(transaction, "target", "") or "",
        "acquirer": getattr(transaction, "acquirer", "") or "",
        "bev": _parse_val(getattr(transaction, "bev", None)),
        "ttm_revenue": _parse_val(getattr(transaction, "ttm_revenue", None)),
        "ttm_ebitda": _parse_val(getattr(transaction, "ttm_ebitda", None)),
        "ttm_ebit": _parse_val(getattr(transaction, "ttm_ebit", None)),
    }


def _parse_val(val) -> Optional[float]:
    if val is None or str(val).strip() in ("", "-", "NA"):
        return None
    try:
        return float(str(val).replace(",", "").replace("$", "").replace("x", "").strip())
    except (ValueError, TypeError):
        return None


def _pad(values: list, count: int, default="") -> list:
    result = list(values or [])
    while len(result) < count:
        result.append(default)
    return result[:count]


def gt_state_from_session(session_data: dict) -> dict:
    raw = (session_data or {}).get("gt_page_state", {}) or {}

    try:
        n_cols = int(raw.get("num_multiples", MAX_COLS))
    except (TypeError, ValueError):
        n_cols = MAX_COLS

    n_cols = max(1, min(MAX_COLS, n_cols))

    metric_selections = _pad(
        _safe_list(raw.get("metric_selections"), DEFAULT_METRICS),
        MAX_COLS,
    )
    metric_selections = [
        value if value in METRICS else DEFAULT_METRICS[i]
        for i, value in enumerate(metric_selections)
    ]

    selected_low = _pad(
        _safe_list(raw.get("selected_low")),
        MAX_COLS,
    )
    selected_high = _pad(
        _safe_list(raw.get("selected_high")),
        MAX_COLS,
    )
    weights = _pad(
        _safe_list(raw.get("weights")),
        MAX_COLS,
    )

    default_weight = f"{100.0 / n_cols:.1f}%"
    for i in range(MAX_COLS):
        if i < n_cols and not weights[i]:
            weights[i] = default_weight

    excluded_rows = _pad(
        _safe_list(raw.get("excluded_rows")),
        MAX_ROWS,
        False,
    )
    excluded_rows = [bool(value) for value in excluded_rows]

    return {
        "num_multiples": n_cols,
        "dloc": raw.get("dloc", "19.4%"),
        "metric_selections": metric_selections,
        "selected_low": selected_low,
        "selected_high": selected_high,
        "weights": weights,
        "excluded_rows": excluded_rows,
    }


def get_gt_results(
    session_data: dict,
    source_results: dict,
    state: Optional[dict] = None,
) -> dict:
    """
    Calculate GT results from current session and source data.

    Returns dictionary with all values consumed by web/pages/gt.py.
    """
    session_data = session_data or {}
    source_results = source_results or {}
    state = state or gt_state_from_session(session_data)

    inputs = dict_to_project_inputs(session_data)
    transactions = [
        _normalise_transaction(transaction)
        for transaction in (inputs.gt_transactions or [])
    ]

    n_cols = max(
        1,
        min(
            MAX_COLS,
            int(state.get("num_multiples", MAX_COLS)),
        ),
    )

    metrics = list(state.get("metric_selections") or DEFAULT_METRICS)
    metrics = [
        metric if metric in METRICS else DEFAULT_METRICS[i]
        for i, metric in enumerate(_pad(metrics, MAX_COLS, DEFAULT_METRICS[0]))
    ][:n_cols]

    selected_low = _pad(
        list(state.get("selected_low") or []),
        n_cols,
    )
    selected_high = _pad(
        list(state.get("selected_high") or []),
        n_cols,
    )
    weights = _pad(
        list(state.get("weights") or []),
        n_cols,
    )

    excluded_rows = _pad(
        list(state.get("excluded_rows") or []),
        MAX_ROWS,
        False,
    )

    dloc = state.get("dloc", "19.4%")

    def subject_metric_getter(line_key: str, period: str):
        return get_subject_metric_value(
            session_data,
            source_results,
            line_key,
            period,
        )

    result = calculate_gt(
        transactions=transactions,
        metrics=metrics,
        excluded_rows=excluded_rows,
        selected_low=selected_low,
        selected_high=selected_high,
        weights=weights,
        subject_metric_getter=subject_metric_getter,
        subject_debt=get_subject_debt(session_data, source_results),
        dloc=_parse_dloc(dloc),
    )

    # Add adapter properties required by web/pages/gt.py
    result["inputs"] = inputs
    result["n_cols"] = n_cols
    result["metric_selections"] = metrics
    result["tx_rows"] = result.get("transactions", [])
    result["multiples_per_col"] = _multiples_per_column(
        result["transactions"],
        len(metrics),
    )
    result["dloc"] = _parse_dloc(dloc)
    result["debt"] = result.get("bridge", {}).get("total_debt")
    result["eq_ctrl_low"] = result.get("bridge", {}).get("equity_controlling_low")
    result["eq_ctrl_high"] = result.get("bridge", {}).get("equity_controlling_high")
    result["eq_nctrl_low"] = result.get("bridge", {}).get("equity_noncontrolling_low")
    result["eq_nctrl_high"] = result.get("bridge", {}).get("equity_noncontrolling_high")
    result["bev_nctrl_low"] = result.get("bridge", {}).get("bev_noncontrolling_low")
    result["bev_nctrl_high"] = result.get("bridge", {}).get("bev_noncontrolling_high")
    result["chart_data"] = result.get("chart", {})

    return result


def _multiples_per_column(transaction_rows: list, n_cols: int) -> list[list[float]]:
    values: list[list[float]] = [[] for _ in range(n_cols)]

    for row in transaction_rows or []:
        if row.get("excluded"):
            continue

        for index, value in enumerate(row.get("multiples", [])[:n_cols]):
            if value is not None:
                values[index].append(value)

    return values


def _parse_dloc(value) -> Optional[float]:
    if value is None:
        return None

    raw = str(value).strip().replace("%", "").replace(",", "")
    if not raw:
        return None

    try:
        number = float(raw)
    except (TypeError, ValueError):
        return None

    return number / 100.0 if abs(number) > 1 else number