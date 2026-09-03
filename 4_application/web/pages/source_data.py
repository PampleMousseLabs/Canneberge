import dash
import dash_bootstrap_components as dbc
from dash import html, dcc, Input, Output, State, callback, dash_table, ctx
import pandas as pd
import json

from Canneberge.Services.source_data_service import SourceDataService
from Canneberge.app_state import ProjectInputs, Transaction
from web.lib.ui_layout import (
    grid_table_style,
    grid_header_style,
    grid_cell_style,
    grid_filter_style,
    grid_data_style,
)
from web.lib.ui_layout import grid_table_style

dash.register_page(__name__, path="/source-data", name="Source Data")


# Helper: Convert dcc.Store dictionary into a ProjectInputs dataclass instance
def dict_to_project_inputs(data: dict) -> ProjectInputs:
    if not data:
        return ProjectInputs()
    
    # Reconstruct GT Transactions list if present
    gt_raw = data.get("gt_transactions", [])
    gt_objs = []
    for t in gt_raw:
        if isinstance(t, dict) and any(t.values()):
            try:
                gt_objs.append(Transaction(
                    closing_date=str(t.get("closing_date", "")),
                    target=str(t.get("target", "")),
                    acquirer=str(t.get("acquirer", "")),
                    bev=float(t.get("bev")) if t.get("bev") else None,
                    ttm_revenue=float(t.get("ttm_revenue")) if t.get("ttm_revenue") else None,
                    ttm_ebitda=float(t.get("ttm_ebitda")) if t.get("ttm_ebitda") else None,
                    ttm_ebit=float(t.get("ttm_ebit")) if t.get("ttm_ebit") else None,
                ))
            except Exception:
                pass

    return ProjectInputs(
        client=data.get("client", "Ted & Co."),
        subject_company_name=data.get("subject_company_name", "COMPANY NAME"),
        main_title=data.get("main_title", ""),
        valuation_date=data.get("valuation_date", "7/21/2026"),
        numeric_scale=data.get("numeric_scale", "Millions"),
        draft_final=data.get("draft_final", "Draft"),
        standard_of_value=data.get("standard_of_value", "Fair Market Value"),
        taxable_nontaxable=data.get("taxable_nontaxable", "Taxable/Nontaxable"),
        basis_of_value=data.get("basis_of_value", "BEV / Equity Value"),
        company_status=data.get("company_status", "Private Company"),
        subject_ticker=data.get("subject_ticker", ""),
        last_fiscal_year=data.get("last_fiscal_year", "12/31/2025"),
        last_fiscal_quarter=data.get("last_fiscal_quarter", "3/31/2026"),
        next_fiscal_year=data.get("next_fiscal_year", "12/31/2026"),
        nfy_1=data.get("nfy_1", "12/31/2027"),
        nfy_2=data.get("nfy_2", "12/31/2028"),
        gpc_tickers=data.get("gpc_tickers", []),
        gpc_company_names=data.get("gpc_company_names", {}),
        gt_transactions=gt_objs,
        historical_years=int(data.get("historical_years", 5)),
        projection_years=int(data.get("projection_years", 5)),
    )


# -------------------------------------------------------------
# PAGE LAYOUT
# -------------------------------------------------------------
layout = dbc.Container([
    
    # 1. TOOLBAR: REFRESH BUTTONS
    dbc.Card([
        dbc.CardBody([
            dbc.Row([
                dbc.Col([
                    dbc.ButtonGroup([
                        dbc.Button("🔄 Refresh All Sources", id="btn-refresh-all", color="primary", size="sm", n_clicks=0),
                        dbc.Button("⚡ Update Live Marks (2s)", id="btn-refresh-live-marks", color="warning", size="sm", n_clicks=0),
                    ], className="me-2 mb-2 mb-md-0")
                ], xs=12, md="auto"),
                dbc.Col([
                    dbc.ButtonGroup([
                        dbc.Button("StockAnalysis", id="btn-ref-sa", color="secondary", size="sm", outline=True, n_clicks=0),
                        dbc.Button("MarketScreener", id="btn-ref-ms", color="secondary", size="sm", outline=True, n_clicks=0),
                        dbc.Button("FRED", id="btn-ref-fred", color="secondary", size="sm", outline=True, n_clicks=0),
                        dbc.Button("Beta/Vol (Yahoo)", id="btn-ref-bv", color="secondary", size="sm", outline=True, n_clicks=0),
                    ], className="w-100")
                ], xs=12, md=True),
            ], className="align-items-center")
        ])
    ], color="dark", outline=True, className="mb-3 border-secondary"),

    # 2. VIEW & FILTER CONTROLS
    dbc.Card([
        dbc.CardBody([
            dbc.Row([
                # View Source Selector
                dbc.Col([
                    html.Label("Source View:", className="fw-bold me-2 text-light"),
                    dbc.RadioItems(
                        id="radio-source-view",
                        options=[
                            {"label": "StockAnalysis", "value": "stockanalysis"},
                            {"label": "MarketScreener", "value": "marketscreener"},
                            {"label": "FRED", "value": "fred"},
                            {"label": "Beta/Vol (Yahoo)", "value": "beta_vol"},
                        ],
                        value="stockanalysis",
                        inline=True,
                        className="btn-group-sm",
                        inputClassName="btn-check",
                        labelClassName="btn btn-outline-info size-sm",
                        labelCheckedClassName="active",
                        persistence=True,
                        persistence_type="session"
                    )
                ], xs=12, lg=5, className="mb-2 mb-lg-0"),

                # Statement Selector (Shown for StockAnalysis)
                dbc.Col([
                    html.Div(id="div-statement-controls", children=[
                        html.Label("Statement:", className="fw-bold me-2 text-light"),
                        dbc.RadioItems(
                            id="radio-statement-view",
                            options=[
                                {"label": "IS", "value": "IS"},
                                {"label": "BS", "value": "BS"},
                                {"label": "CFS", "value": "CFS"},
                                {"label": "Ratios", "value": "Ratios"},
                            ],
                            value="IS",
                            inline=True,
                            inputClassName="btn-check",
                            labelClassName="btn btn-outline-secondary size-sm",
                            labelCheckedClassName="active",
                            persistence=True,
                            persistence_type="session"
                        )
                    ])
                ], xs=12, lg=4, className="mb-2 mb-lg-0"),

                # Vol Term Control (Shown for Beta/Vol)
                dbc.Col([
                    html.Div(id="div-vol-term-controls", children=[
                        html.Label("Vol Term (yrs):", className="fw-bold me-2 text-light"),
                        dbc.Input(
                            id="input-vol-term",
                            type="number",
                            min=0.25,
                            max=10.0,
                            step=0.25,
                            value=3.0,
                            size="sm",
                            style={"width": "100px", "display": "inline-block"},
                            persistence=True,
                            persistence_type="session"
                        )
                    ], style={"display": "none"})
                ], xs=12, lg=3),
            ], className="align-items-center")
        ])
    ], color="secondary", outline=True, className="mb-3"),

    # Progress and Status notification bar
    html.Div([
        dbc.Collapse(
            id="progress-collapse",
            is_open=False,
            children=dbc.Card([
                dbc.CardBody([
                    html.Div(id="progress-label", className="fw-bold text-info mb-1", children="Initializing harvest..."),
                    dbc.Progress(id="source-progress-bar", value=0, max=100, striped=True, animated=True, color="info", style={"height": "18px"}),
                ])
            ], color="dark", outline=True, className="mb-3 border-info")
        ),
        html.Div(id="source-status-bar", className="mb-3")
    ]),

    # 3. RESULTS TABLE DISPLAY
    dbc.Card([
        dbc.CardHeader(html.Div(id="table-header-title", className="fw-bold text-light")),
        dbc.CardBody([
            html.Div(id="source-data-table-container")
        ])
    ], color="secondary", outline=True, className="mb-4")
], fluid=True)


# -------------------------------------------------------------
# CALLBACKS
# -------------------------------------------------------------

# Callback 1: Toggle Visibility of Statement (IS/BS/CFS/Ratios) & Vol Term Controls
@callback(
    Output("div-statement-controls", "style"),
    Output("div-vol-term-controls", "style"),
    Input("radio-source-view", "value")
)
def toggle_view_controls(selected_source):
    show_sa = {"display": "block"} if selected_source == "stockanalysis" else {"display": "none"}
    show_bv = {"display": "block"} if selected_source == "beta_vol" else {"display": "none"}
    return show_sa, show_bv


# Callback 2: Execute Source Harvests in the Background with Real-Time Progress Bar
@callback(
    Output("source-results-store", "data"),
    Output("source-status-bar", "children"),
    Input("btn-refresh-all", "n_clicks"),
    Input("btn-refresh-live-marks", "n_clicks"),
    Input("btn-ref-sa", "n_clicks"),
    Input("btn-ref-ms", "n_clicks"),
    Input("btn-ref-fred", "n_clicks"),
    Input("btn-ref-bv", "n_clicks"),
    State("session-store", "data"),
    State("source-results-store", "data"),
    State("input-vol-term", "value"),
    background=True,
    # This disables refresh controls and shows the progress collapse while running
    running=[
        (Output("btn-refresh-all", "disabled"), True, False),
        (Output("btn-refresh-live-marks", "disabled"), True, False),
        (Output("btn-ref-sa", "disabled"), True, False),
        (Output("btn-ref-ms", "disabled"), True, False),
        (Output("btn-ref-fred", "disabled"), True, False),
        (Output("btn-ref-bv", "disabled"), True, False),
        (Output("progress-collapse", "is_open"), True, False),
    ],
    # Maps background progress updates directly into the layout's progress elements
    progress=[
        Output("source-progress-bar", "value"),
        Output("source-progress-bar", "max"),
        Output("progress-label", "children"),
    ],
    prevent_initial_call=True
)
def execute_source_refresh(set_progress, btn_all, btn_live, btn_sa, btn_ms, btn_fred, btn_bv,
                           session_data, existing_results, vol_term):
    triggered_id = ctx.triggered_id
    # Page remount (navigate away + back) re-creates buttons; prevent_initial_call
    # does NOT block that. Only run when the triggering button has a real click count.
    click_map = {
        "btn-refresh-all": btn_all,
        "btn-refresh-live-marks": btn_live,
        "btn-ref-sa": btn_sa,
        "btn-ref-ms": btn_ms,
        "btn-ref-fred": btn_fred,
        "btn-ref-bv": btn_bv,
    }
    if not triggered_id or not click_map.get(triggered_id):
        return dash.no_update, dash.no_update

    if not session_data:
        return dash.no_update, dbc.Alert("No active session memory found.", color="warning")

    project_inputs = dict_to_project_inputs(session_data)
    if not project_inputs.active_public_tickers and triggered_id != "btn-ref-fred":
        return dash.no_update, dbc.Alert("No public tickers configured. Add tickers on the Home page first.", color="warning")

    results_acc = existing_results or {}
    
    # Establish a dynamic sub-progress logger
    def create_progress_logger(step_index, total_steps, base_msg):
        def log_progress(msg):
            # Formulate progress as percentage matching current execution block
            pct = int((step_index / total_steps) * 100)
            set_progress((pct, 100, f"{base_msg} • {msg}"))
        return log_progress

    try:
        if triggered_id == "btn-refresh-all":
            steps = 4
            
            # Step 1: StockAnalysis
            logger = create_progress_logger(0, steps, "1/4: Scraping StockAnalysis financials")
            service = SourceDataService(project_inputs=project_inputs, progress_callback=logger)
            results_acc["stockanalysis"] = service.refresh_stockanalysis()
            
            # Step 2: MarketScreener
            logger = create_progress_logger(1, steps, "2/4: Scraping MarketScreener consensus")
            service = SourceDataService(project_inputs=project_inputs, progress_callback=logger)
            results_acc["marketscreener"] = service.refresh_marketscreener()
            
            # Step 3: FRED
            logger = create_progress_logger(2, steps, "3/4: Fetching macro rates from FRED")
            service = SourceDataService(project_inputs=project_inputs, progress_callback=logger)
            results_acc["fred"] = service.refresh_fred()
            
            # Step 4: Beta/Vol
            logger = create_progress_logger(3, steps, "4/4: Computing historical beta/volatility")
            service = SourceDataService(project_inputs=project_inputs, progress_callback=logger)
            results_acc["beta_vol"] = service.refresh_beta_vol(vol_term=float(vol_term or 3.0))
            
            set_progress((100, 100, "✅ All sources harvested!"))
            status_alert = dbc.Alert("✅ All sources refreshed successfully!", color="success", dismissable=True)

        elif triggered_id == "btn-refresh-live-marks":
            set_progress((10, 100, "Updating live market marks via yfinance..."))
            existing_sa = results_acc.get("stockanalysis", {})
            service = SourceDataService(project_inputs=project_inputs, progress_callback=lambda m: set_progress((40, 100, f"Live marks: {m}")))
            live_out = service.refresh_live_marks(existing_sa_results=existing_sa)
            
            results_acc["stockanalysis"] = live_out.get("stockanalysis", existing_sa)
            results_acc["fred"] = live_out.get("fred", results_acc.get("fred", []))
            
            set_progress((100, 100, "⚡ Marks & FRED rates updated!"))
            status_alert = dbc.Alert("⚡ Live Market Marks & FRED rates updated successfully!", color="success", dismissable=True)

        elif triggered_id == "btn-ref-sa":
            logger = create_progress_logger(0, 1, "Scraping StockAnalysis")
            service = SourceDataService(project_inputs=project_inputs, progress_callback=logger)
            results_acc["stockanalysis"] = service.refresh_stockanalysis()
            status_alert = dbc.Alert("✅ StockAnalysis financials refreshed!", color="success", dismissable=True)

        elif triggered_id == "btn-ref-ms":
            logger = create_progress_logger(0, 1, "Scraping MarketScreener")
            service = SourceDataService(project_inputs=project_inputs, progress_callback=logger)
            results_acc["marketscreener"] = service.refresh_marketscreener()
            status_alert = dbc.Alert("✅ MarketScreener estimates refreshed!", color="success", dismissable=True)

        elif triggered_id == "btn-ref-fred":
            logger = create_progress_logger(0, 1, "Fetching FRED")
            service = SourceDataService(project_inputs=project_inputs, progress_callback=logger)
            results_acc["fred"] = service.refresh_fred()
            status_alert = dbc.Alert("✅ FRED macroeconomic rates refreshed!", color="success", dismissable=True)

        elif triggered_id == "btn-ref-bv":
            logger = create_progress_logger(0, 1, "Computing Beta/Vol")
            service = SourceDataService(project_inputs=project_inputs, progress_callback=logger)
            results_acc["beta_vol"] = service.refresh_beta_vol(vol_term=float(vol_term or 3.0))
            status_alert = dbc.Alert("✅ Beta & Volatility metrics computed!", color="success", dismissable=True)

        else:
            return dash.no_update, dash.no_update

        return results_acc, status_alert

    except Exception as e:
        import traceback
        traceback.print_exc()
        err_alert = dbc.Alert(f"❌ Error during harvest execution: {str(e)}", color="danger", dismissable=True)
        return dash.no_update, err_alert


# Callback 3: Render Active Table Based on Source View & Statement Selection
@callback(
    Output("source-data-table-container", "children"),
    Output("table-header-title", "children"),
    Input("source-results-store", "data"),
    Input("radio-source-view", "value"),
    Input("radio-statement-view", "value"),
    State("session-store", "data")
)
def render_results_table(results_data, source_view, statement_view, session_data):
    if not results_data or not results_data.get(source_view):
        title = f"Data View: {source_view.upper()}"
        placeholder = html.P(f"No data available for {source_view}. Click a refresh button above to harvest data.", className="text-muted p-3")
        return placeholder, title

    raw_results = results_data.get(source_view)

    # Handle StockAnalysis nested structure (IS, BS, CFS, Ratios)
    if source_view == "stockanalysis":
        title = f"StockAnalysis Financials — Statement: {statement_view}"
        rows = raw_results.get(statement_view, [])
        if not rows:
            return html.P(f"No records found for StockAnalysis statement: {statement_view}", className="text-muted p-3"), title

        # Historical years filtering
        hist_years = int((session_data or {}).get("historical_years", 5))
        fy_cols = ["LFY", "LFY-1", "LFY-2", "LFY-3", "LFY-4"]
        allowed_fy_cols = fy_cols[:hist_years]

        all_cols = []
        for r in rows:
            for k in r.keys():
                if k not in all_cols:
                    all_cols.append(k)

        preferred_order = ["Ticker", "Line Item", "TTM"] + allowed_fy_cols + ["Key"]
        cols = [c for c in preferred_order if c in all_cols]
        cols += [c for c in all_cols if c not in preferred_order and c not in fy_cols]

    else:
        title = f"Data View: {source_view.upper()}"
        rows = raw_results if isinstance(raw_results, list) else []
        if not rows:
            return html.P(f"No records found for {source_view}.", className="text-muted p-3"), title

        cols = []
        for r in rows:
            for k in r.keys():
                if k not in cols:
                    cols.append(k)

    # Clean display values (handle NaN / None / NaT)
    cleaned_rows = []
    for r in rows:
        cleaned_r = {}
        for c in cols:
            val = r.get(c, "")
            if val is None or str(val).strip().lower() in ("nan", "none", "nat"):
                cleaned_r[c] = ""
            else:
                cleaned_r[c] = str(val).strip() if isinstance(val, str) else val
        cleaned_rows.append(cleaned_r)

    df = pd.DataFrame(cleaned_rows)

    table = dash_table.DataTable(
        columns=[{"name": c, "id": c} for c in cols],
        data=df.to_dict("records"),
        filter_action="native",
        sort_action="native",
        virtualization=True,
        page_action="none",
        fixed_rows={"headers": True},
        style_table=grid_table_style("two"),
        style_header=grid_header_style(),
        style_cell={
            **grid_cell_style(
                text_align="left",
                padding="4px 8px",
                width="120px",
            ),
            "maxWidth": "220px",
            "whiteSpace": "normal",
        },
        style_data=grid_data_style(),
        style_filter=grid_filter_style(),
    )

    return table, title