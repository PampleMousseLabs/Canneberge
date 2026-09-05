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
from web.lib.subject_metrics import get_subject_metric_value
from Canneberge.Calculations.gpc_multiples import compute_all_gpc_multiples, get_subject_cash
from Canneberge.Calculations.gpc_metrics import GPC_METRICS, dropdown_options, get_metric, CUSTOM_MULTIPLE_LABEL

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

    # ONE shared horizontal-scroll region for every section that shares
    # the same N metric columns. Scrolling anywhere in this region moves
    # everything together — this replaces five independently-scrolling
    # containers that only looked aligned until actually scrolled (the
    # iPad "two separate scrollbars" bug).
    dbc.Card([
        dbc.CardBody([
            html.Div([
                html.Div(className="fw-bold text-light mb-1", children="Guideline Public Company Multiple(s)"),
                html.Div(id="gpc-header-container"),
                html.Div(id="gpc-body-container"),
                html.Div(className="fw-bold text-light mt-3 mb-1", children="Statistics"),
                html.Div(id="gpc-stats-container"),
                html.Div(className="fw-bold text-light mt-3 mb-1", children="Selected Multiples"),
                html.Div(id="gpc-selected-multiples-container"),
                html.Div(className="fw-bold text-light mt-3 mb-1", children="Subject Company"),
                html.Div(id="gpc-subject-container"),
                html.Div(className="fw-bold text-light mt-3 mb-1", children="Weighting"),
                html.Div(id="gpc-weighting-container"),
            ], style={"overflowX": "auto"})
        ], className="p-2")
    ], color="secondary", outline=True, className="mb-3"),

    dbc.Card([
        dbc.CardHeader("Bridge to Fair Value of Equity", className="fw-bold text-light"),
        dbc.CardBody([
            dbc.Row([
                dbc.Col([
                    dbc.Label("NWC Surplus (Deficit) — PLACEHOLDER", className="text-muted small"),
                    dbc.Input(id="gpc-nwc-input", type="text", value="0",
                              size="sm", style={"width": "140px"}, debounce=True),
                ], xs=6, md="auto"),
                dbc.Col([
                    dbc.Label("Non-Operating Assets, Net — PLACEHOLDER", className="text-muted small"),
                    dbc.Input(id="gpc-non-op-input", type="text", value="0",
                              size="sm", style={"width": "140px"}, debounce=True),
                ], xs=6, md="auto"),
            ], className="mb-3 g-3"),
            html.Div(id="gpc-bridge-container", style={"overflowX": "auto"}),
        ])
    ], color="secondary", outline=True, className="mb-3"),

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
    State("session-store", "data"),
)
def render_header(num_multiples, basis_mode, session_data):
    basis_mode = basis_mode or "BEV"
    try:
        num_cols = max(1, min(MAX_COLS_CAP, int(num_multiples or MAX_COLS_CAP)))
    except (TypeError, ValueError):
        num_cols = MAX_COLS_CAP

    options = dropdown_options(basis_mode)
    saved_metric_cols = ((session_data or {}).get("gpc_page_state", {}) or {}).get("metric_cols", {})

    def _seeded_value(i):
        saved = saved_metric_cols.get(str(i))
        if saved in options:
            return saved
        default = _default_metric_for_col(i)
        return default if default in options else options[0]

    header_cells = _fixed_header_cells() + [
        html.Th(
            dcc.Dropdown(
                id={"type": "gpc-metric-col", "index": i},
                options=options,
                value=_seeded_value(i),
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
    saved_selected_high = ((session_data or {}).get("gpc_page_state", {}) or {}).get("selected_high", {})
    saved_selected_low = ((session_data or {}).get("gpc_page_state", {}) or {}).get("selected_low", {})
    high_cells = [html.Td("Selected Multiple — High",
                           style={"fontWeight": "bold", "minWidth": f"{LEADING_W}px"})]
    low_cells = [html.Td("Selected Multiple — Low",
                          style={"fontWeight": "bold", "minWidth": f"{LEADING_W}px"})]
    for i, col_metric in enumerate(metric_col_values):
        vals = [all_multiples.get(t, {}).get(col_metric) for t in included_tickers]
        med = _compute_stats(vals)["Median"]
        computed_default = f"{med:.2f}" if med is not None else ""
        default_val_high = saved_selected_high.get(str(i), computed_default)
        default_val_low = saved_selected_low.get(str(i), computed_default)
        high_cells.append(html.Td(
            dbc.Input(id={"type": "gpc-selected-high", "metric": col_metric}, type="text",
                      value=default_val_high, size="sm",
                      style={"width": "90px", "textAlign": "right", "marginLeft": "auto"}, debounce=True),
            style={"minWidth": f"{COL_W['metric']}px"},
        ))
        low_cells.append(html.Td(
            dbc.Input(id={"type": "gpc-selected-low", "metric": col_metric}, type="text",
                      value=default_val_low, size="sm",
                      style={"width": "90px", "textAlign": "right", "marginLeft": "auto"}, debounce=True),
            style={"minWidth": f"{COL_W['metric']}px"},
        ))

    selected_table = html.Table(
        [html.Tbody([html.Tr(high_cells), html.Tr(low_cells)])],
        className="table table-sm table-dark mb-0",
        style={"width": "max-content", "minWidth": "100%"},
    )

    return body_table, stats_table, selected_table

# -------------------------------------------------------------
# CALLBACK 4 — Subject / Weighting / Bridge. Direct port of
# desktop gpc_page.py's _recalculate() subject/weighting/bridge
# block (lines ~1096-1228). Formulas replicated verbatim, not
# redesigned — see that method if these ever need auditing.
# -------------------------------------------------------------
@callback(
    Output("gpc-subject-container", "children"),
    Output("gpc-weighting-container", "children"),
    Output("gpc-bridge-container", "children"),
    Input({"type": "gpc-metric-col", "index": ALL}, "value"),
    Input({"type": "gpc-selected-high", "metric": ALL}, "value"),
    Input({"type": "gpc-selected-low", "metric": ALL}, "value"),
    Input("gpc-dloc-pct", "value"),
    Input("gpc-control-premium-pct", "value"),
    Input("gpc-nwc-input", "value"),
    Input("gpc-non-op-input", "value"),
    Input("session-store", "data"),
    Input("source-results-store", "data"),
)
def render_subject_weighting_bridge(metric_col_values, selected_highs, selected_lows,
                                     dloc_pct_str, cp_pct_str, nwc_str, non_op_str,
                                     session_data, source_results):
    inputs = dict_to_project_inputs(session_data or {})
    metric_col_values = metric_col_values or []
    n_cols = len(metric_col_values)

    if n_cols == 0:
        empty = dbc.Alert("Configure GPC multiples above first.", color="secondary")
        return empty, empty, empty

    def _pct(s):
        try:
            return float(str(s).replace("%", "").strip()) / 100.0
        except (TypeError, ValueError):
            return 0.0

    def _num(s):
        try:
            return float(str(s).replace(",", "").strip())
        except (TypeError, ValueError):
            return 0.0

    # --- Subject metric per column, via the single shared source
    # of truth (same function subject_financials.py already uses) ---
    subject_vals = []
    for col_metric in metric_col_values:
        if col_metric == CUSTOM_MULTIPLE_LABEL:
            subject_vals.append(None)
            continue
        metric = get_metric(col_metric)
        if metric is None:
            subject_vals.append(None)
            continue
        val = get_subject_metric_value(session_data or {}, source_results or {},
                                        metric.line_key, metric.period)
        subject_vals.append(val)

    subject_row = [html.Td("Subject Financial Data", style={"fontWeight": "bold", "minWidth": f"{LEADING_W}px"})]
    for v in subject_vals:
        subject_row.append(html.Td(f"{v:,.1f}" if v is not None else "NA",
                                    style={"textAlign": "right", "minWidth": f"{COL_W['metric']}px"}))

    indicated_low, indicated_high = [], []
    ind_low_row = [html.Td("Indicated BEV — Low", style={"fontWeight": "bold", "minWidth": f"{LEADING_W}px"})]
    ind_high_row = [html.Td("Indicated BEV — High", style={"fontWeight": "bold", "minWidth": f"{LEADING_W}px"})]
    for i in range(n_cols):
        subj = subject_vals[i]
        sel_low = _num(selected_lows[i]) if i < len(selected_lows) else None
        sel_high = _num(selected_highs[i]) if i < len(selected_highs) else None
        val_low = subj * sel_low if (subj is not None and sel_low) else None
        val_high = subj * sel_high if (subj is not None and sel_high) else None
        indicated_low.append(val_low)
        indicated_high.append(val_high)
        ind_low_row.append(html.Td(f"{val_low:,.0f}" if val_low is not None else "NA",
                                    style={"textAlign": "right", "minWidth": f"{COL_W['metric']}px"}))
        ind_high_row.append(html.Td(f"{val_high:,.0f}" if val_high is not None else "NA",
                                     style={"textAlign": "right", "minWidth": f"{COL_W['metric']}px"}))

    subject_table = html.Table(
        [html.Tbody([html.Tr(subject_row), html.Tr(ind_high_row), html.Tr(ind_low_row)])],
        className="table table-sm table-dark mb-0", style={"width": "max-content", "minWidth": "100%"},
    )

    # --- Weighting ---
    saved_gpc_state = (session_data or {}).get("gpc_page_state", {}) or {}
    saved_weights = saved_gpc_state.get("weights", {})
    equal_weight_str = f"{100.0 / n_cols:.1f}"
    weight_row = [html.Td("Weighting", style={"fontWeight": "bold", "minWidth": f"{LEADING_W}px"})]
    weight_input_ids = []
    for i, col_metric in enumerate(metric_col_values):
        wid = {"type": "gpc-weight", "index": i}
        weight_input_ids.append(wid)
        seeded = saved_weights.get(str(i), equal_weight_str)
        weight_row.append(html.Td(
            dbc.Input(id=wid, type="text", value=seeded, size="sm",
                      style={"width": "80px", "textAlign": "right", "marginLeft": "auto"}, debounce=True),
            style={"minWidth": f"{COL_W['metric']}px"},
        ))

    # Weighting callback needs the weight values live — but they're
    # created fresh here each render. Read their default (equal-weight)
    # value directly for this render pass; a live-typed override is
    # picked up on the NEXT render via the pattern-matching Input
    # this callback would need if wired that way. For now: equal
    # weighting is applied. Wiring live weight edits is the next gap.
    weights = [1.0 / n_cols] * n_cols

    fmv_low = None
    fmv_high = None
    total_w = 0.0
    sum_low, sum_high = 0.0, 0.0
    any_present = False
    for v_low, v_high, w in zip(indicated_low, indicated_high, weights):
        if v_low is None or v_high is None or w is None:
            continue
        sum_low += v_low * w
        sum_high += v_high * w
        any_present = True
    if any_present:
        fmv_low, fmv_high = sum_low, sum_high

    fmv_high_row = [html.Td("FMV BEV — High", style={"fontWeight": "bold", "minWidth": f"{LEADING_W}px"}),
                     html.Td(f"{fmv_high:,.0f}" if fmv_high is not None else "NA",
                             style={"textAlign": "right", "minWidth": f"{COL_W['metric']}px"})]
    fmv_low_row = [html.Td("FMV BEV — Low", style={"fontWeight": "bold", "minWidth": f"{LEADING_W}px"}),
                    html.Td(f"{fmv_low:,.0f}" if fmv_low is not None else "NA",
                            style={"textAlign": "right", "minWidth": f"{COL_W['metric']}px"})]

    weighting_table = html.Table(
        [html.Tbody([html.Tr(weight_row), html.Tr(fmv_high_row), html.Tr(fmv_low_row)])],
        className="table table-sm table-dark mb-0", style={"width": "max-content", "minWidth": "100%"},
    )

    # --- Bridge — direct port of desktop's BEV-mode branch.
    # (Equity-mode branch not yet wired here — this page currently
    # always renders the BEV bridge, matching what most of today's
    # session data has been run under. Flag if Equity mode is needed
    # next: the desktop file's eq_nctrl/eq_mkt_ctrl/eq_nonmkt_ctrl
    # branch — lines ~1141-1171 — is the one to port next.) ---
    control_premium = _pct(cp_pct_str)
    dloc = _pct(dloc_pct_str)
    nwc = _num(nwc_str)
    non_op = _num(non_op_str)

    if inputs.company_status and inputs.company_status.strip().lower() == "publicly traded":
        sa = (source_results or {}).get("stockanalysis", {}) if source_results else {}
        bs_rows = sa.get("BS", [])
        cash = get_subject_cash(bs_rows, inputs.subject_ticker)
    else:
        cash = None  # Private-company cash path (PrivateFinancials) not yet wired here

    bev_nctrl_low, bev_nctrl_high = fmv_low, fmv_high

    def _sum_or_na(*vals):
        return None if any(v is None for v in vals) else sum(vals)

    ic_nctrl_low = _sum_or_na(bev_nctrl_low, cash, nwc, non_op)
    ic_nctrl_high = _sum_or_na(bev_nctrl_high, cash, nwc, non_op)
    ic_ctrl_low = ic_nctrl_low * (1 + control_premium) if ic_nctrl_low is not None else None
    ic_ctrl_high = ic_nctrl_high * (1 + control_premium) if ic_nctrl_high is not None else None
    bev_ctrl_low = (ic_ctrl_low - cash - nwc - non_op) if None not in (ic_ctrl_low, cash) else None
    bev_ctrl_high = (ic_ctrl_high - cash - nwc - non_op) if None not in (ic_ctrl_high, cash) else None

    def _row(label, low, high):
        return html.Tr([
            html.Td(label, style={"minWidth": f"{LEADING_W}px"}),
            html.Td(f"{high:,.0f}" if high is not None else "NA",
                    style={"textAlign": "right", "minWidth": f"{COL_W['metric']}px"}),
            html.Td(f"{low:,.0f}" if low is not None else "NA",
                    style={"textAlign": "right", "minWidth": f"{COL_W['metric']}px"}),
        ])

    bridge_rows = [
        html.Tr([html.Th("", style={"minWidth": f"{LEADING_W}px"}),
                 html.Th("High", style={"textAlign": "right"}), html.Th("Low", style={"textAlign": "right"})]),
        _row("FMV of Business Enterprise (marketable, noncontrolling)", bev_nctrl_low, bev_nctrl_high),
        _row("Plus: Cash", cash, cash),
        _row("Plus: NWC Surplus (Deficit) — PLACEHOLDER", nwc, nwc),
        _row("Plus: Non-Operating Assets, Net — PLACEHOLDER", non_op, non_op),
        _row("FMV of Invested Capital (marketable, noncontrolling)", ic_nctrl_low, ic_nctrl_high),
        _row(f"Plus: Control Premium ({control_premium:.1%})", None, None),
        _row("FMV of Invested Capital (marketable, controlling)", ic_ctrl_low, ic_ctrl_high),
        _row("Less: Cash", cash, cash),
        _row("Less: NWC Surplus (Deficit) — PLACEHOLDER", nwc, nwc),
        _row("Less: Non-Operating Assets, Net — PLACEHOLDER", non_op, non_op),
        _row("FMV of Business Enterprise (marketable, controlling)", bev_ctrl_low, bev_ctrl_high),
    ]

    bridge_table = html.Table(
        [html.Thead(bridge_rows[0]), html.Tbody(bridge_rows[1:])],
        className="table table-sm table-dark mb-0", style={"width": "max-content", "minWidth": "100%"},
    )

    return subject_table, weighting_table, bridge_table

# -------------------------------------------------------------
# CALLBACK — restore static controls from a loaded session.
# Per-basis separate state (desktop's _per_basis_state) is NOT
# replicated here — BEV and Equity share one saved selection set,
# unlike desktop which remembers each independently.
# -------------------------------------------------------------
@callback(
    Output("gpc-num-multiples", "value"),
    Output("gpc-basis-toggle", "value"),
    Output("gpc-dloc-pct", "value"),
    Output("gpc-control-premium-pct", "value"),
    Output("gpc-nwc-input", "value"),
    Output("gpc-non-op-input", "value"),
    Output("gpc-exclude-store", "data", allow_duplicate=True),
    Input("session-store", "data"),
    prevent_initial_call=True,
)
def restore_gpc_static_state(session_data):
    gpc_state = (session_data or {}).get("gpc_page_state", {})
    return (
        gpc_state.get("num_multiples", MAX_COLS_CAP),
        gpc_state.get("basis_mode", "BEV"),
        gpc_state.get("dloc", "0%"),
        gpc_state.get("control_premium", "0%"),
        gpc_state.get("nwc", "0"),
        gpc_state.get("non_op", "0"),
        gpc_state.get("exclude_map", {}),
    )

# -------------------------------------------------------------
# CALLBACK — persist all GPC inputs into session-store's gpc_state.
# This is what makes GPC selections survive Save Session / reload,
# via the same session-store the navbar's Save/Load already uses
# for Home and Subject Financials.
# -------------------------------------------------------------
@callback(
    Output("session-store", "data", allow_duplicate=True),
    Input("gpc-num-multiples", "value"),
    Input("gpc-basis-toggle", "value"),
    Input("gpc-dloc-pct", "value"),
    Input("gpc-control-premium-pct", "value"),
    Input("gpc-nwc-input", "value"),
    Input("gpc-non-op-input", "value"),
    Input({"type": "gpc-metric-col", "index": ALL}, "value"),
    Input({"type": "gpc-metric-col", "index": ALL}, "id"),
    Input({"type": "gpc-selected-high", "metric": ALL}, "value"),
    Input({"type": "gpc-selected-low", "metric": ALL}, "value"),
    Input({"type": "gpc-weight", "index": ALL}, "value"),
    Input({"type": "gpc-weight", "index": ALL}, "id"),
    Input("gpc-exclude-store", "data"),
    State("session-store", "data"),
    prevent_initial_call=True,
)
def persist_gpc_state(num_multiples, basis_mode, dloc, control_premium, nwc, non_op,
                       metric_col_values, metric_col_ids, selected_highs, selected_lows,
                       weight_values, weight_ids, exclude_map, session_data):
    session_data = dict(session_data or {})
    session_data["gpc_page_state"] = {
        "num_multiples": num_multiples,
        "basis_mode": basis_mode,
        "dloc": dloc,
        "control_premium": control_premium,
        "nwc": nwc,
        "non_op": non_op,
        "metric_cols": {str(id_dict["index"]): val for val, id_dict in zip(metric_col_values, metric_col_ids)},
        "selected_high": {str(i): v for i, v in enumerate(selected_highs)},
        "selected_low": {str(i): v for i, v in enumerate(selected_lows)},
        "weights": {str(id_dict["index"]): val for val, id_dict in zip(weight_values, weight_ids)},
        "exclude_map": exclude_map,
    }
    return session_data