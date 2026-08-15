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

from Canneberge.Ui.gpc_candlestick_chart import GPCCandlestickChart

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
    # NOTE: unlike DCF's header bars, GPC's section labels have never
    # had a background color — just bold + slightly larger text. This
    # preserves that (reuses bold_text, no header_bg involved) rather
    # than forcing DCF's banner look onto a page that was never
    # designed with one.
    t = theme_manager.current
    return f"font-weight: bold; font-size: 11px; color: {t.bold_text};"


def get_link_text_style() -> str:
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


def _parse_float(text: str) -> Optional[float]:
    text = str(text).strip().replace(",", "").replace("x", "")
    if not text:
        return None
    try:
        val = float(text)
    except ValueError:
        return None
    if math.isnan(val) or math.isinf(val):
        return None
    return val


def _parse_pct(text: str) -> Optional[float]:
    text = str(text).strip().replace(",", "")
    if not text:
        return None
    try:
        if "%" in text:
            val = float(text.replace("%", "")) / 100
        else:
            val = float(text)
            val = val / 100 if val > 1 else val
    except ValueError:
        return None
    if math.isnan(val) or math.isinf(val):
        return None
    return val


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


class MultipleInputEdit(QLineEdit):
    """
    Same widget as gt_page.py's version — formats ##.##x on focus-out.

    NOTE: this class is duplicated verbatim in gt_page.py (per the
    original docstring above). That's the same copy-pasted-constant
    drift risk already fixed for INPUT_STYLE, just at the class level
    instead of the string level. Not resolved here (out of scope for
    this pass) - flag for when gt_page.py gets migrated: these should
    become one shared class, not two independently-maintained copies.
    """
    def __init__(self, placeholder="", parent=None):
        super().__init__(parent)
        self.setPlaceholderText(placeholder)
        self.setStyleSheet(get_input_style())
        self.setFixedWidth(W_METRIC - 10)
        self.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.editingFinished.connect(self._format_value)
        # Self-subscribing to theme changes (rather than requiring
        # GPCPage to track every grid instance in a list) means this
        # restyles correctly no matter how many of these exist or
        # where they're placed - removes an entire class of "did I
        # remember to add this widget to the restyle loop" bugs.
        theme_manager.theme_changed.connect(
            lambda _t: self.setStyleSheet(get_input_style())
        )

    def _format_value(self):
        val = _parse_float(self.text())
        if val is not None:
            self.setText(f"{val:.2f}x")


class PctInputEdit(QLineEdit):
    """Same widget as gt_page.py's version — formats ##.#% on focus-out."""
    def __init__(self, placeholder="", parent=None):
        super().__init__(parent)
        self.setPlaceholderText(placeholder)
        self.setStyleSheet(get_input_style())
        self.setFixedWidth(W_METRIC - 10)
        self.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.editingFinished.connect(self._format_value)
        theme_manager.theme_changed.connect(
            lambda _t: self.setStyleSheet(get_input_style())
        )

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
        self.setStyleSheet(get_input_style())
        self.setFixedWidth(W_METRIC - 10)
        self.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.editingFinished.connect(self._format_value)
        theme_manager.theme_changed.connect(
            lambda _t: self.setStyleSheet(get_input_style())
        )

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
                 get_marketscreener_results_callback,
                 get_private_financials_callback,
                 get_subject_debt,
                 get_subject_metric_value):
        super().__init__()
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
        self.chart_link.setStyleSheet(get_link_text_style())

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
        self.chart_link = QLabel('<a href="#">GPC Multiples Range Chart →</a>')
        self.chart_link.setStyleSheet(get_link_text_style())
        self.chart_link.linkActivated.connect(self._on_chart_link_clicked)
        self.grid.addWidget(self.chart_link, r, COL_M_START, 1, 2)
        self._current_row += 1

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

        # GPC starts on a marketable, noncontrolling basis (public
        # market prices reflect minority stakes). Add the three
        # invested-capital adjustments to get to Invested Capital,
        # apply Control Premium there, then subtract the same three
        # adjustments back out to land on BEV (marketable, controlling).
        #
        # NWC Surplus (Deficit) and Non-Operating Assets, Net have no
        # data source yet — both are deliberately left as user-typed
        # placeholder inputs until the NWC page exists. They default
        # to None (shown as NA), not 0 — if either is unset, every row
        # below it that depends on it should also show NA, not silently
        # compute as if the missing value were zero.
        self.bridge_computed_labels_low = {}
        self.bridge_computed_labels_high = {}

        computed_rows = [
            ("FMV of Business Enterprise (marketable, noncontrolling)", "bev_nctrl"),
        ]
        for label_text, key in computed_rows:
            r = self._current_row
            lbl = QLabel(label_text)
            # NOTE: this row was never actually bold (the `if False`
            # disables it) - flagged to Ted rather than silently
            # enabling new behavior. The reference itself used to be a
            # dangling name (BOLD_STYLE was never defined anywhere in
            # this file), which only avoided a NameError because
            # Python never evaluates the untaken branch of a ternary.
            # Fixed the dangling reference; left the disable in place.
            lbl.setStyleSheet(get_bold_style()) if False else None
            self.grid.addWidget(lbl, r, COL_EXCLUDE, 1, 4)
            low_lbl = QLabel("NA")
            high_lbl = QLabel("NA")
            for l in (low_lbl, high_lbl):
                l.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.grid.addWidget(high_lbl, r, COL_M_START)
            self.grid.addWidget(low_lbl, r, COL_M_START + 1)
            self.bridge_computed_labels_low[key] = low_lbl
            self.bridge_computed_labels_high[key] = high_lbl
            self._current_row += 1

        # Plus: Cash — pulls from subject debt/cash callback the same
        # way get_subject_debt already works; wired in _recalculate.
        r = self._current_row
        self.grid.addWidget(QLabel("Plus: Cash"), r, COL_EXCLUDE, 1, 4)
        self.bridge_cash_low = QLabel("NA")
        self.bridge_cash_high = QLabel("NA")
        for l in (self.bridge_cash_low, self.bridge_cash_high):
            l.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.grid.addWidget(self.bridge_cash_high, r, COL_M_START)
        self.grid.addWidget(self.bridge_cash_low, r, COL_M_START + 1)
        self._current_row += 1

        # Plus: NWC Surplus (Deficit) — PLACEHOLDER, no data source yet
        r = self._current_row
        self.grid.addWidget(
            QLabel("Plus: NWC Surplus (Deficit) — PLACEHOLDER"),
            r, COL_EXCLUDE, 1, 4
        )
        self.nwc_input = CurrencyInputEdit(placeholder="e.g. 0")
        self.nwc_input.editingFinished.connect(self._on_inputs_changed)
        self.grid.addWidget(self.nwc_input, r, COL_M_START, alignment=Qt.AlignmentFlag.AlignRight)
        self._current_row += 1

        # Plus: Non-Operating Assets, Net — PLACEHOLDER, no data source yet
        r = self._current_row
        self.grid.addWidget(
            QLabel("Plus: Non-Operating Assets, Net — PLACEHOLDER"),
            r, COL_EXCLUDE, 1, 4
        )
        self.non_op_assets_input = CurrencyInputEdit(placeholder="e.g. 0")
        self.non_op_assets_input.editingFinished.connect(self._on_inputs_changed)
        self.grid.addWidget(self.non_op_assets_input, r, COL_M_START, alignment=Qt.AlignmentFlag.AlignRight)
        self._current_row += 1

        remaining_rows = [
            ("FMV of Invested Capital (marketable, noncontrolling)", "ic_nctrl"),
            ("Plus: Control Premium",                                "control_premium_pct"),
            ("FMV of Invested Capital (marketable, controlling)",    "ic_ctrl"),
            ("Less: Cash",                                           "less_cash"),
            ("Less: NWC Surplus (Deficit) — PLACEHOLDER",            "less_nwc"),
            ("Less: Non-Operating Assets, Net — PLACEHOLDER",        "less_non_op"),
            ("FMV of Business Enterprise (marketable, controlling)", "bev_ctrl"),
        ]

        self.bridge_labels_low = {}
        self.bridge_labels_high = {}
        for label_text, key in remaining_rows:
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
            self.grid.addWidget(low_lbl, r, COL_M_START + 1)
            self.bridge_labels_low[key] = low_lbl
            self.bridge_labels_high[key] = high_lbl
            self._current_row += 1

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

        # Pull scraped data once
        sa_results = self._get_stockanalysis_results_callback() or {}
        is_rows = sa_results.get("IS", [])
        ratio_rows = sa_results.get("Ratios", [])
        bs_rows = sa_results.get("BS", [])
        ms_rows = self._get_marketscreener_results_callback() or []

        # Compute real multiples for every ticker (Custom columns are
        # simply not read from this — the user's typed value wins)
        all_multiples: Dict[str, Dict[str, Optional[float]]] = (
            compute_all_gpc_multiples(is_rows, ms_rows, ratio_rows, bs_rows, tickers)
            if tickers else {}
        )
        bevs = get_ticker_bevs(ratio_rows, bs_rows, tickers) if tickers else {}

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
                        # User-typed value — read directly, no computation
                        multiple = _parse_float(
                            self.tick_mult_inputs[row][col_idx].text()
                        )
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

        # Subject metrics — computed columns pull from StockAnalysis/Private,
        # Custom columns read the user-typed CurrencyInputEdit directly.
        subject_metrics = self._get_subject_metrics(inputs, n_cols)
        for col_idx in range(n_cols):
            if self._is_custom_multiple[col_idx]:
                continue  # value comes straight from the input widget, no label to set
            val = subject_metrics[col_idx]
            self.subject_metric_labels[col_idx].setText(
                _fmt_currency(val) if val is not None else "NA"
            )

        # Indicated BEV
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

        # Bridge — GPC starts on a marketable, noncontrolling basis
        # (public market prices reflect minority stakes). Add Cash,
        # NWC Surplus/Deficit, and Non-Op Assets to reach Invested
        # Capital, apply Control Premium there, then subtract the
        # same three items back out to land on BEV controlling.
        #
        # Cash pulls from BS (public) or PrivateFinancials (private),
        # the same "cash & equivalents" line already used in
        # get_ticker_bev's net debt calc. NWC and Non-Op Assets have
        # no data source yet and remain user-typed placeholders until
        # the NWC page exists. Both default to None (NA) rather than
        # 0, and any row depending on a None placeholder shows NA
        # rather than silently computing through it.
        bev_nctrl_low = fmv_low
        bev_nctrl_high = fmv_high
        self.bridge_computed_labels_low["bev_nctrl"].setText(
            _fmt_currency(bev_nctrl_low) if bev_nctrl_low is not None else "NA"
        )
        self.bridge_computed_labels_high["bev_nctrl"].setText(
            _fmt_currency(bev_nctrl_high) if bev_nctrl_high is not None else "NA"
        )

        if inputs.is_private:
            pf = self._get_private_financials_callback()
            cash = pf.get_bs("cash", "TTM") if pf else None
        elif inputs.is_publicly_traded:
            bs_rows = sa_results.get("BS", [])
            cash = get_subject_cash(bs_rows, inputs.subject_ticker)
        else:
            cash = None
        cash_str = _fmt_currency(cash) if cash is not None else "NA"
        self.bridge_cash_low.setText(cash_str)
        self.bridge_cash_high.setText(cash_str)

        # Blank means "no adjustment" (0), not "unknown" (None) — an
        # unset optional placeholder shouldn't propagate NA through
        # every row below it. bev_nctrl/cash still use None-propagation
        # since those genuinely can be unavailable; NWC/Non-Op Assets
        # are optional adjustments that default to zero when blank.
        nwc = _parse_float(self.nwc_input.text()) or 0.0
        non_op = _parse_float(self.non_op_assets_input.text()) or 0.0

        def _sum_or_na(*vals):
            if any(v is None for v in vals):
                return None
            return sum(vals)

        ic_nctrl_low = _sum_or_na(bev_nctrl_low, cash, nwc, non_op)
        ic_nctrl_high = _sum_or_na(bev_nctrl_high, cash, nwc, non_op)
        self.bridge_labels_low["ic_nctrl"].setText(
            _fmt_currency(ic_nctrl_low) if ic_nctrl_low is not None else "NA"
        )
        self.bridge_labels_high["ic_nctrl"].setText(
            _fmt_currency(ic_nctrl_high) if ic_nctrl_high is not None else "NA"
        )

        control_premium = _parse_pct(self.control_premium_input.text())
        cp_str = _fmt_pct_display(control_premium)
        self.bridge_labels_low["control_premium_pct"].setText(cp_str)
        self.bridge_labels_high["control_premium_pct"].setText(cp_str)

        ic_ctrl_low = (
            ic_nctrl_low * (1 + control_premium)
            if ic_nctrl_low is not None and control_premium is not None else None
        )
        ic_ctrl_high = (
            ic_nctrl_high * (1 + control_premium)
            if ic_nctrl_high is not None and control_premium is not None else None
        )
        self.bridge_labels_low["ic_ctrl"].setText(
            _fmt_currency(ic_ctrl_low) if ic_ctrl_low is not None else "NA"
        )
        self.bridge_labels_high["ic_ctrl"].setText(
            _fmt_currency(ic_ctrl_high) if ic_ctrl_high is not None else "NA"
        )

        self.bridge_labels_low["less_cash"].setText(cash_str)
        self.bridge_labels_high["less_cash"].setText(cash_str)

        nwc_str = _fmt_currency(nwc)
        self.bridge_labels_low["less_nwc"].setText(nwc_str)
        self.bridge_labels_high["less_nwc"].setText(nwc_str)

        non_op_str = _fmt_currency(non_op)
        self.bridge_labels_low["less_non_op"].setText(non_op_str)
        self.bridge_labels_high["less_non_op"].setText(non_op_str)

        bev_ctrl_low = (
            ic_ctrl_low - cash - nwc - non_op
            if None not in (ic_ctrl_low, cash, nwc, non_op) else None
        )
        bev_ctrl_high = (
            ic_ctrl_high - cash - nwc - non_op
            if None not in (ic_ctrl_high, cash, nwc, non_op) else None
        )
        self.bridge_labels_low["bev_ctrl"].setText(
            _fmt_currency(bev_ctrl_low) if bev_ctrl_low is not None else "NA"
        )
        self.bridge_labels_high["bev_ctrl"].setText(
            _fmt_currency(bev_ctrl_high) if bev_ctrl_high is not None else "NA"
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