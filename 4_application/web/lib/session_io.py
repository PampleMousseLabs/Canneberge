"""
Adapts Canneberge.utils.session (which speaks ProjectInputs dataclasses)
to Dash dcc.Store dicts. This is the ONE place where dict <-> dataclass
conversion happens for session persistence. Every page reads the session
dict; only save/load crosses the dataclass boundary.
"""
from pathlib import Path
from typing import Optional

from Canneberge.app_state import (
    ProjectInputs, Transaction, PrivateFinancials, ProjectionData
)
from Canneberge.utils.session import (
    save_session as _core_save_session,
    load_session as _core_load_session,
    list_sessions as _core_list_sessions,
    SESSION_DIR,
)


def _clean_float(val, default=None) -> Optional[float]:
    if val is None or val == "":
        return default
    if isinstance(val, (int, float)):
        return float(val)
    cleaned = str(val).replace("$", "").replace(",", "").replace("%", "").strip()
    try:
        return float(cleaned)
    except (ValueError, TypeError):
        return default


def _clean_pct(val, default=0.21) -> float:
    if val is None or val == "":
        return default
    if isinstance(val, (int, float)):
        return float(val) if val <= 1.0 else float(val) / 100.0
    raw_str = str(val).strip()
    has_pct_sign = "%" in raw_str
    cleaned = raw_str.replace("%", "").replace(",", "").strip()
    try:
        f = float(cleaned)
        return f / 100.0 if (has_pct_sign or f > 1.0) else f
    except (ValueError, TypeError):
        return default


def dict_to_project_inputs(data: dict) -> ProjectInputs:
    """Session-store dict -> ProjectInputs. Same logic previously
    inlined in web/pages/source_data.py — lifted here so every page
    (and save_session_from_store below) uses the same conversion."""
    if not data:
        return ProjectInputs()

    gt_raw = data.get("gt_transactions", [])
    gt_objs = []
    for t in gt_raw:
        if isinstance(t, dict) and any(t.values()):
            gt_objs.append(Transaction(
                closing_date=str(t.get("closing_date", "")),
                target=str(t.get("target", "")),
                acquirer=str(t.get("acquirer", "")),
                bev=_clean_float(t.get("bev")),
                ttm_revenue=_clean_float(t.get("ttm_revenue")),
                ttm_ebitda=_clean_float(t.get("ttm_ebitda")),
                ttm_ebit=_clean_float(t.get("ttm_ebit")),
            ))

    hist_yrs = _clean_float(data.get("historical_years", 5), default=5)
    proj_yrs = _clean_float(data.get("projection_years", 5), default=5)

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
        subject_tax_rate=_clean_pct(data.get("subject_tax_rate", 0.21)),
        last_fiscal_year=data.get("last_fiscal_year", "12/31/2025"),
        last_fiscal_quarter=data.get("last_fiscal_quarter", "3/31/2026"),
        next_fiscal_year=data.get("next_fiscal_year", "12/31/2026"),
        nfy_1=data.get("nfy_1", "12/31/2027"),
        nfy_2=data.get("nfy_2", "12/31/2028"),
        gpc_tickers=data.get("gpc_tickers", []),
        gpc_company_names=data.get("gpc_company_names", {}),
        gt_transactions=gt_objs,
        historical_years=int(hist_yrs),
        projection_years=int(proj_yrs),
    )


def project_inputs_to_dict(pi: ProjectInputs) -> dict:
    """Inverse of dict_to_project_inputs. Used when loading a session
    file back into the browser session-store."""
    return {
        "client": pi.client,
        "subject_company_name": pi.subject_company_name,
        "main_title": pi.main_title,
        "valuation_date": pi.valuation_date,
        "numeric_scale": pi.numeric_scale,
        "draft_final": pi.draft_final,
        "standard_of_value": pi.standard_of_value,
        "taxable_nontaxable": pi.taxable_nontaxable,
        "basis_of_value": pi.basis_of_value,
        "company_status": pi.company_status,
        "subject_ticker": pi.subject_ticker,
        "subject_tax_rate": pi.subject_tax_rate,
        "last_fiscal_year": pi.last_fiscal_year,
        "last_fiscal_quarter": pi.last_fiscal_quarter,
        "next_fiscal_year": pi.next_fiscal_year,
        "nfy_1": pi.nfy_1,
        "nfy_2": pi.nfy_2,
        "historical_years": pi.historical_years,
        "projection_years": pi.projection_years,
        "gpc_tickers": pi.gpc_tickers,
        "gpc_company_names": pi.gpc_company_names,
        "gt_transactions": [
            {
                "closing_date": t.closing_date,
                "target": t.target,
                "acquirer": t.acquirer,
                "bev": t.bev,
                "ttm_revenue": t.ttm_revenue,
                "ttm_ebitda": t.ttm_ebitda,
                "ttm_ebit": t.ttm_ebit,
            }
            for t in pi.gt_transactions
        ],
    }


def save_session_from_stores(
    session_data: dict,
    source_results: dict,
    filepath: Optional[Path] = None,
) -> Path:
    """
    Save the current browser session (session-store + source-results-store)
    to disk. Web-only pages that don't exist yet (gpc/wacc/dcf/nwc/etc.)
    pass empty dicts — as those pages get built, this function should be
    extended to accept their per-page stores.

    File format is fully compatible with the desktop app's session files.
    """
    pi = dict_to_project_inputs(session_data or {})
    pf = PrivateFinancials(
        is_data=(session_data or {}).get("private_is_data", {}),
        bs_data=(session_data or {}).get("private_bs_data", {}),
    )

    return _core_save_session(
        project_inputs=pi,
        private_financials=pf,
        gt_page_state=(session_data or {}).get("gt_page_state", {}),
        gpc_page_state=(session_data or {}).get("gpc_page_state", {}),
        projection_page_state=(session_data or {}).get("projection_page_state", {}),
        wacc_page_state=(session_data or {}).get("wacc_page_state", {}),
        dcf_page_state=(session_data or {}).get("dcf_page_state", {}),
        nwc_page_state=(session_data or {}).get("nwc_page_state", {}),
        dashboard_page_state=(session_data or {}).get("dashboard_page_state", {}),
        debt_page_state=(session_data or {}).get("debt_page_state", {}),
        source_data_results=source_results or {},
        filepath=filepath,
    )


def load_session_to_stores(filepath: Path) -> tuple[dict, dict, str]:
    """
    Load a session file, returning (session_store_dict, source_results_dict, saved_at).
    Populates session-store with project inputs + private financials + any
    saved per-page states. Returns source_data_results separately since
    it lives in its own store.
    """
    payload = _core_load_session(filepath)
    pi_raw = payload["project_inputs_raw"]
    pf = payload["private_financials"]

    session_dict = dict(pi_raw)  # already in dict form from core loader
    session_dict["private_is_data"] = pf.is_data
    session_dict["private_bs_data"] = pf.bs_data
    session_dict["gt_page_state"] = payload.get("gt_page_state") or {}
    # Always a dict — GPC page restore/persist assume mapping, not None
    session_dict["gpc_page_state"] = payload.get("gpc_page_state") or {}
    session_dict["projection_page_state"] = payload["projection_page_state"]
    session_dict["wacc_page_state"] = payload["wacc_page_state"]
    session_dict["dcf_page_state"] = payload["dcf_page_state"]
    session_dict["nwc_page_state"] = payload["nwc_page_state"]
    session_dict["debt_page_state"] = payload["debt_page_state"]
    session_dict["dashboard_page_state"] = payload["dashboard_page_state"]
    session_dict["disk_session_name"] = Path(filepath).stem

    return session_dict, payload["source_data_results"], payload["saved_at"]


def list_available_sessions() -> list:
    """Re-export core's list_sessions with paths converted to strings
    for JSON-serializability in Dash callbacks."""
    sessions = _core_list_sessions()
    return [
        {"path": str(s["path"]), "name": s["name"], "saved_at": s["saved_at"]}
        for s in sessions
    ]