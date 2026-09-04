"""
web/pages/gpc.py

Guideline Public Company (GPC) comparable multiples analysis.

Header (dropdowns) and body (data rows) are built by SEPARATE callbacks.
This matters: dcc.Dropdown components torn down and recreated on every
render lose their visually-selected label even when `value` is
technically correct underneath (a known Dash gotcha). Splitting means
the header only rebuilds when num_multiples/basis actually change —
picking a value, toggling an exclude checkbox, etc. no longer remounts
the dropdowns, so the selection visibly sticks.

Statistics and Selected Multiples tables have NO header row of their
own — they inherit column position from the real dropdown headers in
the ticker grid directly above them. Their leading blank cell is sized
to match the ticker grid's combined Exclude+#+Ticker+Company width
exactly, so their value columns start at the same x-position.
"""

import statistics
import dash
import dash_bootstrap_components as dbc
from dash import html, dcc, Input, Output, State, callback, ALL

from web.lib.session_io import dict_to_project_inputs
from Canneberge.Calculations.gpc_multiples import compute_all_gpc_multiples
from Canneberge.Calculations.gpc_metrics import GPC_METRICS, dropdown_options, CUSTOM_MULTIPLE_LABEL

dash.register_page(__name__, path="/gpc", name="GPC Metrics")

MAX_COLS_CAP = 7
STAT_NAMES = ["Maximum", "Third Quartile", "Average", "Median", "First Quartile", "Minimum"]

COL_W = {"exclude": 70, "num": 30, "ticker": 70, "company": 180, "metric": 140}
LEADING_W = COL_W["exclude"] + COL_W["num"] + COL_W["ticker"] + COL_W["company"]


def _quartile(sorted_vals, q):
    if not sorted_vals:
        return None
    n = len(sorted_vals)
    if n == 1:
        return sorted_vals[0]
    pos = q * (n - 1)
    lo = int(pos)
    hi = min(lo + 1, n - 1)
    frac = pos - lo
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * frac


def _compute_stats(values):
    vals = sorted(v for v in values if v is not None)
    if not vals:
        return {name: None for name in STAT_NAMES}
    return {
        "Maximum": vals[-1],
        "Third Quartile": _quartile(vals, 0.75),
        "Average": sum(vals) / len(vals),
        "Median": statistics.median(vals),
        "First Quartile": _quartile(vals, 0.25),
        "Minimum": vals[0],
    }


def _default_metric_for_col(idx: int) -> str:
    if idx < len(GPC_METRICS):
        return GPC_METRICS[idx].display_name
    return GPC_METRICS[0].display_name


# -------------------------------------------------------------
# LAYOUT
# -------------------------------------------------------------
layout = dbc.Container([
    dbc.Card([
        dbc.CardBody([
            dbc.Row([
                dbc.Col([
                    dbc.Label("How Many Multiples:", className="me-2 mb-0 text-muted"),
                    dbc.Input(
                        id="gpc-num-multiples",
                        type="number", min=1, max=MAX_COLS_CAP, step=1, value=MAX_COLS_CAP,
                        style={"width": "70px"}, size="sm", debounce=True,
                        className="d-inline-block",
                    ),
                ], xs=12, md="auto", className="mb-2 mb-md-0"),

                dbc.Col([
                    dbc.Label("Basis", className="me-2 mb-0 text-muted"),
                    dbc.RadioItems(
                        id="gpc-basis-toggle",
                        options=[
                            {"label": "BEV (Enterprise Value)", "value": "BEV"},
                            {"label": "Equity (Market Cap)", "value": "EQUITY"},
                        ],
                        value="BEV",
                        inline=True,
                        inputClassName="btn-check",
                        labelClassName="btn btn-outline-info size-sm",
                        labelCheckedClassName="active",
                        persistence=True,
                        persistence_type="session",
                    ),
                ], xs=12, md="auto"),

                dbc.Col([
                    dbc.Label("DLOC %", className="me-2 mb-0 text-muted"),
                    dbc.Input(id="gpc-dloc-pct", type="text", value="0%",
                              style={"width": "80px"}, debounce=True, size="sm",
                              className="d-inline-block"),
                ], xs=6, md="auto"),

                dbc.Col([
                    dbc.Label("Control Premium %", className="me-2 mb-0 text-muted"),
                    dbc.Input(id="gpc-control-premium-pct", type="text", value="0%",
                              style={"width": "80px"}, debounce=True, size="sm",
                              className="d-inline-block"),
                ], xs=6, md="auto"),
            ], className="align-items-center g-3"),
        ])
    ], color="dark", outline=True, className="mb-3 border-secondary"),

    dbc.Card([
        dbc.CardHeader("Guideline Public Company Multiple(s)", className="fw-bold text-light"),
        dbc.CardBody([
            html.Div(id="gpc-header-container", style={"overflowX": "auto"}),
            html.Div(id="gpc-body-container", style={"overflowX": "auto"}),
        ], className="p-2")
    ], color="secondary", outline=True, className="mb-3"),

    dbc.Card([
        dbc.CardHeader("Statistics", className="fw-bold text-light"),
        dbc.CardBody([
            html.Div(id="gpc-stats-container", style={"overflowX": "auto"})
        ], className="p-2")
    ], color="secondary", outline=True, className="mb-3"),

    dbc.Card([
        dbc.CardHeader("Selected Multiples", className="fw-bold text-light"),
        dbc.CardBody([
            html.Div(id="gpc-selected-multiples-container", style={"overflowX": "auto"})
        ], className="p-2")
    ], color="secondary", outline=True, className="mb-3"),

    dbc.Card([
        dbc.CardHeader("Subject Company", className="fw-bold text-muted"),
        dbc.CardBody(html.Div("PLACEHOLDER — not yet built", className="text-muted fst-italic"))
    ], color="secondary", outline=True, className="mb-3 opacity-50"),

    dbc.Card([
        dbc.CardHeader("Weighting", className="fw-bold text-muted"),
        dbc.CardBody(html.Div("PLACEHOLDER — not yet built", className="text-muted fst-italic"))
    ], color="secondary", outline=True, className="mb-3 opacity-50"),

    dbc.Card([
        dbc.CardHeader("Bridge to Fair Value of Equity", className="fw-bold text-muted"),
        dbc.CardBody(html.Div("PLACEHOLDER — not yet built", className="text-muted fst-italic"))
    ], color="secondary", outline=True, className="mb-3 opacity-50"),

    dcc.Store(id="gpc-exclude-store", data={}, storage_type="session"),
], fluid=True, className="px-2")


def _fixed_header_cells():
    return [
        html.Th("Exclude", style={"minWidth": f"{COL_W['exclude']}px"}),
        html.Th("#", style={"minWidth": f"{COL_W['num']}px"}),
        html.Th("Ticker", style={"minWidth": f"{COL_W['ticker']}px"}),
        html.Th("Company Name", style={"minWidth": f"{COL_W['company']}px"}),
    ]


# -------------------------------------------------------------
# CALLBACK 1 — HEADER ONLY. Rebuilds only when num_multiples or
# basis change. The dropdown components stay mounted across every
# other interaction (exclude toggles, etc.), so the selected label
# never gets wiped by a remount.
# -------------------------------------------------------------
@callback(
    Output("gpc-header-container", "children"),
    Input("gpc-num-multiples", "value"),
    Input("gpc-basis-toggle", "value"),
)
def render_header(num_multiples, basis_mode):
    basis_mode = basis_mode or "BEV"
    try:
        num_cols = max(1, min(MAX_COLS_CAP, int(num_multiples or MAX_COLS_CAP)))
    except (TypeError, ValueError):
        num_cols = MAX_COLS_CAP

    options = dropdown_options(basis_mode)
    header_cells = _fixed_header_cells() + [
        html.Th(
            dcc.Dropdown(
                id={"type": "gpc-metric-col", "index": i},
                options=options,
                value=_default_metric_for_col(i) if _default_metric_for_col(i) in options else options[0],
                clearable=False,
                className="dbc",
                style={"fontSize": "12px", "minWidth": f"{COL_W['metric'] - 10}px"},
            ),
            style={"minWidth": f"{COL_W['metric']}px"},
        )
        for i in range(num_cols)
    ]
    table = html.Table(
        [html.Thead(html.Tr(header_cells))],
        className="table table-sm table-dark mb-0",
        style={"width": "max-content", "minWidth": "100%"},
    )
    return table


# -------------------------------------------------------------
# CALLBACK 2 — persist exclude-checkbox state
# -------------------------------------------------------------
@callback(
    Output("gpc-exclude-store", "data"),
    Input({"type": "gpc-exclude-chk", "ticker": ALL}, "value"),
    State({"type": "gpc-exclude-chk", "ticker": ALL}, "id"),
    State("gpc-exclude-store", "data"),
    prevent_initial_call=True,
)
def persist_exclude_state(values, ids, existing):
    existing = dict(existing or {})
    for val, id_dict in zip(values, ids):
        existing[id_dict["ticker"]] = bool(val)
    return existing


# -------------------------------------------------------------
# CALLBACK 3 — BODY, STATISTICS, SELECTED MULTIPLES. Reads the
# header dropdowns' LIVE values directly via pattern-matching
# Input — no separate persistence store needed, since these values
# are read, never written, by this callback.
# -------------------------------------------------------------
@callback(
    Output("gpc-body-container", "children"),
    Output("gpc-stats-container", "children"),
    Output("gpc-selected-multiples-container", "children"),
    Input({"type": "gpc-metric-col", "index": ALL}, "value"),
    Input("gpc-exclude-store", "data"),
    Input("session-store", "data"),
    Input("source-results-store", "data"),
)
def render_body(metric_col_values, exclude_map, session_data, source_results):
    inputs = dict_to_project_inputs(session_data or {})
    tickers = inputs.gpc_tickers or []
    exclude_map = exclude_map or {}
    metric_col_values = metric_col_values or []

    if not tickers:
        return dbc.Alert("No GPC tickers configured on the Home page.", color="warning"), "", ""

    sa = (source_results or {}).get("stockanalysis", {}) if source_results else {}
    is_rows = sa.get("IS", [])
    bs_rows = sa.get("BS", [])
    ratio_rows = sa.get("Ratios", [])
    ms_rows = (source_results or {}).get("marketscreener", []) if source_results else []

    if not is_rows and not ratio_rows:
        return dbc.Alert("No source data loaded yet — refresh from the Source Data page first.",
                          color="warning"), "", ""

    # basis_mode isn't a direct Input here (it drives the header
    # callback); infer it from whether the chosen metrics belong to
    # the BEV or EQUITY option set, defaulting to BEV.
    basis_mode = "EQUITY" if any(m in dropdown_options("EQUITY") and m not in dropdown_options("BEV")
                                  for m in metric_col_values) else "BEV"

    all_multiples = compute_all_gpc_multiples(is_rows, ms_rows, ratio_rows, bs_rows, tickers, basis_mode=basis_mode)
    included_tickers = [t for t in tickers if not exclude_map.get(t, False)]

    # --- Body rows (no header — header lives in the sibling
    # gpc-header-container, built by render_header) ---
    body_rows = []
    for idx, ticker in enumerate(tickers):
        is_excluded = exclude_map.get(ticker, False)
        row_multiples = all_multiples.get(ticker, {})
        cells = [
            html.Td(dbc.Checkbox(id={"type": "gpc-exclude-chk", "ticker": ticker}, value=is_excluded),
                     style={"minWidth": f"{COL_W['exclude']}px"}),
            html.Td(str(idx + 1), style={"minWidth": f"{COL_W['num']}px"}),
            html.Td(ticker.upper(), style={"minWidth": f"{COL_W['ticker']}px"}),
            html.Td("", style={"minWidth": f"{COL_W['company']}px"}),
        ]
        for col_metric in metric_col_values:
            val = row_multiples.get(col_metric) if col_metric != CUSTOM_MULTIPLE_LABEL else None
            cells.append(html.Td(f"{val:.2f}x" if val is not None else "NA",
                                  style={"textAlign": "right", "minWidth": f"{COL_W['metric']}px"}))
        body_rows.append(html.Tr(cells, style={"opacity": "0.4" if is_excluded else "1.0"}))

    body_table = html.Table(
        [html.Tbody(body_rows)],
        className="table table-sm table-dark mb-0",
        style={"width": "max-content", "minWidth": "100%"},
    )

    # --- Statistics: no header row at all — position inherited
    # from the real dropdown headers above. Leading cell width
    # matches Exclude+#+Ticker+Company combined exactly. ---
    stats_rows = []
    for stat_name in STAT_NAMES:
        cells = [html.Td(stat_name, style={"fontWeight": "bold", "minWidth": f"{LEADING_W}px"})]
        for col_metric in metric_col_values:
            vals = [all_multiples.get(t, {}).get(col_metric) for t in included_tickers]
            v = _compute_stats(vals)[stat_name]
            cells.append(html.Td(f"{v:.2f}x" if v is not None else "NA",
                                  style={"textAlign": "right", "minWidth": f"{COL_W['metric']}px"}))
        stats_rows.append(html.Tr(cells))

    stats_table = html.Table(
        [html.Tbody(stats_rows)],
        className="table table-sm table-dark mb-0",
        style={"width": "max-content", "minWidth": "100%"},
    )

    # --- Selected Multiples: same leading-width fix ---
    high_cells = [html.Td("Selected Multiple — High",
                           style={"fontWeight": "bold", "minWidth": f"{LEADING_W}px"})]
    low_cells = [html.Td("Selected Multiple — Low",
                          style={"fontWeight": "bold", "minWidth": f"{LEADING_W}px"})]
    for col_metric in metric_col_values:
        vals = [all_multiples.get(t, {}).get(col_metric) for t in included_tickers]
        med = _compute_stats(vals)["Median"]
        default_val = f"{med:.2f}" if med is not None else ""
        high_cells.append(html.Td(
            dbc.Input(id={"type": "gpc-selected-high", "metric": col_metric}, type="text",
                      value=default_val, size="sm",
                      style={"width": "90px", "textAlign": "right"}, debounce=True),
            style={"minWidth": f"{COL_W['metric']}px"},
        ))
        low_cells.append(html.Td(
            dbc.Input(id={"type": "gpc-selected-low", "metric": col_metric}, type="text",
                      value=default_val, size="sm",
                      style={"width": "90px", "textAlign": "right"}, debounce=True),
            style={"minWidth": f"{COL_W['metric']}px"},
        ))

    selected_table = html.Table(
        [html.Tbody([html.Tr(high_cells), html.Tr(low_cells)])],
        className="table table-sm table-dark mb-0",
        style={"width": "max-content", "minWidth": "100%"},
    )

    return body_table, stats_table, selected_table