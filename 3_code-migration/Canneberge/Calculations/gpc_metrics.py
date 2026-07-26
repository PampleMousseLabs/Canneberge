"""
GPC_METRICS is the catalogue of every multiple the GPC page can compute.

Each entry is (display_name, period, line_key):
  - display_name: shown in the dropdown, e.g. "NFY+2 EBITDA"
  - period:        one of the period labels already used across the app
                    (LFY-4 ... LFY, TTM, NFY, NFY+1, NFY+2). Must match
                    the period keys StockAnalysis data is stored under.
  - line_key:       the SA_KEY_MAP key from subject_financials_page.py
                    (e.g. "revenue", "ebitda", "ebit"). Reuses the same
                    vocabulary on purpose — one concept, one name, even
                    though it currently has to be typed in two files.

To add a new multiple (e.g. forward EBIT, or a historical year), add one
tuple here. Nothing else needs to change — the dropdown, the calculation
module, and the page all read from this list.

"Custom Multiple" is NOT in this list. It's a UI sentinel handled
separately in gpc_page.py, since it has no period/line_key — the value
is typed in directly rather than computed.
"""

from typing import NamedTuple


class GPCMetric(NamedTuple):
    display_name: str
    period: str
    line_key: str


GPC_METRICS: list[GPCMetric] = [
    GPCMetric("TTM Revenue",     "TTM",   "revenue"),
    GPCMetric("TTM EBITDA",      "TTM",   "ebitda"),
    GPCMetric("TTM EBIT",        "TTM",   "ebit"),
    GPCMetric("NFY Revenue",     "NFY",   "revenue"),
    GPCMetric("NFY EBITDA",      "NFY",   "ebitda"),
    GPCMetric("NFY+1 Revenue",   "NFY+1", "revenue"),
    GPCMetric("NFY+1 EBITDA",    "NFY+1", "ebitda"),
    GPCMetric("NFY+2 Revenue",   "NFY+2", "revenue"),
    GPCMetric("NFY+2 EBITDA",    "NFY+2", "ebitda"),
]

CUSTOM_MULTIPLE_LABEL = "Custom Multiple"


def dropdown_options() -> list[str]:
    """Full list of dropdown choices: every catalogued metric + Custom Multiple."""
    return [m.display_name for m in GPC_METRICS] + [CUSTOM_MULTIPLE_LABEL]


def get_metric(display_name: str) -> "GPCMetric | None":
    """Look up a GPCMetric by its display name. Returns None for Custom Multiple
    or any name not in the catalogue — callers must check for that."""
    for m in GPC_METRICS:
        if m.display_name == display_name:
            return m
    return None