from typing import Optional, Dict
from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QWidget,
    QButtonGroup,
)
from PyQt6.QtCore import Qt
from datetime import datetime
from dateutil.relativedelta import relativedelta

from Canneberge.app_state import PrivateFinancials, IS_LINES, BS_LINES

INPUT_STYLE = "background-color: #dce9f7; color: #1a4a8a;"
BOLD_STYLE = "font-weight: bold;"

def _parse_float(text: str) -> Optional[float]:
    text = str(text).strip().replace(",", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _fmt(value: Optional[float]) -> str:
    if value is None:
        return ""
    return f"{value:,.0f}"


def _parse_lfq(lfq_str: str) -> Optional[datetime]:
    """Parse last fiscal quarter date string."""
    if not lfq_str:
        return None
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m-%d-%Y"):
        try:
            return datetime.strptime(lfq_str.strip(), fmt)
        except ValueError:
            pass
    return None


def _ytd_labels(lfq_str: str) -> tuple:
    """
    Returns (ytd_prior_label, ytd_current_label) based on LFQ.
    e.g. LFQ = 3/31/2026 ->
        ytd_prior   = "YTD 3/31/2025"
        ytd_current = "YTD 3/31/2026"
    """
    lfq = _parse_lfq(lfq_str)
    if lfq is None:
        return ("YTD Prior", "YTD Current")

    prior = lfq - relativedelta(years=1)
    return (
        f"YTD {prior.strftime('%-m/%-d/%Y').replace('%-m', str(prior.month)).replace('%-d', str(prior.day))}",
        f"YTD {lfq.strftime('%-m/%-d/%Y').replace('%-m', str(lfq.month)).replace('%-d', str(lfq.day))}",
    )


def _format_ytd_label(lfq: datetime, years_offset: int = 0) -> str:
    """Format a YTD column label from a datetime."""
    d = lfq - relativedelta(years=years_offset)
    return f"YTD {d.month}/{d.day}/{d.year}"


class PrivateFinancialsInputPage(QDialog):
    """
    Modal dialog for entering private company IS and BS data.
    Only accessible when CompanyStatus = Private Company.

    Column order:
        LFY-N ... LFY-1, LFY, TTM (calculated), NFY, NFY+1, NFY+2,
        YTD[prior], YTD[current]

    TTM = LFY - YTD_prior + YTD_current
    """

    def __init__(self, private_financials: PrivateFinancials,
                 hist_years: int = 5,
                 last_fiscal_quarter: str = "",
                 parent=None):
        super().__init__(parent)
        self.setWindowTitle("Private Company Financial Data")
        self.setMinimumSize(1400, 700)

        self._hist_years = hist_years
        self._lfq_str = last_fiscal_quarter
        self._lfq = _parse_lfq(last_fiscal_quarter)

        # Work on a copy — only commit on Save
        self._working = PrivateFinancials(
            is_data={k: dict(v) for k, v in private_financials.is_data.items()},
            bs_data={k: dict(v) for k, v in private_financials.bs_data.items()},
        )
        self._saved_financials = private_financials
        self._current_statement = "IS"

        # Input widgets: {stmt: {line_key: {period: QLineEdit}}}
        self._inputs: Dict[str, Dict[str, Dict[str, QLineEdit]]] = {
            "IS": {}, "BS": {},
        }
        # Calc display labels: {stmt: {line_key: {period: QLabel}}}
        self._calc_labels: Dict[str, Dict[str, Dict[str, QLabel]]] = {
            "IS": {}, "BS": {},
        }

        self._build_ui()
        self._load_data()

    def _get_periods(self) -> list:
        """
        Returns ordered period column labels.
        Historical: LFY-N ... LFY-1, LFY
        Then: TTM (calculated), NFY, NFY+1, NFY+2
        Then: YTD prior, YTD current (far right)
        """
        hist = []
        for i in range(self._hist_years, 0, -1):
            hist.append(f"LFY-{i}")
        hist.append("LFY")

        forward = ["TTM", "NFY", "NFY+1", "NFY+2"]

        ytd_prior, ytd_current = self._get_ytd_labels()
        ytd = [ytd_prior, ytd_current]

        return hist + forward + ytd

    def _get_ytd_labels(self) -> tuple:
        """Returns (ytd_prior_label, ytd_current_label)."""
        if self._lfq is None:
            return ("YTD Prior", "YTD Current")
        prior = self._lfq - relativedelta(years=1)
        return (
            f"YTD {prior.month}/{prior.day}/{prior.year}",
            f"YTD {self._lfq.month}/{self._lfq.day}/{self._lfq.year}",
        )

    def _is_ttm(self, period: str) -> bool:
        return period == "TTM"

    def _is_ytd(self, period: str) -> bool:
        return period.startswith("YTD")

    def _build_ui(self):
        outer_layout = QVBoxLayout()

        # Top bar
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

        save_btn = QPushButton("Save")
        save_btn.setStyleSheet(
            "background-color: #1a4a8a; color: white; "
            "font-weight: bold; padding: 4px 16px;"
        )
        save_btn.clicked.connect(self._on_save)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)

        top_bar.addWidget(save_btn)
        top_bar.addWidget(cancel_btn)
        outer_layout.addLayout(top_bar)

        # Scroll area with permanent container — never swap widgets,
        # just show/hide so Qt never deletes them
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)

        self._scroll_container = QWidget()
        container_layout = QVBoxLayout()
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)

        self._is_widget = self._build_statement_grid("IS", IS_LINES)
        self._bs_widget = self._build_statement_grid("BS", BS_LINES)

        container_layout.addWidget(self._is_widget)
        container_layout.addWidget(self._bs_widget)
        self._scroll_container.setLayout(container_layout)

        self._scroll.setWidget(self._scroll_container)
        outer_layout.addWidget(self._scroll)

        self.setLayout(outer_layout)

        # IS visible by default, BS hidden
        self._is_widget.setVisible(True)
        self._bs_widget.setVisible(False)

    def _build_statement_grid(self, stmt: str, lines: list) -> QWidget:
        container = QWidget()
        grid = QGridLayout()
        grid.setSpacing(2)
        grid.setContentsMargins(8, 8, 8, 8)

        periods = self._get_periods()
        ytd_prior, ytd_current = self._get_ytd_labels()

        # Header row
        grid.addWidget(QLabel("Line Item"), 0, 0)
        for col_idx, period in enumerate(periods):
            lbl = QLabel(period)
            lbl.setStyleSheet(BOLD_STYLE)
            lbl.setAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            # TTM and YTD headers styled differently to distinguish
            if period == "TTM":
                lbl.setStyleSheet(
                    "font-weight: bold; color: #555555;"
                )
            elif period.startswith("YTD"):
                lbl.setStyleSheet(
                    "font-weight: bold; color: #1a4a8a;"
                )
            grid.addWidget(lbl, 0, col_idx + 1)

        grid.setColumnStretch(0, 2)
        for i in range(len(periods)):
            grid.setColumnMinimumWidth(i + 1, 90)

        # Data rows
        for row_idx, (key, label, is_calc, bold) in enumerate(lines):
            row = row_idx + 1

            name_lbl = QLabel(label)
            if bold:
                name_lbl.setStyleSheet(BOLD_STYLE)
            grid.addWidget(name_lbl, row, 0)

            self._inputs[stmt][key] = {}
            self._calc_labels[stmt][key] = {}

            for col_idx, period in enumerate(periods):
                is_ttm = period == "TTM"
                is_ytd = period.startswith("YTD")

                # TTM is always calculated, never an input
                if is_calc or is_ttm:
                    val_lbl = QLabel("")
                    val_lbl.setAlignment(
                        Qt.AlignmentFlag.AlignRight |
                        Qt.AlignmentFlag.AlignVCenter
                    )
                    style = BOLD_STYLE if bold else ""
                    if is_ttm:
                        style += " color: #555555;"
                    val_lbl.setStyleSheet(style)
                    grid.addWidget(val_lbl, row, col_idx + 1)
                    self._calc_labels[stmt][key][period] = val_lbl
                else:
                    inp = QLineEdit()
                    # YTD columns get same input style but slightly
                    # different border to visually separate
                    if is_ytd:
                        inp.setStyleSheet(
                            "background-color: #dce9f7; "
                            "color: #1a4a8a; "
                            "border: 1px solid #1a4a8a;"
                        )
                    else:
                        inp.setStyleSheet(INPUT_STYLE)
                    inp.setAlignment(Qt.AlignmentFlag.AlignRight)
                    inp.setFixedWidth(88)
                    inp.editingFinished.connect(
                        lambda s=stmt: self._recalculate(s)
                    )
                    grid.addWidget(inp, row, col_idx + 1)
                    self._inputs[stmt][key][period] = inp

        container.setLayout(grid)
        return container

    def _switch_statement(self, stmt: str):
        self._current_statement = stmt
        self._is_widget.setVisible(stmt == "IS")
        self._bs_widget.setVisible(stmt == "BS")

    def _load_data(self):
        """Populate input fields from working copy."""
        periods = self._get_periods()
        for stmt, lines in [("IS", IS_LINES), ("BS", BS_LINES)]:
            data = (self._working.is_data if stmt == "IS"
                    else self._working.bs_data)
            for key, label, is_calc, bold in lines:
                if is_calc:
                    continue
                for period in periods:
                    val = data.get(key, {}).get(period)
                    widget = self._inputs[stmt].get(key, {}).get(period)
                    if widget and val is not None:
                        widget.setText(f"{val:,.0f}")

        self._recalculate("IS")
        self._recalculate("BS")

    def _get_input(self, stmt: str, key: str,
                   period: str) -> Optional[float]:
        widget = self._inputs[stmt].get(key, {}).get(period)
        if widget:
            return _parse_float(widget.text())
        return None

    def _get_calc(self, stmt: str, key: str,
                  period: str) -> Optional[float]:
        """Read a calculated value back as float."""
        lbl = self._calc_labels[stmt].get(key, {}).get(period)
        if lbl:
            return _parse_float(lbl.text())
        return None

    def _set_calc(self, stmt: str, key: str, period: str,
                  value: Optional[float]):
        lbl = self._calc_labels[stmt].get(key, {}).get(period)
        if lbl:
            lbl.setText(_fmt(value) if value is not None else "")

    def _recalculate(self, stmt: str):
        """Recompute all calculated rows for given statement."""
        periods = self._get_periods()
        ytd_prior, ytd_current = self._get_ytd_labels()

        if stmt == "IS":
            for period in periods:
                def g(key, p=period):
                    return self._get_input("IS", key, p)

                def gc(key, p=period):
                    return self._get_calc("IS", key, p)

                # Cost of Goods Sold = COGS + Adjustment
                cogs_total = _add(g("cogs"), g("cogs_adjustment"))
                self._set_calc("IS", "cost_of_goods_sold", period, cogs_total)

                # Gross Profit = Revenue - Cost of Goods Sold
                gross_profit = _sub(g("revenue"), cogs_total)
                self._set_calc("IS", "gross_profit", period, gross_profit)

                # Operating Expenses = SG&A + R&D + Other + Adjustment
                op_exp = _add(
                    g("sga"), g("rd"),
                    g("other_operating"), g("operating_expense_adj")
                )
                self._set_calc("IS", "operating_expenses", period, op_exp)

                # EBITDA = Gross Profit - Operating Expenses
                ebitda = _sub(gross_profit, op_exp)
                self._set_calc("IS", "ebitda", period, ebitda)

                # EBIT = EBITDA - D&A
                da = _add(g("depreciation"), g("amortization"))
                ebit = _sub(ebitda, da)
                self._set_calc("IS", "ebit", period, ebit)

                # Pretax = EBIT - Interest Expense + Interest Income
                #          + Other Income
                pretax = _add(
                    ebit,
                    _neg(g("interest_expense")),
                    g("interest_income"),
                    g("other_income"),
                )
                self._set_calc("IS", "pretax_income", period, pretax)

                # Income Before Nonrecurring = Pretax - Taxes
                inc_before = _sub(pretax, g("taxes"))
                self._set_calc(
                    "IS", "income_before_nonrecurring", period, inc_before
                )

                # Net Income = Inc Before + Nonrecurring
                net_income = _add(inc_before, g("nonrecurring"))
                self._set_calc("IS", "net_income", period, net_income)

                # Interest Expense (After Tax) =
                #   Interest Expense * (1 - Taxes/Pretax)
                int_exp = g("interest_expense")
                taxes = g("taxes")
                if (int_exp is not None and taxes is not None
                        and pretax is not None and pretax != 0):
                    tax_rate = taxes / pretax
                    int_after_tax = int_exp * (1 - tax_rate)
                elif int_exp is not None:
                    int_after_tax = int_exp
                else:
                    int_after_tax = None
                self._set_calc(
                    "IS", "interest_expense_after_tax",
                    period, int_after_tax
                )

                # Debt-free Net Income = Net Income + Int After Tax
                dfni = _add(net_income, int_after_tax)
                self._set_calc("IS", "debt_free_net_income", period, dfni)

            # TTM = LFY - YTD_prior + YTD_current
            # Apply to every IS line item
            all_keys = [k for k, _, _, _ in IS_LINES]
            for key, label, is_calc, bold in IS_LINES:
                lfy_val = (
                    self._get_calc("IS", key, "LFY")
                    if is_calc
                    else self._get_input("IS", key, "LFY")
                )
                ytd_p = (
                    self._get_calc("IS", key, ytd_prior)
                    if is_calc
                    else self._get_input("IS", key, ytd_prior)
                )
                ytd_c = (
                    self._get_calc("IS", key, ytd_current)
                    if is_calc
                    else self._get_input("IS", key, ytd_current)
                )
                if any(v is not None for v in [lfy_val, ytd_p, ytd_c]):
                    ttm = _add(
                        lfy_val or 0,
                        _neg(ytd_p or 0),
                        ytd_c or 0,
                    )
                else:
                    ttm = None
                self._set_calc("IS", key, "TTM", ttm)

        else:  # BS
            for period in periods:
                def g(key, p=period):
                    return self._get_input("BS", key, p)

                tca = _add(
                    g("cash"), g("st_investments"),
                    g("accounts_receivable"), g("receivables"),
                    g("other_receivables"), g("inventory"),
                    g("other_current_assets"),
                )
                self._set_calc("BS", "total_current_assets", period, tca)

                ta = _add(
                    tca, g("ppe"), g("intangible_assets"),
                    g("goodwill"), g("lt_investments"),
                    g("other_lt_assets"),
                )
                self._set_calc("BS", "total_assets", period, ta)

                tcl = _add(
                    g("st_debt"), g("current_ltd"), g("current_leases"),
                    g("accounts_payable"), g("accrued_expenses"),
                    g("unearned_revenue"), g("other_current_liab"),
                )
                self._set_calc("BS", "total_current_liab", period, tcl)

                tl = _add(
                    tcl, g("lt_debt"), g("lt_leases"),
                    g("lt_operating_leases"), g("other_lt_liab"),
                )
                self._set_calc("BS", "total_liabilities", period, tl)

                te = _add(
                    g("preferred_stock"), g("common_stock"),
                    g("apic"), g("treasury_stock"),
                    g("aoci"), g("minority_interest"),
                    g("retained_earnings"), g("common_equity"),
                    g("placeholder"),
                )
                self._set_calc("BS", "total_equity", period, te)

                self._set_calc(
                    "BS", "total_liab_equity", period, _add(tl, te)
                )

    def _collect_data(self) -> PrivateFinancials:
        """Read all input and calc fields into a fresh PrivateFinancials."""
        pf = PrivateFinancials()
        periods = self._get_periods()

        for stmt, lines in [("IS", IS_LINES), ("BS", BS_LINES)]:
            for key, label, is_calc, bold in lines:
                for period in periods:
                    if is_calc or period == "TTM":
                        lbl = self._calc_labels[stmt].get(
                            key, {}
                        ).get(period)
                        val = _parse_float(lbl.text()) if lbl else None
                    else:
                        val = self._get_input(stmt, key, period)

                    if stmt == "IS":
                        pf.set_is(key, period, val)
                    else:
                        pf.set_bs(key, period, val)
        return pf

    def _on_save(self):
        collected = self._collect_data()
        self._saved_financials.is_data = collected.is_data
        self._saved_financials.bs_data = collected.bs_data
        self.accept()


# ------------------------------------------------------------------
# ARITHMETIC HELPERS — None-safe
# ------------------------------------------------------------------

def _add(*values) -> Optional[float]:
    result = 0.0
    any_value = False
    for v in values:
        if v is not None:
            result += v
            any_value = True
    return result if any_value else None


def _sub(a: Optional[float], b: Optional[float]) -> Optional[float]:
    if a is None and b is None:
        return None
    a = a or 0.0
    b = b or 0.0
    return a - b


def _neg(v: Optional[float]) -> Optional[float]:
    return -v if v is not None else None