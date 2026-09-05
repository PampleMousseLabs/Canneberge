"""
web/components/projection_modal.py

Projection Module modal.
- Editable drivers recalculate when you leave a cell (debounce=True ≈ Enter/Tab out).
- Save writes projection_page_state; modal stays open.
- Cancel/X closes.
- Hist/Proj spinboxes update session + Home page spins + rebuild columns.
"""

from __future__ import annotations

import math
import traceback
from typing import Optional, Dict, List

import dash_bootstrap_components as dbc
from dash import html, dcc, Input, Output, State, callback, ctx, ALL, no_update

from Canneberge.app_state import ProjectionData
from Canneberge.Transforms.sa_key import get_sa_labels
from Canneberge.utils.sa_utils import build_lookup, to_float
from Canneberge.Calculations.projection_resolve import resolve_projection_dollars
from web.lib.session_io import dict_to_project_inputs, _clean_float
from web.lib.subject_metrics import get_historical_line_values, dict_to_projection_data

MS_COVERED_PERIODS = {"NFY", "NFY+1", "NFY+2"}

_INPUT_STYLE = {
    "backgroundColor": "#3d2f5c",
    "color": "#f5f5f5",
    "border": "1px solid #7c68af",
    "textAlign": "right",
    "fontSize": "12px",
    "minWidth": "88px",
    "padding": "2px 4px",
}
_HDR = {
    "position": "sticky", "top": 0, "zIndex": 2,
    "backgroundColor": "#2b3e50", "color": "white", "fontWeight": "bold",
    "padding": "6px 8px", "textAlign": "center", "minWidth": "90px",
    "border": "1px solid #555",
}
_HDR_LABEL = {**_HDR, "left": 0, "zIndex": 3, "minWidth": "240px", "textAlign": "left"}
_LABEL = {
    "position": "sticky", "left": 0, "zIndex": 1,
    "backgroundColor": "#1e1e1e", "color": "#eee",
    "padding": "4px 10px", "whiteSpace": "nowrap", "fontSize": "12px",
    "border": "1px solid #333", "minWidth": "240px",
}
_LABEL_BOLD = {**_LABEL, "fontWeight": "bold"}
_CELL_LOCKED = {
    "padding": "4px 8px", "textAlign": "right", "fontSize": "12px",
    "border": "1px solid #333", "backgroundColor": "#1e1e1e",
    "color": "#aaa", "fontStyle": "italic", "minWidth": "90px",
}

layout = html.Div([
    dcc.Store(id="proj-draft-store", storage_type="memory"),
    dcc.Store(id="proj-suppress-recalc", data=False, storage_type="memory"),
    dbc.Modal(
        [
            dbc.ModalHeader(dbc.ModalTitle("Projection Module"), close_button=True),
            dbc.ModalBody([
                dbc.Row([
                    dbc.Col(html.Div(id="proj-modal-status", className="fw-bold text-info mb-2"), width=True),
                    dbc.Col([
                        dbc.InputGroup([
                            dbc.InputGroupText("Hist Yrs"),
                            dbc.Input(id="proj-spin-hist", type="number", min=0, max=5, size="sm",
                                      style={"width": "65px"}, debounce=True),
                            dbc.InputGroupText("Proj Yrs"),
                            dbc.Input(id="proj-spin-proj", type="number", min=1, max=20, size="sm",
                                      style={"width": "65px"}, debounce=True),
                        ], size="sm"),
                    ], width="auto"),
                ], className="align-items-center mb-2"),
                html.Div(
                    id="proj-modal-grid-container",
                    style={
                        "maxHeight": "65vh",
                        "overflowY": "auto",
                        "overflowX": "auto",
                        "border": "1px solid #444",
                        "borderRadius": "4px",
                        # Without this, Bootstrap's .modal-content flex
                        # layout lets this element (and everything above
                        # it) grow to fit the wide table instead of
                        # containing it — the whole modal balloons past
                        # the viewport rather than scrolling internally.
                        "minWidth": 0,
                        "width": "100%",
                    },
                ),
                html.Small(
                    "Leave a purple cell (Tab/Enter/click away) to recalculate. "
                    "Save writes the session for Subject Financials / DCF. Cancel/X closes.",
                    className="text-muted d-block mt-2",
                ),
            ]),
            dbc.ModalFooter([
                dbc.Button("Cancel", id="btn-proj-cancel", color="secondary", n_clicks=0),
                dbc.Button("Save Projections", id="btn-proj-save", color="primary", n_clicks=0),
            ]),
        ],
        id="modal-projection",
        is_open=False,
        size="xl",
        backdrop=True,
        keyboard=True,
        scrollable=True,
    ),
])


def _fmt_dollars(v: Optional[float]) -> str:
    if v is None:
        return "-"
    try:
        if math.isnan(v) or math.isinf(v):
            return "-"
    except TypeError:
        return "-"
    return f"{v:,.0f}"


def _fmt_pct(v: Optional[float]) -> str:
    if v is None:
        return "-"
    try:
        if math.isnan(v) or math.isinf(v):
            return "-"
    except TypeError:
        return "-"
    return f"{v * 100:.1f}%"


def _parse_pct(text) -> Optional[float]:
    if text is None or str(text).strip() == "":
        return None
    raw = str(text).strip()
    has_pct = "%" in raw
    cleaned = raw.replace("%", "").replace(",", "").strip()
    try:
        f = float(cleaned)
        if math.isnan(f) or math.isinf(f):
            return None
        if has_pct or abs(f) >= 1.0:
            return f / 100.0
        return f
    except (ValueError, TypeError):
        return None


def _div(a, b):
    if a is None or b is None or b == 0:
        return None
    return a / b


def _mul(a, b):
    if a is None or b is None:
        return None
    return a * b


def _hist_ebitda_adjusted(session_data, source_results):
    """Return (source_ebit_like, adjusted EBITDA) historical values.

    Important: our current StockAnalysis/Subject Financials "ebitda" line is
    effectively EBIT / operating income, not true EBITDA. To make historicals
    comparable to MarketScreener forward EBITDA estimates, the adjusted EBITDA
    anchor must add back D&A, other amortization, and SBC.

        Adjusted EBITDA = EBIT + D&A + Other Amortization + SBC

    Subject Financials can still show the as-reported/source line separately;
    this helper is only for the Projection Module's comparable projection base.
    """
    source_ebit_like = get_historical_line_values(session_data, source_results, "ebitda", "IS")

    da = get_historical_line_values(session_data, source_results, "d&a_for_ebitda", "IS")
    if not any(v is not None for v in da.values()):
        da = get_historical_line_values(session_data, source_results, "depreciation", "IS")
    if not any(v is not None for v in da.values()):
        da = get_historical_line_values(session_data, source_results, "depreciation_amortization", "IS")

    other_amort = get_historical_line_values(session_data, source_results, "other_amortization", "IS")
    sbc = get_historical_line_values(session_data, source_results, "stock_based_compensation", "IS")

    adj = {}
    for p, base in source_ebit_like.items():
        if base is None:
            adj[p] = None
        else:
            adj[p] = (
                base
                + (da.get(p) or 0.0)
                + (other_amort.get(p) or 0.0)
                + (sbc.get(p) or 0.0)
            )

    return source_ebit_like, adj


def _tax_rate(session_data) -> Optional[float]:
    inputs = dict_to_project_inputs(session_data or {})
    r = getattr(inputs, "subject_tax_rate", None)
    try:
        if r is None:
            return None
        r = float(r)
        if math.isnan(r) or math.isinf(r):
            return None
        # stored as 0.21 or 21
        return r / 100.0 if r > 1.0 else r
    except (TypeError, ValueError):
        return None


def _growth(cur, prior):
    r = _div(cur, prior)
    return None if r is None else r - 1.0


def _load_ms_via_sakey(source_results: dict, ticker: str) -> dict:
    out = {"revenue": {}, "ebitda": {}, "net_income": {}}
    ms_rows = (source_results or {}).get("marketscreener", []) or []
    if not ms_rows or not ticker:
        return out
    ms_lookup = build_lookup(ms_rows, ticker)
    for key in ("revenue", "ebitda", "net_income"):
        for label in get_sa_labels(key):
            row = ms_lookup.get(label, {})
            if not row:
                continue
            for period in MS_COVERED_PERIODS:
                v = to_float(row.get(period))
                if v is not None:
                    out[key][period] = v
            break
    return out


def _pd_to_blob(pd: ProjectionData) -> dict:
    other = getattr(pd, "other_adj", None) or {}
    return {
        "revenue": dict(pd.revenue),
        "revenue_growth": dict(pd.revenue_growth),
        "gross_profit": dict(pd.gross_profit),
        "gp_improvement": dict(pd.gp_improvement),
        "ebitda": dict(pd.ebitda),
        "ebitda_improvement": dict(pd.ebitda_improvement),
        "da": dict(pd.da),
        "da_pct": dict(pd.da_pct),
        "sbc": dict(pd.sbc),
        "sbc_pct": dict(pd.sbc_pct),
        "other_amort": dict(pd.other_amort),
        "other_amort_pct": dict(pd.other_amort_pct),
        "other_adj": dict(other),
        "net_income": dict(pd.net_income),
        "net_income_margin": dict(pd.net_income_margin),
        "capex": dict(pd.capex),
        "capex_pct": dict(pd.capex_pct),
        "last_edited_revenue": dict(pd.last_edited_revenue or {}),
        "last_edited_ni": dict(pd.last_edited_ni or {}),
    }


def _blob_to_pd(blob: dict) -> ProjectionData:
    if not blob:
        return ProjectionData()
    # reuse subject_metrics loader shape
    fake = {"projection_page_state": blob}
    pd = dict_to_projection_data(fake)
    if not hasattr(pd, "other_adj") or pd.other_adj is None:
        pd.other_adj = {}
    raw_oa = (blob or {}).get("other_adj") or {}
    for k, v in raw_oa.items():
        pd.other_adj[k] = _clean_float(v) if not isinstance(v, (int, float)) else v
    return pd


def _harvest(pd: ProjectionData, cell_ids, cell_values, triggered_id=None) -> ProjectionData:
    """Load all visible cell values into pd.

    CRITICAL: last_edited_revenue / last_edited_ni are set ONLY from the
    input that actually triggered this callback (ctx.triggered_id).
    Writing last_edited for every cell makes whichever field appears
    last in the ALL list win — e.g. stale Growth % overwrites a newly
    typed lower Revenue. That is the 'can't type smaller revenue' bug.
    """
    if not hasattr(pd, "other_adj") or pd.other_adj is None:
        pd.other_adj = {}

    for cell_id, raw_val in zip(cell_ids or [], cell_values or []):
        if not cell_id:
            continue
        field, period = cell_id.get("field"), cell_id.get("period")
        if not field or not period:
            continue

        # Explicit empty → clear (but "0" / "0%" are real values, not empty)
        if raw_val is None or str(raw_val).strip() == "":
            if field == "other_adj":
                pd.other_adj.pop(period, None)
            else:
                bucket = getattr(pd, field, None)
                if isinstance(bucket, dict):
                    bucket[period] = None
            continue

        if field in (
            "gp_improvement", "ebitda_improvement", "da_pct",
            "other_amort_pct", "sbc_pct", "capex_pct", "revenue_growth",
            "net_income_margin",
        ):
            val = _parse_pct(raw_val)
        else:
            val = _clean_float(raw_val)

        # Allow zero: only skip failed parses
        if val is None:
            continue

        if field == "other_adj":
            pd.other_adj[period] = val
        else:
            bucket = getattr(pd, field, None)
            if isinstance(bucket, dict):
                bucket[period] = val

    # Last-edit wins: only the cell the user just left
    if isinstance(triggered_id, dict) and triggered_id.get("type") == "proj-input":
        tf = triggered_id.get("field")
        tp = triggered_id.get("period")
        if tf == "revenue" and tp:
            pd.last_edited_revenue[tp] = "revenue"
        elif tf == "revenue_growth" and tp:
            pd.last_edited_revenue[tp] = "growth"
        elif tf == "net_income" and tp:
            pd.last_edited_ni[tp] = "net_income"
        elif tf == "net_income_margin" and tp:
            pd.last_edited_ni[tp] = "margin"

    return pd


def _resolve(session_data, source_results, pd: ProjectionData) -> dict:
    inputs = dict_to_project_inputs(session_data)
    hist = list(inputs.historical_period_columns) + ["TTM"]
    proj = list(inputs.projection_period_columns)
    is_public = inputs.is_publicly_traded
    h_rev = get_historical_line_values(session_data, source_results, "revenue", "IS")
    h_gp = get_historical_line_values(session_data, source_results, "gross_profit", "IS")
    _h_ebitda_rep, h_ebitda = _hist_ebitda_adjusted(session_data, source_results)
    ms = _load_ms_via_sakey(source_results, inputs.subject_ticker) if is_public else {
        "revenue": {}, "ebitda": {}, "net_income": {}
    }
    return resolve_projection_dollars(
        historical_periods=hist,
        projection_periods=proj,
        hist_revenue=h_rev,
        hist_gross_profit=h_gp,
        hist_ebitda=h_ebitda,
        is_public=is_public,
        ms_revenue=ms["revenue"],
        ms_ebitda=ms["ebitda"],
        projection_data=pd,
    )


def _apply_resolved(pd: ProjectionData, resolved: dict, proj_periods: list) -> None:
    if not hasattr(pd, "other_adj") or pd.other_adj is None:
        pd.other_adj = {}
    for p in proj_periods:
        r = resolved.get(p, {}) or {}
        for k in ("revenue", "gross_profit", "ebitda", "da", "capex",
                  "sbc", "other_amort", "net_income"):
            if r.get(k) is not None:
                bucket = getattr(pd, k, None)
                if isinstance(bucket, dict):
                    bucket[p] = r[k]
        if r.get("other_adj") is not None:
            pd.other_adj[p] = r["other_adj"]


def _sync_growth_display(pd, session_data, source_results, proj_periods):
    """If last edit was Revenue $, recompute Growth %. If last edit was Growth %, leave growth alone."""
    h_rev = get_historical_line_values(session_data, source_results, "revenue", "IS")
    for i, p in enumerate(proj_periods):
        rev = pd.revenue.get(p)
        prior = h_rev.get("TTM") if i == 0 else pd.revenue.get(proj_periods[i - 1])
        g = _growth(rev, prior)
        last = pd.last_edited_revenue.get(p)
        if last == "growth":
            # User owns growth (including 0%). Do not overwrite.
            continue
        # last == "revenue" or unset: growth is derived from revenue chain
        if g is not None:
            pd.revenue_growth[p] = g
        elif last == "revenue":
            # Explicit zero or missing prior → store None/0 appropriately
            pd.revenue_growth[p] = g


def _locked(text):
    return html.Td(text, style=_CELL_LOCKED)


def _inp(field, period, display):
    return html.Td(
        dbc.Input(
            id={"type": "proj-input", "field": field, "period": period},
            type="text",
            value=display,
            debounce=True,  # fires after Tab/Enter/blur — triggers live recalc
            style=_INPUT_STYLE,
            size="sm",
            className="border-0",
        ),
        style={"padding": "2px", "border": "1px solid #333", "backgroundColor": "#1e1e1e"},
    )


def build_table(session_data: dict, source_results: dict, pd: ProjectionData):
    inputs = dict_to_project_inputs(session_data)
    if not hasattr(pd, "other_adj") or pd.other_adj is None:
        pd.other_adj = {}

    hist_periods = list(inputs.historical_period_columns) + ["TTM"]
    proj_periods = list(inputs.projection_period_columns)
    all_periods = hist_periods + proj_periods
    is_public = inputs.is_publicly_traded

    h_rev = get_historical_line_values(session_data, source_results, "revenue", "IS")
    h_gp = get_historical_line_values(session_data, source_results, "gross_profit", "IS")
    h_ebitda_rep, h_ebitda = _hist_ebitda_adjusted(session_data, source_results)
    h_da = get_historical_line_values(session_data, source_results, "d&a_for_ebitda", "IS")
    if not any(v is not None for v in h_da.values()):
        h_da = get_historical_line_values(session_data, source_results, "depreciation", "IS")
    if not any(v is not None for v in h_da.values()):
        h_da = get_historical_line_values(session_data, source_results, "depreciation_amortization", "IS")
    h_sbc = get_historical_line_values(session_data, source_results, "stock_based_compensation", "IS")
    h_oa = get_historical_line_values(session_data, source_results, "other_amortization", "IS")
    h_ni = get_historical_line_values(session_data, source_results, "net_income", "IS")
    h_capex = get_historical_line_values(session_data, source_results, "capex", "IS")
    tax_rate = _tax_rate(session_data)
    ms = _load_ms_via_sakey(source_results, inputs.subject_ticker) if is_public else {
        "revenue": {}, "ebitda": {}, "net_income": {}
    }

    resolved = _resolve(session_data, source_results, pd)
    _apply_resolved(pd, resolved, proj_periods)
    _sync_growth_display(pd, session_data, source_results, proj_periods)

    disp_rev = {p: h_rev.get(p) for p in hist_periods}
    disp_growth = {}
    for i, p in enumerate(hist_periods):
        disp_growth[p] = None if (i == 0 or p == "TTM") else _growth(h_rev.get(p), h_rev.get(hist_periods[i - 1]))

    for i, p in enumerate(proj_periods):
        r = resolved.get(p, {}) or {}
        disp_rev[p] = r.get("revenue")
        prior = h_rev.get("TTM") if i == 0 else (resolved.get(proj_periods[i - 1], {}) or {}).get("revenue")
        disp_growth[p] = _growth(disp_rev.get(p), prior)

    disp_gp = {p: h_gp.get(p) for p in hist_periods}
    disp_ebitda = {p: h_ebitda.get(p) for p in hist_periods}
    disp_da = {p: h_da.get(p) for p in hist_periods}
    disp_capex = {p: h_capex.get(p) for p in hist_periods}
    disp_sbc = {p: h_sbc.get(p) for p in hist_periods}
    disp_oa = {p: h_oa.get(p) for p in hist_periods}
    disp_ni = {p: h_ni.get(p) for p in hist_periods}
    disp_other_adj = {p: None for p in hist_periods}
    disp_taxes = {}

    for p in proj_periods:
        r = resolved.get(p, {}) or {}
        disp_gp[p] = r.get("gross_profit")
        disp_ebitda[p] = r.get("ebitda")
        disp_da[p] = r.get("da")
        disp_capex[p] = r.get("capex")
        rev_p = r.get("revenue")
        disp_sbc[p] = _mul(rev_p, pd.sbc_pct.get(p))
        disp_oa[p] = _mul(rev_p, pd.other_amort_pct.get(p))

        ebitda_p = disp_ebitda.get(p)
        da_p = disp_da.get(p) or 0.0
        oa_p = disp_oa.get(p) or 0.0
        sbc_p = disp_sbc.get(p) or 0.0
        ebit = (ebitda_p - da_p - oa_p - sbc_p) if ebitda_p is not None else None

        # +Other Adjustments is PRE-tax (net interest, other non-op,
        # one-timers). Sitting above the Taxes row, it must be solved
        # pre-tax or the column doesn't foot top-to-bottom — and the
        # residual the user reads off NFY+2 to hand-enter in NFY+3
        # wouldn't be an interpretable number.
        if is_public and p in MS_COVERED_PERIODS:
            analyst_ni = ms.get("net_income", {}).get(p)
            adj = None
            if ebit is not None and analyst_ni is not None \
                    and tax_rate is not None and tax_rate != 1.0:
                adj = (analyst_ni / (1.0 - tax_rate)) - ebit
            disp_other_adj[p] = adj
            if adj is not None:
                pd.other_adj[p] = adj
            pretax = (ebit + adj) if (ebit is not None and adj is not None) else None
            disp_taxes[p] = _mul(pretax, tax_rate)
            disp_ni[p] = analyst_ni
        else:
            adj = pd.other_adj.get(p)
            disp_other_adj[p] = adj
            pretax = (ebit + (adj or 0.0)) if ebit is not None else None
            disp_taxes[p] = _mul(pretax, tax_rate)
            disp_ni[p] = _mul(pretax, (1.0 - tax_rate) if tax_rate is not None else None)

        if disp_sbc[p] is not None:
            pd.sbc[p] = disp_sbc[p]
        if disp_oa[p] is not None:
            pd.other_amort[p] = disp_oa[p]
        if disp_ni[p] is not None:
            pd.net_income[p] = disp_ni[p]

    disp_ebitda_rep = {p: h_ebitda_rep.get(p) for p in hist_periods}
    for p in proj_periods:
        disp_ebitda_rep[p] = None
    for p in hist_periods:
        ebitda_p = h_ebitda.get(p)
        ebit = None
        if ebitda_p is not None:
            ebit = ebitda_p - (h_da.get(p) or 0.0) - (h_oa.get(p) or 0.0) - (h_sbc.get(p) or 0.0)
        disp_taxes[p] = _mul(ebit, tax_rate)

    ni_m = {p: _div(disp_ni.get(p), disp_rev.get(p)) for p in all_periods}

    gp_m = {p: _div(disp_gp.get(p), disp_rev.get(p)) for p in all_periods}
    ebitda_m = {p: _div(disp_ebitda.get(p), disp_rev.get(p)) for p in all_periods}

    gp_imp_h, ebitda_imp_h = {}, {}
    for i, p in enumerate(hist_periods):
        if i == 0 or p == "TTM":
            gp_imp_h[p] = ebitda_imp_h[p] = None
        else:
            prev = hist_periods[i - 1]
            gp_imp_h[p] = (gp_m[p] - gp_m[prev]) if gp_m.get(p) is not None and gp_m.get(prev) is not None else None
            ebitda_imp_h[p] = (ebitda_m[p] - ebitda_m[prev]) if ebitda_m.get(p) is not None and ebitda_m.get(prev) is not None else None

    def ms_lock(p):
        return is_public and p in MS_COVERED_PERIODS

    rows = []
    rows.append(html.Tr([html.Th("Line Item", style=_HDR_LABEL)] + [html.Th(p, style=_HDR) for p in all_periods]))

    # Revenue
    cells = [html.Td("Revenue", style=_LABEL_BOLD)]
    for p in all_periods:
        if p in hist_periods or ms_lock(p):
            cells.append(_locked(_fmt_dollars(disp_rev.get(p))))
        else:
            v = disp_rev.get(p)
            cells.append(_inp("revenue", p, "" if v is None else f"{v:,.0f}"))
    rows.append(html.Tr(cells))

    # Growth
    cells = [html.Td("    Growth (%)", style=_LABEL)]
    for p in all_periods:
        if p in hist_periods or ms_lock(p):
            cells.append(_locked(_fmt_pct(disp_growth.get(p))))
        else:
            if pd.last_edited_revenue.get(p) == "growth" and pd.revenue_growth.get(p) is not None:
                g = pd.revenue_growth.get(p)
            else:
                g = disp_growth.get(p) if disp_growth.get(p) is not None else pd.revenue_growth.get(p)
            cells.append(_inp("revenue_growth", p, "" if g is None else f"{g * 100:.1f}%"))
    rows.append(html.Tr(cells))

    def locked_row(label, values, bold=False, pct=False):
        fmt = _fmt_pct if pct else _fmt_dollars
        c = [html.Td(label, style=_LABEL_BOLD if bold else _LABEL)]
        for p in all_periods:
            c.append(_locked(fmt(values.get(p))))
        rows.append(html.Tr(c))

    def pct_driver(label, field, hist_map=None, lock_ms=False):
        hist_map = hist_map or {}
        c = [html.Td(label, style=_LABEL)]
        for p in all_periods:
            if p in hist_periods:
                c.append(_locked(_fmt_pct(hist_map.get(p))))
            elif lock_ms and ms_lock(p):
                c.append(_locked("-"))
            else:
                v = getattr(pd, field).get(p)
                c.append(_inp(field, p, "" if v is None else f"{v * 100:.1f}%"))
        rows.append(html.Tr(c))

    locked_row("Gross Profit", disp_gp, bold=True)
    locked_row("    Margin (%)", gp_m, pct=True)
    pct_driver("    Improvement (%)", "gp_improvement", gp_imp_h)

    locked_row("EBIT / Operating Income (source)", disp_ebitda_rep)
    locked_row("Adjusted EBITDA (D&A/OA/SBC add-back)", disp_ebitda, bold=True)
    locked_row("    Margin (%)", ebitda_m, pct=True)
    pct_driver("    Improvement (%)", "ebitda_improvement", ebitda_imp_h, lock_ms=True)

    locked_row("D&A", disp_da, bold=True)
    pct_driver("    as % of Revenue", "da_pct", {p: _div(h_da.get(p), h_rev.get(p)) for p in hist_periods})

    locked_row("Other Amortization", disp_oa, bold=True)
    pct_driver("    as % of Revenue", "other_amort_pct", {p: _div(h_oa.get(p), h_rev.get(p)) for p in hist_periods})

    locked_row("Stock-Based Compensation", disp_sbc, bold=True)
    pct_driver("    as % of Revenue", "sbc_pct", {p: _div(h_sbc.get(p), h_rev.get(p)) for p in hist_periods})

    c = [html.Td("+Other Adjustments", style=_LABEL_BOLD)]
    for p in all_periods:
        if p in hist_periods:
            c.append(_locked("-"))
        elif ms_lock(p):
            c.append(_locked(_fmt_dollars(disp_other_adj.get(p))))
        else:
            v = pd.other_adj.get(p)
            c.append(_inp("other_adj", p, "" if v is None else f"{v:,.0f}"))
    rows.append(html.Tr(c))

    locked_row("Taxes", disp_taxes, bold=True)

    locked_row("Net Income", disp_ni, bold=True)
    locked_row("    Margin (%)", ni_m, pct=True)

    locked_row("CapEx", disp_capex, bold=True)
    pct_driver("    as % of Revenue", "capex_pct", {p: _div(h_capex.get(p), h_rev.get(p)) for p in hist_periods})

    table = html.Table(
        [html.Thead(rows[0]), html.Tbody(rows[1:])],
        className="table table-sm mb-0",
        # No fixed width — let the table size to its natural content
        # width (respecting each cell's 88px minWidth) so the parent
        # container's overflowX:auto actually has something to scroll,
        # instead of forcing every column to compress to fit.
        style={"width": "max-content", "minWidth": "100%", "borderCollapse": "separate", "borderSpacing": 0},
    )
    status = (
        f"{inputs.subject_company_name} ({inputs.subject_ticker or 'private'}) · "
        f"{inputs.company_status} · hist={inputs.historical_years} proj={inputs.projection_years}"
    )
    return table, status, inputs.historical_years, inputs.projection_years, pd


def _recalc_from_cells(
    session_data, source_results, cell_ids, cell_values, draft_blob, triggered_id=None
):
    pd = _blob_to_pd(draft_blob) if draft_blob else dict_to_projection_data(session_data)
    pd = _harvest(pd, cell_ids, cell_values, triggered_id=triggered_id)
    inputs = dict_to_project_inputs(session_data)
    resolved = _resolve(session_data, source_results, pd)
    _apply_resolved(pd, resolved, list(inputs.projection_period_columns))
    _sync_growth_display(pd, session_data, source_results, list(inputs.projection_period_columns))
    return pd


# ----- open / cancel -----
@callback(
    Output("modal-projection", "is_open"),
    Output("proj-modal-grid-container", "children"),
    Output("proj-modal-status", "children"),
    Output("proj-spin-hist", "value"),
    Output("proj-spin-proj", "value"),
    Output("proj-draft-store", "data"),
    Output("proj-suppress-recalc", "data", allow_duplicate=True),
    Input("link-open-projection", "n_clicks"),
    Input("btn-proj-cancel", "n_clicks"),
    State("session-store", "data"),
    State("source-results-store", "data"),
    prevent_initial_call=True,
)
def toggle_projection_modal(open_clicks, cancel_clicks, session_data, source_results):
    if ctx.triggered_id == "btn-proj-cancel":
        return False, no_update, no_update, no_update, no_update, no_update, False
    if not open_clicks:
        return no_update, no_update, no_update, no_update, no_update, no_update, no_update
    try:
        session_data = session_data or {}
        pd = dict_to_projection_data(session_data)
        table, status, hy, py, pd = build_table(session_data, source_results or {}, pd)
        # suppress one wave of input callbacks from freshly mounted cells
        return True, table, status, hy, py, _pd_to_blob(pd), True
    except Exception:
        traceback.print_exc()
        return True, html.Pre(traceback.format_exc(), className="text-danger p-2"), "Error", no_update, no_update, no_update, False


# ----- live recalc when leaving a cell -----
@callback(
    Output("proj-modal-grid-container", "children", allow_duplicate=True),
    Output("proj-modal-status", "children", allow_duplicate=True),
    Output("proj-draft-store", "data", allow_duplicate=True),
    Output("proj-suppress-recalc", "data", allow_duplicate=True),
    Input({"type": "proj-input", "field": ALL, "period": ALL}, "value"),
    State({"type": "proj-input", "field": ALL, "period": ALL}, "id"),
    State("session-store", "data"),
    State("source-results-store", "data"),
    State("proj-draft-store", "data"),
    State("proj-suppress-recalc", "data"),
    State("modal-projection", "is_open"),
    prevent_initial_call=True,
)
def live_recalc(values, ids, session_data, source_results, draft, suppress, is_open):
    if not is_open:
        return no_update, no_update, no_update, no_update
    # Ignore the synthetic fire right after we rebuild the grid
    if suppress:
        return no_update, no_update, no_update, False
    if not ids:
        return no_update, no_update, no_update, no_update
    try:
        pd = _recalc_from_cells(
            session_data or {},
            source_results or {},
            ids,
            values,
            draft,
            triggered_id=ctx.triggered_id,
        )
        table, status, _hy, _py, pd = build_table(session_data or {}, source_results or {}, pd)
        status = f"↻ Updated · {status}"
        return table, status, _pd_to_blob(pd), True  # suppress next mount wave
    except Exception:
        traceback.print_exc()
        return no_update, "Recalc error (see terminal)", no_update, False


# ----- hist/proj years: session + home spins + rebuild -----
@callback(
    Output("session-store", "data", allow_duplicate=True),
    Output("input-hist-years", "value", allow_duplicate=True),
    Output("input-proj-years", "value", allow_duplicate=True),
    Output("proj-modal-grid-container", "children", allow_duplicate=True),
    Output("proj-modal-status", "children", allow_duplicate=True),
    Output("proj-draft-store", "data", allow_duplicate=True),
    Output("proj-suppress-recalc", "data", allow_duplicate=True),
    Input("proj-spin-hist", "value"),
    Input("proj-spin-proj", "value"),
    State("session-store", "data"),
    State("source-results-store", "data"),
    State("proj-draft-store", "data"),
    State({"type": "proj-input", "field": ALL, "period": ALL}, "id"),
    State({"type": "proj-input", "field": ALL, "period": ALL}, "value"),
    State("modal-projection", "is_open"),
    prevent_initial_call=True,
)
def on_proj_year_spins(hist_y, proj_y, session_data, source_results, draft, ids, values, is_open):
    if not is_open:
        return no_update, no_update, no_update, no_update, no_update, no_update, no_update
    # Ignore spin values set while opening the modal (same tick as open)
    if ctx.triggered_id not in ("proj-spin-hist", "proj-spin-proj"):
        return no_update, no_update, no_update, no_update, no_update, no_update, no_update

    session_data = dict(session_data or {})
    try:
        hy = int(hist_y) if hist_y is not None else int(session_data.get("historical_years") or 5)
        py = int(proj_y) if proj_y is not None else int(session_data.get("projection_years") or 5)
    except (TypeError, ValueError):
        return no_update, no_update, no_update, no_update, no_update, no_update, no_update

    hy = max(0, min(5, hy))
    py = max(1, min(20, py))
    session_data["historical_years"] = hy
    session_data["projection_years"] = py

    try:
        # Year spin: no single cell edit — keep existing last_edited flags
        pd = _recalc_from_cells(
            session_data, source_results or {}, ids, values, draft, triggered_id=None
        )
        table, status, _a, _b, pd = build_table(session_data, source_results or {}, pd)
        status = f"Columns: hist={hy} proj={py} · {status}"
        return session_data, hy, py, table, status, _pd_to_blob(pd), True
    except Exception:
        traceback.print_exc()
        return session_data, hy, py, no_update, "Year spin error", no_update, False


# ----- Save: commit draft to session, stay open, refresh grid -----
@callback(
    Output("session-store", "data", allow_duplicate=True),
    Output("proj-modal-grid-container", "children", allow_duplicate=True),
    Output("proj-modal-status", "children", allow_duplicate=True),
    Output("proj-draft-store", "data", allow_duplicate=True),
    Output("proj-suppress-recalc", "data", allow_duplicate=True),
    Input("btn-proj-save", "n_clicks"),
    State({"type": "proj-input", "field": ALL, "period": ALL}, "id"),
    State({"type": "proj-input", "field": ALL, "period": ALL}, "value"),
    State("session-store", "data"),
    State("source-results-store", "data"),
    State("proj-draft-store", "data"),
    prevent_initial_call=True,
)
def save_projections(n, ids, values, session_data, source_results, draft):
    if not n:
        return no_update, no_update, no_update, no_update, no_update
    session_data = dict(session_data or {})
    # Save: commit full form; do not invent a last_edited from an arbitrary cell
    pd = _recalc_from_cells(
        session_data, source_results or {}, ids, values, draft, triggered_id=None
    )
    session_data["projection_page_state"] = _pd_to_blob(pd)
    table, status, _hy, _py, pd = build_table(session_data, source_results or {}, pd)
    status = f"✅ Saved to session · {status} · Cancel/X to close"
    return session_data, table, status, _pd_to_blob(pd), True