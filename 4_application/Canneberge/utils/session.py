import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from Canneberge.app_state import (
    ProjectInputs, Transaction, PrivateFinancials, ProjectionData
)

SESSION_DIR = Path(os.environ.get(
    "CANNEBERGE_SESSIONS",
    Path.home() / ".canneberge" / "sessions"
))


def _ensure_dir():
    SESSION_DIR.mkdir(parents=True, exist_ok=True)


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
    debt_page_state: Optional[dict] = None,
    source_data_results: Optional[dict] = None,
    filepath: Optional[Path] = None,
) -> Path:
    """
    Serialize all current inputs and cached web source data to a JSON file.
    Returns the path written to.
    """
    _ensure_dir()

    if filepath is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        name = (
            project_inputs.subject_company_name.replace(" ", "_")
            or "session"
        )
        filepath = SESSION_DIR / f"{name}_{timestamp}.json"

    payload = {
        "version": 2,
        "saved_at": datetime.now().isoformat(),

        "project_inputs": {
            "client": project_inputs.client,
            "subject_company_name": project_inputs.subject_company_name,
            "main_title": project_inputs.main_title,
            "valuation_date": project_inputs.valuation_date,
            "numeric_scale": project_inputs.numeric_scale,
            "draft_final": project_inputs.draft_final,
            "standard_of_value": project_inputs.standard_of_value,
            "taxable_nontaxable": project_inputs.taxable_nontaxable,
            "basis_of_value": project_inputs.basis_of_value,
            "company_status": project_inputs.company_status,
            "subject_ticker": project_inputs.subject_ticker,
            "subject_tax_rate": project_inputs.subject_tax_rate,
            "last_fiscal_year": project_inputs.last_fiscal_year,
            "last_fiscal_quarter": project_inputs.last_fiscal_quarter,
            "next_fiscal_year": project_inputs.next_fiscal_year,
            "nfy_1": project_inputs.nfy_1,
            "nfy_2": project_inputs.nfy_2,
            "historical_years": project_inputs.historical_years,
            "projection_years": project_inputs.projection_years,
            "gpc_tickers": project_inputs.gpc_tickers,
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
                for t in project_inputs.gt_transactions
            ],
        },

        "private_financials": {
            "is_data": private_financials.is_data,
            "bs_data": private_financials.bs_data,
        },

        "gt_page_state":         gt_page_state,
        "gpc_page_state":        gpc_page_state,
        "projection_page_state": projection_page_state,
        "wacc_page_state":       wacc_page_state,
        "dcf_page_state":        dcf_page_state,
        "nwc_page_state":        nwc_page_state,
        "debt_page_state":       debt_page_state or {},
        "dashboard_page_state":  dashboard_page_state,
        "source_data_results":   source_data_results or {},
    }

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=str)

    return filepath


def load_session(filepath: Path) -> dict:
    """
    Load a session JSON file.
    """
    with open(filepath, "r", encoding="utf-8") as f:
        payload = json.load(f)

    pi_raw        = payload.get("project_inputs", {})
    pf_raw        = payload.get("private_financials", {})
    gt_raw        = payload.get("gt_page_state", {})
    gpc_raw       = payload.get("gpc_page_state", {})
    proj_raw      = payload.get("projection_page_state", {})
    wacc_raw      = payload.get("wacc_page_state", {})
    dcf_raw       = payload.get("dcf_page_state", {})
    nwc_raw       = payload.get("nwc_page_state", {})
    debt_raw      = payload.get("debt_page_state", {})
    dashboard_raw = payload.get("dashboard_page_state", {})
    sources_raw   = payload.get("source_data_results", {})

    pf = PrivateFinancials(
        is_data=pf_raw.get("is_data", {}),
        bs_data=pf_raw.get("bs_data", {}),
    )

    return {
        "saved_at":             payload.get("saved_at", ""),
        "project_inputs_raw":    pi_raw,
        "private_financials":    pf,
        "gt_page_state":         gt_raw,
        "gpc_page_state":        gpc_raw,
        "projection_page_state": proj_raw,
        "wacc_page_state":       wacc_raw,
        "dcf_page_state":        dcf_raw,
        "nwc_page_state":        nwc_raw,
        "debt_page_state":       debt_raw,
        "dashboard_page_state":  dashboard_raw,
        "source_data_results":   sources_raw,
    }


def list_sessions() -> list:
    _ensure_dir()
    files = sorted(
        SESSION_DIR.glob("*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    results = []
    for f in files:
        try:
            with open(f, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            results.append({
                "path": f,
                "name": f.stem,
                "saved_at": data.get("saved_at", ""),
            })
        except Exception:
            results.append({
                "path": f,
                "name": f.stem,
                "saved_at": "",
            })
    return results