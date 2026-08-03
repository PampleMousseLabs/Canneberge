import math
import re
from datetime import datetime
from typing import Optional, Dict

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QLineEdit,
    QScrollArea, QFrame, QCheckBox, QPushButton, QComboBox, QSpinBox,
    QDialog, QFormLayout, QDialogButtonBox
)
from PyQt6.QtCore import Qt

# --- Style Constants ---
INPUT_STYLE = "background-color: #dce9f7; color: #1a4a8a;"
BOLD_STYLE = "font-weight: bold;"
HEADER_STYLE = "font-weight: bold; font-size: 11px; background-color: #f0f0f0;"
INDENT_STYLE = "padding-left: 20px;"
MARGIN_ROW_STYLE = "padding-left: 20px; font-style: italic;"
MARGIN_CELL_STYLE = "font-style: italic;"
COL_WIDTH = 95

# Rows where historical columns should render truly blank (no "-")
# because historical Free Cash Flow is never discounted.
HIST_BLANK_ROWS = {
    "Partial Period Adjustment", "Present Value Period",
    "Present Value Factor", "Present Value of Free Cash Flows",
}

# Placeholder values for rows whose calculation isn't wired yet.
# NWC placeholder per Ted's instructions — every cell returns 80085.
# Net Interest Expense (projected) per Ted's instructions — FCFE
# mode every cell returns 8008135; FCFF mode the row is hidden AND
# every cell value is forced to 0 (the placeholder never surfaces).
NWC_PLACEHOLDER = 80085
NET_INT_PROJ_PLACEHOLDER = 8008135


def _fmt_currency(value: Optional[float]) -> str:
    if value is None or (isinstance(value, float) and (math.isnan(value) or math.isinf(value))):
        return "-"
    return f"{value:,.0f}"


def _fmt_pct(value: Optional[float]) -> str:
    if value is None or (isinstance(value, float) and (math.isnan(value) or math.isinf(value))):
        return "-"
    return f"{value:.1%}"


def _make_section_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(HEADER_STYLE)
    lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    return lbl


def _safe_div(a: Optional[float], b: Optional[float]) -> Optional[float]:
    """None-safe division. Returns None if either input is None or
    divisor is zero — never raises, never returns NaN/Inf."""
    if a is None or b is None or b == 0:
        return None
    return a / b


def _parse_label_as_float(text: str) -> Optional[float]:
    """
    Parse a cell text back to a float. Handles formatted currency
    ("1,234"), percentages ("10.5%"), and sentinel strings ("-",
    "", "NA"). Returns None for any unparseable input.
    """
    if not text or text.strip() in ("-", "", "NA"):
        return None
    cleaned = text.replace(",", "").replace("%", "").strip()
    try:
        return float(cleaned)
    except (ValueError, TypeError):
        return None


def _parse_year(text: str) -> Optional[int]:
    """
    Pull a 4-digit year out of a date string. Used for the
    Valuation Date in the Partial Period Adjustment calc.
    Tries the same multi-format parse used elsewhere in the
    codebase first, then falls back to any 19xx/20xx substring.
    """
    if not text:
        return None
    s = text.strip()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m-%d-%Y"):
        try:
            return datetime.strptime(s, fmt).year
        except ValueError:
            continue
    m = re.search(r"(19|20)\d{2}", s)
    if m:
        try:
            return int(m.group(0))
        except ValueError:
            return None
    return None


def _read_label(labels: Dict[int, Dict[int, "QLabel"]],
                row_idx: int, data_idx: int) -> Optional[float]:
    lbl = labels.get(row_idx, {}).get(data_idx)
    if lbl is None:
        return None
    return _parse_label_as_float(lbl.text())


class ProjectionTogglesDialog(QDialog):
    def __init__(self, project_inputs, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Projection Toggles")
        self.setMinimumWidth(350)

        layout = QVBoxLayout()
        form = QFormLayout()

        self.hist_years_spin = QSpinBox()
        self.hist_years_spin.setMinimum(0)
        self.hist_years_spin.setMaximum(5)
        self.hist_years_spin.setValue(project_inputs.historical_years)
        self.hist_years_spin.setStyleSheet(INPUT_STYLE)
        form.addRow("Years of Historicals:", self.hist_years_spin)

        self.proj_years_spin = QSpinBox()
        self.proj_years_spin.setMinimum(1)
        self.proj_years_spin.setMaximum(20)
        self.proj_years_spin.setValue(project_inputs.projection_years)
        self.proj_years_spin.setStyleSheet(INPUT_STYLE)
        form.addRow("Years of Projections:", self.proj_years_spin)

        self.cash_flows_combo = QComboBox()
        self.cash_flows_combo.addItems(["FCFF", "FCFE"])
        self.cash_flows_combo.setStyleSheet(INPUT_STYLE)
        form.addRow("Cash Flows to:", self.cash_flows_combo)

        self.nol_combo = QComboBox()
        self.nol_combo.addItems(["No", "Yes"])
        self.nol_combo.setStyleSheet(INPUT_STYLE)
        form.addRow("NOLs?:", self.nol_combo)

        self.nwc_combo = QComboBox()
        self.nwc_combo.addItems(["No", "Yes"])
        self.nwc_combo.setStyleSheet(INPUT_STYLE)
        form.addRow("Change in NWC provided by Mgmt:", self.nwc_combo)

        self.val_approach_combo = QComboBox()
        self.val_approach_combo.addItems(["DCF", "LBO"])
        self.val_approach_combo.setStyleSheet(INPUT_STYLE)
        form.addRow("Valuation Approach:", self.val_approach_combo)

        layout.addLayout(form)
        layout.addStretch()
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.setLayout(layout)


class DCFPage(QWidget):
    """
    Column architecture:
      Grid columns: 0 = row label. 1..num_hist = historical data.
      Then ONE structural column hosting a vertical-line separator
      (no data). Then num_proj columns of projected data. Then ONE
      structural spacer column (no data, thin, signals a gap before
      the residual year). Then 1 column for the Residual data.

    Table has three header rows, in this order:
      Row 0 — section labels: "Historical Financials" spans the
              historical block; "Projected Financials" spans the
              projected block PLUS the spacer PLUS the Residual
              column (Residual is conceptually a projected column,
              just visually offset — no separate "Residual/Summary"
              label).
      Row 1 — symbolic period labels (LFY-4 ... LFY, NFY ... NFY+N,
              "Residual"), column 0 left blank, no date substitution.
      Row 2 — "FYE" row: computed calendar year per column. Refreshed
              on every _recalculate() (not just structural rebuilds),
              since it depends on Home page date fields and the
              Residual Year footer input, neither of which changes
              the column COUNT.

    The vertical-line separator spans from the section-header row
    down through the Free Cash Flow row (recorded during row build).

    Data sources (per Ted's mapping instructions, "pull from the most
    recent level" rule):
      - Subject Financials page for IS/BS line items, via the
        SubjectFinancialsPage instance passed in
        (get_subject_financials_callback). Uses its public
        get_metric_value() helper, which already handles the
        public/private branching and TTM/projection routing
        documented there.
      - The Projection Module popup writes to the shared
        ProjectionData instance (get_projection_data_callback),
        which is what SubjectFinancialsPage.get_metric_value
        falls back to for projection periods. So pulling
        projected metrics through Subject Financials = pulling
        from the Projection Module, no separate wiring needed.
      - Home page for tax rate and forward/valuation dates.
      - WACC page via get_wacc_value_callback for the discount
        rate displayed in the PV Factor row header.

    The "Cash Flows to:" toggle (FCFF vs FCFE) lives in the
    ProjectionTogglesDialog. Its value is captured into
    self._cash_flows_to on dialog accept and drives two things:
      1. The dynamic row name for the "EBIT" row (EBIT for FCFF,
         EBT for FCFE).
      2. The "Net Interest Expense" row's projected-column
         behavior: in FCFF mode the row is hidden AND every
         projected cell value is forced to 0 (since FCFF is
         unlevered, the placeholder 8008135 sentinel never
         surfaces). In FCFE mode the row stays visible and
         every projected cell returns the 8008135 placeholder.

    The EBIT row itself is always a single physical row whose
    label text gets rewritten by _recalculate() based on the
    toggle. The row's data is the same either way: a calc
    row that pulls Depreciation, Amortization, and (for EBT)
    Net Interest Expense as inputs.
    """

    def __init__(self,
                 get_project_inputs_callback,
                 get_wacc_value_callback,
                 get_subject_financials_callback,
                 get_projection_data_callback,
                 update_projection_callback):
        super().__init__()
        self.get_project_inputs = get_project_inputs_callback
        self.get_wacc_value = get_wacc_value_callback
        self._get_subject_financials = get_subject_financials_callback
        self._get_projection_data = get_projection_data_callback
        self._update_projection_callback = update_projection_callback

        self._calc_labels = {}
        self._input_fields = {}
        self._headers = []
        self._is_historical = []
        self._fye_labels = {}
        self.pv_factor_row_label = None

        # Row indices into self._rows, captured during _build_table_rows.
        # _recalculate() looks up cells via these so we don't string-match
        # on row labels at runtime.
        self._row_idx = {}

        # Grid row positions for the two rows that need dynamic behavior
        # (label rewrite / visibility) outside of cell text updates.
        self._ebit_grid_row = None
        self._net_int_grid_row = None

        self.table_container = None
        self._built_hist_years = None
        self._built_proj_years = None
        self._table_insert_index = 0
        self._num_hist = 0
        self._num_proj = 0

        # Cash Flows to: — FCFF (default) or FCFE. Set by the
        # ProjectionTogglesDialog on accept. Read by _recalculate()
        # to drive the dynamic EBIT/EBT row label and the Net
        # Interest Expense row's projected behavior.
        self._cash_flows_to = "FCFF"

        self._build_ui()
        self._recalculate()

    # ------------------------------------------------------------------
    # PAGE STRUCTURE
    # ------------------------------------------------------------------

    def _build_ui(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)

        self.page_container = QWidget()
        self.page_layout = QVBoxLayout()
        self.page_layout.setSpacing(4)
        self.page_layout.setContentsMargins(10, 10, 10, 10)

        self._build_header_controls()

        self._table_insert_index = self.page_layout.count()

        # Footer panels must exist BEFORE the first table build, since
        # the FYE row's Residual column reads self.res_year_input.
        self._build_footer_panels_placeholder_guard()

        self._rebuild_table_if_needed()

        self.page_layout.addLayout(self._footer_hbox)

        self.page_layout.addStretch(1)
        self.page_container.setLayout(self.page_layout)
        scroll.setWidget(self.page_container)

        outer = QVBoxLayout()
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)
        self.setLayout(outer)

    def _build_header_controls(self):
        # Row order per spec: Ted & Co. / subject / method / date FIRST,
        # then Projection Toggles link directly below it.
        info_row = QHBoxLayout()
        self.lbl_client = QLabel()
        self.lbl_client.setStyleSheet(BOLD_STYLE)
        self.lbl_subject = QLabel()
        self.lbl_subject.setStyleSheet(BOLD_STYLE)
        self.lbl_method = QLabel("Income Approach - Discounted Cash Flow Method")
        self.lbl_method.setStyleSheet(BOLD_STYLE)
        self.lbl_date = QLabel()
        self.lbl_date.setStyleSheet(BOLD_STYLE)

        info_row.addWidget(self.lbl_client)
        info_row.addSpacing(20)
        info_row.addWidget(self.lbl_subject)
        info_row.addSpacing(20)
        info_row.addWidget(self.lbl_method)
        info_row.addStretch()
        info_row.addWidget(self.lbl_date)
        self.page_layout.addLayout(info_row)

        toggle_row = QHBoxLayout()
        self.link_toggles = QPushButton("Projection Toggles")
        self.link_toggles.setStyleSheet(
            "border: none; color: #1a4a8a; text-decoration: underline; background: transparent;"
        )
        self.link_toggles.setCursor(Qt.CursorShape.PointingHandCursor)
        self.link_toggles.clicked.connect(self._open_toggles)
        toggle_row.addWidget(self.link_toggles)
        toggle_row.addStretch()
        self.page_layout.addLayout(toggle_row)

    def _open_toggles(self):
        inputs = self.get_project_inputs()
        dialog = ProjectionTogglesDialog(inputs, self)
        # Pre-select the current cash flows choice so opening the
        # dialog isn't a surprise every time.
        idx = dialog.cash_flows_combo.findText(self._cash_flows_to)
        if idx >= 0:
            dialog.cash_flows_combo.setCurrentIndex(idx)
        if dialog.exec():
            self._cash_flows_to = dialog.cash_flows_combo.currentText()
            new_hist = dialog.hist_years_spin.value()
            new_proj = dialog.proj_years_spin.value()
            if new_hist != inputs.historical_years or new_proj != inputs.projection_years:
                self._update_projection_callback(new_hist, new_proj)
            self._recalculate()

    def _generate_columns(self):
        inputs = self.get_project_inputs()
        hist_labels = inputs.historical_period_columns
        proj_labels = inputs.projection_period_columns

        self._headers = hist_labels + proj_labels + ["Residual"]
        self._is_historical = [True] * len(hist_labels) + [False] * len(proj_labels) + [False]
        self._num_hist = len(hist_labels)
        self._num_proj = len(proj_labels)
        return self._num_hist, self._num_proj

    def _grid_col(self, data_idx: int) -> int:
        """Maps a logical data-column index (0-based, into self._headers)
        to its actual QGridLayout column, accounting for the two
        structural (non-data) columns: the vline separator between
        historical/projected, and the spacer before Residual."""
        num_hist, num_proj = self._num_hist, self._num_proj
        if data_idx < num_hist:
            return 1 + data_idx
        elif data_idx < num_hist + num_proj:
            return 1 + num_hist + 1 + (data_idx - num_hist)
        else:
            return 1 + num_hist + 1 + num_proj + 1

    # ------------------------------------------------------------------
    # TABLE — rebuild-capable region
    # ------------------------------------------------------------------

    def _rebuild_table_if_needed(self, force: bool = False):
        inputs = self.get_project_inputs()
        new_hist = inputs.historical_years
        new_proj = inputs.projection_years

        if (not force and self.table_container is not None
                and new_hist == self._built_hist_years
                and new_proj == self._built_proj_years):
            return

        if self.table_container is not None:
            self.page_layout.removeWidget(self.table_container)
            self.table_container.setParent(None)
            self.table_container.deleteLater()

        self._calc_labels = {}
        self._input_fields = {}
        self._fye_labels = {}
        self.pv_factor_row_label = None
        self._row_idx = {}
        self._ebit_grid_row = None
        self._net_int_grid_row = None

        num_hist, num_proj = self._generate_columns()

        self.table_container = QWidget()
        self.table_grid = QGridLayout()
        self.table_grid.setSpacing(2)
        self.table_grid.setContentsMargins(0, 0, 0, 0)
        self.table_grid.setColumnStretch(0, 2)

        for data_idx in range(len(self._headers)):
            self.table_grid.setColumnMinimumWidth(self._grid_col(data_idx), COL_WIDTH)

        self._current_table_row = 0
        self._build_table_headers(num_hist, num_proj)
        self._build_table_rows(num_hist, num_proj)

        self.table_container.setLayout(self.table_grid)
        self.page_layout.insertWidget(self._table_insert_index, self.table_container)

        self._built_hist_years = new_hist
        self._built_proj_years = new_proj

    def _build_table_headers(self, num_hist: int, num_proj: int):
        # Row 0: section labels. "Projected Financials" spans the
        # projected columns + spacer + Residual — Residual has no
        # separate header, it's covered by this label.
        r = self._current_table_row
        if num_hist > 0:
            self.table_grid.addWidget(_make_section_label("Historical Financials"), r, 1, 1, num_hist)
        proj_span = num_proj + 1 + 1  # projected cols + spacer + residual
        self.table_grid.addWidget(
            _make_section_label("Projected Financials"), r, 1 + num_hist + 1, 1, proj_span
        )
        self._section_header_row = r
        self._current_table_row += 1

        # Row 1: symbolic period labels only — no "Line Item" text in
        # column 0, no date substitution.
        r = self._current_table_row
        for data_idx, col_label in enumerate(self._headers):
            lbl = QLabel(col_label)
            lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            lbl.setStyleSheet("font-size: 10px; color: #555555;")
            self.table_grid.addWidget(lbl, r, self._grid_col(data_idx))
        self._current_table_row += 1

        # Row 2: FYE — placeholders here, populated by _recalculate().
        r = self._current_table_row
        self.table_grid.addWidget(QLabel("FYE"), r, 0)
        for data_idx, col_label in enumerate(self._headers):
            lbl = QLabel("")
            lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            lbl.setStyleSheet("font-size: 10px; color: #555555;")
            self.table_grid.addWidget(lbl, r, self._grid_col(data_idx))
            self._fye_labels[col_label] = lbl
        self._current_table_row += 1

    def _build_table_rows(self, num_hist: int, num_proj: int):
        # tuple = (label, is_bold, is_input, is_indent, is_margin)
        # The EBIT row's displayed label is rewritten dynamically by
        # _recalculate() based on the FCFF/FCFE toggle, so its
        # canonical label here is just "EBIT".
        #
        # The "Less: Increase/(Decrease) in DCF/NWC" row label is
        # renamed to "DFCFNWC" per Ted's instructions (#) footnote.
        self._rows = [
            ("Revenue", False, False, False, False),
            ("Revenue Growth", False, False, False, True),
            ("Cost of Goods Sold", False, False, False, False),
            ("Gross Profit", True, False, False, False),
            ("Gross Profit Margin", False, False, False, True),
            ("Operating Expenses", True, False, False, False),
            ("EBITDA", True, False, False, False),
            ("EBITDA Margin", False, False, False, True),
            ("Depreciation", False, False, False, False),
            ("Amortization", False, False, False, False),
            ("Net Interest Expense", False, False, False, False),
            ("EBIT", True, False, False, False),
            ("EBIT Margin", False, False, False, True),
            ("Taxes", False, False, False, False),
            ("Net Operating Profit After Tax (NOPAT)", True, False, False, False),
            ("Plus: Depreciation", False, False, True, False),
            ("Less: Increase/(Decrease) in DFCFNWC", False, False, True, False),
            ("Less: Capital Expenditures (CapEx)", False, False, True, False),
            ("Less: Other Adjustments", False, False, True, False),
            ("Free Cash Flow", True, False, False, False),
            ("Partial Period Adjustment", False, False, False, False),
            ("Present Value Period", False, False, False, False),
            ("Present Value Factor", False, False, False, False),
            ("Present Value of Free Cash Flows", True, False, False, False),
        ]

        # Capture row label -> index for runtime lookups in _recalculate.
        for idx, (label, _, _, _, _) in enumerate(self._rows):
            self._row_idx[label] = idx

        self._free_cash_flow_row = None

        for idx, (label, is_bold, is_input, is_indent, is_margin) in enumerate(self._rows):
            row = self._current_table_row
            row_lbl = QLabel(label)
            style_parts = []
            if is_bold:
                style_parts.append(BOLD_STYLE)
            if is_indent:
                style_parts.append(INDENT_STYLE)
            if is_margin:
                style_parts.append(MARGIN_ROW_STYLE)
            if style_parts:
                row_lbl.setStyleSheet(" ".join(style_parts))
            self.table_grid.addWidget(row_lbl, row, 0, alignment=Qt.AlignmentFlag.AlignLeft)

            if label == "Present Value Factor":
                self.pv_factor_row_label = row_lbl
            if label == "Free Cash Flow":
                self._free_cash_flow_row = row
            if label == "EBIT":
                self._ebit_grid_row = row
            if label == "Net Interest Expense":
                self._net_int_grid_row = row

            # The "Less: Other Adjustments" row has a mixed source
            # model per Ted's instructions: historical = pulled from
            # Subject Financials ("Acquisitions"), projected/Residual
            # = user input. We create an input widget for projected
            # cells (and Residual) but NOT for historicals, and
            # populate both sides in _recalculate().
            is_other_adj_row = (label == "Less: Other Adjustments")

            self._calc_labels[idx] = {}
            self._input_fields[idx] = {}

            for data_idx in range(len(self._headers)):
                grid_col = self._grid_col(data_idx)
                is_hist_col = self._is_historical[data_idx]

                if is_other_adj_row and not is_hist_col:
                    inp = QLineEdit()
                    inp.setStyleSheet(INPUT_STYLE)
                    inp.setFixedWidth(COL_WIDTH - 10)
                    inp.setAlignment(Qt.AlignmentFlag.AlignRight)
                    inp.editingFinished.connect(self._recalculate)
                    self.table_grid.addWidget(inp, row, grid_col)
                    self._input_fields[idx][data_idx] = inp
                else:
                    blank = is_hist_col and label in HIST_BLANK_ROWS
                    calc_lbl = QLabel("" if blank else "-")
                    calc_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                    cell_style_parts = []
                    if is_bold:
                        cell_style_parts.append(BOLD_STYLE)
                    if is_margin:
                        cell_style_parts.append(MARGIN_CELL_STYLE)
                    if cell_style_parts:
                        calc_lbl.setStyleSheet(" ".join(cell_style_parts))
                    self.table_grid.addWidget(calc_lbl, row, grid_col)
                    self._calc_labels[idx][data_idx] = calc_lbl

            self._current_table_row += 1

        # Vertical separator: section-header row through Free Cash Flow.
        vline_col = 1 + num_hist
        vline = QFrame()
        vline.setFrameShape(QFrame.Shape.VLine)
        vline.setFrameShadow(QFrame.Shadow.Sunken)
        span = (self._free_cash_flow_row - self._section_header_row) + 1
        self.table_grid.addWidget(vline, self._section_header_row, vline_col, span, 1)
        self.table_grid.setColumnMinimumWidth(vline_col, 8)

        # Thin blank spacer before Residual.
        spacer_col = 1 + num_hist + 1 + num_proj
        self.table_grid.setColumnMinimumWidth(spacer_col, 14)

    # ------------------------------------------------------------------
    # FYE calendar-year calculation
    # ------------------------------------------------------------------

    def _compute_fye_years(self, inputs) -> Dict[str, str]:
        """
        LFY comes from Home page's Last Fiscal Year; LFY-N walks
        backward one year per step. NFY/NFY+1/NFY+2 come from Home
        page's three forward-date inputs; NFY+3 and beyond walk
        forward one year per step from NFY+2. Residual comes from the
        Residual Year footer input directly, not a formula chain.
        """
        result: Dict[str, str] = {}

        lfy_year = inputs.last_fiscal_year_year
        nfy_year = inputs.next_fiscal_year_year
        nfy1_year = inputs.nfy_1_year
        nfy2_year = inputs.nfy_2_year

        for label in inputs.historical_period_columns:
            if label == "LFY":
                result[label] = str(lfy_year) if lfy_year is not None else ""
            else:
                try:
                    n = int(label.split("-")[1])
                    result[label] = str(lfy_year - n) if lfy_year is not None else ""
                except (IndexError, ValueError, TypeError):
                    result[label] = ""

        for label in inputs.projection_period_columns:
            if label == "NFY":
                result[label] = str(nfy_year) if nfy_year is not None else ""
            elif label == "NFY+1":
                result[label] = str(nfy1_year) if nfy1_year is not None else ""
            elif label == "NFY+2":
                result[label] = str(nfy2_year) if nfy2_year is not None else ""
            else:
                try:
                    n = int(label.split("+")[1])
                    result[label] = str(nfy2_year + (n - 2)) if nfy2_year is not None else ""
                except (IndexError, ValueError, TypeError):
                    result[label] = ""

        result["Residual"] = self.res_year_input.text().strip() if hasattr(self, "res_year_input") else ""

        return result

    # ------------------------------------------------------------------
    # FOOTER PANELS
    # ------------------------------------------------------------------

    def _build_footer_panels_placeholder_guard(self):
        """Builds the footer panels but stores the layout separately
        (self._footer_hbox) instead of adding it to page_layout here —
        _build_ui adds it AFTER the table, so it always renders below
        regardless of table row count, while still existing early
        enough for the first FYE calculation to read res_year_input."""
        self._footer_hbox = QHBoxLayout()
        self._footer_hbox.setContentsMargins(0, 20, 0, 0)

        res_frame = QFrame()
        res_frame.setFrameShape(QFrame.Shape.StyledPanel)
        res_layout = QVBoxLayout()
        res_layout.addWidget(QLabel("Residual Year Inputs", styleSheet=BOLD_STYLE))

        h_use = QHBoxLayout()
        h_use.addWidget(QLabel("Use Residual Year:"))
        self.res_use_combo = QComboBox()
        self.res_use_combo.addItems(["Yes", "No"])
        self.res_use_combo.setStyleSheet(INPUT_STYLE)
        h_use.addWidget(self.res_use_combo)
        res_layout.addLayout(h_use)

        h_year = QHBoxLayout()
        h_year.addWidget(QLabel("Residual Year:"))
        self.res_year_input = QLineEdit("2035")
        self.res_year_input.setStyleSheet(INPUT_STYLE)
        self.res_year_input.setFixedWidth(60)
        self.res_year_input.editingFinished.connect(self._recalculate)
        h_year.addWidget(self.res_year_input)
        res_layout.addLayout(h_year)

        h_ltg = QHBoxLayout()
        h_ltg.addWidget(QLabel("Long Term Growth Rate:"))
        self.ltg_input = QLineEdit("3.0%")
        self.ltg_input.setStyleSheet(INPUT_STYLE)
        self.ltg_input.setFixedWidth(60)
        h_ltg.addWidget(self.ltg_input)
        res_layout.addLayout(h_ltg)

        self.chk_ebitda = QCheckBox("EBITDA Multiple")
        self.chk_ebitda.setChecked(True)
        self.chk_rev = QCheckBox("Revenue Multiple")
        self.chk_h = QCheckBox("H-Model")
        res_layout.addWidget(self.chk_ebitda)
        res_layout.addWidget(self.chk_rev)
        res_layout.addWidget(self.chk_h)

        res_frame.setLayout(res_layout)
        self._footer_hbox.addWidget(res_frame, 1)

        capex_frame = QFrame()
        capex_frame.setFrameShape(QFrame.Shape.StyledPanel)
        capex_layout = QVBoxLayout()
        capex_layout.addWidget(QLabel("CapEx Options", styleSheet=BOLD_STYLE))

        c1 = QHBoxLayout()
        c1.addWidget(QLabel("Residual CapEx at LTGR:"))
        self.capex_ltg = QLineEdit("425")
        self.capex_ltg.setStyleSheet(INPUT_STYLE)
        self.capex_ltg.setFixedWidth(60)
        c1.addWidget(self.capex_ltg)
        capex_layout.addLayout(c1)

        c2 = QHBoxLayout()
        c2.addWidget(QLabel("Avg of Forecast:"))
        c2.addStretch()
        self.capex_avg_forecast = QLabel("-")
        capex_layout.addLayout(c2)

        c3 = QHBoxLayout()
        c3.addWidget(QLabel("Variable Avg of Forecast:"))
        c3.addStretch()
        self.capex_var_avg = QLabel("-")
        capex_layout.addLayout(c3)

        c4 = QHBoxLayout()
        c4.addWidget(QLabel("Implied LT Cash Flow Growth:"))
        c4.addStretch()
        self.capex_lt_growth = QLabel("-")
        capex_layout.addLayout(c4)

        c5 = QHBoxLayout()
        c5.addWidget(QLabel("Dep. as % of CapEx:"))
        self.capex_dep_pct = QLineEdit("100.0%")
        self.capex_dep_pct.setStyleSheet(INPUT_STYLE)
        self.capex_dep_pct.setFixedWidth(60)
        c5.addWidget(self.capex_dep_pct)
        capex_layout.addLayout(c5)

        capex_frame.setLayout(capex_layout)
        self._footer_hbox.addWidget(capex_frame, 1)

    # ------------------------------------------------------------------
    # DATA ACCESS — Subject Financials, with period-aware routing
    # ------------------------------------------------------------------

    def _sf_get(self, key: str, period_label: str) -> Optional[float]:
        """
        Single source of truth for every IS/BS line item on this page.

        Routes through SubjectFinancialsPage.get_metric_value(), which
        main_window.py wires up as the bound method
        self.subject_financials_page.get_metric_value, so
        self._get_subject_financials IS already the
        (key, period) -> Optional[float] function — call it directly.

        Per Ted's "pull from the most recent level" rule, we don't
        trace through the public/private branching or the
        MarketScreener -> ProjectionModule -> SubjectFinancials
        resolution chain here — Subject Financials already baked
        all of that in.

        Returns None if the metric isn't available for this period
        (e.g. a calc row whose raw components are all blank, or a
        projection period whose key isn't tracked by ProjectionData).
        """
        return self._get_subject_financials(key, period_label)


    # ------------------------------------------------------------------
    # HELPER — safe cell writing
    # ------------------------------------------------------------------

    def _set(self, row_label: str, data_idx: int, text: str):
        idx = self._row_idx.get(row_label)
        if idx is None:
            return
        lbl = self._calc_labels.get(idx, {}).get(data_idx)
        if lbl is not None:
            lbl.setText(text)

    def _set_pct(self, row_label: str, data_idx: int, value: Optional[float]):
        self._set(row_label, data_idx, _fmt_pct(value))

    def _set_currency(self, row_label: str, data_idx: int, value: Optional[float]):
        self._set(row_label, data_idx, _fmt_currency(value))

    # ------------------------------------------------------------------
    # RECALCULATION
    # ------------------------------------------------------------------

    def _recalculate(self):
        self._rebuild_table_if_needed()

        inputs = self.get_project_inputs()
        wacc_val = self.get_wacc_value()

        self.lbl_client.setText(inputs.client)
        self.lbl_subject.setText(inputs.subject_company_name)
        self.lbl_date.setText(f"As of {inputs.valuation_date}")

        pct_str = f"{wacc_val * 100:.2f}%" if wacc_val is not None else "N/A%"
        if self.pv_factor_row_label is not None:
            self.pv_factor_row_label.setText(f"Present Value Factor @ {pct_str}")

        fye_years = self._compute_fye_years(inputs)
        for label, lbl_widget in self._fye_labels.items():
            lbl_widget.setText(fye_years.get(label, ""))

        # EBIT row's label flips between "EBIT" (FCFF) and "EBT"
        # (FCFE) on every recalc. The row's data identity is
        # unchanged — only the text changes.
        self._update_ebit_row_label()

        # Net Interest Expense row's projected-column behavior flips
        # with the FCFF/FCFE toggle. In FCFF the row is hidden (label
        # AND every projected cell invisible). In FCFE the row stays
        # visible and projected cells return the 8008135 placeholder.
        self._apply_net_int_proj_visibility()

        # Per-cell calculations
        self._populate_revenue_and_growth(inputs)
        self._populate_cogs_through_ebitda()
        self._populate_dep_amort_net_int()
        self._populate_ebit_and_ebit_margin()
        self._populate_taxes(inputs)
        self._populate_nopat()
        self._populate_capex_other_nwc()
        self._populate_fcf()
        self._populate_pv_chain(wacc_val, inputs)

    # ------------------------------------------------------------------
    # DYNAMIC ROWS
    # ------------------------------------------------------------------

    def _update_ebit_row_label(self):
        """EBIT <-> EBT dynamic label based on Cash Flows toggle."""
        if self._ebit_grid_row is None:
            return
        lbl_item = self.table_grid.itemAtPosition(self._ebit_grid_row, 0)
        if lbl_item is None:
            return
        widget = lbl_item.widget()
        if widget is None:
            return
        new_text = "EBT" if self._cash_flows_to == "FCFE" else "EBIT"
        widget.setText(new_text)

    def _apply_net_int_proj_visibility(self):
        if self._net_int_grid_row is None:
            return

        is_fcff = (self._cash_flows_to == "FCFF")

        lbl_item = self.table_grid.itemAtPosition(self._net_int_grid_row, 0)
        if lbl_item is not None:
            lbl_item.widget().setVisible(not is_fcff)

        for data_idx in range(len(self._headers)):
            is_hist_col = self._is_historical[data_idx]
            grid_col = self._grid_col(data_idx)
            lbl_item = self.table_grid.itemAtPosition(self._net_int_grid_row, grid_col)
            if lbl_item is None:
                continue
            widget = lbl_item.widget()
            if widget is None:
                continue

            if is_hist_col:
                widget.setVisible(True)
            else:
                widget.setVisible(not is_fcff)
                if is_fcff:
                    widget.setText("0")
                else:
                    widget.setText(str(NET_INT_PROJ_PLACEHOLDER))


    # ------------------------------------------------------------------
    # ROW POPULATION
    # ------------------------------------------------------------------

    def _populate_revenue_and_growth(self, inputs):
        for data_idx, label in enumerate(self._headers):
            if label == "Residual":
                # Revenue Growth for Residual = LTGR (per Ted's
                # terminal-value note: all TV calcs use the CF
                # growing at LTGR, so the growth rate at the
                # bridge is the LTGR itself).
                self._set("Revenue Growth", data_idx, "")
                continue

            rev = self._sf_get("revenue", label)
            self._set_currency("Revenue", data_idx, rev)

            if data_idx == 0:
                # LFY-4 (or LFY-0 if hist_years=0) — no prior period.
                # Per Ted: render blank, not "-", so there's no
                # confusion about whether the missing value is a
                # calculation artifact or a real zero.
                self._set("Revenue Growth", data_idx, "")
                continue

            # Growth: current / prior - 1. "Prior" is the data column
            # to the immediate left in display order. For NFY, that's
            # LFY. For LFY, that's LFY-1. Etc.
            prior_label = self._headers[data_idx - 1]
            curr = self._sf_get("revenue", label)
            prior = self._sf_get("revenue", prior_label)
            if curr is not None and prior is not None and prior != 0:
                self._set_pct("Revenue Growth", data_idx, curr / prior - 1.0)
            else:
                self._set("Revenue Growth", data_idx, "-")

    def _populate_cogs_through_ebitda(self):
        for data_idx, label in enumerate(self._headers):
            if self._is_historical[data_idx]:
                rev = self._sf_get("revenue", label)
                gp = self._sf_get("gross_profit", label)
                cogs = self._sf_get("cost_of_goods_sold", label)
                opex = self._sf_get("operating_expenses", label)
                ebitda = self._sf_get("ebitda", label)
            else:
                # ProjectionData tracks five fields directly. Read
                # them. COGS and OpEx aren't tracked there, so
                # derive from LFY ratios held forward.
                pd = self._get_projection_data()
                rev = pd.revenue.get(label)
                gp = pd.gross_profit.get(label)
                ebitda = pd.ebitda.get(label)
                gp_lfy = self._sf_get("gross_profit", "LFY")
                rev_lfy = self._sf_get("revenue", "LFY")
                opex_lfy = self._sf_get("operating_expenses", "LFY")
                if rev is not None and gp_lfy is not None and rev_lfy not in (None, 0):
                    cogs = rev - (rev * (gp_lfy / rev_lfy))
                else:
                    cogs = None
                if gp is not None and opex_lfy is not None and gp_lfy not in (None, 0):
                    opex = gp * (opex_lfy / gp_lfy)
                else:
                    opex = None

            self._set_currency("Cost of Goods Sold", data_idx, cogs)
            self._set_currency("Gross Profit", data_idx, gp)
            self._set_currency("Operating Expenses", data_idx, opex)
            self._set_currency("EBITDA", data_idx, ebitda)

            self._set_pct("Gross Profit Margin", data_idx, _safe_div(gp, rev))
            self._set_pct("EBITDA Margin", data_idx, _safe_div(ebitda, rev))


    def _populate_dep_amort_net_int(self):
        """
        Depreciation + Amortization: pull from Subject Financials.
        Net Interest Expense (historical only here — projected
        handled in _apply_net_int_proj_visibility):

            Net Int = -(Interest Expense) + Interest Income

        Ted's sign-flip rule: Interest Expense is stored as a
        positive number on Subject Financials' IS (i.e. it's an
        expense, not a negative), so we negate it to match the DCF
        convention where Net Interest Expense is positive when
        interest cost exceeds interest income.
        """
        for data_idx, label in enumerate(self._headers):
            if self._is_historical[data_idx]:
                dep = self._sf_get("depreciation", label)
                amort = self._sf_get("amortization", label)
                int_exp = self._sf_get("interest_expense", label)
                int_inc = self._sf_get("interest_income", label)
                # Both None -> None. Otherwise compute, treating
                # missing components as 0.
                if int_exp is None and int_inc is None:
                    net_int = None
                else:
                    net_int = -(int_exp or 0.0) + (int_inc or 0.0)
                self._set_currency("Depreciation", data_idx, dep)
                self._set_currency("Amortization", data_idx, amort)
                self._set_currency("Net Interest Expense", data_idx, net_int)
            else:
                pd = self._get_projection_data()
                self._set_currency("Depreciation", data_idx, pd.da.get(label))
                self._set_currency("Amortization", data_idx, 0)
                # Net Int projected cell handled in
                # _apply_net_int_proj_visibility.


    def _populate_ebit_and_ebit_margin(self):
        """
        FCFF: EBIT = EBITDA - Depreciation - Amortization
        FCFE: EBT  = EBITDA - Depreciation - Amortization
                       - Net Interest Expense

        Per Ted's "subject to whichever's most recent level" rule,
        depreciation/amortization come from Subject Financials even
        in projected columns (where they currently come back as
        None), so EBIT in projected columns will compute to None
        rather than silently using a Project Module value. This is
        the conservative behavior — better to show a dash than
        guess.
        """
        for data_idx, label in enumerate(self._headers):
            if self._is_historical[data_idx]:
                ebitda = self._sf_get("ebitda", label)
                dep = self._sf_get("depreciation", label)
                amort = self._sf_get("amortization", label)
            else:
                pd = self._get_projection_data()
                ebitda = pd.ebitda.get(label)
                dep = pd.da.get(label)
                amort = 0


            # Net Interest Expense for EBT calc. In projected cells
            # the displayed value follows the FCFF/FCFE toggle, but
            # for the actual EBT arithmetic we want the same data
            # the row shows.
            if self._is_historical[data_idx]:
                int_exp = self._sf_get("interest_expense", label)
                int_inc = self._sf_get("interest_income", label)
                if int_exp is None and int_inc is None:
                    net_int = None
                else:
                    net_int = -(int_exp or 0.0) + (int_inc or 0.0)
            else:
                net_int = 0.0


            if ebitda is None or dep is None or amort is None:
                ebit_or_ebt = None
            elif self._cash_flows_to == "FCFF":
                ebit_or_ebt = ebitda - dep - amort
            else:
                if net_int is None:
                    ebit_or_ebt = None
                else:
                    ebit_or_ebt = ebitda - dep - amort - net_int

            self._set_currency("EBIT", data_idx, ebit_or_ebt)

            rev = self._sf_get("revenue", label)
            self._set_pct("EBIT Margin", data_idx, _safe_div(ebit_or_ebt, rev))

    def _populate_taxes(self, inputs):
        """
        Historicals: pull from Subject Financials (already the
        post-EBT taxes on the IS).
        Projected/Residual: = (EBIT or EBT) * Tax Rate, where Tax
        Rate is the Home page Subject Company Tax Rate input.
        """
        tax_rate = inputs.subject_tax_rate
        ebit_idx = self._row_idx.get("EBIT")
        for data_idx, label in enumerate(self._headers):
            if self._is_historical[data_idx]:
                self._set_currency("Taxes", data_idx, self._sf_get("taxes", label))
            else:
                # Use the value we just wrote into the EBIT/EBT
                # row for this column. We can't call _sf_get
                # because for projection periods EBIT/EBT isn't
                # actually tracked on Subject Financials — it's a
                # local calc on this page.
                ebit_lbl = self._calc_labels.get(ebit_idx, {}).get(data_idx)
                ebit_val = _parse_label_as_float(ebit_lbl.text()) if ebit_lbl is not None else None
                if ebit_val is not None and tax_rate is not None:
                    self._set_currency("Taxes", data_idx, ebit_val * tax_rate)
                else:
                    self._set("Taxes", data_idx, "-")

    def _populate_nopat(self):
        """
        NOPAT = (EBIT or EBT) - Taxes, where both terms come from
        the values this page just wrote into their own rows in this
        recalc pass.
        """
        ebit_idx = self._row_idx.get("EBIT")
        taxes_idx = self._row_idx.get("Taxes")
        for data_idx in range(len(self._headers)):
            ebit_val = _read_label(self._calc_labels, ebit_idx, data_idx)
            tax_val = _read_label(self._calc_labels, taxes_idx, data_idx)
            if ebit_val is not None and tax_val is not None:
                self._set_currency("Net Operating Profit After Tax (NOPAT)", data_idx, ebit_val - tax_val)
            else:
                self._set("Net Operating Profit After Tax (NOPAT)", data_idx, "-")

    def _populate_capex_other_nwc(self):
        """
        Three "less" rows just above Free Cash Flow:

          Plus: Depreciation = same value as the Depreciation row
                 for historicals; LFY Depreciation carried forward
                 to projected/Residual cells (per Ted's "don't pull
                 source twice" — projections don't track
                 depreciation per-period in the current schema).

          Less: Increase/(Decrease) in DFCFNWC: placeholder 80085
                 for every column. (No real NWC wiring yet; the
                 DCF placeholder exists so the FCF formula is
                 exercisable end-to-end.)

          Less: Capital Expenditures (CapEx): from Subject
                 Financials (public "Capital Expenditures" line or
                 private equivalent).

          Less: Other Adjustments: historical = "Acquisitions"
                 from Subject Financials; projected/Residual = the
                 user input field for that column.
        """
        for data_idx, label in enumerate(self._headers):
            # Plus: Depreciation = same value as the Depreciation row
            # directly above. Per Ted: "don't pull source twice."
            if self._is_historical[data_idx]:
                plus_dep = self._sf_get("depreciation", label)
            else:
                plus_dep = self._get_projection_data().da.get(label)
            self._set_currency("Plus: Depreciation", data_idx, plus_dep)


            # NWC placeholder
            self._set("Less: Increase/(Decrease) in DFCFNWC", data_idx, str(NWC_PLACEHOLDER))

            # CapEx
            if self._is_historical[data_idx]:
                capex = self._sf_get("capex", label)
            else:
                capex = self._get_projection_data().capex.get(label)

            self._set_currency("Less: Capital Expenditures (CapEx)", data_idx, capex)

            # Other Adjustments
            other_adj_idx = self._row_idx.get("Less: Other Adjustments")
            if self._is_historical[data_idx]:
                other = self._sf_get("acquisitions", label)
                self._set_currency("Less: Other Adjustments", data_idx, other)
            else:
                inp = self._input_fields.get(other_adj_idx, {}).get(data_idx)
                if inp is not None:
                    raw = inp.text().strip()
                    if raw:
                        parsed = _parse_label_as_float(raw)
                    else:
                        parsed = 0
                    if parsed is not None:
                        inp.setText(f"{parsed:,.0f}")


    def _populate_fcf(self):
        """
        Free Cash Flow =
            NOPAT
          + Depreciation (the "Plus:" line)
          - Increase(Decrease) in DFCFNWC
          - CapEx
          - Other Adjustments

        All five inputs come from the labels this page just wrote
        in this recalc pass.
        """
        nopat_idx = self._row_idx.get("Net Operating Profit After Tax (NOPAT)")
        plus_dep_idx = self._row_idx.get("Plus: Depreciation")
        nwc_idx = self._row_idx.get("Less: Increase/(Decrease) in DFCFNWC")
        capex_idx = self._row_idx.get("Less: Capital Expenditures (CapEx)")
        other_idx = self._row_idx.get("Less: Other Adjustments")
        fcf_idx = self._row_idx.get("Free Cash Flow")

        for data_idx in range(len(self._headers)):
            nopat = _read_label(self._calc_labels, nopat_idx, data_idx)
            plus_dep = _read_label(self._calc_labels, plus_dep_idx, data_idx)
            nwc = _read_label(self._calc_labels, nwc_idx, data_idx)
            capex = _read_label(self._calc_labels, capex_idx, data_idx)
            if self._is_historical[data_idx]:
                other = _read_label(self._calc_labels, other_idx, data_idx)
            else:
                inp = self._input_fields.get(other_idx, {}).get(data_idx)
                if inp is not None:
                    raw = inp.text().strip()
                    other = _parse_label_as_float(raw) if raw else 0
                else:
                    other = None

            terms = [nopat, plus_dep, nwc, capex, other]
            if all(t is not None for t in terms):
                fcf = nopat + plus_dep - nwc - capex - other
                self._set_currency("Free Cash Flow", data_idx, fcf)
            else:
                self._set("Free Cash Flow", data_idx, "-")

    def _populate_pv_chain(self, wacc_val: Optional[float], inputs):
        """
        Discounting chain (per Ted's mid-period convention):

          Partial Period Adjustment (NFY only):
            (NFY year - Valuation Date year) / 365.25
            Computed from Home page's Next Fiscal Year and
            Valuation Date strings. Both parse via the same
            multi-format _parse_year helper.

          Present Value Period (projected columns + Residual):
            NFY:      PPA / 2
            NFY+1:    NFY_PVP * 2 + 0.5
            NFY+2:    prior_PVP + 1
            NFY+3+:   prior_PVP + 1
            Residual: same formula chain as the projected cols;
                      since Residual comes after the last projected
                      column, its PVP = prior (NFY+9) PVP + 1.

          Present Value Factor: 1 / (1 + wacc) ^ PVP.
            If WACC is None, show "-" for every projected column.

          Present Value of Free Cash Flows:
            NFY: FCF * PPA * PVF
            NFY+1..NFY+N, Residual: FCF * PVF

        Historical columns are intentionally blank for all four
        rows — historical FCF is never discounted.
        """
        ppa = None
        nfy_str = inputs.next_fiscal_year
        val_date_str = inputs.valuation_date
        if nfy_str and val_date_str:
            for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m-%d-%Y"):
                try:
                    nfy_dt = datetime.strptime(nfy_str.strip(), fmt)
                    val_dt = datetime.strptime(val_date_str.strip(), fmt)
                    ppa = (nfy_dt - val_dt).days / 365.25
                    break
                except ValueError:
                    continue
        if ppa is not None and ppa <= 0:
            ppa = None


        fcf_idx = self._row_idx.get("Free Cash Flow")
        pvf_idx = self._row_idx.get("Present Value Factor")
        pvp_idx = self._row_idx.get("Present Value Period")
        pv_fcf_idx = self._row_idx.get("Present Value of Free Cash Flows")
        ppa_idx = self._row_idx.get("Partial Period Adjustment")

        # PPA only in NFY column. Every other column (historical or
        # other-projected) is blank for PPA.
        for data_idx, label in enumerate(self._headers):
            if label == "NFY":
                if ppa is not None:
                    self._set("Partial Period Adjustment", data_idx, f"{ppa:.2f}")
                else:
                    self._set("Partial Period Adjustment", data_idx, "-")
            else:
                self._set("Partial Period Adjustment", data_idx, "")

        # PVP, PVF, PV-FCF per projected/Residual column
        prior_pvp: Optional[float] = None
        for data_idx, label in enumerate(self._headers):
            if self._is_historical[data_idx]:
                # Historical cells left blank by HIST_BLANK_ROWS
                # styling. Nothing to do.
                continue

            if label == "NFY":
                pvp = (ppa / 2.0) if ppa is not None else None
            elif label == "NFY+1":
                if prior_pvp is None:
                    pvp = None
                else:
                    pvp = prior_pvp * 2.0 + 0.5
            else:
                # NFY+2, NFY+3, ... and Residual
                if prior_pvp is None:
                    pvp = None
                else:
                    pvp = prior_pvp + 1.0

            if pvp is not None:
                self._set("Present Value Period", data_idx, f"{pvp:.2f}")
            else:
                self._set("Present Value Period", data_idx, "-")

            prior_pvp = pvp

            # PVF
            if pvp is not None and wacc_val is not None and wacc_val > 0:
                pvf = 1.0 / ((1.0 + wacc_val) ** pvp)
                self._set("Present Value Factor", data_idx, f"{pvf:.2f}")
            else:
                self._set("Present Value Factor", data_idx, "-")

            # PV of FCF
            fcf = _read_label(self._calc_labels, fcf_idx, data_idx)
            pvf = _read_label(self._calc_labels, pvf_idx, data_idx) if pvp is not None and wacc_val is not None else None
            if fcf is not None and pvf is not None:
                if label == "NFY" and ppa is not None:
                    pv_fcf = fcf * ppa * pvf
                else:
                    pv_fcf = fcf * pvf
                self._set_currency("Present Value of Free Cash Flows", data_idx, pv_fcf)
            else:
                self._set("Present Value of Free Cash Flows", data_idx, "-")

    # ------------------------------------------------------------------
    # SESSION STATE
    # ------------------------------------------------------------------

    def collect_state(self) -> dict:
        # Capture the "Less: Other Adjustments" projected/Residual
        # user inputs by period label so apply_state can restore
        # them after a table rebuild.
        other_adj_idx = self._row_idx.get("Less: Other Adjustments")
        other_adj: Dict[str, str] = {}
        for data_idx, label in enumerate(self._headers):
            inp = self._input_fields.get(other_adj_idx, {}).get(data_idx)
            if inp is not None:
                other_adj[label] = inp.text()
        return {
            "ltg_input": self.ltg_input.text(),
            "res_use_combo": self.res_use_combo.currentText(),
            "res_year_input": self.res_year_input.text(),
            "chk_ebitda": self.chk_ebitda.isChecked(),
            "chk_rev": self.chk_rev.isChecked(),
            "chk_h": self.chk_h.isChecked(),
            "capex_ltg": self.capex_ltg.text(),
            "capex_dep_pct": self.capex_dep_pct.text(),
            "cash_flows_to": self._cash_flows_to,
            "other_adj_inputs": other_adj,
        }

    def apply_state(self, state: dict):
        if not state:
            return
        self.ltg_input.setText(state.get("ltg_input", "3.0%"))
        self.res_year_input.setText(state.get("res_year_input", "2035"))
        self.capex_ltg.setText(state.get("capex_ltg", "425"))
        self.capex_dep_pct.setText(state.get("capex_dep_pct", "100.0%"))
        self._cash_flows_to = state.get("cash_flows_to", "FCFF")
        # Other-adjustment inputs are restored AFTER
        # _rebuild_table_if_needed has created the new input widgets
        # (via _recalculate). We recalc, push saved text into the
        # QLineEdits, then recalc again so the FCF / PV chain picks
        # up the restored values.
        self._recalculate()
        other_adj_idx = self._row_idx.get("Less: Other Adjustments")
        other_adj = state.get("other_adj_inputs", {})
        for data_idx, label in enumerate(self._headers):
            inp = self._input_fields.get(other_adj_idx, {}).get(data_idx)
            if inp is not None and label in other_adj:
                inp.setText(other_adj[label])
        self._recalculate()
