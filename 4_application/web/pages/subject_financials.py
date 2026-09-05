"""
web/pages/subject_financials.py

Read-only display of subject company Income Statement and Balance Sheet.
- Public company: data from StockAnalysis via web/lib/subject_metrics.py
- Private company: data from PrivateFinancials via web/lib/subject_metrics.py
- Projections: data from ProjectionData via web/lib/subject_metrics.py
"""

import dash
import dash_bootstrap_components as dbc
from dash import html, dcc, Input, Output, State, callback, dash_table, ctx
import pandas as pd

from Canneberge.app_state import IS_LINES, BS_LINES
from web.lib.session_io import dict_to_project_inputs
from web.lib.subject_metrics import get_subject_metric_value
from web.lib.ui_layout import (
    grid_table_style,
    grid_header_style,
    grid_cell_style,
    grid_line_item_col_conditional,
    grid_style_data_conditional,
)

dash.register_page(__name__, path="/subject-financials", name="Subject Financials")

# -------------------------------------------------------------
# LAYOUT
# -------------------------------------------------------------
layout = dbc.Container([
    dbc.Card([
        dbc.CardBody([
            dbc.Row([
                # Statement Selector: IS vs BS
                dbc.Col([
                    dbc.RadioItems(
                        id="subject-stmt-toggle",
                        options=[
                            {"label": "Income Statement (IS)", "value": "IS"},
                            {"label": "Balance Sheet (BS)", "value": "BS"},
                        ],
                        value="IS",
                        inline=True,
                        inputClassName="btn-check",
                        labelClassName="btn btn-outline-info size-sm",
                        labelCheckedClassName="active",
                        persistence=True,
                        persistence_type="session"
                    )
                ], xs=12, md="auto", className="mb-2 mb-md-0"),

                # Source Status Chip / Info
                dbc.Col([
                    html.Div(id="subject-stmt-source-info", className="text-md-end text-muted fw-bold")
                ], xs=12, md=True, className="d-flex align-items-center justify-content-md-end"),
            ], className="align-items-center")
        ])
    ], color="dark", outline=True, className="mb-3 border-secondary"),

    # Grid Container — table drives height via style_table calc (see callback).
    dbc.Card([
        dbc.CardHeader(html.Div(id="subject-grid-title", className="fw-bold text-light")),
        dbc.CardBody([
            html.Div(id="subject-grid-container")
        ], className="p-2")
    ], color="secondary", outline=True, className="mb-2")
], fluid=True, className="px-2")


# -------------------------------------------------------------
# CALLBACK
# -------------------------------------------------------------
@callback(
    Output("subject-grid-container", "children"),
    Output("subject-grid-title", "children"),
    Output("subject-stmt-source-info", "children"),
    Input("subject-stmt-toggle", "value"),
    Input("session-store", "data"),
    Input("source-results-store", "data"),
)
def render_subject_statement(stmt_type, session_data, source_results):
    inputs = dict_to_project_inputs(session_data or {})
    stmt_type = stmt_type or "IS"

    # 1. Determine Source Info Badge
    if inputs.is_publicly_traded:
        ticker = inputs.subject_ticker.upper() if inputs.subject_ticker else "NO TICKER"
        source_badge = html.Span([
            "Source: ",
            dbc.Badge(f"StockAnalysis ({ticker})", color="info", className="ms-1 fs-6")
        ])
    else:
        source_badge = html.Span([
            "Source: ",
            dbc.Badge("Private Financials Form", color="warning", className="ms-1 fs-6")
        ])

    # 2. Determine Columns (Historical + TTM + Projections)
    # Balance sheet is historical/TTM only; IS gets projections too
    if stmt_type == "IS":
        periods = inputs.historical_period_columns + ["TTM"] + inputs.projection_period_columns
        lines = IS_LINES
        title = f"Subject Financials — Income Statement ({inputs.subject_company_name})"
    else:
        periods = inputs.historical_period_columns + ["TTM"]
        lines = BS_LINES
        title = f"Subject Financials — Balance Sheet ({inputs.subject_company_name})"

    # Periods to check for empty-row filtering (historicals + TTM)
    check_periods = inputs.historical_period_columns + ["TTM"]

    # 3. Assemble Rows
    rows_data = []
    bold_indices = []

    for key, label, is_calc, bold in lines:
        # Resolve all period values for this row
        period_vals = {}
        has_any_val = False
        for p in periods:
            val = get_subject_metric_value(session_data, source_results, key, p)
            period_vals[p] = val
            if p in check_periods and val is not None:
                has_any_val = True

        # Non-bold component rows that are empty across all historical periods are hidden
        if not bold and not has_any_val:
            continue

        row_dict = {"Line Item": label}
        for p in periods:
            v = period_vals.get(p)
            row_dict[p] = f"{v:,.0f}" if v is not None else "-"

        if bold:
            bold_indices.append(len(rows_data))

        rows_data.append(row_dict)

    if not rows_data:
        placeholder = html.P("No statement data available. Refresh Source Data or enter private financials.",
                             className="text-muted p-3")
        return placeholder, title, source_badge

    df = pd.DataFrame(rows_data)
    cols = [{"name": c, "id": c} for c in ["Line Item"] + periods]

    # Conditional styling for bold subtotal / total rows
    table = dash_table.DataTable(
        columns=cols,
        data=df.to_dict("records"),
        style_header=grid_header_style(),
        style_cell=grid_cell_style(),
        style_cell_conditional=grid_line_item_col_conditional("Line Item"),
        style_data_conditional=grid_style_data_conditional(bold_indices, line_item_col="Line Item"),
        fixed_rows={"headers": True},
        virtualization=True,
        page_action="none",
        style_table=grid_table_style("one"),
    )

    return table, title, source_badge