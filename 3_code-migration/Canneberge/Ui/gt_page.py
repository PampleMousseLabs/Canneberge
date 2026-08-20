import statistics
from typing import Optional, List

from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QScrollArea,
    QGridLayout,
    QLabel,
    QLineEdit,
    QComboBox,
    QSpinBox,
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QSizePolicy,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor

from Canneberge.app_state import Transaction
from Canneberge.Ui.gpc_candlestick_chart import GPCCandlestickChart
from Canneberge.Ui.theme import theme_manager
from Canneberge.Ui.shared_input_widgets import (
    MultipleInputEdit, PctInputEdit,
    _parse_float, _parse_pct,
)

METRICS = ["TTM Revenue", "TTM EBITDA", "TTM EBIT"]
MAX_COLS = 3
MAX_ROWS = 5

# Column indices — single schema for entire page
COL_EXCLUDE = 0
COL_NUM = 1
COL_DATE = 2
COL_TARGET = 3
COL_ACQUIRER = 4
COL_M0 = 5
COL_M1 = 6
COL_M2 = 7
METRIC_COLS = [COL_M0, COL_M1, COL_M2]

# Fixed widths
W_EXCLUDE = 55
W_NUM = 30
W_DATE = 90
W_METRIC = 120

# =====================================================================
# STYLE — colors come from the active Theme (Canneberge/Ui/theme.py)
# via theme_manager.current. Same pattern as gpc_page.py/dcf_page.py.
#
# NOTE: this is the THIRD independent copy of get_input_style()/CALC_STYLE/
# get_section_header_style() across the codebase (dcf_page.py, gpc_page.py,
# now this file) - flagged, not resolved here. Same for
# MultipleInputEdit/PctInputEdit below, which are byte-identical to
# gpc_page.py's copies.
# =====================================================================


def get_input_style() -> str:
    return theme_manager.current.input_style()


def get_bold_style() -> str:
    return theme_manager.current.bold_style()


def get_section_header_style() -> str:
    # Delegates to the ONE canonical header treatment - same method
    # DCF, GPC, and WACC now all use for section-divider bars.
    return theme_manager.current.header_style()


def get_link_text_style() -> str:
    return f"color: {theme_manager.current.link_color};"


def get_grey_disabled_style() -> str:
    return theme_manager.current.grey_disabled_style()


def get_excluded_row_style() -> str:
    return f"color: {theme_manager.current.disabled_text};"


def get_included_row_style() -> str:
    return f"color: {theme_manager.current.default_text};"


# NOTE: CALC_STYLE ("color: black;") is not referenced anywhere else
# in this file (confirmed via full-file search) - same dead-constant
# situation as gpc_page.py's copy. Left in place, not deleted.
CALC_STYLE = "color: black;"


def _fmt_multiple(value: Optional[float]) -> str:
    if value is None:
        return "NA"
    return f"{value:.2f}x"


def _fmt_currency(value: Optional[float]) -> str:
    if value is None:
        return "NA"
    return f"{value:,.0f}"


def _fmt_pct_display(value: Optional[float]) -> str:
    if value is None:
        return "NA"
    return f"{value:.1%}"


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


def _weighted_sum(values: list, weights: list) -> Optional[float]:
    if not values or not weights:
        return None
    total = 0.0
    for v, w in zip(values, weights):
        if v is None or w is None:
            return None
        total += v * w
    return total


def _make_hrule() -> QFrame:
    line = QFrame()
    line.setFrameShape(QFrame.Shape.HLine)
    line.setFrameShadow(QFrame.Shadow.Sunken)
    return line


def _make_section_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(get_section_header_style())
    return lbl


class GTPage(QWidget):
    """
    Guideline Transaction analysis page.
    Single QGridLayout column schema throughout — cols 5/6/7 always
    correspond to multiple columns 0/1/2 regardless of section.
    """

    def __init__(self, get_project_inputs_callback,
                 get_stockanalysis_results_callback,
                 get_private_financials_callback,
                 get_subject_debt,
                 get_subject_metric_value):
        super().__init__()
        self.get_project_inputs_callback = get_project_inputs_callback
        self._get_stockanalysis_results_callback = get_stockanalysis_results_callback
        self._get_private_financials_callback = get_private_financials_callback
        self._get_subject_debt = get_subject_debt
        self._get_subject_metric_value = get_subject_metric_value

        self._build_ui()
        self._recalculate()

        theme_manager.theme_changed.connect(self._apply_theme)

    def _apply_theme(self, theme=None):
        for lbl in self._section_labels:
            lbl.setStyleSheet(get_section_header_style())
        for hdr in self._bridge_low_high_headers:
            hdr.setStyleSheet(get_bold_style())
        for lbl in self._ticker_col_headers:
            lbl.setStyleSheet(get_bold_style())
        for combo in self.metric_combos:
            combo.setStyleSheet(get_input_style())

        self.lbl_client.setStyleSheet(get_bold_style())
        self.lbl_subject.setStyleSheet(get_bold_style())
        self.lbl_method.setStyleSheet(get_bold_style())
        self.lbl_date.setStyleSheet(get_bold_style())
        self.chart_link.setStyleSheet(get_link_text_style())

        self.num_multiples_spin.setStyleSheet(get_input_style())
        self.dloc_input.setStyleSheet(get_grey_disabled_style())

        self._recalculate()

    def _build_ui(self):
        # Scroll area so content isn't clipped on small screens
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)

        container = QWidget()
        self.grid = QGridLayout()
        self.grid.setSpacing(4)
        self.grid.setContentsMargins(12, 12, 12, 12)

        # Fixed column widths
        self.grid.setColumnMinimumWidth(COL_EXCLUDE, W_EXCLUDE)
        self.grid.setColumnMinimumWidth(COL_NUM, W_NUM)
        self.grid.setColumnMinimumWidth(COL_DATE, W_DATE)
        self.grid.setColumnMinimumWidth(COL_M0, W_METRIC)
        self.grid.setColumnMinimumWidth(COL_M1, W_METRIC)
        self.grid.setColumnMinimumWidth(COL_M2, W_METRIC)

        # Target and Acquirer columns stretch
        self.grid.setColumnStretch(COL_TARGET, 2)
        self.grid.setColumnStretch(COL_ACQUIRER, 2)

        self._current_row = 0
        self._chart_dialog = None
        self._section_labels = []
        self._bridge_low_high_headers = []
        self._ticker_col_headers = []
        self._build_header()
        self._build_controls()
        self._build_transaction_section()
        self._build_statistics_section()
        self._build_selected_multiples_section()
        self._build_subject_section()
        self._build_weighting_section()
        self._build_bridge_section()

        # Push everything to the top
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

    def _add_section_label(self, text: str, row: int, col: int,
                            row_span: int = 1, col_span: int = 1):
        """
        Wraps _make_section_label() + grid placement + registration
        into one call - matches gpc_page.py's identical helper. A new
        section label can't be added without also being captured for
        theme restyle.
        """
        lbl = _make_section_label(text)
        self.grid.addWidget(lbl, row, col, row_span, col_span)
        self._section_labels.append(lbl)
        return lbl

    def _build_header(self):
        r = self._current_row
        self.lbl_client = QLabel()
        self.lbl_client.setStyleSheet(get_bold_style())
        self.lbl_subject = QLabel()
        self.lbl_subject.setStyleSheet(get_bold_style())
        self.lbl_method = QLabel("Guideline Transaction Method")
        self.lbl_method.setStyleSheet(get_bold_style())
        self.lbl_date = QLabel()
        self.lbl_date.setStyleSheet(get_bold_style())

        self.grid.addWidget(self.lbl_client,  r, COL_EXCLUDE, 1, 2)
        self.grid.addWidget(self.lbl_subject, r, COL_DATE,    1, 1)
        self.grid.addWidget(self.lbl_method,  r, COL_TARGET,  1, 2)
        self.grid.addWidget(self.lbl_date,    r, COL_M1,      1, 2)
        self._current_row += 1

        r = self._current_row
        self.chart_link = QLabel('<a href="#">GT Multiples Range Chart →</a>')
        self.chart_link.setStyleSheet(get_link_text_style())
        self.chart_link.linkActivated.connect(self._on_chart_link_clicked)
        self.grid.addWidget(self.chart_link, r, COL_M1, 1, 2)
        self._current_row += 1

    def _on_chart_link_clicked(self, _href=None):
        first_open = self._chart_dialog is None
        if first_open:
            self._chart_dialog = GPCCandlestickChart(
                parent=self,
                window_title="GT Multiples Range",
                chart_title="Range of Selected Transaction Multiples",
            )
        if first_open:
            self._recalculate()  # push current data into the new dialog immediately
        self._chart_dialog.show()
        self._chart_dialog.raise_()
        self._chart_dialog.activateWindow()

    def _build_controls(self):
        r = self._current_row

        spin_label = QLabel("How Many Multiples:")
        self.num_multiples_spin = QSpinBox()
        self.num_multiples_spin.setMinimum(1)
        self.num_multiples_spin.setMaximum(MAX_COLS)
        self.num_multiples_spin.setValue(MAX_COLS)
        self.num_multiples_spin.setStyleSheet(get_input_style())
        self.num_multiples_spin.setFixedWidth(55)
        self.num_multiples_spin.valueChanged.connect(
            self._on_num_multiples_changed
        )

        self.grid.addWidget(spin_label,             r, COL_EXCLUDE, 1, 2)
        self.grid.addWidget(self.num_multiples_spin, r, COL_DATE)
        self._current_row += 1

        r = self._current_row
        dloc_label = QLabel("Discount for Lack of Control:")
        self.dloc_input = QLineEdit("19.4%")
        self.dloc_input.setFixedWidth(70)
        self.dloc_input.setAlignment(Qt.AlignmentFlag.AlignRight)
        # DLOC is derived from the Dashboard's Control Premium
        # (DLOC = CP / (1 + CP)) and pushed here — never typed.
        self.dloc_input.setReadOnly(True)
        self.dloc_input.setStyleSheet(get_grey_disabled_style())

        dloc_row = QHBoxLayout()
        dloc_row.setContentsMargins(0, 0, 0, 0)
        dloc_row.setSpacing(6)
        dloc_row.addWidget(dloc_label)
        dloc_row.addWidget(self.dloc_input)
        dloc_row.addStretch()
        dloc_container = QWidget()
        dloc_container.setLayout(dloc_row)

        self.grid.addWidget(
            dloc_container, r, COL_EXCLUDE, 1, 4,
            alignment=Qt.AlignmentFlag.AlignLeft
        )
        self._current_row += 1

        # Spacer
        self.grid.addWidget(QLabel(""), self._current_row, 0)
        self._current_row += 1

    def _build_transaction_section(self):
        r = self._current_row

        # Section label
        self._add_section_label(
            "Transaction Multiple(s)",
            r, COL_EXCLUDE, 1, 8
        )
        self._current_row += 1
        r = self._current_row

        self._ticker_col_headers = []
        for col, text in [
            (COL_EXCLUDE,   "Exclude"),
            (COL_NUM,       "#"),
            (COL_DATE,      "Closing Date"),
            (COL_TARGET,    "Target Company"),
            (COL_ACQUIRER,  "Acquirer"),
        ]:
            lbl = QLabel(text)
            lbl.setStyleSheet(get_bold_style())
            self.grid.addWidget(lbl, r, col)
            self._ticker_col_headers.append(lbl)

        # Metric dropdown headers (green inputs)
        self.metric_combos = []
        for i, col in enumerate(METRIC_COLS):
            combo = QComboBox()
            combo.addItems(METRICS)
            combo.setCurrentIndex(i)
            combo.setStyleSheet(get_input_style())
            combo.setFixedWidth(W_METRIC - 5)
            combo.currentIndexChanged.connect(self._on_inputs_changed)
            self.metric_combos.append(combo)
            self.grid.addWidget(combo, r, col)

        self._current_row += 1

        # Transaction rows
        self.tx_exclude_checks = []
        self.tx_row_labels = []
        self.tx_mult_labels = []

        for row in range(MAX_ROWS):
            r = self._current_row

            chk = QCheckBox()
            chk.setFixedWidth(W_EXCLUDE)
            chk.stateChanged.connect(self._on_inputs_changed)
            self.tx_exclude_checks.append(chk)
            self.grid.addWidget(chk, r, COL_EXCLUDE,
                                alignment=Qt.AlignmentFlag.AlignCenter)

            num_lbl = QLabel(str(row + 1))
            self.grid.addWidget(num_lbl, r, COL_NUM)

            row_labels = {}
            for col, key in [
                (COL_DATE,     "closing_date"),
                (COL_TARGET,   "target"),
                (COL_ACQUIRER, "acquirer"),
            ]:
                lbl = QLabel("")
                self.grid.addWidget(lbl, r, col)
                row_labels[key] = lbl

            self.tx_row_labels.append(row_labels)

            mult_lbls = []
            for col in METRIC_COLS:
                lbl = QLabel("NA")
                lbl.setAlignment(
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                )
                self.grid.addWidget(lbl, r, col)
                mult_lbls.append(lbl)

            self.tx_mult_labels.append(mult_lbls)
            self._current_row += 1

        # Divider
        self.grid.addWidget(_make_hrule(), self._current_row, COL_EXCLUDE, 1, 8)
        self._current_row += 1

    def _build_statistics_section(self):
        self._add_section_label(
            "Statistics",
            self._current_row, COL_EXCLUDE, 1, 8
        )
        self._current_row += 1

        stat_names = ["Maximum", "Third Quartile", "Average",
                      "Median", "First Quartile", "Minimum"]
        self.stat_label_widgets = {}

        for stat in stat_names:
            r = self._current_row
            self.grid.addWidget(QLabel(stat), r, COL_EXCLUDE, 1, 4)

            col_lbls = []
            for col in METRIC_COLS:
                lbl = QLabel("NA")
                lbl.setAlignment(
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                )
                self.grid.addWidget(lbl, r, col)
                col_lbls.append(lbl)

            self.stat_label_widgets[stat] = col_lbls
            self._current_row += 1

        self.grid.addWidget(_make_hrule(), self._current_row, COL_EXCLUDE, 1, 8)
        self._current_row += 1

    def _build_selected_multiples_section(self):
        self._add_section_label(
            "Selected Multiples",
            self._current_row, COL_EXCLUDE, 1, 8
        )
        self._current_row += 1

        self.selected_low_inputs = []
        self.selected_high_inputs = []

        for label_text, inputs_list in [
            ("Selected Multiple — High",  self.selected_high_inputs),
            ("Selected Multiple — Low", self.selected_low_inputs),
        ]:
            r = self._current_row
            self.grid.addWidget(QLabel(label_text), r, COL_EXCLUDE, 1, 4)

            for i, col in enumerate(METRIC_COLS):
                inp = MultipleInputEdit(placeholder="e.g. 4.0x", width=W_METRIC - 10)
                inp.editingFinished.connect(self._on_inputs_changed)
                inputs_list.append(inp)
                self.grid.addWidget(
                    inp, r, col,
                    alignment=Qt.AlignmentFlag.AlignRight
                )

            self._current_row += 1

        self.grid.addWidget(_make_hrule(), self._current_row, COL_EXCLUDE, 1, 8)
        self._current_row += 1

    def _build_subject_section(self):
        self._add_section_label(
            "Subject Company",
            self._current_row, COL_EXCLUDE, 1, 8
        )
        self._current_row += 1

        # Subject financial data row
        r = self._current_row
        self.lbl_subject_name_inline = QLabel("Subject Financial Data")
        self.grid.addWidget(self.lbl_subject_name_inline, r, COL_EXCLUDE, 1, 4)

        self.subject_metric_labels = []
        for col in METRIC_COLS:
            lbl = QLabel("NA")
            lbl.setAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            self.grid.addWidget(lbl, r, col)
            self.subject_metric_labels.append(lbl)

        self._current_row += 1

        # Indicated BEV rows
        self.indicated_bev_low_labels = []
        self.indicated_bev_high_labels = []

        for label_text, lbls_list in [
            ("Indicated BEV — High",  self.indicated_bev_high_labels),
            ("Indicated BEV — Low", self.indicated_bev_low_labels),
        ]:
            r = self._current_row
            self.grid.addWidget(QLabel(label_text), r, COL_EXCLUDE, 1, 4)

            for col in METRIC_COLS:
                lbl = QLabel("NA")
                lbl.setAlignment(
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                )
                self.grid.addWidget(lbl, r, col)
                lbls_list.append(lbl)

            self._current_row += 1

        self.grid.addWidget(_make_hrule(), self._current_row, COL_EXCLUDE, 1, 8)
        self._current_row += 1

    def _build_weighting_section(self):
        self._add_section_label(
            "Weighting",
            self._current_row, COL_EXCLUDE, 1, 8
        )
        self._current_row += 1

        # Weighting inputs
        r = self._current_row
        self.grid.addWidget(QLabel("Weighting"), r, COL_EXCLUDE, 1, 4)

        self.weight_inputs = []
        default_weight = f"{100 / MAX_COLS:.1f}%"
        for col in METRIC_COLS:
            inp = PctInputEdit(placeholder="e.g. 33.3%", width=W_METRIC - 10)
            inp.setText(default_weight)
            inp.editingFinished.connect(self._on_inputs_changed)
            self.weight_inputs.append(inp)
            self.grid.addWidget(
                inp, r, col,
                alignment=Qt.AlignmentFlag.AlignRight
            )

        self._current_row += 1

        # FMV BEV rows (calculations — black)
        self.fmv_low_label = QLabel("NA")
        self.fmv_high_label = QLabel("NA")

        for label_text, lbl in [
            ("FMV BEV — High",  self.fmv_high_label),
            ("FMV BEV — Low", self.fmv_low_label),
        ]:
            r = self._current_row
            self.grid.addWidget(QLabel(label_text), r, COL_EXCLUDE, 1, 4)
            lbl.setAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            self.grid.addWidget(lbl, r, COL_M0)
            self._current_row += 1

        self.grid.addWidget(_make_hrule(), self._current_row, COL_EXCLUDE, 1, 8)
        self._current_row += 1

    def _build_bridge_section(self):
        self._add_section_label(
            "Bridge",
            self._current_row, COL_EXCLUDE, 1, 8
        )
        self._current_row += 1

        r = self._current_row
        low_hdr = QLabel("Low")
        high_hdr = QLabel("High")
        for hdr in (low_hdr, high_hdr):
            hdr.setStyleSheet(get_bold_style())
            hdr.setAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
        self.grid.addWidget(high_hdr, r, COL_M0)
        self.grid.addWidget(low_hdr, r, COL_M1)
        self._bridge_low_high_headers = [low_hdr, high_hdr]
        self._current_row += 1

        bridge_rows = [
            ("FMV BEV",                                            "fmv_bev_start"),
            ("Less: Total Debt",                                   "total_debt"),
            ("FMV of Equity (marketable, controlling)",            "eq_ctrl"),
            ("Less: Discount for Lack of Control",                 "dloc_pct"),
            ("FMV of Equity (marketable, noncontrolling)",         "eq_nctrl"),
            ("Plus: Total Debt",                                   "total_debt_add"),
            ("FMV of Business Enterprise (marketable, noncontrolling)", "bev_nctrl"),
        ]

        self.bridge_labels_low = {}
        self.bridge_labels_high = {}
        for label_text, key in bridge_rows:
            r = self._current_row
            self.grid.addWidget(QLabel(label_text), r, COL_EXCLUDE, 1, 5)

            low_lbl = QLabel("NA")
            high_lbl = QLabel("NA")
            for lbl in (low_lbl, high_lbl):
                lbl.setAlignment(
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                )
            self.grid.addWidget(high_lbl, r, COL_M0)
            self.grid.addWidget(low_lbl, r, COL_M1)
            self.bridge_labels_low[key] = low_lbl
            self.bridge_labels_high[key] = high_lbl
            self._current_row += 1

    def _set_even_weights(self, n_cols: int):
        """
        Reset active GT weights to equal weighting after the user
        changes How Many Multiples.

        Users may subsequently overwrite individual weights manually.
        """
        n_cols = max(1, min(n_cols, MAX_COLS))
        even_weight = f"{100.0 / n_cols:.1f}%"

        for index, inp in enumerate(self.weight_inputs):
            if index < n_cols:
                inp.setText(even_weight)
            else:
                inp.setText("")

    def _on_num_multiples_changed(self, value: int):
        """
        Number of active GT multiple columns changed.

        The newly active columns default to equal weighting.
        """
        self._set_even_weights(value)
        self._recalculate()        

    # ------------------------------------------------------------------
    # CALCULATION ENGINE
    # ------------------------------------------------------------------

    def _on_inputs_changed(self):
        self._recalculate()

    def _recalculate(self):
        inputs = self.get_project_inputs_callback()
        transactions = inputs.gt_transactions
        n_cols = self.num_multiples_spin.value()

        # Header
        self.lbl_client.setText(inputs.client)
        self.lbl_subject.setText(inputs.subject_company_name)
        self.lbl_date.setText(f"As of {inputs.valuation_date}")
        self.lbl_subject_name_inline.setText(
            f"{inputs.subject_company_name} Financial Data"
        )

        # Show/hide metric columns
        for i, col in enumerate(METRIC_COLS):
            visible = i < n_cols
            self.metric_combos[i].setVisible(visible)
            for stat in self.stat_label_widgets:
                self.stat_label_widgets[stat][i].setVisible(visible)
            self.selected_low_inputs[i].setVisible(visible)
            self.selected_high_inputs[i].setVisible(visible)
            self.subject_metric_labels[i].setVisible(visible)
            self.indicated_bev_low_labels[i].setVisible(visible)
            self.indicated_bev_high_labels[i].setVisible(visible)
            self.weight_inputs[i].setVisible(visible)
            for row in range(MAX_ROWS):
                self.tx_mult_labels[row][i].setVisible(visible)

        # Transaction rows
        multiples_per_col = [[] for _ in range(n_cols)]

        for row in range(MAX_ROWS):
            excluded = self.tx_exclude_checks[row].isChecked()

            if row < len(transactions):
                tx = transactions[row]
                grey = get_excluded_row_style() if excluded else get_included_row_style()

                self.tx_row_labels[row]["closing_date"].setText(tx.closing_date)
                self.tx_row_labels[row]["target"].setText(tx.target)
                self.tx_row_labels[row]["acquirer"].setText(tx.acquirer)

                for lbl in self.tx_row_labels[row].values():
                    lbl.setStyleSheet(grey)

                for col_idx in range(n_cols):
                    metric = self.metric_combos[col_idx].currentText()
                    if excluded:
                        self.tx_mult_labels[row][col_idx].setText("NM")
                        self.tx_mult_labels[row][col_idx].setStyleSheet(
                            get_excluded_row_style()
                        )
                    else:
                        multiple = tx.implied_multiple(metric)
                        self.tx_mult_labels[row][col_idx].setText(
                            _fmt_multiple(multiple)
                        )
                        self.tx_mult_labels[row][col_idx].setStyleSheet(
                            get_included_row_style()
                        )
                        if multiple is not None:
                            multiples_per_col[col_idx].append(multiple)
            else:
                for key in ["closing_date", "target", "acquirer"]:
                    self.tx_row_labels[row][key].setText("")
                for col_idx in range(MAX_COLS):
                    self.tx_mult_labels[row][col_idx].setText("")

        # Statistics
        stat_funcs = {
            "Maximum":        lambda v: max(v),
            "Third Quartile": lambda v: _quartile(v, 0.75),
            "Average":        lambda v: sum(v) / len(v),
            "Median":         lambda v: statistics.median(v),
            "First Quartile": lambda v: _quartile(v, 0.25),
            "Minimum":        lambda v: min(v),
        }

        # Raw (unformatted) stat values per column, captured alongside
        # the display-label loop below, for the candlestick chart —
        # avoids re-parsing "3.81x"/"NA" strings back out of QLabels.
        chart_max, chart_q3, chart_q1, chart_min = [], [], [], []

        for stat, func in stat_funcs.items():
            for col_idx in range(n_cols):
                vals = multiples_per_col[col_idx]
                result = None
                if vals:
                    try:
                        result = func(vals)
                        self.stat_label_widgets[stat][col_idx].setText(
                            _fmt_multiple(result)
                        )
                    except Exception:
                        self.stat_label_widgets[stat][col_idx].setText("NA")
                else:
                    self.stat_label_widgets[stat][col_idx].setText("NA")

                if stat == "Maximum":
                    chart_max.append(result)
                elif stat == "Third Quartile":
                    chart_q3.append(result)
                elif stat == "First Quartile":
                    chart_q1.append(result)
                elif stat == "Minimum":
                    chart_min.append(result)

        # Subject metrics — pulled from StockAnalysis (public) or PrivateFinancials (private)
        subject_metrics = self._get_subject_metrics(inputs, n_cols)
        for col_idx in range(n_cols):
            val = subject_metrics[col_idx]
            self.subject_metric_labels[col_idx].setText(
                _fmt_currency(val) if val is not None else "NA"
            )

        # Indicated BEV
        indicated_low = []
        indicated_high = []

        for col_idx in range(n_cols):
            subj = subject_metrics[col_idx]
            sel_low = _parse_float(self.selected_low_inputs[col_idx].text())
            sel_high = _parse_float(self.selected_high_inputs[col_idx].text())

            if subj is not None and sel_low is not None:
                bev_low = subj * sel_low
                self.indicated_bev_low_labels[col_idx].setText(
                    _fmt_currency(bev_low)
                )
                indicated_low.append(bev_low)
            else:
                self.indicated_bev_low_labels[col_idx].setText("NA")
                indicated_low.append(None)

            if subj is not None and sel_high is not None:
                bev_high = subj * sel_high
                self.indicated_bev_high_labels[col_idx].setText(
                    _fmt_currency(bev_high)
                )
                indicated_high.append(bev_high)
            else:
                self.indicated_bev_high_labels[col_idx].setText("NA")
                indicated_high.append(None)

        # Weighted FMV
        weights = [
            _parse_pct(self.weight_inputs[i].text()) for i in range(n_cols)
        ]

        fmv_low = _weighted_sum(indicated_low, weights)
        fmv_high = _weighted_sum(indicated_high, weights)

        self.fmv_low_label.setText(
            _fmt_currency(fmv_low) if fmv_low is not None else "NA"
        )
        self.fmv_high_label.setText(
            _fmt_currency(fmv_high) if fmv_high is not None else "NA"
        )

        self.bridge_labels_low["fmv_bev_start"].setText(
            _fmt_currency(fmv_low) if fmv_low is not None else "NA"
        )
        self.bridge_labels_high["fmv_bev_start"].setText(
            _fmt_currency(fmv_high) if fmv_high is not None else "NA"
        )

        # Equity bridge
        dloc = _parse_pct(self.dloc_input.text())

        try:
            debt = self._get_subject_debt()
        except Exception:
            debt = None

        debt_str = _fmt_currency(debt) if debt is not None else "NA"
        self.bridge_labels_low["total_debt"].setText(debt_str)
        self.bridge_labels_high["total_debt"].setText(debt_str)

        eq_ctrl_low = (
            fmv_low - debt if fmv_low is not None and debt is not None else None
        )
        eq_ctrl_high = (
            fmv_high - debt if fmv_high is not None and debt is not None else None
        )
        self.bridge_labels_low["eq_ctrl"].setText(
            _fmt_currency(eq_ctrl_low) if eq_ctrl_low is not None else "NA"
        )
        self.bridge_labels_high["eq_ctrl"].setText(
            _fmt_currency(eq_ctrl_high) if eq_ctrl_high is not None else "NA"
        )

        dloc_str = _fmt_pct_display(dloc)
        self.bridge_labels_low["dloc_pct"].setText(dloc_str)
        self.bridge_labels_high["dloc_pct"].setText(dloc_str)
        
        eq_nctrl_low = (
            eq_ctrl_low * (1 - dloc)
            if eq_ctrl_low is not None and dloc is not None else None
        )
        eq_nctrl_high = (
            eq_ctrl_high * (1 - dloc)
            if eq_ctrl_high is not None and dloc is not None else None
        )
        self.bridge_labels_low["eq_nctrl"].setText(
            _fmt_currency(eq_nctrl_low) if eq_nctrl_low is not None else "NA"
        )
        self.bridge_labels_high["eq_nctrl"].setText(
            _fmt_currency(eq_nctrl_high) if eq_nctrl_high is not None else "NA"
        )

        self.bridge_labels_low["total_debt_add"].setText(debt_str)
        self.bridge_labels_high["total_debt_add"].setText(debt_str)

        bev_nctrl_low = (
            eq_nctrl_low + debt
            if eq_nctrl_low is not None and debt is not None else None
        )
        bev_nctrl_high = (
            eq_nctrl_high + debt
            if eq_nctrl_high is not None and debt is not None else None
        )
        self.bridge_labels_low["bev_nctrl"].setText(
            _fmt_currency(bev_nctrl_low) if bev_nctrl_low is not None else "NA"
        )
        self.bridge_labels_high["bev_nctrl"].setText(
            _fmt_currency(bev_nctrl_high) if bev_nctrl_high is not None else "NA"
        )

        chart_labels = [
            self.metric_combos[i].currentText() for i in range(n_cols)
        ]
        if self._chart_dialog is not None:
            self._chart_dialog.update_data(
                chart_labels, chart_q3, chart_max, chart_min, chart_q1
            )

    def _get_subject_metrics(self, inputs, n_cols) -> list:
        """
        Returns subject company metric value per active column.
        Metric order matches METRICS list: TTM Revenue, TTM EBITDA, TTM EBIT.
        Sourced through Subject Financials' get_metric_value — same
        single source of truth GPC uses — rather than reading
        StockAnalysis/PrivateFinancials directly.
        """
        METRIC_LINE_KEYS = {
            "TTM Revenue": "revenue",
            "TTM EBITDA":  "ebitda",
            "TTM EBIT":    "ebit",
        }

        results = []
        for col_idx in range(n_cols):
            metric = self.metric_combos[col_idx].currentText()
            line_key = METRIC_LINE_KEYS.get(metric)
            val = self._get_subject_metric_value(line_key, "TTM") if line_key else None
            results.append(val)

        return results