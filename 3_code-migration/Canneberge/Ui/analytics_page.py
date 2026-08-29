"""
analytics_page.py
Capital Structure Analytics — isolated diagnostic tab. Reads live
values from DCF/WACC/Subject Financials or automatically gathers GPC
peer metrics from StockAnalysis.
"""

from typing import Optional, Callable
from datetime import datetime

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QScrollArea, QPushButton, QLineEdit, QCheckBox, QComboBox, QFrame,
)
from PyQt6.QtCore import Qt

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from matplotlib.ticker import FuncFormatter

from Canneberge.Ui.theme import theme_manager
from Canneberge.Calculations.analytics_math import (
    compute_analytics_ratios, interpret_regime, shock_leverage,
    generate_mm_curve_data,
)


def get_bold_style() -> str:
    return theme_manager.current.bold_style()


def get_header_style() -> str:
    return theme_manager.current.header_style()


def get_input_style() -> str:
    return theme_manager.current.input_style()


def get_note_style() -> str:
    t = theme_manager.current
    return f"color: {t.note_text}; font-style: italic;"


def _parse_label(text: str) -> Optional[float]:
    if not text or text.strip() in ("-", "NA", "N/A", ""):
        return None
    raw = str(text).strip()
    is_pct = "%" in raw

    mult = 1.0
    clean_upper = raw.upper()
    if "B" in clean_upper and "BS" not in clean_upper:
        mult = 1000.0
        raw = raw.replace("B", "").replace("b", "")
    elif "M" in clean_upper:
        mult = 1.0
        raw = raw.replace("M", "").replace("m", "")

    cleaned = (
        raw.replace(",", "").replace("%", "").replace("$", "")
        .replace("(", "-").replace(")", "").strip()
    )
    try:
        val = float(cleaned)
    except (ValueError, TypeError):
        return None
    if is_pct:
        return val / 100.0
    return val * mult


def _try_get_market_cap(get_stockanalysis: Callable, ticker: str) -> Optional[float]:
    try:
        sa = get_stockanalysis() or {}
        rows = sa.get("Ratios", [])
        tick_lower = (ticker or "").strip().lower()
        for row in rows:
            if str(row.get("Ticker", "")).strip().lower() != tick_lower:
                continue
            line_item = str(row.get("Line Item", "")).strip().lower()
            if "market cap" in line_item:
                ttm_val = row.get("TTM")
                parsed = _parse_label(str(ttm_val))
                if parsed is not None:
                    return parsed
    except Exception:
        pass
    return None


def _avg_projected_row(dcf, row_label: str) -> Optional[float]:
    idx = dcf._row_idx.get(row_label)
    if idx is None:
        return None
    vals = []
    for data_idx, is_hist in enumerate(dcf._is_historical):
        if is_hist:
            continue
        if data_idx < len(dcf._headers) and dcf._headers[data_idx] == "Residual":
            continue
        lbl = dcf._calc_labels.get(idx, {}).get(data_idx)
        if lbl is None:
            continue
        v = _parse_label(lbl.text())
        if v is not None:
            vals.append(v)
    return sum(vals) / len(vals) if vals else None


class AnalyticsPage(QWidget):
    def __init__(
        self,
        get_dcf_page: Callable,
        get_wacc_page: Callable,
        get_subject_financials_callback: Callable,
        get_project_inputs_callback: Callable,
        get_stockanalysis_results_callback: Callable,
    ):
        super().__init__()
        self.get_dcf_page = get_dcf_page
        self.get_wacc_page = get_wacc_page
        self.get_subject_financials = get_subject_financials_callback
        self.get_project_inputs = get_project_inputs_callback
        self.get_stockanalysis = get_stockanalysis_results_callback

        self._cached_bev_fcff: Optional[float] = None
        self._cached_equity_fcfe: Optional[float] = None
        self._last_computed_at: Optional[str] = None

        self._header_labels = []
        self._bold_labels = []
        self._val_labels = {}

        self._build_ui()
        theme_manager.theme_changed.connect(self._apply_theme)

    def _apply_theme(self, theme=None):
        t = theme_manager.current
        for lbl in self._header_labels:
            lbl.setStyleSheet(get_header_style())
        for lbl in self._bold_labels:
            lbl.setStyleSheet(get_bold_style())

        self.btn_compute.setStyleSheet(get_input_style())
        self.combo_entity.setStyleSheet(get_input_style())
        self.inp_market_cap.setStyleSheet(get_input_style())
        self.chart_mode_combo.setStyleSheet(get_input_style())
        for w in (self.inp_rc, self.inp_fv_debt, self.inp_k_mu,
                  self.inp_k_theta, self.inp_k_gamma, self.inp_k_wdgap):
            w.setStyleSheet(get_input_style())

        self.figure.patch.set_facecolor(t.window_bg)
        self.refresh()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 10, 10, 10)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        main_layout = QVBoxLayout(container)

        hdr = QLabel("Capital Structure Analytics: FCFF vs FCFE Reconciliation")
        hdr.setStyleSheet(get_header_style())
        self._header_labels.append(hdr)
        main_layout.addWidget(hdr)

        top_row = QHBoxLayout()
        top_row.addWidget(QLabel("Select Entity:"))
        self.combo_entity = QComboBox()
        self.combo_entity.setStyleSheet(get_input_style())
        self.combo_entity.setMinimumWidth(160)
        self.combo_entity.currentTextChanged.connect(self._on_entity_changed)
        top_row.addWidget(self.combo_entity)
        top_row.addSpacing(16)

        self.btn_compute = QPushButton("Compute Both Methods (FCFF + FCFE)")
        self.btn_compute.setStyleSheet(get_input_style())
        self.btn_compute.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_compute.clicked.connect(self._on_compute_both_clicked)
        top_row.addWidget(self.btn_compute)

        self.lbl_last_computed = QLabel("Not yet computed — click to populate.")
        self.lbl_last_computed.setStyleSheet(get_note_style())
        top_row.addWidget(self.lbl_last_computed)

        top_row.addSpacing(20)
        top_row.addWidget(QLabel("Market Cap override:"))
        self.inp_market_cap = QLineEdit("")
        self.inp_market_cap.setPlaceholderText("e.g. 115000")
        self.inp_market_cap.setFixedWidth(110)
        self.inp_market_cap.setStyleSheet(get_input_style())
        self.inp_market_cap.editingFinished.connect(self.refresh)
        top_row.addWidget(self.inp_market_cap)

        top_row.addStretch()
        main_layout.addLayout(top_row)

        h_split = QHBoxLayout()

        left_panel = QVBoxLayout()
        left_panel.addWidget(self._build_inputs_grid())
        left_panel.addWidget(self._build_ratios_grid())

        self.lbl_notes = QLabel("Click 'Compute Both Methods' to populate diagnostics.")
        self.lbl_notes.setWordWrap(True)
        self.lbl_notes.setStyleSheet(get_note_style())
        left_panel.addWidget(self.lbl_notes)

        left_panel.addWidget(self._build_advanced_panel())
        left_panel.addStretch()
        h_split.addLayout(left_panel, 1)

        right_panel = QVBoxLayout()
        chart_ctrl_row = QHBoxLayout()
        chart_ctrl_row.addWidget(QLabel("Chart Mode:"))
        self.chart_mode_combo = QComboBox()
        self.chart_mode_combo.addItems([
            "Friction Analysis (3-Panel)",
            "Illustrative MM Curve (Not Model-Derived)",
        ])
        self.chart_mode_combo.setStyleSheet(get_input_style())
        self.chart_mode_combo.currentTextChanged.connect(lambda _t: self._plot_chart())
        chart_ctrl_row.addWidget(self.chart_mode_combo)
        chart_ctrl_row.addStretch()
        right_panel.addLayout(chart_ctrl_row)

        self.figure = Figure(figsize=(7, 8))
        self.canvas = FigureCanvasQTAgg(self.figure)
        right_panel.addWidget(self.canvas)

        self.lbl_chart_caption = QLabel("")
        self.lbl_chart_caption.setWordWrap(True)
        self.lbl_chart_caption.setStyleSheet(get_note_style())
        right_panel.addWidget(self.lbl_chart_caption)

        h_split.addLayout(right_panel, 1)
        main_layout.addLayout(h_split)

        scroll.setWidget(container)
        outer.addWidget(scroll)

    def _build_inputs_grid(self) -> QWidget:
        w = QWidget()
        g = QGridLayout(w)
        lbl = QLabel("Live Model Inputs")
        lbl.setStyleSheet(get_header_style())
        self._header_labels.append(lbl)
        g.addWidget(lbl, 0, 0, 1, 2)

        self.input_keys = [
            "Enterprise Value (FCFF)", "Equity Value (FCFE)", "Equity Value (FCFF Bridge)",
            "Market Cap", "Book Debt (TTM)", "Cash (TTM)", "WACC", "Cost of Equity (Ke)",
            "After-Tax Cost of Debt (Kd)", "Book Wd (TIC)", "Market Wd (implied)",
            "Avg Projected FCFF", "Avg Projected Interest Expense",
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
            ("λ (Net Leverage)", "Net Debt / BEV"),
            ("R (Residual)", "Equity(FCFF) − Equity(FCFE)"),
            ("R% (Pct Residual)", "R / avg(Equity)"),
            ("Wd Gap", "|Book Wd − Market Wd|"),
            ("MM Spread Gap", "|(Ke−WACC)/Wd − (Ke−Kd)|"),
            ("θ (Debt Service)", "Avg Interest / Avg FCFF"),
            ("γ (Cash Drag)", "(Cash/AvgEq) × (Ke − rc)"),
            ("μ (Debt Mark)", "Book Debt / FV Debt (proxy = 1.0)"),
            ("Ψ (Composite Alarm)", "|λ| × (1 + weighted frictions)"),
        ]

        g.addWidget(QLabel("Metric", styleSheet=get_bold_style()), 1, 0)
        g.addWidget(QLabel("Formula", styleSheet=get_bold_style()), 1, 1)
        g.addWidget(QLabel("Value", styleSheet=get_bold_style()), 1, 2)

        for i, (name, form) in enumerate(self.ratio_keys, 2):
            g.addWidget(QLabel(name), i, 0)
            flbl = QLabel(form)
            flbl.setStyleSheet(get_note_style())
            g.addWidget(flbl, i, 1)
            vlbl = QLabel("-")
            vlbl.setAlignment(Qt.AlignmentFlag.AlignRight)
            vlbl.setStyleSheet(get_bold_style())
            self._bold_labels.append(vlbl)
            self._val_labels[name] = vlbl
            g.addWidget(vlbl, i, 2)
        return w

    def _build_advanced_panel(self) -> QWidget:
        wrap = QWidget()
        wrap_layout = QVBoxLayout(wrap)
        wrap_layout.setContentsMargins(0, 0, 0, 0)

        self.btn_advanced = QPushButton("Show Advanced Overrides")
        self.btn_advanced.setCheckable(True)
        self.btn_advanced.setStyleSheet(get_input_style())
        self.btn_advanced.clicked.connect(self._toggle_advanced)
        wrap_layout.addWidget(self.btn_advanced)

        self.adv_widget = QWidget()
        adv = QGridLayout(self.adv_widget)

        adv.addWidget(QLabel("Cash Interest Yield (rc):"), 0, 0)
        self.inp_rc = QLineEdit("4.5%")
        self.inp_rc.setStyleSheet(get_input_style())
        self.inp_rc.editingFinished.connect(self.refresh)
        adv.addWidget(self.inp_rc, 0, 1)

        self.chk_fv_debt = QCheckBox("Override Fair Value of Debt (default = Book Debt proxy)")
        self.chk_fv_debt.stateChanged.connect(self.refresh)
        adv.addWidget(self.chk_fv_debt, 1, 0, 1, 2)
        self.inp_fv_debt = QLineEdit("")
        self.inp_fv_debt.setPlaceholderText("e.g. 6200")
        self.inp_fv_debt.setStyleSheet(get_input_style())
        self.inp_fv_debt.editingFinished.connect(self.refresh)
        adv.addWidget(self.inp_fv_debt, 2, 0, 1, 2)

        adv.addWidget(QLabel("Ψ Weight — Debt Mark (k_mu):"), 3, 0)
        self.inp_k_mu = QLineEdit("1.00")
        self.inp_k_mu.setStyleSheet(get_input_style())
        self.inp_k_mu.editingFinished.connect(self.refresh)
        adv.addWidget(self.inp_k_mu, 3, 1)

        adv.addWidget(QLabel("Ψ Weight — Debt Service (k_theta):"), 4, 0)
        self.inp_k_theta = QLineEdit("1.00")
        self.inp_k_theta.setStyleSheet(get_input_style())
        self.inp_k_theta.editingFinished.connect(self.refresh)
        adv.addWidget(self.inp_k_theta, 4, 1)

        adv.addWidget(QLabel("Ψ Weight — Cash Drag (k_gamma):"), 5, 0)
        self.inp_k_gamma = QLineEdit("1.00")
        self.inp_k_gamma.setStyleSheet(get_input_style())
        self.inp_k_gamma.editingFinished.connect(self.refresh)
        adv.addWidget(self.inp_k_gamma, 5, 1)

        adv.addWidget(QLabel("Ψ Weight — Wd Gap (k_wdgap):"), 6, 0)
        self.inp_k_wdgap = QLineEdit("1.00")
        self.inp_k_wdgap.setStyleSheet(get_input_style())
        self.inp_k_wdgap.editingFinished.connect(self.refresh)
        adv.addWidget(self.inp_k_wdgap, 6, 1)

        note = QLabel(
            "Note: Fair Value of Debt currently defaults to Book Debt "
            "(μ = 1.0 by construction). A real mark-to-market debt calc "
            "is deferred to a future Debt & Derivatives build."
        )
        note.setWordWrap(True)
        note.setStyleSheet(get_note_style())
        adv.addWidget(note, 7, 0, 1, 2)

        self.adv_widget.setVisible(False)
        wrap_layout.addWidget(self.adv_widget)
        return wrap

    def _toggle_advanced(self):
        self.adv_widget.setVisible(self.btn_advanced.isChecked())

    def _populate_entity_combo(self):
        inputs = self.get_project_inputs()
        subj_name = f"Subject: {inputs.subject_company_name or 'Target'}"
        gpcs = list(getattr(inputs, "active_public_tickers", []) or inputs.gpc_tickers or [])

        current = self.combo_entity.currentText()
        self.combo_entity.blockSignals(True)
        self.combo_entity.clear()
        self.combo_entity.addItem(subj_name, userData="SUBJECT")
        for gpc in gpcs:
            if gpc:
                self.combo_entity.addItem(f"GPC: {gpc.upper()}", userData=gpc.upper())

        idx = self.combo_entity.findText(current)
        if idx >= 0:
            self.combo_entity.setCurrentIndex(idx)
        self.combo_entity.blockSignals(False)

    def _on_entity_changed(self, _text: str):
        is_subj = self.combo_entity.currentData() == "SUBJECT"
        self.btn_compute.setEnabled(is_subj)
        self.refresh()

    def _on_compute_both_clicked(self):
        dcf = self.get_dcf_page()
        orig = dcf._cash_flows_to

        dcf._cash_flows_to = "FCFF"
        dcf._recalculate()
        self._cached_bev_fcff = _parse_label(dcf.bridge_fv_base_label.text())

        dcf._cash_flows_to = "FCFE"
        dcf._recalculate()
        self._cached_equity_fcfe = _parse_label(dcf.bridge_fv_base_label.text())

        dcf._cash_flows_to = orig
        dcf._recalculate()

        self._last_computed_at = datetime.now().strftime("%H:%M:%S")
        self.lbl_last_computed.setText(f"Last computed: {self._last_computed_at}")
        self.refresh()

    def _gather_gpc_inputs(self, ticker: str) -> dict:
        sa = self.get_stockanalysis() or {}
        inputs = self.get_project_inputs()
        wacc_page = self.get_wacc_page()

        st_debt = 0.0
        lt_debt = 0.0
        cash = 0.0
        for row in sa.get("BS", []):
            if str(row.get("Ticker", "")).strip().upper() == ticker:
                item = str(row.get("Line Item", "")).strip().lower()
                if "short-term debt" in item or "current portion" in item:
                    st_debt += _parse_label(str(row.get("TTM"))) or 0.0
                elif "long-term debt" in item:
                    lt_debt += _parse_label(str(row.get("TTM"))) or 0.0
                elif "cash & equivalents" in item or "short-term investments" in item:
                    cash += _parse_label(str(row.get("TTM"))) or 0.0

        book_debt = st_debt + lt_debt
        market_cap = _try_get_market_cap(self.get_stockanalysis, ticker) or _parse_label(self.inp_market_cap.text()) or 100000.0

        avg_interest = 0.0
        avg_fcff = 0.0
        for row in sa.get("IS", []):
            if str(row.get("Ticker", "")).strip().upper() == ticker:
                item = str(row.get("Line Item", "")).strip().lower()
                if "interest expense" in item:
                    avg_interest = abs(_parse_label(str(row.get("TTM"))) or 0.0)
                elif "operating income" in item or "ebit" in item:
                    ebit = _parse_label(str(row.get("TTM"))) or 0.0
                    avg_fcff = ebit * (1.0 - (inputs.subject_tax_rate or 0.25))

        net_debt = book_debt - cash
        bev_fcff = market_cap + max(0.0, net_debt)
        equity_fcfe = market_cap
        equity_fcff = bev_fcff - net_debt

        wacc = getattr(wacc_page, "wacc_value", None) or 0.10
        ke = getattr(wacc_page, "ke_value", None) or 0.12
        kd_after_tax = _parse_label(getattr(wacc_page, "lbl_after_tax_cost_of_debt", QLabel()).text()) or 0.038
        wd_book = book_debt / (book_debt + market_cap) if (book_debt + market_cap) > 0 else 0.20

        rc = _parse_label(self.inp_rc.text()) or 0.045
        return {
            "bev_fcff": bev_fcff,
            "equity_fcfe": equity_fcfe,
            "equity_fcff": equity_fcff,
            "book_debt": book_debt,
            "cash": cash,
            "market_cap": market_cap,
            "wacc": wacc,
            "ke": ke,
            "kd_after_tax": kd_after_tax,
            "wd_book": wd_book,
            "tax_rate": inputs.subject_tax_rate,
            "avg_fcff": max(1.0, avg_fcff),
            "avg_interest": avg_interest,
            "rc": rc,
            "fv_debt_override": None,
            "k_mu": 1.0, "k_theta": 1.0, "k_gamma": 1.0, "k_wdgap": 1.0,
        }

    def _gather_inputs(self) -> dict:
        entity = self.combo_entity.currentData()
        if entity and entity != "SUBJECT":
            return self._gather_gpc_inputs(entity)

        dcf = self.get_dcf_page()
        wacc_page = self.get_wacc_page()
        inputs = self.get_project_inputs()

        book_debt = (
            (self.get_subject_financials("st_debt", "TTM") or 0.0)
            + (self.get_subject_financials("current_ltd", "TTM") or 0.0)
            + (self.get_subject_financials("lt_debt", "TTM") or 0.0)
        )
        cash = self.get_subject_financials("cash", "TTM") or 0.0

        market_cap = _try_get_market_cap(self.get_stockanalysis, inputs.subject_ticker)
        if market_cap is None:
            market_cap = _parse_label(self.inp_market_cap.text())

        wacc = getattr(wacc_page, "wacc_value", None)
        ke = getattr(wacc_page, "ke_value", None)
        kd_after_tax = _parse_label(wacc_page.lbl_after_tax_cost_of_debt.text())
        wd_book = _parse_label(wacc_page.lbl_debt_pct_capital.text())

        avg_fcff = _avg_projected_row(dcf, "Free Cash Flow")
        avg_interest_raw = _avg_projected_row(dcf, "Net Interest Expense")
        avg_interest = abs(avg_interest_raw) if avg_interest_raw is not None else None

        equity_fcff = None
        if self._cached_bev_fcff is not None:
            equity_fcff = self._cached_bev_fcff - book_debt + cash

        rc = _parse_label(self.inp_rc.text()) or 0.045

        fv_debt_override = None
        if self.chk_fv_debt.isChecked():
            fv_debt_override = _parse_label(self.inp_fv_debt.text())

        def _k(inp, default=1.0):
            v = _parse_label(inp.text())
            return v if v is not None else default

        return {
            "bev_fcff": self._cached_bev_fcff,
            "equity_fcfe": self._cached_equity_fcfe,
            "equity_fcff": equity_fcff,
            "book_debt": book_debt,
            "cash": cash,
            "market_cap": market_cap,
            "wacc": wacc,
            "ke": ke,
            "kd_after_tax": kd_after_tax,
            "wd_book": wd_book,
            "tax_rate": inputs.subject_tax_rate,
            "avg_fcff": avg_fcff,
            "avg_interest": avg_interest,
            "rc": rc,
            "fv_debt_override": fv_debt_override,
            "k_mu": _k(self.inp_k_mu),
            "k_theta": _k(self.inp_k_theta),
            "k_gamma": _k(self.inp_k_gamma),
            "k_wdgap": _k(self.inp_k_wdgap),
        }

    def refresh(self):
        self._populate_entity_combo()
        data = self._gather_inputs()

        def setv(key, v, is_pct=False, decimals=0):
            lbl = self._val_labels.get(key)
            if lbl is None:
                return
            if v is None:
                lbl.setText("-")
            elif is_pct:
                lbl.setText(f"{v*100:.2f}%")
            else:
                lbl.setText(f"{v:,.{decimals}f}")

        setv("Enterprise Value (FCFF)", data["bev_fcff"])
        setv("Equity Value (FCFE)", data["equity_fcfe"])
        setv("Equity Value (FCFF Bridge)", data["equity_fcff"])
        setv("Market Cap", data["market_cap"])
        setv("Book Debt (TTM)", data["book_debt"])
        setv("Cash (TTM)", data["cash"])
        setv("WACC", data["wacc"], True)
        setv("Cost of Equity (Ke)", data["ke"], True)
        setv("After-Tax Cost of Debt (Kd)", data["kd_after_tax"], True)
        setv("Book Wd (TIC)", data["wd_book"], True)
        setv("Avg Projected FCFF", data["avg_fcff"])
        setv("Avg Projected Interest Expense", data["avg_interest"])

        ratios = compute_analytics_ratios(**data)
        setv("Market Wd (implied)", ratios["wd_market"], True)

        setv("λ (Net Leverage)", ratios["lam"], True)
        setv("R (Residual)", ratios["residual"])
        setv("R% (Pct Residual)", ratios["pct_residual"], True)
        setv("Wd Gap", ratios["wd_gap"], True)
        setv("MM Spread Gap", ratios["mm_gap"], True)
        setv("θ (Debt Service)", ratios["theta"], True)
        setv("γ (Cash Drag)", ratios["gamma"], True)
        if ratios["mu"] is not None:
            self._val_labels["μ (Debt Mark)"].setText(f"{ratios['mu']:.2f}x")
        setv("Ψ (Composite Alarm)", ratios["psi"], True)

        regime = interpret_regime(ratios)
        self.lbl_notes.setText(regime["notes"])

        self._last_ratios = ratios
        self._last_data = data
        self._plot_chart()

    def _plot_chart(self):
        if not hasattr(self, "_last_data"):
            return
        data = self._last_data
        ratios = self._last_ratios
        t = theme_manager.current
        mode = self.chart_mode_combo.currentText()

        self.figure.clear()
        self.figure.patch.set_facecolor(t.window_bg)

        if mode.startswith("Illustrative"):
            self.lbl_chart_caption.setText(
                "ILLUSTRATIVE ONLY — textbook MM Proposition II on cost "
                "of capital. Anchored to current (Ke, Kd, Wd) but does "
                "NOT plot firm value and is NOT derived from this "
                "model's FCFF/FCFE outputs beyond that single anchor."
            )
            ax = self.figure.add_subplot(111)
            ax.set_facecolor(t.window_bg)
            if data.get("ke") is None or data.get("kd_after_tax") is None:
                ax.text(0.5, 0.5, "Insufficient WACC inputs", ha="center",
                        va="center", transform=ax.transAxes, color=t.default_text)
            else:
                curve = generate_mm_curve_data(
                    data["ke"], data["kd_after_tax"], data["wd_book"] or 0.0
                )
                ax.plot(curve["x_wd"], curve["y_ke"], label="Ke", color=t.chart_edge, lw=2)
                ax.plot(curve["x_wd"], curve["y_wacc"], label="WACC", color=t.chart_fill, lw=3)
                ax.plot(curve["x_wd"], curve["y_kd"], label="Kd (after-tax)",
                        color=t.chart_grid, lw=2, linestyle="--")
                if data.get("wd_book") is not None:
                    ax.axvline(data["wd_book"], color=t.chart_share_price,
                               linestyle="--", label=f"Book Wd ({data['wd_book']*100:.1f}%)")
                ax.set_xlabel("Debt to Capital (Wd)", color=t.default_text)
                ax.set_ylabel("Cost of Capital", color=t.default_text)
                ax.tick_params(colors=t.chart_axis_label)
                for spine in ax.spines.values():
                    spine.set_color(t.chart_grid)
                ax.legend(fontsize=8, facecolor=t.window_bg, edgecolor=t.border_color, labelcolor=t.default_text)
                ax.xaxis.set_major_formatter(FuncFormatter(lambda y, _: f"{y*100:.0f}%"))
                ax.yaxis.set_major_formatter(FuncFormatter(lambda y, _: f"{y*100:.0f}%"))
            self.figure.tight_layout()
            self.canvas.draw()
            return

        self.lbl_chart_caption.setText(
            "X-axis is Net Leverage λ = Net Debt / BEV. "
            "Curves are an approximate re-discount of current BEV / FCFE equity "
            "across hypothetical λ — not a full DCF re-run. "
            "Dashed vertical line = today's live λ position."
        )

        shock = shock_leverage(data)
        current_lam = ratios.get("lam")
        live_r_pct = ratios.get("pct_residual")

        ax_a = self.figure.add_subplot(311)
        ax_b = self.figure.add_subplot(312)
        ax_c = self.figure.add_subplot(313)

        for ax in (ax_a, ax_b, ax_c):
            ax.set_facecolor(t.window_bg)
            ax.tick_params(colors=t.chart_axis_label)
            for spine in ax.spines.values():
                spine.set_color(t.chart_grid)

        c_fcff = t.chart_fill
        c_fcfe = t.chart_edge
        c_resid = t.chart_range
        c_marker = t.chart_share_price

        pct_fmt = FuncFormatter(lambda y, _: f"{y * 100:.0f}%")

        if shock["x_lam"]:
            pct_res_pct = [
                (v * 100.0) if v is not None else None
                for v in shock["y_pct_residual"]
            ]
            ax_a.plot(
                shock["x_lam"], pct_res_pct,
                color=c_resid, lw=2.0, label="Approx |R| / Equity",
            )
            if current_lam is not None:
                ax_a.axvline(
                    current_lam, color=c_marker, linestyle="--", lw=1.5,
                    label=f"Today's λ = {current_lam * 100:.2f}%",
                )
            if live_r_pct is not None:
                ax_a.axhline(
                    abs(live_r_pct) * 100.0, color=c_fcff, linestyle=":",
                    lw=1.2, label=f"Live |R%| = {abs(live_r_pct) * 100:.2f}%",
                )
            ax_a.set_title("Panel A: Method Gap vs Net Leverage (λ)", fontsize=9, color=t.default_text)
            ax_a.set_xlabel("Net Leverage λ = Net Debt / BEV", fontsize=8, color=t.default_text)
            ax_a.set_ylabel("|R| / Equity (%)", fontsize=8, color=t.default_text)
            ax_a.xaxis.set_major_formatter(pct_fmt)
            ax_a.legend(fontsize=7, loc="upper left", facecolor=t.window_bg, edgecolor=t.border_color, labelcolor=t.default_text)
            ax_a.grid(True, alpha=0.25, color=t.chart_grid)

            ax_b.plot(
                shock["x_lam"], shock["y_equity_fcff"],
                color=c_fcff, lw=2.0, label="Equity via FCFF bridge",
            )
            ax_b.plot(
                shock["x_lam"], shock["y_equity_fcfe"],
                color=c_fcfe, lw=2.0, linestyle="--",
                label="Equity via FCFE",
            )
            if current_lam is not None:
                ax_b.axvline(
                    current_lam, color=c_marker, linestyle="--", lw=1.5,
                    label=f"Today's λ = {current_lam * 100:.2f}%",
                )
            ax_b.set_title("Panel B: Equity Value vs Net Leverage (λ)", fontsize=9, color=t.default_text)
            ax_b.set_xlabel("Net Leverage λ = Net Debt / BEV", fontsize=8, color=t.default_text)
            ax_b.set_ylabel("Equity Value", fontsize=8, color=t.default_text)
            ax_b.xaxis.set_major_formatter(pct_fmt)
            ax_b.legend(fontsize=7, loc="upper right", facecolor=t.window_bg, edgecolor=t.border_color, labelcolor=t.default_text)
            ax_b.grid(True, alpha=0.25, color=t.chart_grid)
        else:
            for ax in (ax_a, ax_b):
                ax.text(
                    0.5, 0.5,
                    "No curve data — click Compute Both Methods",
                    ha="center", va="center", transform=ax.transAxes, fontsize=8, color=t.default_text
                )
                ax.set_xlabel("Net Leverage λ = Net Debt / BEV", fontsize=8, color=t.default_text)

        bar_labels = ["|λ|", "θ", "γ", "|μ−1|", "Wd Gap"]
        bar_vals = [
            abs(ratios["lam"]) if ratios["lam"] is not None else 0.0,
            abs(ratios["theta"]) if ratios["theta"] is not None else 0.0,
            abs(ratios["gamma"]) if ratios["gamma"] is not None else 0.0,
            abs(ratios["mu"] - 1.0) if ratios["mu"] is not None else 0.0,
            abs(ratios["wd_gap"]) if ratios["wd_gap"] is not None else 0.0,
        ]
        colors_c = [c_fcff, c_fcfe, c_resid, t.chart_grid, c_marker]
        ax_c.bar(
            bar_labels, [v * 100.0 for v in bar_vals],
            color=colors_c[: len(bar_labels)], edgecolor=t.chart_edge,
        )
        ax_c.set_title("Panel C: Today's Friction Components (feed Ψ)", fontsize=9, color=t.default_text)
        ax_c.set_ylabel("Magnitude (%)", fontsize=8, color=t.default_text)
        ax_c.grid(True, axis="y", alpha=0.25, color=t.chart_grid)

        self.figure.tight_layout()
        self.canvas.draw()