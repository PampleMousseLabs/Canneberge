import math
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


def _fmt_currency(value: Optional[float]) -> str:
    if value is None or math.isnan(value) or math.isinf(value):
        return "-"
    return f"{value:,.0f}"


def _fmt_pct(value: Optional[float]) -> str:
    if value is None or math.isnan(value) or math.isinf(value):
        return "-"
    return f"{value:.1%}"


def _make_section_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(HEADER_STYLE)
    lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    return lbl


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

        self.table_container = None
        self._built_hist_years = None
        self._built_proj_years = None
        self._table_insert_index = 0
        self._num_hist = 0
        self._num_proj = 0

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
        if dialog.exec():
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
            ("Less: Increase/(Decrease) in DCF/NWC", False, False, True, False),
            ("Less: Capital Expenditures (CapEx)", False, False, True, False),
            ("Less: Other Adjustments", False, False, True, False),
            ("Free Cash Flow", True, False, False, False),
            ("Partial Period Adjustment", False, False, False, False),
            ("Present Value Period", False, False, False, False),
            ("Present Value Factor", False, False, False, False),
            ("Present Value of Free Cash Flows", True, False, False, False),
        ]

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

            self._calc_labels[idx] = {}
            self._input_fields[idx] = {}

            for data_idx in range(len(self._headers)):
                grid_col = self._grid_col(data_idx)
                is_hist_col = self._is_historical[data_idx]

                if is_input:
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

    def collect_state(self) -> dict:
        return {
            "ltg_input": self.ltg_input.text(),
            "res_use_combo": self.res_use_combo.currentText(),
            "res_year_input": self.res_year_input.text(),
            "chk_ebitda": self.chk_ebitda.isChecked(),
            "chk_rev": self.chk_rev.isChecked(),
            "chk_h": self.chk_h.isChecked(),
            "capex_ltg": self.capex_ltg.text(),
            "capex_dep_pct": self.capex_dep_pct.text(),
        }

    def apply_state(self, state: dict):
        if not state:
            return
        self.ltg_input.setText(state.get("ltg_input", "3.0%"))
        self.res_year_input.setText(state.get("res_year_input", "2035"))
        self.capex_ltg.setText(state.get("capex_ltg", "425"))
        self.capex_dep_pct.setText(state.get("capex_dep_pct", "100.0%"))
        self._recalculate()