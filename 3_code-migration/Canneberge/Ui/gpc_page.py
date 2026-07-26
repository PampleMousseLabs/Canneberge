import statistics
from typing import Optional, List, Dict

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
)
from PyQt6.QtCore import Qt

from Canneberge.Calculations.gpc_metrics import (
    GPC_METRICS,
    CUSTOM_MULTIPLE_LABEL,
    dropdown_options,
    get_metric,
)
from Canneberge.Calculations.gpc_multiples import (
    compute_all_gpc_multiples,
    get_ticker_bevs,
)

MAX_COLS = 7          # matches MultipleCount named range
MAX_ROWS = 15          # matches the 15-row GPC ticker grid on Home page

# Column indices — same single-schema pattern as gt_page.py.
# No Target/Acquirer columns here — replaced by one Company Name column.
COL_EXCLUDE = 0
COL_NUM = 1
COL_TICKER = 2
COL_COMPANY = 3
COL_M_START = 4
METRIC_COLS = list(range(COL_M_START, COL_M_START + MAX_COLS))

W_EXCLUDE = 55
W_NUM = 30
W_TICKER = 70
W_METRIC = 110

INPUT_STYLE = "background-color: #dce9f7; color: #1a4a8a;"
CALC_STYLE = "color: black;"
SECTION_HEADER_STYLE = "font-weight: bold; font-size: 11px;"


def _parse_float(text: str) -> Optional[float]:
    text = str(text).strip().replace(",", "").replace("x", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _parse_pct(text: str) -> Optional[float]:
    text = str(text).strip().replace(",", "")
    if not text:
        return None
    try:
        if "%" in text:
            return float(text.replace("%", "")) / 100
        val = float(text)
        return val / 100 if val > 1 else val
    except ValueError:
        return None


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
    lbl.setStyleSheet(SECTION_HEADER_STYLE)
    return lbl


class MultipleInputEdit(QLineEdit):
    """Same widget as gt_page.py's version — formats ##.##x on focus-out."""
    def __init__(self, placeholder="", parent=None):
        super().__init__(parent)
        self.setPlaceholderText(placeholder)
        self.setStyleSheet(INPUT_STYLE)
        self.setFixedWidth(W_METRIC - 10)
        self.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.editingFinished.connect(self._format_value)

    def _format_value(self):
        val = _parse_float(self.text())
        if val is not None:
            self.setText(f"{val:.2f}x")


class PctInputEdit(QLineEdit):
    """Same widget as gt_page.py's version — formats ##.#% on focus-out."""
    def __init__(self, placeholder="", parent=None):
        super().__init__(parent)
        self.setPlaceholderText(placeholder)
        self.setStyleSheet(INPUT_STYLE)
        self.setFixedWidth(W_METRIC - 10)
        self.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.editingFinished.connect(self._format_value)

    def _format_value(self):
        val = _parse_pct(self.text())
        if val is not None:
            self.setText(f"{val*100:.1f}%")


class CurrencyInputEdit(QLineEdit):
    """
    New widget, not in gt_page.py. Used when a column is set to
    Custom Multiple — the Subject Company Financial Data cell for
    that column needs to accept a typed number (no metric to pull),
    formatted like currency rather than a multiple.
    """
    def __init__(self, placeholder="", parent=None):
        super().__init__(parent)
        self.setPlaceholderText(placeholder)
        self.setStyleSheet(INPUT_STYLE)
        self.setFixedWidth(W_METRIC - 10)
        self.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.editingFinished.connect(self._format_value)

    def _format_value(self):
        val = _parse_float(self.text())
        if val is not None:
            self.setText(f"{val:,.0f}")


class GPCPage(QWidget):
    """
    Guideline Public Company analysis page.
    Structurally mirrors GTPage: single QGridLayout column schema,
    same Statistics/Selected Multiples/Subject/Weighting/Equity Bridge
    section flow. Differs from GT in:
      - rows are GPC tickers (from ProjectInputs.gpc_tickers), not
        manually-entered transactions
      - up to 7 metric columns instead of 3
      - each column's dropdown includes "Custom Multiple" — when
        selected, that column's per-ticker cells AND the Subject
        Company Financial Data cell become editable inputs instead
        of computed values
      - Control Premium input, no GT equivalent
      - no per-row exclude labels grey out target/acquirer text since
        there's no target/acquirer here — only the ticker/company name
    """

    def __init__(self, get_project_inputs_callback,
                 get_stockanalysis_results_callback,
                 get_private_financials_callback,
                 get_subject_debt):
        super().__init__()
        self.get_project_inputs_callback = get_project_inputs_callback
        self._get_stockanalysis_results_callback = get_stockanalysis_results_callback
        self._get_private_financials_callback = get_private_financials_callback
        self._get_subject_debt = get_subject_debt

        # Per-column Custom Multiple state, keyed by column index.
        # When True, that column's ticker cells + subject cell are
        # editable widgets instead of computed labels.
        self._custom_mode = [False] * MAX_COLS

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
        for col in METRIC_COLS:
            self.grid.setColumnMinimumWidth(col, W_METRIC)

        self.grid.setColumnStretch(COL_COMPANY, 2)

        self._current_row = 0
        self._build_header()
        self._build_controls()
        self._build_ticker_section()
        self._build_statistics_section()
        self._build_selected_multiples_section()
        self._build_subject_section()
        self._build_weighting_section()
        self._build_equity_bridge_section()

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
        self.lbl_method = QLabel("Guideline Public Company Method")
        self.lbl_method.setStyleSheet("font-weight: bold;")
        self.lbl_date = QLabel()
        self.lbl_date.setStyleSheet("font-weight: bold;")

        self.grid.addWidget(self.lbl_client,  r, COL_EXCLUDE, 1, 2)
        self.grid.addWidget(self.lbl_subject, r, COL_TICKER,  1, 1)
        self.grid.addWidget(self.lbl_method,  r, COL_COMPANY, 1, 2)
        self.grid.addWidget(self.lbl_date,    r, COL_M_START, 1, 2)
        self._current_row += 1

    def _build_controls(self):
        r = self._current_row

        spin_label = QLabel("How Many Multiples:")
        self.num_multiples_spin = QSpinBox()
        self.num_multiples_spin.setMinimum(1)
        self.num_multiples_spin.setMaximum(MAX_COLS)
        self.num_multiples_spin.setValue(MAX_COLS)
        self.num_multiples_spin.setStyleSheet(INPUT_STYLE)
        self.num_multiples_spin.setFixedWidth(55)
        self.num_multiples_spin.valueChanged.connect(self._on_inputs_changed)

        self.grid.addWidget(spin_label,             r, COL_EXCLUDE, 1, 2)
        self.grid.addWidget(self.num_multiples_spin, r, COL_TICKER)
        self._current_row += 1

        r = self._current_row
        dloc_label = QLabel("Discount for Lack of Control:")
        self.dloc_input = QLineEdit("19.4%")
        self.dloc_input.setFixedWidth(70)
        self.dloc_input.setStyleSheet(INPUT_STYLE)
        self.dloc_input.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.dloc_input.editingFinished.connect(self._on_inputs_changed)

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

        # Control Premium — no GT equivalent
        r = self._current_row
        cp_label = QLabel("Control Premium:")
        self.control_premium_input = QLineEdit("24.0%")
        self.control_premium_input.setFixedWidth(70)
        self.control_premium_input.setStyleSheet(INPUT_STYLE)
        self.control_premium_input.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.control_premium_input.editingFinished.connect(self._on_inputs_changed)

        cp_row = QHBoxLayout()
        cp_row.setContentsMargins(0, 0, 0, 0)
        cp_row.setSpacing(6)
        cp_row.addWidget(cp_label)
        cp_row.addWidget(self.control_premium_input)
        cp_row.addStretch()
        cp_container = QWidget()
        cp_container.setLayout(cp_row)

        self.grid.addWidget(
            cp_container, r, COL_EXCLUDE, 1, 4,
            alignment=Qt.AlignmentFlag.AlignLeft
        )
        self._current_row += 1

        # Spacer
        self.grid.addWidget(QLabel(""), self._current_row, 0)
        self._current_row += 1

    def _build_ticker_section(self):
        r = self._current_row

        self.grid.addWidget(
            _make_section_label("Guideline Public Company Multiple(s)"),
            r, COL_EXCLUDE, 1, MAX_COLS + 4
        )
        self._current_row += 1
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

        # Metric dropdown headers — options = catalogue + Custom Multiple
        self.metric_combos = []
        for i, col in enumerate(METRIC_COLS):
            combo = QComboBox()
            combo.addItems(dropdown_options())
            combo.setCurrentIndex(i if i < len(GPC_METRICS) else 0)
            combo.setStyleSheet(INPUT_STYLE)
            combo.setFixedWidth(W_METRIC - 5)
            combo.currentIndexChanged.connect(self._on_metric_combo_changed)
            self.metric_combos.append(combo)
            self.grid.addWidget(combo, r, col)

        self._current_row += 1

        # Ticker rows
        self.tick_exclude_checks = []
        self.tick_row_labels = []      # {"ticker": lbl, "company": lbl} per row
        self.tick_mult_labels = []     # computed QLabel per row per col
        self.tick_mult_inputs = []     # editable QLineEdit per row per col (Custom Multiple)

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
            self.tick_row_labels.append({
                "ticker": ticker_lbl,
                "company": company_lbl,
            })

            mult_lbls = []
            mult_inputs = []
            for col in METRIC_COLS:
                lbl = QLabel("NA")
                lbl.setAlignment(
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                )
                self.grid.addWidget(lbl, r, col)
                mult_lbls.append(lbl)

                inp = MultipleInputEdit(placeholder="e.g. 4.0x")
                inp.editingFinished.connect(self._on_inputs_changed)
                inp.setVisible(False)
                self.grid.addWidget(inp, r, col)
                mult_inputs.append(inp)

            self.tick_mult_labels.append(mult_lbls)
            self.tick_mult_inputs.append(mult_inputs)
            self._current_row += 1

        self.grid.addWidget(
            _make_hrule(), self._current_row, COL_EXCLUDE, 1, MAX_COLS + 4
        )
        self._current_row += 1

    def _build_statistics_section(self):
        self.grid.addWidget(
            _make_section_label("Statistics"),
            self._current_row, COL_EXCLUDE, 1, MAX_COLS + 4
        )
        self._current_row += 1

        stat_names = ["Maximum", "Third Quartile", "Average",
                      "Median", "First Quartile", "Minimum"]
        self.stat_label_widgets = {}

        for stat in stat_names:
            r = self._current_row
            self.grid.addWidget(QLabel(stat), r, COL_EXCLUDE, 1, 3)

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

        self.grid.addWidget(
            _make_hrule(), self._current_row, COL_EXCLUDE, 1, MAX_COLS + 4
        )
        self._current_row += 1

    def _build_selected_multiples_section(self):
        self.grid.addWidget(
            _make_section_label("Selected Multiples"),
            self._current_row, COL_EXCLUDE, 1, MAX_COLS + 4
        )
        self._current_row += 1

        self.selected_low_inputs = []
        self.selected_high_inputs = []

        for label_text, inputs_list in [
            ("Selected Multiple — High", self.selected_high_inputs),
            ("Selected Multiple — Low",  self.selected_low_inputs),
        ]:
            r = self._current_row
            self.grid.addWidget(QLabel(label_text), r, COL_EXCLUDE, 1, 3)

            for col in METRIC_COLS:
                inp = MultipleInputEdit(placeholder="e.g. 4.0x")
                inp.editingFinished.connect(self._on_inputs_changed)
                inputs_list.append(inp)
                self.grid.addWidget(
                    inp, r, col,
                    alignment=Qt.AlignmentFlag.AlignRight
                )

            self._current_row += 1

        self.grid.addWidget(
            _make_hrule(), self._current_row, COL_EXCLUDE, 1, MAX_COLS + 4
        )
        self._current_row += 1

    def _build_subject_section(self):
        self.grid.addWidget(
            _make_section_label("Subject Company"),
            self._current_row, COL_EXCLUDE, 1, MAX_COLS + 4
        )
        self._current_row += 1

        r = self._current_row
        self.lbl_subject_name_inline = QLabel("Subject Financial Data")
        self.grid.addWidget(self.lbl_subject_name_inline, r, COL_EXCLUDE, 1, 3)

        # Both a computed label AND an editable input exist per column;
        # only one is visible at a time depending on Custom Multiple state.
        self.subject_metric_labels = []
        self.subject_metric_inputs = []
        for col in METRIC_COLS:
            lbl = QLabel("NA")
            lbl.setAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            self.grid.addWidget(lbl, r, col)
            self.subject_metric_labels.append(lbl)

            inp = CurrencyInputEdit(placeholder="e.g. 1000")
            inp.editingFinished.connect(self._on_inputs_changed)
            inp.setVisible(False)
            self.grid.addWidget(inp, r, col)
            self.subject_metric_inputs.append(inp)

        self._current_row += 1

        self.indicated_bev_low_labels = []
        self.indicated_bev_high_labels = []

        for label_text, lbls_list in [
            ("Indicated BEV — High", self.indicated_bev_high_labels),
            ("Indicated BEV — Low",  self.indicated_bev_low_labels),
        ]:
            r = self._current_row
            self.grid.addWidget(QLabel(label_text), r, COL_EXCLUDE, 1, 3)

            for col in METRIC_COLS:
                lbl = QLabel("NA")
                lbl.setAlignment(
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                )
                self.grid.addWidget(lbl, r, col)
                lbls_list.append(lbl)

            self._current_row += 1

        self.grid.addWidget(
            _make_hrule(), self._current_row, COL_EXCLUDE, 1, MAX_COLS + 4
        )
        self._current_row += 1

    def _build_weighting_section(self):
        self.grid.addWidget(
            _make_section_label("Weighting"),
            self._current_row, COL_EXCLUDE, 1, MAX_COLS + 4
        )
        self._current_row += 1

        r = self._current_row
        self.grid.addWidget(QLabel("Weighting"), r, COL_EXCLUDE, 1, 3)

        self.weight_inputs = []
        default_weight = f"{100 / MAX_COLS:.1f}%"
        for col in METRIC_COLS:
            inp = PctInputEdit(placeholder="e.g. 14.3%")
            inp.setText(default_weight)
            inp.editingFinished.connect(self._on_inputs_changed)
            self.weight_inputs.append(inp)
            self.grid.addWidget(
                inp, r, col,
                alignment=Qt.AlignmentFlag.AlignRight
            )

        self._current_row += 1

        self.fmv_low_label = QLabel("NA")
        self.fmv_high_label = QLabel("NA")

        for label_text, lbl in [
            ("FMV BEV — High", self.fmv_high_label),
            ("FMV BEV — Low",  self.fmv_low_label),
        ]:
            r = self._current_row
            self.grid.addWidget(QLabel(label_text), r, COL_EXCLUDE, 1, 3)
            lbl.setAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            self.grid.addWidget(lbl, r, COL_M_START)
            self._current_row += 1

        self.grid.addWidget(
            _make_hrule(), self._current_row, COL_EXCLUDE, 1, MAX_COLS + 4
        )
        self._current_row += 1

    def _build_equity_bridge_section(self):
        self.grid.addWidget(
            _make_section_label("Equity Bridge"),
            self._current_row, COL_EXCLUDE, 1, MAX_COLS + 4
        )
        self._current_row += 1

        r = self._current_row
        low_hdr = QLabel("Low")
        high_hdr = QLabel("High")
        for hdr in (low_hdr, high_hdr):
            hdr.setStyleSheet("font-weight: bold;")
            hdr.setAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
        self.grid.addWidget(high_hdr, r, COL_M_START)
        self.grid.addWidget(low_hdr, r, COL_M_START + 1)
        self._current_row += 1

        # Same bridge structure as GT, plus a Control Premium step
        # after the noncontrolling equity line — GPC values start
        # noncontrolling (public market prices) and need a premium
        # added to reach a controlling basis, opposite direction from
        # GT's DLOC step. Both DLOC and Control Premium are exposed
        # as inputs; only one is typically nonzero depending on the
        # basis of value, but both are computed so the model doesn't
        # silently assume which one applies.
        bridge_rows = [
            ("Plus: Control Premium",                                    "control_premium_pct"),
            ("FMV of Equity (marketable, controlling)",                  "eq_ctrl"),
            ("Less: Discount for Lack of Control",                       "dloc_pct"),
            ("FMV of Equity (marketable, noncontrolling)",               "eq_nctrl"),
            ("Plus: Total Debt",                                         "total_debt_add"),
            ("FMV of Business Enterprise (marketable, noncontrolling)",  "bev_nctrl"),
        ]

        self.bridge_labels_low = {}
        self.bridge_labels_high = {}
        for label_text, key in bridge_rows:
            r = self._current_row
            self.grid.addWidget(QLabel(label_text), r, COL_EXCLUDE, 1, 4)

            low_lbl = QLabel("NA")
            high_lbl = QLabel("NA")
            for lbl in (low_lbl, high_lbl):
                lbl.setAlignment(
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                )
            self.grid.addWidget(high_lbl, r, COL_M_START)
            self.grid.addWidget(low_lbl, r, COL_M_START + 1)
            self.bridge_labels_low[key] = low_lbl
            self.bridge_labels_high[key] = high_lbl
            self._current_row += 1

    # ------------------------------------------------------------------
    # CUSTOM MULTIPLE MODE HANDLING
    # ------------------------------------------------------------------

    def _on_metric_combo_changed(self, _index=None):
        for i, combo in enumerate(self.metric_combos):
            self._custom_mode[i] = (combo.currentText() == CUSTOM_MULTIPLE_LABEL)
        self._recalculate()

    def _apply_custom_mode_visibility(self, n_cols: int):
        """
        Swap computed label <-> editable input visibility per column
        based on whether that column is in Custom Multiple mode.
        Only touches columns 0..n_cols-1; columns beyond n_cols are
        hidden entirely by the existing visible/n_cols logic elsewhere.
        """
        for i in range(MAX_COLS):
            is_custom = self._custom_mode[i] and i < n_cols
            for row in range(MAX_ROWS):
                self.tick_mult_labels[row][i].setVisible(not is_custom and i < n_cols)
                self.tick_mult_inputs[row][i].setVisible(is_custom)
            self.subject_metric_labels[i].setVisible(not is_custom and i < n_cols)
            self.subject_metric_inputs[i].setVisible(is_custom)

    # ------------------------------------------------------------------
    # CALCULATION ENGINE
    # ------------------------------------------------------------------

    def _on_inputs_changed(self):
        self._recalculate()

    def _recalculate(self):
        inputs = self.get_project_inputs_callback()
        tickers = inputs.gpc_tickers
        n_cols = self.num_multiples_spin.value()

        self.lbl_client.setText(inputs.client)
        self.lbl_subject.setText(inputs.subject_company_name)
        self.lbl_date.setText(f"As of {inputs.valuation_date}")
        self.lbl_subject_name_inline.setText(
            f"{inputs.subject_company_name} Financial Data"
        )

        # Show/hide metric columns based on n_cols
        for i, col in enumerate(METRIC_COLS):
            visible = i < n_cols
            self.metric_combos[i].setVisible(visible)
            for stat in self.stat_label_widgets:
                self.stat_label_widgets[stat][i].setVisible(visible)
            self.selected_low_inputs[i].setVisible(visible)
            self.selected_high_inputs[i].setVisible(visible)
            self.weight_inputs[i].setVisible(visible)
            for row in range(MAX_ROWS):
                self.tick_mult_labels[row][i].setVisible(
                    visible and not self._custom_mode[i]
                )
                self.tick_mult_inputs[row][i].setVisible(
                    visible and self._custom_mode[i]
                )

        self._apply_custom_mode_visibility(n_cols)

        # Pull scraped data once
        sa_results = self._get_stockanalysis_results_callback() or {}
        is_rows = sa_results.get("IS", [])
        ratio_rows = sa_results.get("Ratios", [])

        # Compute real multiples for every ticker (Custom columns are
        # simply not read from this — the user's typed value wins)
        all_multiples: Dict[str, Dict[str, Optional[float]]] = (
            compute_all_gpc_multiples(is_rows, ratio_rows, tickers)
            if tickers else {}
        )
        bevs = get_ticker_bevs(ratio_rows, tickers) if tickers else {}

        multiples_per_col = [[] for _ in range(n_cols)]

        for row in range(MAX_ROWS):
            excluded = self.tick_exclude_checks[row].isChecked()

            if row < len(tickers):
                ticker = tickers[row]
                grey = "color: grey;" if excluded else "color: black;"

                self.tick_row_labels[row]["ticker"].setText(ticker)
                # Company name isn't in this callback chain yet — left
                # blank until GT/GPC gets a shared ticker->name lookup.
                # TODO: wire company name once available (see home_page.py
                # gpc_name_edits — that data currently lives only in the
                # Home page UI, not in ProjectInputs).
                self.tick_row_labels[row]["company"].setText("")

                for lbl in self.tick_row_labels[row].values():
                    lbl.setStyleSheet(grey)

                for col_idx in range(n_cols):
                    if self._custom_mode[col_idx]:
                        # User-typed value — read directly, no computation
                        multiple = _parse_float(
                            self.tick_mult_inputs[row][col_idx].text()
                        )
                    elif excluded:
                        multiple = None
                    else:
                        metric_name = self.metric_combos[col_idx].currentText()
                        multiple = (all_multiples.get(ticker, {}) or {}).get(metric_name)

                    if excluded and not self._custom_mode[col_idx]:
                        self.tick_mult_labels[row][col_idx].setText("NM")
                        self.tick_mult_labels[row][col_idx].setStyleSheet("color: grey;")
                    elif not self._custom_mode[col_idx]:
                        self.tick_mult_labels[row][col_idx].setText(_fmt_multiple(multiple))
                        self.tick_mult_labels[row][col_idx].setStyleSheet("color: black;")

                    if multiple is not None and not excluded:
                        multiples_per_col[col_idx].append(multiple)
            else:
                self.tick_row_labels[row]["ticker"].setText("")
                self.tick_row_labels[row]["company"].setText("")
                for col_idx in range(MAX_COLS):
                    self.tick_mult_labels[row][col_idx].setText("")

        # Statistics
        stat_funcs = {
            "Maximum":        lambda v: max(v),
            "Third Quartile": lambda v: _quartile(v, 0.75),
            "Average":        lambda v: sum(v) / len(v),
            "Median":         lambda v: statistics.median(v),
            "First Quartile": lambda v: _quartile(v, 0.25),
            "Minimum":        lambda v: min(v),
        }

        for stat, func in stat_funcs.items():
            for col_idx in range(n_cols):
                vals = multiples_per_col[col_idx]
                if vals:
                    try:
                        self.stat_label_widgets[stat][col_idx].setText(
                            _fmt_multiple(func(vals))
                        )
                    except Exception:
                        self.stat_label_widgets[stat][col_idx].setText("NA")
                else:
                    self.stat_label_widgets[stat][col_idx].setText("NA")

        # Subject metrics — computed columns pull from StockAnalysis/Private,
        # Custom columns read the user-typed CurrencyInputEdit directly.
        subject_metrics = self._get_subject_metrics(inputs, n_cols)
        for col_idx in range(n_cols):
            if self._custom_mode[col_idx]:
                continue  # value comes straight from the input widget, no label to set
            val = subject_metrics[col_idx]
            self.subject_metric_labels[col_idx].setText(
                _fmt_currency(val) if val is not None else "NA"
            )

        # Indicated BEV
        indicated_low = []
        indicated_high = []

        for col_idx in range(n_cols):
            if self._custom_mode[col_idx]:
                subj = _parse_float(self.subject_metric_inputs[col_idx].text())
            else:
                subj = subject_metrics[col_idx]

            sel_low = _parse_float(self.selected_low_inputs[col_idx].text())
            sel_high = _parse_float(self.selected_high_inputs[col_idx].text())

            if subj is not None and sel_low is not None:
                bev_low = subj * sel_low
                self.indicated_bev_low_labels[col_idx].setText(_fmt_currency(bev_low))
                indicated_low.append(bev_low)
            else:
                self.indicated_bev_low_labels[col_idx].setText("NA")
                indicated_low.append(None)

            if subj is not None and sel_high is not None:
                bev_high = subj * sel_high
                self.indicated_bev_high_labels[col_idx].setText(_fmt_currency(bev_high))
                indicated_high.append(bev_high)
            else:
                self.indicated_bev_high_labels[col_idx].setText("NA")
                indicated_high.append(None)

        # Weighted FMV
        weights = [_parse_pct(self.weight_inputs[i].text()) for i in range(n_cols)]

        fmv_low = _weighted_sum(indicated_low, weights)
        fmv_high = _weighted_sum(indicated_high, weights)

        self.fmv_low_label.setText(_fmt_currency(fmv_low) if fmv_low is not None else "NA")
        self.fmv_high_label.setText(_fmt_currency(fmv_high) if fmv_high is not None else "NA")

        # Equity bridge — GPC direction: FMV BEV is already on a
        # noncontrolling, marketable, minority basis (public market
        # prices for a minority stake). To reach a controlling basis,
        # ADD control premium; to reduce back to noncontrolling, apply
        # DLOC. Both inputs exposed; each combination is computed but
        # it's on the user to know which basis their conclusion needs.
        dloc = _parse_pct(self.dloc_input.text())
        control_premium = _parse_pct(self.control_premium_input.text())

        try:
            debt = self._get_subject_debt()
        except Exception:
            debt = None

        cp_str = _fmt_pct_display(control_premium)
        self.bridge_labels_low["control_premium_pct"].setText(cp_str)
        self.bridge_labels_high["control_premium_pct"].setText(cp_str)

        eq_ctrl_low = (
            fmv_low * (1 + control_premium)
            if fmv_low is not None and control_premium is not None else None
        )
        eq_ctrl_high = (
            fmv_high * (1 + control_premium)
            if fmv_high is not None and control_premium is not None else None
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

        debt_str = _fmt_currency(debt) if debt is not None else "NA"
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

    def _get_subject_metrics(self, inputs, n_cols) -> list:
        """
        Returns subject company metric value per active column, for
        whichever GPC_METRICS entry is selected in that column's dropdown.
        Custom Multiple columns return None here — caller must read the
        editable CurrencyInputEdit directly instead.
        """
        # Line keys currently available on the private-company IS form.
        # See app_state.py IS_LINES for the authoritative list.
        PRIVATE_LINE_KEYS = {"revenue", "ebitda", "ebit"}

        results = []

        for col_idx in range(n_cols):
            if self._custom_mode[col_idx]:
                results.append(None)
                continue

            metric_name = self.metric_combos[col_idx].currentText()
            metric = get_metric(metric_name)
            val = None

            if metric is None:
                results.append(None)
                continue

            if inputs.is_private:
                pf = self._get_private_financials_callback()
                if pf and metric.line_key in PRIVATE_LINE_KEYS:
                    val = pf.get_is(metric.line_key, metric.period)

            elif inputs.is_publicly_traded:
                sa_results = self._get_stockanalysis_results_callback()
                if sa_results:
                    is_rows = sa_results.get("IS", [])
                    ticker = inputs.subject_ticker.lower()
                    for row in is_rows:
                        if (str(row.get("Ticker", "")).lower() == ticker and
                                str(row.get("Line Item", "")).lower() == metric.line_key):
                            raw = row.get(metric.period)
                            if raw is not None:
                                try:
                                    val = float(str(raw).replace(",", ""))
                                except (ValueError, TypeError):
                                    val = None
                            break

            results.append(val)

        return results