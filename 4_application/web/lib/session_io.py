"""
web/lib/session_io.py
Adapts Canneberge.utils.session to Dash dcc.Store dicts.
Performs clean translation of list patterns to dictionary trees on load,
and re-compiles dictionary models to canonical desktop lists on save.
"""
import copy
from pathlib import Path
from typing import Optional

from Canneberge.app_state import ProjectInputs, Transaction, PrivateFinancials
from Canneberge.utils.session import (
    save_session as _core_save_session,
    load_session as _core_load_session,
    list_sessions as _core_list_sessions,
    SESSION_DIR,
)


# ==========================================
# DESKTOP <-> WEB VALUE FORMATTERS
# ==========================================

def clean_val(v) -> str:
    if v is None:
        return ""
    s = str(v).strip()
    if s.endswith("x"):
        s = s[:-1].strip()
    if s.endswith("%"):
        s = s[:-1].strip()
    return s


def format_val(v, suffix: str) -> str:
    if v is None or str(v).strip() == "":
        return ""
    s = str(v).strip()
    if not s.endswith(suffix):
        return s + suffix
    return s


# ==========================================
# PAGE-SPECIFIC BIDIRECTIONAL ADAPTERS
# ==========================================

GPC_SLOT_COUNT = 7
GPC_EXCLUSION_COUNT = 15


def _is_desktop_gpc_shape(state: dict) -> bool:
    """
    Desktop/canonical GPC state has list-shaped fields and/or desktop key names.
    Web-origin legacy files have metric_cols / basis_state / exclude_map.
    """
    if not isinstance(state, dict):
        return False

    return any(k in state for k in [
        "metric_selections",
        "per_basis_state",
        "last_basis_mode",
        "excluded_rows",
    ])


def _slot_dict_from_any(obj, clean_suffixes: bool = True, slot_count: int = GPC_SLOT_COUNT) -> dict:
    """
    Converts either:
      list: ["3.74x", ...]
      dict: {"0": "3.74", ...}
    into:
      {"0": "3.74", ...}
    preserving all 7 slots.
    """
    out = {}

    for i in range(slot_count):
        val = ""

        if isinstance(obj, dict):
            val = obj.get(str(i), obj.get(i, ""))
        elif isinstance(obj, list):
            val = obj[i] if i < len(obj) else ""

        if clean_suffixes:
            val = clean_val(val)
        elif val is None:
            val = ""
        else:
            val = str(val)

        out[str(i)] = val

    return out


def _metric_dict_from_any(obj, slot_count: int = GPC_SLOT_COUNT) -> dict:
    """
    Converts list or dict metric selections into web metric_cols dict.
    Does NOT strip suffixes because metric names are labels, not numeric fields.
    """
    out = {}

    for i in range(slot_count):
        val = ""

        if isinstance(obj, dict):
            val = obj.get(str(i), obj.get(i, ""))
        elif isinstance(obj, list):
            val = obj[i] if i < len(obj) else ""

        out[str(i)] = "" if val is None else str(val)

    return out


def _normalize_web_gpc_state(web_state: dict, gpc_tickers: list[str]) -> dict:
    """
    Handles old/new web-shaped GPC states directly.
    This prevents dict keys like "0", "1", "2" from being misread as values.
    """
    if not web_state:
        return {}

    out = copy.deepcopy(web_state)

    out["num_multiples"] = out.get("num_multiples", 6)
    out["basis_mode"] = out.get("basis_mode", out.get("last_basis_mode", "BEV"))
    out["dloc"] = out.get("dloc", "19.4%")
    out["control_premium"] = out.get("control_premium", "24.0%")
    out["nwc"] = out.get("nwc", "0")
    out["non_op"] = out.get("non_op", "0")

    out["metric_cols"] = _metric_dict_from_any(out.get("metric_cols", {}))
    out["selected_low"] = _slot_dict_from_any(out.get("selected_low", {}), clean_suffixes=True)
    out["selected_high"] = _slot_dict_from_any(out.get("selected_high", {}), clean_suffixes=True)
    out["weights"] = _slot_dict_from_any(out.get("weights", {}), clean_suffixes=True)

    # Exclusions
    if isinstance(out.get("exclude_map"), dict):
        existing = out.get("exclude_map") or {}
        out["exclude_map"] = {
            ticker: bool(existing.get(ticker, False))
            for ticker in gpc_tickers[:GPC_EXCLUSION_COUNT]
        }
    else:
        excl_rows = out.get("excluded_rows", [])
        out["exclude_map"] = {
            ticker: bool(excl_rows[i]) if isinstance(excl_rows, list) and i < len(excl_rows) else False
            for i, ticker in enumerate(gpc_tickers[:GPC_EXCLUSION_COUNT])
        }

    # Dual-basis memory
    basis_state = out.get("basis_state") or {}
    normalized_basis_state = {}

    for basis in ["BEV", "EQUITY"]:
        b = basis_state.get(basis, {}) or {}
        normalized_basis_state[basis] = {
            "metric_cols": _metric_dict_from_any(b.get("metric_cols", {})),
            "selected_low": _slot_dict_from_any(b.get("selected_low", {}), clean_suffixes=True),
            "selected_high": _slot_dict_from_any(b.get("selected_high", {}), clean_suffixes=True),
            "weights": _slot_dict_from_any(b.get("weights", {}), clean_suffixes=True),
        }

    out["basis_state"] = normalized_basis_state

    return out


def gpc_to_web(desk_state: dict, gpc_tickers: list[str]) -> dict:
    if not desk_state:
        return {}

    # Important:
    # Some existing web-created files are already web-shaped.
    # Do NOT run desktop-list conversion on those, or dict keys "0", "1", "2"
    # become fake values.
    if not _is_desktop_gpc_shape(desk_state):
        return _normalize_web_gpc_state(desk_state, gpc_tickers)

    def clean_dict(lst):
        return _slot_dict_from_any(lst, clean_suffixes=True)

    web_state = {
        "num_multiples": desk_state.get("num_multiples", 6),
        "basis_mode": desk_state.get("last_basis_mode", desk_state.get("basis_mode", "BEV")),
        "dloc": desk_state.get("dloc", "19.4%"),
        "control_premium": desk_state.get("control_premium", "24.0%"),
        "nwc": desk_state.get("nwc", "0"),
        "non_op": desk_state.get("non_op", "0"),
    }

    # Exclusion list -> ticker map
    exclude_map = {}
    excl_rows = desk_state.get("excluded_rows", [])
    for i, ticker in enumerate(gpc_tickers[:GPC_EXCLUSION_COUNT]):
        exclude_map[ticker] = bool(excl_rows[i]) if isinstance(excl_rows, list) and i < len(excl_rows) else False
    web_state["exclude_map"] = exclude_map

    # Top-level active basis values
    web_state["metric_cols"] = _metric_dict_from_any(desk_state.get("metric_selections", []))
    web_state["selected_low"] = clean_dict(desk_state.get("selected_low", []))
    web_state["selected_high"] = clean_dict(desk_state.get("selected_high", []))
    web_state["weights"] = clean_dict(desk_state.get("weights", []))

    # Dual-basis memory
    per_basis = desk_state.get("per_basis_state", {}) or {}
    basis_state = {}

    for basis in ["BEV", "EQUITY"]:
        desk_b = per_basis.get(basis, {}) or {}
        basis_state[basis] = {
            "metric_cols": _metric_dict_from_any(desk_b.get("metrics", [])),
            "selected_low": clean_dict(desk_b.get("low", [])),
            "selected_high": clean_dict(desk_b.get("high", [])),
            "weights": clean_dict(desk_b.get("weights", [])),
        }

    web_state["basis_state"] = basis_state

    # Retain extension variables
    skip = {
        "per_basis_state",
        "metric_selections",
        "excluded_rows",
        "last_basis_mode",
        "selected_low",
        "selected_high",
        "weights",
    }

    for k, v in desk_state.items():
        if k not in web_state and k not in skip:
            web_state[k] = copy.deepcopy(v)

    return web_state


def gpc_to_desktop(web_state: dict, gpc_tickers: list[str]) -> dict:
    if not web_state:
        return {}

    def to_list(dct, suffix=""):
        lst = [""] * 7
        for i in range(7):
            val = dct.get(str(i), "")
            lst[i] = format_val(val, suffix)
        return lst

    desk_state = {
        "num_multiples": web_state.get("num_multiples", 6),
        "dloc": web_state.get("dloc", "19.4%"),
        "control_premium": web_state.get("control_premium", "24.0%"),
        "last_basis_mode": web_state.get("basis_mode", "BEV"),
    }

    # Exclusion map conversion
    exclude_map = web_state.get("exclude_map", {})
    excl_rows = [False] * 15
    for i, ticker in enumerate(gpc_tickers[:15]):
        excl_rows[i] = bool(exclude_map.get(ticker, False))
    desk_state["excluded_rows"] = excl_rows

    # Top-level variables
    desk_state["metric_selections"] = [web_state.get("metric_cols", {}).get(str(i), "") for i in range(7)]
    desk_state["selected_low"] = to_list(web_state.get("selected_low", {}), "x")
    desk_state["selected_high"] = to_list(web_state.get("selected_high", {}), "x")
    desk_state["weights"] = to_list(web_state.get("weights", {}), "%")

    # Dual-basis model values
    basis_state = web_state.get("basis_state", {})
    per_basis = {}
    for basis in ["BEV", "EQUITY"]:
        web_b = basis_state.get(basis, {})
        per_basis[basis] = {
            "metrics": [web_b.get("metric_cols", {}).get(str(i), "") for i in range(7)],
            "low": to_list(web_b.get("selected_low", {}), "x"),
            "high": to_list(web_b.get("selected_high", {}), "x"),
            "weights": to_list(web_b.get("weights", {}), "%"),
            "visited": True
        }
    desk_state["per_basis_state"] = per_basis

    # Retain extension variables
    for k, v in web_state.items():
        if k not in desk_state and k not in ["metric_cols", "basis_state", "exclude_map", "basis_mode"]:
            desk_state[k] = copy.deepcopy(v)

    return desk_state


def dashboard_to_web(desk_dash: dict) -> dict:
    return copy.deepcopy(desk_dash)


def dashboard_to_desktop(web_dash: dict) -> dict:
    desk_dash = copy.deepcopy(web_dash)
    gpc_w = desk_dash.get("gpc_weights", [])
    if isinstance(gpc_w, list):
        if len(gpc_w) < 7:
            gpc_w += [""] * (7 - len(gpc_w))
        elif len(gpc_w) > 7:
            gpc_w = gpc_w[:7]
        desk_dash["gpc_weights"] = gpc_w
    return desk_dash


def nwc_to_web(desk_nwc: dict) -> dict:
    web_nwc = copy.deepcopy(desk_nwc)
    pct = web_nwc.get("selected_pct")
    if pct and isinstance(pct, str) and not pct.endswith("%"):
        web_nwc["selected_pct"] = pct + "%"
    return web_nwc


def nwc_to_desktop(web_nwc: dict) -> dict:
    desk_nwc = copy.deepcopy(web_nwc)
    pct = desk_nwc.get("selected_pct")
    if pct and isinstance(pct, str) and pct.endswith("%"):
        desk_nwc["selected_pct"] = pct[:-1].strip()
    return desk_nwc


def wacc_to_web(desk_wacc: dict) -> dict:
    web_wacc = copy.deepcopy(desk_wacc)
    csrp = web_wacc.get("csrp")
    if csrp is not None:
        s = str(csrp).strip()
        if s.endswith("%"):
            s = s[:-1].strip()
            try:
                f = float(s)
                s = str(int(f)) if f.is_integer() else f"{f:.1f}"
            except ValueError:
                pass
        web_wacc["csrp"] = s
    return web_wacc


def wacc_to_desktop(web_wacc: dict) -> dict:
    desk_wacc = copy.deepcopy(web_wacc)
    csrp = desk_wacc.get("csrp")
    if csrp is not None:
        s = str(csrp).strip()
        if not s.endswith("%"):
            try:
                f = float(s)
                s = f"{f:.1f}%"
            except ValueError:
                pass
        desk_wacc["csrp"] = s
    return desk_wacc


# ==========================================
# RUNTIME DERIVED CACHE STRIPPER
# ==========================================

def strip_derived_caches(session_data: dict) -> dict:
    """Removes live calculated output metrics before save to keep files small."""
    cleaned = copy.deepcopy(session_data)

    if "wacc_page_state" in cleaned and isinstance(cleaned["wacc_page_state"], dict):
        for k in ["wacc_value", "ke_value", "after_tax_kd", "we", "wd"]:
            cleaned["wacc_page_state"].pop(k, None)

    if "nwc_page_state" in cleaned and isinstance(cleaned["nwc_page_state"], dict):
        for k in ["surplus_deficit", "actual_nwc", "normalized_nwc", "nwc_by_period", "changes_in_nwc", "nwc_pct_by_period"]:
            cleaned["nwc_page_state"].pop(k, None)

    if "debt_page_state" in cleaned and isinstance(cleaned["debt_page_state"], dict):
        for k in ["interest_expense_by_period", "ending_debt_by_period", "net_borrowing_by_period", "projected_interest"]:
            cleaned["debt_page_state"].pop(k, None)

    if "dcf_page_state" in cleaned and isinstance(cleaned["dcf_page_state"], dict):
        for k in ["fv_base", "sum_pv_fcf", "pv_residual", "discount_rate", "residual_revenue", "effective_cash_flows_to"]:
            cleaned["dcf_page_state"].pop(k, None)

    return cleaned


# ==========================================
# MAIN CORE ADAPTER INTERFACES
# ==========================================

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
    pi = dict_to_project_inputs(session_data or {})
    pf = PrivateFinancials(
        is_data=(session_data or {}).get("private_is_data", {}),
        bs_data=(session_data or {}).get("private_bs_data", {}),
    )

    # 1. Clean live cached outputs before save
    clean_session_data = strip_derived_caches(session_data or {})

    # 2. Extract and translate Web states to Desktop states
    web_gpc = clean_session_data.get("gpc_page_state", {})
    desk_gpc = gpc_to_desktop(web_gpc, pi.gpc_tickers)

    web_dash = clean_session_data.get("dashboard_page_state", {})
    desk_dash = dashboard_to_desktop(web_dash)

    web_nwc = clean_session_data.get("nwc_page_state", {})
    desk_nwc = nwc_to_desktop(web_nwc)

    web_wacc = clean_session_data.get("wacc_page_state", {})
    desk_wacc = wacc_to_desktop(web_wacc)

    # 3. Call standard core saver with updated states
    return _core_save_session(
        project_inputs=pi,
        private_financials=pf,
        gt_page_state=clean_session_data.get("gt_page_state", {}),
        gpc_page_state=desk_gpc,
        projection_page_state=clean_session_data.get("projection_page_state", {}),
        wacc_page_state=desk_wacc,
        dcf_page_state=clean_session_data.get("dcf_page_state", {}),
        nwc_page_state=desk_nwc,
        dashboard_page_state=desk_dash,
        debt_page_state=clean_session_data.get("debt_page_state", {}),
        source_data_results=source_results or {},
        filepath=filepath,
    )


def load_session_to_stores(filepath: Path) -> tuple[dict, dict, str]:
    payload = _core_load_session(filepath)
    pi_raw = payload["project_inputs_raw"]
    pf = payload["private_financials"]

    session_dict = dict(pi_raw)
    session_dict["private_is_data"] = pf.is_data
    session_dict["private_bs_data"] = pf.bs_data
    session_dict["gt_page_state"] = payload.get("gt_page_state") or {}

    gpc_tickers = session_dict.get("gpc_tickers", [])

    # Translate Desktop structures to Web shapes on load
    raw_gpc = payload.get("gpc_page_state") or {}
    session_dict["gpc_page_state"] = gpc_to_web(raw_gpc, gpc_tickers)

    raw_dash = payload.get("dashboard_page_state") or {}
    session_dict["dashboard_page_state"] = dashboard_to_web(raw_dash)

    raw_nwc = payload.get("nwc_page_state") or {}
    session_dict["nwc_page_state"] = nwc_to_web(raw_nwc)

    raw_wacc = payload.get("wacc_page_state") or {}
    session_dict["wacc_page_state"] = wacc_to_web(raw_wacc)

    session_dict["projection_page_state"] = payload["projection_page_state"]
    session_dict["dcf_page_state"] = payload["dcf_page_state"]
    session_dict["debt_page_state"] = payload["debt_page_state"]
    session_dict["disk_session_name"] = Path(filepath).stem

    return session_dict, payload["source_data_results"], payload["saved_at"]


def list_available_sessions() -> list:
    sessions = _core_list_sessions()
    return [
        {"path": str(s["path"]), "name": s["name"], "saved_at": s["saved_at"]}
        for s in sessions
    ]