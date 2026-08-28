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
  checkboxes, and the LFY-4/LFY-3/LFY-2/LFY-1/LFY/TTM column grid are all real;
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
from Canneberge.Ui.theme import theme_manager
from Canneberge.Ui.font_scale import font_scale, NOTE_BASE_PX
from Canneberge.Ui.dcf_page import (
    INDENT_STYLE, MARGIN_ROW_STYLE, MARGIN_CELL_STYLE, COL_WIDTH,
    _fmt_currency, _fmt_pct, _safe_div, _sub_strict as _sub, _mul_strict as _mul,
    _parse_label_as_float, _read_label,
)
from Canneberge.Transforms.sa_key import get_sa_label
from Canneberge.utils.sa_utils import build_lookup, to_float
from Canneberge.Ui.subject_financials_page import _parse_val


def get_bold_style() -> str:
    return theme_manager.current.bold_style()


def get_note_style() -> str:
    # Matches dcf_page.py's period-header treatment exactly - these
    # two pages share the same column-header role (LFY-4/NFY+1/etc.)
    # and were found rendering it two different ways (this page used
    # to bold only the forward columns and leave historical ones
    # completely unstyled; DCF uniformly muted every column). This is
    # now the single shared answer for that role.
    t = theme_manager.current
    return f"font-size: {font_scale.px(NOTE_BASE_PX)}px; color: {t.note_text};"


def get_input_style() -> str:
    return theme_manager.current.input_style()


def get_header_style() -> str:
    # Delegates to the ONE canonical header treatment - same method
    # DCF/GPC/GT/WACC's section bars all use.
    return theme_manager.current.header_style()


def get_border_above_style() -> str:
    return f"border-top: 1px solid {theme_manager.current.border_color};"


def get_emphasis_border_style() -> str:
    t = theme_manager.current
    return t.emphasis_border_above_style(1) + " " + t.emphasis_border_below_style(3)


def get_excluded_row_style() -> str:
    return f"color: {theme_manager.current.disabled_text};"


def get_included_row_style() -> str:
    return f"color: {theme_manager.current.default_text};"

CA_CANDIDATES = [
    "cash", "st_investments", "trading_asset_securities",
    "cash_short_term_investments", "accounts_receivable", "other_receivables",
    "receivables", "finance_div_loans_and_leases", "inventory",
    "finance_div_other_current_assets", "prepaid_expenses",
    "loans_receivable_current", "restricted_cash", "other_current_assets",
]
CL_CANDIDATES = [
    "accounts_payable", "accrued_expenses", "st_debt", "current_ltd",
    "current_leases", "finance_div_debt_current",
    "finance_div_other_current_liabilities", "current_income_taxes_payable",
    "unearned_revenue", "other_current_liab",
]

CA_MAX_ROWS = len(CA_CANDIDATES)
CL_MAX_ROWS = len(CL_CANDIDATES)

CASH_KEYS = {"cash"}
DEBT_KEYS = {"st_debt", "current_ltd", "current_leases"}

_BS_LABEL_BY_KEY = {k: label for k, label, *_r in BS_LINES}

CA_DEFAULT_SELECTIONS = ["cash", "accounts_receivable", "inventory", "other_current_assets", "", "", ""]
CL_DEFAULT_SELECTIONS = ["accounts_payable", "other_current_liab", "", "", "", "", ""]
CA_DEFAULT_ROWS = 7
CL_DEFAULT_ROWS = 7

# GPC NWC formula inputs, expressed as IS/BS keys so the actual
# StockAnalysis label strings come from SA_KEY_MAP (single source of
# truth — same map Subject Financials uses). If a scraped label ever
# changes, both pages update together.
GPC_NWC_KEYS = {
    "tca":   "total_current_assets",   # Total Current Assets        (BS)
    "tcl":   "total_current_liab",     # Total Current Liabilities   (BS)
    "cpltd": "current_ltd",            # Current Portion of LT Debt  (BS)
    "std":   "st_debt",                # Short-Term Debt             (BS)
    "cpl":   "current_leases",         # Current Portion of Leases   (BS)
    "cash":  "cash",                   # Cash & Equivalents          (BS)
    "st_inv": "st_investments",        # Short-Term Investments      (BS)
    "cash_sti": "cash_short_term_investments",  # Cash & ST Inv.     (BS)
    "rev":   "revenue",                # Revenue                     (IS)
}

# Emphasis border for the GPC section's "Surplus/(Deficit)" total line
# now comes from theme.emphasis_border via get_emphasis_border_style()
# (see top of file) - not a local hardcoded hex anymore.


def _fmt_ca_cl_option(key: str) -> str:
    app_label = _BS_LABEL_BY_KEY.get(key)
    if app_label:
        return app_label

    sa_label = get_sa_label(key)
    if sa_label:
        return sa_label.title()

    return key.replace("_", " ").title()


class NWCPage(QWidget):
    def __init__(self,
                 get_project_inputs_callback,
                 get_subject_financials_callback,
                 get_dcf_residual_revenue_callback,
                 get_stockanalysis_results_callback,
                 update_projection_callback):
        super().__init__()
        self.get_project_inputs = get_project_inputs_callback
        self._get_subject_financials = get_subject_financials_callback
        self._get_dcf_residual_revenue = get_dcf_residual_revenue_callback
        self._get_stockanalysis_results = get_stockanalysis_results_callback
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
        self._ca_cl_buttons: List = []

        self.table_container = None
        self._built_hist_years = None
        self._built_proj_years = None
        self._table_insert_index = 0
        self._num_hist = 0
        self._num_proj = 0

        self._nwc_historical_years = 5
        self._gpc_row_widgets: List[dict] = []
        self._gpc_nwc_values: Dict[str, Dict[int, Optional[float]]] = {}

        # Preserve CA/CL combo selections across table rebuilds.
        self._saved_ca_selections: List[str] = []
        self._saved_cl_selections: List[str] = []
        self._ca_row_count = CA_DEFAULT_ROWS
        self._cl_row_count = CL_DEFAULT_ROWS

        # Prevent combo signals from causing _recalculate() while the
        # table is being destroyed/rebuilt.
        self._building_table = False
        self._saved_ca_selections: List[str] = []
        self._saved_cl_selections: List[str] = []

        # The lower GPC section is built from Home's GPC ticker list.
        # Keep a reference so it can be removed/rebuilt when Home's
        # ticker fields change.
        self.gpc_section = None
        self._gpc_section_insert_index = None
        self._built_gpc_tickers: List[str] = []

        # Raw Change in NWC values by period. DCF reads these through
        # get_changes_in_nwc(), rather than parsing displayed labels.
        self._changes_in_nwc_by_period: Dict[str, Optional[float]] = {}

        # Historical NWC ($), Revenue ($), and NWC % of revenue series
        # for the combo chart.
        self._chart_nwc_by_period: Dict[str, Optional[float]] = {}
        self._chart_revenue_by_period: Dict[str, Optional[float]] = {}
        self._chart_nwc_pct_by_period: Dict[str, Optional[float]] = {}
        # {ticker: {"nwc": {period: val}, "rev": {...}, "pct": {...}}}
        self._chart_gpc_series: Dict[str, Dict[str, Dict[str, Optional[float]]]] = {}

        # Set by MainWindow after both NWCPage and DCFPage exist.
        # Lets NWC refresh DCF whenever an NWC input changes.
        self._nwc_changed_callback = None

        self._build_ui()
        self._recalculate()

        theme_manager.theme_changed.connect(self._apply_theme)

    def _apply_theme(self, theme=None):
        for lbl in getattr(self, "_section_labels", []):
            lbl.setStyleSheet(get_header_style())
        for lbl in getattr(self, "_period_header_labels", {}).values():
            lbl.setStyleSheet(get_note_style())
        if hasattr(self, "_lbl_fye"):
            self._lbl_fye.setStyleSheet(get_bold_style())
        if hasattr(self, "lbl_client_header"):
            self.lbl_client_header.setStyleSheet(get_bold_style())
        if hasattr(self, "lbl_gpc_section_title"):
            self.lbl_gpc_section_title.setStyleSheet(get_header_style())
        if hasattr(self, "lbl_nwc_chart_title"):
            self.lbl_nwc_chart_title.setStyleSheet(get_header_style())
        for lbl in getattr(self, "_gpc_col_headers", []):
            lbl.setStyleSheet(get_bold_style())
        for lbl in getattr(self, "_gpc_stat_row_labels", []):
            lbl.setStyleSheet(get_bold_style())
        if hasattr(self, "lbl_selected_row"):
            self.lbl_selected_row.setStyleSheet(get_bold_style())
        if hasattr(self, "lbl_surplus"):
            self.lbl_surplus.setStyleSheet(
                f"{get_bold_style()} {get_emphasis_border_style()}"
            )
        if hasattr(self, "nwc_surplus_deficit_label"):
            self.nwc_surplus_deficit_label.setStyleSheet(
                f"{get_bold_style()} {get_emphasis_border_style()}"
            )

        self.cash_treatment_combo.setStyleSheet(get_input_style())
        self.nwc_basis_combo.setStyleSheet(get_input_style())
        self.selected_nwc_pct_input.setStyleSheet(get_input_style())
        self.hist_years_spin.setStyleSheet(get_input_style())
        self.proj_years_spin.setStyleSheet(get_input_style())
        if hasattr(self, "chart_entity_combo"):
            self.chart_entity_combo.setStyleSheet(get_input_style())
        for b in getattr(self, "_ca_cl_buttons", []):
            b.setStyleSheet(get_input_style())
        for combo in self._ca_combos:
            combo.setStyleSheet(get_input_style())
        for combo in self._cl_combos:
            combo.setStyleSheet(get_input_style())

        # Row labels + calc-cell colors: restyled directly from stored
        # (bold, margin, border_above) flags, NOT via _recalculate().
        # _recalculate() only rebuilds the grid when hist/proj years
        # actually changed (see _rebuild_table_if_needed's force=False
        # gate) - a plain call would silently no-op here and leave
        # every row/cell frozen at its build-time color, same trap
        # DCF's grid had to avoid.
        for row_idx, row_lbl in getattr(self, "_row_labels", {}).items():
            bold, margin, border_above = self._row_style_flags[row_idx]
            style = self._row_style(bold, margin, border_above)
            if style:
                row_lbl.setStyleSheet(style)
        for row_idx, cells in getattr(self, "_calc_labels", {}).items():
            bold, margin, border_above = self._row_style_flags.get(row_idx, (False, False, False))
            style = self._cell_style(bold, margin, border_above)
            if style:
                for cell in cells.values():
                    cell.setStyleSheet(style)

        # Everything else (GPC ticker grey/included coloring, FYE
        # values) IS safe to pick up via a plain recalc - those are
        # genuinely recomputed/re-styled every call, unlike the grid
        # rows above.
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

        # Remember exactly where the GPC section belongs so it can be
        # replaced in-place if the Home-page GPC ticker list changes.
        self._gpc_section_insert_index = self.page_layout.count()

        # GPC section (left, fixed width so its period columns stay
        # aligned with the subject table above) + combo chart (right,
        # absorbs remaining width).
        self._gpc_chart_row = QWidget()
        self._gpc_chart_hbox = QHBoxLayout(self._gpc_chart_row)
        self._gpc_chart_hbox.setContentsMargins(0, 0, 0, 0)
        self._gpc_chart_hbox.setSpacing(12)

        self.gpc_section = self._build_gpc_section()
        self._gpc_chart_hbox.addWidget(self.gpc_section, 0)

        self.nwc_chart_section = self._build_nwc_chart_section()
        self._gpc_chart_hbox.addWidget(self.nwc_chart_section, 1)

        self.page_layout.addWidget(self._gpc_chart_row)

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
        self.lbl_client_header = QLabel(inputs.client, styleSheet=get_bold_style())
        title_row.addWidget(self.lbl_client_header)
        self.lbl_subject_name = QLabel(inputs.subject_company_name)
        title_row.addWidget(self.lbl_subject_name)
        title_row.addWidget(QLabel("Net Working Capital Schedule"))
        title_row.addStretch(1)
        self.page_layout.addLayout(title_row)

        controls = QHBoxLayout()

        controls.addWidget(QLabel("Years of Historical:"))
        self.hist_years_spin = QSpinBox()
        self.hist_years_spin.setRange(1, 5)
        self.hist_years_spin.setValue(self._nwc_historical_years)
        self.hist_years_spin.setStyleSheet(get_input_style())
        self.hist_years_spin.valueChanged.connect(self._on_hist_years_changed)
        controls.addWidget(self.hist_years_spin)

        controls.addSpacing(24)
        controls.addWidget(QLabel("Years of Projections:"))
        self.proj_years_spin = QSpinBox()
        self.proj_years_spin.setRange(1, 15)
        self.proj_years_spin.setValue(inputs.projection_years)
        self.proj_years_spin.setStyleSheet(get_input_style())
        self.proj_years_spin.valueChanged.connect(self._on_proj_years_changed)
        controls.addWidget(self.proj_years_spin)

        controls.addSpacing(24)
        controls.addWidget(QLabel("NWC Cash Treatment:"))
        self.cash_treatment_combo = QComboBox()
        self.cash_treatment_combo.addItems(["Excluding Cash", "Including Cash"])
        self.cash_treatment_combo.setStyleSheet(get_input_style())
        self.cash_treatment_combo.currentTextChanged.connect(self._recalculate)
        controls.addWidget(self.cash_treatment_combo)

        controls.addSpacing(24)
        controls.addWidget(QLabel("NWC Basis:"))
        self.nwc_basis_combo = QComboBox()
        self.nwc_basis_combo.addItems(["% of Revenue", "Turnover Ratios"])
        self.nwc_basis_combo.setStyleSheet(get_input_style())
        self.nwc_basis_combo.currentTextChanged.connect(self._recalculate)
        controls.addWidget(self.nwc_basis_combo)

        controls.addStretch(1)
        self.page_layout.addLayout(controls)

    def _on_hist_years_changed(self, value: int):
        self._nwc_historical_years = value

        # Rebuild the main table for the new historical-period count.
        self._rebuild_table_if_needed(force=True)

        # GPC section uses the same historical columns as the main NWC
        # table, so rebuild that lower section too. This method ends
        # by recalculating the page.
        self.refresh_gpc_section(force=True)

        # GPC has the same historical columns, so rebuild it whenever
        # this page's historical-period count changes.
        self.refresh_gpc_section(force=True)

    def _on_proj_years_changed(self, value: int):
        inputs = self.get_project_inputs()
        self._update_projection_callback(inputs.historical_years, value)

    # ------------------------------------------------------------------
    # COLUMNS
    # ------------------------------------------------------------------

    def _generate_columns(self):
        inputs = self.get_project_inputs()

        hist_labels = []
        for i in range(self._nwc_historical_years - 1, 0, -1):
            hist_labels.append(f"LFY-{i}")
        hist_labels.append("LFY")
        hist_labels.append("TTM")

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
            return None
        return self._get_subject_financials(key, period)

    def _build_gpc_lookup(self, statement: str, ticker: str):
        results = self._get_stockanalysis_results() or {}
        rows = results.get(statement, [])
        return build_lookup(rows, ticker)

    def _gpc_nwc_parts(self, ticker: str, period: str, exclude_cash: bool):
        """
        Returns (nwc_dollars, revenue, nwc_pct) for one GPC/period.
        (None, None, None) if the required inputs aren't available.

        DFNWC   = TCA - [TCL - CPLTD - STD - CPL]
        DFCFNWC = (TCA - cash bucket) - [TCL - CPLTD - STD - CPL]
        """
        bs = self._build_gpc_lookup("BS", ticker)
        is_ = self._build_gpc_lookup("IS", ticker)

        def bs_val(field_key: str) -> Optional[float]:
            sa_label = get_sa_label(GPC_NWC_KEYS[field_key])
            return _parse_val(bs.get(sa_label, {}).get(period, ""))

        def is_val(field_key: str) -> Optional[float]:
            sa_label = get_sa_label(GPC_NWC_KEYS[field_key])
            return _parse_val(is_.get(sa_label, {}).get(period, ""))

        tca = bs_val("tca")
        tcl = bs_val("tcl")
        rev = is_val("rev")

        if tca is None or tcl is None or not rev:
            return None, None, None

        debt_free_cl = (
            tcl
            - (bs_val("cpltd") or 0.0)
            - (bs_val("std") or 0.0)
            - (bs_val("cpl") or 0.0)
        )

        if exclude_cash:
            # "Cash & Short-Term Investments" is a SUBTOTAL of the rows
            # above it. Prefer it when present; else sum the components.
            cash_sti = bs_val("cash_sti")
            if cash_sti is not None:
                cash_bucket = cash_sti
            else:
                cash_bucket = (bs_val("cash") or 0.0) + (bs_val("st_inv") or 0.0)
            nwc = (tca - cash_bucket) - debt_free_cl   # DFCFNWC
        else:
            nwc = tca - debt_free_cl                   # DFNWC

        return nwc, rev, nwc / rev

    def _gpc_nwc_pct(self, ticker: str, period: str, exclude_cash: bool) -> Optional[float]:
        return self._gpc_nwc_parts(ticker, period, exclude_cash)[2]
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

        # Do not allow nested rebuilds. This prevents weird duplicate
        # table layouts if a combo signal fires while widgets are being
        # rebuilt.
        if self._building_table:
            return

        self._building_table = True
        try:
            # Preserve CA/CL dropdown selections before table destruction.
            if self.table_container is not None:
                self._saved_ca_selections = [
                    c.currentData() or "" for c in self._ca_combos
                ]
                self._saved_cl_selections = [
                    c.currentData() or "" for c in self._cl_combos
                ]

                self.page_layout.removeWidget(self.table_container)
                self.table_container.setParent(None)
                self.table_container.deleteLater()

            # Generate the new column set before building the new table.
            self._generate_columns()

            # IMPORTANT: clear all widget references from the old table
            # before building the new one. Otherwise later recalc passes
            # can try to write to deleted QLabel/QComboBox objects.
            self._calc_labels = {}
            self._row_idx = {}
            self._row_labels = {}
            self._row_style_flags = {}
            self._fye_labels = {}
            self._ca_combos = []
            self._cl_combos = []
            self._ca_value_labels = []
            self._cl_value_labels = []

            self.table_container = self._build_table()
            self.page_layout.insertWidget(
                self._table_insert_index,
                self.table_container,
            )

            self._built_hist_years = new_hist
            self._built_proj_years = new_proj

        finally:
            self._building_table = False

    def _build_table(self) -> QWidget:
        self._fye_labels = {}

        container = QWidget()
        grid = QGridLayout()
        grid.setSpacing(4)
        self.table_grid = grid

        # Lock Column 0 width so lower section can match geometry exactly (85px + 265px = 350px)
        grid.setColumnMinimumWidth(0, 350)
        grid.setColumnStretch(0, 0)

        num_hist, num_proj = self._num_hist, self._num_proj

        hist_band = QLabel("Historical Financials", styleSheet=get_header_style(), alignment=Qt.AlignmentFlag.AlignCenter)
        grid.addWidget(hist_band, 0, 1, 1, num_hist)

        proj_band = QLabel("Projected Financials", styleSheet=get_header_style(), alignment=Qt.AlignmentFlag.AlignCenter)
        grid.addWidget(proj_band, 0, 1 + num_hist + 1, 1, num_proj)

        res_band = QLabel("", styleSheet=get_header_style())
        grid.addWidget(res_band, 0, 1 + num_hist + 1 + num_proj + 1)

        self._section_labels = [hist_band, proj_band, res_band]

        self._period_header_labels = {}
        for data_idx, label in enumerate(self._headers):
            grid_col = self._grid_col(data_idx)
            lbl = QLabel(label, alignment=Qt.AlignmentFlag.AlignRight)
            lbl.setStyleSheet(get_note_style())
            self._period_header_labels[data_idx] = lbl
            lbl.setFixedWidth(COL_WIDTH)
            grid.addWidget(lbl, 1, grid_col)

        self._lbl_fye = QLabel("FYE", styleSheet=get_bold_style())
        grid.addWidget(self._lbl_fye, 2, 0)
        for data_idx, label in enumerate(self._headers):
            grid_col = self._grid_col(data_idx)
            fye_lbl = QLabel("", alignment=Qt.AlignmentFlag.AlignRight)
            fye_lbl.setFixedWidth(COL_WIDTH)
            grid.addWidget(fye_lbl, 2, grid_col)
            self._fye_labels[label] = fye_lbl

        self._current_table_row = 3
        self._calc_labels = {}
        self._row_idx = {}
        self._row_labels = {}
        self._row_style_flags = {}
        self._ca_combos = []
        self._cl_combos = []
        self._ca_value_labels = []
        self._cl_value_labels = []
        self._ca_cl_buttons = []

        self._add_calc_row(grid, "Total Revenue", bold=True)
        self._current_table_row += 1

        for i in range(self._ca_row_count):
            self._add_ca_cl_row(grid, is_asset=True, slot=i)
        self._add_ca_cl_buttons(grid, is_asset=True)
        self.ca_sum_row_idx = self._add_calc_row(grid, "Total Current Assets", bold=True, border_above=True)
        self._current_table_row += 1

        for i in range(self._cl_row_count):
            self._add_ca_cl_row(grid, is_asset=False, slot=i)
        self._add_ca_cl_buttons(grid, is_asset=False)
        self.cl_sum_row_idx = self._add_calc_row(grid, "Total Current Liabilities", bold=True, border_above=True)
        self._current_table_row += 1

        self._add_calc_row(grid, "Net Working Capital", bold=True, border_above=True)
        self._add_calc_row(grid, "Net Working Capital % of Revenue", margin=True)
        self._current_table_row += 1
        self._add_calc_row(grid, "Changes in Net Working Capital", border_above=True)

        grid.setRowStretch(self._current_table_row + 1, 1)
        container.setLayout(grid)
        return container

    def _row_style(self, bold: bool, margin: bool, border_above: bool) -> str:
        """Single source of truth for a row's style string - used both
        at build time and by _apply_theme(), so they can't drift apart."""
        parts = []
        if bold:
            parts.append(get_bold_style())
        if margin:
            parts.append(MARGIN_ROW_STYLE)
        if border_above:
            parts.append(get_border_above_style())
        return " ".join(parts)

    def _cell_style(self, bold: bool, margin: bool, border_above: bool) -> str:
        parts = []
        if bold:
            parts.append(get_bold_style())
        if margin:
            parts.append(MARGIN_CELL_STYLE)
        if border_above:
            parts.append(get_border_above_style())
        return " ".join(parts)

    def _add_calc_row(self, grid: QGridLayout, label: str, bold: bool = False,
                       margin: bool = False, border_above: bool = False) -> int:
        row = self._current_table_row
        row_lbl = QLabel(label)
        row_lbl.setFixedWidth(350)
        style = self._row_style(bold, margin, border_above)
        if style:
            row_lbl.setStyleSheet(style)
        grid.addWidget(row_lbl, row, 0, alignment=Qt.AlignmentFlag.AlignLeft)

        cells: Dict[int, QLabel] = {}
        for data_idx in range(len(self._headers)):
            grid_col = self._grid_col(data_idx)
            lbl = QLabel("-", alignment=Qt.AlignmentFlag.AlignRight)
            lbl.setFixedWidth(COL_WIDTH)
            cell_style = self._cell_style(bold, margin, border_above)
            if cell_style:
                lbl.setStyleSheet(cell_style)
            grid.addWidget(lbl, row, grid_col)
            cells[data_idx] = lbl

        row_idx = row
        self._calc_labels[row_idx] = cells
        self._row_idx[label] = row_idx
        # Needed for _apply_theme() to restyle without a full rebuild
        # (a full rebuild is gated behind force=True and would wipe
        # any user-typed values - see _rebuild_table_if_needed).
        self._row_labels[row_idx] = row_lbl
        self._row_style_flags[row_idx] = (bold, margin, border_above)
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

        # Default selection from the original model setup.
        # Dynamically added rows begin as "-- None --".
        selected_key = defaults[slot] if slot < len(defaults) else ""

        # If this table is being rebuilt, prefer the user's prior
        # selection for this row/slot.
        if is_asset and slot < len(self._saved_ca_selections):
            selected_key = self._saved_ca_selections[slot]
        elif (not is_asset) and slot < len(self._saved_cl_selections):
            selected_key = self._saved_cl_selections[slot]

        idx = combo.findData(selected_key)

        # Set the selection BEFORE connecting currentIndexChanged.
        # This is the key fix: restoring combo state must not fire
        # _recalculate() while the table is still being built.
        combo.setCurrentIndex(idx if idx >= 0 else 0)

        combo.setStyleSheet(get_input_style())
        combo.setFixedWidth(340)  # fits inside 350px column without forcing growth
        combo.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
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

    def _add_ca_cl_buttons(self, grid: QGridLayout, is_asset: bool):
        from PyQt6.QtWidgets import QPushButton
        row = self._current_table_row
        holder = QHBoxLayout()
        holder.setContentsMargins(0, 0, 0, 0)
        holder.setSpacing(4)

        btn_add = QPushButton("+")
        btn_sub = QPushButton("−")
        for b in (btn_add, btn_sub):
            b.setFixedWidth(26)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet(get_input_style())
            self._ca_cl_buttons.append(b)

        btn_add.clicked.connect(lambda: self._change_row_count(is_asset, +1))
        btn_sub.clicked.connect(lambda: self._change_row_count(is_asset, -1))

        holder.addWidget(btn_add)
        holder.addWidget(btn_sub)
        holder.addStretch(1)

        wrap = QWidget()
        wrap.setLayout(holder)
        grid.addWidget(wrap, row, 0, alignment=Qt.AlignmentFlag.AlignLeft)
        self._current_table_row += 1

    def _change_row_count(self, is_asset: bool, delta: int):
        if is_asset:
            new_count = self._ca_row_count + delta
            if new_count < 1 or new_count > CA_MAX_ROWS:
                return
            self._ca_row_count = new_count
        else:
            new_count = self._cl_row_count + delta
            if new_count < 1 or new_count > CL_MAX_ROWS:
                return
            self._cl_row_count = new_count
        self._rebuild_table_if_needed(force=True)
        self._recalculate()

    # ------------------------------------------------------------------
    # GPC NWC SECTION
    # ------------------------------------------------------------------

    def _build_gpc_section(self) -> QWidget:
        frame = QFrame()
        frame.setFrameShape(QFrame.Shape.StyledPanel)
        outer = QVBoxLayout()
        outer.setContentsMargins(10, 10, 10, 10)
        outer.setSpacing(6)

        self.lbl_gpc_section_title = QLabel(
            "Net Working Capital % of Revenue", styleSheet=get_header_style()
        )
        outer.addWidget(self.lbl_gpc_section_title)

        grid = QGridLayout()
        grid.setSpacing(4)

        # Dynamic period columns matching top table's historical periods
        gpc_periods = [h for i, h in enumerate(self._headers) if self._is_historical[i]]
        if not gpc_periods:
            gpc_periods = ["LFY - 4", "LFY - 3", "LFY - 2", "LFY - 1", "LFY", "TTM"]

        # 1. Header Row
        self._gpc_col_headers = []
        lbl_exclude = QLabel("Exclude (X)", styleSheet=get_bold_style())
        lbl_gpc_name = QLabel("Guideline Public Company", styleSheet=get_bold_style())
        grid.addWidget(lbl_exclude, 0, 0, alignment=Qt.AlignmentFlag.AlignLeft)
        grid.addWidget(lbl_gpc_name, 0, 1, alignment=Qt.AlignmentFlag.AlignLeft)
        self._gpc_col_headers.extend([lbl_exclude, lbl_gpc_name])

        for i, period_str in enumerate(gpc_periods):
            lbl = QLabel(period_str, styleSheet=get_bold_style(), alignment=Qt.AlignmentFlag.AlignRight)
            lbl.setFixedWidth(COL_WIDTH)
            grid.addWidget(lbl, 0, 2 + i)
            self._gpc_col_headers.append(lbl)

        # Explicit geometry locking:
        # Col 0 (Exclude) + Col 1 (Ticker) = 85 + 265 = 350px (exact match to top table Col 0)
        grid.setColumnMinimumWidth(0, 85)
        grid.setColumnMinimumWidth(1, 265)

        for i in range(len(gpc_periods)):
            grid.setColumnMinimumWidth(2 + i, COL_WIDTH)

        # Spacer column absorbing extra right-hand screen width
        spacer_col = 2 + len(gpc_periods)
        grid.setColumnStretch(spacer_col, 1)

        inputs = self.get_project_inputs()
        tickers = inputs.gpc_tickers or []

        # Save the exact list used to build this widget. During future
        # recalculations, we compare this with Home's current list.
        self._built_gpc_tickers = list(tickers)

        # 2. Ticker Rows
        self._gpc_row_widgets = []
        r = 1
        for ticker in tickers:
            chk = QCheckBox()
            chk.stateChanged.connect(self._recalculate)
            grid.addWidget(chk, r, 0, alignment=Qt.AlignmentFlag.AlignCenter)

            ticker_lbl = QLabel(ticker)
            grid.addWidget(ticker_lbl, r, 1, alignment=Qt.AlignmentFlag.AlignLeft)

            value_labels = []
            for i in range(len(gpc_periods)):
                lbl = QLabel("-", alignment=Qt.AlignmentFlag.AlignRight)
                lbl.setFixedWidth(COL_WIDTH)
                grid.addWidget(lbl, r, 2 + i)
                value_labels.append(lbl)

            self._gpc_row_widgets.append({
                "ticker": ticker,
                "ticker_label": ticker_lbl,
                "exclude": chk,
                "values": value_labels,
            })
            r += 1

        # Spacer row between tickers and statistics
        grid.setRowMinimumHeight(r, 14)
        r += 1

        # 3. Statistics Rows
        self._gpc_stat_labels = {}
        self._gpc_stat_row_labels = []
        for stat_label in ("Maximum", "Third Quartile", "Average", "Median", "First Quartile", "Minimum"):
            stat_lbl = QLabel(stat_label, styleSheet=get_bold_style())
            grid.addWidget(stat_lbl, r, 1, alignment=Qt.AlignmentFlag.AlignLeft)
            self._gpc_stat_row_labels.append(stat_lbl)
            row_labels = []
            for i in range(len(gpc_periods)):
                lbl = QLabel("-", alignment=Qt.AlignmentFlag.AlignRight)
                lbl.setFixedWidth(COL_WIDTH)
                grid.addWidget(lbl, r, 2 + i)
                row_labels.append(lbl)
            self._gpc_stat_labels[stat_label] = row_labels
            r += 1

        # Index of TTM column inside grid (last period column)
        ttm_col_idx = 2 + len(gpc_periods) - 1

        # Spacer row between Stats and selected row
        grid.setRowMinimumHeight(r, 14)
        r += 1

        # 4. "Selected" Row — locked inside grid under TTM
        r += 1
        self.lbl_selected_row = QLabel("Selected", styleSheet=get_bold_style())
        grid.addWidget(self.lbl_selected_row, r, 0, 1, 2, alignment=Qt.AlignmentFlag.AlignLeft)

        self.selected_nwc_pct_input = QLineEdit("15.0%")
        self.selected_nwc_pct_input.setStyleSheet(get_input_style())
        self.selected_nwc_pct_input.setFixedWidth(COL_WIDTH)
        self.selected_nwc_pct_input.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.selected_nwc_pct_input.editingFinished.connect(self._recalculate)
        grid.addWidget(self.selected_nwc_pct_input, r, ttm_col_idx)

        # 5. Bridge Rows — locked inside grid under TTM
        r += 1
        grid.addWidget(QLabel("Normalized Net Working Capital"), r, 0, 1, 2, alignment=Qt.AlignmentFlag.AlignLeft)
        self.normalized_nwc_label = QLabel("-", alignment=Qt.AlignmentFlag.AlignRight)
        self.normalized_nwc_label.setFixedWidth(COL_WIDTH)
        grid.addWidget(self.normalized_nwc_label, r, ttm_col_idx)

        r += 1
        grid.addWidget(QLabel("Actual Net Working Capital"), r, 0, 1, 2, alignment=Qt.AlignmentFlag.AlignLeft)
        self.actual_nwc_label = QLabel("-", alignment=Qt.AlignmentFlag.AlignRight)
        self.actual_nwc_label.setFixedWidth(COL_WIDTH)
        grid.addWidget(self.actual_nwc_label, r, ttm_col_idx)

        r += 1
        self.lbl_surplus = QLabel("Net Working Capital Surplus/(Deficit)")
        self.lbl_surplus.setStyleSheet(f"{get_bold_style()} {get_emphasis_border_style()}")
        grid.addWidget(self.lbl_surplus, r, 0, 1, 2, alignment=Qt.AlignmentFlag.AlignLeft)

        self.nwc_surplus_deficit_label = QLabel("-", alignment=Qt.AlignmentFlag.AlignRight)
        self.nwc_surplus_deficit_label.setFixedWidth(COL_WIDTH)
        self.nwc_surplus_deficit_label.setStyleSheet(
            f"{get_bold_style()} {get_emphasis_border_style()}"
        )
        grid.addWidget(self.nwc_surplus_deficit_label, r, ttm_col_idx)

        outer.addLayout(grid)
        frame.setLayout(outer)
        return frame

    def refresh_gpc_section(self, force: bool = False):
        """
        Rebuild the lower GPC NWC section from Home's current GPC
        ticker list.

        This is needed because the original widget was built only
        once at startup. Merely running _recalculate() updates values
        inside existing rows; it cannot add/remove/change ticker rows.

        Existing exclusion selections and the Selected NWC % input are
        retained for tickers that remain in the list.
        """
        current_tickers = list(self.get_project_inputs().gpc_tickers or [])

        # If Home's ticker list did not actually change, there is no
        # need to rebuild the widget. Still recalculate the displayed
        # percentages in case Source Data changed.
        if not force and current_tickers == self._built_gpc_tickers:
            self._recalculate()
            return

        # Preserve the user-entered selected percentage.
        selected_pct_text = "15.0%"
        if hasattr(self, "selected_nwc_pct_input"):
            selected_pct_text = self.selected_nwc_pct_input.text()

        # Preserve exclusions for tickers that still exist after the
        # Home-page ticker list changes.
        excluded_tickers = {
            row_meta["ticker"]
            for row_meta in self._gpc_row_widgets
            if row_meta["exclude"].isChecked()
        }

        # Remove the old GPC section widget from the side-by-side row.
        if self.gpc_section is not None:
            self._gpc_chart_hbox.removeWidget(self.gpc_section)
            self.gpc_section.setParent(None)
            self.gpc_section.deleteLater()

        # Rebuild and re-insert on the LEFT of the chart (index 0,
        # stretch 0 so it keeps its fixed, column-aligned width).
        self.gpc_section = self._build_gpc_section()
        self._gpc_chart_hbox.insertWidget(0, self.gpc_section, 0)

        # Restore the Selected NWC % input.
        self.selected_nwc_pct_input.setText(selected_pct_text)

        # Restore exclusions for tickers that survived the rebuild.
        # Signals are blocked so restoring a checkbox does not cause
        # repeated recalculation during the rebuild.
        for row_meta in self._gpc_row_widgets:
            checkbox = row_meta["exclude"]
            previous_block_state = checkbox.blockSignals(True)
            checkbox.setChecked(row_meta["ticker"] in excluded_tickers)
            checkbox.blockSignals(previous_block_state)

        # Populate the rebuilt ticker rows and statistics.
        self._recalculate()

    # ------------------------------------------------------------------
    # NWC COMBO CHART
    # ------------------------------------------------------------------

    def _build_nwc_chart_section(self) -> QWidget:
        from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
        from matplotlib.figure import Figure

        frame = QFrame()
        frame.setFrameShape(QFrame.Shape.StyledPanel)
        layout = QVBoxLayout()
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)

        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setSpacing(6)

        self.lbl_nwc_chart_title = QLabel(
            "Net Working Capital vs. % of Revenue",
            styleSheet=get_header_style(),
        )
        header_row.addWidget(self.lbl_nwc_chart_title, 1)

        self.chart_entity_combo = QComboBox()
        self.chart_entity_combo.setStyleSheet(get_input_style())
        self.chart_entity_combo.setMinimumWidth(110)
        self.chart_entity_combo.addItem("Subject")
        self.chart_entity_combo.currentTextChanged.connect(
            lambda _: self._update_nwc_combo_chart()
        )
        header_row.addWidget(self.chart_entity_combo, 0)

        layout.addLayout(header_row)

        self._nwc_figure = Figure(figsize=(6, 4))
        self._nwc_canvas = FigureCanvasQTAgg(self._nwc_figure)
        self._nwc_canvas.setMinimumHeight(320)
        self._nwc_canvas.setMinimumWidth(360)
        self._nwc_canvas.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self._nwc_ax_bar = self._nwc_figure.add_subplot(111)
        self._nwc_ax_line = self._nwc_ax_bar.twinx()
        layout.addWidget(self._nwc_canvas)

        frame.setLayout(layout)
        return frame

    def _refresh_chart_entity_combo(self):
        """Keep the chart's entity dropdown in sync with Home's GPC list.
        Excluded tickers stay in the list — exclusion is a peer-stats
        concept, not a reason to hide a company's own chart."""
        if not hasattr(self, "chart_entity_combo"):
            return

        tickers = [r["ticker"] for r in self._gpc_row_widgets]
        wanted = ["Subject"] + tickers
        existing = [
            self.chart_entity_combo.itemText(i)
            for i in range(self.chart_entity_combo.count())
        ]
        if existing == wanted:
            return

        prior = self.chart_entity_combo.currentText()
        blocked = self.chart_entity_combo.blockSignals(True)
        self.chart_entity_combo.clear()
        self.chart_entity_combo.addItems(wanted)
        idx = self.chart_entity_combo.findText(prior)
        self.chart_entity_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.chart_entity_combo.blockSignals(blocked)

    def _update_nwc_combo_chart(self):
        if not hasattr(self, "_nwc_ax_bar"):
            return
        from matplotlib.ticker import FuncFormatter

        t = theme_manager.current

        # Historical columns only (LFY-N ... LFY, TTM).
        periods = [
            h for idx, h in enumerate(self._headers)
            if self._is_historical[idx]
        ]
        entity = "Subject"
        if hasattr(self, "chart_entity_combo"):
            entity = self.chart_entity_combo.currentText() or "Subject"

        if entity == "Subject":
            nwc_src = self._chart_nwc_by_period
            rev_src = self._chart_revenue_by_period
            pct_src = self._chart_nwc_pct_by_period
        else:
            series = self._chart_gpc_series.get(entity, {})
            nwc_src = series.get("nwc", {})
            rev_src = series.get("rev", {})
            pct_src = series.get("pct", {})

        nwc_vals = [nwc_src.get(p) for p in periods]
        rev_vals = [rev_src.get(p) for p in periods]
        pct_vals = [pct_src.get(p) for p in periods]

        x = list(range(len(periods)))

        self._nwc_ax_bar.clear()
        self._nwc_ax_line.clear()

        self._nwc_figure.patch.set_facecolor(t.window_bg)
        self._nwc_ax_bar.set_facecolor(t.window_bg)

        # Bars: NWC ($)
        bar_vals = [v if v is not None else 0 for v in nwc_vals]
        self._nwc_ax_bar.bar(
            x, bar_vals, color=t.chart_fill,
            edgecolor=t.chart_edge, width=0.5, zorder=2,
        )
        self._nwc_ax_bar.set_xticks(x)
        self._nwc_ax_bar.set_xticklabels(
            periods, color=t.chart_axis_label, fontsize=9
        )
        self._nwc_ax_bar.set_ylabel(
            "Net Working Capital  &  Revenue ($)",
            color=t.default_text, fontsize=9
        )
        self._nwc_ax_bar.tick_params(axis="x", colors=t.chart_axis_label)
        self._nwc_ax_bar.tick_params(axis="y", colors=t.chart_axis_label)
        self._nwc_ax_bar.grid(
            True, axis="y", alpha=0.25, color=t.chart_grid, zorder=0
        )
        self._nwc_ax_bar.axhline(0, color=t.chart_grid, linewidth=0.8, zorder=1)
        for spine in self._nwc_ax_bar.spines.values():
            spine.set_color(t.chart_grid)
        self._nwc_ax_bar.yaxis.set_major_formatter(
            FuncFormatter(lambda val, _: f"{val:,.0f}")
        )

        # Revenue line on the SAME dollar axis as the NWC bars — both
        # are dollars, so this is an honest magnitude comparison (shows
        # revenue climbing while NWC stays negative / non-scaling).
        rev_x = [xi for xi, v in zip(x, rev_vals) if v is not None]
        rev_y = [v for v in rev_vals if v is not None]
        if rev_x:
            self._nwc_ax_bar.plot(
                rev_x, rev_y, color=t.chart_share_price,
                linewidth=2, marker="s", markersize=5, zorder=3,
                label="Revenue",
            )
            self._nwc_ax_bar.legend(
                fontsize=7, loc="upper left",
                facecolor=t.window_bg, edgecolor=t.chart_grid,
                labelcolor=t.default_text,
            )

        # Line: NWC % of revenue (secondary axis)
        pct_plot = [v * 100 if v is not None else None for v in pct_vals]
        plot_x = [xi for xi, v in zip(x, pct_plot) if v is not None]
        plot_y = [v for v in pct_plot if v is not None]
        if plot_x:
            self._nwc_ax_line.plot(
                plot_x, plot_y, color=t.chart_conclude,
                linewidth=2, marker="o", markersize=5, zorder=3,
            )
        self._nwc_ax_line.set_ylabel(
            "NWC % of Revenue", color=t.default_text, fontsize=9
        )
        self._nwc_ax_line.yaxis.set_label_position("right")
        self._nwc_ax_line.tick_params(axis="y", colors=t.chart_axis_label)
        self._nwc_ax_line.yaxis.set_major_formatter(
            FuncFormatter(lambda val, _: f"{val:.1f}%")
        )
        for spine in self._nwc_ax_line.spines.values():
            spine.set_color(t.chart_grid)

        self._nwc_ax_bar.set_title(
            f"{entity} — Net Working Capital vs. % of Revenue",
            color=t.default_text, fontsize=10,
        )

        self._nwc_figure.tight_layout()
        self._nwc_canvas.draw()

    # ------------------------------------------------------------------
    # RECALCULATE
    # ------------------------------------------------------------------

    def _recalculate(self):
        if self._building_table:
            return

        self._rebuild_table_if_needed()
        inputs = self.get_project_inputs()

        # These were being set once at construction and never
        # touched again - if Client or Subject Company Name
        # changed on the Home page after this tab was first built,
        # this title would silently show stale text forever (found
        # via a screenshot showing "COMPANY NAME" instead of the
        # real subject name).
        self.lbl_client_header.setText(inputs.client)
        self.lbl_subject_name.setText(inputs.subject_company_name)

        # Projection Years is shared with Home / DCF. Keep NWC's
        # visible Projection Years spinbox synced to that shared value.
        if self.proj_years_spin.value() != inputs.projection_years:
            blocked = self.proj_years_spin.blockSignals(True)
            self.proj_years_spin.setValue(inputs.projection_years)
            self.proj_years_spin.blockSignals(blocked)

        self._rebuild_table_if_needed()
        inputs = self.get_project_inputs()

        # Home's GPC ticker fields may have changed since the lower
        # GPC section was originally built. Rebuild the section before
        # calculating if its row structure is now stale.
        if list(inputs.gpc_tickers or []) != self._built_gpc_tickers:
            self.refresh_gpc_section(force=True)
            return

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
                if val is not None:
                    ca_sum_by_period[period] = (
                        ca_sum_by_period[period] or 0.0
                    ) + val

        for slot, combo in enumerate(self._cl_combos):
            key = combo.currentData()
            for data_idx, period in enumerate(self._headers):
                val = self._sf_get(key, period) if key else None
                lbl = self._cl_value_labels[slot][data_idx]
                lbl.setText(_fmt_currency(val) if val is not None else "-")
                if val is not None:
                    cl_sum_by_period[period] = (
                        cl_sum_by_period[period] or 0.0
                    ) + val

        ca_sum_label = "Total Current Assets"
        cl_sum_label = "Total Current Liabilities"
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
                if pct_basis:
                    nwc = _mul(rev, selected_pct)
                else:
                    nwc = _sub(ca, cl) if (ca is not None or cl is not None) else None

            nwc_by_period[period] = nwc
            self._set_cell("Net Working Capital", data_idx, nwc)
            self._set_cell("Net Working Capital % of Revenue", data_idx, _safe_div(nwc, rev), is_pct=True)

        # --- Changes in Net Working Capital ---
        # Stored as raw floats so DCF can consume the exact values,
        # rather than reading/parsing the formatted NWC labels.
        self._changes_in_nwc_by_period = {}

        for data_idx, period in enumerate(self._headers):
            prior_period = self._headers[data_idx - 1] if data_idx > 0 else None
            this_nwc = nwc_by_period[period]
            prior_nwc = nwc_by_period.get(prior_period) if prior_period else None

            change = (
                _sub(this_nwc, prior_nwc)
                if prior_period and this_nwc is not None and prior_nwc is not None
                else None
            )

            self._changes_in_nwc_by_period[period] = change
            self._set_cell("Changes in Net Working Capital", data_idx, change)

                        # --- GPC per-ticker NWC % values ---
        gpc_periods = [h for idx, h in enumerate(self._headers)
                       if self._is_historical[idx]]

        exclude_cash = not include_cash

        self._gpc_nwc_values = {}
        for row_meta in self._gpc_row_widgets:
            ticker = row_meta["ticker"]
            excluded = row_meta["exclude"].isChecked()

            row_style = get_excluded_row_style() if excluded else get_included_row_style()
            ticker_lbl = row_meta.get("ticker_label")
            if ticker_lbl is not None:
                ticker_lbl.setStyleSheet(row_style)

            self._gpc_nwc_values[ticker] = {}
            self._chart_gpc_series[ticker] = {"nwc": {}, "rev": {}, "pct": {}}
            for c, period in enumerate(gpc_periods):
                if c >= len(row_meta["values"]):
                    break

                nwc_d, rev_d, pct = self._gpc_nwc_parts(
                    ticker, period, exclude_cash
                )
                self._gpc_nwc_values[ticker][c] = None if excluded else pct

                # Chart series keep their values even when the ticker is
                # excluded — exclusion only affects the peer stat rows.
                self._chart_gpc_series[ticker]["nwc"][period] = nwc_d
                self._chart_gpc_series[ticker]["rev"][period] = rev_d
                self._chart_gpc_series[ticker]["pct"][period] = pct

                lbl = row_meta["values"][c]
                lbl.setText(_fmt_pct(pct) if pct is not None else "-")
                lbl.setStyleSheet(row_style)

        # --- GPC NWC % statistics ---
        if hasattr(self, "_gpc_stat_labels") and "Maximum" in self._gpc_stat_labels:
            num_gpc_cols = len(self._gpc_stat_labels["Maximum"])
            stat_funcs = {
                "Maximum":        lambda v: max(v),
                "Third Quartile": lambda v: _quartile(v, 0.75),
                "Average":        lambda v: sum(v) / len(v),
                "Median":         lambda v: statistics.median(v),
                "First Quartile": lambda v: _quartile(v, 0.25),
                "Minimum":        lambda v: min(v),
            }
            for c in range(num_gpc_cols):
                vals = []
                for row_meta in self._gpc_row_widgets:
                    if row_meta["exclude"].isChecked():
                        continue
                    v = self._gpc_nwc_values.get(row_meta["ticker"], {}).get(c)
                    if v is not None:
                        vals.append(v)
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
        surplus_deficit = _sub(ttm_nwc, normalized_nwc) if (normalized_nwc is not None or ttm_nwc is not None) else None
        self.nwc_surplus_deficit_label.setText(_fmt_currency(surplus_deficit))

        # Store historical NWC ($) and NWC % of revenue for the combo
        # chart, then redraw it.
        self._chart_nwc_by_period = {}
        self._chart_nwc_pct_by_period = {}
        self._chart_revenue_by_period = {}
        for period in self._headers:
            nwc = nwc_by_period.get(period)
            rev = revenue_by_period.get(period)
            self._chart_nwc_by_period[period] = nwc
            self._chart_revenue_by_period[period] = rev
            self._chart_nwc_pct_by_period[period] = _safe_div(nwc, rev)
        self._refresh_chart_entity_combo()
        self._update_nwc_combo_chart()

        # The NWC page is the source of truth for Change in NWC.
        # Refresh DCF after NWC has finished calculating.
        if self._nwc_changed_callback is not None:
            self._nwc_changed_callback()

    def get_changes_in_nwc(self, period: str) -> Optional[float]:
        """
        Public accessor used by DCFPage.

        Returns the raw Change in Net Working Capital for a matching
        period label: LFY-4, LFY-3, LFY-2, LFY-1, LFY, NFY, NFY+1,
        etc. DCF does not have a TTM column, but NWC does; DCF simply
        requests the labels it actually displays.
        """
        return self._changes_in_nwc_by_period.get(period)

    def set_nwc_changed_callback(self, callback):
        """
        MainWindow gives NWC this callback after both pages exist.
        It refreshes the DCF page whenever NWC inputs change.
        """
        self._nwc_changed_callback = callback

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

    def _compute_fye_years(self, inputs) -> Dict[str, str]:
        result: Dict[str, str] = {}
        lfy_year = inputs.last_fiscal_year_year
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

    def collect_state(self) -> dict:
        return {
            "ca_selections": [c.currentData() for c in self._ca_combos],
            "cl_selections": [c.currentData() for c in self._cl_combos],
            "cash_treatment": self.cash_treatment_combo.currentText(),
            "nwc_basis": self.nwc_basis_combo.currentText(),
            "selected_pct": self.selected_nwc_pct_input.text(),
            "historical_years": self._nwc_historical_years,
            "ca_row_count": self._ca_row_count,
            "cl_row_count": self._cl_row_count,
            "gpc_exclusions": [
                r["exclude"].isChecked() for r in self._gpc_row_widgets
            ],
        }

    def apply_state(self, state: dict):
        if not state:
            return

        hist = state.get("historical_years")
        if hist is not None and hist != self._nwc_historical_years:
            self.hist_years_spin.setValue(hist)
            self._nwc_historical_years = hist

        ca_rows = state.get("ca_row_count")
        cl_rows = state.get("cl_row_count")
        if ca_rows is not None and 1 <= ca_rows <= CA_MAX_ROWS:
            self._ca_row_count = ca_rows
        if cl_rows is not None and 1 <= cl_rows <= CL_MAX_ROWS:
            self._cl_row_count = cl_rows

        self._rebuild_table_if_needed(force=True)

        for combo, key in zip(self._ca_combos, state.get("ca_selections", [])):
            idx = combo.findData(key)
            combo.setCurrentIndex(idx if idx >= 0 else 0)
        for combo, key in zip(self._cl_combos, state.get("cl_selections", [])):
            idx = combo.findData(key)
            combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.cash_treatment_combo.setCurrentText(
            state.get("cash_treatment", "Excluding Cash")
        )
        self.nwc_basis_combo.setCurrentText(
            state.get("nwc_basis", "% of Revenue")
        )
        self.selected_nwc_pct_input.setText(
            state.get("selected_pct", "15.0%")
        )
        for row, checked in zip(self._gpc_row_widgets, state.get("gpc_exclusions", [])):
            row["exclude"].setChecked(checked)
        self._recalculate()