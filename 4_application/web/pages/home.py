import dash
import dash_bootstrap_components as dbc
from dash import html, dcc, Input, Output, State, callback, dash_table, ALL
import yfinance as yf

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
                    dbc.Input(id="input-client", value="Ted & Co.", className="mb-2", debounce=True, persistence=True, persistence_type="session"),

                    dbc.Label("Subject Company Name"),
                    dbc.Input(id="input-subject-name", value="COMPANY NAME", className="mb-2", debounce=True, persistence=True, persistence_type="session"),

                    dbc.Label("Main Title"),
                    dbc.Input(id="input-main-title", value="Sensitivity Analysis of COMPANY NAME", className="mb-2", debounce=True, persistence=True, persistence_type="session"),

                    dbc.Label("Valuation Date"),
                    dbc.Input(id="input-val-date", value="7/21/2026", className="mb-2", debounce=True, persistence=True, persistence_type="session"),

                    dbc.Row([
                        dbc.Col([
                            dbc.Label("Numeric Scale"),
                            dbc.Select(id="select-numeric-scale",
                                       options=["Millions", "Thousands", "Actual"],
                                       value="Millions", persistence=True, persistence_type="session")
                        ], md=6),
                        dbc.Col([
                            dbc.Label("Draft/Final"),
                            dbc.Select(id="select-draft-final",
                                       options=["Draft", "Final"],
                                       value="Draft", persistence=True, persistence_type="session")
                        ], md=6),
                    ], className="mb-2"),

                    dbc.Row([
                        dbc.Col([
                            dbc.Label("Standard of Value"),
                            dbc.Select(id="select-standard-val",
                                       options=["Fair Market Value", "Investment Value", "Intrinsic Value"],
                                       value="Fair Market Value", persistence=True, persistence_type="session")
                        ], md=4),
                        dbc.Col([
                            dbc.Label("Taxable Status"),
                            dbc.Select(id="select-taxable",
                                       options=["Taxable/Nontaxable", "Taxable", "Nontaxable"],
                                       value="Taxable/Nontaxable", persistence=True, persistence_type="session")
                        ], md=4),
                        dbc.Col([
                            dbc.Label("Basis of Value"),
                            dbc.Select(id="select-basis-val",
                                       options=["BEV / Equity Value", "Business Enterprise Value", "Equity Value"],
                                       value="BEV / Equity Value", persistence=True, persistence_type="session")
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
                        className="mb-2",
                        persistence=True, persistence_type="session"
                    ),

                    html.Div(id="div-subject-ticker", children=[
                        dbc.Label("Subject Ticker"),
                        dbc.Input(id="input-subject-ticker", value="SPCX", className="mb-2", debounce=True, persistence=True, persistence_type="session")
                    ], style={"display": "none"}),

                    dbc.Label("Tax Rate"),
                    dbc.Input(id="input-tax-rate", value="21%", className="mb-2", debounce=True, persistence=True, persistence_type="session"),

                    dbc.Row([
                        dbc.Col([dbc.Label("Last Fiscal Year"),
                                 dbc.Input(id="input-lfy", value="12/31/2025", className="mb-2", debounce=True, persistence=True, persistence_type="session")], md=6),
                        dbc.Col([dbc.Label("Last Fiscal Quarter"),
                                 dbc.Input(id="input-fq", value="3/31/2026", className="mb-2", debounce=True, persistence=True, persistence_type="session")], md=6),
                    ]),
                    dbc.Row([
                        dbc.Col([dbc.Label("Next FY End"),
                                 dbc.Input(id="input-nfy", value="12/31/2026", className="mb-2", debounce=True, persistence=True, persistence_type="session")], md=4),
                        dbc.Col([dbc.Label("Next FY End + 1"),
                                 dbc.Input(id="input-nfy1", value="12/31/2027", className="mb-2", debounce=True, persistence=True, persistence_type="session")], md=4),
                        dbc.Col([dbc.Label("Next FY End + 2"),
                                 dbc.Input(id="input-nfy2", value="12/31/2028", className="mb-2", debounce=True, persistence=True, persistence_type="session")], md=4),
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
                                    persistence=True, persistence_type="session",
                                    style={"width": "110px"}
                                )),
                                html.Td(dbc.Input(
                                    id={"type": "gpc-name-input", "index": i},
                                    value="",
                                    placeholder="Company Name",
                                    readonly=True,
                                    size="sm",
                                    persistence=True, persistence_type="session"
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
                        persistence=True, persistence_type="session",
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
                            dbc.Input(id="input-hist-years", type="number", min=0, max=5, value=5, debounce=True, persistence=True, persistence_type="session")
                        ], md=6),
                        dbc.Col([
                            dbc.Label("Projection Years (1-20)"),
                            dbc.Input(id="input-proj-years", type="number", min=1, max=20, value=5, debounce=True, persistence=True, persistence_type="session")
                        ], md=6),
                    ])
                ])
            ], color="secondary", outline=True, className="mb-4")
        ], width=12)
    ])
], fluid=True)


# -------------------------------------------------------------
# CALLBACKS
# -------------------------------------------------------------

@callback(
    Output("div-subject-ticker", "style"),
    Input("select-company-status", "value")
)
def toggle_subject_ticker(status):
    return {"display": "block"} if status == "Publicly Traded" else {"display": "none"}


@callback(
    Output({"type": "gpc-name-input", "index": ALL}, "value"),
    Input({"type": "gpc-ticker-input", "index": ALL}, "value"),
)
def update_gpc_company_names(tickers):
    names = []
    for ticker in tickers:
        t = (ticker or "").strip().upper()
        if not t:
            names.append("")
            continue
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