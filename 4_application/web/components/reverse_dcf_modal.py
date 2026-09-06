"""
web/components/reverse_dcf_modal.py

Reverse-DCF dashboard. Solver math lives in:
    Canneberge.Calculations.reverse_dcf
    Canneberge.Calculations.chart_helper

This module only assembles per-ticker inputs the same way desktop
MainWindow._get_reverse_dcf_inputs does, then renders the dialog.

Each comparable uses its OWN observed beta (WACC Beta Type × Frequency),
not the subject's re-levered beta. ERP comes from WACC page state.
NWC is always the excluding-cash (DFCFNWC) convention.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

import dash_bootstrap_components as dbc
import plotly.graph_objects as go
from dash import dcc, html, Input, Output, State, callback, ctx, ALL, no_update

from Canneberge.Calculations.reverse_dcf import (
    extract_ticker_inputs,
    compute_cost_of_equity,
    build_fcfe_schedule,
    compute_reconciliation_a,
    solve_gordon_growth_ltgr,
    solve_h_model,
    compute_ttm_fcfe,
)
from Canneberge.Calculations.chart_helper import (
    compute_gpc_chart_data,
    compute_indexed_summary_stats,
)
from Canneberge.Calculations.wacc import BETA_COLUMN_MAP, parse_pct_input, to_float
from web.lib.session_io import dict_to_project_inputs
from web.lib.wacc_data import wacc_state_from_session


CHART_BG = "#1e1e1e"
CHART_GRID = "#3a4553"
CHART_TEXT = "#e6e6e6"
CHART_AXIS = "#9fb3c8"
CHART_BAR = "#7c68af"
CHART_LINE = "#e5c07b"
CHART_SUBJECT = "#e5c07b"
CHART_FILL = "#4a90d9"

_LINE_KEYS = ["Subject", "Max", "Q3", "Average", "Median", "Q1", "Min"]
_DEFAULT_LINES = {
    "Subject": True, "Max": False, "Q3": True, "Average": False,
    "Median": True, "Q1": True, "Min": False,
}
_STAT_STYLE = {
    "Max":     {"color": "#6b7684", "width": 1.2},
    "Q3":      {"color": "#9fb3c8", "width": 1.5},
    "Average": {"color": "#4a90d9", "width": 1.5},
    "Median":  {"color": "#e6e6e6", "width": 2.0},
    "Q1":      {"color": "#9fb3c8", "width": 1.5},
    "Min":     {"color": "#6b7684", "width": 1.2},
}

_LBL = {"color": "#e6e6e6", "fontSize": "12px", "padding": "2px 6px"}
_LBL_B = {**_LBL, "fontWeight": "bold"}
_CELL = {"color": "#dddddd", "fontSize": "12px", "padding": "2px 6px",
         "textAlign": "right", "whiteSpace": "nowrap"}
_CELL_B = {**_CELL, "fontWeight": "bold", "color": "#ffffff"}
_HDR = {**_CELL, "fontWeight": "bold", "color": "#ffffff",
        "borderBottom": "1px solid #4a5568"}
_NOTE = {"color": "#8fbf9f", "fontSize": "11px", "fontStyle": "italic"}
_INPUT = {
    "backgroundColor": "#2a2a2a", "color": "#f5f5f5",
    "border": "1px solid #666", "fontSize": "12px", "textAlign": "right",
    "height": "26px", "width": "90px", "padding": "2px 4px",
}
_SELECT = {
    "backgroundColor": "#2a2a2a", "color": "#f5f5f5",
    "border": "1px solid #666", "fontSize": "12px", "height": "27px",
}


def _fmt_currency2(v: Optional[float]) -> str:
    if v is None:
        return "-"
    try:
        return f"{v:,.2f}"
    except (TypeError, ValueError):
        return "-"


def _fmt_pct2(v: Optional[float]) -> str:
    if v is None:
        return "-"
    try:
        return f"{v * 100:.2f}%"
    except (TypeError, ValueError):
        return "-"


def _parse_pct_field(text) -> Optional[float]:
    """Desktop Reverse-DCF rule: '%' or |v|>1 → divide by 100."""
    if text is None:
        return None
    t = str(text).strip().replace(",", "")
    if not t:
        return None
    has_pct = "%" in t
    t = t.replace("%", "").strip()
    try:
        v = float(t)
    except (TypeError, ValueError):
        return None
    if has_pct or abs(v) > 1.0:
        return v / 100.0
    return v


def _rdcf_state(session_data: dict) -> dict:
    raw = ((session_data or {}).get("dcf_page_state") or {}).get("reverse_dcf_state") or {}
    visible = dict(_DEFAULT_LINES)
    visible.update(raw.get("visible_lines") or {})
    return {
        "ticker": raw.get("ticker") or "",
        "chart_metric": raw.get("chart_metric") or "Revenue",
        "index_chart_metric": raw.get("index_chart_metric") or "Revenue",
        "solve_for": raw.get("solve_for") or "H",
        "ga": raw.get("ga") or "15.00%",
        "gn": raw.get("gn") or "3.00%",
        "h": raw.get("h") or "6.00",
        "terminal_capex_equals_depr": bool(raw.get("terminal_capex_equals_depr", True)),
        "excluded_tickers": list(raw.get("excluded_tickers") or []),
        "visible_lines": visible,
    }


def _ticker_universe(session_data: dict) -> tuple[List[str], str]:
    inputs = dict_to_project_inputs(session_data or {})
    subject = (inputs.subject_ticker or "").strip().upper()
    gpc = [(t or "").strip().upper() for t in (inputs.gpc_tickers or [])]
    tickers: List[str] = []
    if subject:
        tickers.append(subject)
    for t in gpc:
        if t and t not in tickers:
            tickers.append(t)
    return tickers, subject


def _build_all_inputs(session_data: dict, source_results: dict) -> tuple[Dict[str, dict], str]:
    """Same assembly as desktop MainWindow._get_reverse_dcf_inputs."""
    tickers, subject = _ticker_universe(session_data)
    wacc_state = wacc_state_from_session(session_data)

    sa = (source_results or {}).get("stockanalysis", {}) or {}
    ms_rows = (source_results or {}).get("marketscreener", []) or []
    fred_rows = (source_results or {}).get("fred", []) or []
    beta_vol = (source_results or {}).get("beta_vol", []) or []

    beta_col = BETA_COLUMN_MAP.get(
        (wacc_state["beta_type"], wacc_state["beta_frequency"])
    )
    beta_lookup: Dict[str, dict] = {}
    for row in beta_vol:
        t = str(row.get("Ticker", "")).strip().upper()
        if t:
            beta_lookup[t] = row

    erp_val = parse_pct_input(wacc_state["equity_risk_premium"])

    all_inputs: Dict[str, dict] = {}
    for ticker in tickers:
        observed = (
            to_float(beta_lookup.get(ticker, {}).get(beta_col))
            if beta_col else None
        )
        try:
            inp = extract_ticker_inputs(
                ticker=ticker,
                sa_results=sa,
                ms_rows=ms_rows,
                fred_rows=fred_rows,
                wacc_beta_val=observed,
                erp_val=erp_val,
                nwc_exclude_cash=True,
            )
            if inp:
                all_inputs[ticker] = inp
        except Exception as exc:
            all_inputs[ticker] = {"ticker": ticker, "_error": str(exc)}
    return all_inputs, subject


def _empty_fig(message: str = "No data") -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(
        text=message, xref="paper", yref="paper", x=0.5, y=0.5,
        showarrow=False, font=dict(color=CHART_AXIS, size=12),
    )
    fig.update_layout(
        paper_bgcolor=CHART_BG, plot_bgcolor=CHART_BG,
        xaxis=dict(visible=False), yaxis=dict(visible=False),
        margin=dict(l=20, r=20, t=30, b=20), height=260,
    )
    return fig


def _combo_figure(chart_data: dict, metric: str, ticker: str) -> go.Figure:
    labels = ["NFY", "NFY+1", "NFY+2", "Perp"]
    bars = (chart_data.get("bars") or {}).get(metric, [None] * 4)
    growth = (chart_data.get("growth") or {}).get(metric, [None] * 4)
    bar_vals = [v if v is not None else 0 for v in bars]
    growth_pct = [None if v is None else v * 100 for v in growth]

    fig = go.Figure()
    fig.add_bar(
        x=labels, y=bar_vals, name=metric, marker_color=CHART_BAR,
        yaxis="y",
    )
    fig.add_scatter(
        x=labels, y=growth_pct, name=f"{metric} Growth %",
        mode="lines+markers", line=dict(color=CHART_LINE, width=2),
        marker=dict(size=7), yaxis="y2", connectgaps=False,
    )
    fig.update_layout(
        title=dict(text=f"{ticker} — {metric} & Growth",
                   font=dict(color=CHART_TEXT, size=13)),
        paper_bgcolor=CHART_BG, plot_bgcolor=CHART_BG,
        font=dict(color=CHART_AXIS, size=11),
        margin=dict(l=50, r=50, t=40, b=30), height=280,
        legend=dict(orientation="h", y=1.12, x=0,
                    bgcolor="rgba(0,0,0,0)", font=dict(size=10)),
        xaxis=dict(gridcolor=CHART_GRID, zerolinecolor=CHART_GRID),
        yaxis=dict(title=metric, gridcolor=CHART_GRID,
                   zerolinecolor=CHART_GRID, tickformat=",.0f"),
        yaxis2=dict(title=f"{metric} Growth %", overlaying="y", side="right",
                    showgrid=False, ticksuffix="%"),
    )
    return fig


def _hmodel_figure(
    all_inputs: Dict[str, dict],
    excluded: Set[str],
    subject: str,
    solve_for: str,
    ga: Optional[float],
    gn: Optional[float],
    h_val: Optional[float],
) -> go.Figure:
    labels, values, colors = [], [], []
    for ticker, inp in all_inputs.items():
        if inp.get("_error") or ticker in excluded:
            continue
        try:
            chart_data = compute_gpc_chart_data(inp)
            ke = chart_data.get("ke")
            sched = chart_data.get("fcfe_schedule")
            fcfe_n = sched[-1]["fcfe"] if sched else None
            a = compute_reconciliation_a(inp.get("market_cap"), sched, ke)
            h_res = solve_h_model(
                a, ke, fcfe_n,
                ga=ga, gn=gn, h=h_val,
                solve_for=solve_for,
                full_fade_convention=True,
            )
        except Exception:
            continue
        if h_res.get("value") is None:
            continue
        labels.append(ticker)
        values.append(h_res["value"])
        colors.append(
            CHART_SUBJECT if ticker.upper() == subject.upper() else CHART_FILL
        )

    if not labels:
        return _empty_fig("No valid H-Model results")

    is_pct = solve_for in ("Ga", "Gn")
    text = [
        f"{v * 100:.2f}%" if is_pct else f"{v:.2f}"
        for v in values
    ]
    fig = go.Figure(go.Bar(
        x=values, y=labels, orientation="h",
        marker_color=colors, text=text, textposition="outside",
    ))
    fig.update_layout(
        title=dict(text=f"H-Model: Solved {solve_for} per GPC",
                   font=dict(color=CHART_TEXT, size=13)),
        paper_bgcolor=CHART_BG, plot_bgcolor=CHART_BG,
        font=dict(color=CHART_AXIS, size=11),
        margin=dict(l=70, r=60, t=40, b=30), height=280,
        xaxis=dict(
            gridcolor=CHART_GRID, zerolinecolor=CHART_GRID,
            ticksuffix="%" if is_pct else "",
            tickformat=".1%" if is_pct else None,
        ),
        yaxis=dict(autorange="reversed", gridcolor=CHART_GRID),
    )
    return fig


def _index_figure(
    all_inputs: Dict[str, dict],
    excluded: Set[str],
    subject: str,
    metric: str,
    visible: Dict[str, bool],
) -> go.Figure:
    result = compute_indexed_summary_stats(
        all_inputs=all_inputs,
        metric=metric,
        excluded_tickers=excluded,
        subject_ticker=subject,
    )
    x_labels = result["x_labels"]
    stats = result["stats"]
    subject_series = result["subject"]

    fig = go.Figure()

    def add_two_segment(y_vals, color, width, name):
        if not y_vals:
            return
        solid_x, solid_y = [], []
        for i in range(min(4, len(y_vals))):
            if y_vals[i] is not None:
                solid_x.append(x_labels[i])
                solid_y.append(y_vals[i])
        if solid_x:
            fig.add_scatter(
                x=solid_x, y=solid_y, mode="lines+markers",
                name=name, line=dict(color=color, width=width, dash="solid"),
                marker=dict(size=6),
            )
        if (
            len(y_vals) >= 5
            and y_vals[3] is not None
            and y_vals[4] is not None
        ):
            fig.add_scatter(
                x=[x_labels[3], x_labels[4]],
                y=[y_vals[3], y_vals[4]],
                mode="lines+markers",
                name=name,
                line=dict(color=color, width=width, dash="dash"),
                marker=dict(size=6),
                showlegend=False,
            )

    stat_map = {
        "Max": "max", "Q3": "q3", "Average": "mean",
        "Median": "median", "Q1": "q1", "Min": "min",
    }
    for name, key in stat_map.items():
        if not visible.get(name):
            continue
        style = _STAT_STYLE[name]
        add_two_segment(stats.get(key, []), style["color"], style["width"], name)

    if visible.get("Subject") and subject_series is not None:
        add_two_segment(
            subject_series, CHART_SUBJECT, 2.5, subject or "Subject"
        )

    fig.add_hline(y=100, line=dict(color=CHART_GRID, width=0.8, dash="dot"))
    fig.update_layout(
        title=dict(
            text=f"GPC Indexed {metric} Forecast Range (TTM = 100)",
            font=dict(color=CHART_TEXT, size=13),
        ),
        paper_bgcolor=CHART_BG, plot_bgcolor=CHART_BG,
        font=dict(color=CHART_AXIS, size=11),
        margin=dict(l=50, r=20, t=40, b=30), height=320,
        legend=dict(orientation="h", y=1.12, x=0,
                    bgcolor="rgba(0,0,0,0)", font=dict(size=10)),
        xaxis=dict(gridcolor=CHART_GRID, categoryorder="array",
                   categoryarray=x_labels),
        yaxis=dict(title="Indexed (TTM = 100)", gridcolor=CHART_GRID,
                   zerolinecolor=CHART_GRID),
    )
    return fig


def _bridge_table(inp: dict, force_term_capex: bool) -> html.Table:
    revenue = inp.get("revenue") or {}
    net_income = inp.get("net_income") or {}
    depr_pct = inp.get("depr_pct")
    capex_pct = inp.get("capex_pct")
    nwc_pct = inp.get("nwc_pct")

    rev = {
        "TTM": revenue.get("TTM") or revenue.get("LFY"),
        "NFY": revenue.get("NFY"),
        "NFY+1": revenue.get("NFY+1"),
        "NFY+2": revenue.get("NFY+2"),
    }
    ni = {
        "TTM": net_income.get("TTM"),
        "NFY": net_income.get("NFY"),
        "NFY+1": net_income.get("NFY+1"),
        "NFY+2": net_income.get("NFY+2"),
    }

    schedule = build_fcfe_schedule(
        revenue_prior=rev["TTM"],
        revenue_explicit=[rev["NFY"], rev["NFY+1"], rev["NFY+2"]],
        net_income_explicit=[ni["NFY"], ni["NFY+1"], ni["NFY+2"]],
        depr_pct=depr_pct,
        capex_pct=capex_pct,
        nwc_pct=nwc_pct,
        force_terminal_capex_equals_da=force_term_capex,
    ) or []

    ke = compute_cost_of_equity(
        inp.get("risk_free_rate"),
        inp.get("relevered_beta"),
        inp.get("equity_risk_premium"),
    )

    cols = ["TTM", "NFY", "NFY+1", "NFY+2"]
    dep = {
        c: (rev[c] * depr_pct if rev[c] is not None and depr_pct is not None else None)
        for c in cols
    }
    cap = {
        c: (rev[c] * capex_pct if rev[c] is not None and capex_pct is not None else None)
        for c in cols
    }
    if schedule and force_term_capex and schedule[-1].get("capex") is not None:
        cap["NFY+2"] = schedule[-1]["capex"]

    dnwc = {"TTM": 0.0, "NFY": None, "NFY+1": None, "NFY+2": None}
    fcfe = {
        "TTM": compute_ttm_fcfe(ni["TTM"], rev["TTM"], depr_pct, capex_pct),
        "NFY": None, "NFY+1": None, "NFY+2": None,
    }
    pv = {"TTM": None, "NFY": None, "NFY+1": None, "NFY+2": None}
    for yr, col in zip(schedule, ["NFY", "NFY+1", "NFY+2"]):
        dnwc[col] = yr.get("delta_nwc")
        fcfe[col] = yr.get("fcfe")
        if ke is not None and yr.get("fcfe") is not None:
            pv[col] = yr["fcfe"] / ((1 + ke) ** yr["year_index"])

    def cells(mapping, bold=False):
        st = _CELL_B if bold else _CELL
        return [html.Td(_fmt_currency2(mapping[c]), style=st) for c in cols]

    rows = [
        html.Tr([html.Td("", style=_LBL_B)]
                + [html.Td(c, style=_HDR) for c in cols]),
        html.Tr([html.Td("Revenue", style=_LBL_B)] + cells(rev, True)),
        html.Tr([html.Td("Net Income", style=_LBL)] + cells(ni)),
        html.Tr([html.Td("Depreciation", style=_LBL)] + cells(dep)),
        html.Tr([html.Td("CapEx", style=_LBL)] + cells(cap)),
        html.Tr([html.Td("ΔNWC", style=_LBL)] + cells(dnwc)),
        html.Tr([html.Td("FCFE", style=_LBL_B)] + cells(fcfe, True)),
        html.Tr(
            [html.Td("PV(FCFE)", style=_LBL)]
            + [html.Td("-" if c == "TTM" else _fmt_currency2(pv[c]), style=_CELL)
               for c in cols]
        ),
    ]
    return html.Table(
        [html.Tbody(rows)],
        className="table table-sm table-dark mb-0",
        style={"width": "100%", "borderCollapse": "separate", "borderSpacing": 0},
    )


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------

layout = dbc.Modal(
    [
        dbc.ModalHeader(
            dbc.ModalTitle("Reverse-DCF — Market-Implied Growth"),
            close_button=True,
        ),
        dbc.ModalBody([
            dbc.Row([
                dbc.Col([
                    html.Div([
                        html.Span("Ticker:", className="me-2 text-light"),
                        dbc.Select(id="rdcf-ticker", options=[], value="",
                                   size="sm", style={**_SELECT, "width": "140px"}),
                    ], className="d-flex align-items-center mb-2"),
                    html.Div([
                        html.Span("Market Cap:",
                                  style={**_LBL, "width": "110px",
                                         "display": "inline-block"}),
                        html.Span("-", id="rdcf-market-cap", style=_LBL_B),
                    ]),
                    html.Div([
                        html.Span("Ke:",
                                  style={**_LBL, "width": "110px",
                                         "display": "inline-block"}),
                        html.Span("-", id="rdcf-ke", style=_LBL_B),
                    ], className="mb-2"),
                    html.Div(id="rdcf-bridge"),
                    html.Div([
                        html.Span("Gordon Implied LTGR:", className="me-2 text-light"),
                        html.Span("-", id="rdcf-gordon", style=_LBL_B),
                    ], className="mt-2 mb-2"),
                    html.Div([
                        html.Div([
                            html.Span("Solve for:", className="me-2 text-light"),
                            dbc.Select(
                                id="rdcf-solve-for",
                                options=[{"label": x, "value": x}
                                         for x in ("H", "Ga", "Gn")],
                                value="H", size="sm",
                                style={**_SELECT, "width": "80px"},
                            ),
                            dbc.Checkbox(
                                id="rdcf-term-capex",
                                label="Terminal CapEx = Depr",
                                value=True,
                                className="ms-3 text-light",
                            ),
                        ], className="d-flex align-items-center mb-2"),
                        html.Div([
                            html.Span("Ga (ST Growth):",
                                      style={**_LBL, "width": "130px",
                                             "display": "inline-block"}),
                            dbc.Input(id="rdcf-ga", type="text", value="15.00%",
                                      debounce=True, size="sm", style=_INPUT),
                        ], className="d-flex align-items-center mb-1"),
                        html.Div([
                            html.Span("Gn (LT Growth):",
                                      style={**_LBL, "width": "130px",
                                             "display": "inline-block"}),
                            dbc.Input(id="rdcf-gn", type="text", value="3.00%",
                                      debounce=True, size="sm", style=_INPUT),
                        ], className="d-flex align-items-center mb-1"),
                        html.Div([
                            html.Span("H (Years):",
                                      style={**_LBL, "width": "130px",
                                             "display": "inline-block"}),
                            dbc.Input(id="rdcf-h", type="text", value="6.00",
                                      debounce=True, size="sm", style=_INPUT),
                        ], className="d-flex align-items-center mb-1"),
                        html.Div(id="rdcf-h-result", className="fw-bold text-light mt-1"),
                    ], style={"border": "1px solid #4a5568", "borderRadius": "4px",
                              "padding": "8px", "marginBottom": "8px"}),
                    html.Div(id="rdcf-status", style=_NOTE),
                    dcc.Graph(id="rdcf-hmodel-chart",
                              config={"displayModeBar": False},
                              style={"height": "280px"}),
                ], lg=5),
                dbc.Col([
                    html.Div([
                        html.Span("Chart Metric:", className="me-2 text-light"),
                        dbc.Select(
                            id="rdcf-chart-metric",
                            options=[{"label": m, "value": m}
                                     for m in ("Revenue", "Net Income", "FCFE")],
                            value="Revenue", size="sm",
                            style={**_SELECT, "width": "140px"},
                        ),
                    ], className="d-flex align-items-center mb-1"),
                    dcc.Graph(id="rdcf-combo-chart",
                              config={"displayModeBar": False},
                              style={"height": "280px"}),
                    html.Div([
                        html.Span("Index Chart Metric:", className="me-2 text-light"),
                        dbc.Select(
                            id="rdcf-index-metric",
                            options=[{"label": m, "value": m}
                                     for m in ("Revenue", "Net Income", "FCFE")],
                            value="Revenue", size="sm",
                            style={**_SELECT, "width": "140px"},
                        ),
                    ], className="d-flex align-items-center mt-2 mb-1"),
                    dbc.Row([
                        dbc.Col([
                            html.Div("Exclude:", className="text-light small mb-1"),
                            html.Div(id="rdcf-exclude-container"),
                        ], width=2),
                        dbc.Col(
                            dcc.Graph(id="rdcf-index-chart",
                                      config={"displayModeBar": False},
                                      style={"height": "320px"}),
                            width=10,
                        ),
                    ], className="g-1"),
                    html.Div(
                        [html.Span("Show:", className="me-2 text-light small")]
                        + [
                            dbc.Checkbox(
                                id={"type": "rdcf-show", "line": name},
                                label=name,
                                value=_DEFAULT_LINES[name],
                                className="me-2 text-light small",
                            )
                            for name in _LINE_KEYS
                        ],
                        className="d-flex flex-wrap align-items-center mt-1",
                    ),
                ], lg=7),
            ], className="g-3"),
        ]),
        dbc.ModalFooter(
            dbc.Button("Close", id="rdcf-close", color="secondary",
                       size="sm", n_clicks=0),
        ),
    ],
    id="rdcf-modal",
    is_open=False,
    size="xl",
    scrollable=True,
)


# ---------------------------------------------------------------------------
# Open / close
# ---------------------------------------------------------------------------

@callback(
    Output("rdcf-modal", "is_open"),
    Input("btn-dcf-reverse", "n_clicks"),
    Input("rdcf-close", "n_clicks"),
    State("rdcf-modal", "is_open"),
    prevent_initial_call=True,
)
def toggle_rdcf(open_clicks, close_clicks, is_open):
    trig = ctx.triggered_id
    if trig == "btn-dcf-reverse":
        return True
    if trig == "rdcf-close":
        return False
    return bool(is_open)


# ---------------------------------------------------------------------------
# Hydrate controls when the modal opens
# ---------------------------------------------------------------------------

@callback(
    Output("rdcf-ticker", "options"),
    Output("rdcf-ticker", "value"),
    Output("rdcf-chart-metric", "value"),
    Output("rdcf-index-metric", "value"),
    Output("rdcf-solve-for", "value"),
    Output("rdcf-ga", "value"),
    Output("rdcf-gn", "value"),
    Output("rdcf-h", "value"),
    Output("rdcf-term-capex", "value"),
    Output("rdcf-exclude-container", "children"),
    Input("rdcf-modal", "is_open"),
    State("session-store", "data"),
    prevent_initial_call=True,
)
def hydrate_rdcf(is_open, session_data):
    if not is_open:
        return (no_update,) * 10

    tickers, subject = _ticker_universe(session_data)
    state = _rdcf_state(session_data)
    options = [{"label": t, "value": t} for t in tickers]
    value = state["ticker"] if state["ticker"] in tickers else (tickers[0] if tickers else "")

    excluded = set(state["excluded_tickers"])
    checks = [
        dbc.Checkbox(
            id={"type": "rdcf-exclude", "ticker": t},
            label=t,
            value=(t in excluded),
            className="text-light small d-block",
        )
        for t in tickers
    ]
    return (
        options, value,
        state["chart_metric"], state["index_chart_metric"],
        state["solve_for"], state["ga"], state["gn"], state["h"],
        state["terminal_capex_equals_depr"],
        checks,
    )


@callback(
    Output("rdcf-ga", "disabled"),
    Output("rdcf-gn", "disabled"),
    Output("rdcf-h", "disabled"),
    Input("rdcf-solve-for", "value"),
)
def disable_solved_field(solve_for):
    return solve_for == "Ga", solve_for == "Gn", solve_for == "H"


# ---------------------------------------------------------------------------
# Render tables + charts
# ---------------------------------------------------------------------------

@callback(
    Output("rdcf-market-cap", "children"),
    Output("rdcf-ke", "children"),
    Output("rdcf-bridge", "children"),
    Output("rdcf-gordon", "children"),
    Output("rdcf-h-result", "children"),
    Output("rdcf-status", "children"),
    Output("rdcf-combo-chart", "figure"),
    Output("rdcf-hmodel-chart", "figure"),
    Output("rdcf-index-chart", "figure"),
    Input("rdcf-modal", "is_open"),
    Input("rdcf-ticker", "value"),
    Input("rdcf-chart-metric", "value"),
    Input("rdcf-index-metric", "value"),
    Input("rdcf-solve-for", "value"),
    Input("rdcf-ga", "value"),
    Input("rdcf-gn", "value"),
    Input("rdcf-h", "value"),
    Input("rdcf-term-capex", "value"),
    Input({"type": "rdcf-exclude", "ticker": ALL}, "value"),
    Input({"type": "rdcf-show", "line": ALL}, "value"),
    State({"type": "rdcf-exclude", "ticker": ALL}, "id"),
    State({"type": "rdcf-show", "line": ALL}, "id"),
    State("session-store", "data"),
    State("source-results-store", "data"),
    prevent_initial_call=True,
)
def render_rdcf(
    is_open, ticker, chart_metric, index_metric, solve_for,
    ga_text, gn_text, h_text, term_capex,
    exclude_vals, show_vals, exclude_ids, show_ids,
    session_data, source_results,
):
    if not is_open:
        return (no_update,) * 9

    all_inputs, subject = _build_all_inputs(session_data, source_results)
    ticker = (ticker or "").strip().upper()
    inp = all_inputs.get(ticker)

    excluded: Set[str] = set()
    for cid, val in zip(exclude_ids or [], exclude_vals or []):
        if isinstance(cid, dict) and cid.get("ticker") and val:
            excluded.add(cid["ticker"])

    visible = dict(_DEFAULT_LINES)
    for cid, val in zip(show_ids or [], show_vals or []):
        if isinstance(cid, dict) and cid.get("line"):
            visible[cid["line"]] = bool(val)

    solve_for = solve_for or "H"
    ga = _parse_pct_field(ga_text) if solve_for != "Ga" else None
    gn = _parse_pct_field(gn_text) if solve_for != "Gn" else None
    try:
        h_val = float(str(h_text).strip()) if solve_for != "H" and h_text else None
    except (TypeError, ValueError):
        h_val = None
    force_term = bool(term_capex)

    empty = _empty_fig("No inputs")
    if not inp or inp.get("_error"):
        msg = (inp or {}).get("_error") or "No inputs — refresh Source Data / WACC"
        return ("-", "-", html.Div(msg, className="text-muted"),
                "-", "-", msg, empty, empty, empty)

    ke = compute_cost_of_equity(
        inp.get("risk_free_rate"),
        inp.get("relevered_beta"),
        inp.get("equity_risk_premium"),
    )
    revenue = inp.get("revenue") or {}
    net_income = inp.get("net_income") or {}
    schedule = build_fcfe_schedule(
        revenue_prior=revenue.get("TTM") or revenue.get("LFY"),
        revenue_explicit=[revenue.get("NFY"), revenue.get("NFY+1"), revenue.get("NFY+2")],
        net_income_explicit=[net_income.get("NFY"), net_income.get("NFY+1"), net_income.get("NFY+2")],
        depr_pct=inp.get("depr_pct"),
        capex_pct=inp.get("capex_pct"),
        nwc_pct=inp.get("nwc_pct"),
        force_terminal_capex_equals_da=force_term,
    )
    a = compute_reconciliation_a(inp.get("market_cap"), schedule, ke)
    fcfe_n = schedule[-1]["fcfe"] if schedule else None

    gordon = solve_gordon_growth_ltgr(a, ke, fcfe_n)
    if gordon["value"] is None:
        gordon_text = f"NA ({','.join(gordon['flags'])})" if gordon["flags"] else "NA"
    else:
        gordon_text = _fmt_pct2(gordon["value"])
        if not gordon["is_valid"]:
            gordon_text += f" [{','.join(gordon['flags'])}]"

    h_res = solve_h_model(
        a, ke, fcfe_n, ga=ga, gn=gn, h=h_val,
        solve_for=solve_for, full_fade_convention=True,
    )
    if h_res["value"] is None:
        h_text = "NA"
        status = (
            f"{ticker}: {','.join(h_res['flags'])} | Gordon: {','.join(gordon['flags'])}"
        )
    else:
        if solve_for == "H":
            h_full = h_res["value"]
            h_text = f"H full={h_full:.2f} (h half={h_full / 2:.2f})"
        else:
            h_text = _fmt_pct2(h_res["value"])
        flags = gordon["flags"] + h_res["flags"]
        status = ", ".join(flags) if flags else ""

    try:
        chart_data = compute_gpc_chart_data(inp)
    except Exception:
        chart_data = {"bars": {}, "growth": {}}

    combo = _combo_figure(chart_data, chart_metric or "Revenue", ticker)
    hfig = _hmodel_figure(
        all_inputs, excluded, subject, solve_for, ga, gn, h_val,
    )
    idxfig = _index_figure(
        all_inputs, excluded, subject,
        index_metric or "Revenue", visible,
    )

    return (
        _fmt_currency2(inp.get("market_cap")),
        _fmt_pct2(ke),
        _bridge_table(inp, force_term),
        gordon_text,
        h_text,
        status,
        combo, hfig, idxfig,
    )


# ---------------------------------------------------------------------------
# Persist dialog settings (desktop ignores this extra key)
# ---------------------------------------------------------------------------

@callback(
    Output("session-store", "data", allow_duplicate=True),
    Input("rdcf-ticker", "value"),
    Input("rdcf-chart-metric", "value"),
    Input("rdcf-index-metric", "value"),
    Input("rdcf-solve-for", "value"),
    Input("rdcf-ga", "value"),
    Input("rdcf-gn", "value"),
    Input("rdcf-h", "value"),
    Input("rdcf-term-capex", "value"),
    Input({"type": "rdcf-exclude", "ticker": ALL}, "value"),
    Input({"type": "rdcf-show", "line": ALL}, "value"),
    State({"type": "rdcf-exclude", "ticker": ALL}, "id"),
    State({"type": "rdcf-show", "line": ALL}, "id"),
    State("rdcf-modal", "is_open"),
    State("session-store", "data"),
    prevent_initial_call=True,
)
def persist_rdcf(
    ticker, chart_metric, index_metric, solve_for,
    ga, gn, h, term_capex,
    exclude_vals, show_vals, exclude_ids, show_ids,
    is_open, session_data,
):
    if not is_open:
        return no_update

    session_data = dict(session_data or {})
    dcf_state = dict(session_data.get("dcf_page_state") or {})
    prev = dict(dcf_state.get("reverse_dcf_state") or {})

    excluded = [
        cid["ticker"]
        for cid, val in zip(exclude_ids or [], exclude_vals or [])
        if isinstance(cid, dict) and cid.get("ticker") and val
    ]
    visible = dict(_DEFAULT_LINES)
    for cid, val in zip(show_ids or [], show_vals or []):
        if isinstance(cid, dict) and cid.get("line"):
            visible[cid["line"]] = bool(val)

    new = {
        "ticker": ticker or "",
        "chart_metric": chart_metric or "Revenue",
        "index_chart_metric": index_metric or "Revenue",
        "solve_for": solve_for or "H",
        "ga": ga or "15.00%",
        "gn": gn or "3.00%",
        "h": h or "6.00",
        "terminal_capex_equals_depr": bool(term_capex),
        "excluded_tickers": excluded,
        "visible_lines": visible,
    }
    if new == prev:
        return no_update

    dcf_state["reverse_dcf_state"] = new
    session_data["dcf_page_state"] = dcf_state
    return session_data