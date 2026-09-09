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
from dash import html, dcc, Input, Output, State, callback, ALL, no_update, ctx

from web.lib.session_io import dict_to_project_inputs
from web.lib.subject_metrics import get_subject_metric_value
from Canneberge.Calculations.gpc_multiples import compute_all_gpc_multiples, get_subject_cash
from Canneberge.Calculations.gpc_metrics import GPC_METRICS, dropdown_options, get_metric, CUSTOM_MULTIPLE_LABEL
from Canneberge.Calculations.gpc_multiples import get_subject_cash
from Canneberge.Calculations.value_bridge import BridgeInputs, run_bridge
from Canneberge.Calculations.dcf import parse_number
from web.lib.dashboard_data import parse_weight, dashboard_state_from_session
from web.lib.subject_metrics import get_subject_debt, get_subject_metric_value
from web.components.gt_range_chart import gt_range_chart

dash.register_page(__name__, path="/gpc", name="GPC Metrics")

MAX_COLS_CAP = 7
STAT_NAMES = ["Maximum", "Third Quartile", "Average", "Median", "First Quartile", "Minimum"]

COL_W = {"exclude": 70, "num": 30, "ticker": 70, "company": 180, "metric": 140}
LEADING_W = COL_W["exclude"] + COL_W["num"] + COL_W["ticker"] + COL_W["company"]


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
        html.Td("", style=_col_style("ticker")),
        html.Td(label, style=_col_style("company", **extra)),
    ]


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


_BASIS_SLICE_KEYS = ("metric_cols", "selected_high", "selected_low", "weights")


def _basis_key(basis_mode) -> str:
    return "EQUITY" if str(basis_mode or "").upper() == "EQUITY" else "BEV"


def _safe_dict(val) -> dict:
    """Safely convert any stored value to a dictionary, preventing crashes
    on empty lists, legacy strings, or corrupted states."""
    if isinstance(val, dict):
        return dict(val)
    if isinstance(val, (list, tuple)):
        # Convert index list back to a string-keyed dictionary
        return {str(i): v for i, v in enumerate(val) if v is not None}
    return {}


def _default_metric_for_col(idx: int, basis_mode: str = "BEV") -> str:
    options = [
        o for o in dropdown_options(_basis_key(basis_mode))
        if o != CUSTOM_MULTIPLE_LABEL
    ]
    if not options:
        return CUSTOM_MULTIPLE_LABEL
    return options[idx % len(options)]


def _basis_bucket(gpc_state: dict, basis_mode: str) -> dict:
    """Return the saved BEV/EQUITY-specific GPC substate.

    Backward compatible with old sessions that stored metric_cols,
    selected_high, selected_low, and weights directly at gpc_page_state top level.
    """
    gpc_state = gpc_state or {}
    basis = _basis_key(basis_mode)

    basis_state = _safe_dict(gpc_state.get("basis_state"))
    bucket = _safe_dict(basis_state.get(basis))

    # Legacy fallback only if the old top-level basis matches requested basis.
    legacy_basis = _basis_key(gpc_state.get("basis_mode", "BEV"))
    if legacy_basis == basis:
        for k in _BASIS_SLICE_KEYS:
            if not bucket.get(k) and gpc_state.get(k):
                bucket[k] = _safe_dict(gpc_state.get(k))

    for k in _BASIS_SLICE_KEYS:
        bucket[k] = _safe_dict(bucket.get(k))

    return bucket


def _migrate_gpc_basis_state(prev: dict, legacy_basis: str) -> dict:
    """Build normalized basis_state and migrate old top-level fields once."""
    prev = prev or {}
    raw_basis_state = _safe_dict(prev.get("basis_state"))

    basis_state = {}
    for b in ("BEV", "EQUITY"):
        old_bucket = _safe_dict(raw_basis_state.get(b))
        basis_state[b] = {
            k: _safe_dict(old_bucket.get(k))
            for k in _BASIS_SLICE_KEYS
        }

    legacy_basis = _basis_key(legacy_basis)
    for k in _BASIS_SLICE_KEYS:
        legacy_val = prev.get(k)
        if legacy_val and not basis_state[legacy_basis].get(k):
            basis_state[legacy_basis][k] = _safe_dict(legacy_val)

    return basis_state


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
                        labelClassName="btn btn-outline-info btn-sm py-1 px-2",
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
            ], className="align-items-center g-2"),
        ], className="py-1 px-2")
    ], color="dark", outline=True, className="mb-2 border-secondary"),

    # ONE shared horizontal-scroll region for every section that shares
    # the same N metric columns. Scrolling anywhere in this region moves
    # everything together — this replaces five independently-scrolling
    # containers that only looked aligned until actually scrolled (the
    # iPad "two separate scrollbars" bug).
    dbc.Card([
        dbc.CardBody([
            html.Div([
                dbc.Row([
                    dbc.Col(html.Div(className="fw-bold text-light mb-1",
                                     children="Guideline Public Company Multiple(s)")),
                    dbc.Col(html.A("GPC Multiples Range Chart →", id="gpc-chart-link",
                                   href="#", className="text-warning small"),
                            xs="auto", className="d-flex align-items-center"),
                ], className="justify-content-between g-1 mb-1"),
                html.Table(
                    [
                        html.Colgroup(id="gpc-colgroup"),
                        html.Thead(id="gpc-header-container"),
                        html.Tbody(id="gpc-body-container"),
                    ],
                    className="table table-sm table-dark mb-0",
                    style={"tableLayout": "fixed", "width": "max-content", "minWidth": "100%"},
                ),
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
                    dbc.Label("NWC Surplus (Deficit) — from NWC page",
                              className="text-muted small"),
                    dbc.Input(id="gpc-nwc-input", type="text", value="0",
                              size="sm", style={"width": "140px"}, debounce=True,
                              disabled=True),
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

    # memory: source of truth is session-store["gpc_page_state"]["exclude_map"]
    # (session storage here fought disk load and looked like "saves don't stick")
    dbc.Modal([
        dbc.ModalHeader(dbc.ModalTitle("Range of Selected Multiples")),
        dbc.ModalBody([html.Div(id="gpc-chart-container")]),
        dbc.ModalFooter([
            dbc.Button("Close", id="gpc-chart-close", color="secondary", size="sm", n_clicks=0),
        ]),
    ], id="gpc-chart-modal", is_open=False, size="lg"),

    dcc.Store(id="gpc-exclude-store", data={}, storage_type="memory"),
], fluid=True, className="px-2")


def _fixed_header_cells():
    return [
        html.Th("Exclude", style=_col_style("exclude")),
        html.Th("#", style=_col_style("num")),
        html.Th("Ticker", style=_col_style("ticker")),
        html.Th("Company Name", style=_col_style("company")),
    ]


# -------------------------------------------------------------
# CALLBACK 1 — HEADER ONLY. Rebuilds only when num_multiples or
# basis change. The dropdown components stay mounted across every
# other interaction (exclude toggles, etc.), so the selected label
# never gets wiped by a remount.
# -------------------------------------------------------------
@callback(
    Output("gpc-header-container", "children"),
    Output("gpc-colgroup", "children"),
    Input("gpc-num-multiples", "value"),
    Input("gpc-basis-toggle", "value"),
    State("session-store", "data"),
)
def render_header(num_multiples, basis_mode, session_data):
    basis_mode = _basis_key(basis_mode)
    try:
        num_cols = max(1, min(MAX_COLS_CAP, int(num_multiples or MAX_COLS_CAP)))
    except (TypeError, ValueError):
        num_cols = MAX_COLS_CAP

    options = dropdown_options(basis_mode)
    gpc_state = ((session_data or {}).get("gpc_page_state", {}) or {})
    basis_bucket = _basis_bucket(gpc_state, basis_mode)
    saved_metric_cols = basis_bucket.get("metric_cols", {})

    def _seeded_value(i):
        saved = saved_metric_cols.get(str(i))
        if saved in options:
            return saved
        default = _default_metric_for_col(i, basis_mode)
        return default if default in options else options[0]

    header_cells = _fixed_header_cells() + [
        html.Th(
            dcc.Dropdown(
                id={"type": "gpc-metric-col", "index": i},
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
        html.Col(style={"width": f"{COL_W['ticker']}px"}),
        html.Col(style={"width": f"{COL_W['company']}px"}),
    ] + [html.Col(style={"width": f"{COL_W['metric']}px"}) for _ in range(num_cols)]

    return html.Tr(header_cells), cols


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
    Input("gpc-basis-toggle", "value"),
    Input("gpc-exclude-store", "data"),
    Input("session-store", "data"),
    Input("source-results-store", "data"),
)
def render_body(metric_col_values, basis_mode, exclude_map, session_data, source_results):
    inputs = dict_to_project_inputs(session_data or {})
    tickers = inputs.gpc_tickers or []
    exclude_map = exclude_map or {}
    metric_col_values = metric_col_values or []

    n_cols_for_span = len(metric_col_values) if metric_col_values else MAX_COLS_CAP
    span = n_cols_for_span + 4
    if not tickers:
        empty_row = html.Tr([html.Td(
            dbc.Alert("No GPC tickers configured on the Home page.", color="warning"),
            colSpan=span)])
        return [empty_row], "", ""

    sa = (source_results or {}).get("stockanalysis", {}) if source_results else {}
    is_rows = sa.get("IS", [])
    bs_rows = sa.get("BS", [])
    ratio_rows = sa.get("Ratios", [])
    ms_rows = (source_results or {}).get("marketscreener", []) if source_results else []

    if not is_rows and not ratio_rows:
        empty_row = html.Tr([html.Td(
            dbc.Alert("No source data loaded yet — refresh from the Source Data page first.",
                      color="warning"),
            colSpan=span)])
        return [empty_row], "", ""

    basis_mode = _basis_key(basis_mode)

    all_multiples = compute_all_gpc_multiples(is_rows, ms_rows, ratio_rows, bs_rows, tickers, basis_mode=basis_mode)
    included_tickers = [t for t in tickers if not exclude_map.get(t, False)]

    # --- Body rows live in the shared table's Tbody, so columns
    # share geometry with the header Thead above ---
    body_rows = []
    for idx, ticker in enumerate(tickers):
        is_excluded = exclude_map.get(ticker, False)
        row_multiples = all_multiples.get(ticker, {})
        cells = [
            html.Td(dbc.Checkbox(id={"type": "gpc-exclude-chk", "ticker": ticker}, value=is_excluded),
                    style=_col_style("exclude")),
            html.Td(str(idx + 1), style=_col_style("num")),
            html.Td(ticker.upper(), style=_col_style("ticker")),
            html.Td(
                (inputs.gpc_company_names or {}).get(ticker.upper(), "")
                or (inputs.gpc_company_names or {}).get(ticker, ""),
                style=_col_style("company"),
            ),
        ]
        for col_metric in metric_col_values:
            val = row_multiples.get(col_metric) if col_metric != CUSTOM_MULTIPLE_LABEL else None
            cells.append(html.Td(f"{val:.2f}x" if val is not None else "NA",
                                 style=_col_style("metric", textAlign="right")))
        body_rows.append(html.Tr(cells, style={"opacity": "0.4" if is_excluded else "1.0"}))

    # --- Statistics: same 4 leading cols as main table, so x-positions match ---
    stats_rows = []
    for stat_name in STAT_NAMES:
        cells = _leading_cells(stat_name)
        for col_metric in metric_col_values:
            vals = [all_multiples.get(t, {}).get(col_metric) for t in included_tickers]
            v = _compute_stats(vals)[stat_name]
            cells.append(html.Td(f"{v:.2f}x" if v is not None else "NA",
                                 style=_col_style("metric", textAlign="right")))
        stats_rows.append(html.Tr(cells))

    stats_table = html.Table(
        [html.Tbody(stats_rows)],
        className="table table-sm table-dark mb-0",
        style=TABLE_STYLE,
    )

    # --- Selected Multiples: same 4 leading cols ---
    gpc_state = ((session_data or {}).get("gpc_page_state", {}) or {})
    basis_bucket = _basis_bucket(gpc_state, basis_mode)
    saved_selected_high = basis_bucket.get("selected_high", {})
    saved_selected_low = basis_bucket.get("selected_low", {})
    high_cells = _leading_cells("Selected Multiple — High")
    low_cells = _leading_cells("Selected Multiple — Low")
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
            style=_col_style("metric"),
        ))
        low_cells.append(html.Td(
            dbc.Input(id={"type": "gpc-selected-low", "metric": col_metric}, type="text",
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
    Input("gpc-basis-toggle", "value"),
    Input({"type": "gpc-selected-high", "metric": ALL}, "value"),
    Input({"type": "gpc-selected-low", "metric": ALL}, "value"),
    Input({"type": "gpc-weight", "index": ALL}, "value"),
    Input("gpc-dloc-pct", "value"),
    Input("gpc-control-premium-pct", "value"),
    Input("gpc-nwc-input", "value"),
    Input("gpc-non-op-input", "value"),
    Input("session-store", "data"),
    Input("source-results-store", "data"),
)
def render_subject_weighting_bridge(metric_col_values, basis_mode, selected_highs, selected_lows,
                                     weight_values_live,
                                     dloc_pct_str, cp_pct_str, nwc_str, non_op_str,
                                     session_data, source_results):
    inputs = dict_to_project_inputs(session_data or {})
    metric_col_values = metric_col_values or []
    selected_highs = selected_highs or []
    selected_lows = selected_lows or []
    n_cols = len(metric_col_values)

    # Selected Multiples are dynamically mounted by render_body. During
    # a BEV/Equity switch this callback can briefly receive an empty
    # pattern-match list even while the saved values are already visible
    # in the remounted inputs. Use the active basis bucket as fallback.
    basis_mode = _basis_key(basis_mode)
    active_gpc_state = (session_data or {}).get("gpc_page_state", {}) or {}
    active_basis_bucket = _basis_bucket(active_gpc_state, basis_mode)
    saved_selected_high = active_basis_bucket.get("selected_high", {})
    saved_selected_low = active_basis_bucket.get("selected_low", {})

    if n_cols == 0:
        empty = dbc.Alert("Configure GPC multiples above first.", color="secondary")
        return empty, empty, empty

    def _pct(s):
        try:
            return float(str(s).replace("%", "").strip()) / 100.0
        except (TypeError, ValueError):
            return 0.0

    def _num(s):
        if s is None:
            return None

        text = (
            str(s)
            .replace(",", "")
            .replace("$", "")
            .replace("x", "")
            .replace("X", "")
            .strip()
        )
        if not text:
            return None

        try:
            value = float(text)
        except (TypeError, ValueError):
            return None

        return value if value == value else None

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
        subject_line_key = metric.line_key
        if metric.line_key == "ebitda" and metric.period in {"NFY", "NFY+1", "NFY+2"}:
            # Comparable forward EBITDA comes from MarketScreener (adjusted basis);
            # match it with the subject's Adjusted EBITDA. TTM stays conventional
            # on both sides (StockAnalysis comps vs. compute_is_calculated subject).
            subject_line_key = "adj_ebitda"

        val = get_subject_metric_value(session_data or {}, source_results or {},
                                        subject_line_key, metric.period)
        subject_vals.append(val)

    subject_row = _leading_cells("Subject Financial Data")
    for v in subject_vals:
        subject_row.append(html.Td(f"{v:,.1f}" if v is not None else "NA",
                                   style=_col_style("metric", textAlign="right")))

    indicated_basis = "Equity" if basis_mode == "EQUITY" else "BEV"

    indicated_low, indicated_high = [], []
    ind_low_row = _leading_cells(f"Indicated {indicated_basis} — Low")
    ind_high_row = _leading_cells(f"Indicated {indicated_basis} — High")

    for i in range(n_cols):
        subj = subject_vals[i]

        live_low = selected_lows[i] if i < len(selected_lows) else None
        live_high = selected_highs[i] if i < len(selected_highs) else None

        # On component-remount callback waves, live lists can be empty.
        # Fall back to the selected values stored for this specific basis.
        if live_low is None or str(live_low).strip() == "":
            live_low = saved_selected_low.get(str(i))
        if live_high is None or str(live_high).strip() == "":
            live_high = saved_selected_high.get(str(i))

        sel_low = _num(live_low)
        sel_high = _num(live_high)

        # Zero is mathematically valid; invalid/blank is None.
        val_low = subj * sel_low if (subj is not None and sel_low is not None) else None
        val_high = subj * sel_high if (subj is not None and sel_high is not None) else None
        indicated_low.append(val_low)
        indicated_high.append(val_high)
        ind_low_row.append(html.Td(f"{val_low:,.0f}" if val_low is not None else "NA",
                                   style=_col_style("metric", textAlign="right")))
        ind_high_row.append(html.Td(f"{val_high:,.0f}" if val_high is not None else "NA",
                                    style=_col_style("metric", textAlign="right")))

    subject_table = html.Table(
        [html.Tbody([html.Tr(subject_row), html.Tr(ind_high_row), html.Tr(ind_low_row)])],
        className="table table-sm table-dark mb-0", style=TABLE_STYLE,
    )

    # --- Weighting ---
    saved_gpc_state = (session_data or {}).get("gpc_page_state", {}) or {}
    saved_weights = _basis_bucket(saved_gpc_state, basis_mode).get("weights", {})
    equal_weight_str = f"{100.0 / n_cols:.1f}"
    weight_row = _leading_cells("Weighting")
    weight_input_ids = []
    for i, col_metric in enumerate(metric_col_values):
        wid = {"type": "gpc-weight", "index": i}
        weight_input_ids.append(wid)
        seeded = saved_weights.get(str(i), equal_weight_str)
        weight_row.append(html.Td(
            dbc.Input(id=wid, type="text", value=seeded, size="sm",
                      style={"width": "80px", "textAlign": "right", "marginLeft": "auto"}, debounce=True),
            style=_col_style("metric"),
        ))

    # Live weights (percent strings); fall back to equal weight
    weights = []
    for i in range(n_cols):
        raw = weight_values_live[i] if weight_values_live and i < len(weight_values_live) else None
        if raw is None or str(raw).strip() == "":
            raw = saved_weights.get(str(i), equal_weight_str)
        try:
            w = float(str(raw).replace("%", "").strip()) / 100.0
        except (TypeError, ValueError):
            w = 1.0 / n_cols
        weights.append(w)

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

    # --- Bridge — shared value_bridge.py engine ---
    dash_state = dashboard_state_from_session(session_data or {})

    control_premium = parse_weight(dash_state.get("control_premium"))
    dloc = parse_weight(dash_state.get("dloc"))
    non_op = parse_number(dash_state.get("non_op")) or 0.0

    _nwc_state = (session_data or {}).get("nwc_page_state") or {}
    _nwc_cached = _nwc_state.get("surplus_deficit")
    nwc = _nwc_cached if _nwc_cached is not None else 0.0

    if inputs.company_status and inputs.company_status.strip().lower() == "publicly traded":
        sa = (source_results or {}).get("stockanalysis", {}) if source_results else {}
        bs_rows = sa.get("BS", []) if isinstance(sa, dict) else []
        cash = get_subject_cash(bs_rows, inputs.subject_ticker)
    else:
        pf = (session_data or {}).get("private_bs_data") or {}
        cash = pf.get("cash", {}).get("TTM") if isinstance(pf, dict) else None

    debt = get_subject_debt(session_data or {}, source_results or {})
    pref = get_subject_metric_value(session_data or {}, source_results or {}, "preferred_stock", "TTM")
    nci = get_subject_metric_value(session_data or {}, source_results or {}, "minority_interest", "TTM")

    bi = BridgeInputs(
        cash=cash,
        nwc_surplus=nwc,
        non_operating=non_op,
        debt=debt,
        preferred_stock=pref,
        minority_interest=nci,
        control_premium=control_premium,
        dloc=dloc,
        shares_outstanding=None,
        share_price=None,
    )

    source_basis = "Equity" if basis_mode == "EQUITY" else "BEV"
    bridge_result = run_bridge(
        fmv_low,
        fmv_high,
        natural_level="minority",
        source_basis=source_basis,
        bi=bi,
        equity_mode_includes_cash=False,
    )

    def _row(label, low, high):
        return html.Tr([
            html.Td(label, style={"minWidth": f"{LEADING_W}px", "whiteSpace": "normal"}),
            html.Td(f"{high:,.0f}" if high is not None else "NA",
                    style={"textAlign": "right", "minWidth": f"{COL_W['metric']}px"}),
            html.Td(f"{low:,.0f}" if low is not None else "NA",
                    style={"textAlign": "right", "minWidth": f"{COL_W['metric']}px"}),
        ])

    bridge_rows = [
        html.Tr([html.Th("", style={"minWidth": f"{LEADING_W}px"}),
                 html.Th("High", style={"textAlign": "right"}), html.Th("Low", style={"textAlign": "right"})]),
    ]
    for lbl, lo, hi in bridge_result.get("lines", []):
        bridge_rows.append(_row(lbl, lo, hi))

    bev_ctrl_lo, bev_ctrl_hi = bridge_result.get("bev_controlling", (None, None))
    eq_ctrl_lo, eq_ctrl_hi = bridge_result.get("equity_controlling", (None, None))
    if source_basis == "BEV":
        bridge_rows.append(_row("BEV (controlling, marketable) --> send to Dashboard", bev_ctrl_lo, bev_ctrl_hi))
    else:
        bridge_rows.append(_row("Equity Value (controlling, marketable) --> send to Dashboard", eq_ctrl_lo, eq_ctrl_hi))

    bridge_table = html.Table(
        [html.Thead(bridge_rows[0]), html.Tbody(bridge_rows[1:])],
        className="table table-sm table-dark mb-0", style={"width": "max-content", "minWidth": "100%"},
    )

    return subject_table, weighting_table, bridge_table

# -------------------------------------------------------------
# CALLBACK — restore static controls when:
#   (1) session-load-timestamp fires (Open/New Session), or
#   (2) user navigates to /gpc (page remount — layout defaults otherwise win)
# Do NOT key only off session-store: persist_gpc_state writes session-store
# constantly and would fight the user; remount wouldn't re-run either.
# -------------------------------------------------------------
@callback(
    Output("gpc-num-multiples", "value"),
    Output("gpc-basis-toggle", "value"),
    Output("gpc-dloc-pct", "value"),
    Output("gpc-control-premium-pct", "value"),
    Output("gpc-nwc-input", "value"),
    Output("gpc-non-op-input", "value"),
    Output("gpc-exclude-store", "data", allow_duplicate=True),
    Input("session-load-timestamp", "data"),
    Input("_pages_location", "pathname"),
    State("session-store", "data"),
    prevent_initial_call='initial_duplicate',  # <-- add this
)
def restore_gpc_static_state(_load_ts, pathname, session_data):
    # Only hydrate when landing on this page (or global session load while here)
    if pathname not in ("/gpc", "/gpc/"):
        return (no_update,) * 7

    gpc_state = (session_data or {}).get("gpc_page_state") or {}
    if not gpc_state:
        return (no_update,) * 7

    return (
        gpc_state.get("num_multiples", MAX_COLS_CAP),
        (
            "EQUITY"
            if (session_data or {}).get("basis_of_value") == "Equity Value"
            else "BEV"
        ),
        gpc_state.get("dloc", "0%"),
        gpc_state.get("control_premium", "0%"),
        (
            f"{(session_data or {}).get('nwc_page_state', {}).get('surplus_deficit'):,.0f}"
            if ((session_data or {}).get("nwc_page_state") or {}).get("surplus_deficit") is not None
            else gpc_state.get("nwc", "0")
        ),
        gpc_state.get("non_op", "0"),
        gpc_state.get("exclude_map") or {},
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
    prev = dict(session_data.get("gpc_page_state") or {})

    triggered = ctx.triggered_id
    trigger_type = triggered.get("type") if isinstance(triggered, dict) else triggered

    # Determine basis contexts
    prev_basis = _basis_key(prev.get("basis_mode", basis_mode or "BEV"))
    current_basis = _basis_key(basis_mode or prev.get("basis_mode", "BEV"))

    # Hydrate current per-basis state buckets
    basis_state = _migrate_gpc_basis_state(prev, prev_basis)
    bucket = dict(basis_state.get(current_basis) or {})
    for k in _BASIS_SLICE_KEYS:
        bucket[k] = dict(bucket.get(k) or {})

    # SLICE-AWARE RECALCULATION:
    # We only update the dynamic GPC slice that actually triggered this callback.
    # If the trigger was a basis toggle, page navigation, or static control,
    # we preserve the saved selections for that basis exactly, preventing
    # unmounted/temporary dropdown states from wiping them.
    if trigger_type == "gpc-metric-col" and metric_col_ids:
        valid_options = set(dropdown_options(current_basis))
        bucket["metric_cols"] = {
            str(id_dict["index"]): val
            for val, id_dict in zip(metric_col_values or [], metric_col_ids or [])
            if id_dict is not None and val in valid_options
        }

    elif trigger_type in ("gpc-selected-high", "gpc-selected-low"):
        if selected_highs is not None and len(selected_highs) > 0:
            bucket["selected_high"] = {str(i): v for i, v in enumerate(selected_highs)}
        if selected_lows is not None and len(selected_lows) > 0:
            bucket["selected_low"] = {str(i): v for i, v in enumerate(selected_lows)}

    elif trigger_type == "gpc-weight" and weight_ids:
        bucket["weights"] = {
            str(id_dict["index"]): val
            for val, id_dict in zip(weight_values or [], weight_ids or [])
            if id_dict is not None
        }

    basis_state[current_basis] = bucket

    # Exclusions are shared across both bases
    saved_exclude_map = (
        exclude_map
        if trigger_type == "gpc-exclude-store" and exclude_map is not None
        else (prev.get("exclude_map") or {})
    )

    session_data["gpc_page_state"] = {
        "num_multiples": num_multiples if num_multiples is not None else prev.get("num_multiples", MAX_COLS_CAP),
        "basis_mode": current_basis,
        "dloc": dloc if dloc is not None else prev.get("dloc", "0%"),
        "control_premium": control_premium if control_premium is not None else prev.get("control_premium", "0%"),
        "nwc": nwc if nwc is not None else prev.get("nwc", "0"),
        "non_op": non_op if non_op is not None else prev.get("non_op", "0"),
        "basis_state": basis_state,
        "metric_cols": bucket.get("metric_cols", {}),
        "selected_high": bucket.get("selected_high", {}),
        "selected_low": bucket.get("selected_low", {}),
        "weights": bucket.get("weights", {}),
        "exclude_map": saved_exclude_map,
    }
    return session_data

# -------------------------------------------------------------
# CALLBACK — GPC range chart modal
# -------------------------------------------------------------
@callback(
    Output("gpc-chart-modal", "is_open"),
    Input("gpc-chart-link", "n_clicks"),
    Input("gpc-chart-close", "n_clicks"),
    State("gpc-chart-modal", "is_open"),
    prevent_initial_call=True,
)
def toggle_gpc_chart(open_clicks, close_clicks, is_open):
    trig = ctx.triggered_id
    if trig == "gpc-chart-link":
        return True
    if trig == "gpc-chart-close":
        return False
    return bool(is_open)


@callback(
    Output("gpc-chart-container", "children"),
    Input("gpc-chart-modal", "is_open"),
    State({"type": "gpc-metric-col", "index": ALL}, "value"),
    State("gpc-basis-toggle", "value"),
    State("gpc-exclude-store", "data"),
    State("session-store", "data"),
    State("source-results-store", "data"),
)
def render_gpc_chart(is_open, metric_col_values, basis_mode, exclude_map,
                     session_data, source_results):
    if not is_open:
        return no_update

    inputs = dict_to_project_inputs(session_data or {})
    tickers = inputs.gpc_tickers or []
    exclude_map = exclude_map or {}
    metric_col_values = metric_col_values or []
    basis_mode = _basis_key(basis_mode)

    if not tickers or not metric_col_values:
        return dbc.Alert("No GPC data to chart yet.", color="secondary")

    sa = (source_results or {}).get("stockanalysis", {}) if source_results else {}
    is_rows = sa.get("IS", [])
    bs_rows = sa.get("BS", [])
    ratio_rows = sa.get("Ratios", [])
    ms_rows = (source_results or {}).get("marketscreener", []) if source_results else []

    all_multiples = compute_all_gpc_multiples(
        is_rows, ms_rows, ratio_rows, bs_rows, tickers, basis_mode=basis_mode
    )
    included = [t for t in tickers if not exclude_map.get(t, False)]

    labels, q3, mx, mn, q1 = [], [], [], [], []
    for col_metric in metric_col_values:
        vals = [all_multiples.get(t, {}).get(col_metric) for t in included]
        stats = _compute_stats(vals)
        labels.append(col_metric)
        q3.append(stats["Third Quartile"])
        mx.append(stats["Maximum"])
        mn.append(stats["Minimum"])
        q1.append(stats["First Quartile"])

    fig = gt_range_chart(
        labels=labels,
        q3=q3,
        max_vals=mx,
        min_vals=mn,
        q1=q1,
        title="Range of Selected Multiples",
    )

    return dcc.Graph(
        figure=fig,
        config={"displayModeBar": False},
        style={"height": "520px"},
    )