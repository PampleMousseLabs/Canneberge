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

from typing import Optional

from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QScrollArea,
    QGridLayout,
    QLabel,
    QCheckBox,
    QComboBox,
    QFrame,
)
from PyQt6.QtCore import Qt

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

def _to_float(raw) -> Optional[float]:
    if raw is None:
        return None
    try:
        return float(str(raw).replace(",", ""))
    except (ValueError, TypeError):
        return None


def _fmt_beta(value: Optional[float]) -> str:
    if value is None:
        return "NA"
    return f"{value:.2f}"


class WACCPage(QWidget):
    """
    Weighted Average Cost of Capital — comp-set beta/debt table.
    Structurally mirrors GTPage/GPCPage: single QGridLayout column
    schema, scroll area, Exclude checkboxes per row.
    """

    def __init__(self, get_project_inputs_callback, get_beta_vol_results_callback):
        super().__init__()
        self.get_project_inputs_callback = get_project_inputs_callback
        self._get_beta_vol_results = get_beta_vol_results_callback
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
        for col, text in header_texts.items():
            lbl = QLabel(text)
            lbl.setStyleSheet(HEADER_STYLE)
            lbl.setWordWrap(True)
            lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.grid.addWidget(lbl, r, col)

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
        lbl.setStyleSheet("font-weight: bold; color: #c0392b;")
        self.grid.addWidget(lbl, r, COL_EXCLUDE, 1, 3)

        self.selected_labels = {}
        for col in DATA_COLS:
            data_lbl = _placeholder_label()
            data_lbl.setStyleSheet("font-weight: bold;")
            self.grid.addWidget(data_lbl, r, col)
            self.selected_labels[col] = data_lbl

        self._current_row += 1

    # ------------------------------------------------------------------
    # RECALCULATION — layout population only for now (ticker/company
    # name), no formulas wired. Every DATA_COLS cell stays "-" until
    # each column's calculation is specified.
    # ------------------------------------------------------------------

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

                excluded = self.tick_exclude_checks[row].isChecked()
                grey = "color: grey;" if excluded else "color: black;"
                self.tick_row_labels[row]["ticker"].setStyleSheet(grey)
                self.tick_row_labels[row]["company"].setStyleSheet(grey)
                self.tick_data_labels[row][COL_BETA].setStyleSheet(grey)
            else:
                self.tick_row_labels[row]["ticker"].setText("")
                self.tick_row_labels[row]["company"].setText("")
                self.tick_data_labels[row][COL_BETA].setText("-")