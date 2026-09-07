"""
web/lib/dashboard_data.py

Headless Dashboard reconciliation.

Pulls WACC / DCF / GPC / GT / NWC from session + source data (pages
do not need to have been visited). Bridge math is chart_helper.compute_bridge.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from Canneberge.Calculations.chart_helper import (
    MethodRow,
    BridgeInputs,
    compute_bridge,
    weighted_conclusion,
)
from Canneberge.Calculations.dcf import (
    parse_pct,
    parse_number,
    parse_multiple,
    sensitivity_grid,
    SENS_OFFSETS,
)
from Canneberge.Calculations.gpc_metrics import get_metric, dropdown_options
from Canneberge.Calculations.gpc_multiples import compute_all_gpc_multiples, get_subject_cash
from Canneberge.Calculations.wacc import (
    BETA_TYPE_OPTIONS,
    BETA_FREQUENCY_OPTIONS,
    CAPITAL_STRUCTURE_OPTIONS,
    CORPORATE_RATE_SERIES,
)
from web.lib.session_io import dict_to_project_inputs
from web.lib.subject_metrics import get_subject_debt, get_subject_metric_value
from web.lib.wacc_data import get_wacc_results, wacc_state_from_session
from web.lib.nwc_data import get_nwc_results
from web.lib.dcf_data import dcf_state_from_session, get_dcf_results
from web.lib.gt_data import get_gt_results, gt_state_from_session, MAX_COLS as GT_MAX


GPC_MAX = 7
GT_MAX = 3
RECON_METHODS = ("DCF", "GPC", "GT", "GIPO", "NAV")
STAT_OPTIONS = [
    "Maximum", "Third Quartile", "Average", "Median",
    "First Quartile", "Minimum", "Custom",
]
TV_MODELS = [
    "Gordon Growth", "EBITDA Multiple", "Revenue Multiple", "H-Model",
]
GT_METRICS = ["TTM Revenue", "TTM EBITDA", "TTM EBIT"]
COST_ROWS = [
    "Legal Fees", "Accounting Fees", "Auction Fees",
    "Advertising", "Insolvency Practitioner",
]


def parse_weight(text) -> Optional[float]:
    """'50' or '50%' -> 0.50. Magnitude > 1 is percent."""
    if text is None:
        return None
    raw = str(text).strip()
    if not raw or raw in ("-", "NA"):
        return None
    had = "%" in raw
    val = parse_number(raw.replace("%", ""))
    if val is None:
        return None
    if had or abs(val) > 1:
        return val / 100.0
    return val


def dloc_from_cp(cp_text) -> Optional[float]:
    cp = parse_weight(cp_text)
    if cp is None or cp <= -1:
        return None
    return cp / (1.0 + cp)


def _basis_key(session_data: dict) -> str:
    return (
        "EQUITY"
        if (session_data or {}).get("basis_of_value") == "Equity Value"
        else "BEV"
    )


def dashboard_state_from_session(session_data: dict) -> dict:
    raw = (session_data or {}).get("dashboard_page_state", {}) or {}
    recon = raw.get("recon_weights") or {}
    if not isinstance(recon, dict):
        recon = {}
    cost_vals = raw.get("cost_values") or {}
    if not isinstance(cost_vals, dict):
        cost_vals = {}
    try:
        cost_count = max(1, min(10, int(raw.get("cost_count", 5))))
    except (TypeError, ValueError):
        cost_count = 5
    display = raw.get("display_basis", "BEV")
    if display not in ("BEV", "Equity", "$/Share"):
        display = "BEV"
    debt_stat = raw.get("debt_tic_stat", "Median")
    beta_stat = raw.get("beta_stat", "Median")
    if debt_stat not in STAT_OPTIONS:
        debt_stat = "Median"
    if beta_stat not in STAT_OPTIONS:
        beta_stat = "Median"
    return {
        "control_premium": raw.get("control_premium", "24.0%"),
        "display_basis": display,
        "recon_weights": {m: recon.get(m, "") for m in RECON_METHODS},
        "debt_tic_stat": debt_stat,
        "beta_stat": beta_stat,
        "cost_count": cost_count,
        "cost_values": {k: cost_vals.get(k, "") for k in COST_ROWS},
    }


def _gpc_bucket(session_data: dict) -> dict:
    gpc = (session_data or {}).get("gpc_page_state") or {}
    basis = _basis_key(session_data)
    nested = (gpc.get("basis_state") or {}).get(basis) or {}
    if not isinstance(nested, dict):
        nested = {}

    def _as_dict(val, fallback):
        if isinstance(val, dict) and val:
            return dict(val)
        if isinstance(fallback, dict) and fallback:
            return dict(fallback)
        return {}

    return {
        "num_multiples": gpc.get("num_multiples", GPC_MAX),
        "metric_cols": _as_dict(nested.get("metric_cols"), gpc.get("metric_cols")),
        "selected_high": _as_dict(nested.get("selected_high"), gpc.get("selected_high")),
        "selected_low": _as_dict(nested.get("selected_low"), gpc.get("selected_low")),
        "weights": _as_dict(nested.get("weights"), gpc.get("weights")),
        "control_premium": gpc.get("control_premium", ""),
    }


def _subject_shares_and_price(session_data: dict, source_results: dict):
    inputs = dict_to_project_inputs(session_data or {})
    tick = (inputs.subject_ticker or "").lower()
    market_cap = None
    price = None
    sa = (source_results or {}).get("stockanalysis", {}) or {}
    for row in sa.get("Ratios", []) or []:
        if str(row.get("Ticker", "")).lower() != tick:
            continue
        line = str(row.get("Line Item", "")).strip().lower()
        raw = str(row.get("TTM", "")).replace(",", "")
        try:
            val = float(raw)
        except (TypeError, ValueError):
            continue
        if line in ("market capitalization", "market cap"):
            market_cap = val
        elif line in ("last close price", "previous close"):
            price = val
    shares = (market_cap / price) if (market_cap and price) else None
    return shares, price, market_cap


def _dcf_fv(session_data: dict, source_results: dict):
    state = dcf_state_from_session(session_data)
    calc = get_dcf_results(session_data, source_results, state)

    dr = calc["discount_rate"] if calc["discount_rate"] is not None else 0.10
    lt = calc["ltgr"] if calc["ltgr"] is not None else 0.03

    wacc_vals = [dr + off for off in SENS_OFFSETS]
    ltgr_vals = [lt + off for off in SENS_OFFSETS]

    saved_w = state.get("sens_wacc") or {}
    saved_l = state.get("sens_ltgr") or {}

    wacc_use, ltgr_use = [], []
    for i, off in enumerate(SENS_OFFSETS):
        key = f"{off:.2f}"
        wacc_use.append(
            parse_pct(saved_w[key]) if saved_w.get(key) else wacc_vals[i]
        )
        ltgr_use.append(
            parse_pct(saved_l[key]) if saved_l.get(key) else ltgr_vals[i]
        )

    sens = sensitivity_grid(wacc_use, ltgr_use, calc)
    return calc, sens["low"], sens["high"]


def _gpc_block(session_data: dict, source_results: dict) -> dict:
    inputs = dict_to_project_inputs(session_data or {})
    bucket = _gpc_bucket(session_data)
    try:
        n = max(1, min(GPC_MAX, int(bucket["num_multiples"] or GPC_MAX)))
    except (TypeError, ValueError):
        n = GPC_MAX
    basis = _basis_key(session_data)
    options = dropdown_options(basis)
    names = []
    for i in range(n):
        name = bucket["metric_cols"].get(str(i))
        if name not in options:
            name = options[i % len(options)] if options else ""
        names.append(name)

    subject_vals, ind_low, ind_high = [], [], []
    for i, name in enumerate(names):
        metric = get_metric(name)
        if metric is None:
            subject_vals.append(None)
            ind_low.append(None)
            ind_high.append(None)
            continue
        line = metric.line_key
        if line == "ebitda" and metric.period in {"NFY", "NFY+1", "NFY+2"}:
            line = "adj_ebitda"
        subj = get_subject_metric_value(
            session_data or {}, source_results or {}, line, metric.period
        )
        lo = parse_multiple(bucket["selected_low"].get(str(i)))
        hi = parse_multiple(bucket["selected_high"].get(str(i)))
        subject_vals.append(subj)
        ind_low.append(subj * lo if (subj is not None and lo is not None) else None)
        ind_high.append(subj * hi if (subj is not None and hi is not None) else None)

    weights = []
    for i in range(n):
        w = parse_weight(bucket["weights"].get(str(i), f"{100.0 / n:.1f}"))
        weights.append(w if w is not None else 1.0 / n)

    sum_lo = sum_hi = 0.0
    any_p = False
    for lo, hi, w in zip(ind_low, ind_high, weights):
        if lo is None or hi is None or w is None:
            continue
        sum_lo += lo * w
        sum_hi += hi * w
        any_p = True

    return {
        "n": n,
        "names": names,
        "options": options,
        "indicated_low": ind_low,
        "indicated_high": ind_high,
        "weights": [bucket["weights"].get(str(i), "") for i in range(n)],
        "selected_low": [bucket["selected_low"].get(str(i), "") for i in range(n)],
        "selected_high": [bucket["selected_high"].get(str(i), "") for i in range(n)],
        "fmv_low": sum_lo if any_p else None,
        "fmv_high": sum_hi if any_p else None,
        "source_basis": "Equity" if basis == "EQUITY" else "BEV",
    }


def _gt_block(session_data: dict, source_results: dict) -> dict:
    state = gt_state_from_session(session_data)
    calc = get_gt_results(session_data, source_results, state)
    n = int(state.get("num_multiples") or GT_MAX)
    n = max(1, min(GT_MAX, n))
    return {
        "n": n,
        "names": list(calc.get("metric_selections") or GT_METRICS)[:n],
        "indicated_low": list(calc.get("indicated_low") or [])[:n],
        "indicated_high": list(calc.get("indicated_high") or [])[:n],
        "selected_low": list(state.get("selected_low") or [])[:n],
        "selected_high": list(state.get("selected_high") or [])[:n],
        "weights": list(state.get("weights") or [])[:n],
        "fmv_low": calc.get("fmv_low"),
        "fmv_high": calc.get("fmv_high"),
        "chart": calc.get("chart") or calc.get("chart_data") or {},
    }


def _bridge_inputs(session_data, source_results, dash_state) -> BridgeInputs:
    inputs = dict_to_project_inputs(session_data or {})
    sa = (source_results or {}).get("stockanalysis", {}) or {}
    cash = get_subject_cash(sa.get("BS", []), inputs.subject_ticker)
    nwc = get_nwc_results(session_data, source_results)
    surplus = (nwc.get("bridge") or {}).get("surplus_deficit")
    if surplus is None:
        surplus = ((session_data or {}).get("nwc_page_state") or {}).get("surplus_deficit")
    shares, price, _cap = _subject_shares_and_price(session_data, source_results)
    return BridgeInputs(
        cash=cash,
        nwc_surplus=surplus,
        debt=get_subject_debt(session_data or {}, source_results or {}),
        liquidation=get_subject_metric_value(
            session_data or {}, source_results or {}, "preferred_stock", "TTM"
        ),
        dloc=dloc_from_cp(dash_state["control_premium"]),
        shares_outstanding=shares,
        share_price=price,
    )


def _observed_on_basis(bridge: BridgeInputs, basis: str) -> Optional[float]:
    price = bridge.share_price
    shares = bridge.shares_outstanding
    if price is None:
        return None
    if basis == "$/Share":
        return price
    if shares is None:
        return None
    mkt = price * shares
    if basis == "Equity":
        return mkt
    return mkt + (bridge.debt or 0.0) - (bridge.cash or 0.0)


def _single_bridged(name, low, high, apply_dloc, bridge, basis, source_basis):
    if low is None and high is None:
        return None, None
    row = MethodRow(
        name=name, bev_low=low, bev_high=high,
        apply_dloc=apply_dloc, source_basis=source_basis,
    )
    compute_bridge([row], bridge)
    return row.values_for_basis(basis)


def get_dashboard_results(session_data: dict, source_results: dict) -> dict:
    session_data = session_data or {}
    source_results = source_results or {}
    dash = dashboard_state_from_session(session_data)
    wacc = get_wacc_results(session_data, source_results)
    wacc_state = wacc_state_from_session(session_data)

    dcf_calc, dcf_low, dcf_high = _dcf_fv(session_data, source_results)
    gpc = _gpc_block(session_data, source_results)
    gt = _gt_block(session_data, source_results)
    bridge = _bridge_inputs(session_data, source_results, dash)
    basis = dash["display_basis"]
    is_fcfe = bool(dcf_calc.get("is_fcfe"))
    dcf_source = "Equity" if is_fcfe else "BEV"

    method_rows: List[MethodRow] = [
        MethodRow(
            name="Discounted Cash Flow Method",
            bev_low=dcf_low, bev_high=dcf_high,
            apply_dloc=(dcf_source == "BEV"),
            source_basis=dcf_source,
        )
    ]
    for i, name in enumerate(gpc["names"]):
        method_rows.append(MethodRow(
            name=f"GPC - {name}",
            bev_low=gpc["indicated_low"][i] if i < len(gpc["indicated_low"]) else None,
            bev_high=gpc["indicated_high"][i] if i < len(gpc["indicated_high"]) else None,
            apply_dloc=False,
            source_basis=gpc["source_basis"],
        ))
    for i, name in enumerate(gt["names"]):
        method_rows.append(MethodRow(
            name=f"GT - {name}",
            bev_low=gt["indicated_low"][i] if i < len(gt["indicated_low"]) else None,
            bev_high=gt["indicated_high"][i] if i < len(gt["indicated_high"]) else None,
            apply_dloc=True,
            source_basis="BEV",
        ))
    compute_bridge(method_rows, bridge)

    dcf_pair = (None, None)
    for row in method_rows:
        if row.name == "Discounted Cash Flow Method":
            dcf_pair = row.values_for_basis(basis)
            break

    gpc_pair = _single_bridged(
        "GPC (weighted)", gpc["fmv_low"], gpc["fmv_high"],
        False, bridge, basis, gpc["source_basis"],
    )
    gt_pair = _single_bridged(
        "GT (weighted)", gt["fmv_low"], gt["fmv_high"],
        True, bridge, basis, "BEV",
    )

    pairs = {
        "DCF": dcf_pair,
        "GPC": gpc_pair,
        "GT": gt_pair,
        "GIPO": (None, None),
        "NAV": (None, None),
    }
    weights = [parse_weight(dash["recon_weights"].get(m)) for m in RECON_METHODS]
    concluded = weighted_conclusion(
        [pairs[m] for m in RECON_METHODS], weights
    )
    football = [
        (row.name, *row.values_for_basis(basis))
        for row in method_rows
    ]

    return {
        "dash": dash,
        "wacc": wacc,
        "wacc_state": wacc_state,
        "dcf": dcf_calc,
        "dcf_low": dcf_low,
        "dcf_high": dcf_high,
        "gpc": gpc,
        "gt": gt,
        "bridge": bridge,
        "dloc": bridge.dloc,
        "basis": basis,
        "pairs": pairs,
        "concluded": concluded,
        "observed": _observed_on_basis(bridge, basis),
        "football": football,
        "stats": wacc.get("stats") or {},
        "is_fcfe": is_fcfe,
    }