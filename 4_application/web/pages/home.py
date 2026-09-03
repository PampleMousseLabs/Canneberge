import dash
import dash_bootstrap_components as dbc
from dash import html, dcc, Input, Output, State, callback, dash_table, ALL, no_update, ctx
import yfinance as yf

from Canneberge.app_state import IS_LINES, BS_LINES
from web.lib.session_io import _clean_float
from web.components import projection_modal

dash.register_page(__name__, path="/", name="Home & Inputs")

DEFAULT_GPC = ["RKLB", "AMZN", "FLY", "ASTS", "GOOG", "IRDM", "PLTR", "SOUN", "NBIS"]

DEFAULT_GT = [
    {"closing_date": "6/29/2026", "target": "Iridium Communications Lab", "acquirer": "Rocket Lab",
     "bev": "8000", "ttm_revenue": "871.7", "ttm_ebitda": "495", "ttm_ebit": "236"},
    {"closing_date": "6/15/2026", "target": "Comtech Satellite & Space", "acquirer": "Gilat Satellite Networks",
     "bev": "157.5", "ttm_revenue": "195.2", "ttm_ebitda": "16.8", "ttm_ebit": ""},
    {"closing_date": "8/15/2024", "target": "Terran Orbital", "acquirer": "Lockheed Martin",
     "bev": "450", "ttm_revenue": "94.2", "ttm_ebitda": "", "ttm_ebit": ""},
    {"closing_date": "", "target": "", "acquirer": "", "bev": "", "ttm_revenue": "", "ttm_ebitda": "", "ttm_ebit": ""},
    {"closing_date": "", "target": "", "acquirer": "", "bev": "", "ttm_revenue": "", "ttm_ebitda": "", "ttm_ebit": ""},
]


def _build_project_inputs(
    client, subj_name, main_title, val_date, scale, draft, standard_val, taxable, basis_val,
    status, subj_ticker, tax_rate, lfy, fq, nfy, nfy1, nfy2,
    gpc_tickers, gpc_names, gt_data, hist_yrs, proj_yrs, existing=None
):
    existing = existing or {}

    gpc_dict = {}
    valid_tickers = []
    for t, n in zip(gpc_tickers or [], gpc_names or []):
        t_clean = (t or "").strip().upper()
        if t_clean:
            valid_tickers.append(t_clean)
            gpc_dict[t_clean] = (n or t_clean)

    return {
        "disk_session_name": existing.get("disk_session_name"),
        "client": client,
        "subject_company_name": subj_name,
        "main_title": main_title,
        "valuation_date": val_date,
        "numeric_scale": scale,
        "draft_final": draft,
        "standard_of_value": standard_val,
        "taxable_nontaxable": taxable,
        "basis_of_value": basis_val,
        "company_status": status,
        "subject_ticker": (subj_ticker or "").strip().upper() if status == "Publicly Traded" else "",
        "subject_tax_rate": tax_rate,
        "last_fiscal_year": lfy,
        "last_fiscal_quarter": fq,
        "next_fiscal_year": nfy,
        "nfy_1": nfy1,
        "nfy_2": nfy2,
        "gpc_tickers": valid_tickers,
        "gpc_company_names": gpc_dict,
        "gt_transactions": gt_data or [],
        "historical_years": hist_yrs,
        "projection_years": proj_yrs,
        "status": "live",
        # Preserve blobs owned by other surfaces (modals / future pages).
        # Without this, any Home autosync wipes private financials & projections.
        "private_is_data": existing.get("private_is_data", {}) or {},
        "private_bs_data": existing.get("private_bs_data", {}) or {},
        "projection_page_state": existing.get("projection_page_state", {}) or {},
        "gt_page_state": existing.get("gt_page_state", {}) or {},
        "gpc_page_state": existing.get("gpc_page_state", {}) or {},
        "wacc_page_state": existing.get("wacc_page_state", {}) or {},
        "dcf_page_state": existing.get("dcf_page_state", {}) or {},
        "nwc_page_state": existing.get("nwc_page_state", {}) or {},
        "debt_page_state": existing.get("debt_page_state", {}) or {},
        "dashboard_page_state": existing.get("dashboard_page_state", {}) or {},
    }


layout = dbc.Container([
    # Live status alert
    dbc.Alert(
        id="home-live-status",
        children="Live session will update automatically as you edit fields.",
        color="secondary",
        className="py-2",
    ),

    # -------------------------------------------------------------
    # 1. GENERAL & SUBJECT COMPANY
    # -------------------------------------------------------------
    dbc.Row([
        dbc.Col([
            dbc.Card([
                dbc.CardHeader(html.H5("GENERAL", className="text-light mb-0")),
                dbc.CardBody([
                    dbc.Label("Client"),
                    dbc.Input(id="input-client", value="Ted & Co.", className="mb-2", debounce=True),

                    dbc.Label("Subject Company Name"),
                    dbc.Input(id="input-subject-name", value="COMPANY NAME", className="mb-2", debounce=True),

                    dbc.Label("Main Title"),
                    dbc.Input(id="input-main-title", value="Sensitivity Analysis of COMPANY NAME", className="mb-2", debounce=True),

                    dbc.Label("Valuation Date"),
                    dbc.Input(id="input-val-date", value="7/21/2026", className="mb-2", debounce=True),

                    dbc.Row([
                        dbc.Col([
                            dbc.Label("Numeric Scale"),
                            dbc.Select(id="select-numeric-scale",
                                       options=["Millions", "Thousands", "Actual"],
                                       value="Millions")
                        ], md=6),
                        dbc.Col([
                            dbc.Label("Draft/Final"),
                            dbc.Select(id="select-draft-final",
                                       options=["Draft", "Final"],
                                       value="Draft")
                        ], md=6),
                    ], className="mb-2"),

                    dbc.Row([
                        dbc.Col([
                            dbc.Label("Standard of Value"),
                            dbc.Select(id="select-standard-val",
                                       options=["Fair Market Value", "Investment Value", "Intrinsic Value"],
                                       value="Fair Market Value")
                        ], md=4),
                        dbc.Col([
                            dbc.Label("Taxable Status"),
                            dbc.Select(id="select-taxable",
                                       options=["Taxable/Nontaxable", "Taxable", "Nontaxable"],
                                       value="Taxable/Nontaxable")
                        ], md=4),
                        dbc.Col([
                            dbc.Label("Basis of Value"),
                            dbc.Select(id="select-basis-val",
                                       options=["BEV / Equity Value", "Business Enterprise Value", "Equity Value"],
                                       value="BEV / Equity Value")
                        ], md=4),
                    ])
                ])
            ], color="secondary", outline=True, className="mb-4")
        ], lg=6),

        dbc.Col([
            dbc.Card([
                dbc.CardHeader(html.H5("SUBJECT COMPANY", className="text-light mb-0")),
                dbc.CardBody([
                    dbc.Label("Company Status"),
                    dbc.Select(
                        id="select-company-status",
                        options=["Private Company", "Publicly Traded"],
                        value="Private Company",
                        className="mb-2"
                    ),

                    html.Div(id="div-subject-ticker", children=[
                        dbc.Label("Subject Ticker"),
                        dbc.Input(id="input-subject-ticker", value="SPCX", className="mb-2", debounce=True)
                    ], style={"display": "none"}),

                    # Popout launchers (mirror desktop hyperlinks under Subject Company)
                    html.Div([
                        html.Div(id="div-enter-fin-link", children=[
                            html.A("Enter Financial Data →",
                                   id="link-open-private-fin",
                                   href="#",
                                   className="fw-bold",
                                   style={"color": "#f0ad4e", "textDecoration": "underline"}),
                        ], style={"display": "none"}, className="mb-1"),
                        html.Div([
                            html.A("Projection Module →",
                                   id="link-open-projection",
                                   href="#",
                                   className="fw-bold",
                                   style={"color": "#f0ad4e", "textDecoration": "underline"}),
                        ], className="mb-2"),
                    ]),

                    dbc.Label("Tax Rate"),
                    dbc.Input(id="input-tax-rate", value="21%", className="mb-2", debounce=True),

                    dbc.Row([
                        dbc.Col([dbc.Label("Last Fiscal Year"),
                                 dbc.Input(id="input-lfy", value="12/31/2025", className="mb-2", debounce=True)], md=6),
                        dbc.Col([dbc.Label("Last Fiscal Quarter"),
                                 dbc.Input(id="input-fq", value="3/31/2026", className="mb-2", debounce=True)], md=6),
                    ]),
                    dbc.Row([
                        dbc.Col([dbc.Label("Next FY End"),
                                 dbc.Input(id="input-nfy", value="12/31/2026", className="mb-2", debounce=True)], md=4),
                        dbc.Col([dbc.Label("Next FY End + 1"),
                                 dbc.Input(id="input-nfy1", value="12/31/2027", className="mb-2", debounce=True)], md=4),
                        dbc.Col([dbc.Label("Next FY End + 2"),
                                 dbc.Input(id="input-nfy2", value="12/31/2028", className="mb-2", debounce=True)], md=4),
                    ]),
                ])
            ], color="secondary", outline=True, className="mb-4")
        ], lg=6),
    ]),

    # -------------------------------------------------------------
    # 2. MARKET INPUTS
    # -------------------------------------------------------------
    dbc.Row([
        dbc.Col([
            dbc.Card([
                dbc.CardHeader(html.H5("MARKET INPUTS: GPC (Peer Tickers)", className="text-light mb-0")),
                dbc.CardBody([
                    html.Table([
                        html.Thead(html.Tr([
                            html.Th("#"), html.Th("Entered Ticker"), html.Th("Company Name")
                        ])),
                        html.Tbody([
                            html.Tr([
                                html.Td(str(i + 1), style={"width": "30px"}),
                                html.Td(dbc.Input(
                                    id={"type": "gpc-ticker-input", "index": i},
                                    value=DEFAULT_GPC[i] if i < len(DEFAULT_GPC) else "",
                                    placeholder="Ticker...",
                                    size="sm",
                                    debounce=True,
                                    style={"width": "110px"}
                                )),
                                html.Td(dbc.Input(
                                    id={"type": "gpc-name-input", "index": i},
                                    value="",
                                    placeholder="Company Name",
                                    readonly=True,
                                    size="sm"
                                ))
                            ]) for i in range(15)
                        ])
                    ], className="table table-dark table-sm align-middle mb-0")
                ])
            ], color="secondary", outline=True, className="mb-4")
        ], lg=5),

        dbc.Col([
            dbc.Card([
                dbc.CardHeader(html.H5("MARKET INPUTS: GT (Transactions)", className="text-light mb-0")),
                dbc.CardBody([
                    dash_table.DataTable(
                        id="gt-transactions-table",
                        columns=[
                            {"name": "Closing Date", "id": "closing_date", "editable": True},
                            {"name": "Target Company", "id": "target", "editable": True},
                            {"name": "Acquirer", "id": "acquirer", "editable": True},
                            {"name": "BEV", "id": "bev", "editable": True},
                            {"name": "TTM Rev", "id": "ttm_revenue", "editable": True},
                            {"name": "TTM EBITDA", "id": "ttm_ebitda", "editable": True},
                            {"name": "TTM EBIT", "id": "ttm_ebit", "editable": True},
                        ],
                        data=DEFAULT_GT,
                        editable=True,
                        style_header={"backgroundColor": "#2b3e50", "color": "white", "fontWeight": "bold"},
                        style_cell={"backgroundColor": "#1e1e1e", "color": "white", "fontSize": "12px"},
                        style_table={"overflowX": "auto"},
                    )
                ])
            ], color="secondary", outline=True, className="mb-4")
        ], lg=7),
    ]),

    # -------------------------------------------------------------
    # 3. PROJECTION CONTROLS
    # -------------------------------------------------------------
    dbc.Row([
        dbc.Col([
            dbc.Card([
                dbc.CardHeader(html.H5("PROJECTION CONTROLS", className="text-light mb-0")),
                dbc.CardBody([
                    dbc.Row([
                        dbc.Col([
                            dbc.Label("Historical Years (0-5)"),
                            dbc.Input(id="input-hist-years", type="number", min=0, max=5, value=5, debounce=True)
                        ], md=6),
                        dbc.Col([
                            dbc.Label("Projection Years (1-20)"),
                            dbc.Input(id="input-proj-years", type="number", min=1, max=20, value=5, debounce=True)
                        ], md=6),
                    ])
                ])
            ], color="secondary", outline=True, className="mb-4")
        ], width=12)
    ]),

    # -------------------------------------------------------------
    # POPOUT MODALS
    # -------------------------------------------------------------
    dcc.Store(id="private-fin-periods-store", storage_type="memory"),

    # Private Financials Modal — layout + callbacks live in this file
    dbc.Modal(
        [
            dbc.ModalHeader(dbc.ModalTitle("Enter Private Financial Data"), close_button=False),
            dbc.ModalBody([
                dbc.Alert(
                    id="private-fin-status",
                    color="secondary",
                    className="py-2",
                    children="Edit values below. Save commits to the live session.",
                ),
                dbc.RadioItems(
                    id="private-fin-stmt-toggle",
                    options=[
                        {"label": "Income Statement (IS)", "value": "IS"},
                        {"label": "Balance Sheet (BS)", "value": "BS"},
                    ],
                    value="IS",
                    inline=True,
                    inputClassName="btn-check",
                    labelClassName="btn btn-outline-info size-sm",
                    labelCheckedClassName="active",
                    className="mb-2",
                ),
                html.Div(
                    id="private-fin-grid-container",
                    style={
                        "maxHeight": "60vh",
                        "overflowY": "auto",
                        "overflowX": "auto",
                        "border": "1px solid #444",
                        "borderRadius": "4px",
                    },
                ),
            ]),
            dbc.ModalFooter([
                dbc.Button("Cancel", id="btn-private-fin-cancel", color="secondary", n_clicks=0),
                dbc.Button("Save", id="btn-private-fin-save", color="primary", n_clicks=0),
            ]),
        ],
        id="modal-private-fin",
        is_open=False,
        size="xl",
        backdrop="static",
        keyboard=False,
        scrollable=True,
    ),

    # Projection Module Modal — layout + callbacks live in web/components/projection_modal.py
    projection_modal.layout,
], fluid=True)


# -------------------------------------------------------------
# CALLBACKS
# -------------------------------------------------------------

@callback(
    Output("div-subject-ticker", "style"),
    Output("div-enter-fin-link", "style"),
    Input("select-company-status", "value")
)
def toggle_subject_ticker(status):
    is_public = (status == "Publicly Traded")
    return (
        {"display": "block"} if is_public else {"display": "none"},
        {"display": "none"} if is_public else {"display": "block"},
    )


@callback(
    Output({"type": "gpc-name-input", "index": ALL}, "value"),
    Input({"type": "gpc-ticker-input", "index": ALL}, "value"),
    State("session-store", "data")
)
def update_gpc_company_names(tickers, session_data):
    session_data = session_data or {}
    saved_names = session_data.get("gpc_company_names", {})
    names = []
    for ticker in tickers:
        t = (ticker or "").strip().upper()
        if not t:
            names.append("")
            continue
        # Use cache first to prevent yfinance rate-limiting / load delays
        if t in saved_names and saved_names[t]:
            names.append(saved_names[t])
        else:
            try:
                info = yf.Ticker(t).info
                names.append(info.get("longName") or info.get("shortName") or t)
            except Exception:
                names.append("")
    return names


# AUTO-SYNC: any Home field change updates live session memory
@callback(
    Output("session-store", "data"),
    Output("home-live-status", "children"),
    Input("input-client", "value"),
    Input("input-subject-name", "value"),
    Input("input-main-title", "value"),
    Input("input-val-date", "value"),
    Input("select-numeric-scale", "value"),
    Input("select-draft-final", "value"),
    Input("select-standard-val", "value"),
    Input("select-taxable", "value"),
    Input("select-basis-val", "value"),
    Input("select-company-status", "value"),
    Input("input-subject-ticker", "value"),
    Input("input-tax-rate", "value"),
    Input("input-lfy", "value"),
    Input("input-fq", "value"),
    Input("input-nfy", "value"),
    Input("input-nfy1", "value"),
    Input("input-nfy2", "value"),
    Input({"type": "gpc-ticker-input", "index": ALL}, "value"),
    Input({"type": "gpc-name-input", "index": ALL}, "value"),
    Input("gt-transactions-table", "data"),
    Input("input-hist-years", "value"),
    Input("input-proj-years", "value"),
    State("session-store", "data"),
)
def autosync_session(
    client, subj_name, main_title, val_date, scale, draft, standard_val, taxable, basis_val,
    status, subj_ticker, tax_rate, lfy, fq, nfy, nfy1, nfy2,
    gpc_tickers, gpc_names, gt_data, hist_yrs, proj_yrs, existing
):
    data = _build_project_inputs(
        client, subj_name, main_title, val_date, scale, draft, standard_val, taxable, basis_val,
        status, subj_ticker, tax_rate, lfy, fq, nfy, nfy1, nfy2,
        gpc_tickers, gpc_names, gt_data, hist_yrs, proj_yrs, existing
    )
    n = len(data["gpc_tickers"])
    status_text = f"Live session updated • {data['subject_company_name']} • {n} GPC tickers"
    return data, status_text


# DECOUPLED LOAD HYDRATION: Runs ONLY when a session is loaded or started fresh,
# preventing active typing feedback loops or cursor jumps.
@callback(
    Output("input-client", "value"),
    Output("input-subject-name", "value"),
    Output("input-main-title", "value"),
    Output("input-val-date", "value"),
    Output("select-numeric-scale", "value"),
    Output("select-draft-final", "value"),
    Output("select-standard-val", "value"),
    Output("select-taxable", "value"),
    Output("select-basis-val", "value"),
    Output("select-company-status", "value"),
    Output("input-subject-ticker", "value"),
    Output("input-tax-rate", "value"),
    Output("input-lfy", "value"),
    Output("input-fq", "value"),
    Output("input-nfy", "value"),
    Output("input-nfy1", "value"),
    Output("input-nfy2", "value"),
    Output({"type": "gpc-ticker-input", "index": ALL}, "value"),
    Output("gt-transactions-table", "data"),
    Output("input-hist-years", "value"),
    Output("input-proj-years", "value"),
    Input("session-load-timestamp", "data"),
    State("session-store", "data"),
)
def hydrate_home_page_from_load(load_timestamp, session_data):
    # If the user refreshes their browser and there's a cached session, we want
    # it to populate. If there's no data, let layout defaults stand.
    # Note: 21 items returned here to match the 21 outputs exactly.
    if not session_data:
        return [no_update] * 21

    try:
        client = session_data.get("client", "Ted & Co.")
        subj_name = session_data.get("subject_company_name", "COMPANY NAME")
        main_title = session_data.get("main_title", "")
        val_date = session_data.get("valuation_date", "7/21/2026")
        scale = session_data.get("numeric_scale", "Millions")
        draft = session_data.get("draft_final", "Draft")
        standard_val = session_data.get("standard_of_value", "Fair Market Value")
        taxable = session_data.get("taxable_nontaxable", "Taxable/Nontaxable")
        basis_val = session_data.get("basis_of_value", "BEV / Equity Value")
        status = session_data.get("company_status", "Private Company")
        subj_ticker = session_data.get("subject_ticker", "SPCX")

        tax_rate = session_data.get("subject_tax_rate", 0.21)
        if isinstance(tax_rate, float):
            tax_rate = f"{tax_rate * 100:.1f}%" if tax_rate <= 1.0 else f"{tax_rate}%"

        lfy = session_data.get("last_fiscal_year", "12/31/2025")
        fq = session_data.get("last_fiscal_quarter", "3/31/2026")
        nfy = session_data.get("next_fiscal_year", "12/31/2026")
        nfy1 = session_data.get("nfy_1", "12/31/2027")
        nfy2 = session_data.get("nfy_2", "12/31/2028")

        saved_tickers = session_data.get("gpc_tickers", [])

        gpc_tickers_out = []
        for i in range(15):
            if i < len(saved_tickers):
                gpc_tickers_out.append(saved_tickers[i])
            else:
                gpc_tickers_out.append("")

        gt_transactions = session_data.get("gt_transactions", DEFAULT_GT)

        hist_yrs = session_data.get("historical_years", 5)
        proj_yrs = session_data.get("projection_years", 5)

        return (
            client, subj_name, main_title, val_date, scale, draft, standard_val, taxable, basis_val,
            status, subj_ticker, tax_rate, lfy, fq, nfy, nfy1, nfy2,
            gpc_tickers_out, gt_transactions, hist_yrs, proj_yrs
        )
    except Exception as e:
        import traceback
        print("❌ Error during Home Page Hydration Callback:")
        traceback.print_exc()
        return [no_update] * 21


# ============================================================
# PRIVATE FINANCIALS MODAL — native inputs
# ============================================================

_PERIOD_FALLBACK = ["LFY-4", "LFY-3", "LFY-2", "LFY-1", "LFY", "TTM"]

# Readable inputs on dark modal (Bootstrap dark inputs are too low-contrast)
_PRIV_INPUT_STYLE = {
    "backgroundColor": "#2a2a2a",
    "color": "#f5f5f5",
    "border": "1px solid #666",
    "textAlign": "right",
    "fontSize": "12px",
    "minWidth": "88px",
}


def _private_periods_from_session(session_data: dict) -> list:
    from web.lib.session_io import dict_to_project_inputs
    inputs = dict_to_project_inputs(session_data or {})
    cols = list(inputs.historical_period_columns) + ["TTM"]
    return cols if cols else list(_PERIOD_FALLBACK)


def _private_raw_lines(statement: str):
    lines = IS_LINES if statement == "IS" else BS_LINES
    return [(k, label) for k, label, is_calc, _bold in lines if not is_calc]


def _build_private_fin_table(statement: str, blob: dict, periods: list):
    """html.Table of native inputs — backspace/arrows work like normal forms."""
    blob = blob or {}
    header = html.Tr(
        [html.Th("Line Item", style={"position": "sticky", "top": 0, "left": 0, "zIndex": 3,
                                      "backgroundColor": "#2b3e50", "color": "white",
                                      "padding": "6px 10px", "minWidth": "220px"})]
        + [
            html.Th(
                p,
                style={
                    "position": "sticky",
                    "top": 0,
                    "zIndex": 2,
                    "backgroundColor": "#2b3e50",
                    "color": "white",
                    "padding": "6px 8px",
                    "textAlign": "center",
                    "minWidth": "96px",
                },
            )
            for p in periods
        ]
    )

    body_rows = []
    for key, label in _private_raw_lines(statement):
        per = blob.get(key, {}) or {}
        cells = [
            html.Td(
                label,
                style={
                    "position": "sticky",
                    "left": 0,
                    "zIndex": 1,
                    "backgroundColor": "#1e1e1e",
                    "color": "#eee",
                    "padding": "4px 10px",
                    "whiteSpace": "nowrap",
                    "fontSize": "12px",
                    "border": "1px solid #333",
                },
            )
        ]
        for p in periods:
            raw = per.get(p)
            val = "" if raw is None else str(raw)
            cells.append(
                html.Td(
                    dbc.Input(
                        id={"type": "priv-fin-cell", "key": key, "period": p},
                        type="text",
                        value=val,
                        debounce=False,
                        style=_PRIV_INPUT_STYLE,
                        size="sm",
                        className="border-0",
                    ),
                    style={"padding": "2px", "border": "1px solid #333", "backgroundColor": "#1e1e1e"},
                )
            )
        body_rows.append(html.Tr(cells))

    return html.Table(
        [html.Thead(header), html.Tbody(body_rows)],
        className="table table-sm mb-0",
        style={"width": "100%", "borderCollapse": "separate", "borderSpacing": 0},
    )


def _harvest_private_cells(ids: list, values: list) -> dict:
    """Build {line_key: {period: float}} from pattern-matching inputs."""
    out = {}
    for id_dict, raw in zip(ids or [], values or []):
        if not id_dict:
            continue
        key = id_dict.get("key")
        period = id_dict.get("period")
        if not key or not period:
            continue
        if raw is None or str(raw).strip() == "":
            continue
        val = _clean_float(raw)
        if val is None:
            continue
        out.setdefault(key, {})[period] = val
    return out


# Open modal + paint grid from committed session (single atomic path)
@callback(
    Output("modal-private-fin", "is_open", allow_duplicate=True),
    Output("private-fin-grid-container", "children"),
    Output("private-fin-periods-store", "data"),
    Output("private-fin-status", "children"),
    Output("private-fin-stmt-toggle", "value"),
    Input("link-open-private-fin", "n_clicks"),
    State("session-store", "data"),
    prevent_initial_call=True,
)
def open_private_fin_modal(n_clicks, session_data):
    if not n_clicks:
        return no_update, no_update, no_update, no_update, no_update
    session_data = session_data or {}
    periods = _private_periods_from_session(session_data)
    blob = session_data.get("private_is_data", {}) or {}
    table = _build_private_fin_table("IS", blob, periods)
    n_filled = sum(1 for k, per in blob.items() for _ in (per or {}))
    status = f"Loaded IS from session · {n_filled} cells · edit freely, then Save or Cancel."
    return True, table, periods, status, "IS"


# IS/BS toggle: re-read session for the other statement
# (edits on the hidden statement are only kept if user Saved; switching without Save
#  reloads that statement from last committed session)
@callback(
    Output("private-fin-grid-container", "children", allow_duplicate=True),
    Output("private-fin-status", "children", allow_duplicate=True),
    Input("private-fin-stmt-toggle", "value"),
    State("session-store", "data"),
    State("private-fin-periods-store", "data"),
    State("modal-private-fin", "is_open"),
    prevent_initial_call=True,
)
def switch_private_fin_statement(stmt, session_data, periods, is_open):
    if not is_open:
        return no_update, no_update
    stmt = stmt or "IS"
    session_data = session_data or {}
    periods = periods or _PERIOD_FALLBACK
    blob_key = "private_is_data" if stmt == "IS" else "private_bs_data"
    blob = session_data.get(blob_key, {}) or {}
    table = _build_private_fin_table(stmt, blob, periods)
    n_filled = sum(len(per or {}) for per in blob.values())
    status = (
        f"Showing {stmt} from last Save · {n_filled} cells. "
        f"Unsaved edits on the other statement were not kept — Save before switching if needed."
    )
    return table, status


# Save: harvest visible cells into the active statement blob; preserve the other
@callback(
    Output("session-store", "data", allow_duplicate=True),
    Output("modal-private-fin", "is_open", allow_duplicate=True),
    Output("private-fin-status", "children", allow_duplicate=True),
    Input("btn-private-fin-save", "n_clicks"),
    State({"type": "priv-fin-cell", "key": ALL, "period": ALL}, "id"),
    State({"type": "priv-fin-cell", "key": ALL, "period": ALL}, "value"),
    State("private-fin-stmt-toggle", "value"),
    State("session-store", "data"),
    prevent_initial_call=True,
)
def save_private_fin(n_clicks, cell_ids, cell_values, stmt, session_data):
    if not n_clicks:
        return no_update, no_update, no_update
    session_data = dict(session_data or {})
    stmt = stmt or "IS"
    blob = _harvest_private_cells(cell_ids, cell_values)
    if stmt == "IS":
        session_data["private_is_data"] = blob
    else:
        session_data["private_bs_data"] = blob
    n_keys = sum(1 for per in blob.values() if per)
    return session_data, False, f"Saved {stmt} ({n_keys} lines)."


@callback(
    Output("modal-private-fin", "is_open", allow_duplicate=True),
    Input("btn-private-fin-cancel", "n_clicks"),
    prevent_initial_call=True,
)
def cancel_private_fin(n_clicks):
    if not n_clicks:
        return no_update
    return False