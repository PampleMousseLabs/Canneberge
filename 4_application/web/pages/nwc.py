"""
web/pages/nwc.py

Dash Net Working Capital schedule.

All math lives in Canneberge.Calculations.nwc — this file only fetches
session values, renders, and persists.

State: session-store["nwc_page_state"], desktop-compatible shape plus
cached outputs the GPC bridge and (later) DCF can read without
recomputing:

    ca_selections / cl_selections / cash_treatment / nwc_basis /
    selected_pct / historical_years / ca_row_count / cl_row_count /
    gpc_exclusions              <- written by desktop too

    nwc_by_period / nwc_pct_by_period / changes_in_nwc /
    surplus_deficit / normalized_nwc / actual_nwc
                                <- web-only cache; desktop ignores them

RESIDUAL COLUMN: rendered but intentionally blank. DCF is the single
source of truth for Residual Revenue and the web DCF page does not
exist yet. Nothing here estimates or extrapolates it.
"""

from __future__ import annotations

from typing import Optional, List, Dict

import dash
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
from dash import html, dcc, Input, Output, State, callback, ctx, ALL, no_update

from Canneberge.Calculations.nwc import (
    CA_CANDIDATES, CL_CANDIDATES,
    CA_MAX_ROWS, CL_MAX_ROWS,
    CA_DEFAULT_SELECTIONS, CL_DEFAULT_SELECTIONS,
    CA_DEFAULT_ROWS, CL_DEFAULT_ROWS,
    STAT_NAMES,
    format_ca_cl_option,
    period_columns, historical_columns, fye_years,
    sum_selected_rows, subject_nwc_by_period, changes_in_nwc,
    peer_series, peer_statistics, nwc_bridge,
    parse_pct_text, safe_div,
)
from web.lib.session_io import dict_to_project_inputs
from web.lib.subject_metrics import get_subject_metric_value

dash.register_page(__name__, path="/nwc", name="NWC")


# ---------------------------------------------------------------------------
# Style tokens
# ---------------------------------------------------------------------------

COL_W = 90
LABEL_W = 330
GAP_W = 14
EXCLUDE_W = 80
TICKER_W = 250

_HDR_BAND = {
    "backgroundColor": "#2b3e50", "color": "white", "fontWeight": "bold",
    "padding": "3px 8px", "textAlign": "center", "border": "1px solid #555",
    "fontSize": "12px",
}
_HDR_PERIOD = {
    "color": "#9fb3c8", "fontSize": "11px", "padding": "3px 6px",
    "textAlign": "right", "whiteSpace": "nowrap",
}
_LABEL = {
    "color": "#e6e6e6", "fontSize": "12px", "padding": "3px 6px",
    "whiteSpace": "nowrap",
}
_LABEL_BOLD = {**_LABEL, "fontWeight": "bold"}
_LABEL_MARGIN = {**_LABEL, "fontStyle": "italic", "color": "#9fb3c8",
                 "paddingLeft": "18px"}
_CELL = {
    "color": "#dddddd", "fontSize": "12px", "padding": "3px 6px",
    "textAlign": "right", "whiteSpace": "nowrap",
}
_CELL_BOLD = {**_CELL, "fontWeight": "bold", "color": "#ffffff"}
_CELL_MARGIN = {**_CELL, "fontStyle": "italic", "color": "#9fb3c8"}
_BORDER_TOP = {"borderTop": "1px solid #4a5568"}
_EMPHASIS = {"borderTop": "1px solid #4a5568", "borderBottom": "3px double #4a5568"}

_SELECT_STYLE = {
    "backgroundColor": "#2a2a2a", "color": "#f5f5f5",
    "border": "1px solid #666", "fontSize": "11px",
    "padding": "1px 4px", "height": "26px", "width": f"{LABEL_W - 8}px",
}
_INPUT_STYLE = {
    "backgroundColor": "#2a2a2a", "color": "#f5f5f5",
    "border": "1px solid #666", "fontSize": "12px",
    "textAlign": "right", "padding": "2px 4px",
    "height": "26px", "width": f"{COL_W}px",
}

CHART_BG = "#1e1e1e"
CHART_GRID = "#3a4553"
CHART_TEXT = "#e6e6e6"
CHART_AXIS = "#9fb3c8"
CHART_BAR = "#4a90d9"
CHART_REV = "#e06c75"
CHART_PCT = "#e5c07b"


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

def _fmt_currency(v: Optional[float]) -> str:
    if v is None:
        return "-"
    try:
        return f"{v:,.0f}"
    except (TypeError, ValueError):
        return "-"


def _fmt_pct(v: Optional[float]) -> str:
    if v is None:
        return "-"
    try:
        return f"{v * 100:.1f}%"
    except (TypeError, ValueError):
        return "-"


# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------

def _pad_selections(saved: list, defaults: list, count: int) -> List[str]:
    out: List[str] = []
    for i in range(count):
        if i < len(saved) and saved[i] is not None:
            out.append(str(saved[i]))
        elif i < len(defaults):
            out.append(defaults[i])
        else:
            out.append("")
    return out


def _state_from_session(session_data: dict) -> dict:
    return nwc_state_from_session(session_data)


def _state_from_session_legacy(session_data: dict) -> dict:
    raw = (session_data or {}).get("nwc_page_state", {}) or {}

    def _int(key, default, lo, hi):
        try:
            return max(lo, min(hi, int(raw.get(key, default))))
        except (TypeError, ValueError):
            return default

    ca_rows = _int("ca_row_count", CA_DEFAULT_ROWS, 1, CA_MAX_ROWS)
    cl_rows = _int("cl_row_count", CL_DEFAULT_ROWS, 1, CL_MAX_ROWS)

    return {
        "historical_years": _int("historical_years", 5, 1, 5),
        "ca_row_count": ca_rows,
        "cl_row_count": cl_rows,
        "ca_selections": _pad_selections(
            raw.get("ca_selections") or [], CA_DEFAULT_SELECTIONS, ca_rows
        ),
        "cl_selections": _pad_selections(
            raw.get("cl_selections") or [], CL_DEFAULT_SELECTIONS, cl_rows
        ),
        "cash_treatment": raw.get("cash_treatment", "Excluding Cash"),
        "nwc_basis": raw.get("nwc_basis", "% of Revenue"),
        "selected_pct": raw.get("selected_pct", "15.0%"),
        "gpc_exclusions": list(raw.get("gpc_exclusions") or []),
    }


def _exclusion_map(tickers: List[str], flags: list) -> Dict[str, bool]:
    out: Dict[str, bool] = {}
    for i, t in enumerate(tickers):
        out[t] = bool(flags[i]) if i < len(flags) else False
    return out


# ---------------------------------------------------------------------------
# Core computation shared by the table and chart callbacks
# ---------------------------------------------------------------------------

def _compute(session_data: dict, source_results: dict, state: dict) -> dict:
    return get_nwc_results(session_data, source_results, state)


def _compute_legacy(session_data: dict, source_results: dict, state: dict) -> dict:
    inputs = dict_to_project_inputs(session_data or {})

    headers, is_hist = period_columns(
        state["historical_years"],
        list(inputs.projection_period_columns),
    )
    hist_periods = historical_columns(headers, is_hist)

    def sf(key: str, period: str) -> Optional[float]:
        # Residual has no source anywhere until DCF exists.
        if not key or period == "Residual":
            return None
        return get_subject_metric_value(
            session_data or {}, source_results or {}, key, period
        )

    revenue = {p: sf("revenue", p) for p in headers}

    ca_rows, ca_sums = sum_selected_rows(state["ca_selections"], headers, sf)
    cl_rows, cl_sums = sum_selected_rows(state["cl_selections"], headers, sf)

    selected_pct = parse_pct_text(state["selected_pct"])
    pct_basis = state["nwc_basis"] == "% of Revenue"

    nwc = subject_nwc_by_period(
        headers, is_hist, revenue, ca_sums, cl_sums, selected_pct, pct_basis
    )
    nwc_pct = {p: safe_div(nwc.get(p), revenue.get(p)) for p in headers}
    changes = changes_in_nwc(headers, nwc)

    tickers = list(inputs.gpc_tickers or [])
    excluded = _exclusion_map(tickers, state["gpc_exclusions"])
    exclude_cash = state["cash_treatment"] == "Excluding Cash"

    sa = (source_results or {}).get("stockanalysis", {}) or {}
    peers = peer_series(
        sa.get("BS", []), sa.get("IS", []),
        tickers, hist_periods, exclude_cash,
    )
    peer_pct = {t: peers[t]["pct"] for t in tickers}
    stats = peer_statistics(peer_pct, hist_periods, excluded)

    bridge = nwc_bridge(revenue.get("TTM"), nwc.get("TTM"), selected_pct)

    return {
        "inputs": inputs,
        "headers": headers,
        "is_hist": is_hist,
        "hist_periods": hist_periods,
        "fye": fye_years(
            headers, inputs.last_fiscal_year_year, inputs.next_fiscal_year_year
        ),
        "revenue": revenue,
        "ca_rows": ca_rows, "ca_sums": ca_sums,
        "cl_rows": cl_rows, "cl_sums": cl_sums,
        "nwc": nwc, "nwc_pct": nwc_pct, "changes": changes,
        "tickers": tickers, "excluded": excluded,
        "peers": peers, "peer_pct": peer_pct, "stats": stats,
        "bridge": bridge,
    }


# ---------------------------------------------------------------------------
# Table rendering
# ---------------------------------------------------------------------------

def _colgroup(num_hist: int, num_proj: int):
    cols = [html.Col(style={"width": f"{LABEL_W}px"})]
    cols += [html.Col(style={"width": f"{COL_W}px"}) for _ in range(num_hist)]
    cols.append(html.Col(style={"width": f"{GAP_W}px"}))
    cols += [html.Col(style={"width": f"{COL_W}px"}) for _ in range(num_proj)]
    cols.append(html.Col(style={"width": f"{GAP_W}px"}))
    cols.append(html.Col(style={"width": f"{COL_W}px"}))
    return html.Colgroup(cols)


def _row_cells(headers, num_hist, num_proj, cell_builder, extra=None):
    """Emit period cells with the two spacer columns in the right places."""
    extra = extra or {}
    cells = []
    for idx, period in enumerate(headers):
        if idx == num_hist:
            cells.append(html.Td("", style=extra))
        if idx == num_hist + num_proj:
            cells.append(html.Td("", style=extra))
        cells.append(cell_builder(idx, period))
    return cells


def _build_main_table(state: dict, calc: dict):
    headers = calc["headers"]
    num_hist = sum(1 for h in calc["is_hist"] if h)
    num_proj = len(headers) - num_hist - 1

    rows = []

    # --- band header ---
    rows.append(html.Tr([
        html.Td("", style=_LABEL),
        html.Td("Historical Financials", colSpan=num_hist, style=_HDR_BAND),
        html.Td("", style=_LABEL),
        html.Td("Projected Financials", colSpan=num_proj, style=_HDR_BAND),
        html.Td("", style=_LABEL),
        html.Td("Residual", style=_HDR_BAND),
    ]))

    # --- period labels ---
    rows.append(html.Tr(
        [html.Td("", style=_LABEL)]
        + _row_cells(headers, num_hist, num_proj,
                     lambda i, p: html.Td(p, style=_HDR_PERIOD))
    ))

    # --- FYE ---
    rows.append(html.Tr(
        [html.Td("FYE", style=_LABEL_BOLD)]
        + _row_cells(headers, num_hist, num_proj,
                     lambda i, p: html.Td(calc["fye"].get(p, ""), style=_CELL))
    ))

    def value_row(label, values, label_style, cell_style, is_pct=False,
                  border=False):
        lstyle = {**label_style, **(_BORDER_TOP if border else {})}
        cstyle = {**cell_style, **(_BORDER_TOP if border else {})}
        fmt = _fmt_pct if is_pct else _fmt_currency
        rows.append(html.Tr(
            [html.Td(label, style=lstyle)]
            + _row_cells(
                headers, num_hist, num_proj,
                lambda i, p: html.Td(fmt(values.get(p)), style=cstyle),
                extra=cstyle,
            )
        ))

    def spacer():
        rows.append(html.Tr([html.Td("", style={"height": "10px"})]))

    value_row("Total Revenue", calc["revenue"], _LABEL_BOLD, _CELL_BOLD)
    spacer()

    # --- Current Assets ---
    ca_options = [{"label": "-- None --", "value": ""}] + [
        {"label": format_ca_cl_option(k), "value": k} for k in CA_CANDIDATES
    ]
    for slot, key in enumerate(state["ca_selections"]):
        row_vals = calc["ca_rows"].get(str(slot), {})
        rows.append(html.Tr(
            [html.Td(
                dbc.Select(
                    id={"type": "nwc-ca-select", "slot": slot},
                    options=ca_options, value=key or "",
                    style=_SELECT_STYLE, size="sm",
                ),
                style={"padding": "1px 4px"},
            )]
            + _row_cells(headers, num_hist, num_proj,
                         lambda i, p: html.Td(_fmt_currency(row_vals.get(p)),
                                              style=_CELL))
        ))
    rows.append(html.Tr([html.Td([
        dbc.Button("+", id="nwc-ca-add", size="sm", color="secondary",
                   className="me-1 py-0 px-2", n_clicks=0),
        dbc.Button("−", id="nwc-ca-sub", size="sm", color="secondary",
                   className="py-0 px-2", n_clicks=0),
    ], style={"padding": "2px 4px"})]))

    value_row("Total Current Assets", calc["ca_sums"],
              _LABEL_BOLD, _CELL_BOLD, border=True)
    spacer()

    # --- Current Liabilities ---
    cl_options = [{"label": "-- None --", "value": ""}] + [
        {"label": format_ca_cl_option(k), "value": k} for k in CL_CANDIDATES
    ]
    for slot, key in enumerate(state["cl_selections"]):
        row_vals = calc["cl_rows"].get(str(slot), {})
        rows.append(html.Tr(
            [html.Td(
                dbc.Select(
                    id={"type": "nwc-cl-select", "slot": slot},
                    options=cl_options, value=key or "",
                    style=_SELECT_STYLE, size="sm",
                ),
                style={"padding": "1px 4px"},
            )]
            + _row_cells(headers, num_hist, num_proj,
                         lambda i, p: html.Td(_fmt_currency(row_vals.get(p)),
                                              style=_CELL))
        ))
    rows.append(html.Tr([html.Td([
        dbc.Button("+", id="nwc-cl-add", size="sm", color="secondary",
                   className="me-1 py-0 px-2", n_clicks=0),
        dbc.Button("−", id="nwc-cl-sub", size="sm", color="secondary",
                   className="py-0 px-2", n_clicks=0),
    ], style={"padding": "2px 4px"})]))

    value_row("Total Current Liabilities", calc["cl_sums"],
              _LABEL_BOLD, _CELL_BOLD, border=True)
    spacer()

    value_row("Net Working Capital", calc["nwc"],
              _LABEL_BOLD, _CELL_BOLD, border=True)
    value_row("Net Working Capital % of Revenue", calc["nwc_pct"],
              _LABEL_MARGIN, _CELL_MARGIN, is_pct=True)
    spacer()
    value_row("Changes in Net Working Capital", calc["changes"],
              _LABEL, _CELL, border=True)

    return html.Table(
        [_colgroup(num_hist, num_proj), html.Tbody(rows)],
        className="table table-sm table-dark mb-0",
        style={"tableLayout": "fixed", "width": "max-content",
               "minWidth": "100%", "borderCollapse": "separate",
               "borderSpacing": 0},
    )


def _build_gpc_section(state: dict, calc: dict):
    hist_periods = calc["hist_periods"]
    tickers = calc["tickers"]
    n = len(hist_periods)

    cols = [
        html.Col(style={"width": f"{EXCLUDE_W}px"}),
        html.Col(style={"width": f"{TICKER_W}px"}),
    ] + [html.Col(style={"width": f"{COL_W}px"}) for _ in range(n)]

    rows = []

    rows.append(html.Tr(
        [html.Td("Exclude (X)", style=_LABEL_BOLD),
         html.Td("Guideline Public Company", style=_LABEL_BOLD)]
        + [html.Td(p, style={**_CELL, "fontWeight": "bold"}) for p in hist_periods]
    ))

    for i, ticker in enumerate(tickers):
        excluded = calc["excluded"].get(ticker, False)
        muted = {"color": "#6b7684"} if excluded else {}
        pct_map = calc["peer_pct"].get(ticker, {})
        rows.append(html.Tr(
            [html.Td(
                dbc.Checkbox(
                    id={"type": "nwc-gpc-exclude", "slot": i},
                    value=excluded, className="m-0",
                ),
                style={"textAlign": "center", "padding": "2px"},
            ),
             html.Td(ticker, style={**_LABEL, **muted})]
            + [html.Td(_fmt_pct(pct_map.get(p)), style={**_CELL, **muted})
               for p in hist_periods]
        ))

    rows.append(html.Tr([html.Td("", style={"height": "12px"})]))

    for name in STAT_NAMES:
        by_period = calc["stats"].get(name, {})
        rows.append(html.Tr(
            [html.Td("", style=_LABEL),
             html.Td(name, style=_LABEL_BOLD)]
            + [html.Td(
                _fmt_pct(by_period.get(p)) if by_period.get(p) is not None else "NA",
                style=_CELL_BOLD,
            ) for p in hist_periods]
        ))

    rows.append(html.Tr([html.Td("", style={"height": "12px"})]))

    def bridge_row(label, node, style_l, style_c):
        pad = [html.Td("", style=_CELL) for _ in range(max(0, n - 1))]
        return html.Tr(
            [html.Td("", style=style_l), html.Td(label, style=style_l)]
            + pad + [html.Td(node, style=style_c)]
        )

    rows.append(bridge_row(
        "Selected",
        dbc.Input(
            id="nwc-selected-pct", type="text", value=state["selected_pct"],
            debounce=True, size="sm", style=_INPUT_STYLE,
        ),
        _LABEL_BOLD, {"padding": "1px 4px", "textAlign": "right"},
    ))
    rows.append(bridge_row(
        "Normalized Net Working Capital",
        _fmt_currency(calc["bridge"]["normalized_nwc"]), _LABEL, _CELL,
    ))
    rows.append(bridge_row(
        "Actual Net Working Capital",
        _fmt_currency(calc["bridge"]["actual_nwc"]), _LABEL, _CELL,
    ))
    rows.append(bridge_row(
        "Net Working Capital Surplus/(Deficit)",
        _fmt_currency(calc["bridge"]["surplus_deficit"]),
        {**_LABEL_BOLD, **_EMPHASIS}, {**_CELL_BOLD, **_EMPHASIS},
    ))

    return html.Table(
        [html.Colgroup(cols), html.Tbody(rows)],
        className="table table-sm table-dark mb-0",
        style={"tableLayout": "fixed", "width": "max-content",
               "minWidth": "100%", "borderCollapse": "separate",
               "borderSpacing": 0},
    )


def _build_chart(entity: str, calc: dict) -> go.Figure:
    periods = calc["hist_periods"]

    if entity and entity != "Subject":
        series = calc["peers"].get(entity, {})
        nwc_src = series.get("nwc", {})
        rev_src = series.get("rev", {})
        pct_src = series.get("pct", {})
    else:
        entity = "Subject"
        nwc_src = calc["nwc"]
        rev_src = calc["revenue"]
        pct_src = calc["nwc_pct"]

    nwc_vals = [nwc_src.get(p) for p in periods]
    rev_vals = [rev_src.get(p) for p in periods]
    pct_vals = [None if pct_src.get(p) is None else pct_src[p] * 100
                for p in periods]

    fig = go.Figure()
    fig.add_bar(
        x=periods, y=[v if v is not None else 0 for v in nwc_vals],
        name="Net Working Capital", marker_color=CHART_BAR, yaxis="y",
    )
    fig.add_scatter(
        x=periods, y=rev_vals, name="Revenue", mode="lines+markers",
        line=dict(color=CHART_REV, width=2), marker=dict(symbol="square", size=7),
        yaxis="y", connectgaps=False,
    )
    fig.add_scatter(
        x=periods, y=pct_vals, name="NWC % of Revenue", mode="lines+markers",
        line=dict(color=CHART_PCT, width=2), marker=dict(size=7),
        yaxis="y2", connectgaps=False,
    )

    fig.update_layout(
        title=dict(text=f"{entity} — Net Working Capital vs. % of Revenue",
                   font=dict(color=CHART_TEXT, size=13)),
        paper_bgcolor=CHART_BG, plot_bgcolor=CHART_BG,
        font=dict(color=CHART_AXIS, size=11),
        margin=dict(l=60, r=60, t=50, b=40), height=380,
        legend=dict(orientation="h", y=1.12, x=0,
                    bgcolor="rgba(0,0,0,0)", font=dict(size=10)),
        xaxis=dict(gridcolor=CHART_GRID, zerolinecolor=CHART_GRID),
        yaxis=dict(title="Net Working Capital & Revenue ($)",
                   gridcolor=CHART_GRID, zerolinecolor=CHART_GRID,
                   tickformat=",.0f"),
        yaxis2=dict(title="NWC % of Revenue", overlaying="y", side="right",
                    showgrid=False, ticksuffix="%"),
    )
    return fig


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------

layout = dbc.Container([
    dbc.Card([
        dbc.CardBody([
            dbc.Row([
                dbc.Col(html.Div(id="nwc-title", className="fw-bold text-light"),
                        xs=12, md=True, className="d-flex align-items-center"),
                dbc.Col(html.Div([
                    dbc.Label("Hist Yrs", className="me-1 mb-0 text-muted small"),
                    dbc.Input(id="nwc-hist-years", type="number", min=1, max=5,
                              step=1, value=5, debounce=True, size="sm",
                              style={"width": "58px", "height": "27px",
                                     "fontSize": "12px"}),
                ], className="d-flex align-items-center"), xs="auto"),
                dbc.Col(html.Div([
                    dbc.Label("Proj Yrs", className="me-1 mb-0 text-muted small"),
                    dbc.Input(id="nwc-proj-years", type="number", min=1, max=20,
                              step=1, value=5, debounce=True, size="sm",
                              style={"width": "58px", "height": "27px",
                                     "fontSize": "12px"}),
                ], className="d-flex align-items-center"), xs="auto"),
                dbc.Col(html.Div([
                    dbc.Label("Cash Treatment", className="me-1 mb-0 text-muted small"),
                    dbc.Select(id="nwc-cash-treatment",
                               options=[{"label": "Excluding Cash", "value": "Excluding Cash"},
                                        {"label": "Including Cash", "value": "Including Cash"}],
                               value="Excluding Cash", size="sm",
                               style={"width": "150px", "height": "27px",
                                      "fontSize": "12px"}),
                ], className="d-flex align-items-center"), xs="auto"),
                dbc.Col(html.Div([
                    dbc.Label("NWC Basis", className="me-1 mb-0 text-muted small"),
                    dbc.Select(id="nwc-basis",
                               options=[{"label": "% of Revenue", "value": "% of Revenue"},
                                        {"label": "Turnover Ratios", "value": "Turnover Ratios"}],
                               value="% of Revenue", size="sm",
                               style={"width": "140px", "height": "27px",
                                      "fontSize": "12px"}),
                ], className="d-flex align-items-center"), xs="auto"),
            ], className="align-items-center g-2"),
        ], className="py-1 px-2")
    ], color="dark", outline=True, className="mb-2 border-secondary"),

    dbc.Card([
        dbc.CardBody([
            html.Div(id="nwc-table-container",
                     style={"overflowX": "auto", "minWidth": 0}),
        ], className="p-2")
    ], color="secondary", outline=True, className="mb-2"),

    dbc.Row([
        dbc.Col(dbc.Card([
            dbc.CardHeader("Net Working Capital % of Revenue",
                           className="fw-bold text-light py-1 px-2"),
            dbc.CardBody([
                html.Div(id="nwc-gpc-container",
                         style={"overflowX": "auto", "minWidth": 0}),
            ], className="p-2"),
        ], color="secondary", outline=True), lg=7, className="mb-2"),

        dbc.Col(dbc.Card([
            dbc.CardHeader(dbc.Row([
                dbc.Col("Net Working Capital vs. % of Revenue",
                        className="fw-bold text-light",
                        style={"paddingTop": "4px"}),
                dbc.Col(dbc.Select(id="nwc-chart-entity", options=[],
                                   value="Subject", size="sm",
                                   style={"width": "130px", "height": "27px",
                                          "fontSize": "12px"}),
                        xs="auto"),
            ], className="g-1 align-items-center"), className="py-1 px-2"),
            dbc.CardBody([
                dcc.Graph(id="nwc-chart", config={"displayModeBar": False}),
            ], className="p-1"),
        ], color="secondary", outline=True), lg=5, className="mb-2"),
    ], className="g-2"),
], fluid=True, className="px-2")


# ---------------------------------------------------------------------------
# Hydrate static controls on arrival / session load
# ---------------------------------------------------------------------------

@callback(
    Output("nwc-hist-years", "value"),
    Output("nwc-proj-years", "value"),
    Output("nwc-cash-treatment", "value"),
    Output("nwc-basis", "value"),
    Input("_pages_location", "pathname"),
    Input("session-load-timestamp", "data"),
    State("session-store", "data"),
)
def hydrate_nwc_controls(pathname, _load_ts, session_data):
    if pathname not in ("/nwc", "/nwc/"):
        return (no_update,) * 4
    state = _state_from_session(session_data)
    inputs = dict_to_project_inputs(session_data or {})
    return (
        state["historical_years"],
        inputs.projection_years,
        state["cash_treatment"],
        state["nwc_basis"],
    )


# ---------------------------------------------------------------------------
# Render table + GPC section
# ---------------------------------------------------------------------------

from web.lib.nwc_data import get_nwc_results, nwc_state_from_session

@callback(
    Output("nwc-table-container", "children"),
    Output("nwc-gpc-container", "children"),
    Output("nwc-chart-entity", "options"),
    Output("nwc-title", "children"),
    Input("_pages_location", "pathname"),
    Input("session-store", "data"),
    Input("session-load-timestamp", "data"),
    Input("source-results-store", "data"),
)
def render_nwc(pathname, session_data, _load_ts, source_results):
    if pathname not in ("/nwc", "/nwc/"):
        return no_update, no_update, no_update, no_update

    state = _state_from_session(session_data)
    calc = get_nwc_results(session_data, source_results)
    inputs = calc["inputs"]

    title = (
        f"{inputs.client} · {inputs.subject_company_name} · "
        f"Net Working Capital Schedule"
    )
    entity_options = (
        [{"label": "Subject", "value": "Subject"}]
        + [{"label": t, "value": t} for t in calc["tickers"]]
    )

    return (
        _build_main_table(state, calc),
        _build_gpc_section(state, calc),
        entity_options,
        title,
    )


# ---------------------------------------------------------------------------
# Chart
# ---------------------------------------------------------------------------

@callback(
    Output("nwc-chart", "figure"),
    Input("_pages_location", "pathname"),
    Input("nwc-chart-entity", "value"),
    Input("session-store", "data"),
    Input("source-results-store", "data"),
)
def render_nwc_chart(pathname, entity, session_data, source_results):
    if pathname not in ("/nwc", "/nwc/"):
        return no_update
    state = _state_from_session(session_data)
    calc = _compute(session_data, source_results, state)
    return _build_chart(entity or "Subject", calc)


# ---------------------------------------------------------------------------
# Persist
# ---------------------------------------------------------------------------

def _harvest(ids, values, fallback: List[str], count: int) -> List[str]:
    """Rebuild the selection list from slot-tagged pattern inputs."""
    out = list(fallback)
    while len(out) < count:
        out.append("")
    for cell_id, val in zip(ids or [], values or []):
        if not isinstance(cell_id, dict):
            continue
        try:
            slot = int(cell_id.get("slot"))
        except (TypeError, ValueError):
            continue
        while len(out) <= slot:
            out.append("")
        out[slot] = "" if val is None else str(val)
    return out[:count]


@callback(
    Output("session-store", "data", allow_duplicate=True),
    Input("nwc-hist-years", "value"),
    Input("nwc-proj-years", "value"),
    Input("nwc-cash-treatment", "value"),
    Input("nwc-basis", "value"),
    Input("nwc-selected-pct", "value", allow_optional=True),
    Input({"type": "nwc-ca-select", "slot": ALL}, "value"),
    Input({"type": "nwc-cl-select", "slot": ALL}, "value"),
    Input({"type": "nwc-gpc-exclude", "slot": ALL}, "value"),
    Input("nwc-ca-add", "n_clicks", allow_optional=True),
    Input("nwc-ca-sub", "n_clicks", allow_optional=True),
    Input("nwc-cl-add", "n_clicks", allow_optional=True),
    Input("nwc-cl-sub", "n_clicks", allow_optional=True),
    State({"type": "nwc-ca-select", "slot": ALL}, "id"),
    State({"type": "nwc-cl-select", "slot": ALL}, "id"),
    State({"type": "nwc-gpc-exclude", "slot": ALL}, "id"),
    State("session-store", "data"),
    State("source-results-store", "data"),
    prevent_initial_call=True,
)
def persist_nwc(hist_years, proj_years, cash_treatment, nwc_basis, selected_pct,
                ca_values, cl_values, exclude_values,
                _ca_add, _ca_sub, _cl_add, _cl_sub,
                ca_ids, cl_ids, exclude_ids,
                session_data, source_results):
    trigger = ctx.triggered_id
    if not trigger:
        return no_update

    session_data = dict(session_data or {})
    prev_raw = dict(session_data.get("nwc_page_state") or {})
    state = _state_from_session(session_data)

    ca_count = state["ca_row_count"]
    cl_count = state["cl_row_count"]

    if trigger == "nwc-ca-add":
        ca_count = min(CA_MAX_ROWS, ca_count + 1)
    elif trigger == "nwc-ca-sub":
        ca_count = max(1, ca_count - 1)
    elif trigger == "nwc-cl-add":
        cl_count = min(CL_MAX_ROWS, cl_count + 1)
    elif trigger == "nwc-cl-sub":
        cl_count = max(1, cl_count - 1)

    ca_sel = _harvest(ca_ids, ca_values, state["ca_selections"], ca_count)
    cl_sel = _harvest(cl_ids, cl_values, state["cl_selections"], cl_count)

    exclusions = list(state["gpc_exclusions"])
    tickers = list(dict_to_project_inputs(session_data).gpc_tickers or [])
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

    try:
        hist_years = max(1, min(5, int(hist_years)))
    except (TypeError, ValueError):
        hist_years = state["historical_years"]

    new_state = {
        "historical_years": hist_years,
        "ca_row_count": ca_count,
        "cl_row_count": cl_count,
        "ca_selections": ca_sel,
        "cl_selections": cl_sel,
        "cash_treatment": cash_treatment or state["cash_treatment"],
        "nwc_basis": nwc_basis or state["nwc_basis"],
        "selected_pct": (
            selected_pct if selected_pct is not None else state["selected_pct"]
        ),
        "gpc_exclusions": exclusions,
    }

    # Projection Years is the shared, global value (Home / DCF / NWC).
    # Historical Years stays local to this page.
    try:
        py = max(1, min(20, int(proj_years)))
    except (TypeError, ValueError):
        py = None

    proj_changed = py is not None and py != session_data.get("projection_years")
    if proj_changed:
        session_data["projection_years"] = py

    # Cache computed outputs so GPC (and later DCF) read, not recompute.
    calc = _compute(session_data, source_results, _state_from_session(
        {**session_data, "nwc_page_state": new_state}
    ))
    new_state.update({
        "nwc_by_period": calc["nwc"],
        "nwc_pct_by_period": calc["nwc_pct"],
        "changes_in_nwc": calc["changes"],
        "normalized_nwc": calc["bridge"]["normalized_nwc"],
        "actual_nwc": calc["bridge"]["actual_nwc"],
        "surplus_deficit": calc["bridge"]["surplus_deficit"],
    })

    # No-op guard: a remount wave re-fires every pattern Input with the
    # values it was just given. Writing an identical dict would bounce
    # render -> persist -> render forever.
    if not proj_changed and new_state == prev_raw:
        return no_update

    session_data["nwc_page_state"] = new_state
    return session_data