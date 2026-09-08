"""
Canneberge/utils/session.py
Handles core loading, saving, and listing of sessions.
Includes recursive deep merge logic to preserve web-only extension fields on desktop save.
"""
import json
import copy
from pathlib import Path
from datetime import datetime
from Canneberge.app_state import ProjectInputs, PrivateFinancials, Transaction

# Session Directory
SESSION_DIR = Path.home() / ".canneberge" / "sessions"
SESSION_DIR.mkdir(parents=True, exist_ok=True)

# In-memory single-process cache to track the original payload for merges
_LAST_LOADED_RAW_PAYLOAD = {}


def deep_merge(base: dict, update: dict) -> dict:
    """
    Recursively merges update dict into base dict.
    Type mismatches (e.g., dict overriding a list or vice versa) will default
    to overwriting with the new update type.
    """
    if not isinstance(base, dict) or not isinstance(update, dict):
        return copy.deepcopy(update)
    out = copy.deepcopy(base)
    for k, v in update.items():
        if k in out:
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def project_inputs_to_dict(pi: ProjectInputs) -> dict:
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


def save_session(
    project_inputs: ProjectInputs,
    private_financials: PrivateFinancials,
    gt_page_state: dict,
    gpc_page_state: dict,
    projection_page_state: dict,
    wacc_page_state: dict,
    dcf_page_state: dict,
    nwc_page_state: dict,
    dashboard_page_state: dict,
    debt_page_state: dict,
    source_data_results: dict,
    filepath: Path = None,
) -> Path:
    global _LAST_LOADED_RAW_PAYLOAD
    if filepath is None:
        filepath = SESSION_DIR / "untitled_session.json"
    else:
        filepath = Path(filepath)

    new_payload = {
        "version": "1.0",
        "saved_at": datetime.now().isoformat(),
        "project_inputs": project_inputs_to_dict(project_inputs),
        "private_financials": {
            "is_data": private_financials.is_data,
            "bs_data": private_financials.bs_data,
        },
        "gt_page_state": gt_page_state,
        "gpc_page_state": gpc_page_state,
        "projection_page_state": projection_page_state,
        "wacc_page_state": wacc_page_state,
        "dcf_page_state": dcf_page_state,
        "nwc_page_state": nwc_page_state,
        "dashboard_page_state": dashboard_page_state,
        "debt_page_state": debt_page_state,
        "source_data_results": source_data_results,
    }

    # Overlay update payload on top of original file layout
    base_payload = {}
    if _LAST_LOADED_RAW_PAYLOAD:
        base_payload = copy.deepcopy(_LAST_LOADED_RAW_PAYLOAD)
    elif filepath.exists():
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                base_payload = json.load(f)
        except Exception:
            pass

    if base_payload:
        final_payload = deep_merge(base_payload, new_payload)
    else:
        final_payload = new_payload

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(final_payload, f, indent=2, default=str)

    return filepath


def load_session(filepath: Path) -> dict:
    global _LAST_LOADED_RAW_PAYLOAD
    filepath = Path(filepath)
    with open(filepath, "r", encoding="utf-8") as f:
        payload = json.load(f)

    # Cache raw structure so saving from desktop doesn't strip web-only keys
    _LAST_LOADED_RAW_PAYLOAD = copy.deepcopy(payload)

    pi_raw = payload.get("project_inputs", {})
    gt_objs = []
    for t in pi_raw.get("gt_transactions", []):
        gt_objs.append(Transaction(
            closing_date=t.get("closing_date", ""),
            target=t.get("target", ""),
            acquirer=t.get("acquirer", ""),
            bev=t.get("bev"),
            ttm_revenue=t.get("ttm_revenue"),
            ttm_ebitda=t.get("ttm_ebitda"),
            ttm_ebit=t.get("ttm_ebit"),
        ))

    pi = ProjectInputs(
        client=pi_raw.get("client", "Ted & Co."),
        subject_company_name=pi_raw.get("subject_company_name", "COMPANY NAME"),
        main_title=pi_raw.get("main_title", ""),
        valuation_date=pi_raw.get("valuation_date", "7/21/2026"),
        numeric_scale=pi_raw.get("numeric_scale", "Millions"),
        draft_final=pi_raw.get("draft_final", "Draft"),
        standard_of_value=pi_raw.get("standard_of_value", "Fair Market Value"),
        taxable_nontaxable=pi_raw.get("taxable_nontaxable", "Taxable"),
        basis_of_value=pi_raw.get("basis_of_value", "BEV / Equity Value"),
        company_status=pi_raw.get("company_status", "Private Company"),
        subject_ticker=pi_raw.get("subject_ticker", ""),
        subject_tax_rate=pi_raw.get("subject_tax_rate", 0.21),
        last_fiscal_year=pi_raw.get("last_fiscal_year", "12/31/2025"),
        last_fiscal_quarter=pi_raw.get("last_fiscal_quarter", "3/31/2026"),
        next_fiscal_year=pi_raw.get("next_fiscal_year", "12/31/2026"),
        nfy_1=pi_raw.get("nfy_1", "12/31/2027"),
        nfy_2=pi_raw.get("nfy_2", "12/31/2028"),
        gpc_tickers=pi_raw.get("gpc_tickers", []),
        gpc_company_names=pi_raw.get("gpc_company_names", {}),
        gt_transactions=gt_objs,
        historical_years=int(pi_raw.get("historical_years", 5)),
        projection_years=int(pi_raw.get("projection_years", 5)),
    )

    pf_raw = payload.get("private_financials", {})
    pf = PrivateFinancials(
        is_data=pf_raw.get("is_data", {}),
        bs_data=pf_raw.get("bs_data", {}),
    )

    return {
        "project_inputs_raw": pi_raw,
        "project_inputs": pi,
        "private_financials": pf,
        "gt_page_state": payload.get("gt_page_state") or {},
        "gpc_page_state": payload.get("gpc_page_state") or {},
        "projection_page_state": payload.get("projection_page_state") or {},
        "wacc_page_state": payload.get("wacc_page_state") or {},
        "dcf_page_state": payload.get("dcf_page_state") or {},
        "nwc_page_state": payload.get("nwc_page_state") or {},
        "dashboard_page_state": payload.get("dashboard_page_state") or {},
        "debt_page_state": payload.get("debt_page_state") or {},
        "source_data_results": payload.get("source_data_results") or {},
        "saved_at": payload.get("saved_at", ""),
    }


def list_sessions() -> list:
    sessions = []
    for p in SESSION_DIR.glob("*.json"):
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            sessions.append({
                "path": p,
                "name": p.stem,
                "saved_at": data.get("saved_at", "Unknown"),
            })
        except Exception:
            pass
    return sorted(sessions, key=lambda x: x["saved_at"], reverse=True)