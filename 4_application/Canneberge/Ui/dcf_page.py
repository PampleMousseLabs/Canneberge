import math
import re
from datetime import datetime
from typing import Optional, Dict, List

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QLineEdit,
    QScrollArea, QFrame, QCheckBox, QPushButton, QComboBox, QSpinBox,
    QDialog, QFormLayout, QDialogButtonBox, QSizePolicy
)
from PyQt6.QtCore import Qt

from Canneberge.Ui.theme import theme_manager
from Canneberge.Ui.font_scale import font_scale, NOTE_BASE_PX

from Canneberge.Calculations.reverse_dcf import (
    compute_cost_of_equity,
    build_fcfe_schedule,
    compute_reconciliation_a,
    solve_gordon_growth_ltgr,
    solve_h_model,
    compute_ttm_fcfe,
)
from Canneberge.Calculations.chart_helper import (
    compute_gpc_chart_data,
    compute_indexed_series,
    compute_indexed_summary_stats,
)
from Canneberge.Calculations.valuation_surface import (
    compute_gg_surface_data,
    compute_gg_surface_data_from_explicit,
)
from Canneberge.Ui.valuation_surface_chart import GGSurfaceChart
from Canneberge.Calculations.ratio_catalogue import (
    debt_free_nwc_incl_cash,
    debt_free_nwc_excl_cash,
)

HEADER_FONT_SIZE = 11
INDENT_STYLE = "padding-left: 20px;"
MARGIN_ROW_STYLE = "padding-left: 20px; font-style: italic;"
MARGIN_CELL_STYLE = "font-style: italic;"
COL_WIDTH = 95
BORDER_ABOVE_WIDTH = 1
BORDER_BELOW_WIDTH = 2

def get_input_style() -> str:
    return theme_manager.current.input_style()

def get_bold_style() -> str:
    return theme_manager.current.bold_style()

def get_header_style() -> str:
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

ROWS_WITH_BORDER_ABOVE = {
    "Gross Profit", "EBITDA", "EBIT",
    "Net Operating Profit After Tax (NOPAT)", "Free Cash Flow",
    "Present Value of Free Cash Flows",
}
ROWS_WITH_SPACER_ABOVE = {
    "Operating Expenses", "Net Operating Profit After Tax (NOPAT)",
    "Partial Period Adjustment",
}
FORCE_BOLD_ROWS = {"Revenue"}
MODEL_DROPDOWN_WIDTH = 170
BRIDGE_LABEL_COL_WIDTH = 260
FOOTER_BOX_LABEL_COL_WIDTH = 210
FOOTER_BOX_LEFT_PAD = 340
HIST_BLANK_ROWS = {
    "Partial Period Adjustment", "Present Value Period",
    "Present Value Factor", "Present Value of Free Cash Flows",
}

def _fmt_currency(value: Optional[float]) -> str:
    if value is None or (isinstance(value, float) and (math.isnan(value) or math.isinf(value))):
        return "-"
    return f"{value:,.0f}"

def _fmt_pct(value: Optional[float]) -> str:
    if value is None or (isinstance(value, float) and (math.isnan(value) or math.isinf(value))):
        return "-"
    return f"{value:.1%}"

def _fmt_currency2(value: Optional[float]) -> str:
    if value is None or (isinstance(value, float) and (math.isnan(value) or math.isinf(value))):
        return "-"
    return f"{value:,.2f}"

def _fmt_pct2(value: Optional[float]) -> str:
    if value is None or (isinstance(value, float) and (math.isnan(value) or math.isinf(value))):
        return "-"
    return f"{value*100:.2f}%"

def _make_section_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(get_header_style())
    lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    return lbl

def _safe_div(a: Optional[float], b: Optional[float]) -> Optional[float]:
    if a is None or b is None or b == 0:
        return None
    return a / b

def _sub_strict(a: Optional[float], b: Optional[float]) -> Optional[float]:
    if a is None or b is None:
        return None
    return a - b

def _mul_strict(a: Optional[float], b: Optional[float]) -> Optional[float]:
    if a is None or b is None:
        return None
    return a * b

def _parse_multiple(line_edit) -> Optional[float]:
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
    if not text or text.strip() in ("-", "", "NA"):
        return None
    cleaned = text.replace(",", "").replace("%", "").strip()
    try:
        return float(cleaned)
    except (ValueError, TypeError):
        return None

def _parse_pct_field(text: str) -> Optional[float]:
    """Accepts '15%', '15.00%', '0.15', '15' -> 0.15 decimal."""
    if not text:
        return None
    t = text.strip().replace(",", "")
    is_pct = "%" in t
    t = t.replace("%", "").strip()
    try:
        v = float(t)
    except ValueError:
        return None
    if is_pct:
        return v / 100.0
    # If user typed 15 without %, treat >1 as percent for Ga/Gn
    if abs(v) > 1.0:
        return v / 100.0
    return v

def _parse_year(text: str) -> Optional[int]:
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

def _read_label(labels: Dict[int, Dict[int, "QLabel"]], row_idx: int, data_idx: int) -> Optional[float]:
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

class ReverseDCFDialog(QDialog):
    """
    Reverse-DCF dashboard. Left panel: per-ticker data table + Gordon/H-Model
    solver. Right panel: Combo Chart (bars=absolute values, line=growth rates).
    Ticker dropdown is dynamically populated from all_inputs keys (GPCs + subject).
    """
    # Attribute controlling the subject line color — change this one
    # string to retheme the subject line across both charts instantly.
    _SUBJECT_LINE_COLOR_ATTR = "chart_conclude"

    def __init__(self, parent=None, all_inputs: Optional[Dict[str, Dict]]=None,
                 full_fade_convention: bool=True, subject_ticker: str=""):
        super().__init__(parent)
        self.setWindowTitle("Reverse-DCF — Market-Implied Growth")
        self.setMinimumSize(1100, 650)
        self.all_inputs = all_inputs or {}
        self.full_fade_convention = full_fade_convention
        self.subject_ticker = subject_ticker.strip().upper()
        self.inputs = next(iter(self.all_inputs.values()), None) if self.all_inputs else None
        # Tickers excluded from peer index summary stats (checkboxes)
        self._excluded_tickers: set = set()
        self._build_ui()
        self._populate_ticker_dropdown()
        self._recalculate()

    # ------------------------------------------------------------------
    # UI Construction
    # ------------------------------------------------------------------
    def _build_ui(self):
        from PyQt6.QtWidgets import QSplitter, QGroupBox
        from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
        from matplotlib.figure import Figure

        outer = QVBoxLayout()
        outer.setSpacing(6)
        outer.setContentsMargins(10, 10, 10, 10)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # ==============================================================
        # LEFT PANEL
        # ==============================================================
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setSpacing(8)
        left_layout.setContentsMargins(8, 8, 8, 8)

        # --- Ticker selector ---
        ticker_row = QHBoxLayout()
        ticker_row.addWidget(QLabel("Ticker:"))
        self.combo_ticker = QComboBox()
        self.combo_ticker.setStyleSheet(get_input_style())
        self.combo_ticker.setMinimumWidth(120)
        self.combo_ticker.currentTextChanged.connect(self._on_ticker_changed)
        ticker_row.addWidget(self.combo_ticker)
        ticker_row.addStretch()
        left_layout.addLayout(ticker_row)

        # --- Key metrics ---
        metrics_form = QFormLayout()
        metrics_form.setSpacing(2)
        self.lbl_market_cap = QLabel("-")
        self.lbl_ke         = QLabel("-")
        self.lbl_market_cap.setStyleSheet(get_bold_style())
        self.lbl_ke.setStyleSheet(get_bold_style())
        metrics_form.addRow("Market Cap:", self.lbl_market_cap)
        metrics_form.addRow("Ke:",         self.lbl_ke)
        left_layout.addLayout(metrics_form)

        # --- FCFE Bridge Table ---
        bridge_frame = QFrame()
        bridge_frame.setFrameShape(QFrame.Shape.StyledPanel)
        self.bridge_grid = QGridLayout(bridge_frame)
        self.bridge_grid.setSpacing(3)
        bridge_col_headers = ["", "TTM", "NFY", "NFY+1", "NFY+2"]
        bridge_row_labels  = ["Revenue", "Net Income", "Depreciation",
                               "CapEx", "ΔNWC", "FCFE", "PV(FCFE)"]
        # Header row
        for c, h in enumerate(bridge_col_headers):
            lbl = QLabel(h)
            lbl.setStyleSheet(get_bold_style())
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.bridge_grid.addWidget(lbl, 0, c)
        # Data rows: self.bridge_cells[row_label][col_header] -> QLabel
        self.bridge_cells: Dict[str, Dict[str, QLabel]] = {}
        for r, row_label in enumerate(bridge_row_labels, start=1):
            lbl_row = QLabel(row_label)
            is_bold_row = row_label in ("FCFE", "Revenue")
            lbl_row.setStyleSheet(get_bold_style() if is_bold_row else "")
            self.bridge_grid.addWidget(lbl_row, r, 0)
            self.bridge_cells[row_label] = {}
            for c, col_h in enumerate(bridge_col_headers[1:], start=1):
                cell = QLabel("-")
                cell.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.bridge_grid.addWidget(cell, r, c)
                self.bridge_cells[row_label][col_h] = cell
        left_layout.addWidget(bridge_frame)

        # --- Gordon Growth ---
        gordon_frame = QFrame()
        gordon_frame.setFrameShape(QFrame.Shape.StyledPanel)
        gordon_layout = QFormLayout(gordon_frame)
        gordon_layout.setContentsMargins(6, 4, 6, 4)
        self.lbl_gordon = QLabel("-")
        self.lbl_gordon.setStyleSheet(get_bold_style())
        gordon_layout.addRow("Gordon Implied LTGR:", self.lbl_gordon)
        left_layout.addWidget(gordon_frame)

        # --- H-Model Solver ---
        h_frame = QFrame()
        h_frame.setFrameShape(QFrame.Shape.StyledPanel)
        h_layout = QVBoxLayout(h_frame)
        h_layout.setContentsMargins(6, 6, 6, 6)
        h_layout.setSpacing(4)

        top_h = QHBoxLayout()
        top_h.addWidget(QLabel("Solve for:"))
        self.solve_combo = QComboBox()
        self.solve_combo.addItems(["H", "Ga", "Gn"])
        self.solve_combo.setStyleSheet(get_input_style())
        self.solve_combo.currentTextChanged.connect(self._on_solve_changed)
        self.solve_combo.currentTextChanged.connect(lambda _: self._update_hmodel_chart())
        top_h.addWidget(self.solve_combo)
        top_h.addStretch()
        self.chk_term_capex = QCheckBox("Terminal CapEx = Depr")
        self.chk_term_capex.setChecked(True)
        self.chk_term_capex.stateChanged.connect(self._recalculate)
        top_h.addWidget(self.chk_term_capex)
        h_layout.addLayout(top_h)

        h_form = QFormLayout()
        self.in_ga = QLineEdit("15.00%")
        self.in_gn = QLineEdit("3.00%")
        self.in_h  = QLineEdit("6.00")
        for w in [self.in_ga, self.in_gn, self.in_h]:
            w.setStyleSheet(get_input_style())
            w.setFixedWidth(90)
        self.in_ga.editingFinished.connect(self._format_ga)
        self.in_gn.editingFinished.connect(self._format_gn)
        self.in_h.editingFinished.connect(self._on_h_changed)
        h_form.addRow("Ga (ST Growth):", self.in_ga)
        h_form.addRow("Gn (LT Growth):", self.in_gn)
        h_form.addRow("H (Years):", self.in_h)
        h_layout.addLayout(h_form)

        self.lbl_h_result = QLabel("-")
        self.lbl_h_result.setStyleSheet(get_bold_style())
        h_layout.addWidget(self.lbl_h_result)
        left_layout.addWidget(h_frame)

                # --- Status bar ---
        self.status_label = QLabel("")
        self.status_label.setStyleSheet(get_note_style())
        left_layout.addWidget(self.status_label)

        # --- H-Model Results Chart (bottom left) ---
        self._hmodel_figure = Figure(figsize=(4, 4))
        self._hmodel_canvas = FigureCanvasQTAgg(self._hmodel_figure)
        self._hmodel_ax = self._hmodel_figure.add_subplot(111)
        left_layout.addWidget(self._hmodel_canvas)

        # ==============================================================
        # RIGHT PANEL — Combo Chart
        # ==============================================================
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setSpacing(6)
        right_layout.setContentsMargins(8, 8, 8, 8)

        # Metric selector dropdown
        metric_row = QHBoxLayout()
        metric_row.addWidget(QLabel("Chart Metric:"))
        self.combo_metric = QComboBox()
        self.combo_metric.addItems(["Revenue", "Net Income", "FCFE"])
        self.combo_metric.setStyleSheet(get_input_style())
        self.combo_metric.currentTextChanged.connect(self._update_combo_chart)
        metric_row.addWidget(self.combo_metric)
        metric_row.addStretch()
        right_layout.addLayout(metric_row)

        # Matplotlib Combo Chart
        self._combo_figure = Figure(figsize=(7, 4))
        self._combo_canvas = FigureCanvasQTAgg(self._combo_figure)
        self._combo_ax_bar  = self._combo_figure.add_subplot(111)
        self._combo_ax_line = self._combo_ax_bar.twinx()
        self._apply_chart_theme()
        right_layout.addWidget(self._combo_canvas)

        # ----------------------------------------------------------
        # Second chart: GPC Indexed Forecast Range
        # ----------------------------------------------------------
        index_metric_row = QHBoxLayout()
        index_metric_row.addWidget(QLabel("Index Chart Metric:"))
        self.combo_index_metric = QComboBox()
        self.combo_index_metric.addItems(["Revenue", "Net Income", "FCFE"])
        self.combo_index_metric.setStyleSheet(get_input_style())
        self.combo_index_metric.currentTextChanged.connect(self._update_index_chart)
        index_metric_row.addWidget(self.combo_index_metric)
        index_metric_row.addStretch()
        right_layout.addLayout(index_metric_row)

        # Bottom section: exclude checkboxes (left) + index chart (right)
        index_bottom = QHBoxLayout()

        # Exclude checkbox panel
        self._exclude_scroll = QScrollArea()
        self._exclude_scroll.setWidgetResizable(True)
        self._exclude_scroll.setFixedWidth(110)
        self._exclude_widget = QWidget()
        self._exclude_layout = QVBoxLayout(self._exclude_widget)
        self._exclude_layout.setSpacing(2)
        self._exclude_layout.setContentsMargins(4, 4, 4, 4)
        self._exclude_layout.addWidget(QLabel("Exclude:"))
        self._exclude_checkboxes: Dict[str, QCheckBox] = {}
        self._exclude_scroll.setWidget(self._exclude_widget)
        index_bottom.addWidget(self._exclude_scroll)

        # Index chart matplotlib figure
        self._index_figure = Figure(figsize=(6, 4))
        self._index_canvas = FigureCanvasQTAgg(self._index_figure)
        self._index_ax = self._index_figure.add_subplot(111)
        self._apply_chart_theme()
        index_bottom.addWidget(self._index_canvas)

        right_layout.addLayout(index_bottom)

        # Line visibility checkboxes below index chart
        line_toggle_row = QHBoxLayout()
        line_toggle_row.addWidget(QLabel("Show:"))
        self._line_toggles: Dict[str, QCheckBox] = {}
        _default_checked = {"Subject", "Q3", "Median", "Q1"}
        for line_name in ["Subject", "Max", "Q3", "Average", "Median", "Q1", "Min"]:
            chk = QCheckBox(line_name)
            chk.setChecked(line_name in _default_checked)
            chk.stateChanged.connect(
                lambda _state, _m=line_name: self._update_index_chart(
                    self.combo_index_metric.currentText()
                )
            )
            self._line_toggles[line_name] = chk
            line_toggle_row.addWidget(chk)
        line_toggle_row.addStretch()
        right_layout.addLayout(line_toggle_row)

        # Splitter assembly
        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setSizes([420, 620])

        outer.addWidget(splitter)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        btns.rejected.connect(self.reject)
        outer.addWidget(btns)

        self.setLayout(outer)
        self._on_solve_changed(self.solve_combo.currentText())

    # ------------------------------------------------------------------
    # Theme
    # ------------------------------------------------------------------
    def _apply_chart_theme(self):
        t = theme_manager.current
        self._combo_figure.patch.set_facecolor(t.window_bg)
        self._combo_ax_bar.set_facecolor(t.window_bg)
        if hasattr(self, "_index_figure"):
            self._index_figure.patch.set_facecolor(t.window_bg)
            self._index_ax.set_facecolor(t.window_bg)
        if hasattr(self, "_hmodel_figure"):
            self._hmodel_figure.patch.set_facecolor(t.window_bg)
            self._hmodel_ax.set_facecolor(t.window_bg)

    # ------------------------------------------------------------------
    # Ticker dropdown
    # ------------------------------------------------------------------
    def _populate_ticker_dropdown(self):
        self.combo_ticker.blockSignals(True)
        self.combo_ticker.clear()
        tickers = sorted(self.all_inputs.keys())
        self.combo_ticker.addItems(tickers)
        if tickers:
            self.combo_ticker.setCurrentIndex(0)
            self.inputs = self.all_inputs.get(tickers[0])
        self.combo_ticker.blockSignals(False)
        self._rebuild_exclude_checkboxes(tickers)

    def _rebuild_exclude_checkboxes(self, tickers: list):
        """Rebuild the exclude checkbox list to match current GPC set."""
        # Remove old checkboxes
        for chk in self._exclude_checkboxes.values():
            self._exclude_layout.removeWidget(chk)
            chk.deleteLater()
        self._exclude_checkboxes.clear()
        self._excluded_tickers.clear()

        for ticker in tickers:
            chk = QCheckBox(ticker)
            chk.setChecked(False)
            chk.stateChanged.connect(self._on_exclude_changed)
            self._exclude_layout.addWidget(chk)
            self._exclude_checkboxes[ticker] = chk

        self._exclude_layout.addStretch()

    def _on_exclude_changed(self):
        """Recompute excluded set and redraw index and H-Model charts."""
        self._excluded_tickers = {
            ticker for ticker, chk in self._exclude_checkboxes.items()
            if chk.isChecked()
        }
        self._update_index_chart(self.combo_index_metric.currentText())
        self._update_hmodel_chart()

    def _on_ticker_changed(self, ticker: str):
        self.inputs = self.all_inputs.get(ticker.strip().upper())
        self._recalculate()

    # ------------------------------------------------------------------
    # H-Model solve toggle
    # ------------------------------------------------------------------
    def _format_pct_field(self, line_edit: QLineEdit):
        """Parse, reformat as XX.XX%, then recalculate."""
        val = _parse_pct_field(line_edit.text())
        if val is not None:
            line_edit.setText(f"{val * 100:.2f}%")
        self._recalculate()
        self._update_hmodel_chart()

    def _format_ga(self):
        self._format_pct_field(self.in_ga)

    def _format_gn(self):
        self._format_pct_field(self.in_gn)

    def _on_h_changed(self):
        self._recalculate()
        self._update_hmodel_chart()

    def _on_solve_changed(self, text: str):
        self.in_ga.setEnabled(text != "Ga")
        self.in_gn.setEnabled(text != "Gn")
        self.in_h.setEnabled(text != "H")
        self._recalculate()

    # ------------------------------------------------------------------
    # Main recalculate
    # ------------------------------------------------------------------
    def _recalculate(self):
        # Guard
        if not self.inputs:
            for lbl in [self.lbl_market_cap, self.lbl_ke, self.lbl_gordon, self.lbl_h_result]:
                lbl.setText("NA")
            for row in self.bridge_cells.values():
                for cell in row.values():
                    cell.setText("NA")
            self.status_label.setText("No inputs — wire get_reverse_dcf_inputs_callback in MainWindow")
            return

        # --- Core calculations ---
        ke = compute_cost_of_equity(
            self.inputs.get("risk_free_rate"),
            self.inputs.get("relevered_beta"),
            self.inputs.get("equity_risk_premium"),
        )
        market_cap = self.inputs.get("market_cap")
        revenue    = self.inputs.get("revenue", {})
        net_income = self.inputs.get("net_income", {})
        depr_pct   = self.inputs.get("depr_pct")
        capex_pct  = self.inputs.get("capex_pct")
        nwc_pct    = self.inputs.get("nwc_pct")

        rev_ttm  = revenue.get("TTM") or revenue.get("LFY")
        rev_nfy  = revenue.get("NFY")
        rev_nfy1 = revenue.get("NFY+1")
        rev_nfy2 = revenue.get("NFY+2")
        ni_ttm   = net_income.get("TTM")
        ni_nfy   = net_income.get("NFY")
        ni_nfy1  = net_income.get("NFY+1")
        ni_nfy2  = net_income.get("NFY+2")

        fcfe_schedule = build_fcfe_schedule(
            revenue_prior=rev_ttm,
            revenue_explicit=[rev_nfy, rev_nfy1, rev_nfy2],
            net_income_explicit=[ni_nfy, ni_nfy1, ni_nfy2],
            depr_pct=depr_pct,
            capex_pct=capex_pct,
            nwc_pct=nwc_pct,
            force_terminal_capex_equals_da=self.chk_term_capex.isChecked(),
        )

        a      = compute_reconciliation_a(market_cap, fcfe_schedule, ke)
        fcfe_n = fcfe_schedule[-1]["fcfe"] if fcfe_schedule else None

        # --- Key metrics labels ---
        self.lbl_market_cap.setText(_fmt_currency2(market_cap))
        self.lbl_ke.setText(_fmt_pct2(ke))

        # --- Bridge table ---
        col_keys = ["TTM", "NFY", "NFY+1", "NFY+2"]
        # Revenue
        rev_vals = [rev_ttm, rev_nfy, rev_nfy1, rev_nfy2]
        for col, v in zip(col_keys, rev_vals):
            self.bridge_cells["Revenue"][col].setText(_fmt_currency2(v))
        # Net Income
        ni_vals = [ni_ttm, ni_nfy, ni_nfy1, ni_nfy2]
        for col, v in zip(col_keys, ni_vals):
            self.bridge_cells["Net Income"][col].setText(_fmt_currency2(v))
        # Depreciation, CapEx (% of revenue -> absolute)
        for col, rev_v in zip(col_keys, rev_vals):
            dep_v  = (rev_v * depr_pct)  if (rev_v is not None and depr_pct  is not None) else None
            cap_v  = (rev_v * capex_pct) if (rev_v is not None and capex_pct is not None) else None
            self.bridge_cells["Depreciation"][col].setText(_fmt_currency2(dep_v))
            self.bridge_cells["CapEx"][col].setText(_fmt_currency2(cap_v))
        # ΔNWC — TTM = 0 (base), rest from schedule
        self.bridge_cells["ΔNWC"]["TTM"].setText("0")
        if fcfe_schedule:
            for yr, col in zip(fcfe_schedule, ["NFY", "NFY+1", "NFY+2"]):
                self.bridge_cells["ΔNWC"][col].setText(_fmt_currency2(yr["delta_nwc"]))
        # FCFE — TTM computed, rest from schedule
        from Canneberge.Calculations.reverse_dcf import compute_ttm_fcfe
        fcfe_ttm = compute_ttm_fcfe(ni_ttm, rev_ttm, depr_pct, capex_pct)
        self.bridge_cells["FCFE"]["TTM"].setText(_fmt_currency2(fcfe_ttm))
        if fcfe_schedule:
            for yr, col in zip(fcfe_schedule, ["NFY", "NFY+1", "NFY+2"]):
                self.bridge_cells["FCFE"][col].setText(_fmt_currency2(yr["fcfe"]))
        # PV(FCFE)
        self.bridge_cells["PV(FCFE)"]["TTM"].setText("-")
        if fcfe_schedule and ke is not None:
            for yr, col in zip(fcfe_schedule, ["NFY", "NFY+1", "NFY+2"]):
                pv = yr["fcfe"] / ((1 + ke) ** yr["year_index"])
                self.bridge_cells["PV(FCFE)"][col].setText(_fmt_currency2(pv))

        # --- Gordon Growth ---
        gordon = solve_gordon_growth_ltgr(a, ke, fcfe_n)
        if gordon["value"] is None:
            self.lbl_gordon.setText(f"NA ({','.join(gordon['flags'])})")
        else:
            self.lbl_gordon.setText(
                _fmt_pct2(gordon["value"]) +
                ("" if gordon["is_valid"] else f" [{','.join(gordon['flags'])}]")
            )

        # --- H-Model ---
        solve_for = self.solve_combo.currentText()
        ga = _parse_pct_field(self.in_ga.text()) if solve_for != "Ga" else None
        gn = _parse_pct_field(self.in_gn.text()) if solve_for != "Gn" else None
        try:
            h_val = float(self.in_h.text().strip()) if solve_for != "H" else None
        except Exception:
            h_val = None

        h_res = solve_h_model(
            a, ke, fcfe_n, ga=ga, gn=gn, h=h_val,
            solve_for=solve_for, full_fade_convention=self.full_fade_convention,
        )
        if h_res["value"] is None:
            self.lbl_h_result.setText("NA")
            self.status_label.setText(
                f"{self.inputs.get('ticker','')}: {','.join(h_res['flags'])} | "
                f"Gordon: {','.join(gordon['flags'])}"
            )
        else:
            if solve_for == "H":
                h_full = h_res["value"]
                h_half = h_full / 2 if self.full_fade_convention else h_full
                self.lbl_h_result.setText(f"H full={h_full:.2f} (h half={h_half:.2f})")
            else:
                self.lbl_h_result.setText(_fmt_pct2(h_res["value"]))
            all_flags = gordon["flags"] + h_res["flags"]
            self.status_label.setText(", ".join(all_flags) if all_flags else "")

        # --- Store chart data for current ticker & redraw ---
        self._chart_data = compute_gpc_chart_data(self.inputs)
        self._update_combo_chart(self.combo_metric.currentText())
        self._update_index_chart(self.combo_index_metric.currentText())
        self._update_hmodel_chart()

    # ------------------------------------------------------------------
    # H-Model Results Chart
    # ------------------------------------------------------------------
    def _update_hmodel_chart(self):
        if not self.all_inputs:
            return

        t = theme_manager.current
        subject_color = getattr(t, self._SUBJECT_LINE_COLOR_ATTR, t.chart_conclude)
        solve_for = self.solve_combo.currentText()  # "H", "Ga", "Gn"

        # Parse fixed inputs
        ga = _parse_pct_field(self.in_ga.text()) if solve_for != "Ga" else None
        gn = _parse_pct_field(self.in_gn.text()) if solve_for != "Gn" else None
        try:
            h_val = float(self.in_h.text().strip()) if solve_for != "H" else None
        except Exception:
            h_val = None

        # Collect results across all tickers
        ticker_labels = []
        bar_values    = []
        bar_colors    = []

        for ticker, inp in self.all_inputs.items():
            if inp.get("_error"):
                continue
            if ticker in self._excluded_tickers:
                continue
            try:
                chart_data = compute_gpc_chart_data(inp)
                ke         = chart_data.get("ke")
                fcfe_sched = chart_data.get("fcfe_schedule")
                fcfe_n     = fcfe_sched[-1]["fcfe"] if fcfe_sched else None
                market_cap = inp.get("market_cap")

                a = compute_reconciliation_a(market_cap, fcfe_sched, ke)
                h_res = solve_h_model(
                    a, ke, fcfe_n,
                    ga=ga, gn=gn, h=h_val,
                    solve_for=solve_for,
                    full_fade_convention=self.full_fade_convention,
                )
            except Exception:
                continue

            if h_res["value"] is None:
                continue  # skip invalid — user can investigate via ticker dropdown

            ticker_labels.append(ticker)
            bar_values.append(h_res["value"])
            bar_colors.append(
                subject_color if ticker.upper() == self.subject_ticker.upper()
                else t.chart_fill
            )

        self._hmodel_ax.clear()
        self._hmodel_figure.patch.set_facecolor(t.window_bg)
        self._hmodel_ax.set_facecolor(t.window_bg)

        if not ticker_labels:
            self._hmodel_ax.text(
                0.5, 0.5, "No valid results",
                ha="center", va="center",
                color=t.chart_axis_label, fontsize=9,
                transform=self._hmodel_ax.transAxes,
            )
            self._hmodel_figure.tight_layout()
            self._hmodel_canvas.draw()
            return

        # Horizontal bar chart — tickers on Y axis, values on X axis
        y_pos = list(range(len(ticker_labels)))
        self._hmodel_ax.barh(
            y_pos, bar_values,
            color=bar_colors,
            edgecolor=t.chart_edge,
            height=0.6,
            zorder=2,
        )
        self._hmodel_ax.set_yticks(y_pos)
        self._hmodel_ax.set_yticklabels(ticker_labels, color=t.chart_axis_label, fontsize=8)
        self._hmodel_ax.tick_params(axis="x", colors=t.chart_axis_label)
        self._hmodel_ax.grid(True, axis="x", alpha=0.25, color=t.chart_grid, zorder=0)
        for spine in self._hmodel_ax.spines.values():
            spine.set_color(t.chart_grid)

        # Data labels at end of each bar
        is_pct = solve_for in ("Ga", "Gn")
        for y, val in zip(y_pos, bar_values):
            label_text = f"{val * 100:.2f}%" if is_pct else f"{val:.2f}"
            x_offset   = max(abs(v) for v in bar_values) * 0.02
            self._hmodel_ax.text(
                val + (x_offset if val >= 0 else -x_offset),
                y,
                label_text,
                va="center",
                ha="left" if val >= 0 else "right",
                color=t.default_text,
                fontsize=7,
                zorder=3,
            )

        # X axis format
        if is_pct:
            from matplotlib.ticker import FuncFormatter
            self._hmodel_ax.xaxis.set_major_formatter(
                FuncFormatter(lambda val, _: f"{val * 100:.1f}%")
            )

        self._hmodel_ax.set_title(
            f"H-Model: Solved {solve_for} per GPC",
            color=t.default_text, fontsize=9,
        )
        self._hmodel_ax.axvline(0, color=t.chart_grid, linewidth=0.8, zorder=1)

        self._hmodel_figure.tight_layout()
        self._hmodel_canvas.draw()

    # ------------------------------------------------------------------
    # Index Chart
    # ------------------------------------------------------------------
    def _update_index_chart(self, metric: str):
        if not self.all_inputs:
            return

        t = theme_manager.current
        subject_color = getattr(t, self._SUBJECT_LINE_COLOR_ATTR, t.chart_conclude)

        result = compute_indexed_summary_stats(
            all_inputs=self.all_inputs,
            metric=metric,
            excluded_tickers=self._excluded_tickers,
            subject_ticker=self.subject_ticker,
        )

        x_labels = result["x_labels"]
        x        = list(range(len(x_labels)))
        stats    = result["stats"]
        subject  = result["subject"]

        self._index_ax.clear()
        self._index_figure.patch.set_facecolor(t.window_bg)
        self._index_ax.set_facecolor(t.window_bg)

        # x indices: 0=TTM, 1=NFY, 2=NFY+1, 3=NFY+2, 4=Perp
        # solid segment: indices 0-3, dashed segment: indices 3-4
        SOLID_IDX  = slice(0, 4)   # TTM -> NFY+2
        DASH_IDX   = slice(3, 5)   # NFY+2 -> Perp

        def _plot_two_segment(ax, x, y_vals, color, lw, label, marker=None, ms=4, zorder=2):
            """
            Plots a line as two segments:
              solid:  TTM -> NFY+2  (indices 0-3)
              dashed: NFY+2 -> Perp (indices 3-4)
            Only the solid segment gets the legend label to avoid duplicates.
            """
            # Solid segment
            sx = [x[i] for i in range(4) if i < len(y_vals) and y_vals[i] is not None]
            sy = [y_vals[i] for i in range(4) if i < len(y_vals) and y_vals[i] is not None]
            if sx:
                kwargs = dict(color=color, linewidth=lw, linestyle="-",
                              label=label, zorder=zorder)
                if marker:
                    kwargs.update(marker=marker, markersize=ms)
                ax.plot(sx, sy, **kwargs)

            # Dashed segment (NFY+2 -> Perp, indices 3 and 4)
            dx = []
            dy = []
            for i in [3, 4]:
                if i < len(y_vals) and y_vals[i] is not None:
                    dx.append(x[i])
                    dy.append(y_vals[i])
            if len(dx) == 2:
                kwargs = dict(color=color, linewidth=lw, linestyle="--",
                              zorder=zorder)
                if marker:
                    kwargs.update(marker=marker, markersize=ms)
                ax.plot(dx, dy, **kwargs)

        # Stat line styling — all solid->dashed via _plot_two_segment
        stat_styles = {
            "max":    {"color": t.chart_grid,        "lw": 1.2, "label": "Max"},
            "q3":     {"color": t.chart_axis_label,  "lw": 1.5, "label": "Q3"},
            "mean":   {"color": t.chart_fill,        "lw": 1.5, "label": "Average"},
            "median": {"color": t.default_text,      "lw": 2.0, "label": "Median"},
            "q1":     {"color": t.chart_axis_label,  "lw": 1.5, "label": "Q1"},
            "min":    {"color": t.chart_grid,        "lw": 1.2, "label": "Min"},
        }

        # Map stat_key -> toggle label
        stat_toggle_map = {
            "max":    "Max",
            "q3":     "Q3",
            "mean":   "Average",
            "median": "Median",
            "q1":     "Q1",
            "min":    "Min",
        }

        for stat_name, style in stat_styles.items():
            toggle_label = stat_toggle_map[stat_name]
            if not self._line_toggles.get(toggle_label, QCheckBox()).isChecked():
                continue
            y_vals = stats.get(stat_name, [])
            _plot_two_segment(
                self._index_ax, x, y_vals,
                color=style["color"], lw=style["lw"],
                label=style["label"], zorder=2,
            )

        # Subject line
        if subject is not None and self._line_toggles.get("Subject", QCheckBox()).isChecked():
            _plot_two_segment(
                self._index_ax, x, subject,
                color=subject_color, lw=2.5,
                label=self.subject_ticker or "Subject",
                marker="o", ms=5, zorder=3,
            )

        self._index_ax.set_xticks(x)
        self._index_ax.set_xticklabels(x_labels, color=t.chart_axis_label, fontsize=9)
        self._index_ax.set_ylabel("Indexed (TTM = 100)", color=t.default_text, fontsize=9)
        self._index_ax.tick_params(colors=t.chart_axis_label)
        self._index_ax.grid(True, axis="y", alpha=0.25, color=t.chart_grid, zorder=0)
        self._index_ax.axhline(100, color=t.chart_grid, linewidth=0.8, linestyle=":", zorder=1)
        for spine in self._index_ax.spines.values():
            spine.set_color(t.chart_grid)
        self._index_ax.legend(
            fontsize=7, loc="upper left",
            facecolor=t.window_bg, edgecolor=t.chart_grid,
            labelcolor=t.default_text,
        )
        self._index_ax.set_title(
            f"GPC Indexed {metric} Forecast Range (TTM = 100)",
            color=t.default_text, fontsize=10,
        )

        self._index_figure.tight_layout()
        self._index_canvas.draw()

    # ------------------------------------------------------------------
    # Combo Chart
    # ------------------------------------------------------------------
    def _update_combo_chart(self, metric: str):
        if not hasattr(self, "_chart_data") or self._chart_data is None:
            return

        t = theme_manager.current
        bars   = self._chart_data["bars"].get(metric, [None, None, None, None])
        growth = self._chart_data["growth"].get(metric, [None, None, None, None])
        x_labels = ["NFY", "NFY+1", "NFY+2", "Perp"]
        x = list(range(len(x_labels)))

        self._combo_ax_bar.clear()
        self._combo_ax_line.clear()
        self._apply_chart_theme()

        # Bars (primary axis)
        bar_vals = [v if v is not None else 0 for v in bars]
        self._combo_ax_bar.bar(
            x, bar_vals, color=t.chart_fill,
            edgecolor=t.chart_edge, width=0.5, zorder=2,
        )
        from matplotlib.ticker import FuncFormatter
        self._combo_ax_bar.set_xticks(x)
        self._combo_ax_bar.set_xticklabels(x_labels, color=t.chart_axis_label, fontsize=9)
        self._combo_ax_bar.set_ylabel(metric, color=t.default_text, fontsize=9)
        self._combo_ax_bar.tick_params(axis="x", colors=t.chart_axis_label)
        self._combo_ax_bar.tick_params(axis="y", colors=t.chart_axis_label)
        self._combo_ax_bar.grid(True, axis="y", alpha=0.25, color=t.chart_grid, zorder=0)
        for spine in self._combo_ax_bar.spines.values():
            spine.set_color(t.chart_grid)
        self._combo_ax_bar.yaxis.set_major_formatter(
            FuncFormatter(lambda val, _: f"{val:,.0f}")
        )
        self._combo_ax_line.tick_params(axis="y", colors=t.chart_axis_label)
        for spine in self._combo_ax_line.spines.values():
            spine.set_color(t.chart_grid)

        # Line (secondary axis — growth %)
        growth_vals = [v * 100 if v is not None else None for v in growth]
        plot_x = [xi for xi, v in zip(x, growth_vals) if v is not None]
        plot_y = [v  for v   in growth_vals             if v is not None]
        if plot_x:
            self._combo_ax_line.plot(
                plot_x, plot_y,
                color=t.chart_edge,
                linewidth=2, marker="o", markersize=5, zorder=3,
            )
        self._combo_ax_line.set_ylabel(f"{metric} Growth %", color=t.default_text, fontsize=9)
        self._combo_ax_line.yaxis.set_label_position("right")
        self._combo_ax_line.tick_params(axis="y", colors=t.chart_axis_label)
        
        ticker = self.inputs.get("ticker", "") if self.inputs else ""
        self._combo_ax_bar.set_title(
            f"{ticker} — {metric} & Growth", color=t.default_text, fontsize=10,
        )

        self._combo_figure.tight_layout()
        self._combo_canvas.draw()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def set_all_inputs(self, all_inputs: Dict[str, Dict]):
        """Called externally to refresh with a new GPC set."""
        self.all_inputs = all_inputs or {}
        self._populate_ticker_dropdown()
        self._recalculate()

class DCFPage(QWidget):
    def __init__(self,
                 get_project_inputs_callback,
                 get_wacc_value_callback,
                 get_subject_financials_callback,
                 get_projection_data_callback,
                 update_projection_callback,
                 get_nwc_change_callback=None,
                 get_ke_value_callback=None,
                 get_reverse_dcf_inputs_callback=None,
                 get_gpc_tickers_callback=None,
                 get_projected_interest_expense_callback=None):
        super().__init__()
        self.get_project_inputs = get_project_inputs_callback
        self.get_wacc_value = get_wacc_value_callback
        self.get_ke_value = get_ke_value_callback or (lambda: None)
        self._get_subject_financials = get_subject_financials_callback
        self._get_projection_data = get_projection_data_callback
        self._update_projection_callback = update_projection_callback
        self._get_nwc_change = get_nwc_change_callback or (lambda _period: None)
        self._get_reverse_dcf_inputs_callback = get_reverse_dcf_inputs_callback
        self._get_gpc_tickers_callback = get_gpc_tickers_callback
        self._get_projected_interest_expense = (
            get_projected_interest_expense_callback or (lambda _period: None)
        )

        self._calc_labels = {}
        self._input_fields = {}
        self._headers = []
        self._is_historical = []
        self._fye_labels = {}
        self.pv_factor_row_label = None
        self._row_labels = {}
        self._period_header_labels = {}
        self._section_labels = []
        self._row_idx = {}
        self._ebit_grid_row = None
        self._ebit_margin_grid_row = None
        self._net_int_grid_row = None
        self.table_container = None
        self._built_hist_years = None
        self._built_proj_years = None
        self._table_insert_index = 0
        self._num_hist = 0
        self._num_proj = 0
        self._cash_flows_to = "FCFF"
        # Per cash-flow-mode memory for TV multiple inputs so an
        # EBITDA exit multiple typed under FCFF is not reused under FCFE.
        self._per_cf_tv_multiples = {
            "FCFF": {"EBITDA Multiple": None, "Revenue Multiple": None},
            "FCFE": {"EBITDA Multiple": None, "Revenue Multiple": None},
        }
        self._last_cf_mode = None

        # Full-precision output from Canneberge.Calculations.dcf.build_dcf().
        # The PyQt page renders this result; it no longer recomputes the DCF
        # by reading rounded values back from QLabel text.
        self._shared_calc = None

        self._build_ui()
        self._recalculate()
        theme_manager.theme_changed.connect(self._apply_theme)

    def _get_discount_rate(self) -> Optional[float]:
        """Returns Ke for FCFE, WACC for FCFF."""
        if self._cash_flows_to == "FCFE":
            return self.get_ke_value()
        return self.get_wacc_value()

    def _apply_theme(self, theme=None):
        self.lbl_client.setStyleSheet(get_bold_style())
        self.lbl_subject.setStyleSheet(get_bold_style())
        self.lbl_method.setStyleSheet(get_bold_style())
        self.lbl_date.setStyleSheet(get_bold_style())
        self.link_toggles.setStyleSheet(get_link_style())
        if hasattr(self, 'link_reverse_dcf'):
            self.link_reverse_dcf.setStyleSheet(get_link_style())
        for lbl in self._period_header_labels.values():
            lbl.setStyleSheet(get_note_style())
        for lbl in self._fye_labels.values():
            lbl.setStyleSheet(get_note_style())
        for lbl in self._section_labels:
            lbl.setStyleSheet(get_header_style())
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
        self._lbl_tv_header.setStyleSheet(get_bold_style())
        self.tv_model_combo.setStyleSheet(get_input_style())
        self.ltg_input.setStyleSheet(get_input_style())
        for model_inputs in self._tv_inputs.values():
            for inp in model_inputs.values():
                inp.setStyleSheet(get_input_style())
        self.capex_dep_pct.setStyleSheet(get_input_style())
        self.bridge_other_adj_input.setStyleSheet(get_input_style())
        self.bridge_fv_base_row_label.setStyleSheet(get_bold_style() + get_border_above_style())
        self.bridge_fv_base_label.setStyleSheet(get_bold_style() + get_border_above_style() + get_border_below_style())
        self._lbl_sensitivity_header.setStyleSheet(get_bold_style())
        self._lbl_wacc_ltgr_corner.setStyleSheet(get_bold_style())
        for inp in self.sens_wacc_inputs:
            inp.setStyleSheet(get_input_style())
        for inp in self.sens_ltgr_inputs:
            inp.setStyleSheet(get_input_style())
        self._recalculate()

    def _build_ui(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self.page_container = QWidget()
        self.page_layout = QVBoxLayout()
        self.page_layout.setSpacing(4)
        self.page_layout.setContentsMargins(10, 10, 10, 10)
        self._build_header_controls()
        self._table_insert_index = self.page_layout.count()
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
        self.link_toggles.setStyleSheet(get_link_style())
        self.link_toggles.setCursor(Qt.CursorShape.PointingHandCursor)
        self.link_toggles.clicked.connect(self._open_toggles)
        toggle_row.addWidget(self.link_toggles)

        toggle_row.addStretch()
        self.page_layout.addLayout(toggle_row)

    def _open_toggles(self):
        inputs = self.get_project_inputs()
        dialog = ProjectionTogglesDialog(inputs, self)
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

    def _open_reverse_dcf(self):
        all_inputs = {}
        # Try to get all GPC tickers + subject from callback
        if self._get_reverse_dcf_inputs_callback is not None:
            try:
                proj_inputs = self.get_project_inputs()
                # Get subject ticker
                subject_ticker = (
                    getattr(proj_inputs, 'subject_ticker', None) or
                    getattr(proj_inputs, 'ticker', None) or
                    getattr(proj_inputs, 'subject_company_name', None) or
                    "SUBJ"
                )
                # Get GPC tickers if callback available
                gpc_tickers = []
                if self._get_gpc_tickers_callback is not None:
                    try:
                        gpc_tickers = self._get_gpc_tickers_callback() or []
                    except Exception as e:
                        print(f"GPC tickers callback failed: {e}")

                # Loop all tickers: subject + GPCs
                all_tickers = [subject_ticker] + [
                    t for t in gpc_tickers if t != subject_ticker
                ]
                for ticker in all_tickers:
                    try:
                        inp = self._get_reverse_dcf_inputs_callback(ticker)
                        if inp is not None:
                            all_inputs[ticker.upper()] = inp
                    except Exception as e:
                        print(f"Reverse-DCF input fetch failed for {ticker}: {e}")
            except Exception as e:
                print(f"Reverse-DCF open failed: {e}")

        # Fallback: build from page data for subject only
        if not all_inputs:
            fallback = self._build_reverse_dcf_inputs_from_page()
            if fallback:
                ticker_key = fallback.get("ticker", "SUBJ").upper()
                all_inputs[ticker_key] = fallback

        subject_ticker = (
            getattr(proj_inputs, 'subject_ticker', None) or
            getattr(proj_inputs, 'ticker', None) or
            "SUBJ"
        )
        dlg = ReverseDCFDialog(self, all_inputs=all_inputs,
                               full_fade_convention=True,
                               subject_ticker=subject_ticker)
        dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dlg.show()

    def _build_reverse_dcf_inputs_from_page(self) -> Optional[Dict]:
        """Fallback when MainWindow callback not wired yet. Builds from DCF grid."""
        try:
            # Revenue
            revenue = {}
            for lbl in ["LFY","TTM","NFY","NFY+1","NFY+2"]:
                try:
                    revenue[lbl] = self._get_subject_financials("revenue", lbl)
                except:
                    revenue[lbl] = None
            if revenue.get("TTM") is None:
                revenue["TTM"] = revenue.get("LFY")

            net_income = {}
            for lbl in ["LFY","TTM","NFY","NFY+1","NFY+2"]:
                try:
                    val = self._get_subject_financials("net_income", lbl)
                    if val is None:
                        val = self._get_subject_financials("net income", lbl)
                    net_income[lbl] = val
                except:
                    net_income[lbl] = None

            rev_ttm = revenue.get("TTM") or revenue.get("LFY")
            dep_ttm = None
            capex_ttm = None
            try:
                dep_ttm = self._get_subject_financials("d&a_for_ebitda", "LFY")
                if dep_ttm is None:
                    dep_ttm = self._get_subject_financials("depreciation", "LFY")
            except:
                dep_ttm = None
            try:
                capex_ttm = self._get_subject_financials("capex", "LFY")
            except:
                capex_ttm = None

            depr_pct = (abs(dep_ttm)/rev_ttm) if dep_ttm and rev_ttm else None
            capex_pct = (abs(capex_ttm)/rev_ttm) if capex_ttm and rev_ttm else None

            # NWC % from BS
            nwc_keys = ["total_current_assets", "total_current_liab",
            "current_ltd", "st_debt", "current_leases", "cash"]
            bs = {}
            for k in nwc_keys:
                try:
                    bs[k] = self._get_subject_financials(k, "LFY")
                except:
                    bs[k] = None
            try:
                nwc_val = debt_free_nwc_excl_cash(bs)
            except:
                nwc_val = None
            nwc_pct = (nwc_val/rev_ttm) if nwc_val and rev_ttm else None

            return {
                "ticker": getattr(self.get_project_inputs(), 'subject_company_name', 'SUBJ'),
                "market_cap": None,
                "revenue": revenue,
                "net_income": net_income,
                "depr_pct": depr_pct,
                "capex_pct": capex_pct,
                "nwc_pct": nwc_pct,
                "risk_free_rate": None,
                "relevered_beta": None,
                "equity_risk_premium": None,
            }
        except Exception:
            return None

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
        num_hist, num_proj = self._num_hist, self._num_proj
        if data_idx < num_hist:
            return 1 + data_idx
        elif data_idx < num_hist + num_proj:
            return 1 + num_hist + 1 + (data_idx - num_hist)
        else:
            return 1 + num_hist + 1 + num_proj + 1

    def _rebuild_table_if_needed(self, force: bool = False):
        inputs = self.get_project_inputs()
        new_hist = inputs.historical_years
        new_proj = inputs.projection_years
        if (not force and self.table_container is not None and new_hist == self._built_hist_years and new_proj == self._built_proj_years):
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
        if not hasattr(self, '_valuation_surface_dialog'):
            self._valuation_surface_dialog = None
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
        r = self._current_table_row
        self._section_labels = []
        if num_hist > 0:
            hist_lbl = _make_section_label("Historical Financials")
            self.table_grid.addWidget(hist_lbl, r, 1, 1, num_hist)
            self._section_labels.append(hist_lbl)
        proj_span = num_proj + 1 + 1
        proj_lbl = _make_section_label("Projected Financials")
        self.table_grid.addWidget(proj_lbl, r, 1 + num_hist + 1, 1, proj_span)
        self._section_labels.append(proj_lbl)
        self._section_header_row = r
        self._current_table_row += 1
        r = self._current_table_row
        for data_idx, col_label in enumerate(self._headers):
            lbl = QLabel(col_label)
            lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            lbl.setStyleSheet(get_note_style())
            self.table_grid.addWidget(lbl, r, self._grid_col(data_idx))
            self._period_header_labels[data_idx] = lbl
        self._current_table_row += 1
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
            ("Stock-Based Compensation", False, False, False, False),
            ("+Other Adjustments", False, False, False, False),
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
        for idx, (label, _, _, _, _) in enumerate(self._rows):
            self._row_idx[label] = idx
        self._free_cash_flow_row = None
        for idx, (label, is_bold, is_input, is_indent, is_margin) in enumerate(self._rows):
            is_bold = is_bold or (label in FORCE_BOLD_ROWS)
            if label in ROWS_WITH_SPACER_ABOVE:
                self._current_table_row += 1
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
            is_other_adj_row = (label == "Less: Other Adjustments")
            is_amort_row = (label == "Amortization")
            self._calc_labels[idx] = {}
            self._input_fields[idx] = {}
            for data_idx in range(len(self._headers)):
                grid_col = self._grid_col(data_idx)
                is_hist_col = self._is_historical[data_idx]
                col_label = self._headers[data_idx]
                make_input = ((is_other_adj_row and not is_hist_col) or (is_amort_row and col_label == "Residual"))
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
                    cell_style = self._calc_cell_style(label, is_bold, is_margin, is_hist_col)
                    if cell_style:
                        calc_lbl.setStyleSheet(cell_style)
                    self.table_grid.addWidget(calc_lbl, row, grid_col)
                    self._calc_labels[idx][data_idx] = calc_lbl
            self._current_table_row += 1
        vline_col = 1 + num_hist
        vline = QFrame()
        vline.setFrameShape(QFrame.Shape.VLine)
        vline.setFrameShadow(QFrame.Shadow.Sunken)
        span = (self._free_cash_flow_row - self._section_header_row) + 1
        self.table_grid.addWidget(vline, self._section_header_row, vline_col, span, 1)
        self.table_grid.setColumnMinimumWidth(vline_col, 8)
        spacer_col = 1 + num_hist + 1 + num_proj
        self.table_grid.setColumnMinimumWidth(spacer_col, 14)

    def _compute_fye_years(self, inputs) -> Dict[str, str]:
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
        final_proj_year_str = None
        if inputs.projection_period_columns:
            final_proj_year_str = result.get(inputs.projection_period_columns[-1])
        try:
            result["Residual"] = str(int(final_proj_year_str) + 1) if final_proj_year_str else ""
        except (ValueError, TypeError):
            result["Residual"] = ""
        return result

    def _build_footer_panels_placeholder_guard(self):
        self._footer_hbox = QHBoxLayout()
        self._footer_hbox.setContentsMargins(0, 20, 0, 0)
        res_frame = QFrame()
        res_frame.setFrameShape(QFrame.Shape.StyledPanel)
        res_layout = QVBoxLayout()
        res_layout.setContentsMargins(8, 8, 8, 8)
        tv_header_row = QHBoxLayout()
        self._lbl_tv_header = QLabel("Terminal Value", styleSheet=get_bold_style())
        tv_header_row.addWidget(self._lbl_tv_header)
        tv_header_row.addStretch()
        self.link_reverse_dcf = QPushButton("Reverse-DCF →")
        self.link_reverse_dcf.setStyleSheet(get_link_style())
        self.link_reverse_dcf.setCursor(Qt.CursorShape.PointingHandCursor)
        self.link_reverse_dcf.clicked.connect(self._open_reverse_dcf)
        tv_header_row.addWidget(self.link_reverse_dcf)
        res_layout.addLayout(tv_header_row)
        h_model = QHBoxLayout()
        h_model.addWidget(QLabel("Model:"))
        self.tv_model_combo = QComboBox()
        self.tv_model_combo.addItems(["Gordon Growth", "EBITDA Multiple", "Revenue Multiple", "H-Model"])
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
        h_dep = QHBoxLayout()
        h_dep.addWidget(QLabel("Dep. as % of CapEx:"))
        self.capex_dep_pct = QLineEdit("100.0%")
        self.capex_dep_pct.setStyleSheet(get_input_style())
        self.capex_dep_pct.setFixedWidth(60)
        self.capex_dep_pct.editingFinished.connect(self._recalculate)
        h_dep.addWidget(self.capex_dep_pct)
        res_layout.addLayout(h_dep)
        self._tv_panels: Dict[str, QWidget] = {}
        self._tv_outputs: Dict[str, Dict[str, QLabel]] = {}
        self._tv_inputs: Dict[str, Dict[str, QLineEdit]] = {}
        res_layout.addWidget(self._build_gordon_growth_panel())
        res_layout.addWidget(self._build_ebitda_multiple_panel())
        res_layout.addWidget(self._build_revenue_multiple_panel())
        res_layout.addWidget(self._build_h_model_panel())
        res_frame.setLayout(res_layout)
        self._apply_tv_model_visibility()
        bridge_widget = self._build_fv_bridge()
        self._footer_hbox.addWidget(bridge_widget, 1)
        res_frame.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)
        res_row = QHBoxLayout()
        res_row.addStretch(1)
        res_row.addWidget(res_frame)
        right_col = QVBoxLayout()
        right_col.addLayout(res_row)
        right_col.addStretch(1)
        self._footer_hbox.addLayout(right_col, 2)

    def _build_fv_bridge(self) -> QWidget:
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
        h_hl_hdr.addWidget(QLabel("FV Low"))
        h_hl_hdr.addSpacing(20)
        h_hl_hdr.addWidget(QLabel("FV High"))
        h_hl_hdr.addStretch()
        layout.addLayout(h_hl_hdr)
        h_hl_val = QHBoxLayout()
        hl_spacer2 = QLabel("")
        hl_spacer2.setFixedWidth(LABEL_COL_WIDTH)
        h_hl_val.addWidget(hl_spacer2)
        self.bridge_fv_high_label = QLabel("-")
        self.bridge_fv_low_label = QLabel("-")
        h_hl_val.addWidget(self.bridge_fv_low_label)
        h_hl_val.addSpacing(20)
        h_hl_val.addWidget(self.bridge_fv_high_label)
        h_hl_val.addStretch()
        layout.addLayout(h_hl_val)
        layout.addSpacing(14)
        self._lbl_sensitivity_header = QLabel("Sensitivity: Fair Value by WACC / LTGR", styleSheet=get_bold_style())
        layout.addWidget(self._lbl_sensitivity_header)
        layout.addWidget(self._build_sensitivity_table())
        layout.addStretch(1)
        widget.setLayout(layout)
        return widget

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
        model = self.tv_model_combo.currentText()
        final_idx = self._num_hist + self._num_proj - 1
        if final_idx < 0:
            return
        ltgr = self._get_ltgr()
        final_pvp = _read_label(self._calc_labels, self._row_idx.get("Present Value Period"), final_idx)
        residual_idx = self._headers.index("Residual") if "Residual" in self._headers else None
        residual_fcf = _read_label(self._calc_labels, self._row_idx.get("Free Cash Flow"), residual_idx) if residual_idx is not None else None
        final_fcf = _read_label(self._calc_labels, self._row_idx.get("Free Cash Flow"), final_idx)
        final_ebitda = _read_label(self._calc_labels, self._row_idx.get("EBITDA"), final_idx)
        final_revenue = _read_label(self._calc_labels, self._row_idx.get("Revenue"), final_idx)
        cap_rate = (wacc_val - ltgr) if (wacc_val is not None and ltgr is not None) else None
        def out(m: str, key: str, text: str):
            lbl = self._tv_outputs.get(m, {}).get(key)
            if lbl is not None:
                lbl.setText(text)
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
        revenue_mult = _parse_multiple(self._tv_inputs.get("Revenue Multiple", {}).get("multiple"))
        revenue_residual_value = _mul_strict(final_revenue, revenue_mult)
        revenue_pv_factor = ebitda_pv_factor
        revenue_pv_residual_value = _mul_strict(revenue_residual_value, revenue_pv_factor)
        out("Revenue Multiple", "revenue", _fmt_currency(final_revenue))
        out("Revenue Multiple", "multiple_out", f"{revenue_mult:.2f}x" if revenue_mult is not None else "-")
        out("Revenue Multiple", "residual_value", _fmt_currency(revenue_residual_value))
        out("Revenue Multiple", "pv_factor", f"{revenue_pv_factor:.2f}" if revenue_pv_factor is not None else "-")
        out("Revenue Multiple", "pv_residual_value", _fmt_currency(revenue_pv_residual_value))
        num_years = _parse_label_as_float(self._tv_inputs.get("H-Model", {}).get("num_years").text()) if self._tv_inputs.get("H-Model", {}).get("num_years") else None
        short_growth_text = self._tv_inputs.get("H-Model", {}).get("short_term_growth")
        short_growth = None
        if short_growth_text is not None:
            t = short_growth_text.text().strip().replace("%", "")
            try:
                short_growth = float(t) / 100.0
            except ValueError:
                short_growth = None
        h_residual_value = None
        if (final_fcf is not None and num_years is not None and short_growth is not None and ltgr is not None and cap_rate not in (None, 0)):
            h_residual_value = (((final_fcf * num_years) / 2.0) * (short_growth - ltgr) / cap_rate) + (gg_residual_value if gg_residual_value is not None else 0.0)
        h_pv_factor = gg_pv_factor
        h_pv_residual_value = _mul_strict(h_residual_value, h_pv_factor)
        out("H-Model", "cash_flow", _fmt_currency(final_fcf))
        out("H-Model", "cap_rate", _fmt_pct(cap_rate))
        out("H-Model", "residual_value", _fmt_currency(h_residual_value))
        out("H-Model", "pv_factor", f"{h_pv_factor:.2f}" if h_pv_factor is not None else "-")
        out("H-Model", "pv_residual_value", _fmt_currency(h_pv_residual_value))

    def _render_shared_dcf_rows(self, calc: dict):
        """Render build_dcf()['rows'] into the existing PyQt table."""
        rows = calc.get("rows", {}) or {}
        is_hist = calc.get("is_hist", []) or []

        key_to_label = {
            "revenue": "Revenue",
            "revenue_growth": "Revenue Growth",
            "cogs": "Cost of Goods Sold",
            "gross_profit": "Gross Profit",
            "gp_margin": "Gross Profit Margin",
            "operating_expenses": "Operating Expenses",
            "ebitda": "EBITDA",
            "ebitda_margin": "EBITDA Margin",
            "depreciation": "Depreciation",
            "amortization": "Amortization",
            "net_interest": "Net Interest Expense",
            "ebit": "EBIT",
            "ebit_margin": "EBIT Margin",
            "sbc": "Stock-Based Compensation",
            "other_adj": "+Other Adjustments",
            "taxes": "Taxes",
            "nopat": "Net Operating Profit After Tax (NOPAT)",
            "plus_dep": "Plus: Depreciation",
            "less_nwc": "Less: Increase/(Decrease) in DFCFNWC",
            "less_capex": "Less: Capital Expenditures (CapEx)",
            "less_other_adj": "Less: Other Adjustments",
            "fcf": "Free Cash Flow",
            "ppa": "Partial Period Adjustment",
            "pvp": "Present Value Period",
            "pvf": "Present Value Factor",
            "pv_fcf": "Present Value of Free Cash Flows",
        }

        pct_keys = {
            "revenue_growth",
            "gp_margin",
            "ebitda_margin",
            "ebit_margin",
        }
        historical_blank_keys = {"ppa", "pvp", "pvf", "pv_fcf"}

        for row_key, row_values in rows.items():
            row_label = key_to_label.get(row_key)
            if row_label is None or not isinstance(row_values, dict):
                continue

            for data_idx, period in enumerate(self._headers):
                value = row_values.get(period)

                if (
                    data_idx < len(is_hist)
                    and is_hist[data_idx]
                    and row_key in historical_blank_keys
                ):
                    text = ""
                elif value is None:
                    text = "-"
                elif row_key in pct_keys:
                    text = _fmt_pct(value)
                elif row_key == "ppa":
                    text = f"{value:.4f}"
                elif row_key == "pvp":
                    text = f"{value:.2f}"
                elif row_key == "pvf":
                    text = f"{value:.4f}"
                else:
                    text = _fmt_currency(value)

                # _set() naturally skips cells represented by QLineEdit,
                # including projected Less: Other Adjustments and the
                # Residual Amortization input.
                self._set(row_label, data_idx, text)

        # Keep the internal row key as "EBITDA" for compatibility with
        # Reverse-DCF and other desktop code, but present the correct label.
        ebitda_idx = self._row_idx.get("EBITDA")
        ebitda_label = self._row_labels.get(ebitda_idx)
        if ebitda_label is not None:
            ebitda_label.setText("Adjusted EBITDA")

        # Web displays the Projection Module P&L plug only in FCFE.
        other_adj_idx = self._row_idx.get("+Other Adjustments")
        if other_adj_idx is not None:
            visible = bool(calc.get("is_fcfe"))
            row_label_widget = self._row_labels.get(other_adj_idx)
            if row_label_widget is not None:
                row_label_widget.setVisible(visible)

            for widget in self._calc_labels.get(other_adj_idx, {}).values():
                widget.setVisible(visible)

            for widget in self._input_fields.get(other_adj_idx, {}).values():
                widget.setVisible(visible)

    def _render_shared_terminal_values(self):
        """Render shared terminal-value outputs into existing TV panels."""
        calc = self._shared_calc or {}
        tv = calc.get("tv", {}) or {}

        output_aliases = {
            "cashflow": "cash_flow",
            "cashflowvalue": "cash_flow",
            "residualcashflow": "cash_flow",
            "metric": "metric",
            "metricvalue": "metric",
            "multiple": "multiple",
            "caprate": "cap_rate",
            "capitalizationrate": "cap_rate",
            "residualvalue": "residual_value",
            "pvfactor": "pv_factor",
            "presentvaluefactor": "pv_factor",
            "pvresidual": "pv_residual",
            "pvresidualvalue": "pv_residual",
            "discountedresidualvalue": "pv_residual",
        }

        for model, model_values in tv.items():
            outputs = self._tv_outputs.get(model, {}) or {}
            if not isinstance(model_values, dict):
                continue

            for output_key, widget in outputs.items():
                if widget is None:
                    continue

                semantic_key = output_key if output_key in model_values else None
                if semantic_key is None:
                    normalized = (
                        str(output_key)
                        .lower()
                        .replace("_", "")
                        .replace(" ", "")
                        .replace("-", "")
                    )
                    semantic_key = output_aliases.get(normalized)

                if semantic_key is None:
                    continue

                value = model_values.get(semantic_key)
                if value is None:
                    widget.setText("-")
                elif semantic_key == "cap_rate":
                    widget.setText(f"{value * 100:.2f}%")
                elif semantic_key == "pv_factor":
                    widget.setText(f"{value:.4f}")
                elif semantic_key == "multiple":
                    widget.setText(f"{value:.2f}x")
                else:
                    widget.setText(_fmt_currency(value))

    def _sf_get(self, key: str, period_label: str) -> Optional[float]:
        return self._get_subject_financials(key, period_label)

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

    def _recalculate(self):
        from Canneberge.Calculations.dcf import (
            build_dcf,
            calculate_ppa,
            normalise_rate,
        )

        inputs = self.get_project_inputs()

        # Home Basis of Value remains authoritative.
        if getattr(inputs, "basis_of_value", None) == "Equity Value":
            new_cf = "FCFE"
        elif getattr(inputs, "basis_of_value", None) == "Business Enterprise Value":
            new_cf = "FCFF"
        else:
            new_cf = self._cash_flows_to

        if self._last_cf_mode is not None and new_cf != self._last_cf_mode:
            # Save the outgoing cash-flow mode's terminal multiples.
            for model in ("EBITDA Multiple", "Revenue Multiple"):
                widget = self._tv_inputs.get(model, {}).get("multiple")
                if widget is not None:
                    self._per_cf_tv_multiples[self._last_cf_mode][model] = (
                        widget.text()
                    )

            # Restore the incoming mode's multiples.
            for model in ("EBITDA Multiple", "Revenue Multiple"):
                widget = self._tv_inputs.get(model, {}).get("multiple")
                if widget is None:
                    continue

                saved = self._per_cf_tv_multiples[new_cf][model]
                widget.blockSignals(True)
                widget.setText(saved if saved is not None else "")
                widget.blockSignals(False)

        self._cash_flows_to = new_cf
        self._last_cf_mode = new_cf

        self._rebuild_table_if_needed()

        historical_periods = list(inputs.historical_period_columns)
        projection_periods = list(inputs.projection_period_columns)
        is_fcfe = self._cash_flows_to == "FCFE"
        discount_rate = self._get_discount_rate()

        # Cash-flow Other Adjustments are user inputs and are separate from
        # Projection Module +Other Adjustments.
        other_adj_inputs: Dict[str, str] = {}
        less_other_adj_idx = self._row_idx.get("Less: Other Adjustments")
        for data_idx, period in enumerate(self._headers):
            widget = self._input_fields.get(
                less_other_adj_idx, {}
            ).get(data_idx)
            if widget is not None:
                other_adj_inputs[period] = widget.text()

        # Residual amortization remains a user input.
        residual_amortization = ""
        amortization_idx = self._row_idx.get("Amortization")
        if "Residual" in self._headers:
            residual_idx = self._headers.index("Residual")
            residual_widget = self._input_fields.get(
                amortization_idx, {}
            ).get(residual_idx)
            if residual_widget is not None:
                residual_amortization = residual_widget.text()

        tv_inputs = {
            model: {
                key: widget.text()
                for key, widget in fields.items()
            }
            for model, fields in self._tv_inputs.items()
        }
        tv_model = self.tv_model_combo.currentText()

        # Same signed convention as web:
        # positive interest income, negative interest expense.
        net_interest_by_period: Dict[str, Optional[float]] = {}
        for period in self._headers:
            if period in historical_periods:
                interest_income = self._sf_get("interest_income", period)
                interest_expense = self._sf_get("interest_expense", period)

                if interest_income is None and interest_expense is None:
                    net_interest_by_period[period] = None
                else:
                    net_interest_by_period[period] = (
                        (interest_income or 0.0)
                        - abs(interest_expense or 0.0)
                    )
            elif period in projection_periods:
                try:
                    interest_cost = self._get_projected_interest_expense(period)
                except Exception:
                    interest_cost = None

                net_interest_by_period[period] = (
                    -abs(interest_cost)
                    if interest_cost is not None
                    else None
                )

        changes_in_nwc: Dict[str, Optional[float]] = {}
        for period in self._headers:
            try:
                changes_in_nwc[period] = self._get_nwc_change(period)
            except Exception:
                changes_in_nwc[period] = None

        projection_data = self._get_projection_data()

        def sf(key: str, period: str) -> Optional[float]:
            # Projection Module pre-tax plug lives on ProjectionData, not on
            # Subject Financials. Same source web reads (pd.other_adj).
            if key == "other_adj":
                if period in projection_periods:
                    other_adj_map = getattr(projection_data, "other_adj", {}) or {}
                    return other_adj_map.get(period)
                return None
            return self._sf_get(key, period)

        calc = build_dcf(
            historical_period_columns=historical_periods,
            projection_period_columns=projection_periods,
            sf=sf,
            changes_in_nwc=changes_in_nwc,
            net_interest_by_period=net_interest_by_period,
            other_adj_inputs=other_adj_inputs,
            residual_amortization=residual_amortization,
            tax_rate=normalise_rate(
                getattr(inputs, "subject_tax_rate", None)
            ),
            discount_rate=discount_rate,
            ltgr=self._get_ltgr(),
            dep_pct_of_capex=self._get_dep_pct_of_capex(),
            ppa=calculate_ppa(
                inputs.next_fiscal_year,
                inputs.valuation_date,
            ),
            is_fcfe=is_fcfe,
            tv_model=tv_model,
            tv_inputs=tv_inputs,
            bridge_other_adj=self.bridge_other_adj_input.text(),
        )

        # Required by shared fv_for_assumptions() during sensitivity.
        calc["tv_model"] = tv_model
        calc["tv_inputs"] = tv_inputs
        self._shared_calc = calc

        self.lbl_client.setText(inputs.client)
        self.lbl_subject.setText(inputs.subject_company_name)
        self.lbl_date.setText(f"As of {inputs.valuation_date}")

        rate_label = "Ke" if is_fcfe else "WACC"
        pct_str = (
            f"{discount_rate * 100:.2f}%"
            if discount_rate is not None
            else "N/A%"
        )
        if self.pv_factor_row_label is not None:
            self.pv_factor_row_label.setText(
                f"Present Value Factor @ {rate_label} = {pct_str}"
            )

        fye_years = self._compute_fye_years(inputs)
        for label, label_widget in self._fye_labels.items():
            label_widget.setText(fye_years.get(label, ""))

        self._render_shared_dcf_rows(calc)
        self._update_ebit_row_label()
        self._apply_net_int_proj_visibility()
        self._render_shared_terminal_values()
        self._populate_fv_bridge(inputs)

        # Existing table renderer remains, but its evaluator is redirected
        # to shared fv_for_assumptions() by the next patch.
        self._populate_sensitivity_table(inputs)

    def refresh(self):
        self._recalculate()

    def _update_ebit_row_label(self):
        is_fcfe = (self._cash_flows_to == "FCFE")
        new_text = "EBT" if is_fcfe else "EBIT"
        if self._ebit_grid_row is not None:
            lbl_item = self.table_grid.itemAtPosition(self._ebit_grid_row, 0)
            if lbl_item is not None and lbl_item.widget() is not None:
                lbl_item.widget().setText(new_text)
        if self._ebit_margin_grid_row is not None:
            lbl_item = self.table_grid.itemAtPosition(self._ebit_margin_grid_row, 0)
            if lbl_item is not None and lbl_item.widget() is not None:
                lbl_item.widget().setText(f"{new_text} Margin")
        nopat_idx = self._row_idx.get("Net Operating Profit After Tax (NOPAT)")
        nopat_lbl = self._row_labels.get(nopat_idx)
        if nopat_lbl is not None:
            nopat_lbl.setText(
                "Net Income" if is_fcfe
                else "Net Operating Profit After Tax (NOPAT)"
            )

    def _apply_net_int_proj_visibility(self):
        """Show Net Interest row only for FCFE. Values come from populate methods."""
        if self._net_int_grid_row is None:
            return
        is_fcff = (self._cash_flows_to == "FCFF")
        show = not is_fcff
        lbl_item = self.table_grid.itemAtPosition(self._net_int_grid_row, 0)
        if lbl_item is not None and lbl_item.widget() is not None:
            lbl_item.widget().setVisible(show)
        for data_idx in range(len(self._headers)):
            grid_col = self._grid_col(data_idx)
            cell_item = self.table_grid.itemAtPosition(self._net_int_grid_row, grid_col)
            if cell_item is None:
                continue
            widget = cell_item.widget()
            if widget is None:
                continue
            widget.setVisible(show)

    def _populate_revenue_and_growth(self, inputs):
        for data_idx, label in enumerate(self._headers):
            if label == "Residual":
                self._set("Revenue Growth", data_idx, "")
                continue
            rev = self._sf_get("revenue", label)
            self._set_currency("Revenue", data_idx, rev)
            if data_idx == 0:
                self._set("Revenue Growth", data_idx, "")
                continue
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

    def _get_net_interest_value(self, data_idx: int) -> Optional[float]:
        label = self._headers[data_idx]
        int_exp = self._sf_get("interest_expense", label)
        int_inc = self._sf_get("interest_income", label)

        if int_exp is None and int_inc is None:
            return None

        exp_abs = abs(int_exp) if int_exp is not None else 0.0
        inc_val = int_inc if int_inc is not None else 0.0
        return inc_val - exp_abs

    def _populate_dep_amort_net_int(self):
        for data_idx, label in enumerate(self._headers):
            if self._is_historical[data_idx]:
                dep = self._sf_get("d&a_for_ebitda", label)
                if dep is None:
                    dep = self._sf_get("depreciation", label)
                if dep is None:
                    dep = self._sf_get("depreciation_amortization", label)
                amort = self._sf_get("amortization", label)
                if dep is not None and amort is None:
                    amort = 0.0

                net_int = self._get_net_interest_value(data_idx)

                self._set_currency("Depreciation", data_idx, dep)
                self._set_currency("Amortization", data_idx, amort)
                self._set_currency("Net Interest Expense", data_idx, net_int)
            else:
                if label == "Residual":
                    continue
                pd = self._get_projection_data()
                self._set_currency("Depreciation", data_idx, pd.da.get(label))
                self._set_currency("Amortization", data_idx, pd.other_amort.get(label))

                net_int = self._get_net_interest_value(data_idx)
                self._set_currency("Net Interest Expense", data_idx, net_int)

    def _populate_ebit_and_ebit_margin(self):
        for data_idx, label in enumerate(self._headers):
            if self._is_historical[data_idx]:
                ebitda = self._sf_get("ebitda", label)
                dep = self._sf_get("depreciation", label)
                if dep is None:
                    dep = self._sf_get("d&a_for_ebitda", label)
                amort = self._sf_get("amortization", label)
            else:
                pd = self._get_projection_data()
                ebitda = pd.ebitda.get(label)
                dep = pd.da.get(label)
                amort = pd.other_amort.get(label)

            if label == "Residual":
                continue

            net_int = self._get_net_interest_value(data_idx)

            if ebitda is None or dep is None:
                ebit_or_ebt = None
            elif self._cash_flows_to == "FCFF":
                ebit_or_ebt = ebitda - dep - (amort or 0.0)
            else:
                # FCFE Mode: EBT = EBITDA - Dep - Amort + NetInterest (where NetInterest is negative for expense)
                ebit_or_ebt = ebitda - dep - (amort or 0.0) + (net_int or 0.0)

            self._set_currency("EBIT", data_idx, ebit_or_ebt)
            rev = self._sf_get("revenue", label)
            self._set_pct("EBIT Margin", data_idx, _safe_div(ebit_or_ebt, rev))
    def _populate_sbc(self):
        for data_idx, label in enumerate(self._headers):
            if label == "Residual":
                continue
            if self._is_historical[data_idx]:
                sbc = self._sf_get("stock_based_compensation", label)
            else:
                pd = self._get_projection_data()
                sbc = pd.sbc.get(label)
            self._set_currency("Stock-Based Compensation", data_idx, sbc)

    def _populate_taxes(self, inputs):
        tax_rate = inputs.subject_tax_rate
        ebit_idx = self._row_idx.get("EBIT")
        sbc_idx  = self._row_idx.get("Stock-Based Compensation")
        for data_idx, label in enumerate(self._headers):
            if self._is_historical[data_idx]:
                self._set_currency("Taxes", data_idx, self._sf_get("taxes", label))
            else:
                ebit_val = _read_label(self._calc_labels, ebit_idx, data_idx)
                sbc_val  = _read_label(self._calc_labels, sbc_idx, data_idx)
                if ebit_val is not None and tax_rate is not None:
                    # SBC is a pre-tax economic cost — subtract before applying
                    # statutory rate so the tax shield is captured. FCFF NOPAT
                    # and FCFE Net Income both bottom out from EBIT-after-SBC.
                    base = ebit_val - (sbc_val or 0.0)
                    self._set_currency("Taxes", data_idx, base * tax_rate)
                else:
                    self._set("Taxes", data_idx, "-")

    def _populate_nopat(self):
        ebit_idx  = self._row_idx.get("EBIT")
        sbc_idx   = self._row_idx.get("Stock-Based Compensation")
        taxes_idx = self._row_idx.get("Taxes")
        is_fcfe = (self._cash_flows_to == "FCFE")
        for data_idx, label in enumerate(self._headers):
            if label == "Residual":
                continue
            if is_fcfe:
                # FCFE: bottom-line Net Income. Analyst-wins on MS-covered
                # projection periods (comes through Subject Financials'
                # get_metric_value, which honors pd.net_income override).
                # Historicals get SF's computed NI from the IS waterfall.
                ni = self._sf_get("net_income", label)
                self._set_currency(
                    "Net Operating Profit After Tax (NOPAT)", data_idx, ni
                )
            else:
                # FCFF: NOPAT = (EBIT − SBC) × (1 − t), computed as
                # (EBIT − SBC) − Taxes since Taxes was already built on
                # the post-SBC base in _populate_taxes.
                ebit_val = _read_label(self._calc_labels, ebit_idx, data_idx)
                sbc_val  = _read_label(self._calc_labels, sbc_idx, data_idx)
                tax_val  = _read_label(self._calc_labels, taxes_idx, data_idx)
                if ebit_val is not None and tax_val is not None:
                    base = ebit_val - (sbc_val or 0.0)
                    self._set_currency(
                        "Net Operating Profit After Tax (NOPAT)",
                        data_idx,
                        base - tax_val,
                    )
                else:
                    self._set(
                        "Net Operating Profit After Tax (NOPAT)", data_idx, "-"
                    )

    def _populate_capex_other_nwc(self):
        for data_idx, label in enumerate(self._headers):
            if self._is_historical[data_idx]:
                dep_val = self._sf_get("d&a_for_ebitda", label)
                if dep_val is None:
                    dep_val = self._sf_get("depreciation", label)
                if dep_val is None:
                    dep_val = self._sf_get("depreciation_amortization", label)
                amort_val = self._sf_get("amortization", label)
                plus_dep = None
                if dep_val is not None or amort_val is not None:
                    plus_dep = (dep_val or 0.0) + (amort_val or 0.0)
            else:
                pd = self._get_projection_data()
                da_val = pd.da.get(label)
                oa_val = pd.other_amort.get(label)
                plus_dep = None
                if da_val is not None or oa_val is not None:
                    plus_dep = (da_val or 0.0) + (oa_val or 0.0)
            self._set_currency("Plus: Depreciation", data_idx, plus_dep)
            nwc_change_val = None
            if hasattr(self, '_get_nwc_change') and self._get_nwc_change is not None:
                result = self._get_nwc_change(label if callable(self._get_nwc_change) and not isinstance(self._get_nwc_change, dict) else label)
                if isinstance(result, dict):
                    nwc_change_val = result.get(label)
                else:
                    nwc_change_val = result
            if nwc_change_val is not None:
                self._set_currency("Less: Increase/(Decrease) in DFCFNWC", data_idx, nwc_change_val)
            else:
                nwc_change = self._get_nwc_change(label)
                self._set_currency("Less: Increase/(Decrease) in DFCFNWC", data_idx, nwc_change)
            if self._is_historical[data_idx]:
                capex = self._sf_get("capex", label)
            else:
                capex = self._get_projection_data().capex.get(label)
            self._set_currency("Less: Capital Expenditures (CapEx)", data_idx, capex)
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
        nopat_idx = self._row_idx.get("Net Operating Profit After Tax (NOPAT)")
        plus_dep_idx = self._row_idx.get("Plus: Depreciation")
        nwc_idx = self._row_idx.get("Less: Increase/(Decrease) in DFCFNWC")
        capex_idx = self._row_idx.get("Less: Capital Expenditures (CapEx)")
        other_idx = self._row_idx.get("Less: Other Adjustments")
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
        else:
            pass

        if ppa is not None and ppa <= 0:
            ppa = None

        fcf_idx = self._row_idx.get("Free Cash Flow")
        prior_pvp: Optional[float] = None

        for data_idx, label in enumerate(self._headers):
            if self._is_historical[data_idx]:
                continue
            if label == "Residual":
                self._set("Partial Period Adjustment", data_idx, "")
                self._set("Present Value Period", data_idx, "")
                self._set("Present Value Factor", data_idx, "")
                self._set("Present Value of Free Cash Flows", data_idx, "")
                continue

            if label == "NFY":
                if ppa is not None:
                    self._set("Partial Period Adjustment", data_idx, f"{ppa:.4f}")
                else:
                    self._set("Partial Period Adjustment", data_idx, "-")
            else:
                self._set("Partial Period Adjustment", data_idx, "")

            if label == "NFY":
                pvp = (ppa / 2.0) if ppa is not None else None
            elif label == "NFY+1":
                pvp = (prior_pvp * 2.0 + 0.5) if prior_pvp is not None else None
            else:
                pvp = (prior_pvp + 1.0) if prior_pvp is not None else None

            if pvp is not None:
                self._set("Present Value Period", data_idx, f"{pvp:.2f}")
            else:
                self._set("Present Value Period", data_idx, "-")

            prior_pvp = pvp

            pvf_full: Optional[float] = None
            if pvp is not None and wacc_val is not None and wacc_val > 0:
                pvf_full = 1.0 / ((1.0 + wacc_val) ** pvp)
                self._set("Present Value Factor", data_idx, f"{pvf_full:.2f}")
            else:
                self._set("Present Value Factor", data_idx, "-")

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
        container = QWidget()
        grid = QGridLayout()
        grid.setHorizontalSpacing(0)
        grid.setVerticalSpacing(4)
        grid.setColumnMinimumWidth(1, 16)
        wacc_now = self._get_discount_rate()
        ltgr_now = self._get_ltgr()
        wacc_now = wacc_now if wacc_now is not None else 0.10
        ltgr_now = ltgr_now if ltgr_now is not None else 0.03
        self._lbl_wacc_ltgr_corner = QLabel("Discount Rate \\ LTGR", styleSheet=get_bold_style())
        grid.addWidget(self._lbl_wacc_ltgr_corner, 0, 0)
        DATA_COL_WIDTH = 78
        FIRST_DATA_COL = 2
        self.sens_wacc_inputs = []
        self._sens_wacc_auto_text = []
        for col, offset in enumerate([0.02, 0.01, 0.0, -0.01, -0.02]):
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
        for row, offset in enumerate([0.02, 0.01, 0.0, -0.01, -0.02]):
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

    def _compute_fv_for_assumptions(
        self,
        wacc_override: float,
        ltgr_override: float,
        ga_override: Optional[float] = None,
        h_override: Optional[float] = None,
    ) -> Optional[float]:
        shared_calc = getattr(self, "_shared_calc", None)
        if shared_calc is not None:
            from Canneberge.Calculations.dcf import fv_for_assumptions

            _locals = locals()
            wacc_arg = None
            ltgr_arg = None

            for _name in ("wacc", "wacc_override", "wacc_val"):
                if _name in _locals:
                    wacc_arg = _locals[_name]
                    break

            for _name in ("ltgr", "ltgr_override", "ltgr_val"):
                if _name in _locals:
                    ltgr_arg = _locals[_name]
                    break

            return fv_for_assumptions(wacc_arg, ltgr_arg, shared_calc)
        """
        Pure mathematical WACC/LTGR override FV calculation.
        Executes entirely in memory with zero Qt widget mutation.
        """
        from Canneberge.Calculations.valuation_surface import evaluate_dcf_fv

        final_idx = self._num_hist + self._num_proj - 1
        if final_idx < 0:
            return None

        # 1. Sum explicit PV FCFs
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

        # 2. Extract final projected year base metrics
        pvp_idx = self._row_idx.get("Present Value Period")
        final_pvp = _read_label(self._calc_labels, pvp_idx, final_idx)
        final_fcf = _read_label(self._calc_labels, self._row_idx.get("Free Cash Flow"), final_idx)
        final_revenue = _read_label(self._calc_labels, self._row_idx.get("Revenue"), final_idx)
        final_capex = _read_label(self._calc_labels, self._row_idx.get("Less: Capital Expenditures (CapEx)"), final_idx)

        # 3. Extract inputs
        inputs = self.get_project_inputs()
        model = self.tv_model_combo.currentText()

        other_adj_bridge_text = self.bridge_other_adj_input.text().strip()
        other_adj_bridge = _parse_label_as_float(other_adj_bridge_text) or 0.0

        # H-Model params (allow overrides from 3D surface sliders)
        num_years = h_override if h_override is not None else (
            _parse_label_as_float(self._tv_inputs.get("H-Model", {}).get("num_years").text())
            if self._tv_inputs.get("H-Model", {}).get("num_years") else 5.0
        )
        short_growth_text = self._tv_inputs.get("H-Model", {}).get("short_term_growth")
        short_growth = ga_override if ga_override is not None else (
            _parse_pct_field(short_growth_text.text()) if short_growth_text else 0.20
        )

        # Multiples
        ebitda_m = _parse_multiple(self._tv_inputs.get("EBITDA Multiple", {}).get("multiple"))
        rev_m    = _parse_multiple(self._tv_inputs.get("Revenue Multiple", {}).get("multiple"))
        final_ebitda = _read_label(self._calc_labels, self._row_idx.get("EBITDA"), final_idx)

        # Real, pipeline-computed Residual FCF, rescaled for this LTGR
        # override — same real number _populate_terminal_value() itself
        # anchors on, not an approximation. Used for both Gordon Growth
        # and H-Model (both depend on residual_fcf); Multiple-based
        # models don't use it at all.
        residual_idx = self._headers.index("Residual") if "Residual" in self._headers else None
        residual_fcf = (
            _read_label(self._calc_labels, self._row_idx.get("Free Cash Flow"), residual_idx)
            if residual_idx is not None else None
        )
        current_ltgr = self._get_ltgr()
        if residual_fcf is not None and current_ltgr is not None and (1.0 + current_ltgr) != 0:
            residual_fcf = residual_fcf * (1.0 + ltgr_override) / (1.0 + current_ltgr)

        if model == "Gordon Growth":
            cap_rate = (wacc_override - ltgr_override) if wacc_override is not None else None
            if (
                residual_fcf is not None
                and cap_rate is not None
                and cap_rate > 0
                and final_pvp is not None
                and any_val
            ):
                residual_value = residual_fcf / cap_rate
                pv_factor = 1.0 / ((1.0 + wacc_override) ** final_pvp)
                return sum_pv_fcf + (residual_value * pv_factor) + other_adj_bridge
            return None

        return evaluate_dcf_fv(
            wacc=wacc_override,
            ltgr=ltgr_override,
            sum_pv_explicit_fcf=(sum_pv_fcf if any_val else None),
            final_pvp=final_pvp,
            final_fcf=final_fcf,
            final_revenue=final_revenue,
            final_capex=final_capex,
            dep_pct_of_capex=self._get_dep_pct_of_capex(),
            tax_rate=inputs.subject_tax_rate,
            dfcfnwc_residual=self._get_nwc_change("Residual"),
            other_adj_residual=0.0,
            other_adj_bridge=other_adj_bridge,
            is_fcfe=(self._cash_flows_to == "FCFE"),
            final_net_interest=_read_label(self._calc_labels, self._row_idx.get("Net Interest Expense"), final_idx),
            model=model,
            h_num_years=num_years,
            h_short_growth=short_growth,
            ebitda_mult=ebitda_m,
            revenue_mult=rev_m,
            final_ebitda=final_ebitda,
            residual_fcf_override=residual_fcf,
        )

    def _compute_fv_base_for(self, wacc_override: float, ltgr_text_override: str) -> Optional[float]:
        shared_calc = getattr(self, "_shared_calc", None)
        if shared_calc is not None:
            from Canneberge.Calculations.dcf import (
                fv_for_assumptions,
                normalise_rate,
                parse_pct,
            )

            return fv_for_assumptions(
                normalise_rate(wacc_override),
                parse_pct(ltgr_text_override),
                shared_calc,
            )
        """Legacy wrapper — sensitivity table still uses this signature."""
        try:
            ltgr_val = float(ltgr_text_override.strip().replace("%", "")) / 100.0
        except ValueError:
            return None
        return self._compute_fv_for_assumptions(wacc_override, ltgr_val)

    def _populate_sensitivity_table(self, inputs):
        if not hasattr(self, "sens_value_labels"):
            return
        wacc_now = self._get_discount_rate()
        ltgr_now = self._get_ltgr()

        rate_label = "Ke" if self._cash_flows_to == "FCFE" else "WACC"
        if hasattr(self, "_lbl_sensitivity_header"):
            self._lbl_sensitivity_header.setText(f"Sensitivity: Fair Value by {rate_label} / LTGR")

        if wacc_now is not None:
            for col, offset in enumerate([0.02, 0.01, 0.0, -0.01, -0.02]):
                inp = self.sens_wacc_inputs[col]
                if inp.text() == self._sens_wacc_auto_text[col]:
                    new_text = f"{(wacc_now + offset) * 100:.4f}%"
                    inp.setText(new_text)
                    self._sens_wacc_auto_text[col] = new_text

        if ltgr_now is not None:
            for row, offset in enumerate([0.02, 0.01, 0.0, -0.01, -0.02]):
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

        high_coord = (1, 3)
        low_coord  = (3, 1)
        center_coord = (2, 2)

        # 1. First pass: evaluate pure math grid
        grid_fvs = {}
        valid_fvs = []
        for row in range(5):
            for col in range(5):
                w = wacc_vals[col]
                l = ltgr_vals[row]
                if w is not None and l is not None and w > 0:
                    fv = self._compute_fv_for_assumptions(w, l)
                    grid_fvs[(row, col)] = fv
                    if fv is not None and fv > 0:
                        valid_fvs.append(fv)
                else:
                    grid_fvs[(row, col)] = None

        min_fv = min(valid_fvs) if valid_fvs else 0.0
        max_fv = max(valid_fvs) if valid_fvs else 0.0
        t = theme_manager.current

        # 2. Second pass: display formatted text + RGBA Heatmap tint
        for row in range(5):
            for col in range(5):
                lbl = self.sens_value_labels[row][col]
                fv = grid_fvs.get((row, col))

                if fv is None:
                    lbl.setText("-")
                    lbl.setStyleSheet("")
                    continue

                lbl.setText(_fmt_currency(fv))

                # Normalize range 0.0 (Lowest = Red) to 1.0 (Highest = Green)
                if max_fv > min_fv:
                    norm = (fv - min_fv) / (max_fv - min_fv)
                else:
                    norm = 0.5

                if norm < 0.5:
                    # Interpolate Red -> Muted Gray
                    ratio = norm / 0.5
                    r = int(211 * (1 - ratio) + 120 * ratio)
                    g = int(47 * (1 - ratio) + 120 * ratio)
                    b = int(47 * (1 - ratio) + 120 * ratio)
                    alpha = 0.35 * (1 - ratio) + 0.1 * ratio
                else:
                    # Interpolate Muted Gray -> Soft Green
                    ratio = (norm - 0.5) / 0.5
                    r = int(120 * (1 - ratio) + 46 * ratio)
                    g = int(120 * (1 - ratio) + 125 * ratio)
                    b = int(120 * (1 - ratio) + 50 * ratio)
                    alpha = 0.1 * (1 - ratio) + 0.35 * ratio

                bg_color = f"rgba({r}, {g}, {b}, {alpha:.2f})"
                is_bold = (row, col) in (high_coord, low_coord, center_coord)
                weight_css = "font-weight: bold;" if is_bold else ""
                text_color = f"color: {t.bold_text if is_bold else t.default_text};"
                border_css = f"border: 1px solid {t.emphasis_border};" if (row, col) == center_coord else ""

                lbl.setStyleSheet(f"background-color: {bg_color}; {weight_css} {text_color} {border_css} padding: 2px 4px; border-radius: 3px;")

        self.bridge_fv_high_label.setText(
            self.sens_value_labels[high_coord[0]][high_coord[1]].text()
        )
        self.bridge_fv_low_label.setText(
            self.sens_value_labels[low_coord[0]][low_coord[1]].text()
        )

    def _populate_fv_bridge(self, inputs):
        calc = getattr(self, "_shared_calc", None) or {}

        sum_pv_fcf = calc.get("sum_pv_fcf")
        pv_residual = calc.get("pv_residual")
        fv_base = calc.get("fv_base")

        self.bridge_sum_pv_label.setText(_fmt_currency(sum_pv_fcf))
        self.bridge_disc_residual_label.setText(_fmt_currency(pv_residual))
        self.bridge_fv_base_label.setText(_fmt_currency(fv_base))

        is_fcff = self._cash_flows_to == "FCFF"
        self.bridge_fv_base_row_label.setText(
            "Fair Value of Business Enterprise (Base):"
            if is_fcff
            else "Fair Value of Equity (Base):"
        )

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
        final_capex = final("Less: Capital Expenditures (CapEx)")
        final_revenue = final("Revenue")
        capex_ratio = _safe_div(final_capex, final_revenue)
        residual_capex = revenue * capex_ratio if (revenue is not None and capex_ratio is not None) else None
        self._set_currency("Less: Capital Expenditures (CapEx)", data_idx, residual_capex)
        dep_pct = self._get_dep_pct_of_capex()
        depreciation = residual_capex * dep_pct if (residual_capex is not None and dep_pct is not None) else None
        self._set_currency("Depreciation", data_idx, depreciation)
        amort_idx = self._row_idx.get("Amortization")
        amort_inp = self._input_fields.get(amort_idx, {}).get(data_idx)
        amortization = _parse_label_as_float(amort_inp.text()) if amort_inp is not None else None
        total_da_addback = None
        if depreciation is not None or amortization is not None:
            total_da_addback = (depreciation or 0.0) + (amortization or 0.0)
        self._set_currency("Plus: Depreciation", data_idx, total_da_addback)
        net_interest = None
        if is_fcfe:
            net_interest = grow(final("Net Interest Expense"))
            self._set_currency("Net Interest Expense", data_idx, net_interest)
        if ebitda is None or depreciation is None:
            ebit_or_ebt = None
        elif is_fcfe:
            ebit_or_ebt = None if net_interest is None else (
                ebitda - depreciation - (amortization or 0.0) + net_interest
            )
        else:
            ebit_or_ebt = ebitda - depreciation - (amortization or 0.0)
        self._set_currency("EBIT", data_idx, ebit_or_ebt)
        self._set_pct("EBIT Margin", data_idx, _safe_div(ebit_or_ebt, revenue))
        # Residual SBC — grow with revenue, same convention as D&A/CapEx
        residual_sbc = grow(final("Stock-Based Compensation"))
        self._set_currency("Stock-Based Compensation", data_idx, residual_sbc)

        # Taxes on EBIT-after-SBC (or EBT-after-SBC for FCFE)
        base_for_tax = None
        if ebit_or_ebt is not None:
            base_for_tax = ebit_or_ebt - (residual_sbc or 0.0)
        taxes = base_for_tax * tax_rate if (base_for_tax is not None and tax_rate is not None) else None
        self._set_currency("Taxes", data_idx, taxes)

        if is_fcfe:
            # Grow last explicit NI with LTGR — matches how Revenue/EBITDA
            # residualize, keeps FCFE bottom line reader-consistent with
            # the analyst-anchored NFY/NFY+1/NFY+2 values that seeded it.
            nopat = grow(final("Net Operating Profit After Tax (NOPAT)"))
        else:
            nopat = (base_for_tax - (taxes or 0.0)) if base_for_tax is not None else None
        self._set_currency("Net Operating Profit After Tax (NOPAT)", data_idx, nopat)
        dfcfnwc = self._get_nwc_change("Residual")
        self._set_currency("Less: Increase/(Decrease) in DFCFNWC", data_idx, dfcfnwc)
        other_adj_idx = self._row_idx.get("Less: Other Adjustments")
        other_inp = self._input_fields.get(other_adj_idx, {}).get(data_idx)
        other_adj = None
        if other_inp is not None:
            raw = other_inp.text().strip()
            other_adj = _parse_label_as_float(raw) if raw else 0.0
        fcf = None
        if nopat is not None and dfcfnwc is not None:
            fcf = nopat + (total_da_addback or 0.0) - dfcfnwc - (residual_capex or 0.0) - (other_adj or 0.0)
        self._set_currency("Free Cash Flow", data_idx, fcf)

    def get_residual_revenue(self) -> Optional[float]:
        calc = getattr(self, "_shared_calc", None) or {}
        rows = calc.get("rows", {}) or {}
        revenue = rows.get("revenue", {}) or {}

        if "Residual" in revenue:
            return revenue.get("Residual")

        if "Residual" not in self._headers:
            return None

        return _read_label(
            self._calc_labels,
            self._row_idx.get("Revenue"),
            self._headers.index("Residual"),
        )

    def collect_state(self) -> dict:
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
        tv_inputs_state = {model: {key: widget.text() for key, widget in fields.items()} for model, fields in self._tv_inputs.items()}
        return {
            "ltg_input": self.ltg_input.text(),
            "tv_model": self.tv_model_combo.currentText(),
            "tv_inputs": tv_inputs_state,
            "capex_dep_pct": self.capex_dep_pct.text(),
            "cash_flows_to": self._cash_flows_to,
            "other_adj_inputs": other_adj,
            "residual_amortization": residual_amortization,
            "bridge_other_adj": self.bridge_other_adj_input.text(),
            "per_cf_tv_multiples": self._per_cf_tv_multiples,
            "last_cf_mode": self._last_cf_mode,
        }

    def apply_state(self, state: dict):
        if not state:
            return

        self.ltg_input.setText(state.get("ltg_input", "3.0%"))
        self.capex_dep_pct.setText(
            state.get("capex_dep_pct", "100.0%")
        )
        self.bridge_other_adj_input.setText(
            state.get("bridge_other_adj", "")
        )

        self._cash_flows_to = state.get("cash_flows_to", "FCFF")

        if isinstance(state.get("per_cf_tv_multiples"), dict):
            self._per_cf_tv_multiples = state["per_cf_tv_multiples"]

        self._last_cf_mode = state.get(
            "last_cf_mode",
            self._cash_flows_to,
        )

        tv_model = state.get("tv_model", "Gordon Growth")
        tv_model_idx = self.tv_model_combo.findText(tv_model)
        if tv_model_idx >= 0:
            blocked = self.tv_model_combo.blockSignals(True)
            self.tv_model_combo.setCurrentIndex(tv_model_idx)
            self.tv_model_combo.blockSignals(blocked)

        self._apply_tv_model_visibility()

        for model, fields in state.get("tv_inputs", {}).items():
            for key, text in fields.items():
                widget = self._tv_inputs.get(model, {}).get(key)
                if widget is not None:
                    blocked = widget.blockSignals(True)
                    widget.setText("" if text is None else str(text))
                    widget.blockSignals(blocked)

        # Ensure the input-bearing table exists before restoring its cells.
        self._rebuild_table_if_needed()

        other_adj_idx = self._row_idx.get("Less: Other Adjustments")
        other_adj = state.get("other_adj_inputs", {}) or {}
        for data_idx, period in enumerate(self._headers):
            widget = self._input_fields.get(
                other_adj_idx, {}
            ).get(data_idx)
            if widget is not None and period in other_adj:
                blocked = widget.blockSignals(True)
                widget.setText(
                    ""
                    if other_adj[period] is None
                    else str(other_adj[period])
                )
                widget.blockSignals(blocked)

        amortization_idx = self._row_idx.get("Amortization")
        residual_idx = (
            self._headers.index("Residual")
            if "Residual" in self._headers
            else None
        )
        residual_widget = (
            self._input_fields.get(amortization_idx, {}).get(residual_idx)
            if residual_idx is not None
            else None
        )
        if (
            residual_widget is not None
            and "residual_amortization" in state
        ):
            blocked = residual_widget.blockSignals(True)
            residual_widget.setText(
                ""
                if state["residual_amortization"] is None
                else str(state["residual_amortization"])
            )
            residual_widget.blockSignals(blocked)

        # Calculate once, after every saved input has been restored.
        self._recalculate()
        self._recalculate()