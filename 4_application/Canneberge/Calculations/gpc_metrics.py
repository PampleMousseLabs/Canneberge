"""
GPC_METRICS is the catalogue of every multiple the GPC page can compute.
All multiples evaluate aggregate Market Cap ($) or BEV ($) against aggregate line items ($).
No per-share math anywhere — StockAnalysis and MarketScreener return total dollar amounts.
"""

from typing import NamedTuple


class GPCMetric(NamedTuple):
    display_name: str
    period: str
    line_key: str
    bev_allowed: bool = True
    equity_allowed: bool = True


GPC_METRICS: list[GPCMetric] = [
    # --- BEV & Equity Allowed ---
    GPCMetric("TTM Revenue",     "TTM",   "revenue",      bev_allowed=True,  equity_allowed=True),
    GPCMetric("NFY Revenue",     "NFY",   "revenue",      bev_allowed=True,  equity_allowed=True),
    GPCMetric("NFY+1 Revenue",   "NFY+1", "revenue",      bev_allowed=True,  equity_allowed=True),
    GPCMetric("NFY+2 Revenue",   "NFY+2", "revenue",      bev_allowed=True,  equity_allowed=True),

    # --- BEV Mode Only ---
    GPCMetric("TTM EBITDA",      "TTM",   "ebitda",       bev_allowed=True,  equity_allowed=False),
    GPCMetric("TTM EBIT",        "TTM",   "ebit",         bev_allowed=True,  equity_allowed=False),
    GPCMetric("NFY Adjusted EBITDA",   "NFY",   "ebitda", bev_allowed=True,  equity_allowed=False),
    GPCMetric("NFY+1 Adjusted EBITDA", "NFY+1", "ebitda", bev_allowed=True,  equity_allowed=False),
    GPCMetric("NFY+2 Adjusted EBITDA", "NFY+2", "ebitda", bev_allowed=True,  equity_allowed=False),

    # --- Equity Mode Only (Market Cap / Aggregate Metric $) ---
    GPCMetric("TTM Net Income",  "TTM",   "net_income",   bev_allowed=False, equity_allowed=True),
    GPCMetric("TTM Book Equity", "TTM",   "total_equity", bev_allowed=False, equity_allowed=True),
    GPCMetric("NFY Net Income",  "NFY",   "net_income",   bev_allowed=False, equity_allowed=True),
    GPCMetric("NFY+1 Net Income","NFY+1", "net_income",   bev_allowed=False, equity_allowed=True),
    GPCMetric("NFY+2 Net Income","NFY+2", "net_income",   bev_allowed=False, equity_allowed=True),
]

CUSTOM_MULTIPLE_LABEL = "Custom Multiple"


def dropdown_options(basis_mode: str = "BEV") -> list[str]:
    is_equity = (basis_mode == "EQUITY")
    valid_metrics = [
        m.display_name for m in GPC_METRICS
        if (m.equity_allowed if is_equity else m.bev_allowed)
    ]
    return valid_metrics + [CUSTOM_MULTIPLE_LABEL]


def get_metric(display_name: str) -> "GPCMetric | None":
    for m in GPC_METRICS:
        if m.display_name == display_name:
            return m
    return None


def convert_metric_on_toggle(old_name: str, to_basis_mode: str) -> str:
    if old_name == CUSTOM_MULTIPLE_LABEL:
        return CUSTOM_MULTIPLE_LABEL

    valid_options = dropdown_options(to_basis_mode)
    if old_name in valid_options:
        return old_name

    if to_basis_mode == "EQUITY":
        conversion_map = {
            "TTM EBITDA": "TTM Net Income",
            "TTM EBIT": "TTM Net Income",
            "NFY Adjusted EBITDA": "NFY Net Income",
            "NFY+1 Adjusted EBITDA": "NFY+1 Net Income",
            "NFY+2 Adjusted EBITDA": "NFY+2 Net Income",
        }
        return conversion_map.get(old_name, valid_options[0])
    else:
        conversion_map = {
            "TTM Net Income": "TTM EBITDA",
            "TTM Book Equity": "TTM EBITDA",
            "NFY Net Income": "NFY Adjusted EBITDA",
            "NFY+1 Net Income": "NFY+1 Adjusted EBITDA",
            "NFY+2 Net Income": "NFY+2 Adjusted EBITDA",
        }
        return conversion_map.get(old_name, valid_options[0])