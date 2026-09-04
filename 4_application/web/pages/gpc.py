"""
web/pages/gpc.py

Guideline Public Company (GPC) comparable multiples analysis.
Matches the desktop Canneberge/Ui/gpc_page.py structure section-by-section
(see that file's _build_* method order). This increment covers:
    Controls -> Ticker section -> Statistics -> Selected Multiples
Subject-company application, Weighting, and the Bridge-to-equity section
are NOT yet built (they depend on cash/NWC data not yet wired here) —
see _build_subject_section / _build_weighting_section / _build_bridge_section
in the desktop file for the next increment.
"""

import statistics
import dash
import dash_bootstrap_components as dbc
from dash import html, dcc, Input, Output, State, callback, ALL

from web.lib.session_io import dict_to_project_inputs
from Canneberge.Calculations.gpc_multiples import compute_all_gpc_multiples
from Canneberge.Calculations.gpc_metrics import GPC_METRICS, dropdown_options, CUSTOM_MULTIPLE_LABEL

dash.register_page(__name__, path="/gpc", name="GPC Metrics")

MAX_COLS = 7   # matches desktop MultipleCount named range
STAT_NAMES = ["Maximum", "Third Quartile", "Average", "Median", "First Quartile", "Minimum"]


def _quartile(sorted_vals, q):
    """Simple linear-interpolation quartile, no numpy dependency here."""
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
    # --- Controls ---
    dbc.Card([
        dbc.CardBody([
            dbc.Row([
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
                ], xs=12, md="auto", className="mb-2 mb-md-0"),

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

    # --- Per-column metric pickers ---
    dbc.Card([
        dbc.CardHeader("Guideline Public Company Multiple(s)", className="fw-bold text-light"),
        dbc.CardBody([
            dbc.Row([
                dbc.Col([
                    dbc.Label(f"Col {i + 1}", className="text-muted small mb-1 d-block"),
                    dcc.Dropdown(
                        id={"type": "gpc-metric-col", "index": i},
                        options=[],  # populated by sync_metric_options
                        value=None,
                        clearable=False,
                        style={"fontSize": "12px"},
                    ),
                ], xs=6, md=True)
                for i in range(MAX_COLS)
            ], className="g-2"),
        ])
    ], color="secondary", outline=True, className="mb-3"),

    # --- Ticker grid (exclude toggle + per-column multiple values) ---
    dbc.Card([
        dbc.CardBody([
            html.Div(id="gpc-ticker-grid-container")
        ], className="p-2")
    ], color="secondary", outline=True, className="mb-3"),

    # --- Statistics ---
    dbc.Card([
        dbc.CardHeader("Statistics", className="fw-bold text-light"),
        dbc.CardBody([
            html.Div(id="gpc-stats-container")
        ], className="p-2")
    ], color="secondary", outline=True, className="mb-3"),

    # --- Selected Multiples (editable High/Low per column) ---
    dbc.Card([
        dbc.CardHeader("Selected Multiples", className="fw-bold text-light"),
        dbc.CardBody([
            html.Div(id="gpc-selected-multiples-container")
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
    dcc.Store(id="gpc-selected-store", data={}, storage_type="session"),
], fluid=True, className="px-2")


# -------------------------------------------------------------
# CALLBACK — populate each column's metric dropdown options
# (depends only on basis mode, same options list for every column)
# -------------------------------------------------------------
@callback(
    Output({"type": "gpc-metric-col", "index": ALL}, "options"),
    Output({"type": "gpc-metric-col", "index": ALL}, "value"),
    Input("gpc-basis-toggle", "value"),
)
def sync_metric_options(basis_mode):
    basis_mode = basis_mode or "BEV"
    options = dropdown_options(basis_mode)
    values = [_default_metric_for_col(i) if _default_metric_for_col(i) in options else options[0]
              for i in range(MAX_COLS)]
    return [options] * MAX_COLS, values


# -------------------------------------------------------------
# CALLBACK — build the ticker grid, run the calc, populate stats
# -------------------------------------------------------------
@callback(
    Output("gpc-ticker-grid-container", "children"),
    Output("gpc-stats-container", "children"),
    Output("gpc-selected-multiples-container", "children"),
    Input("gpc-basis-toggle", "value"),
    Input({"type": "gpc-metric-col", "index": ALL}, "value"),
    Input("gpc-exclude-store", "data"),
    Input("session-store", "data"),
    Input("source-results-store", "data"),
)
def render_gpc_page(basis_mode, metric_col_values, exclude_map, session_data, source_results):
    inputs = dict_to_project_inputs(session_data or {})
    basis_mode = basis_mode or "BEV"
    tickers = inputs.gpc_tickers or []
    exclude_map = exclude_map or {}

    if not tickers:
        msg = dbc.Alert("No GPC tickers configured on the Home page.", color="warning")
        return msg, "", ""

    sa = (source_results or {}).get("stockanalysis", {}) if source_results else {}
    is_rows = sa.get("IS", [])
    bs_rows = sa.get("BS", [])
    ratio_rows = sa.get("Ratios", [])
    ms_rows = (source_results or {}).get("marketscreener", []) if source_results else []

    if not is_rows and not ratio_rows:
        msg = dbc.Alert("No source data loaded yet — refresh from the Source Data page first.", color="warning")
        return msg, "", ""

    all_multiples = compute_all_gpc_multiples(is_rows, ms_rows, ratio_rows, bs_rows, tickers, basis_mode=basis_mode)

    metric_col_values = metric_col_values or [_default_metric_for_col(i) for i in range(MAX_COLS)]

    # --- Ticker grid ---
    header_row = html.Tr([
        html.Th("Exclude"), html.Th("#"), html.Th("Ticker"), html.Th("Company"),
    ] + [html.Th(metric_col_values[i] or "") for i in range(MAX_COLS)])

    body_rows = []
    for idx, ticker in enumerate(tickers):
        is_excluded = exclude_map.get(ticker, False)
        row_multiples = all_multiples.get(ticker, {})
        cells = [
            html.Td(dbc.Checkbox(
                id={"type": "gpc-exclude-chk", "ticker": ticker},
                value=is_excluded,
            )),
            html.Td(str(idx + 1)),
            html.Td(ticker.upper()),
            html.Td(""),  # company name — not yet piped in from Home page ticker grid
        ]
        for col_metric in metric_col_values:
            val = row_multiples.get(col_metric) if col_metric != CUSTOM_MULTIPLE_LABEL else None
            cells.append(html.Td(f"{val:.2f}x" if val is not None else "NA",
                                  style={"textAlign": "right"}))
        body_rows.append(html.Tr(cells, style={"opacity": "0.4" if is_excluded else "1.0"}))

    ticker_table = html.Table(
        [html.Thead(header_row), html.Tbody(body_rows)],
        className="table table-sm table-dark mb-0",
    )

    # --- Statistics (only over non-excluded rows) --
    included_tickers = [t for t in tickers if not exclude_map.get(t, False)]
    stats_rows = []
    for stat_name in STAT_NAMES:
        cells = [html.Td(stat_name, style={"fontWeight": "bold"})]
        for col_metric in metric_col_values:
            vals = [all_multiples.get(t, {}).get(col_metric) for t in included_tickers]
            stat_vals = _compute_stats(vals)
            v = stat_vals[stat_name]
            cells.append(html.Td(f"{v:.2f}x" if v is not None else "NA", style={"textAlign": "right"}))
        stats_rows.append(html.Tr(cells))

    stats_table = html.Table(
        [html.Tbody(stats_rows)],
        className="table table-sm table-dark mb-0",
    )

    # --- Selected Multiples (pre-filled from Median, user can override) ---
    median_row_cells_high = [html.Td("Selected Multiple — High", style={"fontWeight": "bold"})]
    median_row_cells_low = [html.Td("Selected Multiple — Low", style={"fontWeight": "bold"})]
    for col_metric in metric_col_values:
        vals = [all_multiples.get(t, {}).get(col_metric) for t in included_tickers]
        med = _compute_stats(vals)["Median"]
        default_val = f"{med:.2f}" if med is not None else ""
        median_row_cells_high.append(html.Td(
            dbc.Input(
                id={"type": "gpc-selected-high", "metric": col_metric},
                type="text", value=default_val, size="sm",
                style={"width": "80px", "textAlign": "right"},
                debounce=True,
            )
        ))
        median_row_cells_low.append(html.Td(
            dbc.Input(
                id={"type": "gpc-selected-low", "metric": col_metric},
                type="text", value=default_val, size="sm",
                style={"width": "80px", "textAlign": "right"},
                debounce=True,
            )
        ))

    selected_table = html.Table(
        [html.Tbody([html.Tr(median_row_cells_high), html.Tr(median_row_cells_low)])],
        className="table table-sm table-dark mb-0",
    )

    return ticker_table, stats_table, selected_table


# -------------------------------------------------------------
# CALLBACK — persist exclude-checkbox state
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