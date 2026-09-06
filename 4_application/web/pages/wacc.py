"""
web/pages/wacc.py

Dash Weighted Average Cost of Capital page.

All math lives in Canneberge.Calculations.wacc — this file fetches
session values, renders, and persists.

State: session-store["wacc_page_state"], desktop-compatible shape plus
cached outputs DCF will read:

    beta_type / beta_frequency / capital_structure /
    selected_debt_tic / selected_relevered_beta /
    equity_risk_premium / size_premium / csrp /
    pretax_debt_series / excluded_rows      <- written by desktop too

    wacc_value / ke_value / after_tax_kd / we / wd
                                            <- web-only cache

Only the comp table re-renders. Every user input lives in the static
layout so typing never remounts the field you are in.
"""

from __future__ import annotations

from typing import Optional, List, Dict

import dash
import dash_bootstrap_components as dbc
from dash import html, Input, Output, State, callback, ctx, ALL, no_update

from Canneberge.Calculations.wacc import (
    BETA_TYPE_OPTIONS, BETA_FREQUENCY_OPTIONS, CAPITAL_STRUCTURE_OPTIONS,
    CAPITAL_STRUCTURE_HEADER_MAP, CORPORATE_RATE_SERIES,
    DATA_COLS, BETA_COLS, STAT_NAMES,
    parse_pct_input, to_float, fmt_beta, fmt_pct,
    comp_table, column_statistics,
    risk_free_rate, pretax_cost_of_debt,
    cost_of_equity, after_tax_cost_of_debt, wacc_summary,
)
from web.lib.session_io import dict_to_project_inputs

dash.register_page(__name__, path="/wacc", name="WACC")


# ---------------------------------------------------------------------------
# Geometry / style
# ---------------------------------------------------------------------------

W_EXCLUDE, W_NUM, W_TICKER, W_COMPANY, W_DATA = 62, 30, 70, 200, 132

_HDR = {
    "color": "#ffffff", "fontWeight": "bold", "fontSize": "11px",
    "padding": "4px 6px", "textAlign": "right", "whiteSpace": "normal",
    "verticalAlign": "bottom", "borderBottom": "1px solid #4a5568",
}
_HDR_L = {**_HDR, "textAlign": "left"}
_BAND = {
    "backgroundColor": "#2b3e50", "color": "white", "fontWeight": "bold",
    "fontSize": "11px", "padding": "3px 8px", "border": "1px solid #555",
}
_LBL = {"color": "#e6e6e6", "fontSize": "12px", "padding": "3px 6px",
        "whiteSpace": "nowrap"}
_LBL_B = {**_LBL, "fontWeight": "bold"}
_CELL = {"color": "#dddddd", "fontSize": "12px", "padding": "3px 6px",
         "textAlign": "right", "whiteSpace": "nowrap"}
_CELL_MUTED = {**_CELL, "color": "#6b7684"}
_CELL_B = {**_CELL, "fontWeight": "bold", "color": "#ffffff"}
_NOTE = {"color": "#8fbf9f", "fontStyle": "italic", "fontSize": "11px",
         "paddingLeft": "10px"}

_INPUT = {
    "backgroundColor": "#2a2a2a", "color": "#f5f5f5",
    "border": "1px solid #666", "fontSize": "12px", "textAlign": "right",
    "padding": "2px 4px", "height": "26px", "width": f"{W_DATA - 8}px",
}
_INPUT_SM = {**_INPUT, "width": "90px"}
_SELECT = {
    "backgroundColor": "#2a2a2a", "color": "#f5f5f5",
    "border": "1px solid #666", "fontSize": "12px",
    "height": "27px", "padding": "1px 6px",
}

LABEL_W = 280
VALUE_W = 90


def _colgroup(n_data: int = 6):
    return html.Colgroup([
        html.Col(style={"width": f"{W_EXCLUDE}px"}),
        html.Col(style={"width": f"{W_NUM}px"}),
        html.Col(style={"width": f"{W_TICKER}px"}),
        html.Col(style={"width": f"{W_COMPANY}px"}),
    ] + [html.Col(style={"width": f"{W_DATA}px"}) for _ in range(n_data)])


_TABLE_STYLE = {
    "tableLayout": "fixed", "width": "max-content", "minWidth": "100%",
    "borderCollapse": "separate", "borderSpacing": 0,
}


def _fmt_col(col: str, val: Optional[float]) -> str:
    return fmt_beta(val) if col in BETA_COLS else fmt_pct(val)


# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------

def _state_from_session(session_data: dict) -> dict:
    raw = (session_data or {}).get("wacc_page_state", {}) or {}

    def _opt(key, options, default):
        val = raw.get(key)
        return val if val in options else default

    return {
        "beta_type": _opt("beta_type", BETA_TYPE_OPTIONS, BETA_TYPE_OPTIONS[0]),
        "beta_frequency": _opt(
            "beta_frequency", BETA_FREQUENCY_OPTIONS, BETA_FREQUENCY_OPTIONS[0]
        ),
        "capital_structure": _opt(
            "capital_structure", CAPITAL_STRUCTURE_OPTIONS,
            CAPITAL_STRUCTURE_OPTIONS[0],
        ),
        "selected_debt_tic": raw.get("selected_debt_tic", ""),
        "selected_relevered_beta": raw.get("selected_relevered_beta", ""),
        "equity_risk_premium": raw.get("equity_risk_premium", ""),
        "size_premium": raw.get("size_premium", ""),
        "csrp": raw.get("csrp", ""),
        "pretax_debt_series": _opt(
            "pretax_debt_series", list(CORPORATE_RATE_SERIES.keys()),
            list(CORPORATE_RATE_SERIES.keys())[0],
        ),
        "excluded_rows": list(raw.get("excluded_rows") or []),
    }


def _exclusion_map(tickers: List[str], flags: list) -> Dict[str, bool]:
    return {
        t: (bool(flags[i]) if i < len(flags) else False)
        for i, t in enumerate(tickers)
    }


# ---------------------------------------------------------------------------
# Compute
# ---------------------------------------------------------------------------

def _compute(session_data: dict, source_results: dict, state: dict) -> dict:
    inputs = dict_to_project_inputs(session_data or {})
    tickers = list(inputs.gpc_tickers or [])

    sa = (source_results or {}).get("stockanalysis", {}) or {}
    beta_vol_rows = (source_results or {}).get("beta_vol", []) or []
    fred_rows = (source_results or {}).get("fred", []) or []

    selected_debt_tic = parse_pct_input(state["selected_debt_tic"])
    selected_tax_rate = getattr(inputs, "subject_tax_rate", None)

    rows = comp_table(
        tickers=tickers,
        beta_vol_rows=beta_vol_rows,
        bs_rows=sa.get("BS", []),
        ratio_rows=sa.get("Ratios", []),
        is_rows=sa.get("IS", []),
        beta_type=state["beta_type"],
        beta_frequency=state["beta_frequency"],
        capital_structure=state["capital_structure"],
        historical_period_columns=list(inputs.historical_period_columns),
        selected_debt_tic=selected_debt_tic,
        selected_tax_rate=selected_tax_rate,
        fallback_tax_rate=selected_tax_rate,
    )
    excluded = _exclusion_map(tickers, state["excluded_rows"])
    stats = column_statistics(rows, excluded)

    rf = risk_free_rate(fred_rows)
    be = to_float(state["selected_relevered_beta"])
    erp = parse_pct_input(state["equity_risk_premium"])
    sp = parse_pct_input(state["size_premium"])
    csrp = parse_pct_input(state["csrp"])
    ke_parts = cost_of_equity(rf, be, erp, sp, csrp)

    pretax_kd = pretax_cost_of_debt(fred_rows, state["pretax_debt_series"])
    kd = after_tax_cost_of_debt(pretax_kd, selected_tax_rate)

    summary = wacc_summary(
        selected_debt_tic, ke_parts["cost_of_equity"], kd
    )

    return {
        "inputs": inputs, "tickers": tickers,
        "rows": rows, "excluded": excluded, "stats": stats,
        "selected_debt_tic": selected_debt_tic,
        "selected_tax_rate": selected_tax_rate,
        "rf": rf, "be": be,
        "adjusted_erp": ke_parts["adjusted_erp"],
        "ke": ke_parts["cost_of_equity"],
        "pretax_kd": pretax_kd, "after_tax_kd": kd,
        **summary,
    }


# ---------------------------------------------------------------------------
# Comp table render
# ---------------------------------------------------------------------------

def _build_comp_table(state: dict, calc: dict):
    headers = [
        ("beta", "Observed Beta"),
        ("debt_equity", "Debt (Book) as a % of Equity"),
        ("debt_tic", CAPITAL_STRUCTURE_HEADER_MAP.get(
            state["capital_structure"], "Debt (Book) as a % of TIC")),
        ("tax_rate", "Effective Tax Rate"),
        ("unlevered_beta", "Unlevered Beta"),
        ("relevered_beta", "Re-Levered Beta"),
    ]

    trs = [html.Tr(
        [html.Th("Exclude", style=_HDR_L), html.Th("#", style=_HDR_L),
         html.Th("Ticker", style=_HDR_L), html.Th("Company Name", style=_HDR_L)]
        + [html.Th(label, style=_HDR) for _c, label in headers]
    )]

    for i, ticker in enumerate(calc["tickers"]):
        excluded = calc["excluded"].get(ticker, False)
        cs = _CELL_MUTED if excluded else _CELL
        ls = {**_LBL, "color": "#6b7684"} if excluded else _LBL
        metrics = calc["rows"].get(ticker, {})
        trs.append(html.Tr(
            [html.Td(
                dbc.Checkbox(
                    id={"type": "wacc-exclude", "slot": i},
                    value=excluded, className="m-0",
                ),
                style={"textAlign": "center", "padding": "2px"},
             ),
             html.Td(str(i + 1), style=ls),
             html.Td(ticker, style=ls),
             html.Td(
                 (calc["inputs"].gpc_company_names or {}).get(ticker.upper(), ""),
                 style={**ls, "overflow": "hidden", "textOverflow": "ellipsis"},
             )]
            + [html.Td(_fmt_col(c, metrics.get(c)), style=cs)
               for c, _label in headers]
        ))

    trs.append(html.Tr([html.Td("Statistics", colSpan=10, style=_BAND)]))

    for name in STAT_NAMES:
        by_col = calc["stats"].get(name, {})
        trs.append(html.Tr(
            [html.Td("", style=_LBL), html.Td("", style=_LBL),
             html.Td(name, colSpan=2, style=_LBL_B)]
            + [html.Td(_fmt_col(c, by_col.get(c)), style=_CELL_B)
               for c, _label in headers]
        ))

    return html.Table(
        [_colgroup(), html.Tbody(trs)],
        className="table table-sm table-dark mb-0",
        style=_TABLE_STYLE,
    )


# ---------------------------------------------------------------------------
# Static rows for the lower sections
# ---------------------------------------------------------------------------

def _kv_row(label: str, value_id: str, note: str = "", bold: bool = False):
    lstyle = {**(_LBL_B if bold else _LBL), "width": f"{LABEL_W}px",
              "display": "inline-block"}
    vstyle = {**(_CELL_B if bold else _CELL), "width": f"{VALUE_W}px",
              "display": "inline-block"}
    kids = [html.Span(label, style=lstyle),
            html.Span("-", id=value_id, style=vstyle)]
    if note:
        kids.append(html.Span(note, style=_NOTE))
    return html.Div(kids, className="d-flex align-items-center",
                    style={"padding": "1px 0"})


def _kv_input_row(label: str, input_id: str, placeholder: str, note: str = ""):
    kids = [
        html.Span(label, style={**_LBL, "width": f"{LABEL_W}px",
                                "display": "inline-block"}),
        dbc.Input(id=input_id, type="text", value="", placeholder=placeholder,
                  debounce=True, size="sm",
                  style={**_INPUT_SM, "width": f"{VALUE_W}px"}),
    ]
    if note:
        kids.append(html.Span(note, style=_NOTE))
    return html.Div(kids, className="d-flex align-items-center",
                    style={"padding": "1px 0"})


def _section(title: str):
    return html.Div(title, style={**_BAND, "marginTop": "10px",
                                  "marginBottom": "4px"})


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------

layout = dbc.Container([
    dbc.Card([
        dbc.CardBody([
            dbc.Row([
                dbc.Col(html.Div(id="wacc-title",
                                 className="fw-bold text-light"),
                        xs=12, md=True,
                        className="d-flex align-items-center"),
                dbc.Col(html.Div([
                    dbc.Label("Beta Type", className="me-1 mb-0 text-muted small"),
                    dbc.Select(id="wacc-beta-type",
                               options=[{"label": o, "value": o}
                                        for o in BETA_TYPE_OPTIONS],
                               value=BETA_TYPE_OPTIONS[0], size="sm",
                               style={**_SELECT, "width": "140px"}),
                ], className="d-flex align-items-center"), xs="auto"),
                dbc.Col(html.Div([
                    dbc.Label("Frequency", className="me-1 mb-0 text-muted small"),
                    dbc.Select(id="wacc-beta-frequency",
                               options=[{"label": o, "value": o}
                                        for o in BETA_FREQUENCY_OPTIONS],
                               value=BETA_FREQUENCY_OPTIONS[0], size="sm",
                               style={**_SELECT, "width": "150px"}),
                ], className="d-flex align-items-center"), xs="auto"),
                dbc.Col(html.Div([
                    dbc.Label("Capital Structure",
                              className="me-1 mb-0 text-muted small"),
                    dbc.Select(id="wacc-capital-structure",
                               options=[{"label": o, "value": o}
                                        for o in CAPITAL_STRUCTURE_OPTIONS],
                               value=CAPITAL_STRUCTURE_OPTIONS[0], size="sm",
                               style={**_SELECT, "width": "200px"}),
                ], className="d-flex align-items-center"), xs="auto"),
            ], className="align-items-center g-2"),
        ], className="py-1 px-2")
    ], color="dark", outline=True, className="mb-2 border-secondary"),

    # Comp table + Selected row share one scroll region so columns line up.
    dbc.Card([
        dbc.CardBody([
            html.Div([
                html.Div(id="wacc-comp-table"),
                html.Table([_colgroup(), html.Tbody([html.Tr([
                    html.Td("", style=_LBL),
                    html.Td("", style=_LBL),
                    html.Td("Selected", colSpan=2,
                            style={**_LBL_B, "borderTop": "1px solid #4a5568"}),
                    html.Td("", style={**_CELL, "borderTop": "1px solid #4a5568"}),
                    html.Td("", style={**_CELL, "borderTop": "1px solid #4a5568"}),
                    html.Td(dbc.Input(id="wacc-selected-debt-tic", type="text",
                                      value="", placeholder="e.g. 25.0%",
                                      debounce=True, size="sm", style=_INPUT),
                            style={"padding": "2px",
                                   "borderTop": "1px solid #4a5568"}),
                    html.Td("-", id="wacc-selected-tax-rate",
                            style={**_CELL_B, "borderTop": "1px solid #4a5568"}),
                    html.Td("", style={**_CELL, "borderTop": "1px solid #4a5568"}),
                    html.Td(dbc.Input(id="wacc-selected-relevered-beta",
                                      type="text", value="", placeholder="e.g. 1.25",
                                      debounce=True, size="sm", style=_INPUT),
                            style={"padding": "2px",
                                   "borderTop": "1px solid #4a5568"}),
                ])])], className="table table-sm table-dark mb-0",
                    style=_TABLE_STYLE),
            ], style={"overflowX": "auto", "minWidth": 0}),
        ], className="p-2")
    ], color="secondary", outline=True, className="mb-2"),

    dbc.Card([
        dbc.CardBody([
            _section("Cost of Equity (Ke) — MCAPM Method"),
            _kv_row("Risk-Free Rate (Rf)", "wacc-rf",
                    "The risk-free rate is based on the yield of 20-year "
                    "constant maturity U.S. Treasury bonds per FRED."),
            _kv_row("Re-Levered Beta (Be)", "wacc-be",
                    "Be = Ba x [ 1 + (Wd / We) x ( 1 - T) ]"),
            _kv_input_row("Equity Risk Premium (Rm - Rf)", "wacc-erp",
                          "e.g. 5.0%", "Kroll"),
            _kv_row("Adjusted Equity Risk Premium", "wacc-adjusted-erp",
                    "(Rm - Rf)"),
            _kv_input_row("Size Premium (SP)", "wacc-size-premium", "e.g. 0.0%"),
            _kv_input_row("Company Specific Risk Premium (CSRP)", "wacc-csrp",
                          "e.g. 5.0%",
                          "The company specific premium takes into account "
                          "company-specific risks including the uncertainty of "
                          "achieving the financial projections."),
            _kv_row("Cost of Equity", "wacc-ke",
                    "Ke = Rf + Be (Rm - Rf) + SP + CSRP", bold=True),

            _section("After-Tax Cost of Debt (Kd)"),
            html.Div([
                html.Span("Pre-Tax Cost of Debt",
                          style={**_LBL, "width": f"{LABEL_W}px",
                                 "display": "inline-block"}),
                html.Span("-", id="wacc-pretax-kd",
                          style={**_CELL, "width": f"{VALUE_W}px",
                                 "display": "inline-block"}),
                dbc.Select(id="wacc-pretax-debt-series",
                           options=[{"label": k, "value": k}
                                    for k in CORPORATE_RATE_SERIES],
                           value=list(CORPORATE_RATE_SERIES)[0], size="sm",
                           style={**_SELECT, "width": "240px",
                                  "marginLeft": "8px"}),
            ], className="d-flex align-items-center",
               style={"padding": "1px 0"}),
            _kv_row("Tax Rate (T)", "wacc-tax-rate-kd"),
            _kv_row("After-Tax Cost of Debt", "wacc-after-tax-kd",
                    "Kd = Kd (1 - T)", bold=True),

            _section("Weighted Average Cost of Capital"),
            _kv_row("Equity % of Capital (We)", "wacc-we"),
            _kv_row("Cost of Equity (Ke)", "wacc-ke-ref"),
            _kv_row("Weighted Cost of Equity", "wacc-weighted-ke"),
            html.Div(style={"height": "8px"}),
            _kv_row("Debt % of Capital (Wd)", "wacc-wd"),
            _kv_row("Cost of Debt (Kd)", "wacc-kd-ref"),
            _kv_row("Weighted Cost of Debt", "wacc-weighted-kd"),
            html.Hr(style={"borderColor": "#4a5568", "margin": "6px 0"}),
            _kv_row("WACC", "wacc-final", bold=True),
        ], className="p-2")
    ], color="secondary", outline=True, className="mb-2"),
], fluid=True, className="px-2")


# ---------------------------------------------------------------------------
# Hydrate static controls
# ---------------------------------------------------------------------------

@callback(
    Output("wacc-beta-type", "value"),
    Output("wacc-beta-frequency", "value"),
    Output("wacc-capital-structure", "value"),
    Output("wacc-selected-debt-tic", "value"),
    Output("wacc-selected-relevered-beta", "value"),
    Output("wacc-erp", "value"),
    Output("wacc-size-premium", "value"),
    Output("wacc-csrp", "value"),
    Output("wacc-pretax-debt-series", "value"),
    Input("_pages_location", "pathname"),
    Input("session-load-timestamp", "data"),
    State("session-store", "data"),
)
def hydrate_wacc_controls(pathname, _load_ts, session_data):
    if pathname not in ("/wacc", "/wacc/"):
        return (no_update,) * 9
    s = _state_from_session(session_data)
    return (
        s["beta_type"], s["beta_frequency"], s["capital_structure"],
        s["selected_debt_tic"], s["selected_relevered_beta"],
        s["equity_risk_premium"], s["size_premium"], s["csrp"],
        s["pretax_debt_series"],
    )


# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------

@callback(
    Output("wacc-comp-table", "children"),
    Output("wacc-title", "children"),
    Output("wacc-selected-tax-rate", "children"),
    Output("wacc-rf", "children"),
    Output("wacc-be", "children"),
    Output("wacc-adjusted-erp", "children"),
    Output("wacc-ke", "children"),
    Output("wacc-pretax-kd", "children"),
    Output("wacc-tax-rate-kd", "children"),
    Output("wacc-after-tax-kd", "children"),
    Output("wacc-we", "children"),
    Output("wacc-ke-ref", "children"),
    Output("wacc-weighted-ke", "children"),
    Output("wacc-wd", "children"),
    Output("wacc-kd-ref", "children"),
    Output("wacc-weighted-kd", "children"),
    Output("wacc-final", "children"),
    Input("_pages_location", "pathname"),
    Input("session-store", "data"),
    Input("session-load-timestamp", "data"),
    Input("source-results-store", "data"),
)
def render_wacc(pathname, session_data, _load_ts, source_results):
    if pathname not in ("/wacc", "/wacc/"):
        return (no_update,) * 17

    state = _state_from_session(session_data)
    calc = _compute(session_data, source_results, state)
    inputs = calc["inputs"]

    title = (
        f"{inputs.client} · {inputs.subject_company_name} · "
        f"Weighted Average Cost of Capital · As of {inputs.valuation_date}"
    )
    wacc = calc["wacc"]

    return (
        _build_comp_table(state, calc),
        title,
        fmt_pct(calc["selected_tax_rate"]),
        fmt_pct(calc["rf"]),
        fmt_beta(calc["be"]),
        fmt_pct(calc["adjusted_erp"]),
        fmt_pct(calc["ke"]),
        fmt_pct(calc["pretax_kd"]),
        fmt_pct(calc["selected_tax_rate"]),
        fmt_pct(calc["after_tax_kd"]),
        fmt_pct(calc["we"]),
        fmt_pct(calc["ke"]),
        fmt_pct(calc["weighted_cost_of_equity"]),
        fmt_pct(calc["wd"]),
        fmt_pct(calc["after_tax_kd"]),
        fmt_pct(calc["weighted_cost_of_debt"]),
        f"{wacc * 100:.2f}%" if wacc is not None else "NA",
    )


# ---------------------------------------------------------------------------
# Persist
# ---------------------------------------------------------------------------

@callback(
    Output("session-store", "data", allow_duplicate=True),
    Input("wacc-beta-type", "value"),
    Input("wacc-beta-frequency", "value"),
    Input("wacc-capital-structure", "value"),
    Input("wacc-selected-debt-tic", "value"),
    Input("wacc-selected-relevered-beta", "value"),
    Input("wacc-erp", "value"),
    Input("wacc-size-premium", "value"),
    Input("wacc-csrp", "value"),
    Input("wacc-pretax-debt-series", "value"),
    Input({"type": "wacc-exclude", "slot": ALL}, "value"),
    State({"type": "wacc-exclude", "slot": ALL}, "id"),
    State("session-store", "data"),
    State("source-results-store", "data"),
    prevent_initial_call=True,
)
def persist_wacc(beta_type, beta_frequency, capital_structure,
                 selected_debt_tic, selected_relevered_beta,
                 erp, size_premium, csrp, pretax_debt_series,
                 exclude_values, exclude_ids, session_data, source_results):
    if not ctx.triggered_id:
        return no_update

    session_data = dict(session_data or {})
    prev = dict(session_data.get("wacc_page_state") or {})
    state = _state_from_session(session_data)

    tickers = list(dict_to_project_inputs(session_data).gpc_tickers or [])
    exclusions = list(state["excluded_rows"])
    while len(exclusions) < len(tickers):
        exclusions.append(False)
    for cell_id, val in zip(exclude_ids or [], exclude_values or []):
        if not isinstance(cell_id, dict):
            continue
        try:
            slot = int(cell_id.get("slot"))
        except (TypeError, ValueError):
            continue
        while len(exclusions) <= slot:
            exclusions.append(False)
        exclusions[slot] = bool(val)

    def _keep(new, key):
        return new if new is not None else state[key]

    new_state = {
        "beta_type": _keep(beta_type, "beta_type"),
        "beta_frequency": _keep(beta_frequency, "beta_frequency"),
        "capital_structure": _keep(capital_structure, "capital_structure"),
        "selected_debt_tic": _keep(selected_debt_tic, "selected_debt_tic"),
        "selected_relevered_beta": _keep(
            selected_relevered_beta, "selected_relevered_beta"
        ),
        "equity_risk_premium": _keep(erp, "equity_risk_premium"),
        "size_premium": _keep(size_premium, "size_premium"),
        "csrp": _keep(csrp, "csrp"),
        "pretax_debt_series": _keep(pretax_debt_series, "pretax_debt_series"),
        "excluded_rows": exclusions,
    }

    # Cache outputs so DCF reads rather than recomputes. wacc_value is
    # the ROUNDED figure, matching desktop's WACCPage.wacc_value.
    calc = _compute(session_data, source_results, new_state)
    new_state.update({
        "wacc_value": calc["wacc"],
        "ke_value": calc["ke"],
        "after_tax_kd": calc["after_tax_kd"],
        "we": calc["we"],
        "wd": calc["wd"],
    })

    if new_state == prev:
        return no_update

    session_data["wacc_page_state"] = new_state
    return session_data