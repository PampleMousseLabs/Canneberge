"""
web/pages/gt.py

Guideline Transaction (GT) comparable multiples analysis.

Header (dropdowns) and body (data rows) are built by SEPARATE callbacks
to preserve focused input states, matching GPC's architecture exactly.

Statistics, Selected, Subject, and Weighting tables have NO headers of
their own — they inherit column positions from the real dropdown headers
directly above them by using matching fixed column widths.

The Bridge is a separate card below where High and Low columns align
pixel-perfectly under the first two metric columns.
"""

import statistics
import dash
import dash_bootstrap_components as dbc
from dash import html, dcc, Input, Output, State, callback, ALL, no_update, ctx

from web.lib.session_io import dict_to_project_inputs
from web.lib.subject_metrics import get_subject_metric_value
from web.lib.gt_data import (
    gt_state_from_session, get_gt_results,
    METRICS, MAX_COLS, MAX_ROWS, STAT_NAMES,
    _fmt_multiple, _fmt_currency, _fmt_pct,
)
from web.components.gt_range_chart import gt_range_chart

dash.register_page(__name__, path="/gt", name="GT")


COL_W = {"exclude": 70, "num": 30, "date": 90, "target": 180, "acquirer": 180, "metric": 120}
LEADING_W = COL_W["exclude"] + COL_W["num"] + COL_W["date"] + COL_W["target"] + COL_W["acquirer"]


def _col_style(name, **extra):
    w = f"{COL_W[name]}px"
    base = {"width": w, "minWidth": w, "maxWidth": w, "overflow": "hidden",
            "whiteSpace": "nowrap", "textOverflow": "ellipsis"}
    base.update(extra)
    return base


TABLE_STYLE = {"tableLayout": "fixed", "width": "max-content", "minWidth": "100%"}


def _leading_cells(label, bold=True):
    extra = {"fontWeight": "bold"} if bold else {}
    return [
        html.Td("", style=_col_style("exclude")),
        html.Td("", style=_col_style("num")),
        html.Td("", style=_col_style("date")),
        html.Td("", style=_col_style("target")),
        html.Td(label, style=_col_style("acquirer", **extra)),
    ]


# -------------------------------------------------------------
# LAYOUT
# -------------------------------------------------------------
layout = dbc.Container([
    # Controls Card
    dbc.Card([
        dbc.CardBody([
            dbc.Row([
                dbc.Col([
                    html.Div([
                        dbc.Label("How Many:", className="me-1 mb-0 text-muted small"),
                        dbc.Input(
                            id="gt-num-multiples",
                            type="number", min=1, max=MAX_COLS, step=1, value=MAX_COLS,
                            style={"width": "60px", "height": "28px", "fontSize": "12px"}, size="sm", debounce=True,
                            className="d-inline-block",
                        ),
                    ], className="d-flex align-items-center"),
                ], xs=12, md="auto", className="mb-2 mb-md-0"),

                dbc.Col([
                    html.Div([
                        dbc.Label("DLOC %", className="me-1 mb-0 text-muted small"),
                        dbc.Input(id="gt-dloc-pct", type="text", value="19.4%",
                                  style={"width": "65px", "height": "28px", "fontSize": "12px"}, size="sm",
                                  disabled=True, className="d-inline-block"),
                    ], className="d-flex align-items-center"),
                ], xs=6, md="auto"),
            ], className="align-items-center g-2"),
        ], className="py-1 px-2")
    ], color="dark", outline=True, className="mb-2 border-secondary"),

    # Main Grid Card
    dbc.Card([
        dbc.CardBody([
            html.Div([
                dbc.Row([
                    dbc.Col(html.Div(className="fw-bold text-light mb-1", children="Guideline Transaction Multiple(s)")),
                    dbc.Col(html.A("GT Multiples Range Chart →", id="gt-chart-link", href="#", className="text-warning small"),
                            xs="auto", className="d-flex align-items-center"),
                ], className="justify-content-between g-1 mb-1"),
                html.Table(
                    [
                        html.Colgroup(id="gt-colgroup"),
                        html.Thead(id="gt-header-container"),
                        html.Tbody(id="gt-body-container"),
                    ],
                    className="table table-sm table-dark mb-0",
                    style={"tableLayout": "fixed", "width": "max-content", "minWidth": "100%"},
                ),
                html.Div(className="fw-bold text-light mt-3 mb-1", children="Statistics"),
                html.Div(id="gt-stats-container"),
                html.Div(className="fw-bold text-light mt-3 mb-1", children="Selected Multiples"),
                html.Div(id="gt-selected-multiples-container"),
                html.Div(className="fw-bold text-light mt-3 mb-1", children="Subject Company"),
                html.Div(id="gt-subject-container"),
                html.Div(className="fw-bold text-light mt-3 mb-1", children="Weighting"),
                html.Div(id="gt-weighting-container"),
            ], style={"overflowX": "auto"})
        ], className="p-2")
    ], color="secondary", outline=True, className="mb-3"),

    # Bridge Card
    dbc.Card([
        dbc.CardHeader("Bridge", className="fw-bold text-light py-1 px-2"),
        dbc.CardBody([
            html.Div(id="gt-bridge-container", style={"overflowX": "auto"}),
        ])
    ], color="secondary", outline=True, className="mb-3"),

    # Chart Modal
    dbc.Modal([
        dbc.ModalHeader(dbc.ModalTitle("Range of Selected Transaction Multiples")),
        dbc.ModalBody([
            html.Div(id="gt-chart-container"),
        ]),
        dbc.ModalFooter([
            dbc.Button("Close", id="gt-chart-close", color="secondary", size="sm", n_clicks=0),
        ]),
    ], id="gt-chart-modal", is_open=False, size="lg"),

    dcc.Store(id="gt-exclude-store", data={}, storage_type="memory"),
], fluid=True, className="px-2")


def _fixed_header_cells():
    return [
        html.Th("Exclude", style=_col_style("exclude")),
        html.Th("#", style=_col_style("num")),
        html.Th("Closing Date", style=_col_style("date")),
        html.Th("Target Company", style=_col_style("target")),
        html.Th("Acquirer", style=_col_style("acquirer")),
    ]


# -------------------------------------------------------------
# CALLBACK 1 — HEADER ONLY
# -------------------------------------------------------------
@callback(
    Output("gt-header-container", "children"),
    Output("gt-colgroup", "children"),
    Input("gt-num-multiples", "value"),
    State("session-store", "data"),
)
def render_header(num_multiples, session_data):
    try:
        num_cols = max(1, min(MAX_COLS, int(num_multiples or MAX_COLS)))
    except (TypeError, ValueError):
        num_cols = MAX_COLS

    options = METRICS
    gt_state = ((session_data or {}).get("gt_page_state", {}) or {})
    saved_metric_cols = gt_state.get("metric_selections", [])

    def _seeded_value(i):
        if i < len(saved_metric_cols) and saved_metric_cols[i] in options:
            return saved_metric_cols[i]
        return options[i % len(options)]

    header_cells = _fixed_header_cells() + [
        html.Th(
            dcc.Dropdown(
                id={"type": "gt-metric-col", "index": i},
                options=options,
                value=_seeded_value(i),
                clearable=False,
                className="dbc",
                style={"fontSize": "12px"},
            ),
            style=_col_style("metric"),
        )
        for i in range(num_cols)
    ]

    cols = [
        html.Col(style={"width": f"{COL_W['exclude']}px"}),
        html.Col(style={"width": f"{COL_W['num']}px"}),
        html.Col(style={"width": f"{COL_W['date']}px"}),
        html.Col(style={"width": f"{COL_W['target']}px"}),
        html.Col(style={"width": f"{COL_W['acquirer']}px"}),
    ] + [html.Col(style={"width": f"{COL_W['metric']}px"}) for _ in range(num_cols)]

    return html.Tr(header_cells), cols


# -------------------------------------------------------------
# CALLBACK 2 — Exclusions
# -------------------------------------------------------------
@callback(
    Output("gt-exclude-store", "data"),
    Input({"type": "gt-exclude-chk", "slot": ALL}, "value"),
    State({"type": "gt-exclude-chk", "slot": ALL}, "id"),
    State("gt-exclude-store", "data"),
    prevent_initial_call=True,
)
def persist_exclude_state(values, ids, existing):
    existing = dict(existing or {})
    for val, id_dict in zip(values, ids):
        existing[str(id_dict["slot"])] = bool(val)
    return existing


# -------------------------------------------------------------
# CALLBACK 3 — BODY, STATISTICS, SELECTED MULTIPLES
# -------------------------------------------------------------
@callback(
    Output("gt-body-container", "children"),
    Output("gt-stats-container", "children"),
    Output("gt-selected-multiples-container", "children"),
    Input({"type": "gt-metric-col", "index": ALL}, "value"),
    Input("gt-exclude-store", "data"),
    Input("session-store", "data"),
    Input("source-results-store", "data"),
)
def render_body(metric_col_values, exclude_map, session_data, source_results):
    inputs = dict_to_project_inputs(session_data or {})
    exclude_map = exclude_map or {}
    metric_col_values = metric_col_values or []
    n_cols = len(metric_col_values)

    span = n_cols + 5
    transactions = list(inputs.gt_transactions or [])
    if not transactions:
        empty_row = html.Tr([html.Td(
            dbc.Alert("No GT transactions configured on the Home page.", color="warning"),
            colSpan=span)])
        return [empty_row], "", ""

    # Reconstruct current page state from input context
    state = gt_state_from_session(session_data)
    state["num_multiples"] = n_cols
    state["metric_selections"] = metric_col_values
    state["excluded_rows"] = [exclude_map.get(str(i), False) for i in range(MAX_ROWS)]

    calc = get_gt_results(session_data, source_results, state)
    tx_rows = calc["tx_rows"]

    # --- Body Rows ---
    body_rows = []
    for idx, tx in enumerate(tx_rows):
        is_excluded = tx["excluded"]
        cells = [
            html.Td(dbc.Checkbox(id={"type": "gt-exclude-chk", "slot": idx}, value=is_excluded),
                    style=_col_style("exclude")),
            html.Td(str(idx + 1), style=_col_style("num")),
            html.Td(tx["closing_date"], style=_col_style("date")),
            html.Td(tx["target"], style=_col_style("target")),
            html.Td(tx["acquirer"], style=_col_style("acquirer")),
        ]
        for col_idx in range(n_cols):
            val = tx["multiples"][col_idx]
            cells.append(html.Td(f"{val:.2f}x" if val is not None else "NA",
                                 style=_col_style("metric", textAlign="right")))
        body_rows.append(html.Tr(cells, style={"opacity": "0.4" if is_excluded else "1.0"}))

    # --- Statistics Rows ---
    stats_rows = []
    for stat_name in STAT_NAMES:
        cells = _leading_cells(stat_name)
        stat_vals = calc["stats"].get(stat_name, [])
        for col_idx in range(n_cols):
            v = stat_vals[col_idx] if col_idx < len(stat_vals) else None
            cells.append(html.Td(f"{v:.2f}x" if v is not None else "NA",
                                 style=_col_style("metric", textAlign="right")))
        stats_rows.append(html.Tr(cells))

    stats_table = html.Table(
        [html.Tbody(stats_rows)],
        className="table table-sm table-dark mb-0",
        style=TABLE_STYLE,
    )

    # --- Selected Multiples ---
    high_cells = _leading_cells("Selected Multiple — High")
    low_cells = _leading_cells("Selected Multiple — Low")
    for i in range(n_cols):
        col_metric = metric_col_values[i]
        vals = calc["multiples_per_col"][i] if i < len(calc["multiples_per_col"]) else []
        med = statistics.median(vals) if vals else None
        computed_default = f"{med:.2f}" if med is not None else ""
        default_val_high = state["selected_high"][i] if (i < len(state["selected_high"]) and state["selected_high"][i]) else computed_default
        default_val_low = state["selected_low"][i] if (i < len(state["selected_low"]) and state["selected_low"][i]) else computed_default

        high_cells.append(html.Td(
            dbc.Input(id={"type": "gt-selected-high", "col": i}, type="text",
                      value=default_val_high, size="sm",
                      style={"width": "90px", "textAlign": "right", "marginLeft": "auto"}, debounce=True),
            style=_col_style("metric"),
        ))
        low_cells.append(html.Td(
            dbc.Input(id={"type": "gt-selected-low", "col": i}, type="text",
                      value=default_val_low, size="sm",
                      style={"width": "90px", "textAlign": "right", "marginLeft": "auto"}, debounce=True),
            style=_col_style("metric"),
        ))

    selected_table = html.Table(
        [html.Tbody([html.Tr(high_cells), html.Tr(low_cells)])],
        className="table table-sm table-dark mb-0",
        style=TABLE_STYLE,
    )

    return body_rows, stats_table, selected_table


# -------------------------------------------------------------
# CALLBACK 4 — SUBJECT / WEIGHTING / BRIDGE
# -------------------------------------------------------------
@callback(
    Output("gt-subject-container", "children"),
    Output("gt-weighting-container", "children"),
    Output("gt-bridge-container", "children"),
    Input({"type": "gt-metric-col", "index": ALL}, "value"),
    Input({"type": "gt-selected-high", "col": ALL}, "value"),
    Input({"type": "gt-selected-low", "col": ALL}, "value"),
    Input({"type": "gt-weight", "col": ALL}, "value"),
    Input("gt-dloc-pct", "value"),
    State("gt-exclude-store", "data"),
    State("session-store", "data"),
    State("source-results-store", "data"),
)
def render_subject_weighting_bridge(metric_col_values, selected_highs, selected_lows,
                                     weight_values_live, dloc_input_val,
                                     exclude_map, session_data, source_results):
    metric_col_values = metric_col_values or []
    n_cols = len(metric_col_values)

    if n_cols == 0:
        empty = dbc.Alert("Configure GT multiples above first.", color="secondary")
        return empty, empty, empty

    state = gt_state_from_session(session_data)
    state["num_multiples"] = n_cols
    state["metric_selections"] = metric_col_values
    state["excluded_rows"] = [exclude_map.get(str(i), False) for i in range(MAX_ROWS)]
    state["selected_high"] = ["" if v is None else str(v) for v in selected_highs]
    state["selected_low"] = ["" if v is None else str(v) for v in selected_lows]
    state["weights"] = ["" if v is None else str(v) for v in weight_values_live]

    calc = get_gt_results(session_data, source_results, state)
    subject_metrics = calc["subject_metrics"]
    indicated_low = calc["indicated_low"]
    indicated_high = calc["indicated_high"]
    weights = calc["weights"]
    fmv_low = calc["fmv_low"]
    fmv_high = calc["fmv_high"]
    dloc = calc["dloc"]
    debt = calc["debt"]
    eq_ctrl_low = calc["eq_ctrl_low"]
    eq_ctrl_high = calc["eq_ctrl_high"]
    eq_nctrl_low = calc["eq_nctrl_low"]
    eq_nctrl_high = calc["eq_nctrl_high"]
    bev_nctrl_low = calc["bev_nctrl_low"]
    bev_nctrl_high = calc["bev_nctrl_high"]

    # --- Subject Company row ---
    subject_row = _leading_cells(f"{calc['inputs'].subject_company_name} Financial Data")
    for v in subject_metrics:
        subject_row.append(html.Td(f"{v:,.0f}" if v is not None else "NA",
                                   style=_col_style("metric", textAlign="right")))

    ind_low_row = _leading_cells("Indicated BEV — Low")
    ind_high_row = _leading_cells("Indicated BEV — High")
    for i in range(n_cols):
        v_low = indicated_low[i]
        v_high = indicated_high[i]
        ind_low_row.append(html.Td(f"{v_low:,.0f}" if v_low is not None else "NA",
                                   style=_col_style("metric", textAlign="right")))
        ind_high_row.append(html.Td(f"{v_high:,.0f}" if v_high is not None else "NA",
                                    style=_col_style("metric", textAlign="right")))

    subject_table = html.Table(
        [html.Tbody([html.Tr(subject_row), html.Tr(ind_high_row), html.Tr(ind_low_row)])],
        className="table table-sm table-dark mb-0", style=TABLE_STYLE,
    )

    # --- Weighting ---
    equal_weight_str = f"{100.0 / n_cols:.1f}%"
    weight_row = _leading_cells("Weighting")
    for i in range(n_cols):
        seeded = state["weights"][i] if (i < len(state["weights"]) and state["weights"][i]) else equal_weight_str
        weight_row.append(html.Td(
            dbc.Input(id={"type": "gt-weight", "col": i}, type="text", value=seeded, size="sm",
                      style={"width": "80px", "textAlign": "right", "marginLeft": "auto"}, debounce=True),
            style=_col_style("metric"),
        ))

    fmv_high_row = _leading_cells("FMV BEV — High") + [
        html.Td(f"{fmv_high:,.0f}" if fmv_high is not None else "NA",
                style=_col_style("metric", textAlign="right"))
    ] + [html.Td("", style=_col_style("metric")) for _ in range(max(0, n_cols - 1))]
    fmv_low_row = _leading_cells("FMV BEV — Low") + [
        html.Td(f"{fmv_low:,.0f}" if fmv_low is not None else "NA",
                style=_col_style("metric", textAlign="right"))
    ] + [html.Td("", style=_col_style("metric")) for _ in range(max(0, n_cols - 1))]

    weighting_table = html.Table(
        [html.Tbody([html.Tr(weight_row), html.Tr(fmv_high_row), html.Tr(fmv_low_row)])],
        className="table table-sm table-dark mb-0", style=TABLE_STYLE,
    )

    # --- Bridge Card ---
    def _row(label, low, high, is_pct=False):
        fmt = _fmt_pct if is_pct else _fmt_currency
        return html.Tr([
            html.Td(label, style={"minWidth": f"{LEADING_W}px"}),
            html.Td(fmt(high), style={"textAlign": "right", "minWidth": f"{COL_W['metric']}px", "fontWeight": "bold"}),
            html.Td(fmt(low), style={"textAlign": "right", "minWidth": f"{COL_W['metric']}px", "fontWeight": "bold"}),
        ])

    bridge_rows = [
        html.Tr([html.Th("", style={"minWidth": f"{LEADING_W}px"}),
                 html.Th("High", style={"textAlign": "right"}), html.Th("Low", style={"textAlign": "right"})]),
        _row("FMV BEV", fmv_low, fmv_high),
        _row("Less: Total Debt", debt, debt),
        _row("FMV of Equity (marketable, controlling)", eq_ctrl_low, eq_ctrl_high),
        _row("Less: Discount for Lack of Control", dloc, dloc, is_pct=True),
        _row("FMV of Equity (marketable, noncontrolling)", eq_nctrl_low, eq_nctrl_high),
        _row("Plus: Total Debt", debt, debt),
        _row("FMV of Business Enterprise (marketable, noncontrolling)", bev_nctrl_low, bev_nctrl_high),
    ]

    bridge_table = html.Table(
        [html.Thead(bridge_rows[0]), html.Tbody(bridge_rows[1:])],
        className="table table-sm table-dark mb-0", style={"width": "max-content", "minWidth": "100%"},
    )

    return subject_table, weighting_table, bridge_table


# -------------------------------------------------------------
# CALLBACK — Hydrate dropdowns / exclusions on page load
# -------------------------------------------------------------
@callback(
    Output("gt-exclude-store", "data", allow_duplicate=True),
    Input("session-load-timestamp", "data"),
    Input("_pages_location", "pathname"),
    State("session-store", "data"),
    prevent_initial_call='initial_duplicate',
)
def restore_gt_static_state(_load_ts, pathname, session_data):
    if pathname not in ("/gt", "/gt/"):
        return no_update

    state = gt_state_from_session(session_data)
    tickers = list(dict_to_project_inputs(session_data).gt_transactions or [])
    exclusions = {}
    for i in range(len(tickers)):
        exclusions[str(i)] = state["excluded_rows"][i] if i < len(state["excluded_rows"]) else False

    return exclusions


# -------------------------------------------------------------
# CALLBACK — Chart Modal
# -------------------------------------------------------------
@callback(
    Output("gt-chart-modal", "is_open"),
    Input("gt-chart-link", "n_clicks"),
    Input("gt-chart-close", "n_clicks"),
    State("gt-chart-modal", "is_open"),
    prevent_initial_call=True,
)
def toggle_gt_chart(open_clicks, close_clicks, is_open):
    trig = ctx.triggered_id
    if trig == "gt-chart-link":
        return True
    if trig == "gt-chart-close":
        return False
    return bool(is_open)


@callback(
    Output("gt-chart-container", "children"),
    Input("gt-chart-modal", "is_open"),
    State("gt-exclude-store", "data"),
    State("session-store", "data"),
    State("source-results-store", "data"),
)
def render_gt_chart(is_open, exclude_map, session_data, source_results):
    if not is_open:
        return no_update

    exclude_map = exclude_map or {}
    state = gt_state_from_session(session_data)
    state["excluded_rows"] = [exclude_map.get(str(i), False) for i in range(MAX_ROWS)]
    
    calc = get_gt_results(session_data, source_results, state)
    chart_data = calc["chart_data"]
    labels = calc["metric_selections"]

    fig = gt_range_chart(
        labels=labels,
        q3=chart_data.get("q3", []),
        max_vals=chart_data.get("max", []),
        min_vals=chart_data.get("min", []),
        q1=chart_data.get("q1", []),
        title="Range of Selected Transaction Multiples",
    )

    return dcc.Graph(
        figure=fig,
        config={"displayModeBar": False},
        style={"height": "520px"},
    )