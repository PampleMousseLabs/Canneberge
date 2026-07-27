from typing import Optional, List, Dict

import math

from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QScrollArea,
    QButtonGroup,
    QPushButton,
    QFrame,
)
from PyQt6.QtCore import Qt

from Canneberge.app_state import ProjectInputs, PrivateFinancials, IS_LINES, BS_LINES

BOLD_STYLE = "font-weight: bold;"
SECTION_STYLE = "font-weight: bold; font-size: 11px;"


def _fmt(value) -> str:
    if value is None or str(value).lower() in ("nan", "none", "-"):
        return "-"
    try:
        f = float(str(value).replace(",",""))
        return f"{f:,.0f}"
    except: return "-"


def _make_hrule() -> QFrame:
    line = QFrame()
    line.setFrameShape(QFrame.Shape.HLine)
    line.setFrameShadow(QFrame.Shadow.Sunken)
    return line

def _parse_val(value) -> Optional[float]:
    if value is None or str(value).strip().lower() in ("", "-", "nan", "none"):
        return None
    try:
        v = float(str(value).replace(",", ""))
        if math.isnan(v) or math.isinf(v):
            return None
        return v
    except (ValueError, TypeError):
        return None

# Map our IS/BS keys to StockAnalysis line item names
SA_KEY_MAP = {
    "revenue": "revenue",
    "cogs": "cost of revenue",
    "gross_profit": "gross profit",
    "sga": "selling, general & admin",
    "rd": "research & development",
    "other_operating": "other operating expenses",
    "operating_expenses": "total operating expenses",
    "ebitda": "ebitda",
    "depreciation": "depreciation & amortization expenses",
    "ebit": "ebit",
    "interest_expense": "interest expense",
    "interest_income": "interest income",
    "other_income": "other non-operating income (expense)",
    "pretax_income": "pretax income",
    "taxes": "provision for income taxes",
    "net_income": "net income",
    "capex": "capital expenditures",
    "cash": "cash & equivalents",
    "st_investments": "short-term investments",
    "accounts_receivable": "accounts receivable",
    "inventory": "inventory",
    "other_current_assets": "other current assets",
    "total_current_assets": "total current assets",
    "ppe": "net property, plant & equipment",
    "goodwill": "goodwill",
    "intangible_assets": "other intangible assets",
    "lt_investments": "long-term investments",
    "other_lt_assets": "other long-term assets",
    "total_assets": "total assets",
    "st_debt": "short-term debt",
    "current_ltd": "current portion of long-term debt",
    "current_leases": "current portion of long-term leases",
    "accounts_payable": "accounts payable",
    "accrued_expenses": "accrued expenses",
    "unearned_revenue": "unearned revenue",
    "other_current_liab": "other current liabilities",
    "total_current_liab": "total current liabilities",
    "lt_debt": "long-term debt",
    "lt_leases": "long-term leases",
    "lt_operating_leases": "long term portion of operating leases",
    "other_lt_liab": "other long-term liabilities",
    "total_liabilities": "total liabilities",
    "preferred_stock": "preferred stock",
    "common_stock": "common stock",
    "apic": "additional paid-in capital",
    "treasury_stock": "treasury stock",
    "aoci": "accumulated other comprehensive income",
    "minority_interest": "minority interest",
    "retained_earnings": "retained earnings",
    "placeholder2": "",  # no public equivalent; private-input only
    "placeholder": "",  # demo row only; no public equivalent, always shows "-"
    "total_equity": "shareholders' equity",
    "total_liab_equity": "total liabilities & equity",
}


class SubjectFinancialsPage(QWidget):
    """
    Read-only display of subject company IS and BS.
    - If Publicly Traded: shows StockAnalysis data pulled for subject ticker
    - If Private: shows data entered in PrivateFinancialsInputPage
    Always reflects current state — no editing here.
    """

    def __init__(self, get_project_inputs_callback,
                 get_stockanalysis_results_callback,
                 get_private_financials_callback):
        super().__init__()
        self.get_project_inputs = get_project_inputs_callback
        self.get_stockanalysis_results = get_stockanalysis_results_callback
        self.get_private_financials = get_private_financials_callback

        self._current_statement = "IS"
        self._build_ui()

    def _build_ui(self):
        outer = QVBoxLayout()

        # Top bar: IS / BS toggle
        top_bar = QHBoxLayout()

        self.stmt_group = QButtonGroup(self)
        self.stmt_group.setExclusive(True)

        self.btn_is = QPushButton("IS")
        self.btn_bs = QPushButton("BS")

        for btn, stmt in [(self.btn_is, "IS"), (self.btn_bs, "BS")]:
            btn.setCheckable(True)
            btn.clicked.connect(
                lambda checked, s=stmt: self._switch_statement(s)
            )
            self.stmt_group.addButton(btn)
            top_bar.addWidget(btn)

        self.btn_is.setChecked(True)
        top_bar.addStretch()

        self.status_label = QLabel("")
        top_bar.addWidget(self.status_label)
        outer.addLayout(top_bar)

        # Scroll area
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        outer.addWidget(self._scroll)

        self.setLayout(outer)
        self.refresh()

    def _switch_statement(self, stmt: str):
        self._current_statement = stmt
        self.refresh()

    def refresh(self):
        """Rebuild display from current data."""
        inputs = self.get_project_inputs()

        if inputs.is_publicly_traded:
            self.status_label.setText(
                f"Source: StockAnalysis ({inputs.subject_ticker})"
            )
            widget = self._build_public_view(inputs)
        else:
            self.status_label.setText(
                "Source: Private Company Input Form"
            )
            widget = self._build_private_view(inputs)

        self._scroll.setWidget(widget)

    def _get_periods(self, inputs: ProjectInputs) -> List[str]:
        """Historical periods only for display (no projected in read-only view)."""
        return inputs.historical_period_columns + ["TTM"]

    def _build_public_view(self, inputs: ProjectInputs) -> QWidget:
        """Build read-only grid from StockAnalysis results."""
        container = QWidget()
        grid = QGridLayout()
        grid.setSpacing(2)
        grid.setContentsMargins(8, 8, 8, 8)

        results = self.get_stockanalysis_results()
        stmt_results = results.get(
            self._current_statement, []
        ) if results else []

        ticker = inputs.subject_ticker.lower()

        # Filter to subject ticker only
        subject_rows = [
            r for r in stmt_results
            if str(r.get("Ticker", "")).lower() == ticker
        ]

        lines = IS_LINES if self._current_statement == "IS" else BS_LINES
        periods = self._get_periods(inputs)

        # Header
        grid.addWidget(QLabel("Line Item"), 0, 0)
        for col_idx, period in enumerate(periods):
            lbl = QLabel(period)
            lbl.setStyleSheet(BOLD_STYLE)
            lbl.setAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            grid.addWidget(lbl, 0, col_idx + 1)

        grid.setColumnStretch(0, 2)
        for i in range(len(periods)):
            grid.setColumnMinimumWidth(i + 1, 90)

        # Build lookup: line_item_lower -> {period -> value}
        lookup: Dict[str, Dict[str, str]] = {}
        for row in subject_rows:
            key = str(row.get("Line Item", "")).strip().lower()
            lookup[key] = {
                k: v for k, v in row.items()
                if k not in ("Ticker", "Key", "Line Item")
            }

        
        for row_idx, (key, label, is_calc, bold) in enumerate(lines):
            row = row_idx + 1
            name_lbl = QLabel(label)
            if bold:
                name_lbl.setStyleSheet(BOLD_STYLE)
            grid.addWidget(name_lbl, row, 0)

            sa_key = SA_KEY_MAP.get(key, "").lower()
            row_data = lookup.get(sa_key, {})

            for col_idx, period in enumerate(periods):
                val = row_data.get(period, "")
                val_lbl = QLabel(_fmt(val) if val else "-")
                val_lbl.setAlignment(
                    Qt.AlignmentFlag.AlignRight |
                    Qt.AlignmentFlag.AlignVCenter
                )
                if bold:
                    val_lbl.setStyleSheet(BOLD_STYLE)
                grid.addWidget(val_lbl, row, col_idx + 1)

        grid.setRowStretch(len(lines) + 2, 1)
        container.setLayout(grid)
        return container

    def _build_private_view(self, inputs: ProjectInputs) -> QWidget:
        """Build read-only grid from PrivateFinancials dataclass."""
        container = QWidget()
        grid = QGridLayout()
        grid.setSpacing(2)
        grid.setContentsMargins(8, 8, 8, 8)

        pf = self.get_private_financials()
        lines = IS_LINES if self._current_statement == "IS" else BS_LINES
        periods = self._visible_private_periods(inputs)

        # total_equity/total_liab_equity are marked is_calc=True in BS_LINES,
        # but PrivateFinancials only stores raw manually-entered values —
        # nothing writes a correct total_equity into pf.bs_data upstream.
        # Compute both here instead of doing a flat get_bs() lookup.
        equity_component_keys = [
            "preferred_stock", "common_stock", "apic",
            "treasury_stock", "aoci", "minority_interest",
            "retained_earnings", "common_equity", "placeholder",
        ]

        def _computed_bs_value(key: str, period: str):
            if key == "total_equity":
                total = 0.0
                any_present = False
                for k in equity_component_keys:
                    v = pf.get_bs(k, period)
                    if v is not None:
                        total += v
                        any_present = True
                return total if any_present else None
            if key == "total_liab_equity":
                liab = pf.get_bs("total_liabilities", period)
                equity = _computed_bs_value("total_equity", period)
                if liab is None and equity is None:
                    return None
                return (liab or 0.0) + (equity or 0.0)
            return pf.get_bs(key, period)

        # Header
        grid.addWidget(QLabel("Line Item"), 0, 0)
        for col_idx, period in enumerate(periods):
            lbl = QLabel(period)
            lbl.setStyleSheet(BOLD_STYLE)
            lbl.setAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            grid.addWidget(lbl, 0, col_idx + 1)

        grid.setColumnStretch(0, 2)
        for i in range(len(periods)):
            grid.setColumnMinimumWidth(i + 1, 90)

        for row_idx, (key, label, is_calc, bold) in enumerate(lines):
            row = row_idx + 1
            name_lbl = QLabel(label)
            if bold:
                name_lbl.setStyleSheet(BOLD_STYLE)
            grid.addWidget(name_lbl, row, 0)

            for col_idx, period in enumerate(periods):
                if self._current_statement == "IS":
                    val = pf.get_is(key, period)
                elif key in ("total_equity", "total_liab_equity"):
                    val = _computed_bs_value(key, period)
                else:
                    val = pf.get_bs(key, period)

                val_lbl = QLabel(_fmt(val) if val is not None else "-")
                val_lbl.setAlignment(
                    Qt.AlignmentFlag.AlignRight |
                    Qt.AlignmentFlag.AlignVCenter
                )
                if bold:
                    val_lbl.setStyleSheet(BOLD_STYLE)
                grid.addWidget(val_lbl, row, col_idx + 1)

        grid.setRowStretch(len(lines) + 2, 1)
        container.setLayout(grid)
        return container

    def _visible_private_periods(self, inputs: ProjectInputs) -> List[str]:
        from dateutil.relativedelta import relativedelta
        from datetime import datetime

        hist = inputs.historical_period_columns

        forward = ["TTM", "NFY", "NFY+1", "NFY+2"]

        # YTD labels
        lfq_str = inputs.last_fiscal_quarter
        lfq = None
        for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m-%d-%Y"):
            try:
                lfq = datetime.strptime(lfq_str.strip(), fmt)
                break
            except ValueError:
                pass

        if lfq:
            prior = lfq - relativedelta(years=1)
            ytd = [
                f"YTD {prior.month}/{prior.day}/{prior.year}",
                f"YTD {lfq.month}/{lfq.day}/{lfq.year}",
            ]
        else:
            ytd = ["YTD Prior", "YTD Current"]

        return hist + forward + ytd

    def get_subject_debt(self) -> float:
        """Helper for GT page."""
        inputs = self.get_project_inputs()
        res = 0.0
        keys = ["st_debt", "current_ltd", "lt_debt"]
        if inputs.is_private:
            pf = self.get_private_financials()
            for k in keys: res += (pf.get_bs(k, "TTM") or 0.0)
        else:
            sa = self.get_stockanalysis_results().get("BS", [])
            tick = inputs.subject_ticker.lower()
            for k in keys:
                sa_key = SA_KEY_MAP.get(k)
                for r in sa:
                    if str(r.get("Ticker")).lower() == tick and str(r.get("Line Item")).lower() == sa_key:
                        try: res += float(str(r.get("TTM")).replace(",",""))
                        except: pass
        return res

    def get_historical_line_values(self, key: str, statement: str = "IS") -> Dict[str, Optional[float]]:
        """
        Returns {period_label: float_or_None} for the given line-item key,
        across historical periods + TTM (LFY-N ... LFY, TTM).

        Resolves via StockAnalysis (public) or PrivateFinancials (private) —
        the exact same branching used by _build_public_view/_build_private_view.

        This is the single source of truth for other pages (Projection Module,
        GT, GPC, future NWC/DCF) needing subject company historicals as raw
        floats rather than display strings. Don't duplicate the public/private
        resolution logic elsewhere — call this instead.
        """
        inputs = self.get_project_inputs()
        periods = inputs.historical_period_columns + ["TTM"]
        result: Dict[str, Optional[float]] = {}

        if inputs.is_publicly_traded:
            results = self.get_stockanalysis_results()
            stmt_results = results.get(statement, []) if results else []
            ticker = inputs.subject_ticker.lower()
            subject_rows = [
                r for r in stmt_results
                if str(r.get("Ticker", "")).lower() == ticker
            ]
            sa_key = SA_KEY_MAP.get(key, "").lower()
            row_data = {}
            for row in subject_rows:
                if str(row.get("Line Item", "")).strip().lower() == sa_key:
                    row_data = {
                        k: v for k, v in row.items()
                        if k not in ("Ticker", "Key", "Line Item")
                    }
                    break
            for period in periods:
                result[period] = _parse_val(row_data.get(period, ""))
        else:
            pf = self.get_private_financials()
            for period in periods:
                if statement == "IS":
                    result[period] = pf.get_is(key, period)
                else:
                    result[period] = pf.get_bs(key, period)

        return result    