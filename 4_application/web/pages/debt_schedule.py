"""
web/pages/debt_schedule.py

Dash Debt Schedule page.

Uses the shared pure calculation engine:
    Canneberge.Calculations.debt_schedule

State is stored in:
    session-store["debt_page_state"]

The stored shape remains compatible with the desktop DebtSchedulePage:
{
    "rate_basis": "Effective Rate",
    "row_count": 3,
    "rows": [
        {
            "name": "...",
            "issuance": "...",
            "maturity": "...",
            "coupon": "...",
            "effective": "...",
            "principal": "..."
        }
    ]
}

Calculated values are also cached in the state so other web pages can
consume them immediately:
    projected_interest
    interest_expense_by_period
    ending_debt_by_period
    net_borrowing_by_period
"""

from __future__ import annotations

from datetime import date
from typing import Optional

import dash
import dash_bootstrap_components as dbc
from dash import html, Input, Output, State, callback, ctx, ALL, no_update

from Canneberge.Calculations.debt_schedule import (
    parse_date,
    add_years,
    build_period_boundaries,
    compute_debt_schedule,
)
from web.lib.session_io import dict_to_project_inputs


dash.register_page(__name__, path="/debt-schedule", name="Debt Schedule")


COL_W = 85
DEFAULT_ROWS = 3
MAX_ROWS = 20

INPUT_COLS = [
    ("name", "Note", 130),
    ("issuance", "Issued", 90),
    ("maturity", "Matures", 90),
    ("coupon", "Coupon %", 85),
    ("effective", "Effective %", 95),
    ("principal", "Principal", 105),
]

_INPUT_STYLE = {
    "backgroundColor": "#2a2a2a",
    "color": "#f5f5f5",
    "border": "1px solid #666",
    "fontSize": "12px",
    "padding": "3px 5px",
    "width": "100%",
}

_HEADER_STYLE = {
    "backgroundColor": "#2b3e50",
    "color": "white",
    "fontWeight": "bold",
    "padding": "6px 8px",
    "border": "1px solid #555",
    "whiteSpace": "nowrap",
    "textAlign": "center",
}

_LABEL_STYLE = {
    "backgroundColor": "#1e1e1e",
    "color": "#eee",
    "fontWeight": "bold",
    "padding": "6px 8px",
    "border": "1px solid #333",
    "whiteSpace": "nowrap",
}

_CELL_STYLE = {
    "backgroundColor": "#1e1e1e",
    "color": "#ddd",
    "padding": "5px 8px",
    "border": "1px solid #333",
    "whiteSpace": "nowrap",
    "textAlign": "right",
}

_TOTAL_LABEL_STYLE = {
    **_LABEL_STYLE,
    "textAlign": "left",
}

_TOTAL_CELL_STYLE = {
    **_CELL_STYLE,
    "fontWeight": "bold",
}


# -------------------------------------------------------------
# Helpers
# -------------------------------------------------------------

def _parse_number(value) -> Optional[float]:
    if value is None:
        return None

    text = str(value).strip().replace(",", "").replace("$", "")
    if not text:
        return None

    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def _parse_pct(value) -> Optional[float]:
    """
    Match the desktop behavior: 5 or 5% becomes 0.05.
    """
    if value is None:
        return None

    text = str(value).strip().replace(",", "").replace("%", "")
    if not text:
        return None

    try:
        return float(text) / 100.0
    except (TypeError, ValueError):
        return None


def _fmt_value(value) -> str:
    if value is None:
        return "-"
    return f"{value:,.2f}"


def _blank_row() -> dict:
    return {
        "name": "",
        "issuance": "",
        "maturity": "",
        "coupon": "",
        "effective": "",
        "principal": "",
    }


def _normalise_row(row: dict | None) -> dict:
    row = row or {}
    return {
        "name": "" if row.get("name") is None else str(row.get("name")),
        "issuance": "" if row.get("issuance") is None else str(row.get("issuance")),
        "maturity": "" if row.get("maturity") is None else str(row.get("maturity")),
        "coupon": "" if row.get("coupon") is None else str(row.get("coupon")),
        "effective": "" if row.get("effective") is None else str(row.get("effective")),
        "principal": "" if row.get("principal") is None else str(row.get("principal")),
    }


def _state_from_session(session_data: dict) -> dict:
    raw = (session_data or {}).get("debt_page_state", {}) or {}

    try:
        row_count = int(raw.get("row_count", DEFAULT_ROWS))
    except (TypeError, ValueError):
        row_count = DEFAULT_ROWS

    row_count = max(1, min(MAX_ROWS, row_count))

    saved_rows = [
        _normalise_row(row)
        for row in (raw.get("rows", []) or [])
    ]

    while len(saved_rows) < row_count:
        saved_rows.append(_blank_row())

    saved_rows = saved_rows[:row_count]

    return {
        "rate_basis": raw.get("rate_basis", "Effective Rate"),
        "row_count": row_count,
        "rows": saved_rows,
    }


def _period_boundaries(session_data: dict):
    inputs = dict_to_project_inputs(session_data or {})

    lfy_end = parse_date(inputs.last_fiscal_year)
    nfy_end = parse_date(inputs.next_fiscal_year)

    if lfy_end is None or nfy_end is None:
        return []

    try:
        projection_years = int(inputs.projection_years or 1)
    except (TypeError, ValueError):
        projection_years = 1

    projection_years = max(1, min(20, projection_years))

    return build_period_boundaries(
        lfy_end=lfy_end,
        nfy_end=nfy_end,
        nfy1_end=parse_date(inputs.nfy_1),
        nfy2_end=parse_date(inputs.nfy_2),
        projection_years=projection_years,
        hist_years=1,
    )


def _engine_tranches(rows: list[dict]) -> list[dict]:
    tranches = []

    for row in rows:
        tranches.append({
            "name": row.get("name", "").strip(),
            "issuance": parse_date(row.get("issuance")),
            "maturity": parse_date(row.get("maturity")),
            "coupon_rate": _parse_pct(row.get("coupon")),
            "effective_rate": _parse_pct(row.get("effective")),
            "principal": _parse_number(row.get("principal")),
        })

    return tranches


def _compute_results(session_data: dict, rows: list[dict], rate_basis: str):
    boundaries = _period_boundaries(session_data)

    if not boundaries:
        return boundaries, {
            "interest_by_tranche": [{} for _ in rows],
            "interest_expense_by_period": {},
            "ending_debt_by_period": {},
            "net_borrowing_by_period": {},
        }

    rate_key = (
        "effective_rate"
        if rate_basis == "Effective Rate"
        else "coupon_rate"
    )

    results = compute_debt_schedule(
        _engine_tranches(rows),
        boundaries,
        rate_key=rate_key,
    )

    return boundaries, results


def _harvest_rows(cell_ids, cell_values, fallback_rows: list[dict]) -> list[dict]:
    """
    Reconstruct all visible tranche rows from the current Dash inputs.

    IDs carry the slot and field, so this does not depend on pattern-matching
    order.
    """
    rows = [_normalise_row(row) for row in fallback_rows]

    max_slot = -1
    for cell_id in cell_ids or []:
        if isinstance(cell_id, dict):
            try:
                max_slot = max(max_slot, int(cell_id.get("slot", -1)))
            except (TypeError, ValueError):
                pass

    while len(rows) <= max_slot:
        rows.append(_blank_row())

    for cell_id, raw_value in zip(cell_ids or [], cell_values or []):
        if not isinstance(cell_id, dict):
            continue

        field = cell_id.get("field")
        slot = cell_id.get("slot")

        if field not in {key for key, _label, _width in INPUT_COLS}:
            continue

        try:
            slot = int(slot)
        except (TypeError, ValueError):
            continue

        while len(rows) <= slot:
            rows.append(_blank_row())

        rows[slot][field] = "" if raw_value is None else str(raw_value)

    return rows


def _state_with_results(
    session_data: dict,
    rows: list[dict],
    rate_basis: str,
) -> dict:
    boundaries, results = _compute_results(
        session_data,
        rows,
        rate_basis,
    )

    interest_by_period = results.get("interest_expense_by_period", {}) or {}
    ending_debt = results.get("ending_debt_by_period", {}) or {}
    net_borrowing = results.get("net_borrowing_by_period", {}) or {}

    projected_interest = {
        period: value
        for period, value in interest_by_period.items()
        if period.startswith("NFY")
    }

    return {
        "rate_basis": rate_basis,
        "row_count": len(rows),
        "rows": rows,

        # Native calculation-engine result
        "interest_expense_by_period": interest_by_period,
        "ending_debt_by_period": ending_debt,
        "net_borrowing_by_period": net_borrowing,

        # Compatibility key already consumed by projection_modal.py
        "projected_interest": projected_interest,
    }


# -------------------------------------------------------------
# Layout
# -------------------------------------------------------------

layout = dbc.Container(
    [
        dbc.Card(
            [
                dbc.CardHeader(
                    html.H5("Debt Schedule", className="text-light mb-0")
                ),
                dbc.CardBody(
                    [
                        dbc.Row(
                            [
                                dbc.Col(
                                    [
                                        dbc.Label("Rate Basis"),
                                        dbc.Select(
                                            id="debt-rate-basis",
                                            options=[
                                                {
                                                    "label": "Effective Rate",
                                                    "value": "Effective Rate",
                                                },
                                                {
                                                    "label": "Coupon Rate",
                                                    "value": "Coupon Rate",
                                                },
                                            ],
                                            value="Effective Rate",
                                        ),
                                    ],
                                    xs=12,
                                    md=3,
                                ),
                                dbc.Col(
                                    html.Div(
                                        id="debt-status",
                                        className="text-info mt-4",
                                    ),
                                    xs=12,
                                    md=9,
                                ),
                            ],
                            className="align-items-start mb-3",
                        ),
                        html.Div(
                            [
                                dbc.Button(
                                    "+",
                                    id="debt-add-row",
                                    color="secondary",
                                    size="sm",
                                    className="me-1",
                                    n_clicks=0,
                                ),
                                dbc.Button(
                                    "−",
                                    id="debt-remove-row",
                                    color="secondary",
                                    size="sm",
                                    className="me-3",
                                    n_clicks=0,
                                ),
                                html.Span(
                                    "Add/remove debt tranches. Use ReFi to create a "
                                    "five-year refinancing row from an existing note.",
                                    className="text-muted small",
                                ),
                            ],
                            className="mb-2",
                        ),
                        html.Div(
                            id="debt-grid-container",
                            style={
                                "overflowX": "auto",
                                "border": "1px solid #444",
                                "borderRadius": "4px",
                            },
                        ),
                    ]
                ),
            ],
            color="secondary",
            outline=True,
            className="mb-3",
        )
    ],
    fluid=True,
    className="px-2",
)


# -------------------------------------------------------------
# Hydrate rate basis when navigating to the page or loading a session
# -------------------------------------------------------------

@callback(
    Output("debt-rate-basis", "value"),
    Input("_pages_location", "pathname"),
    Input("session-load-timestamp", "data"),
    State("session-store", "data"),
)
def hydrate_debt_rate_basis(pathname, _load_timestamp, session_data):
    if pathname != "/debt-schedule":
        return no_update

    state = _state_from_session(session_data or {})
    return state["rate_basis"]


# -------------------------------------------------------------
# Render table
# -------------------------------------------------------------

@callback(
    Output("debt-grid-container", "children"),
    Output("debt-status", "children"),
    Input("_pages_location", "pathname"),
    Input("session-store", "data"),
    Input("session-load-timestamp", "data"),
    Input("debt-rate-basis", "value"),
)
def render_debt_schedule(pathname, session_data, _load_timestamp, rate_basis):
    if pathname != "/debt-schedule":
        return no_update, no_update

    session_data = session_data or {}
    state = _state_from_session(session_data)

    rate_basis = rate_basis or state["rate_basis"]
    rows = state["rows"]

    boundaries, results = _compute_results(
        session_data,
        rows,
        rate_basis,
    )

    periods = [label for label, _prior, _end in boundaries]
    interest_rows = results.get("interest_by_tranche", []) or []

    header_cells = [
        html.Th(label, style={**_HEADER_STYLE, "minWidth": f"{width}px"})
        for _key, label, width in INPUT_COLS
    ]

    header_cells.extend(
        html.Th(
            period,
            style={**_HEADER_STYLE, "minWidth": f"{COL_W}px"},
        )
        for period in periods
    )

    header_cells.append(
        html.Th(
            "ReFi",
            style={**_HEADER_STYLE, "minWidth": "65px"},
        )
    )

    body_rows = []

    for slot, row in enumerate(rows):
        cells = []

        for field, _label, width in INPUT_COLS:
            cells.append(
                html.Td(
                    dbc.Input(
                        id={
                            "type": "debt-cell",
                            "slot": slot,
                            "field": field,
                        },
                        type="text",
                        value=row.get(field, ""),
                        debounce=True,
                        size="sm",
                        style={**_INPUT_STYLE, "minWidth": f"{width}px"},
                    ),
                    style={
                        "padding": "2px",
                        "border": "1px solid #333",
                        "backgroundColor": "#1e1e1e",
                        "minWidth": f"{width}px",
                    },
                )
            )

        tranche_interest = (
            interest_rows[slot]
            if slot < len(interest_rows)
            else {}
        )

        for period in periods:
            value = tranche_interest.get(period)
            cells.append(
                html.Td(
                    _fmt_value(value),
                    style={**_CELL_STYLE, "minWidth": f"{COL_W}px"},
                )
            )

        cells.append(
            html.Td(
                dbc.Button(
                    "↻ ReFi",
                    id={"type": "debt-refi", "slot": slot},
                    color="secondary",
                    size="sm",
                    n_clicks=0,
                    style={"fontSize": "11px", "whiteSpace": "nowrap"},
                ),
                style={
                    **_CELL_STYLE,
                    "minWidth": "65px",
                    "textAlign": "center",
                },
            )
        )

        body_rows.append(html.Tr(cells))

    total_rows = [
        (
            "Total Interest Expense",
            results.get("interest_expense_by_period", {}) or {},
        ),
        (
            "Ending Debt Balance",
            results.get("ending_debt_by_period", {}) or {},
        ),
        (
            "Net Borrowing",
            results.get("net_borrowing_by_period", {}) or {},
        ),
    ]

    for label, values in total_rows:
        cells = [
            html.Td(
                label,
                colSpan=len(INPUT_COLS),
                style=_TOTAL_LABEL_STYLE,
            )
        ]

        for period in periods:
            cells.append(
                html.Td(
                    _fmt_value(values.get(period)),
                    style={**_TOTAL_CELL_STYLE, "minWidth": f"{COL_W}px"},
                )
            )

        cells.append(
            html.Td("", style={**_TOTAL_CELL_STYLE, "minWidth": "65px"})
        )
        body_rows.append(html.Tr(cells))

    table = html.Table(
        [
            html.Thead(html.Tr(header_cells)),
            html.Tbody(body_rows),
        ],
        className="table table-sm table-dark mb-0",
        style={
            "width": "max-content",
            "minWidth": "100%",
            "borderCollapse": "separate",
            "borderSpacing": 0,
        },
    )

    inputs = dict_to_project_inputs(session_data)
    if not boundaries:
        status = (
            "Enter valid Last Fiscal Year and Next FY End dates on the Home page "
            "to generate debt schedule periods."
        )
    else:
        status = (
            f"{inputs.subject_company_name} · {rate_basis} · "
            f"{len(periods)} periods · changes save to the live session"
        )

    return table, status


# -------------------------------------------------------------
# Persist rows and recalculate whenever an input/control changes
# -------------------------------------------------------------

@callback(
    Output("session-store", "data", allow_duplicate=True),
    Input("debt-rate-basis", "value"),
    Input(
        {"type": "debt-cell", "slot": ALL, "field": ALL},
        "value",
    ),
    State(
        {"type": "debt-cell", "slot": ALL, "field": ALL},
        "id",
    ),
    Input("debt-add-row", "n_clicks"),
    Input("debt-remove-row", "n_clicks"),
    Input({"type": "debt-refi", "slot": ALL}, "n_clicks"),
    State("session-store", "data"),
    prevent_initial_call=True,
)
def persist_debt_schedule(
    rate_basis,
    cell_values,
    cell_ids,
    add_clicks,
    remove_clicks,
    refi_clicks,
    session_data,
):
    trigger = ctx.triggered_id

    if not trigger:
        return no_update

    session_data = dict(session_data or {})
    old_state = _state_from_session(session_data)

    rows = _harvest_rows(
        cell_ids,
        cell_values,
        old_state["rows"],
    )

    if isinstance(trigger, dict) and trigger.get("type") == "debt-refi":
        try:
            slot = int(trigger.get("slot"))
        except (TypeError, ValueError):
            return no_update

        if len(rows) >= MAX_ROWS or slot >= len(rows):
            return no_update

        source = rows[slot]
        maturity = parse_date(source.get("maturity"))

        refi_row = {
            "name": f"ReFi - {source.get('name', '')}".strip(),
            "issuance": source.get("maturity", ""),
            "maturity": (
                add_years(maturity, 5).strftime("%m/%d/%Y")
                if maturity
                else ""
            ),
            "coupon": "",
            "effective": "",
            "principal": source.get("principal", ""),
        }

        rows.append(refi_row)

    elif trigger == "debt-add-row":
        if len(rows) >= MAX_ROWS:
            return no_update
        rows.append(_blank_row())

    elif trigger == "debt-remove-row":
        if len(rows) <= 1:
            return no_update
        rows = rows[:-1]

    rate_basis = rate_basis or old_state["rate_basis"]

    new_state = _state_with_results(
        session_data,
        rows,
        rate_basis,
    )

    session_data["debt_page_state"] = new_state
    return session_data