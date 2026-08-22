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
)
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
NET_INT_PROJ_PLACEHOLDER = 8008135

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
    Simple box with Solve for dropdown. No data entry for blue inputs —
    they come from extract_ticker_inputs() via MainWindow callback.
    When fcfe_n_not_positive or other flag -> NA + flag to status bar.
    """
    def __init__(self, parent=None, initial_inputs: Optional[Dict]=None, full_fade_convention: bool=True):
        super().__init__(parent)
        self.setWindowTitle("Reverse-DCF — Market-Implied Growth")
        self.setMinimumWidth(820)
        self.inputs = initial_inputs
        self.full_fade_convention = full_fade_convention
        self._build_ui()
        self._recalculate()

    def _build_ui(self):
        outer = QVBoxLayout()
        outer.setSpacing(8)
        outer.setContentsMargins(12,12,12,12)

        # Header info
        info_form = QFormLayout()
        self.lbl_ticker = QLabel(self.inputs.get("ticker","-") if self.inputs else "-")
        self.lbl_ticker.setStyleSheet(get_bold_style())
        info_form.addRow("Ticker:", self.lbl_ticker)

        self.lbl_market_cap = QLabel("-")
        self.lbl_ke = QLabel("-")
        self.lbl_pv_sum = QLabel("-")
        self.lbl_a = QLabel("-")
        self.lbl_fcfe_n = QLabel("-")
        info_form.addRow("Market Cap:", self.lbl_market_cap)
        info_form.addRow("Ke:", self.lbl_ke)
        info_form.addRow("ΣPV(FCFE):", self.lbl_pv_sum)
        info_form.addRow("A:", self.lbl_a)
        info_form.addRow("FCFE_N:", self.lbl_fcfe_n)
        outer.addLayout(info_form)

        # FCFE bridge grid
        self.bridge_frame = QFrame()
        self.bridge_frame.setFrameShape(QFrame.Shape.StyledPanel)
        self.bridge_grid = QGridLayout()
        self.bridge_grid.setSpacing(4)
        headers = ["Yr","Revenue","NetIncome","Depr","CapEx","ΔNWC","FCFE","PV(FCFE)"]
        for c,h in enumerate(headers):
            lbl = QLabel(h)
            lbl.setStyleSheet(get_bold_style())
            self.bridge_grid.addWidget(lbl, 0, c)
        # 3 rows for N=3
        self.bridge_cells = []
        for r in range(3):
            row_cells = []
            for c in range(len(headers)):
                lbl = QLabel("-")
                lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
                self.bridge_grid.addWidget(lbl, r+1, c)
                row_cells.append(lbl)
            self.bridge_cells.append(row_cells)
        self.bridge_frame.setLayout(self.bridge_grid)
        outer.addWidget(self.bridge_frame)

        # Gordon
        gordon_form = QFormLayout()
        self.lbl_gordon = QLabel("-")
        self.lbl_gordon.setStyleSheet(get_bold_style())
        gordon_form.addRow("Gordon Implied LTGR:", self.lbl_gordon)
        outer.addLayout(gordon_form)

        # H-Model controls
        h_box = QFrame()
        h_box.setFrameShape(QFrame.Shape.StyledPanel)
        h_layout = QVBoxLayout()
        h_layout.setContentsMargins(8,8,8,8)

        top_h = QHBoxLayout()
        top_h.addWidget(QLabel("Solve for:"))
        self.solve_combo = QComboBox()
        self.solve_combo.addItems(["H","Ga","Gn"])
        self.solve_combo.setStyleSheet(get_input_style())
        self.solve_combo.currentTextChanged.connect(self._on_solve_changed)
        top_h.addWidget(self.solve_combo)
        top_h.addStretch()
        self.chk_term_capex = QCheckBox("Terminal CapEx = Depr")
        self.chk_term_capex.setChecked(True)
        self.chk_term_capex.stateChanged.connect(self._recalculate)
        top_h.addWidget(self.chk_term_capex)
        h_layout.addLayout(top_h)

        form = QFormLayout()
        self.in_ga = QLineEdit("15.00%")
        self.in_gn = QLineEdit("3.00%")
        self.in_h = QLineEdit("6.00")
        for w in [self.in_ga, self.in_gn, self.in_h]:
            w.setStyleSheet(get_input_style())
            w.setFixedWidth(90)
            w.editingFinished.connect(self._recalculate)
        form.addRow("Ga (ST Growth):", self.in_ga)
        form.addRow("Gn (LT Growth):", self.in_gn)
        form.addRow("H (Full Years):", self.in_h)
        h_layout.addLayout(form)

        self.lbl_h_result = QLabel("-")
        self.lbl_h_result.setStyleSheet(get_bold_style())
        h_layout.addWidget(self.lbl_h_result)

        h_box.setLayout(h_layout)
        outer.addWidget(h_box)

        # Status bar where source_data statuses live
        self.status_label = QLabel("")
        self.status_label.setStyleSheet(get_note_style())
        outer.addWidget(self.status_label)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        btns.rejected.connect(self.reject)
        outer.addWidget(btns)

        self.setLayout(outer)
        self._on_solve_changed(self.solve_combo.currentText())

    def _on_solve_changed(self, text: str):
        # Only solved-for variable is disabled, per spec - no circular
        self.in_ga.setEnabled(text != "Ga")
        self.in_gn.setEnabled(text != "Gn")
        self.in_h.setEnabled(text != "H")
        self._recalculate()

    def _recalculate(self):
        if not self.inputs:
            self.lbl_market_cap.setText("NA")
            self.lbl_ke.setText("NA")
            self.lbl_pv_sum.setText("NA")
            self.lbl_a.setText("NA")
            self.lbl_fcfe_n.setText("NA")
            self.lbl_gordon.setText("NA")
            self.lbl_h_result.setText("NA")
            self.status_label.setText("No inputs - wire get_reverse_dcf_inputs_callback in MainWindow")
            return

        rf = self.inputs.get("risk_free_rate")
        beta = self.inputs.get("relevered_beta")
        erp = self.inputs.get("equity_risk_premium")
        ke = compute_cost_of_equity(rf, beta, erp)

        revenue = self.inputs.get("revenue", {})
        net_income = self.inputs.get("net_income", {})
        rev_prior = revenue.get("TTM") or revenue.get("LFY")
        rev_explicit = [revenue.get("NFY"), revenue.get("NFY+1"), revenue.get("NFY+2")]
        ni_explicit = [net_income.get("NFY"), net_income.get("NFY+1"), net_income.get("NFY+2")]

        fcfe_schedule = build_fcfe_schedule(
            revenue_prior=rev_prior,
            revenue_explicit=rev_explicit,
            net_income_explicit=ni_explicit,
            depr_pct=self.inputs.get("depr_pct"),
            capex_pct=self.inputs.get("capex_pct"),
            nwc_pct=self.inputs.get("nwc_pct"),
            force_terminal_capex_equals_da=self.chk_term_capex.isChecked(),
        )

        market_cap = self.inputs.get("market_cap")
        a = compute_reconciliation_a(market_cap, fcfe_schedule, ke)
        pv_sum = None
        fcfe_n = None
        if fcfe_schedule and ke is not None:
            pv_sum = sum(yr["fcfe"]/((1+ke)**yr["year_index"]) for yr in fcfe_schedule)
            fcfe_n = fcfe_schedule[-1]["fcfe"]

        # Update header
        self.lbl_market_cap.setText(_fmt_currency2(market_cap))
        self.lbl_ke.setText(_fmt_pct2(ke))
        self.lbl_pv_sum.setText(_fmt_currency2(pv_sum))
        self.lbl_a.setText(_fmt_currency2(a))
        self.lbl_fcfe_n.setText(_fmt_currency2(fcfe_n))
        self.lbl_ticker.setText(self.inputs.get("ticker","-"))

        # Bridge table
        if fcfe_schedule:
            for r, yr in enumerate(fcfe_schedule):
                pv = yr["fcfe"]/((1+ke)**yr["year_index"]) if ke is not None else None
                vals = [yr["year_index"], yr["revenue"], yr["net_income"], yr["depreciation"], yr["capex"], yr["delta_nwc"], yr["fcfe"], pv]
                for c,v in enumerate(vals):
                    self.bridge_cells[r][c].setText(_fmt_currency2(v) if c!=0 else str(v))
        else:
            for r in range(3):
                for c in range(8):
                    self.bridge_cells[r][c].setText("NA")

        # Gordon
        gordon = solve_gordon_growth_ltgr(a, ke, fcfe_n)
        if gordon["value"] is None:
            self.lbl_gordon.setText(f"NA ({','.join(gordon['flags'])})")
        else:
            self.lbl_gordon.setText(_fmt_pct2(gordon["value"]) + ("" if gordon["is_valid"] else f" [{','.join(gordon['flags'])}]"))

        # H-Model
        solve_for = self.solve_combo.currentText()
        ga = _parse_pct_field(self.in_ga.text()) if solve_for != "Ga" else None
        gn = _parse_pct_field(self.in_gn.text()) if solve_for != "Gn" else None
        try:
            h_val = float(self.in_h.text().strip()) if solve_for != "H" else None
        except:
            h_val = None

        h_res = solve_h_model(a, ke, fcfe_n, ga=ga, gn=gn, h=h_val, solve_for=solve_for, full_fade_convention=self.full_fade_convention)

        if h_res["value"] is None:
            # Flag -> NA, print flag to bottom bar where source_data statuses are
            if solve_for == "H":
                self.lbl_h_result.setText("NA")
            else:
                self.lbl_h_result.setText("NA")
            self.status_label.setText(f"{self.inputs.get('ticker','')}: {','.join(h_res['flags'])} | Gordon: {','.join(gordon['flags'])}")
        else:
            if solve_for == "H":
                h_full = h_res["value"]
                h_half = h_full/2 if self.full_fade_convention else h_full
                self.lbl_h_result.setText(f"H full={h_full:.2f} (h half={h_half:.2f})")
            else:
                self.lbl_h_result.setText(_fmt_pct2(h_res["value"]))
            # Still surface flags if any (e.g. solved_gn_gte_ke)
            all_flags = gordon["flags"] + h_res["flags"]
            self.status_label.setText(", ".join(all_flags) if all_flags else "")

    def set_inputs(self, inputs: Dict):
        self.inputs = inputs
        self._recalculate()

class DCFPage(QWidget):
    def __init__(self,
                 get_project_inputs_callback,
                 get_wacc_value_callback,
                 get_subject_financials_callback,
                 get_projection_data_callback,
                 update_projection_callback, 
                 get_nwc_change_callback=None,
                 get_reverse_dcf_inputs_callback=None,
                 get_gpc_tickers_callback=None):
        super().__init__()
        self.get_project_inputs = get_project_inputs_callback
        self.get_wacc_value = get_wacc_value_callback
        self._get_subject_financials = get_subject_financials_callback
        self._get_projection_data = get_projection_data_callback
        self._update_projection_callback = update_projection_callback
        self._get_nwc_change = get_nwc_change_callback or (lambda _period: None)
        self._get_reverse_dcf_inputs_callback = get_reverse_dcf_inputs_callback
        self._get_gpc_tickers_callback = get_gpc_tickers_callback

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
        self._build_ui()
        self._recalculate()
        theme_manager.theme_changed.connect(self._apply_theme)

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
        self._lbl_capex_header.setStyleSheet(get_bold_style())
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

        self.link_reverse_dcf = QPushButton("Reverse-DCF (Market-Implied)")
        self.link_reverse_dcf.setStyleSheet(get_link_style())
        self.link_reverse_dcf.setCursor(Qt.CursorShape.PointingHandCursor)
        self.link_reverse_dcf.clicked.connect(self._open_reverse_dcf)
        toggle_row.addWidget(self.link_reverse_dcf)

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
        inputs = None
        if self._get_reverse_dcf_inputs_callback is not None:
            try:
                proj_inputs = self.get_project_inputs()
                ticker = getattr(proj_inputs, 'subject_ticker', None) or getattr(proj_inputs, 'ticker', None) or getattr(proj_inputs, 'subject_company_name', None) or "ADBE"
                inputs = self._get_reverse_dcf_inputs_callback(ticker)
            except Exception as e:
                print(f"Reverse-DCF callback failed: {e}")
                inputs = None
        if inputs is None:
            inputs = self._build_reverse_dcf_inputs_from_page()
        dlg = ReverseDCFDialog(self, initial_inputs=inputs, full_fade_convention=True)
        dlg.exec()

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
                    net_income[lbl] = self._get_subject_financials("net income", lbl)
                except:
                    net_income[lbl] = None

            rev_ttm = revenue.get("TTM") or revenue.get("LFY")
            dep_ttm = None
            capex_ttm = None
            try:
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
            bs_keys = {
                "total_current_assets": "total current assets",
                "total_current_liab": "total current liabilities",
                "current_ltd": "current portion of long-term debt",
                "st_debt": "short-term debt",
                "current_leases": "current portion of leases",
                "cash": "cash & equivalents",
            }
            bs = {}
            for k,v in bs_keys.items():
                try:
                    bs[k] = self._get_subject_financials(v, "LFY")
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
        self._lbl_tv_header = QLabel("Terminal Value", styleSheet=get_bold_style())
        res_layout.addWidget(self._lbl_tv_header)
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
        bridge_widget = self._build_fv_bridge()
        self._footer_hbox.addWidget(bridge_widget, 1)
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
        self._update_ebit_row_label()
        self._apply_net_int_proj_visibility()
        self._populate_revenue_and_growth(inputs)
        self._populate_cogs_through_ebitda()
        self._populate_dep_amort_net_int()
        self._populate_ebit_and_ebit_margin()
        self._populate_taxes(inputs)
        self._populate_nopat()
        self._populate_capex_other_nwc()
        self._populate_fcf()
        self._populate_pv_chain(wacc_val, inputs)
        self._populate_residual_column(inputs)
        self._populate_terminal_value(wacc_val, inputs)
        self._populate_fv_bridge(inputs)
        self._populate_sensitivity_table(inputs)

    def refresh(self):
        self._recalculate()

    def _update_ebit_row_label(self):
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

    def _populate_dep_amort_net_int(self):
        for data_idx, label in enumerate(self._headers):
            if self._is_historical[data_idx]:
                dep = self._sf_get("depreciation", label)
                amort = self._sf_get("amortization", label)
                int_exp = self._sf_get("interest_expense", label)
                int_inc = self._sf_get("interest_income", label)
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

    def _populate_ebit_and_ebit_margin(self):
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
        tax_rate = inputs.subject_tax_rate
        ebit_idx = self._row_idx.get("EBIT")
        for data_idx, label in enumerate(self._headers):
            if self._is_historical[data_idx]:
                self._set_currency("Taxes", data_idx, self._sf_get("taxes", label))
            else:
                ebit_lbl = self._calc_labels.get(ebit_idx, {}).get(data_idx)
                ebit_val = _parse_label_as_float(ebit_lbl.text()) if ebit_lbl is not None else None
                if ebit_val is not None and tax_rate is not None:
                    self._set_currency("Taxes", data_idx, ebit_val * tax_rate)
                else:
                    self._set("Taxes", data_idx, "-")

    def _populate_nopat(self):
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
        for data_idx, label in enumerate(self._headers):
            if self._is_historical[data_idx]:
                plus_dep = self._sf_get("depreciation", label)
            else:
                plus_dep = self._get_projection_data().da.get(label)
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
        if ppa is not None and ppa <= 0:
            ppa = None
        fcf_idx = self._row_idx.get("Free Cash Flow")
        prior_pvp: Optional[float] = None
        for data_idx, label in enumerate(self._headers):
            if self._is_historical[data_idx]:
                continue
            if label == "Residual":
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
                if prior_pvp is None:
                    pvp = None
                else:
                    pvp = prior_pvp + 1.0
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
        wacc_now = self.get_wacc_value()
        ltgr_now = self._get_ltgr()
        wacc_now = wacc_now if wacc_now is not None else 0.10
        ltgr_now = ltgr_now if ltgr_now is not None else 0.03
        self._lbl_wacc_ltgr_corner = QLabel("WACC \\ LTGR", styleSheet=get_bold_style())
        grid.addWidget(self._lbl_wacc_ltgr_corner, 0, 0)
        DATA_COL_WIDTH = 78
        FIRST_DATA_COL = 2
        self.sens_wacc_inputs = []
        self._sens_wacc_auto_text = []
        for col, offset in enumerate([-0.02, -0.01, 0.0, 0.01, 0.02]):
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
        self.bridge_fv_high_label.setText(self.sens_value_labels[high_coord[0]][high_coord[1]].text())
        self.bridge_fv_low_label.setText(self.sens_value_labels[low_coord[0]][low_coord[1]].text())
        wacc_val = self.get_wacc_value()
        self._populate_residual_column(inputs)
        self._populate_pv_chain(wacc_val, inputs)
        self._populate_terminal_value(wacc_val, inputs)
        self._populate_fv_bridge(inputs)

    def _populate_fv_bridge(self, inputs):
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
        self.bridge_fv_base_row_label.setText("Fair Value of Business Enterprise (Base):" if is_fcff else "Fair Value of Equity (Base):")

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
        self._set_currency("Plus: Depreciation", data_idx, depreciation)
        amort_idx = self._row_idx.get("Amortization")
        amort_inp = self._input_fields.get(amort_idx, {}).get(data_idx)
        amortization = _parse_label_as_float(amort_inp.text()) if amort_inp is not None else None
        net_interest = None
        if is_fcfe:
            net_interest = grow(final("Net Interest Expense"))
            self._set_currency("Net Interest Expense", data_idx, net_interest)
        if ebitda is None or depreciation is None:
            ebit_or_ebt = None
        elif is_fcfe:
            ebit_or_ebt = None if net_interest is None else (ebitda - depreciation - (amortization or 0.0) - net_interest)
        else:
            ebit_or_ebt = ebitda - depreciation - (amortization or 0.0)
        self._set_currency("EBIT", data_idx, ebit_or_ebt)
        self._set_pct("EBIT Margin", data_idx, _safe_div(ebit_or_ebt, revenue))
        taxes = ebit_or_ebt * tax_rate if (ebit_or_ebt is not None and tax_rate is not None) else None
        self._set_currency("Taxes", data_idx, taxes)
        nopat = (ebit_or_ebt - (taxes or 0.0)) if ebit_or_ebt is not None else None
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
            fcf = nopat + (depreciation or 0.0) - dfcfnwc - (residual_capex or 0.0) - (other_adj or 0.0)
        self._set_currency("Free Cash Flow", data_idx, fcf)

    def get_residual_revenue(self) -> Optional[float]:
        if "Residual" not in self._headers:
            return None
        return _read_label(self._calc_labels, self._row_idx.get("Revenue"), self._headers.index("Residual"))

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