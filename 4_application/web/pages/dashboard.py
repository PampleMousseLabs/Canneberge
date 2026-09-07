"""
web/pages/dashboard.py

Control-surface + reconciliation. Inputs live in the static layout.
Recalc updates labels and the football-field chart only.
"""

from __future__ import annotations

from typing import Optional

import dash
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
from dash import html, dcc, Input, Output, State, callback, ctx, ALL, no_update
from plotly.graph_objects import Figure

from Canneberge.Calculations.gpc_metrics import dropdown_options
from Canneberge.Calculations.wacc import (
    BETA_TYPE_OPTIONS, BETA_FREQUENCY_OPTIONS, CAPITAL_STRUCTURE_OPTIONS,
    CORPORATE_RATE_SERIES,
)
from web.lib.dashboard_data import (
    GPC_MAX, GT_MAX, RECON_METHODS, STAT_OPTIONS, TV_MODELS, GT_METRICS,
    COST_ROWS, dashboard_state_from_session, get_dashboard_results,
    dloc_from_cp, parse_weight, _basis_key, _gpc_bucket,
)
from web.lib.session_io import dict_to_project_inputs
from web.lib.wacc_data import wacc_state_from_session
from web.lib.dcf_data import dcf_state_from_session
from web.lib.gt_data import gt_state_from_session, get_gt_results
from web.components.gt_range_chart import gt_range_chart
from Canneberge.Calculations.gpc_multiples import compute_all_gpc_multiples
from web.lib.subject_metrics import get_subject_metric_value  # noqa: F401

dash.register_page(__name__, path="/dashboard", name="Dashboard")

_INP = {
    "backgroundColor": "#2a2a2a", "color": "#f5f5f5",
    "border": "1px solid #666", "fontSize": "12px", "textAlign": "right",
    "height": "26px", "padding": "2px 4px",
}
_SEL = {
    "backgroundColor": "#2a2a2a", "color": "#f5f5f5",
    "border": "1px solid #666", "fontSize": "12px", "height": "26px",
}
_HDR = {
    "backgroundColor": "#3d4fbf", "color": "white", "fontWeight": "bold",
    "fontSize": "13px", "padding": "4px 8px", "textAlign": "center",
}
_LBL = {"color": "#e6e6e6", "fontSize": "12px", "whiteSpace": "nowrap"}
_LBL_B = {**_LBL, "fontWeight": "bold"}
_SUB = {
    "backgroundColor": "#2b3e50", "color": "white", "fontWeight": "bold",
    "fontSize": "11px", "padding": "2px 8px",
}


def _fmt(v, basis: str) -> str:
    if v is None:
        return "-"
    if basis == "$/Share":
        return f"{v:,.2f}"
    return f"{v:,.0f}"


def _fmt_pct(v: Optional[float]) -> str:
    return "-" if v is None else f"{v * 100:.1f}%"


def _inp(oid, width, value="", disabled=False, placeholder=""):
    return dbc.Input(
        id=oid, type="text", value=value, placeholder=placeholder,
        debounce=True, size="sm", disabled=disabled,
        style={**_INP, "width": f"{width}px"},
    )


def _select(oid, options, value, width):
    return dbc.Select(
        id=oid, options=[{"label": o, "value": o} for o in options],
        value=value, size="sm", style={**_SEL, "width": f"{width}px"},
    )


def _kv(label, widget, hint=None):
    kids = [
        html.Span(label, style={**_LBL, "width": "150px", "display": "inline-block"}),
        widget,
    ]
    if hint:
        kids.append(html.Span(hint, className="text-muted small ms-2"))
    return html.Div(kids, className="d-flex align-items-center mb-1")


def _football_figure(rows, observed, concluded, basis: str) -> Figure:
    plotted = [(n, lo, hi) for n, lo, hi in rows if lo is not None and hi is not None]
    fig = go.Figure()
    if not plotted:
        fig.add_annotation(
            text="No method values to plot", xref="paper", yref="paper",
            x=0.5, y=0.5, showarrow=False, font=dict(color="#9fb3c8"),
        )
        fig.update_layout(
            paper_bgcolor="#1e1e1e", plot_bgcolor="#1e1e1e",
            xaxis=dict(visible=False), yaxis=dict(visible=False),
            height=360, margin=dict(l=20, r=20, t=20, b=20),
        )
        return fig

    names = [p[0] for p in plotted][::-1]
    lows = [p[1] for p in plotted][::-1]
    highs = [p[2] for p in plotted][::-1]
    widths = [h - lo if h != lo else abs(h) * 0.002 for lo, h in zip(lows, highs)]
    fig.add_bar(
        x=widths, y=names, base=lows, orientation="h",
        marker=dict(color="#c678dd", line=dict(color="#e5c07b", width=1)),
        name="Valuation Range",
        text=[f"{_fmt(lo, basis)}  {_fmt(h, basis)}" for lo, h in zip(lows, highs)],
        textposition="outside",
        insidetextanchor="middle",
    )
    marker_title = {"Equity": "Market Cap", "$/Share": "Share Price"}.get(basis, "Observed EV")
    if observed is not None:
        fig.add_vline(x=observed, line=dict(color="#e06c75", width=2, dash="dash"))
    if concluded is not None:
        fig.add_vline(x=concluded, line=dict(color="#e5c07b", width=2.4))
    fig.update_layout(
        paper_bgcolor="#1e1e1e", plot_bgcolor="#1e1e1e",
        font=dict(color="#9fb3c8", size=11),
        height=max(340, 28 * len(plotted) + 80),
        margin=dict(l=180, r=80, t=20, b=40),
        xaxis=dict(gridcolor="#3a4553", tickprefix="$",
                   tickformat=".2f" if basis == "$/Share" else ",.0f"),
        yaxis=dict(gridcolor="#3a4553"),
        showlegend=False,
        annotations=[
            dict(text=marker_title, x=1, y=0, xref="paper", yref="paper",
                 showarrow=False, font=dict(color="#e06c75", size=10),
                 xanchor="right", yanchor="bottom"),
        ] if observed is not None else [],
    )
    return fig


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------

def _gpc_rows():
    rows = [html.Div([
        html.Span("", style={"width": "210px", "display": "inline-block"}),
        html.Span("Low", style={**_LBL, "width": "72px", "display": "inline-block",
                                "textAlign": "right"}),
        html.Span("High", style={**_LBL, "width": "72px", "display": "inline-block",
                                 "textAlign": "right"}),
        html.Span("Weight", style={**_LBL, "width": "72px", "display": "inline-block",
                                   "textAlign": "right"}),
    ], className="d-flex mb-1")]
    for i in range(GPC_MAX):
        rows.append(html.Div([
            dbc.Select(id={"type": "dash-gpc-metric", "i": i}, options=[],
                       size="sm", style={**_SEL, "width": "210px"}),
            _inp({"type": "dash-gpc-low", "i": i}, 72),
            _inp({"type": "dash-gpc-high", "i": i}, 72),
            _inp({"type": "dash-gpc-wt", "i": i}, 72),
        ], className="d-flex align-items-center mb-1", id={"type": "dash-gpc-row", "i": i}))
    return rows


def _gt_rows():
    rows = [html.Div([
        html.Span("", style={"width": "210px", "display": "inline-block"}),
        html.Span("Low", style={**_LBL, "width": "72px", "display": "inline-block",
                                "textAlign": "right"}),
        html.Span("High", style={**_LBL, "width": "72px", "display": "inline-block",
                                 "textAlign": "right"}),
        html.Span("Weight", style={**_LBL, "width": "72px", "display": "inline-block",
                                   "textAlign": "right"}),
    ], className="d-flex mb-1")]
    for i in range(GT_MAX):
        rows.append(html.Div([
            dbc.Select(
                id={"type": "dash-gt-metric", "i": i},
                options=[{"label": m, "value": m} for m in GT_METRICS],
                value=GT_METRICS[i], size="sm",
                style={**_SEL, "width": "210px"},
            ),
            _inp({"type": "dash-gt-low", "i": i}, 72),
            _inp({"type": "dash-gt-high", "i": i}, 72),
            _inp({"type": "dash-gt-wt", "i": i}, 72),
        ], className="d-flex align-items-center mb-1", id={"type": "dash-gt-row", "i": i}))
    return rows


layout = dbc.Container([
    dbc.Row([
        dbc.Col(dbc.Card([
            html.Div("Income Approach", style=_HDR),
            dbc.CardBody([
                html.A("WACC", id="dash-wacc-link", href="#", className="text-warning small"),
                _kv("Debt/TIC", html.Div([
                    _inp("dash-debt-tic", 80),
                    _select("dash-debt-tic-stat", STAT_OPTIONS, "Median", 120),
                ], className="d-flex")),
                _kv("Beta", html.Div([
                    _inp("dash-beta", 80),
                    _select("dash-beta-stat", STAT_OPTIONS, "Median", 120),
                ], className="d-flex")),
                _kv("ERP", _inp("dash-erp", 80), "Per Kroll"),
                _kv("Size Premium", _inp("dash-size-premium", 80)),
                _kv("CSRP", _inp("dash-csrp", 80), "Projection Risk"),
                _kv("Pre-Tax Cost of Debt", html.Div([
                    html.Span("-", id="dash-pretax-kd", style={**_LBL, "width": "80px",
                                                               "display": "inline-block",
                                                               "textAlign": "right"}),
                    _select("dash-pretax-series", list(CORPORATE_RATE_SERIES.keys()),
                            list(CORPORATE_RATE_SERIES.keys())[0], 210),
                ], className="d-flex align-items-center")),
                _kv("WACC", html.Span("-", id="dash-wacc-value", style=_LBL_B)),
                html.Div("DCF Options", style={**_SUB, "margin": "8px 0 4px"}),
                _kv("Terminal Year", _select("dash-tv-model", TV_MODELS, "Gordon Growth", 180)),
                html.Div(id="dash-tv-ltgr-row", children=_kv("Long Term Growth Rate", _inp("dash-ltgr", 80, "3.0%"))),
                html.Div(id="dash-tv-mult-row", children=_kv("Selected Multiple", _inp("dash-tv-multiple", 80, "10.00x")), style={"display": "none"}),
                html.Div(id="dash-tv-years-row", children=_kv("Number of Years", _inp("dash-tv-years", 80, "5")), style={"display": "none"}),
                html.Div(id="dash-tv-stgr-row", children=_kv("Short Term Growth Rate", _inp("dash-tv-stgr", 80, "20.0%")), style={"display": "none"}),
                html.Div("CapEx Options", style={**_SUB, "margin": "8px 0 4px"}),
                _kv("Dep. as % of CapEx", _inp("dash-dep-pct", 80, "100.0%")),
            ], className="p-2"),
        ], color="secondary", outline=True), lg=4, className="mb-2"),

        dbc.Col(dbc.Card([
            html.Div("Market Approach", style=_HDR),
            dbc.CardBody([
                html.Div([
                    html.A("GPC", id="dash-gpc-chart-link", href="#", className="text-warning small me-3"),
                    html.Span("How Many Multiples:", className="text-muted small me-1"),
                    dbc.Input(id="dash-gpc-n", type="number", min=1, max=GPC_MAX, step=1,
                              value=GPC_MAX, debounce=True, size="sm",
                              style={**_INP, "width": "58px", "textAlign": "center"}),
                ], className="d-flex align-items-center mb-2"),
                html.Div(_gpc_rows()),
                html.Hr(style={"borderColor": "#4a5568", "margin": "8px 0"}),
                html.Div([
                    html.A("GT", id="dash-gt-chart-link", href="#", className="text-warning small me-3"),
                    html.Span("How Many Multiples:", className="text-muted small me-1"),
                    dbc.Input(id="dash-gt-n", type="number", min=1, max=GT_MAX, step=1,
                              value=GT_MAX, debounce=True, size="sm",
                              style={**_INP, "width": "58px", "textAlign": "center"}),
                ], className="d-flex align-items-center mb-2"),
                html.Div(_gt_rows()),
            ], className="p-2"),
        ], color="secondary", outline=True), lg=5, className="mb-2"),

        dbc.Col(dbc.Card([
            html.Div("Future Space", style=_HDR),
            dbc.CardBody([
                html.Div("Top-right probe", className="text-muted small"),
                html.Div("Use this area later for:", className="text-muted small"),
                html.Li("dynamic charts", className="text-muted small"),
                html.Li("helper lists", className="text-muted small"),
                html.Li("summaries", className="text-muted small"),
            ], className="p-2"),
        ], color="secondary", outline=True), lg=3, className="mb-2"),
    ], className="g-2"),

    dbc.Row([
        dbc.Col(dbc.Card([
            html.Div("Reconciliation of Values", style=_HDR),
            dbc.CardBody([
                html.Div([
                    html.Span("", style={"width": "48px", "display": "inline-block"}),
                    html.Span("Low", style={**_LBL, "width": "90px", "display": "inline-block",
                                            "textAlign": "right"}),
                    html.Span("High", style={**_LBL, "width": "90px", "display": "inline-block",
                                             "textAlign": "right"}),
                    html.Span("Weighting", style={**_LBL, "width": "90px", "display": "inline-block",
                                                  "textAlign": "right"}),
                ], className="d-flex mb-1"),
                *[
                    html.Div([
                        html.Span(m, style={**_LBL, "width": "48px", "display": "inline-block"}),
                        html.Span("-", id=f"dash-recon-{m.lower()}-low",
                                  style={**_LBL, "width": "90px", "display": "inline-block",
                                         "textAlign": "right"}),
                        html.Span("-", id=f"dash-recon-{m.lower()}-high",
                                  style={**_LBL, "width": "90px", "display": "inline-block",
                                         "textAlign": "right"}),
                        _inp({"type": "dash-recon-wt", "m": m}, 90),
                    ], className="d-flex align-items-center mb-1")
                    for m in RECON_METHODS
                ],
                html.Hr(style={"borderColor": "#4a5568", "margin": "6px 0"}),
                _kv("Control Premium:", _inp("dash-cp", 80, "24.0%")),
                _kv("Implied DLOC:", html.Span("-", id="dash-dloc", style=_LBL)),
                _kv("Display:", _select("dash-display", ["BEV", "Equity", "$/Share"], "BEV", 110)),
                _kv("Concluded FV:", html.Span("-", id="dash-concluded", style=_LBL_B)),
                html.Div([
                    html.Span("Observed EV:", id="dash-observed-label",
                              style={**_LBL, "width": "150px", "display": "inline-block"}),
                    html.Span("-", id="dash-observed", style=_LBL),
                ], className="d-flex"),
            ], className="p-2"),
        ], color="secondary", outline=True), lg=3, className="mb-2"),

        dbc.Col(dbc.Card([
            html.Div("Cost Approach", style=_HDR),
            dbc.CardBody([
                html.Div("NAV Method", className="fw-bold text-light small mb-1"),
                html.Div([
                    html.Span("Asset Value - Liquidation Basis", className="text-light small me-2"),
                    html.Span("Cost Count", className="text-muted small me-1"),
                    dbc.Input(id="dash-cost-count", type="number", min=1, max=10, step=1,
                              value=5, debounce=True, size="sm",
                              style={**_INP, "width": "58px", "textAlign": "center"}),
                ], className="d-flex align-items-center mb-2"),
                *[
                    _kv(name, _inp({"type": "dash-cost", "k": name}, 85))
                    for name in COST_ROWS
                ],
            ], className="p-2"),
        ], color="secondary", outline=True), lg=3, className="mb-2"),

        dbc.Col(dbc.Card([
            html.Div("Football Field Chart", style=_HDR),
            dbc.CardBody([
                dcc.Graph(id="dash-football", config={"displayModeBar": False},
                          style={"height": "380px"}),
            ], className="p-1"),
        ], color="secondary", outline=True), lg=6, className="mb-2"),
    ], className="g-2"),

    dbc.Modal([
        dbc.ModalHeader(dbc.ModalTitle("WACC Options")),
        dbc.ModalBody([
            _kv("Beta Type:", _select("dash-wacc-beta-type", BETA_TYPE_OPTIONS,
                                      BETA_TYPE_OPTIONS[0], 210)),
            _kv("Beta Frequency:", _select("dash-wacc-beta-freq", BETA_FREQUENCY_OPTIONS,
                                           BETA_FREQUENCY_OPTIONS[0], 210)),
            _kv("Capital Structure:", _select("dash-wacc-cap", CAPITAL_STRUCTURE_OPTIONS,
                                              CAPITAL_STRUCTURE_OPTIONS[0], 210)),
        ]),
        dbc.ModalFooter([
            dbc.Button("Cancel", id="dash-wacc-opt-cancel", color="secondary", size="sm", n_clicks=0),
            dbc.Button("OK", id="dash-wacc-opt-ok", color="primary", size="sm", n_clicks=0),
        ]),
    ], id="dash-wacc-modal", is_open=False),

    dbc.Modal([
        dbc.ModalHeader(dbc.ModalTitle("Range of Selected Multiples")),
        dbc.ModalBody(html.Div(id="dash-gpc-chart-body")),
        dbc.ModalFooter(dbc.Button("Close", id="dash-gpc-chart-close",
                                   color="secondary", size="sm", n_clicks=0)),
    ], id="dash-gpc-chart-modal", is_open=False, size="lg"),

    dbc.Modal([
        dbc.ModalHeader(dbc.ModalTitle("Range of Selected Transaction Multiples")),
        dbc.ModalBody(html.Div(id="dash-gt-chart-body")),
        dbc.ModalFooter(dbc.Button("Close", id="dash-gt-chart-close",
                                   color="secondary", size="sm", n_clicks=0)),
    ], id="dash-gt-chart-modal", is_open=False, size="lg"),
], fluid=True, className="px-2")


# ---------------------------------------------------------------------------
# Hydrate inputs on enter / session load only
# ---------------------------------------------------------------------------

@callback(
    Output("dash-debt-tic", "value"),
    Output("dash-debt-tic-stat", "value"),
    Output("dash-beta", "value"),
    Output("dash-beta-stat", "value"),
    Output("dash-erp", "value"),
    Output("dash-size-premium", "value"),
    Output("dash-csrp", "value"),
    Output("dash-pretax-series", "value"),
    Output("dash-tv-model", "value"),
    Output("dash-ltgr", "value"),
    Output("dash-tv-multiple", "value"),
    Output("dash-tv-years", "value"),
    Output("dash-tv-stgr", "value"),
    Output("dash-dep-pct", "value"),
    Output("dash-gpc-n", "value"),
    Output("dash-gt-n", "value"),
    Output("dash-cp", "value"),
    Output("dash-display", "value"),
    Output("dash-cost-count", "value"),
    Output({"type": "dash-gpc-metric", "i": ALL}, "options"),
    Output({"type": "dash-gpc-metric", "i": ALL}, "value"),
    Output({"type": "dash-gpc-low", "i": ALL}, "value"),
    Output({"type": "dash-gpc-high", "i": ALL}, "value"),
    Output({"type": "dash-gpc-wt", "i": ALL}, "value"),
    Output({"type": "dash-gt-metric", "i": ALL}, "value"),
    Output({"type": "dash-gt-low", "i": ALL}, "value"),
    Output({"type": "dash-gt-high", "i": ALL}, "value"),
    Output({"type": "dash-gt-wt", "i": ALL}, "value"),
    Output({"type": "dash-recon-wt", "m": ALL}, "value"),
    Output({"type": "dash-cost", "k": ALL}, "value"),
    Input("_pages_location", "pathname"),
    Input("session-load-timestamp", "data"),
    State("session-store", "data"),
)
def hydrate_dashboard(pathname, _ts, session_data):
    if pathname not in ("/dashboard", "/dashboard/"):
        return (
            *([no_update] * 19),
            [no_update] * GPC_MAX,
            [no_update] * GPC_MAX,
            [no_update] * GPC_MAX,
            [no_update] * GPC_MAX,
            [no_update] * GPC_MAX,
            [no_update] * GT_MAX,
            [no_update] * GT_MAX,
            [no_update] * GT_MAX,
            [no_update] * GT_MAX,
            [no_update] * len(RECON_METHODS),
            [no_update] * len(COST_ROWS),
        )

    session_data = session_data or {}
    dash = dashboard_state_from_session(session_data)
    wacc_s = wacc_state_from_session(session_data)
    dcf_s = dcf_state_from_session(session_data)
    gpc = _gpc_bucket(session_data)
    gt_s = gt_state_from_session(session_data)
    basis = _basis_key(session_data)
    gpc_opts = [{"label": o, "value": o} for o in dropdown_options(basis)]
    try:
        gpc_n = max(1, min(GPC_MAX, int(gpc.get("num_multiples") or GPC_MAX)))
    except (TypeError, ValueError):
        gpc_n = GPC_MAX
    try:
        gt_n = max(1, min(GT_MAX, int(gt_s.get("num_multiples") or GT_MAX)))
    except (TypeError, ValueError):
        gt_n = GT_MAX

    gpc_metrics, gpc_lo, gpc_hi, gpc_wt = [], [], [], []
    opts_list = dropdown_options(basis)
    for i in range(GPC_MAX):
        name = gpc["metric_cols"].get(str(i))
        if name not in opts_list:
            name = opts_list[i % len(opts_list)] if opts_list else ""
        gpc_metrics.append(name)
        gpc_lo.append(gpc["selected_low"].get(str(i), ""))
        gpc_hi.append(gpc["selected_high"].get(str(i), ""))
        gpc_wt.append(gpc["weights"].get(str(i), f"{100.0 / gpc_n:.1f}%" if i < gpc_n else ""))

    gt_metrics = list(gt_s.get("metric_selections") or GT_METRICS)[:GT_MAX]
    while len(gt_metrics) < GT_MAX:
        gt_metrics.append(GT_METRICS[len(gt_metrics) % 3])
    gt_lo = list(gt_s.get("selected_low") or []) + [""] * GT_MAX
    gt_hi = list(gt_s.get("selected_high") or []) + [""] * GT_MAX
    gt_wt = list(gt_s.get("weights") or []) + [""] * GT_MAX

    tv_in = dcf_s.get("tv_inputs") or {}
    series = wacc_s["pretax_debt_series"]
    if series not in CORPORATE_RATE_SERIES:
        series = list(CORPORATE_RATE_SERIES.keys())[0]

    recon_wts = [dash["recon_weights"].get(m, "") for m in RECON_METHODS]
    cost_vals = [dash["cost_values"].get(k, "") for k in COST_ROWS]

    return (
        wacc_s.get("selected_debt_tic", ""),
        dash["debt_tic_stat"],
        wacc_s.get("selected_relevered_beta", ""),
        dash["beta_stat"],
        wacc_s.get("equity_risk_premium", ""),
        wacc_s.get("size_premium", ""),
        wacc_s.get("csrp", ""),
        series,
        dcf_s.get("tv_model", "Gordon Growth"),
        dcf_s.get("ltg_input", "3.0%"),
        (tv_in.get("EBITDA Multiple") or {}).get("multiple")
        or (tv_in.get("Revenue Multiple") or {}).get("multiple") or "10.00x",
        (tv_in.get("H-Model") or {}).get("num_years", "5"),
        (tv_in.get("H-Model") or {}).get("short_term_growth", "20.0%"),
        dcf_s.get("capex_dep_pct", "100.0%"),
        gpc_n, gt_n,
        dash["control_premium"],
        dash["display_basis"],
        dash["cost_count"],
        [gpc_opts] * GPC_MAX,
        gpc_metrics, gpc_lo[:GPC_MAX], gpc_hi[:GPC_MAX], gpc_wt[:GPC_MAX],
        gt_metrics[:GT_MAX], gt_lo[:GT_MAX], gt_hi[:GT_MAX], gt_wt[:GT_MAX],
        recon_wts, cost_vals,
    )


# ---------------------------------------------------------------------------
# TV row visibility + GPC/GT enable
# ---------------------------------------------------------------------------

@callback(
    Output("dash-tv-mult-row", "style"),
    Output("dash-tv-years-row", "style"),
    Output("dash-tv-stgr-row", "style"),
    Input("dash-tv-model", "value"),
)
def tv_visibility(model):
    hide = {"display": "none"}
    show = {}
    is_mult = model in ("EBITDA Multiple", "Revenue Multiple")
    is_h = model == "H-Model"
    return (show if is_mult else hide,
            show if is_h else hide,
            show if is_h else hide)


@callback(
    Output({"type": "dash-gpc-metric", "i": ALL}, "disabled"),
    Output({"type": "dash-gpc-low", "i": ALL}, "disabled"),
    Output({"type": "dash-gpc-high", "i": ALL}, "disabled"),
    Output({"type": "dash-gpc-wt", "i": ALL}, "disabled"),
    Input("dash-gpc-n", "value"),
)
def enable_gpc_rows(n):
    try:
        n = max(1, min(GPC_MAX, int(n)))
    except (TypeError, ValueError):
        n = GPC_MAX
    flags = [i >= n for i in range(GPC_MAX)]
    return flags, flags, flags, flags


@callback(
    Output({"type": "dash-gt-metric", "i": ALL}, "disabled"),
    Output({"type": "dash-gt-low", "i": ALL}, "disabled"),
    Output({"type": "dash-gt-high", "i": ALL}, "disabled"),
    Output({"type": "dash-gt-wt", "i": ALL}, "disabled"),
    Input("dash-gt-n", "value"),
)
def enable_gt_rows(n):
    try:
        n = max(1, min(GT_MAX, int(n)))
    except (TypeError, ValueError):
        n = GT_MAX
    flags = [i >= n for i in range(GT_MAX)]
    return flags, flags, flags, flags


# ---------------------------------------------------------------------------
# Stat dropdowns copy WACC statistics into the value box
# ---------------------------------------------------------------------------

@callback(
    Output("dash-debt-tic", "value", allow_duplicate=True),
    Output("dash-beta", "value", allow_duplicate=True),
    Input("dash-debt-tic-stat", "value"),
    Input("dash-beta-stat", "value"),
    State("session-store", "data"),
    State("source-results-store", "data"),
    prevent_initial_call=True,
)
def apply_wacc_stat(debt_stat, beta_stat, session_data, source_results):
    from web.lib.wacc_data import get_wacc_results
    stats = get_wacc_results(session_data or {}, source_results or {}).get("stats") or {}
    trig = ctx.triggered_id
    debt_out, beta_out = no_update, no_update
    if trig == "dash-debt-tic-stat" and debt_stat and debt_stat != "Custom":
        v = (stats.get(debt_stat) or {}).get("debt_tic")
        if v is not None:
            debt_out = f"{v * 100:.1f}%"
    if trig == "dash-beta-stat" and beta_stat and beta_stat != "Custom":
        v = (stats.get(beta_stat) or {}).get("relevered_beta")
        if v is not None:
            beta_out = f"{v:.2f}"
    return debt_out, beta_out


# ---------------------------------------------------------------------------
# Outputs (labels + chart) — inputs are not outputs
# ---------------------------------------------------------------------------

@callback(
    Output("dash-wacc-value", "children"),
    Output("dash-pretax-kd", "children"),
    Output("dash-dloc", "children"),
    Output("dash-concluded", "children"),
    Output("dash-observed", "children"),
    Output("dash-observed-label", "children"),
    Output("dash-recon-dcf-low", "children"),
    Output("dash-recon-dcf-high", "children"),
    Output("dash-recon-gpc-low", "children"),
    Output("dash-recon-gpc-high", "children"),
    Output("dash-recon-gt-low", "children"),
    Output("dash-recon-gt-high", "children"),
    Output("dash-recon-gipo-low", "children"),
    Output("dash-recon-gipo-high", "children"),
    Output("dash-recon-nav-low", "children"),
    Output("dash-recon-nav-high", "children"),
    Output("dash-football", "figure"),
    Input("_pages_location", "pathname"),
    Input("session-store", "data"),
    Input("source-results-store", "data"),
    Input("dash-display", "value"),
)
def render_dashboard_outputs(pathname, session_data, source_results, display):
    if pathname not in ("/dashboard", "/dashboard/"):
        return (no_update,) * 17
    session_data = dict(session_data or {})
    if display in ("BEV", "Equity", "$/Share"):
        dstate = dict(session_data.get("dashboard_page_state") or {})
        dstate["display_basis"] = display
        session_data["dashboard_page_state"] = dstate
    try:
        res = get_dashboard_results(session_data, source_results)
    except Exception as exc:
        empty = go.Figure()
        empty.update_layout(paper_bgcolor="#1e1e1e", plot_bgcolor="#1e1e1e",
                            xaxis=dict(visible=False), yaxis=dict(visible=False), height=360)
        msg = f"Dashboard error: {exc}"
        return (msg, "-", "-", "-", "-", "Observed:",
                "-", "-", "-", "-", "-", "-", "-", "-", "-", "-", empty)

    basis = res["basis"]
    wacc = res["wacc"]
    pairs = res["pairs"]
    obs_label = {
        "Equity": "Observed Market Cap:",
        "$/Share": "Observed Share Price:",
    }.get(basis, "Observed EV:")
    fig = _football_figure(res["football"], res["observed"], res["concluded"], basis)

    def pair(m):
        lo, hi = pairs.get(m, (None, None))
        return _fmt(lo, basis), _fmt(hi, basis)

    dcf_l, dcf_h = pair("DCF")
    gpc_l, gpc_h = pair("GPC")
    gt_l, gt_h = pair("GT")
    return (
        _fmt_pct(wacc.get("wacc")) if wacc.get("wacc") is not None else "-",
        _fmt_pct(wacc.get("pretax_kd")),
        _fmt_pct(res["dloc"]),
        _fmt(res["concluded"], basis),
        _fmt(res["observed"], basis),
        obs_label,
        dcf_l, dcf_h, gpc_l, gpc_h, gt_l, gt_h, "-", "-", "-", "-",
        fig,
    )


# ---------------------------------------------------------------------------
# Persist → nested session states
# ---------------------------------------------------------------------------

@callback(
    Output("session-store", "data", allow_duplicate=True),
    Input("dash-debt-tic", "value"),
    Input("dash-debt-tic-stat", "value"),
    Input("dash-beta", "value"),
    Input("dash-beta-stat", "value"),
    Input("dash-erp", "value"),
    Input("dash-size-premium", "value"),
    Input("dash-csrp", "value"),
    Input("dash-pretax-series", "value"),
    Input("dash-tv-model", "value"),
    Input("dash-ltgr", "value"),
    Input("dash-tv-multiple", "value"),
    Input("dash-tv-years", "value"),
    Input("dash-tv-stgr", "value"),
    Input("dash-dep-pct", "value"),
    Input("dash-gpc-n", "value"),
    Input("dash-gt-n", "value"),
    Input("dash-cp", "value"),
    Input("dash-display", "value"),
    Input("dash-cost-count", "value"),
    Input({"type": "dash-gpc-metric", "i": ALL}, "value"),
    Input({"type": "dash-gpc-low", "i": ALL}, "value"),
    Input({"type": "dash-gpc-high", "i": ALL}, "value"),
    Input({"type": "dash-gpc-wt", "i": ALL}, "value"),
    Input({"type": "dash-gt-metric", "i": ALL}, "value"),
    Input({"type": "dash-gt-low", "i": ALL}, "value"),
    Input({"type": "dash-gt-high", "i": ALL}, "value"),
    Input({"type": "dash-gt-wt", "i": ALL}, "value"),
    Input({"type": "dash-recon-wt", "m": ALL}, "value"),
    Input({"type": "dash-cost", "k": ALL}, "value"),
    State({"type": "dash-gpc-metric", "i": ALL}, "id"),
    State({"type": "dash-gt-metric", "i": ALL}, "id"),
    State({"type": "dash-recon-wt", "m": ALL}, "id"),
    State({"type": "dash-cost", "k": ALL}, "id"),
    State("session-store", "data"),
    prevent_initial_call=True,
)
def persist_dashboard(
    debt_tic, debt_stat, beta, beta_stat, erp, size_p, csrp, pretax_series,
    tv_model, ltgr, tv_mult, tv_years, tv_stgr, dep_pct,
    gpc_n, gt_n, cp, display, cost_count,
    gpc_metrics, gpc_lo, gpc_hi, gpc_wt,
    gt_metrics, gt_lo, gt_hi, gt_wt,
    recon_wts, cost_vals,
    gpc_metric_ids, gt_metric_ids, recon_ids, cost_ids,
    session_data,
):
    if not ctx.triggered_id:
        return no_update
    session_data = dict(session_data or {})
    wacc = dict(session_data.get("wacc_page_state") or {})
    dcf = dict(session_data.get("dcf_page_state") or {})
    gpc = dict(session_data.get("gpc_page_state") or {})
    gt = dict(session_data.get("gt_page_state") or {})
    dash = dict(session_data.get("dashboard_page_state") or {})

    if debt_tic is not None:
        wacc["selected_debt_tic"] = debt_tic
    if beta is not None:
        wacc["selected_relevered_beta"] = beta
    if erp is not None:
        wacc["equity_risk_premium"] = erp
    if size_p is not None:
        wacc["size_premium"] = size_p
    if csrp is not None:
        wacc["csrp"] = csrp
    if pretax_series in CORPORATE_RATE_SERIES:
        wacc["pretax_debt_series"] = pretax_series

    if tv_model in TV_MODELS:
        dcf["tv_model"] = tv_model
    if ltgr is not None:
        dcf["ltg_input"] = ltgr
    if dep_pct is not None:
        dcf["capex_dep_pct"] = dep_pct
    tv_inputs = dict(dcf.get("tv_inputs") or {})
    if tv_model in ("EBITDA Multiple", "Revenue Multiple") and tv_mult is not None:
        bucket = dict(tv_inputs.get(tv_model) or {})
        bucket["multiple"] = tv_mult
        tv_inputs[tv_model] = bucket
    if tv_model == "H-Model":
        h = dict(tv_inputs.get("H-Model") or {})
        if tv_years is not None:
            h["num_years"] = tv_years
        if tv_stgr is not None:
            h["short_term_growth"] = tv_stgr
        tv_inputs["H-Model"] = h
    dcf["tv_inputs"] = tv_inputs

    try:
        gpc_n = max(1, min(GPC_MAX, int(gpc_n)))
    except (TypeError, ValueError):
        gpc_n = GPC_MAX
    try:
        gt_n = max(1, min(GT_MAX, int(gt_n)))
    except (TypeError, ValueError):
        gt_n = GT_MAX

    basis = _basis_key(session_data)
    basis_state = dict(gpc.get("basis_state") or {})
    bucket = dict(basis_state.get(basis) or {})
    metric_cols, sel_lo, sel_hi, wts = {}, {}, {}, {}
    even = f"{100.0 / gpc_n:.1f}%"
    reset_gpc_w = ctx.triggered_id == "dash-gpc-n"
    for i in range(gpc_n):
        metric_cols[str(i)] = (gpc_metrics[i] if i < len(gpc_metrics) else "") or ""
        sel_lo[str(i)] = gpc_lo[i] if i < len(gpc_lo) else ""
        sel_hi[str(i)] = gpc_hi[i] if i < len(gpc_hi) else ""
        wts[str(i)] = even if reset_gpc_w else (gpc_wt[i] if i < len(gpc_wt) else even)
    bucket.update({
        "metric_cols": metric_cols, "selected_low": sel_lo,
        "selected_high": sel_hi, "weights": wts,
    })
    basis_state[basis] = bucket
    gpc["basis_state"] = basis_state
    gpc["num_multiples"] = gpc_n
    gpc["metric_cols"] = metric_cols
    gpc["selected_low"] = sel_lo
    gpc["selected_high"] = sel_hi
    gpc["weights"] = wts
    if cp is not None:
        gpc["control_premium"] = cp

    even_gt = f"{100.0 / gt_n:.1f}%"
    reset_gt_w = ctx.triggered_id == "dash-gt-n"
    gt["num_multiples"] = gt_n
    gt["metric_selections"] = list(gt_metrics or GT_METRICS)[:gt_n]
    gt["selected_low"] = list(gt_lo or [])[:gt_n]
    gt["selected_high"] = list(gt_hi or [])[:gt_n]
    if reset_gt_w:
        gt["weights"] = [even_gt] * gt_n
    else:
        gt["weights"] = list(gt_wt or [])[:gt_n]
    dloc = dloc_from_cp(cp)
    if dloc is not None:
        gt["dloc"] = f"{dloc * 100:.1f}%"
        gpc["dloc"] = f"{dloc * 100:.1f}%"

    recon = dict(dash.get("recon_weights") or {})
    for cid, val in zip(recon_ids or [], recon_wts or []):
        if isinstance(cid, dict) and cid.get("m"):
            recon[cid["m"]] = "" if val is None else str(val)
    costs = dict(dash.get("cost_values") or {})
    for cid, val in zip(cost_ids or [], cost_vals or []):
        if isinstance(cid, dict) and cid.get("k"):
            costs[cid["k"]] = "" if val is None else str(val)

    trig = ctx.triggered_id
    debt_stat_out = debt_stat
    beta_stat_out = beta_stat
    if trig == "dash-debt-tic":
        debt_stat_out = "Custom"
    if trig == "dash-beta":
        beta_stat_out = "Custom"

    dash.update({
        "control_premium": cp if cp is not None else dash.get("control_premium", "24.0%"),
        "display_basis": display if display in ("BEV", "Equity", "$/Share") else dash.get("display_basis", "BEV"),
        "recon_weights": recon,
        "debt_tic_stat": debt_stat_out or "Median",
        "beta_stat": beta_stat_out or "Median",
        "cost_count": cost_count,
        "cost_values": costs,
        "gpc_weights": list(wts.values()),
        "gt_weights": gt.get("weights", []),
    })

    session_data["wacc_page_state"] = wacc
    session_data["dcf_page_state"] = dcf
    session_data["gpc_page_state"] = gpc
    session_data["gt_page_state"] = gt
    session_data["dashboard_page_state"] = dash
    return session_data


# ---------------------------------------------------------------------------
# WACC options modal
# ---------------------------------------------------------------------------

@callback(
    Output("dash-wacc-modal", "is_open"),
    Output("dash-wacc-beta-type", "value"),
    Output("dash-wacc-beta-freq", "value"),
    Output("dash-wacc-cap", "value"),
    Input("dash-wacc-link", "n_clicks"),
    Input("dash-wacc-opt-cancel", "n_clicks"),
    Input("dash-wacc-opt-ok", "n_clicks"),
    State("session-store", "data"),
    prevent_initial_call=True,
)
def wacc_modal(open_c, cancel_c, ok_c, session_data):
    trig = ctx.triggered_id
    if trig == "dash-wacc-link":
        s = wacc_state_from_session(session_data or {})
        return True, s["beta_type"], s["beta_frequency"], s["capital_structure"]
    return False, no_update, no_update, no_update


@callback(
    Output("session-store", "data", allow_duplicate=True),
    Input("dash-wacc-opt-ok", "n_clicks"),
    State("dash-wacc-beta-type", "value"),
    State("dash-wacc-beta-freq", "value"),
    State("dash-wacc-cap", "value"),
    State("session-store", "data"),
    prevent_initial_call=True,
)
def save_wacc_options(n, beta_type, freq, cap, session_data):
    if not n:
        return no_update
    session_data = dict(session_data or {})
    wacc = dict(session_data.get("wacc_page_state") or {})
    if beta_type in BETA_TYPE_OPTIONS:
        wacc["beta_type"] = beta_type
    if freq in BETA_FREQUENCY_OPTIONS:
        wacc["beta_frequency"] = freq
    if cap in CAPITAL_STRUCTURE_OPTIONS:
        wacc["capital_structure"] = cap
    session_data["wacc_page_state"] = wacc
    return session_data


# ---------------------------------------------------------------------------
# Chart modals
# ---------------------------------------------------------------------------

@callback(
    Output("dash-gpc-chart-modal", "is_open"),
    Input("dash-gpc-chart-link", "n_clicks"),
    Input("dash-gpc-chart-close", "n_clicks"),
    State("dash-gpc-chart-modal", "is_open"),
    prevent_initial_call=True,
)
def toggle_gpc_chart(a, b, is_open):
    if ctx.triggered_id == "dash-gpc-chart-link":
        return True
    if ctx.triggered_id == "dash-gpc-chart-close":
        return False
    return bool(is_open)


@callback(
    Output("dash-gt-chart-modal", "is_open"),
    Input("dash-gt-chart-link", "n_clicks"),
    Input("dash-gt-chart-close", "n_clicks"),
    State("dash-gt-chart-modal", "is_open"),
    prevent_initial_call=True,
)
def toggle_gt_chart(a, b, is_open):
    if ctx.triggered_id == "dash-gt-chart-link":
        return True
    if ctx.triggered_id == "dash-gt-chart-close":
        return False
    return bool(is_open)


@callback(
    Output("dash-gpc-chart-body", "children"),
    Input("dash-gpc-chart-modal", "is_open"),
    State("session-store", "data"),
    State("source-results-store", "data"),
)
def render_dash_gpc_chart(is_open, session_data, source_results):
    if not is_open:
        return no_update
    inputs = dict_to_project_inputs(session_data or {})
    tickers = inputs.gpc_tickers or []
    gpc = _gpc_bucket(session_data or {})
    basis = _basis_key(session_data or {})
    try:
        n = max(1, min(GPC_MAX, int(gpc.get("num_multiples") or GPC_MAX)))
    except (TypeError, ValueError):
        n = GPC_MAX
    names = [gpc["metric_cols"].get(str(i), "") for i in range(n)]
    sa = (source_results or {}).get("stockanalysis", {}) or {}
    all_m = compute_all_gpc_multiples(
        sa.get("IS", []), (source_results or {}).get("marketscreener", []) or [],
        sa.get("Ratios", []), sa.get("BS", []), tickers, basis_mode=basis,
    )
    excl = ((session_data or {}).get("gpc_page_state") or {}).get("exclude_map") or {}
    included = [t for t in tickers if not excl.get(t, False)]
    labels, q3, mx, mn, q1 = [], [], [], [], []
    for name in names:
        vals = sorted(v for t in included if (v := all_m.get(t, {}).get(name)) is not None)
        labels.append(name)
        if not vals:
            q3.append(None); mx.append(None); mn.append(None); q1.append(None)
            continue
        n_v = len(vals)
        mx.append(vals[-1]); mn.append(vals[0])
        q3.append(vals[int(0.75 * (n_v - 1))])
        q1.append(vals[int(0.25 * (n_v - 1))])
    fig = gt_range_chart(labels, q3, mx, mn, q1, title="Range of Selected Multiples")
    return dcc.Graph(figure=fig, config={"displayModeBar": False}, style={"height": "520px"})


@callback(
    Output("dash-gt-chart-body", "children"),
    Input("dash-gt-chart-modal", "is_open"),
    State("session-store", "data"),
    State("source-results-store", "data"),
)
def render_dash_gt_chart(is_open, session_data, source_results):
    if not is_open:
        return no_update

    state = gt_state_from_session(session_data or {})
    calc = get_gt_results(session_data or {}, source_results or {}, state)
    chart = calc.get("chart_data") or calc.get("chart") or {}

    fig = gt_range_chart(
        calc.get("metric_selections") or [],
        chart.get("q3") or chart.get("open") or [],
        chart.get("max") or chart.get("high") or [],
        chart.get("min") or chart.get("low") or [],
        chart.get("q1") or chart.get("close") or [],
        title="Range of Selected Transaction Multiples",
    )

    return dcc.Graph(
        figure=fig,
        config={"displayModeBar": False},
        style={"height": "520px"},
    )