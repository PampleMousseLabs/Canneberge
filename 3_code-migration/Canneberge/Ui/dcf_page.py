import math
import re
from datetime import datetime
from typing import Optional, Dict

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QLineEdit,
    QScrollArea, QFrame, QCheckBox, QPushButton, QComboBox, QSpinBox,
    QDialog, QFormLayout, QDialogButtonBox, QSizePolicy
)
from PyQt6.QtCore import Qt

from Canneberge.Ui.theme import theme_manager
from Canneberge.Ui.font_scale import font_scale, NOTE_BASE_PX

# =====================================================================
# STYLE CONFIG — this is the block to edit for any purely visual
# change (fonts, sizes, borders, spacers, widths, which rows are
# bold). Nothing below this block should need touching to change how
# the page LOOKS — if a visual change requires editing code outside
# this block, that's a gap in this config, not something to hand-edit
# elsewhere.
#
# Colors are NO LONGER hardcoded here. They come from the active
# Theme (Canneberge/Ui/theme.py) via theme_manager.current. The
# get_*_style() functions below read theme_manager.current live, so
# calling them after a theme switch always returns the new colors.
# Only structural values (widths, font sizes, which rows get which
# treatment) stay as local constants — those aren't theme concerns.
# =====================================================================

HEADER_FONT_SIZE = 11  # px
INDENT_STYLE = "padding-left: 20px;"
MARGIN_ROW_STYLE = "padding-left: 20px; font-style: italic;"
MARGIN_CELL_STYLE = "font-style: italic;"
COL_WIDTH = 95  # px, width of each LFY-4/NFY/etc. data column

# --- Borders ---
# Change thickness here; color comes from the active theme.
BORDER_ABOVE_WIDTH = 1   # px, thin underline-above rule (subtotal rows)
BORDER_BELOW_WIDTH = 2   # px, thick underline-below rule (grand total rows)


def get_input_style() -> str:
    return theme_manager.current.input_style()


def get_bold_style() -> str:
    return theme_manager.current.bold_style()


def get_header_style() -> str:
    # Delegates to the ONE canonical header treatment (theme.py's
    # Theme.header_style()) instead of building a DCF-local version -
    # this IS what every other page's section headers now use too.
    return theme_manager.current.header_style()


def get_border_above_style() -> str:
    t = theme_manager.current
    return f"border-top: {BORDER_ABOVE_WIDTH}px solid {t.border_color};"


def get_border_below_style() -> str:
    t = theme_manager.current
    return f"border-bottom: {BORDER_BELOW_WIDTH}px solid {t.border_color};"


def get_link_style() -> str:
    return theme_manager.current.link_style()


def get_note_style() -> str:
    t = theme_manager.current
    return f"font-size: {font_scale.px(NOTE_BASE_PX)}px; color: {t.note_text};"

# Rows that get a thin border ABOVE them, across every historical +
# projected + Residual data cell (not just the label). "EBIT" covers
# its FCFE relabel to "EBT" too, since the border is keyed off
# whatever the row's grid position is, not its current text.
ROWS_WITH_BORDER_ABOVE = {
    "Gross Profit", "EBITDA", "EBIT",
    "Net Operating Profit After Tax (NOPAT)", "Free Cash Flow",
    "Present Value of Free Cash Flows",
}

# Rows that get a blank spacer row directly above them.
ROWS_WITH_SPACER_ABOVE = {
    "Operating Expenses", "Net Operating Profit After Tax (NOPAT)",
    "Partial Period Adjustment",
}

# Rows forced bold regardless of the is_bold flag already in
# _build_table_rows's row tuple (e.g. Revenue is defined as a
# non-bold row there but Ted wants it bold on this page specifically).
FORCE_BOLD_ROWS = {"Revenue"}

# --- Fixed widths for specific controls ---
MODEL_DROPDOWN_WIDTH = 170        # fits "Gordon Growth" (13 chars) + arrow with room
BRIDGE_LABEL_COL_WIDTH = 260      # fits "Fair Value of Business Enterprise (Base):" unwrapped
FOOTER_BOX_LABEL_COL_WIDTH = 210  # Terminal Value / CapEx Options label column width
FOOTER_BOX_LEFT_PAD = 340         # blank space pushing those boxes' labels toward the right edge

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
    lbl.setStyleSheet(get_header_style())
    lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    return lbl


def _safe_div(a: Optional[float], b: Optional[float]) -> Optional[float]:
    """None-safe division. Returns None if either input is None or
    divisor is zero — never raises, never returns NaN/Inf."""
    if a is None or b is None or b == 0:
        return None
    return a / b


def _sub_strict(a: Optional[float], b: Optional[float]) -> Optional[float]:
    """a - b, but None (not a partial number) if either side is
    missing — used for Residual's Gross Profit/EBITDA, which are
    real differences of two grown figures, not sums-with-0-fallback."""
    if a is None or b is None:
        return None
    return a - b


def _mul_strict(a: Optional[float], b: Optional[float]) -> Optional[float]:
    if a is None or b is None:
        return None
    return a * b


def _parse_multiple(line_edit) -> Optional[float]:
    """Parse a '10.00x' style multiple input. None if unset/unparseable."""
    if line_edit is None:
        return None
    text = line_edit.text().strip().lower().replace("x", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


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
        self.hist_years_spin.setStyleSheet(get_input_style())
        form.addRow("Years of Historicals:", self.hist_years_spin)

        self.proj_years_spin = QSpinBox()
        self.proj_years_spin.setMinimum(1)
        self.proj_years_spin.setMaximum(20)
        self.proj_years_spin.setValue(project_inputs.projection_years)
        self.proj_years_spin.setStyleSheet(get_input_style())
        form.addRow("Years of Projections:", self.proj_years_spin)

        self.cash_flows_combo = QComboBox()
        self.cash_flows_combo.addItems(["FCFF", "FCFE"])
        self.cash_flows_combo.setStyleSheet(get_input_style())
        form.addRow("Cash Flows to:", self.cash_flows_combo)

        self.nol_combo = QComboBox()
        self.nol_combo.addItems(["No", "Yes"])
        self.nol_combo.setStyleSheet(get_input_style())
        form.addRow("NOLs?:", self.nol_combo)

        self.nwc_combo = QComboBox()
        self.nwc_combo.addItems(["No", "Yes"])
        self.nwc_combo.setStyleSheet(get_input_style())
        form.addRow("Change in NWC provided by Mgmt:", self.nwc_combo)

        self.val_approach_combo = QComboBox()
        self.val_approach_combo.addItems(["DCF", "LBO"])
        self.val_approach_combo.setStyleSheet(get_input_style())
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
                 update_projection_callback, 
                 get_nwc_change_callback=None):
        super().__init__()
        self.get_project_inputs = get_project_inputs_callback
        self.get_wacc_value = get_wacc_value_callback
        self._get_subject_financials = get_subject_financials_callback
        self._get_projection_data = get_projection_data_callback
        self._update_projection_callback = update_projection_callback
        # MainWindow supplies this callback. It returns the raw
        # Change in NWC for a given period from NWCPage.
        #
        # During DCFPage's first construction, NWCPage does not exist
        # yet, so MainWindow safely returns None until it is created.
        self._get_nwc_change = get_nwc_change_callback or (lambda _period: None)

        self._calc_labels = {}
        self._input_fields = {}
        self._headers = []
        self._is_historical = []
        self._fye_labels = {}
        self.pv_factor_row_label = None
        # Theme live-refresh needs these to restyle in place without
        # rebuilding (rebuilding would destroy any user-typed values
        # in self._input_fields). Populated alongside their sibling
        # dicts in _build_table_headers / _build_table_rows.
        self._row_labels = {}          # {row_idx: QLabel}
        self._period_header_labels = {}  # {data_idx: QLabel} (row 1, "LFY-4" etc.)
        self._section_labels = []      # ["Historical Financials", "Projected Financials"] bars

        # Row indices into self._rows, captured during _build_table_rows.
        # _recalculate() looks up cells via these so we don't string-match
        # on row labels at runtime.
        self._row_idx = {}

        # Grid row positions for the two rows that need dynamic behavior
        # (label rewrite / visibility) outside of cell text updates.
        self._ebit_grid_row = None
        self._ebit_margin_grid_row = None
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

        # Live theme switching. Does NOT rebuild the grid (that would
        # destroy any values the user has typed into _input_fields) —
        # it walks the existing widget references and reapplies each
        # one's stylesheet using the same _row_label_style /
        # _calc_cell_style logic used at build time.
        theme_manager.theme_changed.connect(self._apply_theme)

    # ------------------------------------------------------------------
    # THEME
    # ------------------------------------------------------------------

    def _apply_theme(self, theme=None):
        """
        Called whenever the user switches themes (View > Theme). Walks
        every persistent styled widget on this page and reapplies its
        stylesheet from the new active theme.

        Deliberately does NOT rebuild the table grid — rebuilding would
        destroy the QLineEdit widgets in self._input_fields, which can
        hold values the user has manually typed in (Other Adjustments /
        Amortization Residual overrides). Restyling in place preserves
        those values exactly as-is.

        `theme` param is accepted because Qt's signal passes it, but
        every getter below reads theme_manager.current directly, so
        it's not actually used — this always reflects the live theme.
        """
        # --- Header info row ---
        self.lbl_client.setStyleSheet(get_bold_style())
        self.lbl_subject.setStyleSheet(get_bold_style())
        self.lbl_method.setStyleSheet(get_bold_style())
        self.lbl_date.setStyleSheet(get_bold_style())
        self.link_toggles.setStyleSheet(get_link_style())

        # --- Main data grid: period header row ---
        for lbl in self._period_header_labels.values():
            lbl.setStyleSheet(get_note_style())
        for lbl in self._fye_labels.values():
            lbl.setStyleSheet(get_note_style())
        for lbl in self._section_labels:
            lbl.setStyleSheet(get_header_style())

        # --- Main data grid: row labels + calc cells + input cells ---
        # self._rows holds (label, is_bold, is_input, is_indent, is_margin)
        # in the same order used at build time — reuse it so restyle
        # logic can never drift from build logic.
        for idx, (label, is_bold, is_input, is_indent, is_margin) in enumerate(self._rows):
            is_bold = is_bold or (label in FORCE_BOLD_ROWS)

            row_lbl = self._row_labels.get(idx)
            if row_lbl is not None:
                style = self._row_label_style(label, is_bold, is_indent, is_margin)
                row_lbl.setStyleSheet(style)

            for data_idx, is_hist_col in enumerate(self._is_historical):
                inp = self._input_fields.get(idx, {}).get(data_idx)
                if inp is not None:
                    inp.setStyleSheet(get_input_style())
                    continue
                calc_lbl = self._calc_labels.get(idx, {}).get(data_idx)
                if calc_lbl is not None:
                    style = self._calc_cell_style(label, is_bold, is_margin, is_hist_col)
                    if style:
                        calc_lbl.setStyleSheet(style)

        # --- Terminal Value box ---
        self._lbl_tv_header.setStyleSheet(get_bold_style())
        self.tv_model_combo.setStyleSheet(get_input_style())
        self.ltg_input.setStyleSheet(get_input_style())
        for model_inputs in self._tv_inputs.values():
            for inp in model_inputs.values():
                inp.setStyleSheet(get_input_style())

        # --- CapEx Options box ---
        self._lbl_capex_header.setStyleSheet(get_bold_style())
        self.capex_dep_pct.setStyleSheet(get_input_style())

        # --- Fair Value bridge ---
        self.bridge_other_adj_input.setStyleSheet(get_input_style())
        self.bridge_fv_base_row_label.setStyleSheet(
            get_bold_style() + get_border_above_style()
        )
        self.bridge_fv_base_label.setStyleSheet(
            get_bold_style() + get_border_above_style() + get_border_below_style()
        )

        # --- Sensitivity table ---
        self._lbl_sensitivity_header.setStyleSheet(get_bold_style())
        self._lbl_wacc_ltgr_corner.setStyleSheet(get_bold_style())
        for inp in self.sens_wacc_inputs:
            inp.setStyleSheet(get_input_style())
        for inp in self.sens_ltgr_inputs:
            inp.setStyleSheet(get_input_style())
        # sens_value_labels' bold-on-high/low-cell styling is already
        # recomputed by _populate_sensitivity_table() using
        # get_bold_style(), and _recalculate() runs that every pass —
        # so one recalc pass picks up the new theme for those cells
        # without needing separate handling here.
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
        self.lbl_client.setStyleSheet(get_bold_style())
        self.lbl_subject = QLabel()
        self.lbl_subject.setStyleSheet(get_bold_style())
        self.lbl_method = QLabel("Income Approach - Discounted Cash Flow Method")
        self.lbl_method.setStyleSheet(get_bold_style())
        self.lbl_date = QLabel()
        self.lbl_date.setStyleSheet(get_bold_style())

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
            get_link_style()
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
        self._row_labels = {}
        self._period_header_labels = {}
        self._section_labels = []
        self.pv_factor_row_label = None
        self._row_idx = {}
        self._ebit_grid_row = None
        self._ebit_margin_grid_row = None
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
        self._section_labels = []
        if num_hist > 0:
            hist_lbl = _make_section_label("Historical Financials")
            self.table_grid.addWidget(hist_lbl, r, 1, 1, num_hist)
            self._section_labels.append(hist_lbl)
        proj_span = num_proj + 1 + 1  # projected cols + spacer + residual
        proj_lbl = _make_section_label("Projected Financials")
        self.table_grid.addWidget(
            proj_lbl, r, 1 + num_hist + 1, 1, proj_span
        )
        self._section_labels.append(proj_lbl)
        self._section_header_row = r
        self._current_table_row += 1

        # Row 1: symbolic period labels only — no "Line Item" text in
        # column 0, no date substitution.
        r = self._current_table_row
        for data_idx, col_label in enumerate(self._headers):
            lbl = QLabel(col_label)
            lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            lbl.setStyleSheet(get_note_style())
            self.table_grid.addWidget(lbl, r, self._grid_col(data_idx))
            self._period_header_labels[data_idx] = lbl
        self._current_table_row += 1

        # Row 2: FYE — placeholders here, populated by _recalculate().
        r = self._current_table_row
        self.table_grid.addWidget(QLabel("FYE"), r, 0)
        for data_idx, col_label in enumerate(self._headers):
            lbl = QLabel("")
            lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            lbl.setStyleSheet(get_note_style())
            self.table_grid.addWidget(lbl, r, self._grid_col(data_idx))
            self._fye_labels[col_label] = lbl
        self._current_table_row += 1

    def _row_label_style(self, label: str, is_bold: bool, is_indent: bool, is_margin: bool) -> str:
        """
        Single source of truth for a row LABEL's stylesheet string.
        Used both when the row is first built and again by
        _apply_theme() on a theme switch, so the two can never drift
        apart the way separately-maintained style logic would.
        """
        parts = []
        if is_bold:
            parts.append(get_bold_style())
        if is_indent:
            parts.append(INDENT_STYLE)
        if is_margin:
            parts.append(MARGIN_ROW_STYLE)
        if label in ROWS_WITH_BORDER_ABOVE:
            parts.append(get_border_above_style())
        return " ".join(parts)

    def _calc_cell_style(self, label: str, is_bold: bool, is_margin: bool, is_hist_col: bool) -> str:
        """Single source of truth for a calculated-value cell's stylesheet."""
        parts = []
        if is_bold:
            parts.append(get_bold_style())
        if is_margin:
            parts.append(MARGIN_CELL_STYLE)
        if label in ROWS_WITH_BORDER_ABOVE:
            if not (label == "Present Value of Free Cash Flows" and is_hist_col):
                parts.append(get_border_above_style())
        return " ".join(parts)

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
            is_bold = is_bold or (label in FORCE_BOLD_ROWS)

            if label in ROWS_WITH_SPACER_ABOVE:
                self._current_table_row += 1  # blank grid row, no widgets

            row = self._current_table_row
            row_lbl = QLabel(label)
            row_style = self._row_label_style(label, is_bold, is_indent, is_margin)
            if row_style:
                row_lbl.setStyleSheet(row_style)
            self.table_grid.addWidget(row_lbl, row, 0, alignment=Qt.AlignmentFlag.AlignLeft)
            self._row_labels[idx] = row_lbl

            if label == "Present Value Factor":
                self.pv_factor_row_label = row_lbl
            if label == "Free Cash Flow":
                self._free_cash_flow_row = row
            if label == "EBIT":
                self._ebit_grid_row = row
            if label == "EBIT Margin":
                self._ebit_margin_grid_row = row
            if label == "Net Interest Expense":
                self._net_int_grid_row = row

            # The "Less: Other Adjustments" row has a mixed source
            # model per Ted's instructions: historical = pulled from
            # Subject Financials ("Acquisitions"), projected/Residual
            # = user input. We create an input widget for projected
            # cells (and Residual) but NOT for historicals, and
            # populate both sides in _recalculate().
            is_other_adj_row = (label == "Less: Other Adjustments")
            # Amortization is a normal pulled/calc row for every column
            # except Residual, where Ted's instructions make it a user
            # input (Terminal Value amortization has no source to pull
            # from — nothing upstream projects it).
            is_amort_row = (label == "Amortization")

            self._calc_labels[idx] = {}
            self._input_fields[idx] = {}

            for data_idx in range(len(self._headers)):
                grid_col = self._grid_col(data_idx)
                is_hist_col = self._is_historical[data_idx]

                col_label = self._headers[data_idx]
                make_input = (
                    (is_other_adj_row and not is_hist_col)
                    or (is_amort_row and col_label == "Residual")
                )

                if make_input:
                    inp = QLineEdit()
                    inp.setStyleSheet(get_input_style())
                    inp.setFixedWidth(COL_WIDTH - 10)
                    inp.setAlignment(Qt.AlignmentFlag.AlignRight)
                    inp.editingFinished.connect(self._recalculate)
                    self.table_grid.addWidget(inp, row, grid_col)
                    self._input_fields[idx][data_idx] = inp
                else:
                    blank = is_hist_col and label in HIST_BLANK_ROWS
                    calc_lbl = QLabel("" if blank else "-")
                    calc_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                    # PV of FCF is blank on historical columns by design
                    # (HIST_BLANK_ROWS) — a border-top CSS rule renders on
                    # an empty label too, so that one row's border only
                    # applies to projected/Residual columns. Handled
                    # inside _calc_cell_style via the is_hist_col arg.
                    cell_style = self._calc_cell_style(label, is_bold, is_margin, is_hist_col)
                    if cell_style:
                        calc_lbl.setStyleSheet(cell_style)
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

        # Residual FYE = Final Projection Period's year + 1 — there's
        # no more standalone "Residual Year" input to read (deleted
        # per Ted's Terminal Value box redesign); Residual is defined
        # as the year immediately after the last discrete projection.
        final_proj_year_str = None
        if inputs.projection_period_columns:
            final_proj_year_str = result.get(inputs.projection_period_columns[-1])
        try:
            result["Residual"] = str(int(final_proj_year_str) + 1) if final_proj_year_str else ""
        except (ValueError, TypeError):
            result["Residual"] = ""

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
        res_layout.setContentsMargins(8, 8, 8, 8)
        self._lbl_tv_header = QLabel("Terminal Value", styleSheet=get_bold_style())
        res_layout.addWidget(self._lbl_tv_header)

        h_model = QHBoxLayout()
        h_model.addWidget(QLabel("Model:"))
        self.tv_model_combo = QComboBox()
        self.tv_model_combo.addItems(
            ["Gordon Growth", "EBITDA Multiple", "Revenue Multiple", "H-Model"]
        )
        self.tv_model_combo.setStyleSheet(get_input_style())
        self.tv_model_combo.setFixedWidth(MODEL_DROPDOWN_WIDTH)
        self.tv_model_combo.currentTextChanged.connect(self._on_tv_model_changed)
        h_model.addWidget(self.tv_model_combo)
        res_layout.addLayout(h_model)

        h_ltg = QHBoxLayout()
        h_ltg.addWidget(QLabel("Long Term Growth Rate:"))
        self.ltg_input = QLineEdit("3.0%")
        self.ltg_input.setStyleSheet(get_input_style())
        self.ltg_input.setFixedWidth(60)
        self.ltg_input.editingFinished.connect(self._recalculate)
        h_ltg.addWidget(self.ltg_input)
        res_layout.addLayout(h_ltg)

        # Each model gets its own sub-panel (own inputs + own output
        # rows), stacked in the same QVBoxLayout, visibility toggled by
        # tv_model_combo — same end result as the Excel workbook's
        # VBA-driven group show/hide, just done with widget visibility
        # instead of row grouping.
        self._tv_panels: Dict[str, QWidget] = {}
        self._tv_outputs: Dict[str, Dict[str, QLabel]] = {}
        self._tv_inputs: Dict[str, Dict[str, QLineEdit]] = {}

        res_layout.addWidget(self._build_gordon_growth_panel())
        res_layout.addWidget(self._build_ebitda_multiple_panel())
        res_layout.addWidget(self._build_revenue_multiple_panel())
        res_layout.addWidget(self._build_h_model_panel())

        res_frame.setLayout(res_layout)

        self._apply_tv_model_visibility()

        capex_frame = QFrame()
        capex_frame.setFrameShape(QFrame.Shape.StyledPanel)
        capex_layout = QVBoxLayout()
        capex_layout.setContentsMargins(8, 8, 8, 8)
        self._lbl_capex_header = QLabel("CapEx Options", styleSheet=get_bold_style())
        capex_layout.addWidget(self._lbl_capex_header)

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
        self.capex_dep_pct.setStyleSheet(get_input_style())
        self.capex_dep_pct.setFixedWidth(60)
        c5.addWidget(self.capex_dep_pct)
        capex_layout.addLayout(c5)

        capex_frame.setLayout(capex_layout)

        # Layout: left column = the new Fair Value bridge (lives where
        # the Terminal Value box used to sit, directly under PV of FCF,
        # left-aligned, plain lines rather than a boxed panel per
        # Ted's instructions). Right column = Terminal Value box
        # stacked above CapEx Options — both right-aligned now.
        bridge_widget = self._build_fv_bridge()
        self._footer_hbox.addWidget(bridge_widget, 1)

        # Boxes take their own natural (compact) width and float to
        # the right edge of this column — the blank space this
        # creates sits OUTSIDE the box border, between the two
        # columns, not stretched open inside the box like the
        # left-padding approach did.
        res_frame.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)
        capex_frame.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)

        res_row = QHBoxLayout()
        res_row.addStretch(1)
        res_row.addWidget(res_frame)

        capex_row = QHBoxLayout()
        capex_row.addStretch(1)
        capex_row.addWidget(capex_frame)

        right_col = QVBoxLayout()
        right_col.addLayout(res_row)
        right_col.addLayout(capex_row)
        right_col.addStretch(1)
        self._footer_hbox.addLayout(right_col, 2)

    def _build_fv_bridge(self) -> QWidget:
        """
        Replaces the old boxed Terminal Value spot: plain lines, not a
        panel. Sum of PV of FCF + Discounted Residual Value (linked to
        whichever Terminal Value model is currently selected) + a user
        -input Other Adjustment, reconciling to a Fair Value Base,
        continuing straight into FV High/Low. The WACC/LTGR sensitivity
        table is a separate full-width section at the bottom of the
        page (see _build_ui) — not nested in here.
        """
        widget = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)

        LABEL_COL_WIDTH = BRIDGE_LABEL_COL_WIDTH

        def row(text_label: str, input_widget=None) -> QLabel:
            h = QHBoxLayout()
            lbl = QLabel(text_label)
            lbl.setFixedWidth(LABEL_COL_WIDTH)
            h.addWidget(lbl)
            if input_widget is not None:
                h.addWidget(input_widget)
                h.addStretch()
                layout.addLayout(h)
                return input_widget
            val_lbl = QLabel("-")
            h.addWidget(val_lbl)
            h.addStretch()
            layout.addLayout(h)
            return val_lbl

        self.bridge_sum_pv_label = row("Sum of Present Value of Free Cash Flows:")
        self.bridge_disc_residual_label = row("Discounted Residual Value:")
        self.bridge_other_adj_input = QLineEdit("")
        self.bridge_other_adj_input.setStyleSheet(get_input_style())
        self.bridge_other_adj_input.setFixedWidth(90)
        self.bridge_other_adj_input.editingFinished.connect(self._recalculate)
        row("Other Adjustment:", self.bridge_other_adj_input)

        layout.addSpacing(10)
        self.bridge_fv_base_row_label = QLabel("Fair Value of Business Enterprise (Base):")
        self.bridge_fv_base_row_label.setStyleSheet(get_bold_style() + get_border_above_style())
        self.bridge_fv_base_row_label.setFixedWidth(LABEL_COL_WIDTH)
        h_base = QHBoxLayout()
        h_base.addWidget(self.bridge_fv_base_row_label)
        self.bridge_fv_base_label = QLabel("-")
        self.bridge_fv_base_label.setStyleSheet(get_bold_style() + get_border_above_style() + get_border_below_style())
        h_base.addWidget(self.bridge_fv_base_label)
        h_base.addStretch()
        layout.addLayout(h_base)

        h_hl_hdr = QHBoxLayout()
        hl_spacer = QLabel("")
        hl_spacer.setFixedWidth(LABEL_COL_WIDTH)
        h_hl_hdr.addWidget(hl_spacer)
        h_hl_hdr.addWidget(QLabel("FV High"))
        h_hl_hdr.addSpacing(20)
        h_hl_hdr.addWidget(QLabel("FV Low"))
        h_hl_hdr.addStretch()
        layout.addLayout(h_hl_hdr)

        h_hl_val = QHBoxLayout()
        hl_spacer2 = QLabel("")
        hl_spacer2.setFixedWidth(LABEL_COL_WIDTH)
        h_hl_val.addWidget(hl_spacer2)
        self.bridge_fv_high_label = QLabel("-")
        self.bridge_fv_low_label = QLabel("-")
        h_hl_val.addWidget(self.bridge_fv_high_label)
        h_hl_val.addSpacing(20)
        h_hl_val.addWidget(self.bridge_fv_low_label)
        h_hl_val.addStretch()
        layout.addLayout(h_hl_val)

        layout.addSpacing(14)
        self._lbl_sensitivity_header = QLabel("Sensitivity: Fair Value by WACC / LTGR", styleSheet=get_bold_style())
        layout.addWidget(self._lbl_sensitivity_header)
        layout.addWidget(self._build_sensitivity_table())

        layout.addStretch(1)
        widget.setLayout(layout)
        return widget

    # ------------------------------------------------------------------
    # TERMINAL VALUE — 4 model panels
    # ------------------------------------------------------------------

    def _tv_output_row(self, form: QFormLayout, model: str, key: str, label_text: str):
        lbl = QLabel("-")
        lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        form.addRow(label_text, lbl)
        self._tv_outputs.setdefault(model, {})[key] = lbl

    def _tv_input_row(self, form: QFormLayout, model: str, key: str, label_text: str, default: str):
        inp = QLineEdit(default)
        inp.setStyleSheet(get_input_style())
        inp.setFixedWidth(70)
        inp.editingFinished.connect(self._recalculate)
        form.addRow(label_text, inp)
        self._tv_inputs.setdefault(model, {})[key] = inp

    def _build_gordon_growth_panel(self) -> QWidget:
        panel = QWidget()
        form = QFormLayout()
        panel.setLayout(form)
        self._tv_output_row(form, "Gordon Growth", "cash_flow", "Residual Year Cash Flow:")
        self._tv_output_row(form, "Gordon Growth", "cap_rate", "Capitalization Rate:")
        self._tv_output_row(form, "Gordon Growth", "residual_value", "Residual Value:")
        self._tv_output_row(form, "Gordon Growth", "pv_factor", "PV Factor:")
        self._tv_output_row(form, "Gordon Growth", "pv_residual_value", "Present Value of Residual Value:")
        self._tv_panels["Gordon Growth"] = panel
        return panel

    def _build_ebitda_multiple_panel(self) -> QWidget:
        panel = QWidget()
        form = QFormLayout()
        panel.setLayout(form)
        self._tv_input_row(form, "EBITDA Multiple", "multiple", "Selected Multiple:", "10.00x")
        self._tv_output_row(form, "EBITDA Multiple", "ebitda", "EBITDA:")
        self._tv_output_row(form, "EBITDA Multiple", "multiple_out", "EBITDA Multiple:")
        self._tv_output_row(form, "EBITDA Multiple", "residual_value", "Residual Value:")
        self._tv_output_row(form, "EBITDA Multiple", "pv_factor", "PV Factor:")
        self._tv_output_row(form, "EBITDA Multiple", "pv_residual_value", "Present Value of Residual Value:")
        self._tv_panels["EBITDA Multiple"] = panel
        return panel

    def _build_revenue_multiple_panel(self) -> QWidget:
        panel = QWidget()
        form = QFormLayout()
        panel.setLayout(form)
        self._tv_input_row(form, "Revenue Multiple", "multiple", "Selected Multiple:", "10.00x")
        self._tv_output_row(form, "Revenue Multiple", "revenue", "Revenue:")
        self._tv_output_row(form, "Revenue Multiple", "multiple_out", "Revenue Multiple:")
        self._tv_output_row(form, "Revenue Multiple", "residual_value", "Residual Value:")
        self._tv_output_row(form, "Revenue Multiple", "pv_factor", "PV Factor:")
        self._tv_output_row(form, "Revenue Multiple", "pv_residual_value", "Present Value of Residual Value:")
        self._tv_panels["Revenue Multiple"] = panel
        return panel

    def _build_h_model_panel(self) -> QWidget:
        panel = QWidget()
        form = QFormLayout()
        panel.setLayout(form)
        self._tv_input_row(form, "H-Model", "num_years", "Number of Years:", "5")
        self._tv_input_row(form, "H-Model", "short_term_growth", "Short Term Growth Rate:", "20.0%")
        self._tv_output_row(form, "H-Model", "cash_flow", "Free Cash Flow:")
        self._tv_output_row(form, "H-Model", "cap_rate", "Capitalization Rate:")
        self._tv_output_row(form, "H-Model", "residual_value", "Residual Value:")
        self._tv_output_row(form, "H-Model", "pv_factor", "PV Factor:")
        self._tv_output_row(form, "H-Model", "pv_residual_value", "Present Value of Residual Value:")
        self._tv_panels["H-Model"] = panel
        return panel

    def _on_tv_model_changed(self, _text: str):
        self._apply_tv_model_visibility()
        self._recalculate()

    def _apply_tv_model_visibility(self):
        current = self.tv_model_combo.currentText()
        for model, panel in self._tv_panels.items():
            panel.setVisible(model == current)

    def _populate_terminal_value(self, wacc_val: Optional[float], inputs):
        """
        Terminal Value box. All four models share: WACC (page-level),
        LTGR (this box's own input), and the Final Projection Period's
        already-resolved grid values (EBITDA/Revenue/FCF/PV Period) —
        read straight from the main grid at final_idx, same
        "most recent level" rule as everything else on this page.

        Gordon Growth and H-Model discount off the Final Projection
        Period's own PV Period (not a chained Residual-column period —
        the main grid intentionally leaves Residual's PVP blank).
        EBITDA/Revenue Multiple offset that PV Period by +0.5 per
        Ted's formulas (mid-year-convention exit at the multiple,
        rather than end-of-year).
        """
        model = self.tv_model_combo.currentText()
        final_idx = self._num_hist + self._num_proj - 1
        if final_idx < 0:
            return

        ltgr = self._get_ltgr()
        final_pvp = _read_label(self._calc_labels, self._row_idx.get("Present Value Period"), final_idx)
        residual_idx = self._headers.index("Residual") if "Residual" in self._headers else None
        residual_fcf = (
            _read_label(self._calc_labels, self._row_idx.get("Free Cash Flow"), residual_idx)
            if residual_idx is not None else None
        )
        final_fcf = _read_label(self._calc_labels, self._row_idx.get("Free Cash Flow"), final_idx)
        final_ebitda = _read_label(self._calc_labels, self._row_idx.get("EBITDA"), final_idx)
        final_revenue = _read_label(self._calc_labels, self._row_idx.get("Revenue"), final_idx)

        cap_rate = (wacc_val - ltgr) if (wacc_val is not None and ltgr is not None) else None

        def out(m: str, key: str, text: str):
            lbl = self._tv_outputs.get(m, {}).get(key)
            if lbl is not None:
                lbl.setText(text)

        # --- Gordon Growth ---
        gg_residual_value = _safe_div(residual_fcf, cap_rate)
        gg_pv_factor = None
        if final_pvp is not None and wacc_val is not None:
            gg_pv_factor = 1.0 / ((1.0 + wacc_val) ** final_pvp)
        gg_pv_residual_value = _mul_strict(gg_residual_value, gg_pv_factor)

        out("Gordon Growth", "cash_flow", _fmt_currency(residual_fcf))
        out("Gordon Growth", "cap_rate", _fmt_pct(cap_rate))
        out("Gordon Growth", "residual_value", _fmt_currency(gg_residual_value))
        out("Gordon Growth", "pv_factor", f"{gg_pv_factor:.2f}" if gg_pv_factor is not None else "-")
        out("Gordon Growth", "pv_residual_value", _fmt_currency(gg_pv_residual_value))

        # --- EBITDA Multiple ---
        ebitda_mult = _parse_multiple(self._tv_inputs.get("EBITDA Multiple", {}).get("multiple"))
        ebitda_residual_value = _mul_strict(final_ebitda, ebitda_mult)
        ebitda_pv_factor = None
        if final_pvp is not None and wacc_val is not None:
            ebitda_pv_factor = 1.0 / ((1.0 + wacc_val) ** (final_pvp + 0.5))
        ebitda_pv_residual_value = _mul_strict(ebitda_residual_value, ebitda_pv_factor)

        out("EBITDA Multiple", "ebitda", _fmt_currency(final_ebitda))
        out("EBITDA Multiple", "multiple_out", f"{ebitda_mult:.2f}x" if ebitda_mult is not None else "-")
        out("EBITDA Multiple", "residual_value", _fmt_currency(ebitda_residual_value))
        out("EBITDA Multiple", "pv_factor", f"{ebitda_pv_factor:.2f}" if ebitda_pv_factor is not None else "-")
        out("EBITDA Multiple", "pv_residual_value", _fmt_currency(ebitda_pv_residual_value))

        # --- Revenue Multiple ---
        revenue_mult = _parse_multiple(self._tv_inputs.get("Revenue Multiple", {}).get("multiple"))
        revenue_residual_value = _mul_strict(final_revenue, revenue_mult)
        revenue_pv_factor = ebitda_pv_factor  # same PVP+0.5 convention
        revenue_pv_residual_value = _mul_strict(revenue_residual_value, revenue_pv_factor)

        out("Revenue Multiple", "revenue", _fmt_currency(final_revenue))
        out("Revenue Multiple", "multiple_out", f"{revenue_mult:.2f}x" if revenue_mult is not None else "-")
        out("Revenue Multiple", "residual_value", _fmt_currency(revenue_residual_value))
        out("Revenue Multiple", "pv_factor", f"{revenue_pv_factor:.2f}" if revenue_pv_factor is not None else "-")
        out("Revenue Multiple", "pv_residual_value", _fmt_currency(revenue_pv_residual_value))

        # --- H-Model ---
        num_years = _parse_label_as_float(
            self._tv_inputs.get("H-Model", {}).get("num_years").text()
        ) if self._tv_inputs.get("H-Model", {}).get("num_years") else None
        short_growth_text = self._tv_inputs.get("H-Model", {}).get("short_term_growth")
        short_growth = None
        if short_growth_text is not None:
            t = short_growth_text.text().strip().replace("%", "")
            try:
                short_growth = float(t) / 100.0
            except ValueError:
                short_growth = None

        h_residual_value = None
        if (final_fcf is not None and num_years is not None and short_growth is not None
                and ltgr is not None and cap_rate not in (None, 0)):
            h_residual_value = (
                (((final_fcf * num_years) / 2.0) * (short_growth - ltgr) / cap_rate)
                + (gg_residual_value if gg_residual_value is not None else 0.0)
            )
        h_pv_factor = gg_pv_factor  # same 1/(1+WACC)^PVP convention as Gordon Growth
        h_pv_residual_value = _mul_strict(h_residual_value, h_pv_factor)

        out("H-Model", "cash_flow", _fmt_currency(final_fcf))
        out("H-Model", "cap_rate", _fmt_pct(cap_rate))
        out("H-Model", "residual_value", _fmt_currency(h_residual_value))
        out("H-Model", "pv_factor", f"{h_pv_factor:.2f}" if h_pv_factor is not None else "-")
        out("H-Model", "pv_residual_value", _fmt_currency(h_pv_residual_value))

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
        # Residual runs LAST and overwrites whatever the generic
        # per-row passes above wrote for the Residual column (those
        # passes only know Subject Financials / ProjectionData, which
        # have no "Residual" period — Residual is a self-contained
        # LTGR-grown formula chain, computed here end-to-end).
        self._populate_residual_column(inputs)
        self._populate_terminal_value(wacc_val, inputs)
        self._populate_fv_bridge(inputs)
        self._populate_sensitivity_table(inputs)

    def refresh(self):
        """Public refresh entry point used by MainWindow/NWCPage."""
        self._recalculate()

    # ------------------------------------------------------------------
    # DYNAMIC ROWS
    # ------------------------------------------------------------------

    def _update_ebit_row_label(self):
        """EBIT <-> EBT dynamic label based on Cash Flows toggle.
        Applies to both the EBIT row itself and its Margin row —
        the margin row was previously left stuck on "EBIT Margin"
        even in FCFE mode."""
        new_text = "EBT" if self._cash_flows_to == "FCFE" else "EBIT"

        if self._ebit_grid_row is not None:
            lbl_item = self.table_grid.itemAtPosition(self._ebit_grid_row, 0)
            if lbl_item is not None and lbl_item.widget() is not None:
                lbl_item.widget().setText(new_text)

        if self._ebit_margin_grid_row is not None:
            lbl_item = self.table_grid.itemAtPosition(self._ebit_margin_grid_row, 0)
            if lbl_item is not None and lbl_item.widget() is not None:
                lbl_item.widget().setText(f"{new_text} Margin")

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
                widget.setVisible(not is_fcff)
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
                # Projected: pull straight from Subject Financials, same
                # as every other row on this page — it already resolves
                # cost_of_goods_sold (Revenue - Gross Profit) and
                # operating_expenses (Gross Profit - EBITDA) correctly
                # for projection periods via ProjectionData. There is
                # no LFY-ratio fallback anymore: that was a stale
                # formula from before Subject Financials exposed these
                # keys for projected periods, and it silently diverged
                # from the confirmed Gross Profit - EBITDA formula.
                rev = self._sf_get("revenue", label)
                gp = self._sf_get("gross_profit", label)
                ebitda = self._sf_get("ebitda", label)
                cogs = self._sf_get("cost_of_goods_sold", label)
                opex = self._sf_get("operating_expenses", label)

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


            if ebitda is None or dep is None:
                ebit_or_ebt = None
            elif self._cash_flows_to == "FCFF":
                ebit_or_ebt = ebitda - dep - (amort or 0.0)
            else:
                ebit_or_ebt = ebitda - dep - (amort or 0.0) - (net_int or 0.0)

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


            # Change in NWC pulled from the NWC page (was 80085 placeholder)
            nwc_change_val = None
            if hasattr(self, '_get_nwc_change') and self._get_nwc_change is not None:
                # Assumes callback returns Optional[float] or a dict by period
                result = self._get_nwc_change(label if callable(self._get_nwc_change) and not isinstance(self._get_nwc_change, dict) else label)
                if isinstance(result, dict):
                    nwc_change_val = result.get(label)
                else:
                    nwc_change_val = result
            if nwc_change_val is not None:
                self._set_currency("Less: Increase/(Decrease) in DFCFNWC", data_idx, nwc_change_val)
            else:
            # Change in NWC comes directly from the NWC schedule.
            # Same period labels are used on both pages:
            # LFY-4 ... LFY, NFY ... NFY+N, Residual.
                nwc_change = self._get_nwc_change(label)
                self._set_currency(
                    "Less: Increase/(Decrease) in DFCFNWC",
                    data_idx,
                    nwc_change,
                )

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

            required = [nopat, plus_dep, nwc, capex]
            if all(t is not None for t in required):
                fcf = nopat + plus_dep - nwc - capex - (other or 0.0)
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

            if label == "Residual":
                # Per the Excel model, Residual does NOT continue the
                # PVP/PVF/PV-FCF chain in the main grid — those exist
                # only inside the Terminal Value box, computed off
                # the Final Projection Period's PV Period, not off a
                # chained Residual-column PVP. Blank these three
                # explicitly (not left at their initial-build "-")
                # since Residual isn't "missing data," it's simply
                # not part of this chain at all.
                self._set("Present Value Period", data_idx, "")
                self._set("Present Value Factor", data_idx, "")
                self._set("Present Value of Free Cash Flows", data_idx, "")
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
            pvf_full: Optional[float] = None
            if pvp is not None and wacc_val is not None and wacc_val > 0:
                pvf_full = 1.0 / ((1.0 + wacc_val) ** pvp)
                self._set("Present Value Factor", data_idx, f"{pvf_full:.2f}")
            else:
                self._set("Present Value Factor", data_idx, "-")

            # PV of FCF — uses pvf_full (the actual computed value),
            # NOT a re-parse of the 2-decimal display label above.
            # That re-parse was the actual source of the NFY variance
            # against Excel (3,128 vs 3,140): a true PVF like 0.98039
            # displays as "0.98", and using the rounded string for the
            # multiplication baked that rounding into every PV of FCF
            # cell. Same failure shape as the WACC label round-trip
            # fixed earlier — anywhere a value is read back from its
            # own formatted display label instead of a kept float is
            # a precision leak, and this file had two of them.
            fcf = _read_label(self._calc_labels, fcf_idx, data_idx)
            if fcf is not None and pvf_full is not None:
                if label == "NFY" and ppa is not None:
                    pv_fcf = fcf * ppa * pvf_full
                else:
                    pv_fcf = fcf * pvf_full
                self._set_currency("Present Value of Free Cash Flows", data_idx, pv_fcf)
            else:
                self._set("Present Value of Free Cash Flows", data_idx, "-")

    def _build_sensitivity_table(self) -> QWidget:
        """
        WACC x LTGR sensitivity table. Every cell in the WACC row and
        LTGR column is a real user input (per Ted: "make all WACC
        spots and LTGR spots user input fields") — seeded with
        WACC/LTGR -2%/-1%/(actual)/+1%/+2%, and kept in sync with the
        page's live WACC/LTGR on every recalc UNTIL the user edits a
        given cell (see _populate_sensitivity_table's auto-text
        tracking) — Ted's WACC changes often, so a one-time default
        would go stale.

        Column layout is corner label, one narrow spacer column, then
        5 data columns — no spacing between the 5 data columns
        themselves. Header inputs and value labels share the same
        fixed width and right-alignment so a WACC header sits directly
        above its own value column (this, not an actual extra 5
        columns, was the source of the "looks like 10 columns"
        report — mismatched center/right alignment made the header
        float away from its value column visually).
        """
        container = QWidget()
        grid = QGridLayout()
        grid.setHorizontalSpacing(0)
        grid.setVerticalSpacing(4)
        grid.setColumnMinimumWidth(1, 16)  # the one intentional gap column

        wacc_now = self.get_wacc_value()
        ltgr_now = self._get_ltgr()
        wacc_now = wacc_now if wacc_now is not None else 0.10
        ltgr_now = ltgr_now if ltgr_now is not None else 0.03

        self._lbl_wacc_ltgr_corner = QLabel("WACC \\ LTGR", styleSheet=get_bold_style())
        grid.addWidget(self._lbl_wacc_ltgr_corner, 0, 0)

        DATA_COL_WIDTH = 78
        FIRST_DATA_COL = 2  # 0 = corner label, 1 = spacer

        self.sens_wacc_inputs = []
        self._sens_wacc_auto_text = []
        for col, offset in enumerate([-0.02, -0.01, 0.0, 0.01, 0.02]):
            # WACC default at 4 decimal places, exactly matching the
            # WACC page's own display precision, per Ted's instruction.
            text = f"{(wacc_now + offset) * 100:.4f}%"
            inp = QLineEdit(text)
            inp.setStyleSheet(get_input_style())
            inp.setFixedWidth(DATA_COL_WIDTH)
            inp.setAlignment(Qt.AlignmentFlag.AlignRight)
            inp.editingFinished.connect(self._recalculate)
            self.sens_wacc_inputs.append(inp)
            self._sens_wacc_auto_text.append(text)
            grid.addWidget(inp, 0, FIRST_DATA_COL + col, alignment=Qt.AlignmentFlag.AlignRight)

        self.sens_ltgr_inputs = []
        self._sens_ltgr_auto_text = []
        self.sens_value_labels = []
        for row, offset in enumerate([-0.02, -0.01, 0.0, 0.01, 0.02]):
            text = f"{(ltgr_now + offset) * 100:.1f}%"
            inp = QLineEdit(text)
            inp.setStyleSheet(get_input_style())
            inp.setFixedWidth(DATA_COL_WIDTH)
            inp.setAlignment(Qt.AlignmentFlag.AlignRight)
            inp.editingFinished.connect(self._recalculate)
            self.sens_ltgr_inputs.append(inp)
            self._sens_ltgr_auto_text.append(text)
            grid.addWidget(inp, row + 1, 0, alignment=Qt.AlignmentFlag.AlignRight)

            value_row = []
            for col in range(5):
                lbl = QLabel("-")
                lbl.setFixedWidth(DATA_COL_WIDTH)
                lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
                grid.addWidget(lbl, row + 1, FIRST_DATA_COL + col, alignment=Qt.AlignmentFlag.AlignRight)
                value_row.append(lbl)
            self.sens_value_labels.append(value_row)

        container.setLayout(grid)
        return container

    def _compute_fv_base_for(self, wacc_override: float, ltgr_text_override: str) -> Optional[float]:
        """
        Re-runs the real PV chain / Terminal Value / bridge math at an
        overridden WACC and LTGR, WITHOUT touching the page's actual
        WACC (that's a parameter everywhere already, not a widget) and
        with LTGR temporarily swapped on self.ltg_input then restored.
        This deliberately reuses the same populate methods the live
        page uses rather than a second hand-written formula set, so
        the data table can't silently drift from the real formulas —
        exactly the kind of divergence that caused the OpEx and PVF
        bugs earlier in this project.

        Revenue/COGS/GP/OpEx/EBITDA/Depreciation/Taxes/NOPAT/CapEx and
        the discrete-period Free Cash Flow values do NOT depend on
        WACC or LTGR at all and are left as whatever the live grid
        already computed — only the Residual column (LTGR-dependent),
        the PV chain (WACC-dependent), the Terminal Value box (both),
        and the bridge total are recomputed here.
        """
        orig_ltgr_text = self.ltg_input.text()
        try:
            self.ltg_input.setText(ltgr_text_override)
            inputs = self.get_project_inputs()
            self._populate_residual_column(inputs)
            self._populate_pv_chain(wacc_override, inputs)
            self._populate_terminal_value(wacc_override, inputs)
            self._populate_fv_bridge(inputs)
            return _parse_label_as_float(self.bridge_fv_base_label.text())
        finally:
            self.ltg_input.setText(orig_ltgr_text)

    def _populate_sensitivity_table(self, inputs):
        if not hasattr(self, "sens_value_labels"):
            return

        # Keep the WACC/LTGR header defaults tracking the page's live
        # WACC/LTGR — Ted's WACC changes often (Beta refresh, capital
        # structure edits), so a one-time default at construction goes
        # stale. Only refresh a field if its current text still
        # matches the last value THIS method auto-set — if it
        # differs, the user typed something, and that edit sticks.
        wacc_now = self.get_wacc_value()
        ltgr_now = self._get_ltgr()
        if wacc_now is not None:
            for col, offset in enumerate([-0.02, -0.01, 0.0, 0.01, 0.02]):
                inp = self.sens_wacc_inputs[col]
                if inp.text() == self._sens_wacc_auto_text[col]:
                    new_text = f"{(wacc_now + offset) * 100:.4f}%"
                    inp.setText(new_text)
                    self._sens_wacc_auto_text[col] = new_text
        if ltgr_now is not None:
            for row, offset in enumerate([-0.02, -0.01, 0.0, 0.01, 0.02]):
                inp = self.sens_ltgr_inputs[row]
                if inp.text() == self._sens_ltgr_auto_text[row]:
                    new_text = f"{(ltgr_now + offset) * 100:.1f}%"
                    inp.setText(new_text)
                    self._sens_ltgr_auto_text[row] = new_text

        def _pct_or_none(text: str) -> Optional[float]:
            v = _parse_label_as_float(text)
            return (v / 100.0) if v is not None else None

        wacc_vals = [_pct_or_none(w.text()) for w in self.sens_wacc_inputs]
        ltgr_vals = [_pct_or_none(l.text()) for l in self.sens_ltgr_inputs]

        # FV High = @ WACC-1% (col idx 1), LTGR+1% (row idx 3)
        # FV Low  = @ WACC+1% (col idx 3), LTGR-1% (row idx 1)
        high_coord = (3, 1)
        low_coord = (1, 3)

        for row in range(5):
            for col in range(5):
                lbl = self.sens_value_labels[row][col]
                w = wacc_vals[col]
                l = ltgr_vals[row]
                if w is None or l is None or w <= 0:
                    lbl.setText("-")
                    lbl.setStyleSheet("")
                    continue
                fv = self._compute_fv_base_for(w, self.sens_ltgr_inputs[row].text())
                lbl.setText(_fmt_currency(fv))
                lbl.setStyleSheet(get_bold_style() if (row, col) in (high_coord, low_coord) else "")

        # Wire FV High/Low off the two specific cells above, then do
        # one real recalc pass to restore the live grid — every call
        # to _compute_fv_base_for above overwrote the main grid's PV
        # chain / Terminal Value / bridge cells with an overridden
        # WACC/LTGR, so the page is currently showing the LAST
        # sensitivity cell's numbers, not the real live ones.
        self.bridge_fv_high_label.setText(self.sens_value_labels[high_coord[0]][high_coord[1]].text())
        self.bridge_fv_low_label.setText(self.sens_value_labels[low_coord[0]][low_coord[1]].text())

        wacc_val = self.get_wacc_value()
        self._populate_residual_column(inputs)
        self._populate_pv_chain(wacc_val, inputs)
        self._populate_terminal_value(wacc_val, inputs)
        self._populate_fv_bridge(inputs)

    def _populate_fv_bridge(self, inputs):
        """
        Sum of PV of FCF: sums the "Present Value of Free Cash Flows"
        row across every projected column (NFY through the Final
        Projection Period). Residual is excluded — it's already blank
        in that row (Residual's PV lives inside the Terminal Value
        box, not the main grid's PV chain).

        Discounted Residual Value: linked to whichever Terminal Value
        model is currently selected — reads that model's own
        "Present Value of Residual Value" output directly, so
        switching the model dropdown automatically updates this line.

        FV Base label switches Business Enterprise <-> Equity based
        on the FCFF/FCFE toggle, per Ted's instruction.
        """
        pv_fcf_idx = self._row_idx.get("Present Value of Free Cash Flows")
        sum_pv_fcf = 0.0
        any_val = False
        for data_idx, label in enumerate(self._headers):
            if self._is_historical[data_idx] or label == "Residual":
                continue
            v = _read_label(self._calc_labels, pv_fcf_idx, data_idx)
            if v is not None:
                sum_pv_fcf += v
                any_val = True
        sum_pv_fcf = sum_pv_fcf if any_val else None
        self.bridge_sum_pv_label.setText(_fmt_currency(sum_pv_fcf))

        model = self.tv_model_combo.currentText()
        disc_resid_lbl = self._tv_outputs.get(model, {}).get("pv_residual_value")
        disc_resid = _parse_label_as_float(disc_resid_lbl.text()) if disc_resid_lbl is not None else None
        self.bridge_disc_residual_label.setText(_fmt_currency(disc_resid))

        other_adj_text = self.bridge_other_adj_input.text().strip()
        other_adj = _parse_label_as_float(other_adj_text) if other_adj_text else 0.0

        if sum_pv_fcf is None and disc_resid is None:
            fv_base = None
        else:
            fv_base = (sum_pv_fcf or 0.0) + (disc_resid or 0.0) + (other_adj or 0.0)
        self.bridge_fv_base_label.setText(_fmt_currency(fv_base))

        is_fcff = (self._cash_flows_to == "FCFF")
        self.bridge_fv_base_row_label.setText(
            "Fair Value of Business Enterprise (Base):" if is_fcff
            else "Fair Value of Equity (Base):"
        )

        # FV High / FV Low: pending the WACC/LTGR sensitivity data
        # table (not built yet) — deliberately left blank rather than
        # computed off a table that doesn't exist.

    def _get_ltgr(self) -> Optional[float]:
        text = self.ltg_input.text().strip().replace("%", "")
        if not text:
            return None
        try:
            return float(text) / 100.0
        except ValueError:
            return None

    def _get_dep_pct_of_capex(self) -> Optional[float]:
        text = self.capex_dep_pct.text().strip().replace("%", "")
        if not text:
            return None
        try:
            return float(text) / 100.0
        except ValueError:
            return None

    def _populate_residual_column(self, inputs):
        """
        Residual is a self-contained column: every line item grows the
        Final Projection Period's own value at LTGR (or is otherwise
        formula-derived), per Ted's Residual Year instructions. It has
        no source in Subject Financials or ProjectionData, so unlike
        every other column this page doesn't pull — it computes.

        "Final Projection Period" = the last NFY+N column, read
        straight from this page's own grid cells (already-resolved
        values), per the same "pull from the most recent level" rule
        used everywhere else on this page.
        """
        if "Residual" not in self._headers:
            return
        data_idx = self._headers.index("Residual")
        final_idx = self._num_hist + self._num_proj - 1
        if final_idx < 0:
            return

        ltgr = self._get_ltgr()
        tax_rate = inputs.subject_tax_rate
        is_fcfe = (self._cash_flows_to == "FCFE")

        def final(row_label: str) -> Optional[float]:
            return _read_label(self._calc_labels, self._row_idx.get(row_label), final_idx)

        growth_factor = (1.0 + ltgr) if ltgr is not None else None

        def grow(value: Optional[float]) -> Optional[float]:
            return value * growth_factor if (value is not None and growth_factor is not None) else None

        # Revenue, COGS, OpEx: final projected period's own value grown
        # at LTGR. Gross Profit / EBITDA are then LOCAL differences of
        # those grown figures, not separately grown.
        revenue = grow(final("Revenue"))
        cogs = grow(final("Cost of Goods Sold"))
        opex = grow(final("Operating Expenses"))

        gross_profit = _sub_strict(revenue, cogs)
        ebitda = _sub_strict(gross_profit, opex)

        self._set_currency("Revenue", data_idx, revenue)
        self._set_currency("Cost of Goods Sold", data_idx, cogs)
        self._set_currency("Gross Profit", data_idx, gross_profit)
        self._set_pct("Gross Profit Margin", data_idx, _safe_div(gross_profit, revenue))
        self._set_currency("Operating Expenses", data_idx, opex)
        self._set_currency("EBITDA", data_idx, ebitda)
        self._set_pct("EBITDA Margin", data_idx, _safe_div(ebitda, revenue))

        # Depreciation = Residual CapEx * Dep-as-%-of-CapEx (CapEx
        # Options box). CapEx itself is computed further below, but
        # its formula only needs Revenue/final-period ratios, not
        # Depreciation, so no circularity — compute CapEx first.
        final_capex = final("Less: Capital Expenditures (CapEx)")
        final_revenue = final("Revenue")
        capex_ratio = _safe_div(final_capex, final_revenue)
        residual_capex = revenue * capex_ratio if (revenue is not None and capex_ratio is not None) else None
        self._set_currency("Less: Capital Expenditures (CapEx)", data_idx, residual_capex)

        dep_pct = self._get_dep_pct_of_capex()
        depreciation = residual_capex * dep_pct if (residual_capex is not None and dep_pct is not None) else None
        self._set_currency("Depreciation", data_idx, depreciation)
        self._set_currency("Plus: Depreciation", data_idx, depreciation)

        # Amortization: user input field for this column specifically.
        amort_idx = self._row_idx.get("Amortization")
        amort_inp = self._input_fields.get(amort_idx, {}).get(data_idx)
        amortization = _parse_label_as_float(amort_inp.text()) if amort_inp is not None else None

        # Net Interest Expense = Final Projection Period Net Interest
        # Expense grown at LTGR. The final-period cell already holds
        # the FCFF/FCFE-appropriate value (0 or the 8008135
        # placeholder) via _apply_net_int_proj_visibility, so reading
        # it directly is correct for either mode.
        net_interest = None
        if is_fcfe:
            net_interest = grow(final("Net Interest Expense"))
            self._set_currency("Net Interest Expense", data_idx, net_interest)

        if ebitda is None or depreciation is None:
            ebit_or_ebt = None
        elif is_fcfe:
            ebit_or_ebt = None if net_interest is None else (
                ebitda - depreciation - (amortization or 0.0) - net_interest
            )
        else:
            ebit_or_ebt = ebitda - depreciation - (amortization or 0.0)

        self._set_currency("EBIT", data_idx, ebit_or_ebt)
        self._set_pct("EBIT Margin", data_idx, _safe_div(ebit_or_ebt, revenue))

        taxes = ebit_or_ebt * tax_rate if (ebit_or_ebt is not None and tax_rate is not None) else None
        self._set_currency("Taxes", data_idx, taxes)

        nopat = (ebit_or_ebt - (taxes or 0.0)) if ebit_or_ebt is not None else None
        self._set_currency("Net Operating Profit After Tax (NOPAT)", data_idx, nopat)

        # Residual Change in NWC comes from NWCPage's Residual column.
        dfcfnwc = self._get_nwc_change("Residual")
        self._set_currency(
            "Less: Increase/(Decrease) in DFCFNWC",
            data_idx,
            dfcfnwc,
        )

        other_adj_idx = self._row_idx.get("Less: Other Adjustments")
        other_inp = self._input_fields.get(other_adj_idx, {}).get(data_idx)
        other_adj = None
        if other_inp is not None:
            raw = other_inp.text().strip()
            other_adj = _parse_label_as_float(raw) if raw else 0.0

        fcf = None
        if nopat is not None and dfcfnwc is not None:
            fcf = (
                nopat
                + (depreciation or 0.0)
                - dfcfnwc
                - (residual_capex or 0.0)
                - (other_adj or 0.0)
            )
        self._set_currency("Free Cash Flow", data_idx, fcf)

    def get_residual_revenue(self) -> Optional[float]:
        """Public accessor for NWC's Residual row — NWC's own Residual
        Total Revenue is defined as DCF's Residual Revenue directly,
        not re-derived. Single source of truth stays on this page."""
        if "Residual" not in self._headers:
            return None
        return _read_label(self._calc_labels, self._row_idx.get("Revenue"), self._headers.index("Residual"))

    def collect_state(self) -> dict:
        # Capture the "Less: Other Adjustments" projected/Residual
        # user inputs by period label so apply_state can restore
        # them after a table rebuild. Same treatment for the
        # Residual-only Amortization input.
        other_adj_idx = self._row_idx.get("Less: Other Adjustments")
        other_adj: Dict[str, str] = {}
        for data_idx, label in enumerate(self._headers):
            inp = self._input_fields.get(other_adj_idx, {}).get(data_idx)
            if inp is not None:
                other_adj[label] = inp.text()

        amort_idx = self._row_idx.get("Amortization")
        residual_idx = self._headers.index("Residual") if "Residual" in self._headers else None
        amort_inp = self._input_fields.get(amort_idx, {}).get(residual_idx) if residual_idx is not None else None
        residual_amortization = amort_inp.text() if amort_inp is not None else ""

        tv_inputs_state = {
            model: {key: widget.text() for key, widget in fields.items()}
            for model, fields in self._tv_inputs.items()
        }

        return {
            "ltg_input": self.ltg_input.text(),
            "tv_model": self.tv_model_combo.currentText(),
            "tv_inputs": tv_inputs_state,
            "capex_dep_pct": self.capex_dep_pct.text(),
            "cash_flows_to": self._cash_flows_to,
            "other_adj_inputs": other_adj,
            "residual_amortization": residual_amortization,
        }

    def apply_state(self, state: dict):
        if not state:
            return
        self.ltg_input.setText(state.get("ltg_input", "3.0%"))
        self.capex_dep_pct.setText(state.get("capex_dep_pct", "100.0%"))
        self._cash_flows_to = state.get("cash_flows_to", "FCFF")

        tv_model = state.get("tv_model", "Gordon Growth")
        idx = self.tv_model_combo.findText(tv_model)
        if idx >= 0:
            self.tv_model_combo.setCurrentIndex(idx)
        self._apply_tv_model_visibility()

        for model, fields in state.get("tv_inputs", {}).items():
            for key, text in fields.items():
                widget = self._tv_inputs.get(model, {}).get(key)
                if widget is not None:
                    widget.setText(text)

        # Other-adjustment / Residual-amortization inputs are restored
        # AFTER _rebuild_table_if_needed has created the new input
        # widgets (via _recalculate). We recalc, push saved text into
        # the QLineEdits, then recalc again so FCF / PV chain / EBIT
        # pick up the restored values.
        self._recalculate()
        other_adj_idx = self._row_idx.get("Less: Other Adjustments")
        other_adj = state.get("other_adj_inputs", {})
        for data_idx, label in enumerate(self._headers):
            inp = self._input_fields.get(other_adj_idx, {}).get(data_idx)
            if inp is not None and label in other_adj:
                inp.setText(other_adj[label])

        amort_idx = self._row_idx.get("Amortization")
        residual_idx = self._headers.index("Residual") if "Residual" in self._headers else None
        amort_inp = self._input_fields.get(amort_idx, {}).get(residual_idx) if residual_idx is not None else None
        if amort_inp is not None and "residual_amortization" in state:
            amort_inp.setText(state["residual_amortization"])

        self._recalculate()