"""
web/pages/dcf.py

Dash Discounted Cash Flow page.

All math lives in Canneberge.Calculations.dcf. WACC and NWC come from
web/lib/wacc_data.py and web/lib/nwc_data.py, computed on the fly — no
page needs to have been visited first.

State: session-store["dcf_page_state"], desktop-compatible plus web-only
extras (bridge_other_adj, sens_wacc / sens_ltgr overrides, cached outputs).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import dash
import dash_bootstrap_components as dbc
from dash import html, Input, Output, State, callback, ctx, ALL, no_update

from Canneberge.Calculations.dcf import (
    ROW_SPECS, ROWS_WITH_BORDER_ABOVE, ROWS_WITH_SPACER_ABOVE,
    HIST_BLANK_ROWS, PCT_ROWS, FACTOR_ROWS, TV_MODELS,
    SENS_OFFSETS, SENS_HIGH_COORD, SENS_LOW_COORD, SENS_CENTER_COORD,
    parse_pct, parse_number, normalise_rate,
    dcf_period_columns, dcf_fye_years, calculate_ppa,
    build_dcf, sensitivity_grid,
)
from web.lib.session_io import dict_to_project_inputs
from web.lib.subject_metrics import get_subject_metric_value
from web.lib.wacc_data import get_wacc_results
from web.lib.nwc_data import get_nwc_results
from web.components import reverse_dcf_modal

dash.register_page(__name__, path="/dcf", name="DCF")


# ---------------------------------------------------------------------------
# Geometry / style
# ---------------------------------------------------------------------------

COL_W = 88
LABEL_W = 300
GAP_W = 12
SENS_W = 82

_BAND = {
    "backgroundColor": "#2b3e50", "color": "white", "fontWeight": "bold",
    "fontSize": "11px", "padding": "3px 8px", "textAlign": "center",
    "border": "1px solid #555",
}
_HDR_PERIOD = {
    "color": "#9fb3c8", "fontSize": "11px", "padding": "3px 6px",
    "textAlign": "right", "whiteSpace": "nowrap",
}
_LBL = {"color": "#e6e6e6", "fontSize": "11px", "padding": "3px 6px",
        "whiteSpace": "nowrap"}
_LBL_B = {**_LBL, "fontWeight": "bold"}
_LBL_INDENT = {**_LBL, "paddingLeft": "18px"}
_LBL_MARGIN = {**_LBL, "fontStyle": "italic", "color": "#9fb3c8",
               "paddingLeft": "18px"}
_CELL = {"color": "#dddddd", "fontSize": "11px", "padding": "3px 6px",
         "textAlign": "right", "whiteSpace": "nowrap"}
_CELL_B = {**_CELL, "fontWeight": "bold", "color": "#ffffff"}
_CELL_MARGIN = {**_CELL, "fontStyle": "italic", "color": "#9fb3c8"}
_BORDER_TOP = {"borderTop": "1px solid #4a5568"}
_EMPHASIS = {"borderTop": "1px solid #4a5568", "borderBottom": "3px double #4a5568"}

_INPUT = {
    "backgroundColor": "#2a2a2a", "color": "#f5f5f5",
    "border": "1px solid #666", "fontSize": "11px", "textAlign": "right",
    "padding": "1px 4px", "height": "24px", "width": f"{COL_W - 6}px",
}
_INPUT_SM = {**_INPUT, "width": "90px"}
_INPUT_SENS = {**_INPUT, "width": f"{SENS_W}px"}
_SELECT = {
    "backgroundColor": "#2a2a2a", "color": "#f5f5f5",
    "border": "1px solid #666", "fontSize": "12px",
    "height": "27px", "padding": "1px 6px",
}

_TABLE = {
    "tableLayout": "fixed", "width": "max-content", "minWidth": "100%",
    "borderCollapse": "separate", "borderSpacing": 0,
}

PANEL_LBL_W = 200
PANEL_VAL_W = 92


def _fmt_currency(v) -> str:
    if v is None:
        return "-"
    try:
        return f"{v:,.0f}"
    except (TypeError, ValueError):
        return "-"


def _fmt_pct(v) -> str:
    if v is None:
        return "-"
    try:
        return f"{v * 100:.1f}%"
    except (TypeError, ValueError):
        return "-"


def _fmt_factor(v) -> str:
    if v is None:
        return "-"
    try:
        return f"{v:.4f}" if abs(v) < 1 else f"{v:.2f}"
    except (TypeError, ValueError):
        return "-"


def _fmt_row(row_key: str, v) -> str:
    if row_key in PCT_ROWS:
        return _fmt_pct(v)
    if row_key == "pvp":
        return "-" if v is None else f"{v:.2f}"
    if row_key == "pvf":
        return "-" if v is None else f"{v:.2f}"
    if row_key == "ppa":
        return "-" if v is None else f"{v:.4f}"
    return _fmt_currency(v)


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

_TV_DEFAULTS = {
    "Gordon Growth": {},
    "EBITDA Multiple": {"multiple": "10.00x"},
    "Revenue Multiple": {"multiple": "10.00x"},
    "H-Model": {"num_years": "5", "short_term_growth": "20.0%"},
}


def _state_from_session(session_data: dict) -> dict:
    raw = (session_data or {}).get("dcf_page_state", {}) or {}
    saved_tv = raw.get("tv_inputs") or {}

    tv_inputs: Dict[str, Dict[str, str]] = {}
    for model, defaults in _TV_DEFAULTS.items():
        saved = saved_tv.get(model) or {}
        tv_inputs[model] = {
            k: (saved.get(k) if saved.get(k) is not None else d)
            for k, d in defaults.items()
        }

    model = raw.get("tv_model")
    if model not in TV_MODELS:
        model = "Gordon Growth"

    cf = raw.get("cash_flows_to")
    if cf not in ("FCFF", "FCFE"):
        cf = "FCFF"

    return {
        "ltg_input": raw.get("ltg_input", "3.0%"),
        "tv_model": model,
        "capex_dep_pct": raw.get("capex_dep_pct", "100.0%"),
        "cash_flows_to": cf,
        "other_adj_inputs": dict(raw.get("other_adj_inputs") or {}),
        "residual_amortization": raw.get("residual_amortization", ""),
        "bridge_other_adj": raw.get("bridge_other_adj", ""),
        "tv_inputs": tv_inputs,
        # v1 persisted every generated sensitivity header during Dash
        # remounts, which froze auto WACC/LTGR values permanently.
        #
        # v2 stores only values the user intentionally overrides.
        # Existing v1 sensitivity maps are intentionally discarded once;
        # they were auto-generated values, not reliable user selections.
        "sens_wacc": (
            dict(raw.get("sens_wacc") or {})
            if raw.get("sensitivity_override_version") == 2
            else {}
        ),
        "sens_ltgr": (
            dict(raw.get("sens_ltgr") or {})
            if raw.get("sensitivity_override_version") == 2
            else {}
        ),
        "nols": raw.get("nols", "No"),
        "nwc_by_mgmt": raw.get("nwc_by_mgmt", "No"),
        "valuation_approach": raw.get("valuation_approach", "DCF"),
    }


def _effective_cash_flows_to(session_data: dict, state: dict) -> str:
    """Home's Basis of Value overrides the toggles dialog — desktop rule."""
    basis = (session_data or {}).get("basis_of_value")
    if basis == "Equity Value":
        return "FCFE"
    if basis == "Business Enterprise Value":
        return "FCFF"
    return state["cash_flows_to"]


# ---------------------------------------------------------------------------
# Compute
# ---------------------------------------------------------------------------

def _compute(session_data: dict, source_results: dict, state: dict) -> dict:
    inputs = dict_to_project_inputs(session_data or {})
    hist_cols = list(inputs.historical_period_columns)
    proj_cols = list(inputs.projection_period_columns)

    cash_flows_to = _effective_cash_flows_to(session_data, state)
    is_fcfe = cash_flows_to == "FCFE"

    discount_rate = get_wacc_results(session_data, source_results)
    discount_rate = discount_rate["ke"] if is_fcfe else discount_rate["wacc"]

    nwc = get_nwc_results(session_data, source_results)
    changes = nwc.get("changes", {}) or {}

    debt_state = (session_data or {}).get("debt_page_state", {}) or {}
    interest_map = debt_state.get("interest_expense_by_period") or {}
    if not interest_map:
        interest_map = debt_state.get("projected_interest") or {}

    headers, _is_hist = dcf_period_columns(hist_cols, proj_cols)

    net_interest: Dict[str, Optional[float]] = {}
    for p in headers:
        if p in hist_cols:
            inc = get_subject_metric_value(session_data, source_results, "interest_income", p)
            exp = get_subject_metric_value(session_data, source_results, "interest_expense", p)
            if inc is None and exp is None:
                net_interest[p] = None
            else:
                net_interest[p] = (inc or 0.0) - abs(exp or 0.0)
        else:
            v = parse_number(interest_map.get(p))
            net_interest[p] = -abs(v) if v is not None else None

    def sf(key: str, period: str) -> Optional[float]:
        return get_subject_metric_value(
            session_data or {}, source_results or {}, key, period
        )

    calc = build_dcf(
        historical_period_columns=hist_cols,
        projection_period_columns=proj_cols,
        sf=sf,
        changes_in_nwc=changes,
        net_interest_by_period=net_interest,
        other_adj_inputs=state["other_adj_inputs"],
        residual_amortization=state["residual_amortization"],
        tax_rate=normalise_rate(getattr(inputs, "subject_tax_rate", None)),
        discount_rate=discount_rate,
        ltgr=parse_pct(state["ltg_input"]),
        dep_pct_of_capex=parse_pct(state["capex_dep_pct"]),
        ppa=calculate_ppa(inputs.next_fiscal_year, inputs.valuation_date),
        is_fcfe=is_fcfe,
        tv_model=state["tv_model"],
        tv_inputs=state["tv_inputs"],
        bridge_other_adj=state["bridge_other_adj"],
    )

    calc["inputs"] = inputs
    calc["cash_flows_to"] = cash_flows_to
    calc["tv_model"] = state["tv_model"]
    calc["tv_inputs"] = state["tv_inputs"]
    calc["fye"] = dcf_fye_years(
        hist_cols, proj_cols,
        inputs.last_fiscal_year_year, inputs.next_fiscal_year_year,
        inputs.nfy_1_year, inputs.nfy_2_year,
    )
    return calc


# ---------------------------------------------------------------------------
# Main grid
# ---------------------------------------------------------------------------

def _colgroup(num_hist: int, num_proj: int):
    cols = [html.Col(style={"width": f"{LABEL_W}px"})]
    cols += [html.Col(style={"width": f"{COL_W}px"}) for _ in range(num_hist)]
    cols.append(html.Col(style={"width": f"{GAP_W}px"}))
    cols += [html.Col(style={"width": f"{COL_W}px"}) for _ in range(num_proj)]
    cols.append(html.Col(style={"width": f"{GAP_W}px"}))
    cols.append(html.Col(style={"width": f"{COL_W}px"}))
    return html.Colgroup(cols)


def _period_cells(headers, num_hist, num_proj, builder, gap_style=None):
    gap_style = gap_style or {}
    cells = []
    for idx, period in enumerate(headers):
        if idx == num_hist:
            cells.append(html.Td("", style=gap_style))
        if idx == num_hist + num_proj:
            cells.append(html.Td("", style=gap_style))
        cells.append(builder(idx, period))
    return cells


def _build_main_table(state: dict, calc: dict):
    headers = calc["headers"]
    is_hist = calc["is_hist"]
    num_hist = calc["num_hist"]
    num_proj = calc["num_proj"]
    rows = calc["rows"]
    is_fcfe = calc["is_fcfe"]
    fye = calc["fye"]

    trs = []

    trs.append(html.Tr([
        html.Td("", style=_LBL),
        html.Td("Historical Financials", colSpan=num_hist, style=_BAND) if num_hist
        else html.Td("", style=_LBL),
        html.Td("", style=_LBL),
        html.Td("Projected Financials", colSpan=num_proj, style=_BAND),
        html.Td("", style=_LBL),
        html.Td("Residual", style=_BAND),
    ]))

    trs.append(html.Tr(
        [html.Td("", style=_LBL)]
        + _period_cells(headers, num_hist, num_proj,
                        lambda i, p: html.Td(p, style=_HDR_PERIOD))
    ))

    trs.append(html.Tr(
        [html.Td("FYE", style=_LBL_B)]
        + _period_cells(headers, num_hist, num_proj,
                        lambda i, p: html.Td(fye.get(p, ""), style=_HDR_PERIOD))
    ))

    for row_key, label, bold, indent, margin in ROW_SPECS:
        if row_key in ROWS_WITH_SPACER_ABOVE:
            trs.append(html.Tr([html.Td("", style={"height": "8px"})]))

        display = label
        if is_fcfe:
            if row_key == "ebit":
                display = "EBT"
            elif row_key == "ebit_margin":
                display = "EBT Margin"
            elif row_key == "nopat":
                display = "Net Income"

        if row_key == "pvf":
            rate_lbl = "Ke" if is_fcfe else "WACC"
            dr = calc["discount_rate"]
            pct = f"{dr * 100:.2f}%" if dr is not None else "N/A%"
            display = f"Present Value Factor @ {rate_lbl} = {pct}"

        lstyle = _LBL_B if bold else (_LBL_MARGIN if margin else (_LBL_INDENT if indent else _LBL))
        cstyle = _CELL_B if bold else (_CELL_MARGIN if margin else _CELL)
        if row_key in ROWS_WITH_BORDER_ABOVE:
            lstyle = {**lstyle, **_BORDER_TOP}
            cstyle = {**cstyle, **_BORDER_TOP}

        # Net Interest only shows in FCFE mode.
        if row_key == "net_interest" and not is_fcfe:
            continue
        if row_key == "other_adj" and not is_fcfe:
            continue

        def cell(i, p, _rk=row_key, _cs=cstyle):
            if _rk == "less_other_adj" and not is_hist[i]:
                return html.Td(
                    dbc.Input(
                        id={"type": "dcf-other-adj", "period": p},
                        type="text", debounce=True, size="sm",
                        value=state["other_adj_inputs"].get(p, ""),
                        style=_INPUT,
                    ),
                    style={"padding": "1px 2px", **({k: v for k, v in _cs.items()
                                                     if k == "borderTop"})},
                )
            if _rk == "amortization" and p == "Residual":
                return html.Td(
                    dbc.Input(
                        id="dcf-residual-amortization",
                        type="text", debounce=True, size="sm",
                        value=state["residual_amortization"],
                        style=_INPUT,
                    ),
                    style={"padding": "1px 2px"},
                )
            if is_hist[i] and _rk in HIST_BLANK_ROWS:
                return html.Td("", style=_cs)
            return html.Td(_fmt_row(_rk, rows[_rk].get(p)), style=_cs)

        trs.append(html.Tr(
            [html.Td(display, style=lstyle)]
            + _period_cells(headers, num_hist, num_proj, cell, gap_style=cstyle)
        ))

    return html.Table(
        [_colgroup(num_hist, num_proj), html.Tbody(trs)],
        className="table table-sm table-dark mb-0",
        style=_TABLE,
    )


# ---------------------------------------------------------------------------
# TV panel
# ---------------------------------------------------------------------------

def _panel_out(label: str, value: str, bold: bool = False):
    return html.Div([
        html.Span(label, style={**(_LBL_B if bold else _LBL),
                                "width": f"{PANEL_LBL_W}px",
                                "display": "inline-block"}),
        html.Span(value, style={**(_CELL_B if bold else _CELL),
                                "width": f"{PANEL_VAL_W}px",
                                "display": "inline-block"}),
    ], className="d-flex align-items-center", style={"padding": "1px 0"})


def _panel_in(label: str, model: str, key: str, value: str):
    return html.Div([
        html.Span(label, style={**_LBL, "width": f"{PANEL_LBL_W}px",
                                "display": "inline-block"}),
        dbc.Input(
            id={"type": "dcf-tv-input", "model": model, "key": key},
            type="text", value=value, debounce=True, size="sm",
            style={**_INPUT_SM, "width": f"{PANEL_VAL_W}px"},
        ),
    ], className="d-flex align-items-center", style={"padding": "1px 0"})


def _build_tv_panel(state: dict, calc: dict):
    model = state["tv_model"]
    tv = calc["tv"].get(model, {}) or {}
    cfg = state["tv_inputs"].get(model, {}) or {}
    mult = tv.get("multiple")

    if model == "Gordon Growth":
        body = [
            _panel_out("Residual Year Cash Flow:", _fmt_currency(tv.get("cash_flow"))),
            _panel_out("Capitalization Rate:", _fmt_pct(tv.get("cap_rate"))),
            _panel_out("Residual Value:", _fmt_currency(tv.get("residual_value"))),
            _panel_out("PV Factor:", _fmt_factor(tv.get("pv_factor"))),
            _panel_out("Present Value of Residual Value:",
                       _fmt_currency(tv.get("pv_residual")), bold=True),
        ]
    elif model in ("EBITDA Multiple", "Revenue Multiple"):
        metric_lbl = "EBITDA:" if model == "EBITDA Multiple" else "Revenue:"
        mult_lbl = "EBITDA Multiple:" if model == "EBITDA Multiple" else "Revenue Multiple:"
        body = [
            _panel_in("Selected Multiple:", model, "multiple", cfg.get("multiple", "10.00x")),
            _panel_out(metric_lbl, _fmt_currency(tv.get("metric"))),
            _panel_out(mult_lbl, f"{mult:.2f}x" if mult is not None else "-"),
            _panel_out("Residual Value:", _fmt_currency(tv.get("residual_value"))),
            _panel_out("PV Factor:", _fmt_factor(tv.get("pv_factor"))),
            _panel_out("Present Value of Residual Value:",
                       _fmt_currency(tv.get("pv_residual")), bold=True),
        ]
    else:  # H-Model
        body = [
            _panel_in("Number of Years:", model, "num_years", cfg.get("num_years", "5")),
            _panel_in("Short Term Growth Rate:", model, "short_term_growth",
                      cfg.get("short_term_growth", "20.0%")),
            _panel_out("Free Cash Flow:", _fmt_currency(tv.get("cash_flow"))),
            _panel_out("Capitalization Rate:", _fmt_pct(tv.get("cap_rate"))),
            _panel_out("Residual Value:", _fmt_currency(tv.get("residual_value"))),
            _panel_out("PV Factor:", _fmt_factor(tv.get("pv_factor"))),
            _panel_out("Present Value of Residual Value:",
                       _fmt_currency(tv.get("pv_residual")), bold=True),
        ]

    return html.Div(body)


# ---------------------------------------------------------------------------
# Sensitivity
# ---------------------------------------------------------------------------

def _sens_defaults(calc: dict, state: dict):
    dr = calc["discount_rate"] if calc["discount_rate"] is not None else 0.10
    lt = calc["ltgr"] if calc["ltgr"] is not None else 0.03

    wacc_texts, ltgr_texts = [], []
    for off in SENS_OFFSETS:
        key = f"{off:.2f}"
        saved = state["sens_wacc"].get(key)
        wacc_texts.append(saved if saved else f"{(dr + off) * 100:.4f}%")
        saved_l = state["sens_ltgr"].get(key)
        ltgr_texts.append(saved_l if saved_l else f"{(lt + off) * 100:.1f}%")
    return wacc_texts, ltgr_texts


def _heat_style(fv, min_fv, max_fv, bold, center):
    norm = (fv - min_fv) / (max_fv - min_fv) if max_fv > min_fv else 0.5
    if norm < 0.5:
        r0 = norm / 0.5
        rr = int(211 * (1 - r0) + 120 * r0)
        gg = int(47 * (1 - r0) + 120 * r0)
        bb = int(47 * (1 - r0) + 120 * r0)
        a = 0.35 * (1 - r0) + 0.1 * r0
    else:
        r0 = (norm - 0.5) / 0.5
        rr = int(120 * (1 - r0) + 46 * r0)
        gg = int(120 * (1 - r0) + 125 * r0)
        bb = int(120 * (1 - r0) + 50 * r0)
        a = 0.1 * (1 - r0) + 0.35 * r0

    style = {
        **_CELL,
        "backgroundColor": f"rgba({rr}, {gg}, {bb}, {a:.2f})",
        "borderRadius": "3px",
        "padding": "2px 4px",
        "width": f"{SENS_W}px",
    }
    if bold:
        style["fontWeight"] = "bold"
        style["color"] = "#ffffff"
    if center:
        style["border"] = "1px solid #7c68af"
    return style


def _build_sensitivity(state: dict, calc: dict):
    wacc_texts, ltgr_texts = _sens_defaults(calc, state)
    wacc_vals = [parse_pct(t) for t in wacc_texts]
    ltgr_vals = [parse_pct(t) for t in ltgr_texts]

    result = sensitivity_grid(wacc_vals, ltgr_vals, calc)
    grid = result["grid"]
    min_fv, max_fv = result["min_fv"], result["max_fv"]

    rate_lbl = "Ke" if calc["is_fcfe"] else "WACC"

    header = [
        html.Td(f"{rate_lbl} \\ LTGR", style={**_LBL_B, "fontSize": "10px",
                                              "width": f"{SENS_W}px"}),
        html.Td("", style={"width": "14px"}),
    ]
    for i, off in enumerate(SENS_OFFSETS):
        header.append(html.Td(
            dbc.Input(
                id={"type": "dcf-sens-wacc", "offset": f"{off:.2f}"},
                type="text", value=wacc_texts[i], debounce=True, size="sm",
                style=_INPUT_SENS,
            ),
            style={"padding": "1px 2px"},
        ))

    trs = [html.Tr(header)]

    for r, off in enumerate(SENS_OFFSETS):
        cells = [
            html.Td(
                dbc.Input(
                    id={"type": "dcf-sens-ltgr", "offset": f"{off:.2f}"},
                    type="text", value=ltgr_texts[r], debounce=True, size="sm",
                    style=_INPUT_SENS,
                ),
                style={"padding": "1px 2px"},
            ),
            html.Td("", style={"width": "14px"}),
        ]
        for c in range(len(SENS_OFFSETS)):
            fv = grid.get((r, c))
            if fv is None:
                cells.append(html.Td("-", style={**_CELL, "width": f"{SENS_W}px"}))
                continue
            bold = (r, c) in (SENS_HIGH_COORD, SENS_LOW_COORD, SENS_CENTER_COORD)
            center = (r, c) == SENS_CENTER_COORD
            cells.append(html.Td(_fmt_currency(fv),
                                 style=_heat_style(fv, min_fv, max_fv, bold, center)))
        trs.append(html.Tr(cells))

    return html.Table(
        [html.Tbody(trs)],
        className="table table-sm table-dark mb-0",
        style={"width": "max-content", "borderCollapse": "separate",
               "borderSpacing": 0},
    ), result


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------

BRIDGE_LBL_W = 250
BRIDGE_VAL_W = 100


def _bridge_row(label, value_id, bold=False, emphasis=False):
    lstyle = {**(_LBL_B if bold else _LBL), "width": f"{BRIDGE_LBL_W}px",
              "display": "inline-block"}
    vstyle = {**(_CELL_B if bold else _CELL), "width": f"{BRIDGE_VAL_W}px",
              "display": "inline-block"}
    if emphasis:
        lstyle = {**lstyle, **_EMPHASIS}
        vstyle = {**vstyle, **_EMPHASIS}
    return html.Div([
        html.Span(label, id=f"{value_id}-label", style=lstyle),
        html.Span("-", id=value_id, style=vstyle),
    ], className="d-flex align-items-center", style={"padding": "1px 0"})


layout = dbc.Container([
    dbc.Card([
        dbc.CardBody([
            dbc.Row([
                dbc.Col(html.Div(id="dcf-title", className="fw-bold text-light"),
                        xs=12, md=True, className="d-flex align-items-center"),
                dbc.Col(dbc.Button("Projection Toggles", id="btn-dcf-toggles",
                                   color="info", size="sm", outline=True,
                                   className="py-1 px-2", n_clicks=0),
                        xs="auto"),
            ], className="align-items-center g-2"),
        ], className="py-1 px-2")
    ], color="dark", outline=True, className="mb-2 border-secondary"),

    dbc.Card([
        dbc.CardBody([
            html.Div(id="dcf-table-container",
                     style={"overflowX": "auto", "minWidth": 0}),
        ], className="p-2")
    ], color="secondary", outline=True, className="mb-2"),

    dbc.Row([
        dbc.Col(dbc.Card([
            dbc.CardBody([
                _bridge_row("Sum of Present Value of Free Cash Flows:", "dcf-sum-pv"),
                _bridge_row("Discounted Residual Value:", "dcf-disc-residual"),
                html.Div([
                    html.Span("Other Adjustment:",
                              style={**_LBL, "width": f"{BRIDGE_LBL_W}px",
                                     "display": "inline-block"}),
                    dbc.Input(id="dcf-bridge-other-adj", type="text", value="",
                              debounce=True, size="sm",
                              style={**_INPUT_SM, "width": f"{BRIDGE_VAL_W}px"}),
                ], className="d-flex align-items-center",
                   style={"padding": "1px 0"}),
                html.Div(style={"height": "8px"}),
                _bridge_row("Fair Value (Base):", "dcf-fv-base",
                            bold=True, emphasis=True),
                html.Div([
                    html.Span("", style={"width": f"{BRIDGE_LBL_W}px",
                                         "display": "inline-block"}),
                    html.Span("FV Low", style={**_LBL, "width": f"{BRIDGE_VAL_W}px",
                                               "display": "inline-block",
                                               "textAlign": "right"}),
                    html.Span("FV High", style={**_LBL, "width": f"{BRIDGE_VAL_W}px",
                                                "display": "inline-block",
                                                "textAlign": "right"}),
                ], className="d-flex", style={"padding": "1px 0"}),
                html.Div([
                    html.Span("", style={"width": f"{BRIDGE_LBL_W}px",
                                         "display": "inline-block"}),
                    html.Span("-", id="dcf-fv-low",
                              style={**_CELL_B, "width": f"{BRIDGE_VAL_W}px",
                                     "display": "inline-block"}),
                    html.Span("-", id="dcf-fv-high",
                              style={**_CELL_B, "width": f"{BRIDGE_VAL_W}px",
                                     "display": "inline-block"}),
                ], className="d-flex", style={"padding": "1px 0"}),
                html.Div(style={"height": "12px"}),
                html.Div(id="dcf-sens-header", className="fw-bold text-light",
                         style={"fontSize": "12px", "marginBottom": "4px"}),
                html.Div(id="dcf-sensitivity-container",
                         style={"overflowX": "auto", "minWidth": 0}),
            ], className="p-2")
        ], color="secondary", outline=True), lg=7, className="mb-2"),

        dbc.Col(dbc.Card([
            dbc.CardHeader(
                dbc.Row([
                    dbc.Col("Terminal Value", className="fw-bold text-light",
                            style={"paddingTop": "4px"}),
                    dbc.Col(
                        dbc.Button(
                            "Reverse-DCF →",
                            id="btn-dcf-reverse",
                            color="warning",
                            outline=True,
                            size="sm",
                            className="py-0 px-2",
                            n_clicks=0,
                        ),
                        xs="auto",
                    ),
                ], className="g-1 align-items-center"),
                className="py-1 px-2",
            ),
            dbc.CardBody([
                html.Div([
                    html.Span("Model:", style={**_LBL, "width": "120px",
                                               "display": "inline-block"}),
                    dbc.Select(id="dcf-tv-model",
                               options=[{"label": m, "value": m} for m in TV_MODELS],
                               value="Gordon Growth", size="sm",
                               style={**_SELECT, "width": "175px"}),
                ], className="d-flex align-items-center mb-1"),
                html.Div([
                    html.Span("Long Term Growth Rate:",
                              style={**_LBL, "width": "170px",
                                     "display": "inline-block"}),
                    dbc.Input(id="dcf-ltg-input", type="text", value="3.0%",
                              debounce=True, size="sm",
                              style={**_INPUT_SM, "width": "80px"}),
                ], className="d-flex align-items-center mb-1"),
                html.Div([
                    html.Span("Dep. as % of CapEx:",
                              style={**_LBL, "width": "170px",
                                     "display": "inline-block"}),
                    dbc.Input(id="dcf-capex-dep-pct", type="text", value="100.0%",
                              debounce=True, size="sm",
                              style={**_INPUT_SM, "width": "80px"}),
                ], className="d-flex align-items-center mb-2"),
                html.Hr(style={"borderColor": "#4a5568", "margin": "6px 0"}),
                html.Div(id="dcf-tv-panel"),
            ], className="p-2")
        ], color="secondary", outline=True), lg=5, className="mb-2"),
    ], className="g-2"),

    dbc.Modal([
        dbc.ModalHeader(dbc.ModalTitle("Projection Toggles")),
        dbc.ModalBody([
            dbc.Row([
                dbc.Col([dbc.Label("Years of Historicals:", className="small"),
                         dbc.Input(id="dcf-toggle-hist", type="number",
                                   min=0, max=5, step=1, size="sm")], md=6),
                dbc.Col([dbc.Label("Years of Projections:", className="small"),
                         dbc.Input(id="dcf-toggle-proj", type="number",
                                   min=1, max=20, step=1, size="sm")], md=6),
            ], className="g-2 mb-2"),
            dbc.Row([
                dbc.Col([dbc.Label("Cash Flows to:", className="small"),
                         dbc.Select(id="dcf-toggle-cf",
                                    options=[{"label": "FCFF", "value": "FCFF"},
                                             {"label": "FCFE", "value": "FCFE"}],
                                    size="sm")], md=6),
                dbc.Col([dbc.Label("NOLs?:", className="small"),
                         dbc.Select(id="dcf-toggle-nols",
                                    options=[{"label": "No", "value": "No"},
                                             {"label": "Yes", "value": "Yes"}],
                                    size="sm")], md=6),
            ], className="g-2 mb-2"),
            dbc.Row([
                dbc.Col([dbc.Label("Change in NWC provided by Mgmt:",
                                   className="small"),
                         dbc.Select(id="dcf-toggle-nwc",
                                    options=[{"label": "No", "value": "No"},
                                             {"label": "Yes", "value": "Yes"}],
                                    size="sm")], md=6),
                dbc.Col([dbc.Label("Valuation Approach:", className="small"),
                         dbc.Select(id="dcf-toggle-approach",
                                    options=[{"label": "DCF", "value": "DCF"},
                                             {"label": "LBO", "value": "LBO"}],
                                    size="sm")], md=6),
            ], className="g-2"),
            html.Small(
                "Cash Flows to is overridden by Home's Basis of Value unless "
                "that is set to \"BEV / Equity Value\".",
                className="text-muted d-block mt-2",
            ),
        ]),
        dbc.ModalFooter([
            dbc.Button("Cancel", id="btn-dcf-toggles-cancel",
                       color="secondary", size="sm", n_clicks=0),
            dbc.Button("OK", id="btn-dcf-toggles-ok",
                       color="primary", size="sm", n_clicks=0),
        ]),
    ], id="dcf-toggles-modal", is_open=False),
    reverse_dcf_modal.layout,
], fluid=True, className="px-2")


# ---------------------------------------------------------------------------
# Hydrate
# ---------------------------------------------------------------------------

@callback(
    Output("dcf-tv-model", "value"),
    Output("dcf-ltg-input", "value"),
    Output("dcf-capex-dep-pct", "value"),
    Output("dcf-bridge-other-adj", "value"),
    Input("_pages_location", "pathname"),
    Input("session-load-timestamp", "data"),
    State("session-store", "data"),
)
def hydrate_dcf(pathname, _ts, session_data):
    if pathname not in ("/dcf", "/dcf/"):
        return (no_update,) * 4
    s = _state_from_session(session_data)
    return s["tv_model"], s["ltg_input"], s["capex_dep_pct"], s["bridge_other_adj"]


# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------

@callback(
    Output("dcf-table-container", "children"),
    Output("dcf-tv-panel", "children"),
    Output("dcf-sensitivity-container", "children"),
    Output("dcf-sens-header", "children"),
    Output("dcf-title", "children"),
    Output("dcf-sum-pv", "children"),
    Output("dcf-disc-residual", "children"),
    Output("dcf-fv-base", "children"),
    Output("dcf-fv-base-label", "children"),
    Output("dcf-fv-low", "children"),
    Output("dcf-fv-high", "children"),
    Input("_pages_location", "pathname"),
    Input("session-store", "data"),
    Input("session-load-timestamp", "data"),
    Input("source-results-store", "data"),
    Input("dcf-tv-model", "value"),
    Input("dcf-ltg-input", "value"),
    Input("dcf-capex-dep-pct", "value"),
    Input("dcf-bridge-other-adj", "value"),
)
def render_dcf(pathname, session_data, _ts, source_results,
               tv_model, ltg_input, capex_dep_pct, bridge_other_adj):
    if pathname not in ("/dcf", "/dcf/"):
        return (no_update,) * 11

    state = _state_from_session(session_data)
    if tv_model in TV_MODELS:
        state["tv_model"] = tv_model
    if ltg_input is not None:
        state["ltg_input"] = ltg_input
    if capex_dep_pct is not None:
        state["capex_dep_pct"] = capex_dep_pct
    if bridge_other_adj is not None:
        state["bridge_other_adj"] = bridge_other_adj

    calc = _compute(session_data, source_results, state)
    inputs = calc["inputs"]

    sens_table, sens_result = _build_sensitivity(state, calc)
    rate_lbl = "Ke" if calc["is_fcfe"] else "WACC"

    fv_label = (
        "Fair Value of Equity (Base):" if calc["is_fcfe"]
        else "Fair Value of Business Enterprise (Base):"
    )

    title = (
        f"{inputs.client} · {inputs.subject_company_name} · "
        f"Income Approach — Discounted Cash Flow Method · "
        f"As of {inputs.valuation_date}"
    )

    return (
        _build_main_table(state, calc),
        _build_tv_panel(state, calc),
        sens_table,
        f"Sensitivity: Fair Value by {rate_lbl} / LTGR",
        title,
        _fmt_currency(calc["sum_pv_fcf"]),
        _fmt_currency(calc["pv_residual"]),
        _fmt_currency(calc["fv_base"]),
        fv_label,
        _fmt_currency(sens_result["low"]),
        _fmt_currency(sens_result["high"]),
    )


# ---------------------------------------------------------------------------
# Persist
# ---------------------------------------------------------------------------

@callback(
    Output("session-store", "data", allow_duplicate=True),
    Input("dcf-tv-model", "value"),
    Input("dcf-ltg-input", "value"),
    Input("dcf-capex-dep-pct", "value"),
    Input("dcf-bridge-other-adj", "value"),
    Input("dcf-residual-amortization", "value", allow_optional=True),
    Input({"type": "dcf-other-adj", "period": ALL}, "value"),
    Input({"type": "dcf-tv-input", "model": ALL, "key": ALL}, "value"),
    Input({"type": "dcf-sens-wacc", "offset": ALL}, "value"),
    Input({"type": "dcf-sens-ltgr", "offset": ALL}, "value"),
    State({"type": "dcf-other-adj", "period": ALL}, "id"),
    State({"type": "dcf-tv-input", "model": ALL, "key": ALL}, "id"),
    State({"type": "dcf-sens-wacc", "offset": ALL}, "id"),
    State({"type": "dcf-sens-ltgr", "offset": ALL}, "id"),
    State("session-store", "data"),
    State("source-results-store", "data"),
    prevent_initial_call=True,
)
def persist_dcf(tv_model, ltg_input, capex_dep_pct, bridge_other_adj,
                residual_amort, other_adj_vals, tv_vals, sens_w_vals, sens_l_vals,
                other_adj_ids, tv_ids, sens_w_ids, sens_l_ids,
                session_data, source_results):
    if not ctx.triggered_id:
        return no_update

    session_data = dict(session_data or {})
    prev = dict(session_data.get("dcf_page_state") or {})
    state = _state_from_session(session_data)

    other_adj = dict(state["other_adj_inputs"])
    for cid, val in zip(other_adj_ids or [], other_adj_vals or []):
        if isinstance(cid, dict) and cid.get("period"):
            other_adj[cid["period"]] = "" if val is None else str(val)

    tv_inputs = {m: dict(v) for m, v in state["tv_inputs"].items()}
    for cid, val in zip(tv_ids or [], tv_vals or []):
        if isinstance(cid, dict):
            m, k = cid.get("model"), cid.get("key")
            if m in tv_inputs and k:
                tv_inputs[m][k] = "" if val is None else str(val)

    # Only explicitly user-modified sensitivity headers become saved
    # overrides. Generated/default cells must remain auto-linked to the
    # current Ke/WACC and LTGR.
    sens_wacc = dict(state["sens_wacc"])
    sens_ltgr = dict(state["sens_ltgr"])

    new_state = {
        "ltg_input": ltg_input if ltg_input is not None else state["ltg_input"],
        "tv_model": tv_model if tv_model in TV_MODELS else state["tv_model"],
        "capex_dep_pct": capex_dep_pct if capex_dep_pct is not None else state["capex_dep_pct"],
        "cash_flows_to": state["cash_flows_to"],
        "bridge_other_adj": bridge_other_adj if bridge_other_adj is not None else state["bridge_other_adj"],
        "residual_amortization": residual_amort if residual_amort is not None else state["residual_amortization"],
        "other_adj_inputs": other_adj,
        "tv_inputs": tv_inputs,
        "sens_wacc": sens_wacc,
        "sens_ltgr": sens_ltgr,
        "sensitivity_override_version": 2,
        "nols": state["nols"],
        "nwc_by_mgmt": state["nwc_by_mgmt"],
        "valuation_approach": state["valuation_approach"],
    }

    calc = _compute(session_data, source_results, new_state)

    # A sensitivity grid is callback-generated. When the table remounts,
    # Dash supplies every default cell value again. Compare each visible
    # value with its current auto-generated value:
    #
    #   same as auto value -> do not save an override
    #   different          -> user intentionally overrode that cell
    #
    # This is the Dash equivalent of desktop's _sens_*_auto_text logic.
    triggered = ctx.triggered_id
    trigger_type = triggered.get("type") if isinstance(triggered, dict) else triggered

    if trigger_type == "dcf-sens-wacc" and sens_w_ids:
        manual_wacc = {}
        current_rate = calc["discount_rate"]
        if current_rate is not None:
            for cid, value in zip(sens_w_ids or [], sens_w_vals or []):
                if not isinstance(cid, dict):
                    continue
                offset_text = cid.get("offset")
                try:
                    offset = float(offset_text)
                except (TypeError, ValueError):
                    continue

                entered = parse_pct(value)
                auto_value = current_rate + offset

                # Blank restores automatic behavior. Numeric values equal
                # to the generated default are also automatic.
                if entered is None:
                    continue
                if abs(entered - auto_value) > 1e-10:
                    manual_wacc[str(offset_text)] = str(value)

        sens_wacc = manual_wacc
        new_state["sens_wacc"] = sens_wacc

    if trigger_type == "dcf-sens-ltgr" and sens_l_ids:
        manual_ltgr = {}
        current_ltgr = calc["ltgr"]
        if current_ltgr is not None:
            for cid, value in zip(sens_l_ids or [], sens_l_vals or []):
                if not isinstance(cid, dict):
                    continue
                offset_text = cid.get("offset")
                try:
                    offset = float(offset_text)
                except (TypeError, ValueError):
                    continue

                entered = parse_pct(value)
                auto_value = current_ltgr + offset

                if entered is None:
                    continue
                if abs(entered - auto_value) > 1e-10:
                    manual_ltgr[str(offset_text)] = str(value)

        sens_ltgr = manual_ltgr
        new_state["sens_ltgr"] = sens_ltgr

    new_state.update({
        "effective_cash_flows_to": calc["cash_flows_to"],
        "discount_rate": calc["discount_rate"],
        "sum_pv_fcf": calc["sum_pv_fcf"],
        "pv_residual": calc["pv_residual"],
        "fv_base": calc["fv_base"],
        "residual_revenue": calc["rows"]["revenue"].get("Residual"),
    })

    if new_state == prev:
        return no_update

    session_data["dcf_page_state"] = new_state
    return session_data


# ---------------------------------------------------------------------------
# Toggles modal
# ---------------------------------------------------------------------------

@callback(
    Output("dcf-toggles-modal", "is_open"),
    Output("dcf-toggle-hist", "value"),
    Output("dcf-toggle-proj", "value"),
    Output("dcf-toggle-cf", "value"),
    Output("dcf-toggle-nols", "value"),
    Output("dcf-toggle-nwc", "value"),
    Output("dcf-toggle-approach", "value"),
    Input("btn-dcf-toggles", "n_clicks"),
    Input("btn-dcf-toggles-cancel", "n_clicks"),
    Input("btn-dcf-toggles-ok", "n_clicks"),
    State("session-store", "data"),
    prevent_initial_call=True,
)
def toggle_dcf_modal(open_c, cancel_c, ok_c, session_data):
    trig = ctx.triggered_id
    if trig == "btn-dcf-toggles":
        inputs = dict_to_project_inputs(session_data or {})
        s = _state_from_session(session_data)
        return (True, inputs.historical_years, inputs.projection_years,
                s["cash_flows_to"], s["nols"], s["nwc_by_mgmt"],
                s["valuation_approach"])
    if trig in ("btn-dcf-toggles-cancel", "btn-dcf-toggles-ok"):
        return (False,) + (no_update,) * 6
    return (no_update,) * 7


@callback(
    Output("session-store", "data", allow_duplicate=True),
    Input("btn-dcf-toggles-ok", "n_clicks"),
    State("dcf-toggle-hist", "value"),
    State("dcf-toggle-proj", "value"),
    State("dcf-toggle-cf", "value"),
    State("dcf-toggle-nols", "value"),
    State("dcf-toggle-nwc", "value"),
    State("dcf-toggle-approach", "value"),
    State("session-store", "data"),
    prevent_initial_call=True,
)
def apply_dcf_toggles(n, hist_y, proj_y, cf, nols, nwc_mgmt, approach, session_data):
    if not n:
        return no_update

    session_data = dict(session_data or {})

    try:
        session_data["historical_years"] = max(0, min(5, int(hist_y)))
    except (TypeError, ValueError):
        pass
    try:
        session_data["projection_years"] = max(1, min(20, int(proj_y)))
    except (TypeError, ValueError):
        pass

    dcf_state = dict(session_data.get("dcf_page_state") or {})
    if cf in ("FCFF", "FCFE"):
        dcf_state["cash_flows_to"] = cf
    dcf_state["nols"] = nols or "No"
    dcf_state["nwc_by_mgmt"] = nwc_mgmt or "No"
    dcf_state["valuation_approach"] = approach or "DCF"
    session_data["dcf_page_state"] = dcf_state

    return session_data