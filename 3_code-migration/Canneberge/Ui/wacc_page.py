"""
wacc_page.py
Canneberge — Weighted Average Cost of Capital page.

Layout-only skeleton for now, per Ted's instruction: structure, columns,
headers, and row count match the Excel WACC worksheet's "Debt (Book)"
comp-set table. No calculations wired yet — every data cell is a
placeholder "-" label until each column's formula is specified.

Row count is dynamic, driven by ProjectInputs.gpc_tickers (same source
GPC page uses), capped at 15 slots to match the Home page's GPC grid.
"""

import statistics
from typing import Optional, Dict, List

from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QScrollArea,
    QGridLayout,
    QLabel,
    QLineEdit,
    QCheckBox,
    QComboBox,
    QFrame,
)

from PyQt6.QtCore import Qt

from Canneberge.Calculations.ratio_catalogue import (
    compute_debt_to_tic_book,
    compute_historic_capital_structure,
    debt_to_equity_from_debt_to_tic,
    compute_effective_tax_rate,
)

# Beta Type + Beta Frequency -> matching column in the Beta/Vol (Yahoo)
# Source Data results. Capital Structure is intentionally NOT part of
# this map — it drives the Debt (Book) as % of Equity/TIC columns
# instead, not Observed Beta. Wired separately when those columns are built.
BETA_TYPE_OPTIONS = ["Raw Betas", "Adjusted Betas"]
BETA_FREQUENCY_OPTIONS = ["5-Year Monthly", "2-Year Weekly"]
CAPITAL_STRUCTURE_OPTIONS = [
    "As of Valuation Date",
    "Historical 2 Yr. Average",
    "Historical 5 Year Average",
]

# Capital Structure dropdown -> Debt/TIC column header text.
CAPITAL_STRUCTURE_HEADER_MAP = {
    "As of Valuation Date":       "Debt (Book) as a % of TIC",
    "Historical 2 Yr. Average":   "2 Yr. Historic Capital Structure",
    "Historical 5 Year Average":  "5 Yr. Historic Capital Structure",
}

# FRED corporate-rate series available for Pre-Tax Cost of Debt.
CORPORATE_RATE_SERIES = {
    "ICE BofA US Corporate Master":   "BAMLC0A0CMEY",
    "ICE BofA AAA US Corporate":      "BAMLC0A1CAAAEY",
    "ICE BofA AA US Corporate":       "BAMLC0A2CAAEY",
    "ICE BofA A US Corporate":        "BAMLC0A3CAEY",
    "ICE BofA BBB US Corporate":      "BAMLC0A4CBBBEY",
}

BETA_COLUMN_MAP = {
    ("Raw Betas",      "2-Year Weekly"):  "2yr Raw",
    ("Adjusted Betas", "2-Year Weekly"):  "2yr Adj",
    ("Raw Betas",      "5-Year Monthly"): "5yr Raw",
    ("Adjusted Betas", "5-Year Monthly"): "5yr Adj",
}

MAX_ROWS = 15

# Column indices — single schema, same pattern as gt_page.py/gpc_page.py
COL_EXCLUDE = 0
COL_NUM = 1
COL_TICKER = 2
COL_COMPANY = 3
COL_BETA = 4
COL_DEBT_EQUITY = 5
COL_DEBT_TIC = 6
COL_TAX_RATE = 7
COL_UNLEVERED_BETA = 8
COL_RELEVERED_BETA = 9
DATA_COLS = [COL_BETA, COL_DEBT_EQUITY, COL_DEBT_TIC, COL_TAX_RATE, COL_UNLEVERED_BETA, COL_RELEVERED_BETA]

W_EXCLUDE = 55
W_NUM = 30
W_TICKER = 70
W_DATA = 130

HEADER_STYLE = "font-weight: bold; color: #6912b0;"
SECTION_HEADER_STYLE = "font-weight: bold; font-size: 11px;"


def _make_hrule() -> QFrame:
    line = QFrame()
    line.setFrameShape(QFrame.Shape.HLine)
    line.setFrameShadow(QFrame.Shadow.Sunken)
    return line


def _make_section_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(SECTION_HEADER_STYLE)
    return lbl


def _placeholder_label() -> QLabel:
    lbl = QLabel("-")
    lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    return lbl

INPUT_STYLE = "background-color: #dce9f7; color: #1a4a8a;"


class PctInputEdit(QLineEdit):
    """Editable percent input, formats ##.#% on focus-out."""
    def __init__(self, placeholder="", parent=None):
        super().__init__(parent)
        self.setPlaceholderText(placeholder)
        self.setStyleSheet(INPUT_STYLE)
        self.setFixedWidth(W_DATA - 10)
        self.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.editingFinished.connect(self._format_value)

    def _format_value(self):
        val = _parse_pct_input(self.text())
        if val is not None:
            self.setText(f"{val * 100:.1f}%")


class BetaInputEdit(QLineEdit):
    """Editable beta input, formats X.XX on focus-out."""
    def __init__(self, placeholder="", parent=None):
        super().__init__(parent)
        self.setPlaceholderText(placeholder)
        self.setStyleSheet(INPUT_STYLE)
        self.setFixedWidth(W_DATA - 10)
        self.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.editingFinished.connect(self._format_value)

    def _format_value(self):
        val = _to_float(self.text())
        if val is not None:
            self.setText(f"{val:.2f}")


def _parse_pct_input(text: str) -> Optional[float]:
    text = str(text).strip().replace(",", "").replace("%", "")
    if not text:
        return None
    try:
        val = float(text)
    except (ValueError, TypeError):
        return None
    return val / 100.0 if abs(val) > 1 else val

def _to_float(raw) -> Optional[float]:
    if raw is None:
        return None
    try:
        return float(str(raw).replace(",", ""))
    except (ValueError, TypeError):
        return None

def _to_pct_float_local(raw) -> Optional[float]:
    """FRED's LatestValue is a plain number meaning a percent (e.g. '4.98'
    means 4.98%), not pre-divided — different shape than StockAnalysis's
    '%'-suffixed strings, so this is intentionally separate from
    _to_pct_float in ratio_catalogue.py."""
    val = _to_float(raw)
    return val / 100.0 if val is not None else None

def _fmt_beta(value: Optional[float]) -> str:
    if value is None:
        return "NA"
    return f"{value:.2f}"

def _fmt_pct(value: Optional[float]) -> str:
    if value is None:
        return "NA"
    return f"{value * 100:.1f}%"

def _quartile(values: list, q: float) -> float:
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    if n == 1:
        return sorted_vals[0]
    idx = q * (n - 1)
    lo = int(idx)
    hi = lo + 1
    if hi >= n:
        return sorted_vals[-1]
    frac = idx - lo
    return sorted_vals[lo] + frac * (sorted_vals[hi] - sorted_vals[lo])


def _compute_unlevered_beta(
    observed_beta: Optional[float], debt_pct_equity: Optional[float], tax_rate: Optional[float]
) -> Optional[float]:
    if observed_beta is None or debt_pct_equity is None or tax_rate is None:
        return None
    denom = 1 + debt_pct_equity * (1 - tax_rate)
    if denom == 0:
        return None
    return observed_beta / denom


def _compute_relevered_beta(
    unlevered_beta: Optional[float], selected_debt_pct_tic: Optional[float],
    selected_tax_rate: Optional[float]
) -> Optional[float]:
    if unlevered_beta is None or selected_debt_pct_tic is None or selected_tax_rate is None:
        return None
    if selected_debt_pct_tic == 1:
        return None
    factor = 1 + (selected_debt_pct_tic / (1 - selected_debt_pct_tic)) * (1 - selected_tax_rate)
    return unlevered_beta * factor
    

class WACCPage(QWidget):
    """
    Weighted Average Cost of Capital — comp-set beta/debt table.
    Structurally mirrors GTPage/GPCPage: single QGridLayout column
    schema, scroll area, Exclude checkboxes per row.
    """

    def __init__(self, get_project_inputs_callback, get_beta_vol_results_callback,
                 get_stockanalysis_results_callback, get_fred_results_callback):
        super().__init__()
        self.get_project_inputs_callback = get_project_inputs_callback
        self._get_beta_vol_results = get_beta_vol_results_callback
        self._get_stockanalysis_results = get_stockanalysis_results_callback
        self._get_fred_results = get_fred_results_callback
        self._build_ui()
        self._recalculate()

    def _build_ui(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)

        container = QWidget()
        self.grid = QGridLayout()
        self.grid.setSpacing(4)
        self.grid.setContentsMargins(12, 12, 12, 12)

        self.grid.setColumnMinimumWidth(COL_EXCLUDE, W_EXCLUDE)
        self.grid.setColumnMinimumWidth(COL_NUM, W_NUM)
        self.grid.setColumnMinimumWidth(COL_TICKER, W_TICKER)
        for col in DATA_COLS:
            self.grid.setColumnMinimumWidth(col, W_DATA)

        self.grid.setColumnStretch(COL_COMPANY, 2)

        self._current_row = 0
        self._build_header()
        self._build_inputs_section()
        self._build_ticker_section()
        self._build_statistics_section()
        self._build_selected_section()
        self._build_cost_of_equity_section()
        self._build_cost_of_debt_section()
        self._build_wacc_summary_section()

        self.grid.setRowStretch(self._current_row + 50, 1)

        container.setLayout(self.grid)
        scroll.setWidget(container)

        outer = QVBoxLayout()
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)
        self.setLayout(outer)

    # ------------------------------------------------------------------
    # SECTION BUILDERS
    # ------------------------------------------------------------------

    def _build_header(self):
        r = self._current_row
        self.lbl_client = QLabel()
        self.lbl_client.setStyleSheet("font-weight: bold;")
        self.lbl_subject = QLabel()
        self.lbl_subject.setStyleSheet("font-weight: bold;")
        self.lbl_method = QLabel("Weighted Average Cost of Capital")
        self.lbl_method.setStyleSheet("font-weight: bold;")
        self.lbl_date = QLabel()
        self.lbl_date.setStyleSheet("font-weight: bold;")

        self.grid.addWidget(self.lbl_client,  r, COL_EXCLUDE, 1, 2)
        self.grid.addWidget(self.lbl_subject, r, COL_TICKER,  1, 1)
        self.grid.addWidget(self.lbl_method,  r, COL_COMPANY, 1, 2)
        self.grid.addWidget(self.lbl_date,    r, COL_BETA,    1, 2)
        self._current_row += 1

        # Spacer
        self.grid.addWidget(QLabel(""), self._current_row, 0)
        self._current_row += 1

    def _build_inputs_section(self):
        r = self._current_row

        self.beta_type_combo = QComboBox()
        self.beta_type_combo.addItems(BETA_TYPE_OPTIONS)
        self.beta_type_combo.currentIndexChanged.connect(self._on_inputs_changed)

        self.beta_frequency_combo = QComboBox()
        self.beta_frequency_combo.addItems(BETA_FREQUENCY_OPTIONS)
        self.beta_frequency_combo.currentIndexChanged.connect(self._on_inputs_changed)

        self.capital_structure_combo = QComboBox()
        self.capital_structure_combo.addItems(CAPITAL_STRUCTURE_OPTIONS)
        self.capital_structure_combo.currentIndexChanged.connect(self._on_inputs_changed)

        for label_text, combo in [
            ("Beta Type:",          self.beta_type_combo),
            ("Beta Frequency:",     self.beta_frequency_combo),
            ("Capital Structure:",  self.capital_structure_combo),
        ]:
            row_layout = QHBoxLayout()
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(6)
            lbl = QLabel(label_text)
            lbl.setStyleSheet("font-weight: bold;")
            row_layout.addWidget(lbl)
            row_layout.addWidget(combo)
            row_layout.addStretch()
            row_container = QWidget()
            row_container.setLayout(row_layout)

            self.grid.addWidget(
                row_container, self._current_row, COL_EXCLUDE, 1, 6,
                alignment=Qt.AlignmentFlag.AlignLeft
            )
            self._current_row += 1

        # Spacer
        self.grid.addWidget(QLabel(""), self._current_row, 0)
        self._current_row += 1

    def _on_inputs_changed(self):
        self._recalculate()

    def _build_ticker_section(self):
        r = self._current_row

        for col, text in [
            (COL_EXCLUDE, "Exclude"),
            (COL_NUM,     "#"),
            (COL_TICKER,  "Ticker"),
            (COL_COMPANY, "Company Name"),
        ]:
            lbl = QLabel(text)
            lbl.setStyleSheet("font-weight: bold;")
            self.grid.addWidget(lbl, r, col)

        header_texts = {
            COL_BETA:             "Observed Beta",
            COL_DEBT_EQUITY:      "Debt (Book) as a % of Equity",
            COL_DEBT_TIC:         "Debt (Book) as a % of TIC",
            COL_TAX_RATE:         "Effective Tax Rate",
            COL_UNLEVERED_BETA:   "Unlevered Beta",
            COL_RELEVERED_BETA:   "Re-Levered Beta",
        }

        self.header_labels: Dict[int, QLabel] = {}
        for col, text in header_texts.items():
            lbl = QLabel(text)
            lbl.setStyleSheet(HEADER_STYLE)
            lbl.setWordWrap(True)
            lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.grid.addWidget(lbl, r, col)
            self.header_labels[col] = lbl

        self._current_row += 1

        self.tick_exclude_checks = []
        self.tick_row_labels = []      # {"ticker": lbl, "company": lbl} per row
        self.tick_data_labels = []     # one QLabel per row per DATA_COLS entry

        for row in range(MAX_ROWS):
            r = self._current_row

            chk = QCheckBox()
            chk.setFixedWidth(W_EXCLUDE)
            chk.stateChanged.connect(self._on_inputs_changed)
            self.tick_exclude_checks.append(chk)
            self.grid.addWidget(chk, r, COL_EXCLUDE,
                                alignment=Qt.AlignmentFlag.AlignCenter)

            num_lbl = QLabel(str(row + 1))
            self.grid.addWidget(num_lbl, r, COL_NUM)

            ticker_lbl = QLabel("")
            company_lbl = QLabel("")
            self.grid.addWidget(ticker_lbl, r, COL_TICKER)
            self.grid.addWidget(company_lbl, r, COL_COMPANY)
            self.tick_row_labels.append({"ticker": ticker_lbl, "company": company_lbl})

            row_data_lbls = {}
            for col in DATA_COLS:
                lbl = _placeholder_label()
                self.grid.addWidget(lbl, r, col)
                row_data_lbls[col] = lbl
            self.tick_data_labels.append(row_data_lbls)

            self._current_row += 1

        self.grid.addWidget(_make_hrule(), self._current_row, COL_EXCLUDE, 1, 10)
        self._current_row += 1

    def _build_statistics_section(self):
        self.grid.addWidget(
            _make_section_label("Statistics"),
            self._current_row, COL_EXCLUDE, 1, 10
        )
        self._current_row += 1

        stat_names = ["Maximum", "Third Quartile", "Average",
                      "Median", "First Quartile", "Minimum"]
        self.stat_label_widgets = {}

        for stat in stat_names:
            r = self._current_row
            self.grid.addWidget(QLabel(stat), r, COL_EXCLUDE, 1, 3)

            col_lbls = {}
            for col in DATA_COLS:
                lbl = _placeholder_label()
                self.grid.addWidget(lbl, r, col)
                col_lbls[col] = lbl

            self.stat_label_widgets[stat] = col_lbls
            self._current_row += 1

        self.grid.addWidget(_make_hrule(), self._current_row, COL_EXCLUDE, 1, 10)
        self._current_row += 1

    def _build_selected_section(self):
        r = self._current_row
        lbl = QLabel("Selected")
        lbl.setStyleSheet("font-weight: bold; color: #6912b0;")
        self.grid.addWidget(lbl, r, COL_EXCLUDE, 1, 3)

        # Only three cells are ever populated on this row: Debt%TIC and
        # Re-Levered Beta are user-typed inputs; Effective Tax Rate is a
        # read-only mirror of the Home page's Tax Rate field, never
        # independently editable here. Observed Beta, Debt%Equity, and
        # Unlevered Beta stay permanently blank — there's no single
        # "target" figure for those three.
        self.selected_debt_tic_input = PctInputEdit(placeholder="e.g. 25.0%")
        self.selected_debt_tic_input.editingFinished.connect(self._on_inputs_changed)
        self.grid.addWidget(self.selected_debt_tic_input, r, COL_DEBT_TIC)

        self.selected_tax_rate_label = _placeholder_label()
        self.selected_tax_rate_label.setStyleSheet("font-weight: bold;")
        self.grid.addWidget(self.selected_tax_rate_label, r, COL_TAX_RATE)

        self.selected_relevered_beta_input = BetaInputEdit(placeholder="e.g. 1.25")
        self.selected_relevered_beta_input.editingFinished.connect(self._on_inputs_changed)
        self.grid.addWidget(self.selected_relevered_beta_input, r, COL_RELEVERED_BETA)

        self._current_row += 1

    def _add_note(self, row: int, note: str):
        if not note:
            return
        note_lbl = QLabel(note)
        note_lbl.setWordWrap(True)
        note_lbl.setStyleSheet("color: #555555; font-style: italic;")
        self.grid.addWidget(note_lbl, row, COL_DEBT_TIC, 1, 5)

    def _build_labeled_row(self, label_text: str, bold: bool = False, note: str = "") -> QLabel:
        """One label (spanning cols 0-3) + one value QLabel (col COL_BETA)
        + an optional static note further right (formula/source citation)."""
        r = self._current_row
        lbl = QLabel(label_text)
        if bold:
            lbl.setStyleSheet("font-weight: bold;")
        self.grid.addWidget(lbl, r, COL_EXCLUDE, 1, 4)

        val_lbl = _placeholder_label()
        if bold:
            val_lbl.setStyleSheet("font-weight: bold;")
        self.grid.addWidget(val_lbl, r, COL_BETA)

        self._add_note(r, note)

        self._current_row += 1
        return val_lbl

    def _build_labeled_input_row(self, label_text: str, placeholder: str, note: str = "") -> "PctInputEdit":
        r = self._current_row
        lbl = QLabel(label_text)
        self.grid.addWidget(lbl, r, COL_EXCLUDE, 1, 4)

        inp = PctInputEdit(placeholder=placeholder)
        inp.editingFinished.connect(self._on_inputs_changed)
        self.grid.addWidget(inp, r, COL_BETA)

        self._add_note(r, note)

        self._current_row += 1
        return inp

    def _build_labeled_dropdown_row(self, label_text: str, options: list, note: str = "") -> "QComboBox":
        """Label + a value QLabel (col COL_BETA, computed from the dropdown
        selection) + the dropdown itself one column right (col COL_DEBT_EQUITY)."""
        r = self._current_row
        lbl = QLabel(label_text)
        self.grid.addWidget(lbl, r, COL_EXCLUDE, 1, 4)

        val_lbl = _placeholder_label()
        self.grid.addWidget(val_lbl, r, COL_BETA)

        combo = QComboBox()
        combo.addItems(options)
        combo.setStyleSheet(INPUT_STYLE)
        combo.currentIndexChanged.connect(self._on_inputs_changed)
        self.grid.addWidget(combo, r, COL_DEBT_EQUITY, 1, 2)

        self._add_note(r, note)

        self._current_row += 1
        return combo, val_lbl

    def _build_cost_of_equity_section(self):
        self.grid.addWidget(
            _make_section_label("Cost of Equity (Ke) - MCAPM Method"),
            self._current_row, COL_EXCLUDE, 1, 10
        )
        self._current_row += 1

        self.lbl_risk_free_rate = self._build_labeled_row(
            "Risk-Free Rate (Rf)",
            note="The risk-free rate is based on the yield of 20-year constant "
                 "maturity U.S. Treasury bonds per FRED."
        )
        self.lbl_relevered_beta_display = self._build_labeled_row(
            "Re-Levered Beta (Be)",
            note="Be = Ba x [ 1 + (Wd / We) x ( 1 - T) ]"
        )
        self.input_equity_risk_premium = self._build_labeled_input_row(
            "Equity Risk Premium (Rm - Rf)", "e.g. 5.0%", note="Kroll"
        )
        self.lbl_adjusted_erp = self._build_labeled_row(
            "Adjusted Equity Risk Premium", note="(Rm - Rf)"
        )
        self.input_size_premium = self._build_labeled_input_row(
            "Size Premium (SP)", "e.g. 0.0%"
        )
        self.input_csrp = self._build_labeled_input_row(
            "Company Specific Risk Premium (CSRP)", "e.g. 5.0%",
            note="The company specific premium takes into account company-specific "
                 "risks including the uncertainty of achieving the financial projections."
        )
        self.lbl_cost_of_equity = self._build_labeled_row(
            "Cost of Equity", bold=True,
            note="Ke = Rf + Be (Rm - Rf) + SP + CSRP"
        )

        self.grid.addWidget(QLabel(""), self._current_row, 0)
        self._current_row += 1

    def _build_cost_of_debt_section(self):
        self.grid.addWidget(
            _make_section_label("After-Tax Cost of Debt (Kd)"),
            self._current_row, COL_EXCLUDE, 1, 10
        )
        self._current_row += 1

        self.pretax_debt_combo, self.lbl_pretax_cost_of_debt = self._build_labeled_dropdown_row(
            "Pre-Tax Cost of Debt", list(CORPORATE_RATE_SERIES.keys())
        )
        self.lbl_tax_rate_kd = self._build_labeled_row("Tax Rate (T)")
        self.lbl_after_tax_cost_of_debt = self._build_labeled_row(
            "After-Tax Cost of Debt", bold=True, note="Kd = Kd (1 - T)"
        )

        self.grid.addWidget(QLabel(""), self._current_row, 0)
        self._current_row += 1

    def _build_wacc_summary_section(self):
        self.grid.addWidget(
            _make_section_label("Weighted Average Cost of Capital"),
            self._current_row, COL_EXCLUDE, 1, 10
        )
        self._current_row += 1

        self.lbl_equity_pct_capital = self._build_labeled_row("Equity % of Capital (We)")
        self.lbl_cost_of_equity_ref = self._build_labeled_row("Cost of Equity (Ke)")
        self.lbl_weighted_cost_of_equity = self._build_labeled_row("Weighted Cost of Equity")

        self.grid.addWidget(QLabel(""), self._current_row, 0)
        self._current_row += 1

        self.lbl_debt_pct_capital = self._build_labeled_row("Debt % of Capital (Wd)")
        self.lbl_cost_of_debt_ref = self._build_labeled_row("Cost of Debt (Kd)")
        self.lbl_weighted_cost_of_debt = self._build_labeled_row("Weighted Cost of Debt")

        self.grid.addWidget(_make_hrule(), self._current_row, COL_EXCLUDE, 1, 10)
        self._current_row += 1

        self.lbl_wacc_rounded = self._build_labeled_row("WACC (Rounded)", bold=True)

    # ------------------------------------------------------------------
    # RECALCULATION — layout population only for now (ticker/company
    # name), no formulas wired. Every DATA_COLS cell stays "-" until
    # each column's calculation is specified.
    # ------------------------------------------------------------------

    def _on_inputs_changed(self):
        self._recalculate()

    def _recalculate(self):
        inputs = self.get_project_inputs_callback()
        tickers = inputs.gpc_tickers

        self.lbl_client.setText(inputs.client)
        self.lbl_subject.setText(inputs.subject_company_name)
        self.lbl_date.setText(f"As of {inputs.valuation_date}")

        beta_type = self.beta_type_combo.currentText()
        beta_frequency = self.beta_frequency_combo.currentText()
        beta_col = BETA_COLUMN_MAP.get((beta_type, beta_frequency))

        beta_vol_rows = self._get_beta_vol_results() or []
        beta_lookup = {}
        for row_data in beta_vol_rows:
            t = str(row_data.get("Ticker", "")).strip().upper()
            if t:
                beta_lookup[t] = row_data

        capital_structure = self.capital_structure_combo.currentText()
        self.header_labels[COL_DEBT_TIC].setText(
            CAPITAL_STRUCTURE_HEADER_MAP.get(capital_structure, "Debt (Book) as a % of TIC")
        )

        sa_results = self._get_stockanalysis_results() or {}
        bs_rows = sa_results.get("BS", [])
        ratio_rows = sa_results.get("Ratios", [])
        is_rows = sa_results.get("IS", [])

        hist_periods = inputs.historical_period_columns + ["TTM"]
        two_yr_periods = hist_periods[-3:] if len(hist_periods) >= 3 else hist_periods
        five_yr_periods = hist_periods

        # Selected-row inputs — drive every row's Re-Levered Beta via the
        # target capital structure, plus the Home-page-linked tax rate.
        self.selected_tax_rate_label.setText(_fmt_pct(inputs.subject_tax_rate))
        selected_debt_tic = _parse_pct_input(self.selected_debt_tic_input.text())
        selected_tax_rate = inputs.subject_tax_rate

        stats_values: Dict[int, List[float]] = {col: [] for col in DATA_COLS}

        for row in range(MAX_ROWS):
            if row < len(tickers):
                ticker = tickers[row]
                self.tick_row_labels[row]["ticker"].setText(ticker)
                self.tick_row_labels[row]["company"].setText(
                    inputs.gpc_company_names.get(ticker.upper(), "")
                )

                beta_val = None
                if beta_col:
                    row_data = beta_lookup.get(ticker.upper(), {})
                    beta_val = _to_float(row_data.get(beta_col))
                self.tick_data_labels[row][COL_BETA].setText(_fmt_beta(beta_val))

                if capital_structure == "Historical 2 Yr. Average":
                    debt_tic_val = compute_historic_capital_structure(
                        bs_rows, ratio_rows, ticker, two_yr_periods
                    )
                elif capital_structure == "Historical 5 Year Average":
                    debt_tic_val = compute_historic_capital_structure(
                        bs_rows, ratio_rows, ticker, five_yr_periods
                    )
                else:
                    debt_tic_val = compute_debt_to_tic_book(bs_rows, ticker, "TTM")
                self.tick_data_labels[row][COL_DEBT_TIC].setText(_fmt_pct(debt_tic_val))

                debt_equity_val = debt_to_equity_from_debt_to_tic(debt_tic_val)
                self.tick_data_labels[row][COL_DEBT_EQUITY].setText(_fmt_pct(debt_equity_val))

                tax_rate_val = compute_effective_tax_rate(
                    is_rows, ticker, fallback_rate=inputs.subject_tax_rate
                )
                self.tick_data_labels[row][COL_TAX_RATE].setText(_fmt_pct(tax_rate_val))

                unlevered_beta_val = _compute_unlevered_beta(beta_val, debt_equity_val, tax_rate_val)
                self.tick_data_labels[row][COL_UNLEVERED_BETA].setText(_fmt_beta(unlevered_beta_val))

                relevered_beta_val = _compute_relevered_beta(
                    unlevered_beta_val, selected_debt_tic, selected_tax_rate
                )
                self.tick_data_labels[row][COL_RELEVERED_BETA].setText(_fmt_beta(relevered_beta_val))

                excluded = self.tick_exclude_checks[row].isChecked()
                grey = "color: grey;" if excluded else "color: black;"
                for col in [COL_BETA, COL_DEBT_TIC, COL_DEBT_EQUITY, COL_TAX_RATE,
                            COL_UNLEVERED_BETA, COL_RELEVERED_BETA]:
                    self.tick_data_labels[row][col].setStyleSheet(grey)
                self.tick_row_labels[row]["ticker"].setStyleSheet(grey)
                self.tick_row_labels[row]["company"].setStyleSheet(grey)

                if not excluded:
                    for col, val in [
                        (COL_BETA, beta_val), (COL_DEBT_TIC, debt_tic_val),
                        (COL_DEBT_EQUITY, debt_equity_val), (COL_TAX_RATE, tax_rate_val),
                        (COL_UNLEVERED_BETA, unlevered_beta_val), (COL_RELEVERED_BETA, relevered_beta_val),
                    ]:
                        if val is not None:
                            stats_values[col].append(val)
            else:
                self.tick_row_labels[row]["ticker"].setText("")
                self.tick_row_labels[row]["company"].setText("")
                for col in DATA_COLS:
                    self.tick_data_labels[row][col].setText("-")

        stat_funcs = {
            "Maximum":        lambda v: max(v),
            "Third Quartile": lambda v: _quartile(v, 0.75),
            "Average":        lambda v: sum(v) / len(v),
            "Median":         lambda v: statistics.median(v),
            "First Quartile": lambda v: _quartile(v, 0.25),
            "Minimum":        lambda v: min(v),
        }
        beta_cols = {COL_BETA, COL_UNLEVERED_BETA, COL_RELEVERED_BETA}

        for stat, func in stat_funcs.items():
            for col in DATA_COLS:
                vals = stats_values[col]
                if vals:
                    try:
                        result = func(vals)
                        text = _fmt_beta(result) if col in beta_cols else _fmt_pct(result)
                    except Exception:
                        text = "NA"
                else:
                    text = "NA"
                self.stat_label_widgets[stat][col].setText(text)

        # ------------------------------------------------------------
        # Cost of Equity / Cost of Debt / WACC summary
        # ------------------------------------------------------------
        fred_rows = self._get_fred_results() or []
        risk_free_rate = None
        for row_data in fred_rows:
            if str(row_data.get("SeriesID", "")).strip().upper() == "DGS20":
                risk_free_rate = _to_pct_float_local(row_data.get("LatestValue"))
                break
        self.lbl_risk_free_rate.setText(_fmt_pct(risk_free_rate))

        relevered_beta_selected = _to_float(self.selected_relevered_beta_input.text())
        self.lbl_relevered_beta_display.setText(_fmt_beta(relevered_beta_selected))

        erp = _parse_pct_input(self.input_equity_risk_premium.text())
        adjusted_erp = (
            relevered_beta_selected * erp
            if relevered_beta_selected is not None and erp is not None else None
        )
        self.lbl_adjusted_erp.setText(_fmt_pct(adjusted_erp))

        size_premium = _parse_pct_input(self.input_size_premium.text())
        csrp = _parse_pct_input(self.input_csrp.text())

        cost_of_equity = None
        if None not in (risk_free_rate, adjusted_erp, size_premium, csrp):
            cost_of_equity = risk_free_rate + adjusted_erp + size_premium + csrp
        self.lbl_cost_of_equity.setText(_fmt_pct(cost_of_equity))

        selected_series_label = self.pretax_debt_combo.currentText()
        selected_series_id = CORPORATE_RATE_SERIES.get(selected_series_label)
        pretax_cost_of_debt = None
        for row_data in fred_rows:
            if str(row_data.get("SeriesID", "")).strip().upper() == selected_series_id:
                pretax_cost_of_debt = _to_pct_float_local(row_data.get("LatestValue"))
                break
        self.lbl_pretax_cost_of_debt.setText(_fmt_pct(pretax_cost_of_debt))
        self.lbl_tax_rate_kd.setText(_fmt_pct(selected_tax_rate))

        after_tax_cost_of_debt = None
        if pretax_cost_of_debt is not None and selected_tax_rate is not None:
            after_tax_cost_of_debt = pretax_cost_of_debt * (1 - selected_tax_rate)
        self.lbl_after_tax_cost_of_debt.setText(_fmt_pct(after_tax_cost_of_debt))

        we = 1 - selected_debt_tic if selected_debt_tic is not None else None
        wd = selected_debt_tic

        self.lbl_equity_pct_capital.setText(_fmt_pct(we))
        self.lbl_cost_of_equity_ref.setText(_fmt_pct(cost_of_equity))
        weighted_cost_of_equity = (
            we * cost_of_equity if we is not None and cost_of_equity is not None else None
        )
        self.lbl_weighted_cost_of_equity.setText(_fmt_pct(weighted_cost_of_equity))

        self.lbl_debt_pct_capital.setText(_fmt_pct(wd))
        self.lbl_cost_of_debt_ref.setText(_fmt_pct(after_tax_cost_of_debt))
        weighted_cost_of_debt = (
            wd * after_tax_cost_of_debt if wd is not None and after_tax_cost_of_debt is not None else None
        )
        self.lbl_weighted_cost_of_debt.setText(_fmt_pct(weighted_cost_of_debt))

        wacc = None
        if weighted_cost_of_equity is not None and weighted_cost_of_debt is not None:
            wacc = weighted_cost_of_equity + weighted_cost_of_debt
        self.lbl_wacc_rounded.setText(_fmt_pct(wacc))