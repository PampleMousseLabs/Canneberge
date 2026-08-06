"""
NWC — Net Working Capital schedule.

Architecture notes / deliberate deviations from the literal Excel
screenshot, per Ted's "borrow exactly what is from the DCF page,
don't pay attention to screenshot year numbers" instruction:

- Header band (Historical/Projected Financials, FYE row) is built the
  same way DCF's is: historical columns from a LOCAL, unlinked
  Years-of-Historical spinbox; projected columns from the SAME global
  projection_years as every other page (linked, per Ted's instruction);
  plus a Residual column whose Total Revenue is pulled directly from
  DCF's own Residual Revenue (DCF is the single source of truth for
  Residual — NWC does not re-derive it).

- Added a TTM column between the historical block and NFY that isn't
  part of DCF's own header set. DCF deliberately has no TTM column,
  but Ted's own "Changes in NWC" formula explicitly starts at
  "NFY - TTM", so TTM has to exist as a real column here, not just an
  off-grid scalar lookup. This is the one place this page's headers
  differ from DCF's.

- "Net Working Capital (Historical)" and "Net Working Capital
  (Projected)" are described as two lines in the instructions, but
  built here as ONE row whose formula branches by column type — same
  pattern as every multi-formula row on the DCF page (Depreciation,
  EBIT, etc.). Two same-named-concept rows would be inconsistent with
  how the rest of this app represents "one line, different formula
  per column type."

- The Excel screenshot's "Long Term Growth Rate" field on this page
  is not implemented — nothing in the given formula list uses it.
  Residual Total Revenue is pulled pre-grown from DCF (which already
  applied LTGR internally), so this page has no independent use for
  its own LTGR input. Flag if that's wrong.

- Current Asset / Current Liability line items have NO projected
  values anywhere in this app (Subject Financials' BS is never
  projected — only IS periods get ProjectionData). This means:
    * CA/CL row cells are blank ("-") for every projected column and
      Residual — there's nothing to pull.
    * "Turnover Ratios" NWC Basis, whose projected-period formula per
      Ted's instructions is literally "(Current Assets - Current
      Liabilities)", is therefore also blank on projected columns —
      not a bug, there's no BS projection to feed it. Only "% of
      Revenue" basis actually produces projected NWC values right now.

- GPC NWC section: structure only, per "just get the setup... I will
  tell you the calculations afterwards" — ticker rows, Exclude(X)
  checkboxes, and the LFY-2/LFY-1/LFY/TTM column grid are all real;
  the per-cell values and Max/Min rows are static placeholders, not
  wired to any computation yet.
"""

import math
import statistics
from typing import Optional, Dict, List

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QLineEdit,
    QScrollArea, QFrame, QComboBox, QSpinBox, QCheckBox, QSizePolicy
)
from PyQt6.QtCore import Qt

from Canneberge.app_state import BS_LINES
from Canneberge.Ui.gpc_page import _quartile
from Canneberge.Ui.dcf_page import (
    BOLD_STYLE, INPUT_STYLE, HEADER_STYLE, INDENT_STYLE, MARGIN_ROW_STYLE,
    MARGIN_CELL_STYLE, COL_WIDTH, BORDER_COLOR,
    _fmt_currency, _fmt_pct, _safe_div, _sub_strict as _sub, _mul_strict as _mul,
    _parse_label_as_float, _read_label,
)

# Current Asset / Current Liability candidate keys — these are
# literally BS_LINES' own current-asset and current-liability
# sections (7 rows each, not a coincidence with "up to 7" in the spec
# — that's the full schema StockAnalysis's BS scrape has for each).
CA_CANDIDATES = [
    "cash", "st_investments", "accounts_receivable", "receivables",
    "other_receivables", "inventory", "other_current_assets",
]
CL_CANDIDATES = [
    "st_debt", "current_ltd", "current_leases", "accounts_payable",
    "accrued_expenses", "unearned_revenue", "other_current_liab",
]

CASH_KEYS = {"cash"}
DEBT_KEYS = {"st_debt", "current_ltd", "current_leases"}

_BS_LABEL_BY_KEY = {k: label for k, label, *_r in BS_LINES}

CA_DEFAULT_SELECTIONS = ["cash", "accounts_receivable", "inventory", "other_current_assets", "", "", ""]
CL_DEFAULT_SELECTIONS = ["accounts_payable", "other_current_liab", "", "", "", "", ""]

# Purple borders for the GPC section's "Surplus/(Deficit)" total line
# — this page's one deliberate style deviation from DCF's black
# borders, matching the Excel model's purple section banding. Kept
# local rather than added to DCF's shared STYLE CONFIG since nothing
# else on this page (or DCF) uses purple.
NWC_BORDER_PURPLE = "#4b1f7a"
BORDER_ABOVE_STYLE_PURPLE = f"border-top: 1px solid {NWC_BORDER_PURPLE};"
BORDER_BELOW_STYLE_PURPLE = f"border-bottom: 3px solid {NWC_BORDER_PURPLE};"


def _fmt_ca_cl_option(key: str) -> str:
    return _BS_LABEL_BY_KEY.get(key, key)


class NWCPage(QWidget):
    def __init__(self,
                 get_project_inputs_callback,
                 get_subject_financials_callback,
                 get_dcf_residual_revenue_callback,
                 update_projection_callback):
        super().__init__()
        self.get_project_inputs = get_project_inputs_callback
        self._get_subject_financials = get_subject_financials_callback
        self._get_dcf_residual_revenue = get_dcf_residual_revenue_callback
        self._update_projection_callback = update_projection_callback

        self._calc_labels: Dict[int, Dict[int, QLabel]] = {}
        self._row_idx: Dict[str, int] = {}
        self._headers: List[str] = []
        self._is_historical: List[bool] = []
        self._fye_labels: Dict[str, QLabel] = {}

        self._ca_combos: List[QComboBox] = []
        self._cl_combos: List[QComboBox] = []
        self._ca_value_labels: List[Dict[int, QLabel]] = []
        self._cl_value_labels: List[Dict[int, QLabel]] = []

        self.table_container = None
        self._built_hist_years = None
        self._built_proj_years = None
        self._table_insert_index = 0
        self._num_hist = 0
        self._num_proj = 0

        # Local, unlinked — per Ted: only Years of Projections syncs
        # with the rest of the app.
        self._nwc_historical_years = 5

        self._gpc_row_widgets: List[dict] = []

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
        self._rebuild_table_if_needed()

        self.page_layout.addSpacing(16)
        self.page_layout.addWidget(self._build_gpc_section())

        self.page_layout.addStretch(1)
        self.page_container.setLayout(self.page_layout)
        scroll.setWidget(self.page_container)

        outer = QVBoxLayout()
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)
        self.setLayout(outer)

    def _build_header_controls(self):
        inputs = self.get_project_inputs()

        title_row = QHBoxLayout()
        title_row.addWidget(QLabel(inputs.client, styleSheet=BOLD_STYLE))
        title_row.addWidget(QLabel(inputs.subject_company_name))
        title_row.addWidget(QLabel("Net Working Capital Schedule"))
        title_row.addStretch(1)
        self.page_layout.addLayout(title_row)

        controls = QHBoxLayout()

        controls.addWidget(QLabel("Years of Historical:"))
        self.hist_years_spin = QSpinBox()
        self.hist_years_spin.setRange(1, 5)
        self.hist_years_spin.setValue(self._nwc_historical_years)
        self.hist_years_spin.valueChanged.connect(self._on_hist_years_changed)
        controls.addWidget(self.hist_years_spin)

        controls.addSpacing(24)
        controls.addWidget(QLabel("Years of Projections:"))
        self.proj_years_spin = QSpinBox()
        self.proj_years_spin.setRange(1, 15)
        self.proj_years_spin.setValue(inputs.projection_years)
        self.proj_years_spin.valueChanged.connect(self._on_proj_years_changed)
        controls.addWidget(self.proj_years_spin)

        controls.addSpacing(24)
        controls.addWidget(QLabel("NWC Cash Treatment:"))
        self.cash_treatment_combo = QComboBox()
        self.cash_treatment_combo.addItems(["Excluding Cash", "Including Cash"])
        self.cash_treatment_combo.setStyleSheet(INPUT_STYLE)
        self.cash_treatment_combo.currentTextChanged.connect(self._recalculate)
        controls.addWidget(self.cash_treatment_combo)

        controls.addSpacing(24)
        controls.addWidget(QLabel("NWC Basis:"))
        self.nwc_basis_combo = QComboBox()
        self.nwc_basis_combo.addItems(["% of Revenue", "Turnover Ratios"])
        self.nwc_basis_combo.setStyleSheet(INPUT_STYLE)
        self.nwc_basis_combo.currentTextChanged.connect(self._recalculate)
        controls.addWidget(self.nwc_basis_combo)

        controls.addStretch(1)
        self.page_layout.addLayout(controls)

    def _on_hist_years_changed(self, value: int):
        self._nwc_historical_years = value
        self._rebuild_table_if_needed(force=True)
        self._recalculate()

    def _on_proj_years_changed(self, value: int):
        inputs = self.get_project_inputs()
        # Only projection years is linked — pass the CURRENT (unchanged)
        # global historical_years through untouched, so Home page's
        # own historical spinbox isn't disturbed by an NWC-driven call.
        self._update_projection_callback(inputs.historical_years, value)
        self._rebuild_table_if_needed(force=True)
        self._recalculate()

    # ------------------------------------------------------------------
    # COLUMNS
    # ------------------------------------------------------------------

    def _generate_columns(self):
        inputs = self.get_project_inputs()

        hist_labels = []
        for i in range(self._nwc_historical_years - 1, 0, -1):
            hist_labels.append(f"LFY-{i}")
        hist_labels.append("LFY")
        hist_labels.append("TTM")  # see module docstring

        proj_labels = list(inputs.projection_period_columns)

        self._headers = hist_labels + proj_labels + ["Residual"]
        self._is_historical = [True] * len(hist_labels) + [False] * len(proj_labels) + [False]
        self._num_hist = len(hist_labels)
        self._num_proj = len(proj_labels)
        return self._num_hist, self._num_proj

    def _grid_col(self, data_idx: int) -> int:
        num_hist, num_proj = self._num_hist, self._num_proj
        if data_idx < num_hist:
            return 1 + data_idx
        elif data_idx < num_hist + num_proj:
            return 1 + num_hist + 1 + (data_idx - num_hist)
        else:
            return 1 + num_hist + 1 + num_proj + 1

    def _sf_get(self, key: str, period: str) -> Optional[float]:
        if period == "Residual":
            return None  # BS items have no Residual — handled per-row where needed
        return self._get_subject_financials(key, period)

    # ------------------------------------------------------------------
    # TABLE BUILD
    # ------------------------------------------------------------------

    def _rebuild_table_if_needed(self, force: bool = False):
        inputs = self.get_project_inputs()
        new_hist = self._nwc_historical_years
        new_proj = inputs.projection_years

        if (not force and self.table_container is not None
                and new_hist == self._built_hist_years
                and new_proj == self._built_proj_years):
            return

        num_hist, num_proj = self._generate_columns()

        if self.table_container is not None:
            self.page_layout.removeWidget(self.table_container)
            self.table_container.deleteLater()

        self.table_container = self._build_table()
        self.page_layout.insertWidget(self._table_insert_index, self.table_container)

        self._built_hist_years = new_hist
        self._built_proj_years = new_proj

    def _build_table(self) -> QWidget:
        container = QWidget()
        grid = QGridLayout()
        grid.setSpacing(4)
        self.table_grid = grid

        num_hist, num_proj = self._num_hist, self._num_proj
        total_cols = 1 + num_hist + 1 + num_proj + 1 + 1  # label + hist + vline + proj + spacer + residual

        # --- Header bands ---
        hist_band = QLabel("Historical Financials", styleSheet=HEADER_STYLE, alignment=Qt.AlignmentFlag.AlignCenter)
        grid.addWidget(hist_band, 0, 1, 1, num_hist)

        proj_band = QLabel("Projected Financials", styleSheet=HEADER_STYLE, alignment=Qt.AlignmentFlag.AlignCenter)
        grid.addWidget(proj_band, 0, 1 + num_hist + 1, 1, num_proj)

        res_band = QLabel("", styleSheet=HEADER_STYLE)
        grid.addWidget(res_band, 0, 1 + num_hist + 1 + num_proj + 1)

        for data_idx, label in enumerate(self._headers):
            grid_col = self._grid_col(data_idx)
            lbl = QLabel(label, alignment=Qt.AlignmentFlag.AlignRight)
            if not self._is_historical[data_idx]:
                lbl.setStyleSheet(BOLD_STYLE)
            lbl.setFixedWidth(COL_WIDTH)
            grid.addWidget(lbl, 1, grid_col)

        grid.addWidget(QLabel("FYE", styleSheet=BOLD_STYLE), 2, 0)
        for data_idx, label in enumerate(self._headers):
            grid_col = self._grid_col(data_idx)
            fye_lbl = QLabel("", alignment=Qt.AlignmentFlag.AlignRight)
            fye_lbl.setFixedWidth(COL_WIDTH)
            grid.addWidget(fye_lbl, 2, grid_col)
            self._fye_labels[label] = fye_lbl

        self._current_table_row = 3
        self._calc_labels = {}
        self._row_idx = {}
        self._ca_combos = []
        self._cl_combos = []
        self._ca_value_labels = []
        self._cl_value_labels = []

        # --- Total Revenue ---
        self._add_calc_row(grid, "Total Revenue", bold=True)
        self._current_table_row += 1  # spacer

        # --- Current Assets ---
        for i in range(7):
            self._add_ca_cl_row(grid, is_asset=True, slot=i)
        self.ca_sum_row_idx = self._add_calc_row(grid, "Total Current Assets", bold=True,
                                                  border_above=True)
        self._current_table_row += 1  # spacer

        # --- Current Liabilities ---
        for i in range(7):
            self._add_ca_cl_row(grid, is_asset=False, slot=i)
        self.cl_sum_row_idx = self._add_calc_row(grid, "Total Current Liabilities", bold=True,
                                                  border_above=True)
        self._current_table_row += 1  # spacer

        # --- NWC / NWC% / Changes ---
        self._add_calc_row(grid, "Net Working Capital", bold=True, border_above=True)
        self._add_calc_row(grid, "Net Working Capital % of Revenue", margin=True)
        self._current_table_row += 1  # spacer
        self._add_calc_row(grid, "Changes in Net Working Capital", border_above=True)

        grid.setRowStretch(self._current_table_row + 1, 1)
        container.setLayout(grid)
        return container

    def _add_calc_row(self, grid: QGridLayout, label: str, bold: bool = False,
                       margin: bool = False, border_above: bool = False) -> int:
        row = self._current_table_row
        row_lbl = QLabel(label)
        style_parts = []
        if bold:
            style_parts.append(BOLD_STYLE)
        if margin:
            style_parts.append(MARGIN_ROW_STYLE)
        if border_above:
            style_parts.append(f"border-top: 1px solid {BORDER_COLOR};")
        if style_parts:
            row_lbl.setStyleSheet(" ".join(style_parts))
        grid.addWidget(row_lbl, row, 0, alignment=Qt.AlignmentFlag.AlignLeft)

        cells: Dict[int, QLabel] = {}
        for data_idx in range(len(self._headers)):
            grid_col = self._grid_col(data_idx)
            lbl = QLabel("-", alignment=Qt.AlignmentFlag.AlignRight)
            lbl.setFixedWidth(COL_WIDTH)
            cell_style = []
            if bold:
                cell_style.append(BOLD_STYLE)
            if margin:
                cell_style.append(MARGIN_CELL_STYLE)
            if border_above:
                cell_style.append(f"border-top: 1px solid {BORDER_COLOR};")
            if cell_style:
                lbl.setStyleSheet(" ".join(cell_style))
            grid.addWidget(lbl, row, grid_col)
            cells[data_idx] = lbl

        row_idx = row
        self._calc_labels[row_idx] = cells
        self._row_idx[label] = row_idx
        self._current_table_row += 1
        return row_idx

    def _add_ca_cl_row(self, grid: QGridLayout, is_asset: bool, slot: int):
        row = self._current_table_row
        candidates = CA_CANDIDATES if is_asset else CL_CANDIDATES
        defaults = CA_DEFAULT_SELECTIONS if is_asset else CL_DEFAULT_SELECTIONS

        combo = QComboBox()
        combo.addItem("-- None --", "")
        for key in candidates:
            combo.addItem(_fmt_ca_cl_option(key), key)
        default_key = defaults[slot]
        idx = combo.findData(default_key)
        combo.setCurrentIndex(idx if idx >= 0 else 0)
        combo.setStyleSheet(INPUT_STYLE)
        combo.currentIndexChanged.connect(self._recalculate)
        grid.addWidget(combo, row, 0)

        cells: Dict[int, QLabel] = {}
        for data_idx in range(len(self._headers)):
            grid_col = self._grid_col(data_idx)
            lbl = QLabel("-", alignment=Qt.AlignmentFlag.AlignRight)
            lbl.setFixedWidth(COL_WIDTH)
            grid.addWidget(lbl, row, grid_col)
            cells[data_idx] = lbl

        if is_asset:
            self._ca_combos.append(combo)
            self._ca_value_labels.append(cells)
        else:
            self._cl_combos.append(combo)
            self._cl_value_labels.append(cells)

        self._current_table_row += 1

    # ------------------------------------------------------------------
    # GPC NWC SECTION (structure only — calcs pending)
    # ------------------------------------------------------------------

    def _build_gpc_section(self) -> QWidget:
        frame = QFrame()
        frame.setFrameShape(QFrame.Shape.StyledPanel)
        outer = QVBoxLayout()
        outer.addWidget(QLabel("Net Working Capital % of Revenue", styleSheet=BOLD_STYLE))

        grid = QGridLayout()
        grid.setSpacing(4)
        headers = ["Exclude (X)", "Guideline Public Company", "LFY - 2", "LFY - 1", "LFY", "TTM"]
        for c, h in enumerate(headers):
            grid.addWidget(QLabel(h, styleSheet=BOLD_STYLE), 0, c)

        inputs = self.get_project_inputs()
        tickers = inputs.gpc_tickers or []

        self._gpc_row_widgets = []
        r = 1
        for ticker in tickers:
            chk = QCheckBox()
            chk.stateChanged.connect(self._recalculate)
            grid.addWidget(chk, r, 0, alignment=Qt.AlignmentFlag.AlignCenter)
            grid.addWidget(QLabel(ticker), r, 1)
            value_labels = []
            for c in range(4):
                lbl = QLabel("-", alignment=Qt.AlignmentFlag.AlignRight)
                lbl.setFixedWidth(COL_WIDTH)
                grid.addWidget(lbl, r, 2 + c)
                value_labels.append(lbl)
            self._gpc_row_widgets.append({"ticker": ticker, "exclude": chk, "values": value_labels})
            r += 1

        # Same six statistics used everywhere else in this app (GPC
        # multiples, WACC beta) — Maximum/Third Quartile/Average/
        # Median/First Quartile/Minimum, exclude-aware. Per-ticker NWC
        # % values themselves aren't wired yet (Ted hasn't given that
        # formula/cash-toggle interaction), so these will read "NA"
        # until those cells populate — the stat machinery itself
        # doesn't depend on that being done first.
        self._gpc_stat_labels: Dict[str, List[QLabel]] = {}
        for stat_label in ("Maximum", "Third Quartile", "Average", "Median", "First Quartile", "Minimum"):
            grid.addWidget(QLabel(stat_label, styleSheet=BOLD_STYLE), r, 1)
            row_labels = []
            for c in range(4):
                lbl = QLabel("-", alignment=Qt.AlignmentFlag.AlignRight)
                lbl.setFixedWidth(COL_WIDTH)
                grid.addWidget(lbl, r, 2 + c)
                row_labels.append(lbl)
            self._gpc_stat_labels[stat_label] = row_labels
            r += 1

        outer.addLayout(grid)
        outer.addSpacing(10)

        # --- Selected row: user input %, aligned under TTM ---
        selected_row = QHBoxLayout()
        selected_row.addWidget(QLabel("Selected"))
        selected_row.addStretch(1)
        self.selected_nwc_pct_input = QLineEdit("15.0%")
        self.selected_nwc_pct_input.setStyleSheet(INPUT_STYLE)
        self.selected_nwc_pct_input.setFixedWidth(COL_WIDTH)
        self.selected_nwc_pct_input.editingFinished.connect(self._recalculate)
        selected_row.addWidget(self.selected_nwc_pct_input)
        outer.addLayout(selected_row)

        outer.addSpacing(14)

        def bridge_row(label_text: str, bold=False, border_above=None, border_below=None) -> QLabel:
            h = QHBoxLayout()
            lbl_widget = QLabel(label_text)
            style = []
            if bold:
                style.append(BOLD_STYLE)
            if border_above:
                style.append(border_above)
            if style:
                lbl_widget.setStyleSheet(" ".join(style))
            h.addWidget(lbl_widget)
            h.addStretch(1)
            val_lbl = QLabel("-", alignment=Qt.AlignmentFlag.AlignRight)
            val_lbl.setFixedWidth(COL_WIDTH)
            val_style = []
            if bold:
                val_style.append(BOLD_STYLE)
            if border_above:
                val_style.append(border_above)
            if border_below:
                val_style.append(border_below)
            if val_style:
                val_lbl.setStyleSheet(" ".join(val_style))
            h.addWidget(val_lbl)
            outer.addLayout(h)
            return val_lbl

        self.normalized_nwc_label = bridge_row("Normalized Net Working Capital")
        self.actual_nwc_label = bridge_row("Actual Net Working Capital")
        self.nwc_surplus_deficit_label = bridge_row(
            "Net Working Capital Surplus/(Deficit)",
            bold=True,
            border_above=BORDER_ABOVE_STYLE_PURPLE,
            border_below=BORDER_BELOW_STYLE_PURPLE,
        )

        frame.setLayout(outer)
        return frame

    # ------------------------------------------------------------------
    # RECALCULATE
    # ------------------------------------------------------------------

    def _recalculate(self):
        self._rebuild_table_if_needed()
        inputs = self.get_project_inputs()

        fye_years = self._compute_fye_years(inputs)
        for label, lbl_widget in self._fye_labels.items():
            lbl_widget.setText(fye_years.get(label, ""))

        include_cash = (self.cash_treatment_combo.currentText() == "Including Cash")
        pct_basis = (self.nwc_basis_combo.currentText() == "% of Revenue")

        # --- Total Revenue ---
        revenue_by_period: Dict[str, Optional[float]] = {}
        for data_idx, period in enumerate(self._headers):
            if period == "Residual":
                rev = self._get_dcf_residual_revenue()
            else:
                rev = self._sf_get("revenue", period)
            revenue_by_period[period] = rev
            self._set_cell("Total Revenue", data_idx, rev)

        # --- Current Assets / Current Liabilities rows + sums ---
        ca_sum_by_period: Dict[str, Optional[float]] = {p: None for p in self._headers}
        cl_sum_by_period: Dict[str, Optional[float]] = {p: None for p in self._headers}

        for slot, combo in enumerate(self._ca_combos):
            key = combo.currentData()
            for data_idx, period in enumerate(self._headers):
                val = self._sf_get(key, period) if key else None
                lbl = self._ca_value_labels[slot][data_idx]
                lbl.setText(_fmt_currency(val) if val is not None else "-")
                if val is not None and not (key in CASH_KEYS and not include_cash):
                    ca_sum_by_period[period] = (ca_sum_by_period[period] or 0.0) + val

        for slot, combo in enumerate(self._cl_combos):
            key = combo.currentData()
            for data_idx, period in enumerate(self._headers):
                val = self._sf_get(key, period) if key else None
                lbl = self._cl_value_labels[slot][data_idx]
                lbl.setText(_fmt_currency(val) if val is not None else "-")
                if val is not None and key not in DEBT_KEYS:
                    cl_sum_by_period[period] = (cl_sum_by_period[period] or 0.0) + val

        ca_sum_label = "Total Current Assets" if include_cash else "Cash-Free Current Assets"
        cl_sum_label = "Debt-Free Current Liabilities"
        self._retitle_row(self.ca_sum_row_idx, ca_sum_label)
        self._retitle_row(self.cl_sum_row_idx, cl_sum_label)

        for data_idx, period in enumerate(self._headers):
            self._set_cell_by_row(self.ca_sum_row_idx, data_idx, ca_sum_by_period[period])
            self._set_cell_by_row(self.cl_sum_row_idx, data_idx, cl_sum_by_period[period])

        # --- Net Working Capital / NWC% / Changes ---
        selected_pct = _parse_label_as_float(self.selected_nwc_pct_input.text())
        selected_pct = (selected_pct / 100.0) if selected_pct is not None else None

        nwc_by_period: Dict[str, Optional[float]] = {}
        for data_idx, period in enumerate(self._headers):
            is_hist = self._is_historical[data_idx]
            ca = ca_sum_by_period[period]
            cl = cl_sum_by_period[period]
            rev = revenue_by_period[period]

            if period == "Residual":
                nwc = _mul(rev, selected_pct)
            elif is_hist:
                nwc = _sub(ca, cl) if (ca is not None or cl is not None) else None
            else:
                # Projected: % of Revenue is fully wired. Turnover
                # Ratios' formula per Ted is literally CA - CL, but
                # CA/CL have no projected values anywhere in this app
                # (BS is never projected) — so it stays blank until a
                # BS projection mechanism exists, not guessed at here.
                if pct_basis:
                    nwc = _mul(rev, selected_pct)
                else:
                    nwc = _sub(ca, cl) if (ca is not None or cl is not None) else None

            nwc_by_period[period] = nwc
            self._set_cell("Net Working Capital", data_idx, nwc)
            self._set_cell("Net Working Capital % of Revenue", data_idx, _safe_div(nwc, rev), is_pct=True)

        for data_idx, period in enumerate(self._headers):
            prior_period = self._headers[data_idx - 1] if data_idx > 0 else None
            this_nwc = nwc_by_period[period]
            prior_nwc = nwc_by_period.get(prior_period) if prior_period else None
            change = _sub(this_nwc, prior_nwc) if (prior_period and this_nwc is not None and prior_nwc is not None) else None
            self._set_cell("Changes in Net Working Capital", data_idx, change)

        # --- GPC NWC % stats (Maximum/Third Quartile/Average/Median/
        # First Quartile/Minimum) — same pattern as GPC page's
        # multiples stats: collect non-excluded rows' current values
        # per column, apply the standard stat functions. The values
        # themselves are still placeholders until the per-ticker NWC%
        # formula is defined; this only wires the aggregation, which
        # doesn't depend on that.
        if hasattr(self, "_gpc_stat_labels"):
            stat_funcs = {
                "Maximum":        lambda v: max(v),
                "Third Quartile": lambda v: _quartile(v, 0.75),
                "Average":        lambda v: sum(v) / len(v),
                "Median":         lambda v: statistics.median(v),
                "First Quartile": lambda v: _quartile(v, 0.25),
                "Minimum":        lambda v: min(v),
            }
            for c in range(4):
                vals = []
                for row in self._gpc_row_widgets:
                    if row["exclude"].isChecked():
                        continue
                    v = _parse_label_as_float(row["values"][c].text())
                    if v is not None:
                        vals.append(v / 100.0)  # cell text is "25.0%" -> 25.0 raw; _fmt_pct wants a fraction
                for stat, func in stat_funcs.items():
                    lbl = self._gpc_stat_labels[stat][c]
                    if vals:
                        try:
                            lbl.setText(_fmt_pct(func(vals)))
                        except Exception:
                            lbl.setText("NA")
                    else:
                        lbl.setText("NA")

        # --- GPC bridge ---
        ttm_period = "TTM" if "TTM" in self._headers else None
        ttm_revenue = revenue_by_period.get(ttm_period) if ttm_period else None
        ttm_nwc = nwc_by_period.get(ttm_period) if ttm_period else None

        normalized_nwc = _mul(ttm_revenue, selected_pct)
        self.normalized_nwc_label.setText(_fmt_currency(normalized_nwc))
        self.actual_nwc_label.setText(_fmt_currency(ttm_nwc))
        surplus_deficit = _sub(normalized_nwc, ttm_nwc) if (normalized_nwc is not None or ttm_nwc is not None) else None
        self.nwc_surplus_deficit_label.setText(_fmt_currency(surplus_deficit))

    def _set_cell(self, label: str, data_idx: int, value: Optional[float], is_pct: bool = False):
        row_idx = self._row_idx.get(label)
        if row_idx is None:
            return
        lbl = self._calc_labels.get(row_idx, {}).get(data_idx)
        if lbl is None:
            return
        lbl.setText((_fmt_pct if is_pct else _fmt_currency)(value))

    def _set_cell_by_row(self, row_idx: int, data_idx: int, value: Optional[float]):
        lbl = self._calc_labels.get(row_idx, {}).get(data_idx)
        if lbl is not None:
            lbl.setText(_fmt_currency(value))

    def _retitle_row(self, row_idx: int, new_label: str):
        item = self.table_grid.itemAtPosition(row_idx, 0)
        if item is not None and item.widget() is not None:
            item.widget().setText(new_label)
        # Keep _row_idx lookups working under the OLD label used at
        # build time — both CA/CL summation labels are looked up by
        # their row_idx directly (ca_sum_row_idx/cl_sum_row_idx), not
        # by string, so retitling the visible text doesn't break
        # _set_cell_by_row.

    def _compute_fye_years(self, inputs) -> Dict[str, str]:
        """Mirrors DCF's FYE row: real calendar years under each
        historical/projected column, current LFY under TTM (same
        fiscal year, just a rolling-twelve-month view of it), and
        Residual = Final Projection Period year + 1."""
        result: Dict[str, str] = {}
        lfy_year = inputs.last_fiscal_year_year
        if lfy_year is not None:
            for i, label in enumerate(reversed(
                    [f"LFY-{j}" for j in range(self._nwc_historical_years - 1, 0, -1)] + ["LFY"])):
                offset = i
                result[label] = str(lfy_year - offset) if label != "LFY" else str(lfy_year)
            # fix: recompute cleanly forward instead of the reversed trick above
        hist_labels = [h for h in self._headers if h.startswith("LFY-")] + (["LFY"] if "LFY" in self._headers else [])
        if lfy_year is not None:
            n = len(hist_labels)
            for i, label in enumerate(hist_labels):
                result[label] = str(lfy_year - (n - 1 - i))
        if "TTM" in self._headers:
            result["TTM"] = str(lfy_year) if lfy_year is not None else ""

        nfy_year = inputs.next_fiscal_year_year
        if nfy_year is not None:
            proj_labels = [h for h in self._headers if h == "NFY" or h.startswith("NFY+")]
            for i, label in enumerate(proj_labels):
                result[label] = str(nfy_year + i)
            if proj_labels:
                result["Residual"] = str(nfy_year + len(proj_labels))

        return result