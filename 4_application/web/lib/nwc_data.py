"""
web/lib/nwc_data.py

Headless NWC resolver. Returns the same dict web/pages/nwc.py was already
building, so the page keeps working unchanged, plus a populated Residual
column so DCF can read changes_in_nwc["Residual"].

Residual Revenue comes from Canneberge.Calculations.dcf.residual_revenue,
driven by dcf_page_state["ltg_input"]. DCF reads NWC; NWC reads only the
LTGR text out of session — no circular import.
"""

from typing import Dict, List, Optional

from Canneberge.Calculations.nwc import (
    CA_MAX_ROWS, CL_MAX_ROWS,
    CA_DEFAULT_SELECTIONS, CL_DEFAULT_SELECTIONS,
    CA_DEFAULT_ROWS, CL_DEFAULT_ROWS,
    period_columns, historical_columns, fye_years,
    sum_selected_rows, subject_nwc_by_period, changes_in_nwc,
    peer_series, peer_statistics, nwc_bridge,
    parse_pct_text, safe_div,
)
from Canneberge.Calculations.dcf import parse_pct, residual_revenue
from web.lib.session_io import dict_to_project_inputs
from web.lib.subject_metrics import get_subject_metric_value


def _pad_selections(saved: list, defaults: list, count: int) -> List[str]:
    out: List[str] = []
    for i in range(count):
        if i < len(saved) and saved[i] is not None:
            out.append(str(saved[i]))
        elif i < len(defaults):
            out.append(defaults[i])
        else:
            out.append("")
    return out


def nwc_state_from_session(session_data: dict) -> dict:
    raw = (session_data or {}).get("nwc_page_state", {}) or {}

    def _int(key, default, lo, hi):
        try:
            return max(lo, min(hi, int(raw.get(key, default))))
        except (TypeError, ValueError):
            return default

    ca_rows = _int("ca_row_count", CA_DEFAULT_ROWS, 1, CA_MAX_ROWS)
    cl_rows = _int("cl_row_count", CL_DEFAULT_ROWS, 1, CL_MAX_ROWS)

    return {
        "historical_years": _int("historical_years", 5, 1, 5),
        "ca_row_count": ca_rows,
        "cl_row_count": cl_rows,
        "ca_selections": _pad_selections(
            raw.get("ca_selections") or [], CA_DEFAULT_SELECTIONS, ca_rows
        ),
        "cl_selections": _pad_selections(
            raw.get("cl_selections") or [], CL_DEFAULT_SELECTIONS, cl_rows
        ),
        "cash_treatment": raw.get("cash_treatment", "Excluding Cash"),
        "nwc_basis": raw.get("nwc_basis", "% of Revenue"),
        "selected_pct": raw.get("selected_pct", "15.0%"),
        "gpc_exclusions": list(raw.get("gpc_exclusions") or []),
    }


def _exclusion_map(tickers: List[str], flags: list) -> Dict[str, bool]:
    return {
        t: (bool(flags[i]) if i < len(flags) else False)
        for i, t in enumerate(tickers)
    }


def get_nwc_results(
    session_data: dict,
    source_results: dict,
    state: Optional[dict] = None,
) -> dict:
    state = state or nwc_state_from_session(session_data)
    inputs = dict_to_project_inputs(session_data or {})

    headers, is_hist = period_columns(
        state["historical_years"],
        list(inputs.projection_period_columns),
    )
    hist_periods = historical_columns(headers, is_hist)

    def sf(key: str, period: str) -> Optional[float]:
        if not key or period == "Residual":
            return None
        return get_subject_metric_value(
            session_data or {}, source_results or {}, key, period
        )

    revenue = {p: sf("revenue", p) for p in headers}

    # Residual Revenue — the one value NWC cannot source itself.
    dcf_state = (session_data or {}).get("dcf_page_state", {}) or {}
    ltgr = parse_pct(dcf_state.get("ltg_input", "3.0%"))
    proj_cols = list(inputs.projection_period_columns)
    final_proj = proj_cols[-1] if proj_cols else None
    revenue["Residual"] = residual_revenue(
        revenue.get(final_proj) if final_proj else None, ltgr
    )

    ca_rows, ca_sums = sum_selected_rows(state["ca_selections"], headers, sf)
    cl_rows, cl_sums = sum_selected_rows(state["cl_selections"], headers, sf)

    selected_pct = parse_pct_text(state["selected_pct"])
    pct_basis = state["nwc_basis"] == "% of Revenue"

    nwc = subject_nwc_by_period(
        headers, is_hist, revenue, ca_sums, cl_sums, selected_pct, pct_basis
    )
    nwc_pct = {p: safe_div(nwc.get(p), revenue.get(p)) for p in headers}
    changes = changes_in_nwc(headers, nwc)

    tickers = list(inputs.gpc_tickers or [])
    excluded = _exclusion_map(tickers, state["gpc_exclusions"])
    exclude_cash = state["cash_treatment"] == "Excluding Cash"

    sa = (source_results or {}).get("stockanalysis", {}) or {}
    peers = peer_series(
        sa.get("BS", []), sa.get("IS", []),
        tickers, hist_periods, exclude_cash,
    )
    peer_pct = {t: peers[t]["pct"] for t in tickers}
    stats = peer_statistics(peer_pct, hist_periods, excluded)

    bridge = nwc_bridge(revenue.get("TTM"), nwc.get("TTM"), selected_pct)

    return {
        "inputs": inputs,
        "headers": headers,
        "is_hist": is_hist,
        "hist_periods": hist_periods,
        "fye": fye_years(
            headers, inputs.last_fiscal_year_year, inputs.next_fiscal_year_year
        ),
        "revenue": revenue,
        "ca_rows": ca_rows, "ca_sums": ca_sums,
        "cl_rows": cl_rows, "cl_sums": cl_sums,
        "nwc": nwc, "nwc_pct": nwc_pct, "changes": changes,
        "tickers": tickers, "excluded": excluded,
        "peers": peers, "peer_pct": peer_pct, "stats": stats,
        "bridge": bridge,
    }