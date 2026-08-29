"""
theory_page.py
Displays the academic reconciliation and Modigliani-Miller dynamics.
"""
from typing import Optional
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, 
    QScrollArea, QFrame, QPushButton, QLineEdit
)
from PyQt6.QtCore import Qt

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure

from Canneberge.Ui.theme import theme_manager
from Canneberge.Calculations.theory_math import compute_theory_diagnostics, generate_mm_curve_data

def get_bold_style() -> str:
    return theme_manager.current.bold_style()

def get_header_style() -> str:
    return theme_manager.current.header_style()

def get_input_style() -> str:
    return theme_manager.current.input_style()

def _parse_label(text: str) -> float:
    if not text or text in ("-", "NA", "N/A"):
        return 0.0
    cleaned = text.replace(",", "").replace("%", "").replace("$", "").replace("(", "-").replace(")", "").strip()
    try:
        return float(cleaned)
    except ValueError:
        return 0.0

class TheoryPage(QWidget):
    def __init__(self, get_dcf_page, get_wacc_page, get_subject_financials, get_project_inputs, get_stockanalysis):
        super().__init__()
        self.get_dcf_page = get_dcf_page
        self.get_wacc_page = get_wacc_page
        self.get_subject_financials = get_subject_financials
        self.get_project_inputs = get_project_inputs
        self.get_stockanalysis = get_stockanalysis
        
        self._build_ui()
        theme_manager.theme_changed.connect(self._apply_theme)

    def _apply_theme(self, theme=None):
        t = theme_manager.current
        for lbl in self._header_labels:
            lbl.setStyleSheet(get_header_style())
        for lbl in self._bold_labels:
            lbl.setStyleSheet(get_bold_style())
        
        self.figure.patch.set_facecolor(t.window_bg)
        self.ax.set_facecolor(t.window_bg)
        self.ax.tick_params(colors=t.chart_axis_label)
        for spine in self.ax.spines.values():
            spine.set_color(t.chart_grid)
        self.refresh()

    def _build_ui(self):
        self._header_labels = []
        self._bold_labels = []
        self._val_labels = {}
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        main_layout = QVBoxLayout(container)
        
        # Header
        hdr = QLabel("Theory & Dynamics: Capital Structure vs. Market Output")
        hdr.setStyleSheet(get_header_style())
        self._header_labels.append(hdr)
        main_layout.addWidget(hdr)
        
        # Splitter for Grid vs Chart
        h_split = QHBoxLayout()
        
        # Left Panel (Grids)
        left_panel = QVBoxLayout()
        left_panel.addWidget(self._build_inputs_grid())
        left_panel.addWidget(self._build_ratios_grid())
        
        # Notes block
        self.lbl_notes = QLabel("Refresh tab to calculate dynamics.")
        self.lbl_notes.setWordWrap(True)
        self.lbl_notes.setStyleSheet(f"color: {theme_manager.current.note_text}; font-style: italic; padding: 10px;")
        left_panel.addWidget(self.lbl_notes)
        left_panel.addStretch()
        
        h_split.addLayout(left_panel, 1)
        
        # Right Panel (Chart)
        right_panel = QVBoxLayout()
        self.figure = Figure(figsize=(6, 5))
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.ax = self.figure.add_subplot(111)
        right_panel.addWidget(self.canvas)
        
        # Overrides (Advanced)
        self.btn_adv = QPushButton("Show Advanced Overrides")
        self.btn_adv.setCheckable(True)
        self.btn_adv.clicked.connect(self._toggle_advanced)
        right_panel.addWidget(self.btn_adv)
        
        self.adv_widget = QWidget()
        adv_layout = QHBoxLayout(self.adv_widget)
        adv_layout.addWidget(QLabel("Cash Yield (rc):"))
        self.inp_rc = QLineEdit("4.5%")
        self.inp_rc.setStyleSheet(get_input_style())
        self.inp_rc.editingFinished.connect(self.refresh)
        adv_layout.addWidget(self.inp_rc)
        adv_layout.addStretch()
        self.adv_widget.setVisible(False)
        right_panel.addWidget(self.adv_widget)
        
        h_split.addLayout(right_panel, 1)
        main_layout.addLayout(h_split)
        
        scroll.setWidget(container)
        layout.addWidget(scroll)

    def _toggle_advanced(self):
        self.adv_widget.setVisible(self.btn_adv.isChecked())

    def _build_inputs_grid(self) -> QWidget:
        w = QWidget()
        g = QGridLayout(w)
        lbl = QLabel("Model Inputs")
        lbl.setStyleSheet(get_header_style())
        self._header_labels.append(lbl)
        g.addWidget(lbl, 0, 0, 1, 2)
        
        self.input_keys = [
            "Enterprise Value (FCFF)", "Equity Value (FCFE)", "Equity Value (FCFF Bridge)",
            "Market Cap", "Book Debt (TTM)", "Cash (TTM)", "WACC", "Cost of Equity (Ke)", "Book Wd"
        ]
        
        for i, k in enumerate(self.input_keys, 1):
            klbl = QLabel(k)
            klbl.setStyleSheet(get_bold_style())
            self._bold_labels.append(klbl)
            g.addWidget(klbl, i, 0)
            
            vlbl = QLabel("-")
            vlbl.setAlignment(Qt.AlignmentFlag.AlignRight)
            self._val_labels[k] = vlbl
            g.addWidget(vlbl, i, 1)
            
        return w

    def _build_ratios_grid(self) -> QWidget:
        w = QWidget()
        g = QGridLayout(w)
        lbl = QLabel("Friction Diagnostics")
        lbl.setStyleSheet(get_header_style())
        self._header_labels.append(lbl)
        g.addWidget(lbl, 0, 0, 1, 3)
        
        self.ratio_keys = [
            ("λ (Net Leverage)", "ND / BEV"),
            ("R (Absolute Residual)", "FCFF_Eq - FCFE_Eq"),
            ("R / Ve (% Residual)", "R / avg(Ve)"),
            ("Market Wd", "Debt / (Debt + MCap)"),
            ("MM Spread Gap", "Actual vs Expected Spread"),
            ("θ (Debt Service Bite)", "Interest / FCFF"),
        ]
        
        g.addWidget(QLabel("Metric", styleSheet=get_bold_style()), 1, 0)
        g.addWidget(QLabel("Formula", styleSheet=get_bold_style()), 1, 1)
        g.addWidget(QLabel("Value", styleSheet=get_bold_style()), 1, 2)
        
        for i, (name, form) in enumerate(self.ratio_keys, 2):
            g.addWidget(QLabel(name), i, 0)
            flbl = QLabel(form)
            flbl.setStyleSheet(f"color: {theme_manager.current.note_text}; font-size: 10px;")
            g.addWidget(flbl, i, 1)
            
            vlbl = QLabel("-")
            vlbl.setAlignment(Qt.AlignmentFlag.AlignRight)
            vlbl.setStyleSheet(get_bold_style())
            self._bold_labels.append(vlbl)
            self._val_labels[name] = vlbl
            g.addWidget(vlbl, i, 2)
            
        return w

    def _fetch_data(self):
        dcf = self.get_dcf_page()
        wacc = self.get_wacc_page()
        inputs = self.get_project_inputs()
        
        # Temporarily force DCF to FCFF to get BEV, then FCFE to get Eq, then restore.
        # Since this tab is a sandbox, we do a silent read-calc cycle.
        orig = dcf._cash_flows_to
        
        dcf._cash_flows_to = "FCFF"
        dcf._recalculate()
        bev = _parse_label(dcf.bridge_fv_base_label.text())
        
        dcf._cash_flows_to = "FCFE"
        dcf._recalculate()
        eq_fcfe = _parse_label(dcf.bridge_fv_base_label.text())
        
        dcf._cash_flows_to = orig
        dcf._recalculate()

        # Build FCFF Equity bridge
        debt_ttm = 0.0
        cash_ttm = 0.0
        if self.get_subject_financials:
            # Quick proxy for debt/cash
            debt_ttm = (self.get_subject_financials("st_debt", "TTM") or 0.0) + (self.get_subject_financials("lt_debt", "TTM") or 0.0)
            cash_ttm = self.get_subject_financials("cash", "TTM") or 0.0
            
        eq_fcff = bev - debt_ttm + cash_ttm if bev else 0.0
        
        sa = self.get_stockanalysis()
        mcap = 0.0
        if sa and "IS" in sa: # Rough fetch from subject inputs
            mcap = wacc.inputs.get("market_cap", 0.0) if hasattr(wacc, "inputs") and wacc.inputs else 115000.0 # fallback

        wd_book = _parse_label(wacc.lbl_debt_pct_capital.text()) / 100.0 if hasattr(wacc, 'lbl_debt_pct_capital') else 0.38
        ke = wacc.ke_value if hasattr(wacc, 'ke_value') else 0.12
        wac_val = wacc.wacc_value if hasattr(wacc, 'wacc_value') else 0.10
        kd = _parse_label(wacc.lbl_after_tax_cost_of_debt.text()) / 100.0 if hasattr(wacc, 'lbl_after_tax_cost_of_debt') else 0.03
        
        rc_val = _parse_label(self.inp_rc.text()) / 100.0
        
        return {
            "bev_fcff": bev,
            "equity_fcfe": eq_fcfe,
            "equity_fcff": eq_fcff,
            "book_debt": debt_ttm,
            "cash": cash_ttm,
            "market_cap": mcap,
            "wacc": wac_val,
            "ke": ke,
            "kd_after_tax": kd,
            "wd_book": wd_book,
            "tax_rate": inputs.subject_tax_rate or 0.25,
            "avg_fcff": bev / 15.0 if bev else 1.0, # Proxy for now
            "avg_interest": debt_ttm * 0.05,        # Proxy for now
            "rc": rc_val
        }

    def refresh(self):
        data = self._fetch_data()
        
        # Populate Inputs
        def setv(k, v, is_pct=False):
            if k in self._val_labels:
                self._val_labels[k].setText(f"{v*100:.2f}%" if is_pct else f"{v:,.0f}")
                
        setv("Enterprise Value (FCFF)", data["bev_fcff"])
        setv("Equity Value (FCFE)", data["equity_fcfe"])
        setv("Equity Value (FCFF Bridge)", data["equity_fcff"])
        setv("Market Cap", data["market_cap"])
        setv("Book Debt (TTM)", data["book_debt"])
        setv("Cash (TTM)", data["cash"])
        setv("WACC", data["wacc"], True)
        setv("Cost of Equity (Ke)", data["ke"], True)
        setv("Book Wd", data["wd_book"], True)
        
        # Run Brain
        res = compute_theory_diagnostics(**data)
        
        # Populate Ratios
        setv("λ (Net Leverage)", res["lam"], True)
        setv("R (Absolute Residual)", res["residual"])
        setv("R / Ve (% Residual)", res["pct_residual"], True)
        setv("Market Wd", res["wd_market"], True)
        setv("MM Spread Gap", res["mm_spread_gap"], True)
        setv("θ (Debt Service Bite)", res["theta"], True)
        
        # Dynamic Note
        if res["mm_spread_gap"] > 0.03:
            note = "⚠️ <b>MM Spread Mismatch:</b> Your WACC inputs reflect a book capital structure that differs heavily from market reality. Expect FCFF and FCFE to diverge as leverage assumptions fight."
        elif res["lam"] < 0.10:
            note = "✅ <b>Low Leverage Regime:</b> Debt is diluted by cash/EV scale. FCFF and FCFE align almost perfectly mathematically."
        else:
            note = "✅ <b>Balanced Regime:</b> Cost of capital inputs are internally consistent."
        self.lbl_notes.setText(note)
        
        # Chart
        self._plot_mm_curve(data["ke"], data["kd_after_tax"], data["wd_book"], res["wd_market"])

    def _plot_mm_curve(self, ke, kd, wd_book, wd_market):
        self.ax.clear()
        t = theme_manager.current
        
        curve = generate_mm_curve_data(ke, kd, wd_book)
        
        self.ax.plot(curve["x_wd"], curve["y_ke"], label="Cost of Equity (Ke)", color=t.chart_edge, lw=2)
        self.ax.plot(curve["x_wd"], curve["y_wacc"], label="WACC", color=t.chart_fill, lw=3)
        self.ax.plot(curve["x_wd"], curve["y_kd"], label="Kd (After-Tax)", color=t.chart_grid, lw=2, linestyle="--")
        
        self.ax.axvline(wd_book, color=t.chart_conclude, linestyle=":", label=f"Book Wd ({wd_book*100:.1f}%)")
        if wd_market > 0:
            self.ax.axvline(wd_market, color=t.default_text, linestyle="-.", label=f"Market Wd ({wd_market*100:.1f}%)")
        
        self.ax.set_title("Modigliani-Miller Cost of Capital Dynamics", color=t.default_text)
        self.ax.set_xlabel("Debt to Capital (Wd)", color=t.default_text)
        self.ax.set_ylabel("Cost of Capital", color=t.default_text)
        self.ax.legend(facecolor=t.window_bg, edgecolor=t.border_color, labelcolor=t.default_text)
        
        from matplotlib.ticker import FuncFormatter
        self.ax.xaxis.set_major_formatter(FuncFormatter(lambda y, _: '{:.0%}'.format(y)))
        self.ax.yaxis.set_major_formatter(FuncFormatter(lambda y, _: '{:.0%}'.format(y)))
        
        self.figure.tight_layout()
        self.canvas.draw()