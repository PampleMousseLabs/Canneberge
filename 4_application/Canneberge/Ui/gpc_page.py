import math
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

from Canneberge.Ui.theme import theme_manager
from Canneberge.Ui.shared_input_widgets import (
    MultipleInputEdit, PctInputEdit, CurrencyInputEdit,
    _parse_float, _parse_pct,
)

from Canneberge.Ui.gpc_candlestick_chart import GPCCandlestickChart

from Canneberge.Calculations.value_bridge import BridgeInputs, run_bridge
from Canneberge.Calculations.gpc_metrics import (
    GPC_METRICS,
    CUSTOM_MULTIPLE_LABEL,
    dropdown_options,
    get_metric,
)
from Canneberge.Calculations.gpc_multiples import (
    compute_all_gpc_multiples,
    get_ticker_bevs,
    get_subject_cash,
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

# =====================================================================
# STYLE — colors come from the active Theme (Canneberge/Ui/theme.py)
# via theme_manager.current. See dcf_page.py's top-of-file comment for
# the full rationale; same pattern here.
# =====================================================================


def get_input_style() -> str:
    return theme_manager.current.input_style()


def get_bold_style() -> str:
    return theme_manager.current.bold_style()


def get_section_header_style() -> str:
    # Delegates to the ONE canonical header treatment (theme.py's
    # Theme.header_style()) - DCF's bold-on-colored-bar look, now
    # used everywhere, not a GPC-specific plain-bold variant.
    return theme_manager.current.header_style()


def get_link_text_style() -> str:
    # NOTE: no longer called - chart_link now embeds color directly
    # in its HTML anchor via _chart_link_html() instead (the actual
    # fix for QLabel rich-text anchors ignoring an outer stylesheet).
    # Left in place rather than deleted, same as CALC_STYLE below.
    # chart_link is a QLabel with an HTML <a> tag doing its own
    # underline — only the text color needs to come from the theme,
    # unlike DCF's link_toggles (a QPushButton faking a link, which
    # needs the full border/background/underline treatment).
    return f"color: {theme_manager.current.link_color};"


def get_grey_disabled_style() -> str:
    return theme_manager.current.grey_disabled_style()


def get_excluded_row_style() -> str:
    # "Excluded" comp rows (checkbox ticked to drop a GPC from the
    # analysis) — dims the ticker/company text. Reuses disabled_text
    # rather than adding a new field: semantically the same
    # "de-emphasized, not currently active" role as a disabled input.
    return f"color: {theme_manager.current.disabled_text};"


def get_included_row_style() -> str:
    return f"color: {theme_manager.current.default_text};"


# NOTE: CALC_STYLE ("color: black;") exists below but is not referenced
# anywhere else in this file - confirmed via full-file search. Left in
# place rather than silently deleted; flag to Ted to confirm it's dead
# (possibly a placeholder for planned use) before removing.
CALC_STYLE = "color: black;"


def _fmt_multiple(value: Optional[float]) -> str:
    if value is None or math.isnan(value) or math.isinf(value):
        return "NA"
    return f"{value:.2f}x"


def _fmt_currency(value: Optional[float]) -> str:
    if value is None or math.isnan(value) or math.isinf(value):
        return "NA"
    return f"{value:,.0f}"


def _fmt_pct_display(value: Optional[float]) -> str:
    if value is None or math.isnan(value) or math.isinf(value):
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
    """
    Sums value*weight for every column where BOTH are present.
    Columns missing either a value or a weight are skipped entirely —
    NOT treated as zero, and remaining weights are NOT renormalized.
    Weights don't need to sum to 100%; the user may intentionally
    weight unevenly (e.g. 50/25/15/10/0). Returns None only if every
    column is missing data, since a sum of nothing isn't a real answer.
    """
    total = 0.0
    any_present = False
    for v, w in zip(values, weights):
        if v is None or w is None:
            continue
        total += v * w
        any_present = True
    return total if any_present else None


def _make_hrule() -> QFrame:
    line = QFrame()
    line.setFrameShape(QFrame.Shape.HLine)
    line.setFrameShadow(QFrame.Shadow.Sunken)
    return line


def _make_section_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(get_section_header_style())
    return lbl


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
                 get_marketscreener_results_callback,
                 get_private_financials_callback,
                 get_subject_debt,
                 get_subject_metric_value,
                 get_dashboard_bridge_values_callback=None,
                 get_nwc_surplus_callback=None):
        super().__init__()
        self._get_dashboard_bridge_values = (
            get_dashboard_bridge_values_callback or (lambda: {})
        )
        self._get_nwc_surplus = get_nwc_surplus_callback or (lambda: None)
        self._last_bridge_result = None
        self.get_project_inputs_callback = get_project_inputs_callback
        self._get_stockanalysis_results_callback = get_stockanalysis_results_callback
        self._get_marketscreener_results_callback = get_marketscreener_results_callback
        self._get_private_financials_callback = get_private_financials_callback
        self._get_subject_debt = get_subject_debt
        self._get_subject_metric_value = get_subject_metric_value

        # Per-column Custom Multiple state, keyed by column index.
        # When True, that column's ticker cells + subject cell are
        # editable widgets instead of computed labels.
        self._is_custom_multiple = [False] * MAX_COLS
        self._last_basis_mode = None
        # Per-basis memory for metric dropdowns + selected multiples +
        # weights. Flipping Home basis_of_value saves the outgoing
        # basis and restores the incoming one so EV/EBITDA 10x does
        # not silently become P/E 10x.
        self._per_basis_state = {
            "BEV": {
                "metrics": [None] * MAX_COLS,
                "low": [""] * MAX_COLS,
                "high": [""] * MAX_COLS,
                "weights": [None] * MAX_COLS,
                "visited": False,
            },
            "EQUITY": {
                "metrics": [None] * MAX_COLS,
                "low": [""] * MAX_COLS,
                "high": [""] * MAX_COLS,
                "weights": [None] * MAX_COLS,
                "visited": False,
            },
        }
        self._chart_dialog = None
        self._section_labels = []          # every _make_section_label() instance
        self._bridge_low_high_headers = []  # "Low"/"High" bold headers
        self._ticker_col_headers = []      # "Exclude"/"#"/"Ticker"/"Company Name"

        self._build_ui()
        self._recalculate()

        # Live theme switching. Section-label bars, header info row,
        # dloc/control premium inputs, and Low/High headers are
        # restyled directly here. The per-cell MultipleInputEdit /
        # PctInputEdit / CurrencyInputEdit widgets restyle themselves
        # (see their own theme_changed subscriptions above) rather
        # than being tracked in a list here. The excluded/included
        # ticker-row text colors are re-derived by _recalculate() at
        # the end, since that logic already lives there.
        theme_manager.theme_changed.connect(self._apply_theme)

    def _apply_theme(self, theme=None):
        for lbl in self._section_labels:
            lbl.setStyleSheet(get_section_header_style())
        for hdr in self._bridge_low_high_headers:
            hdr.setStyleSheet(get_bold_style())
        for lbl in self._ticker_col_headers:
            lbl.setStyleSheet(get_bold_style())

        self.lbl_client.setStyleSheet(get_bold_style())
        self.lbl_subject.setStyleSheet(get_bold_style())
        self.lbl_method.setStyleSheet(get_bold_style())
        self.lbl_date.setStyleSheet(get_bold_style())
        self.chart_link.setText(self._chart_link_html())

        self.num_multiples_spin.setStyleSheet(get_input_style())
        self.dloc_input.setStyleSheet(get_grey_disabled_style())
        self.control_premium_input.setStyleSheet(get_input_style())

        self._recalculate()

    def _add_section_label(self, text: str, row: int, col: int,
                            row_span: int = 1, col_span: int = 1):
        """
        Wraps _make_section_label() + grid placement + registration
        into one call, so a new section label can't be added to the
        page without also being captured for theme restyle - the six
        call sites below all go through this instead of calling
        _make_section_label() + addWidget() directly.
        """
        lbl = _make_section_label(text)
        self.grid.addWidget(lbl, row, col, row_span, col_span)
        self._section_labels.append(lbl)
        return lbl

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
        self._build_bridge_section()

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
        self.lbl_client.setStyleSheet(get_bold_style())
        self.lbl_subject = QLabel()
        self.lbl_subject.setStyleSheet(get_bold_style())
        self.lbl_method = QLabel("Guideline Public Company Method")
        self.lbl_method.setStyleSheet(get_bold_style())
        self.lbl_date = QLabel()
        self.lbl_date.setStyleSheet(get_bold_style())

        self.grid.addWidget(self.lbl_client,  r, COL_EXCLUDE, 1, 2)
        self.grid.addWidget(self.lbl_subject, r, COL_TICKER,  1, 1)
        self.grid.addWidget(self.lbl_method,  r, COL_COMPANY, 1, 2)
        self.grid.addWidget(self.lbl_date,    r, COL_M_START, 1, 2)
        self._current_row += 1

        r = self._current_row
        self.chart_link = QLabel(self._chart_link_html())
        self.chart_link.linkActivated.connect(self._on_chart_link_clicked)
        self.grid.addWidget(self.chart_link, r, COL_M_START, 1, 2)
        self._current_row += 1

    def _chart_link_html(self) -> str:
        # Color must be embedded directly in the <a> tag itself -
        # QLabel's outer setStyleSheet("color: ...") does not
        # reliably override Qt's rich-text engine for anchor text,
        # which is why this used to show a default system blue
        # regardless of theme.
        color = theme_manager.current.link_color
        return (
            f'<a href="#" style="color:{color}; text-decoration:underline;">'
            f'GPC Multiples Range Chart →</a>'
        )

    def _on_chart_link_clicked(self, _href=None):
        first_open = self._chart_dialog is None
        if first_open:
            self._chart_dialog = GPCCandlestickChart(parent=self)
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
        self.grid.addWidget(self.num_multiples_spin, r, COL_TICKER)
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

        # Control Premium — no GT equivalent
        r = self._current_row
        cp_label = QLabel("Control Premium:")
        self.control_premium_input = QLineEdit("24.0%")
        self.control_premium_input.setFixedWidth(70)
        self.control_premium_input.setStyleSheet(get_input_style())
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

        self._add_section_label(
            "Guideline Public Company Multiple(s)",
            r, COL_EXCLUDE, 1, MAX_COLS + 4
        )
        self._current_row += 1
        r = self._current_row

        self._ticker_col_headers = []
        for col, text in [
            (COL_EXCLUDE, "Exclude"),
            (COL_NUM,     "#"),
            (COL_TICKER,  "Ticker"),
            (COL_COMPANY, "Company Name"),
        ]:
            lbl = QLabel(text)
            lbl.setStyleSheet(get_bold_style())
            self.grid.addWidget(lbl, r, col)
            self._ticker_col_headers.append(lbl)

        # Metric dropdown headers — options = catalogue + Custom Multiple
        self.metric_combos = []
        for i, col in enumerate(METRIC_COLS):
            combo = QComboBox()
            combo.addItems(dropdown_options())
            combo.setCurrentIndex(i if i < len(GPC_METRICS) else 0)
            combo.setStyleSheet(get_input_style())
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

                inp = MultipleInputEdit(placeholder="e.g. 4.0x", width=W_METRIC - 10)
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
        self._add_section_label(
            "Statistics",
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
        self._add_section_label(
            "Selected Multiples",
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
                inp = MultipleInputEdit(placeholder="e.g. 4.0x", width=W_METRIC - 10)
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
        self._add_section_label(
            "Subject Company",
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

            inp = CurrencyInputEdit(placeholder="e.g. 1000", width=W_METRIC - 10)
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
        self._add_section_label(
            "Weighting",
            self._current_row, COL_EXCLUDE, 1, MAX_COLS + 4
        )
        self._current_row += 1

        r = self._current_row
        self.grid.addWidget(QLabel("Weighting"), r, COL_EXCLUDE, 1, 3)

        self.weight_inputs = []
        default_weight = f"{100 / MAX_COLS:.1f}%"
        for col in METRIC_COLS:
            inp = PctInputEdit(placeholder="e.g. 14.3%", width=W_METRIC - 10)
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

    BRIDGE_ROW_SLOTS = 10

    def _build_bridge_section(self):
        self._add_section_label(
            "Bridge",
            self._current_row, COL_EXCLUDE, 1, MAX_COLS + 4
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
        self.grid.addWidget(high_hdr, r, COL_M_START)
        self.grid.addWidget(low_hdr, r, COL_M_START + 1)
        self._bridge_low_high_headers = [low_hdr, high_hdr]
        self._current_row += 1

        # Kept for compatibility with any external references; unused now.
        self.bridge_computed_labels_low = {}
        self.bridge_computed_labels_high = {}
        self.bridge_labels_low = {}
        self.bridge_labels_high = {}

        # Dashboard-owned inputs shown here read-only (mirrors, not sources).
        # nwc comes from the NWC page; non_op / CP / DLOC from Dashboard.
        self.nwc_input = CurrencyInputEdit(placeholder="from NWC page", width=W_METRIC - 10)
        self.non_op_assets_input = CurrencyInputEdit(placeholder="from Dashboard", width=W_METRIC - 10)
        for w in (self.nwc_input, self.non_op_assets_input):
            w.setReadOnly(True)
            w.setFrame(False)
            w.setVisible(False)  # values are rendered in the generic rows below

        # Generic bridge rows populated from run_bridge()["lines"].
        self._bridge_row_text = []
        self._bridge_row_low = []
        self._bridge_row_high = []
        for _ in range(self.BRIDGE_ROW_SLOTS):
            r = self._current_row
            text_lbl = QLabel("")
            text_lbl.setWordWrap(True)
            self.grid.addWidget(text_lbl, r, COL_EXCLUDE, 1, 4)
            low_lbl = QLabel("")
            high_lbl = QLabel("")
            for lbl in (low_lbl, high_lbl):
                lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.grid.addWidget(high_lbl, r, COL_M_START)
            self.grid.addWidget(low_lbl, r, COL_M_START + 1)
            for lbl in (text_lbl, low_lbl, high_lbl):
                lbl.setVisible(False)
            self._bridge_row_text.append(text_lbl)
            self._bridge_row_low.append(low_lbl)
            self._bridge_row_high.append(high_lbl)
            self._current_row += 1

    def _render_bridge_rows(self, rows):
        """rows: list of (text, low, high, bold). Fills the generic slots."""
        for i in range(self.BRIDGE_ROW_SLOTS):
            if i < len(rows):
                text, low, high, bold = rows[i]
                self._bridge_row_text[i].setText(text)
                self._bridge_row_text[i].setStyleSheet(get_bold_style() if bold else "")
                self._bridge_row_low[i].setText(_fmt_currency(low) if low is not None else "NA")
                self._bridge_row_high[i].setText(_fmt_currency(high) if high is not None else "NA")
                for lbl in (self._bridge_row_text[i], self._bridge_row_low[i], self._bridge_row_high[i]):
                    lbl.setVisible(True)
            else:
                for lbl in (self._bridge_row_text[i], self._bridge_row_low[i], self._bridge_row_high[i]):
                    lbl.setVisible(False)

    def _lock_dashboard_owned_inputs(self):
        """CP / DLOC / Non-Op / NWC are owned elsewhere; render as plain text."""
        for attr in ("control_premium_input", "dloc_input", "nwc_input", "non_op_assets_input"):
            w = getattr(self, attr, None)
            if w is None:
                continue
            if hasattr(w, "setReadOnly"):
                w.setReadOnly(True)
            if hasattr(w, "setFrame"):
                w.setFrame(False)

    def _save_basis_state(self, basis_key: str):
        """Snapshot current UI inputs into per-basis memory."""
        if basis_key not in self._per_basis_state:
            return
        state = self._per_basis_state[basis_key]
        state["metrics"] = [c.currentText() for c in self.metric_combos]
        state["low"] = [inp.text() for inp in self.selected_low_inputs]
        state["high"] = [inp.text() for inp in self.selected_high_inputs]
        state["weights"] = [inp.text() for inp in self.weight_inputs]
        state["visited"] = True

    def _load_basis_state(self, basis_key: str, *, first_visit: bool,
                          prior_basis_key: Optional[str] = None):
        """
        Restore UI inputs for basis_key.
        First visit: convert metric labels from prior basis (if any),
        leave low/high blank, copy weights from prior basis (or keep
        current even split).
        """
        from Canneberge.Calculations.gpc_metrics import (
            dropdown_options, convert_metric_on_toggle, CUSTOM_MULTIPLE_LABEL,
        )
        state = self._per_basis_state[basis_key]
        new_options = dropdown_options(basis_key)

        for col_idx in range(MAX_COLS):
            combo = self.metric_combos[col_idx]
            combo.blockSignals(True)
            combo.clear()
            combo.addItems(new_options)

            if first_visit:
                # Seed metric via convert from prior basis selection
                if prior_basis_key and self._per_basis_state[prior_basis_key]["metrics"][col_idx]:
                    src = self._per_basis_state[prior_basis_key]["metrics"][col_idx]
                    target = convert_metric_on_toggle(src, basis_key)
                else:
                    target = combo.itemText(min(col_idx, combo.count() - 1))
                idx = combo.findText(target)
                combo.setCurrentIndex(idx if idx >= 0 else 0)

                # Blank low/high on first visit — force fresh inputs
                self.selected_low_inputs[col_idx].blockSignals(True)
                self.selected_high_inputs[col_idx].blockSignals(True)
                self.selected_low_inputs[col_idx].setText("")
                self.selected_high_inputs[col_idx].setText("")
                self.selected_low_inputs[col_idx].blockSignals(False)
                self.selected_high_inputs[col_idx].blockSignals(False)

                # Weights: copy from prior basis if available, else leave
                if prior_basis_key:
                    prior_w = self._per_basis_state[prior_basis_key]["weights"][col_idx]
                    if prior_w is not None:
                        self.weight_inputs[col_idx].blockSignals(True)
                        self.weight_inputs[col_idx].setText(prior_w)
                        self.weight_inputs[col_idx].blockSignals(False)
            else:
                saved_metric = state["metrics"][col_idx]
                idx = combo.findText(saved_metric) if saved_metric else -1
                combo.setCurrentIndex(idx if idx >= 0 else 0)

                self.selected_low_inputs[col_idx].blockSignals(True)
                self.selected_high_inputs[col_idx].blockSignals(True)
                self.selected_low_inputs[col_idx].setText(state["low"][col_idx] or "")
                self.selected_high_inputs[col_idx].setText(state["high"][col_idx] or "")
                self.selected_low_inputs[col_idx].blockSignals(False)
                self.selected_high_inputs[col_idx].blockSignals(False)

                if state["weights"][col_idx] is not None:
                    self.weight_inputs[col_idx].blockSignals(True)
                    self.weight_inputs[col_idx].setText(state["weights"][col_idx])
                    self.weight_inputs[col_idx].blockSignals(False)

            combo.blockSignals(False)
            self._is_custom_multiple[col_idx] = (
                combo.currentText() == CUSTOM_MULTIPLE_LABEL
            )

    def _set_even_weights(self, n_cols: int):
        """
        Reset active GPC weights to equal weighting after the user
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
        Number of active GPC multiple columns changed.

        The new active columns default to equal weighting. This does
        not prevent later manual edits to individual weight fields.
        """
        self._set_even_weights(value)
        self._recalculate()        

    # ------------------------------------------------------------------
    # CUSTOM MULTIPLE MODE HANDLING
    # ------------------------------------------------------------------

    def _on_metric_combo_changed(self, _index=None):
        for i, combo in enumerate(self.metric_combos):
            self._is_custom_multiple[i] = (combo.currentText() == CUSTOM_MULTIPLE_LABEL)
        if self._last_basis_mode is not None:
            self._save_basis_state(self._last_basis_mode)
        self._recalculate()

    def _apply_is_custom_multiple_visibility(self, n_cols: int):
        """
        Swap computed label <-> editable input visibility per column
        based on whether that column is in Custom Multiple mode.
        Only touches columns 0..n_cols-1; columns beyond n_cols are
        hidden entirely by the existing visible/n_cols logic elsewhere.
        """
        for i in range(MAX_COLS):
            is_custom = self._is_custom_multiple[i] and i < n_cols
            for row in range(MAX_ROWS):
                self.tick_mult_labels[row][i].setVisible(not is_custom and i < n_cols)
                self.tick_mult_inputs[row][i].setVisible(is_custom)
            self.subject_metric_labels[i].setVisible(not is_custom and i < n_cols)
            self.subject_metric_inputs[i].setVisible(is_custom)

    # ------------------------------------------------------------------
    # CALCULATION ENGINE
    # ------------------------------------------------------------------

    def _on_inputs_changed(self):
        # Keep the active basis snapshot current so a later toggle
        # does not restore a stale mid-edit version.
        if self._last_basis_mode is not None:
            self._save_basis_state(self._last_basis_mode)
        self._recalculate()

    def _recalculate(self):
        inputs = self.get_project_inputs_callback()
        tickers = inputs.gpc_tickers
        n_cols = self.num_multiples_spin.value()

        # Mode determination from Home Page Basis of Value
        is_equity_mode = (inputs.basis_of_value == "Equity Value")
        basis_key = "EQUITY" if is_equity_mode else "BEV"

        mode_changed = (
            self._last_basis_mode is not None
            and self._last_basis_mode != basis_key
        )
        first_render = self._last_basis_mode is None

        if mode_changed:
            # Persist outgoing basis, restore incoming basis
            self._save_basis_state(self._last_basis_mode)
            first_visit = not self._per_basis_state[basis_key]["visited"]
            self._load_basis_state(
                basis_key,
                first_visit=first_visit,
                prior_basis_key=self._last_basis_mode,
            )
        elif first_render:
            # Initial paint: install correct dropdown options for
            # whatever Home is currently set to, without wiping inputs.
            self._load_basis_state(
                basis_key,
                first_visit=True,
                prior_basis_key=None,
            )

        self._last_basis_mode = basis_key

        self.lbl_client.setText(inputs.client)
        self.lbl_subject.setText(inputs.subject_company_name)
        self.lbl_date.setText(f"As of {inputs.valuation_date}")
        self.lbl_subject_name_inline.setText(
            f"{inputs.subject_company_name} Financial Data"
        )

        for i, col in enumerate(METRIC_COLS):
            visible = i < n_cols
            self.metric_combos[i].setVisible(visible)
            for stat in self.stat_label_widgets:
                self.stat_label_widgets[stat][i].setVisible(visible)
            self.selected_low_inputs[i].setVisible(visible)
            self.selected_high_inputs[i].setVisible(visible)
            self.weight_inputs[i].setVisible(visible)
            self.indicated_bev_low_labels[i].setVisible(visible)
            self.indicated_bev_high_labels[i].setVisible(visible)
            for row in range(MAX_ROWS):
                self.tick_mult_labels[row][i].setVisible(
                    visible and not self._is_custom_multiple[i]
                )
                self.tick_mult_inputs[row][i].setVisible(
                    visible and self._is_custom_multiple[i]
                )

        self._apply_is_custom_multiple_visibility(n_cols)

        sa_results = self._get_stockanalysis_results_callback() or {}
        is_rows = sa_results.get("IS", [])
        ratio_rows = sa_results.get("Ratios", [])
        bs_rows = sa_results.get("BS", [])
        ms_rows = self._get_marketscreener_results_callback() or []

        all_multiples: Dict[str, Dict[str, Optional[float]]] = (
            compute_all_gpc_multiples(is_rows, ms_rows, ratio_rows, bs_rows, tickers, basis_mode=basis_key)
            if tickers else {}
        )

        multiples_per_col = [[] for _ in range(n_cols)]

        for row in range(MAX_ROWS):
            excluded = self.tick_exclude_checks[row].isChecked()

            if row < len(tickers):
                ticker = tickers[row]
                grey = get_excluded_row_style() if excluded else get_included_row_style()

                self.tick_row_labels[row]["ticker"].setText(ticker)
                self.tick_row_labels[row]["company"].setText(
                    inputs.gpc_company_names.get(ticker.upper(), "")
                )

                for lbl in self.tick_row_labels[row].values():
                    lbl.setStyleSheet(grey)

                for col_idx in range(n_cols):
                    if self._is_custom_multiple[col_idx]:
                        multiple = _parse_float(self.tick_mult_inputs[row][col_idx].text())
                    elif excluded:
                        multiple = None
                    else:
                        metric_name = self.metric_combos[col_idx].currentText()
                        multiple = (all_multiples.get(ticker, {}) or {}).get(metric_name)

                    if excluded and not self._is_custom_multiple[col_idx]:
                        self.tick_mult_labels[row][col_idx].setText("NM")
                        self.tick_mult_labels[row][col_idx].setStyleSheet(get_excluded_row_style())
                    elif not self._is_custom_multiple[col_idx]:
                        self.tick_mult_labels[row][col_idx].setText(_fmt_multiple(multiple))
                        self.tick_mult_labels[row][col_idx].setStyleSheet(get_included_row_style())

                    if multiple is not None and not excluded:
                        multiples_per_col[col_idx].append(multiple)
            else:
                self.tick_row_labels[row]["ticker"].setText("")
                self.tick_row_labels[row]["company"].setText("")
                for col_idx in range(MAX_COLS):
                    self.tick_mult_labels[row][col_idx].setText("")

        stat_funcs = {
            "Maximum":        lambda v: max(v),
            "Third Quartile": lambda v: _quartile(v, 0.75),
            "Average":        lambda v: sum(v) / len(v),
            "Median":         lambda v: statistics.median(v),
            "First Quartile": lambda v: _quartile(v, 0.25),
            "Minimum":        lambda v: min(v),
        }

        chart_max, chart_q3, chart_q1, chart_min = [], [], [], []

        for stat, func in stat_funcs.items():
            for col_idx in range(n_cols):
                vals = multiples_per_col[col_idx]
                result = None
                if vals:
                    try:
                        result = func(vals)
                        self.stat_label_widgets[stat][col_idx].setText(_fmt_multiple(result))
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

        subject_metrics = self._get_subject_metrics(inputs, n_cols)
        for col_idx in range(n_cols):
            if self._is_custom_multiple[col_idx]:
                continue
            val = subject_metrics[col_idx]
            self.subject_metric_labels[col_idx].setText(
                _fmt_currency(val) if val is not None else "NA"
            )

        indicated_low = []
        indicated_high = []

        for col_idx in range(n_cols):
            if self._is_custom_multiple[col_idx]:
                subj = _parse_float(self.subject_metric_inputs[col_idx].text())
            else:
                subj = subject_metrics[col_idx]

            sel_low = _parse_float(self.selected_low_inputs[col_idx].text())
            sel_high = _parse_float(self.selected_high_inputs[col_idx].text())

            if subj is not None and sel_low is not None:
                val_low = subj * sel_low
                self.indicated_bev_low_labels[col_idx].setText(_fmt_currency(val_low))
                indicated_low.append(val_low)
            else:
                self.indicated_bev_low_labels[col_idx].setText("NA")
                indicated_low.append(None)

            if subj is not None and sel_high is not None:
                val_high = subj * sel_high
                self.indicated_bev_high_labels[col_idx].setText(_fmt_currency(val_high))
                indicated_high.append(val_high)
            else:
                self.indicated_bev_high_labels[col_idx].setText("NA")
                indicated_high.append(None)

        weights = [_parse_pct(self.weight_inputs[i].text()) for i in range(n_cols)]
        fmv_low = _weighted_sum(indicated_low, weights)
        fmv_high = _weighted_sum(indicated_high, weights)

        self.fmv_low_label.setText(_fmt_currency(fmv_low) if fmv_low is not None else "NA")
        self.fmv_high_label.setText(_fmt_currency(fmv_high) if fmv_high is not None else "NA")

        # Bridge Section — shared value_bridge engine. GPC is minority-native.
        self._lock_dashboard_owned_inputs()

        dash_vals = self._get_dashboard_bridge_values() or {}
        control_premium = dash_vals.get("control_premium")
        dloc = dash_vals.get("dloc")
        non_op = dash_vals.get("non_op") or 0.0

        nwc = self._get_nwc_surplus()

        if inputs.is_private:
            pf = self._get_private_financials_callback()
            cash = pf.get_bs("cash", "TTM") if pf else None
        elif inputs.is_publicly_traded:
            cash = get_subject_cash(bs_rows, inputs.subject_ticker)
        else:
            cash = None

        try:
            debt = self._get_subject_debt()
        except Exception:
            debt = None
        preferred = self._get_subject_metric_value("preferred_stock", "TTM")
        nci = self._get_subject_metric_value("minority_interest", "TTM")

        bi = BridgeInputs(
            cash=cash,
            nwc_surplus=nwc,
            non_operating=non_op,
            debt=debt,
            preferred_stock=preferred,
            minority_interest=nci,
            control_premium=control_premium,
            dloc=dloc,
            shares_outstanding=None,
            share_price=None,
        )
        source_basis = "Equity" if is_equity_mode else "BEV"
        result = run_bridge(
            fmv_low, fmv_high,
            natural_level="minority",
            source_basis=source_basis,
            bi=bi,
            equity_mode_includes_cash=False,
        )
        self._last_bridge_result = result

        # Mirror Dashboard-owned values into the (read-only) compat widgets.
        for widget, text in (
            (getattr(self, "control_premium_input", None),
             f"{control_premium * 100:.1f}%" if control_premium is not None else ""),
            (getattr(self, "dloc_input", None),
             f"{dloc * 100:.1f}%" if dloc is not None else ""),
            (getattr(self, "nwc_input", None),
             _fmt_currency(nwc) if nwc is not None else ""),
            (getattr(self, "non_op_assets_input", None), _fmt_currency(non_op)),
        ):
            if widget is not None:
                widget.blockSignals(True)
                widget.setText(text)
                widget.blockSignals(False)

        bridge_rows = []
        if not is_equity_mode:
            bridge_rows.append(("Debt + Preferred Stock + Minority Interest (subject TTM)",
                                (debt or 0.0) + (preferred or 0.0) + (nci or 0.0),
                                (debt or 0.0) + (preferred or 0.0) + (nci or 0.0), False))
            bridge_rows.append(("Cash & Cash Equivalents (subject TTM)", cash, cash, False))
        bridge_rows.append(("NWC Surplus/(Deficit) (from NWC page)", nwc, nwc, False))
        bridge_rows.append(("Non-Operating Assets (from Dashboard)", non_op, non_op, False))
        for text, lo, hi in result.get("lines", []):
            bridge_rows.append((text, lo, hi, False))
        if is_equity_mode:
            lo, hi = result["equity_controlling"]
            bridge_rows.append(("Equity Value (controlling, marketable) → Dashboard", lo, hi, True))
        else:
            lo, hi = result["bev_controlling"]
            bridge_rows.append(("BEV (controlling, marketable) → Dashboard", lo, hi, True))
        self._render_bridge_rows(bridge_rows)

        chart_labels = [self.metric_combos[i].currentText() for i in range(n_cols)]
        if self._chart_dialog is not None:
            self._chart_dialog.update_data(chart_labels, chart_q3, chart_max, chart_min, chart_q1)

    def _get_subject_metrics(self, inputs, n_cols) -> list:
        """
        Returns subject company metric value per active column, for
        whichever GPC_METRICS entry is selected in that column's dropdown.
        Custom Multiple columns return None here — caller must read the
        editable CurrencyInputEdit directly instead.

        Every value — historical, TTM, or projected (NFY/NFY+1/NFY+2) —
        is sourced through Subject Financials' get_metric_value, which is
        the single source of truth for subject-company data regardless
        of period or company status. This page no longer reads
        StockAnalysis or PrivateFinancials directly for subject metrics.
        """
        results = []

        for col_idx in range(n_cols):
            if self._is_custom_multiple[col_idx]:
                results.append(None)
                continue

            metric_name = self.metric_combos[col_idx].currentText()
            metric = get_metric(metric_name)

            if metric is None:
                results.append(None)
                continue

            val = self._get_subject_metric_value(metric.line_key, metric.period)
            results.append(val)

        return results