import math
from typing import Optional

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
INDENT_STYLE = "padding-left: 20px;"  # Non-italic indent
COL_WIDTH = 95

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
        self.pv_factor_label = None
        self._build_ui()
        self._recalculate()

    def _build_ui(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)

        self.container = QWidget()
        self.grid = QGridLayout()
        self.grid.setSpacing(2)
        self.grid.setContentsMargins(10, 10, 10, 10)

        self.grid.setColumnStretch(0, 2)
        self._current_row = 0

        # FIX: Generate columns first so _headers is populated BEFORE building header controls
        self._generate_columns()

        self._build_header_controls()
        self._build_table()
        self._build_footer_panels()

        self.grid.setRowStretch(self._current_row + 50, 1)
        self.container.setLayout(self.grid)
        scroll.setWidget(self.container)

        outer = QVBoxLayout()
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)
        self.setLayout(outer)

    def _build_header_controls(self):
        r = self._current_row
        
        toggle_frame = QFrame()
        toggle_frame.setFrameShape(QFrame.Shape.Box)
        toggle_layout = QHBoxLayout()
        toggle_layout.setContentsMargins(5, 5, 5, 5)
        
        self.link_toggles = QPushButton("Projection Toggles")
        self.link_toggles.setStyleSheet("border: none; color: #1a4a8a; text-decoration: underline; background: transparent;")
        self.link_toggles.setCursor(Qt.CursorShape.PointingHandCursor)
        self.link_toggles.clicked.connect(self._open_toggles)
        toggle_layout.addWidget(self.link_toggles)
        toggle_layout.addStretch()
        toggle_frame.setLayout(toggle_layout)
        
        self.grid.addWidget(toggle_frame, r, 0, 1, len(self._headers) + 1)
        self._current_row += 1

        r = self._current_row
        self.lbl_client = QLabel()
        self.lbl_client.setStyleSheet(BOLD_STYLE)
        self.lbl_subject = QLabel()
        self.lbl_subject.setStyleSheet(BOLD_STYLE)
        self.lbl_method = QLabel("Income Approach - Discounted Cash Flow Method")
        self.lbl_method.setStyleSheet(BOLD_STYLE)
        self.lbl_date = QLabel()
        self.lbl_date.setStyleSheet(BOLD_STYLE)

        self.grid.addWidget(self.lbl_client,  r, 0, alignment=Qt.AlignmentFlag.AlignLeft)
        self.grid.addWidget(self.lbl_subject, r, 1, alignment=Qt.AlignmentFlag.AlignLeft)
        self.grid.addWidget(self.lbl_method,  r, 2, alignment=Qt.AlignmentFlag.AlignLeft)
        self.grid.addWidget(self.lbl_date,    r, 4, alignment=Qt.AlignmentFlag.AlignRight)
        self._current_row += 1

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
        
        self._headers = hist_labels + proj_labels + ["Residual", "Historical Average"]
        self._is_historical = [True]*len(hist_labels) + [False]*len(proj_labels) + [False, False]
        return len(hist_labels), len(proj_labels)

    def _build_table(self):
        num_hist, num_proj = self._generate_columns()
        
        for i in range(len(self._headers) + 1):
            self.grid.setColumnMinimumWidth(i, COL_WIDTH)

        r = self._current_row
        
        self.grid.addWidget(QLabel("Line Item"), r, 0)
        if num_hist > 0:
            self.grid.addWidget(_make_section_label("Historical Financials"), r, 1, 1, num_hist)
        if num_proj > 0:
            self.grid.addWidget(_make_section_label("Projected Financials"), r, 1 + num_hist, 1, num_proj)
        self.grid.addWidget(_make_section_label("Residual / Summary"), r, 1 + num_hist + num_proj, 1, 2)
        self._current_row += 1

        r = self._current_row
        inputs = self.get_project_inputs()
        self.grid.addWidget(QLabel("FYE"), r, 0)
        
        for i, col_label in enumerate(self._headers):
            display_text = col_label
            if "NFY" in col_label:
                if col_label == "NFY":
                    display_text = inputs.next_fiscal_year
                elif col_label == "NFY+1":
                    display_text = inputs.nfy_1
                elif col_label == "NFY+2":
                    display_text = inputs.nfy_2
            
            lbl = QLabel(display_text)
            lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            lbl.setStyleSheet("font-size: 10px; color: #555555;")
            self.grid.addWidget(lbl, r, i + 1)
        self._current_row += 1

        self._rows = [
            ("Revenue", False, False, False),
            ("Revenue Growth", False, False, False),
            ("Cost of Goods Sold", False, False, False),
            ("Gross Profit", True, False, False),
            ("Gross Profit Margin", False, False, False),
            ("Operating Expenses", True, False, False),
            ("EBITDA", True, False, False),
            ("EBITDA Margin", False, False, False),
            ("Depreciation", False, False, False),
            ("Amortization", False, False, False),
            ("Net Interest Expense", False, False, False),
            ("EBIT", True, False, False),
            ("EBIT Margin", False, False, False),
            ("Taxes", False, False, False),
            ("Net Operating Profit After Tax (NOPAT)", True, False, False),
            ("Plus: Depreciation", False, False, True),
            ("Less: Increase/(Decrease) in DCF/NWC", False, False, True),
            ("Less: Capital Expenditures (CapEx)", False, False, True),
            ("Less: Other Adjustments", False, False, True),
            ("Free Cash Flow", True, False, False),
            ("Partial Period Adjustment", False, False, False),
            ("Present Value Period", False, False, False),
            ("Present Value Factor", False, False, False),
            ("Present Value of Free Cash Flows", True, False, False)
        ]

        for idx, (label, is_bold, is_input, is_indent) in enumerate(self._rows):
            row = self._current_row
            row_lbl = QLabel(label)
            if is_bold: row_lbl.setStyleSheet(BOLD_STYLE)
            if is_indent: row_lbl.setStyleSheet(INDENT_STYLE)
            
            self.grid.addWidget(row_lbl, row, 0, alignment=Qt.AlignmentFlag.AlignLeft)

            self._calc_labels[idx] = {}
            self._input_fields[idx] = {}

            for col_idx in range(len(self._headers)):
                if is_input:
                    inp = QLineEdit()
                    inp.setStyleSheet(INPUT_STYLE)
                    inp.setFixedWidth(COL_WIDTH - 10)
                    inp.setAlignment(Qt.AlignmentFlag.AlignRight)
                    inp.editingFinished.connect(self._recalculate)
                    self.grid.addWidget(inp, row, col_idx + 1)
                    self._input_fields[idx][col_idx] = inp
                else:
                    calc_lbl = QLabel("-")
                    calc_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                    if is_bold: calc_lbl.setStyleSheet(BOLD_STYLE)
                    self.grid.addWidget(calc_lbl, row, col_idx + 1)
                    self._calc_labels[idx][col_idx] = calc_lbl
                    
                    if label == "Present Value Factor":
                        self.pv_factor_label = calc_lbl
            self._current_row += 1

    def _build_footer_panels(self):
        r = self._current_row
        footer_hbox = QHBoxLayout()
        footer_hbox.setContentsMargins(0, 20, 0, 0)
        
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
        footer_hbox.addWidget(res_frame, 1)

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
        footer_hbox.addWidget(capex_frame, 1)
        
        self.grid.addLayout(footer_hbox, r, 0, 1, len(self._headers) + 1)
        self._current_row += 3

    def _recalculate(self):
        inputs = self.get_project_inputs()
        wacc_val = self.get_wacc_value()

        self.lbl_client.setText(inputs.client)
        self.lbl_subject.setText(inputs.subject_company_name)
        self.lbl_date.setText(f"As of {inputs.valuation_date}")

        pct_str = f"{wacc_val * 100:.2f}%" if wacc_val is not None else "N/A%"
        if self.pv_factor_label is not None:
            self.pv_factor_label.setText(f"Present Value Factor @ {pct_str}")

        print("DCF Recalculate triggered.")

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
        if not state: return
        self.ltg_input.setText(state.get("ltg_input", "3.0%"))
        self.res_year_input.setText(state.get("res_year_input", "2035"))
        self.capex_ltg.setText(state.get("capex_ltg", "425"))
        self.capex_dep_pct.setText(state.get("capex_dep_pct", "100.0%"))
        self._recalculate()