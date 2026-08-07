from pathlib import Path

from PyQt6.QtWidgets import (
    QMainWindow, QTabWidget, QMenuBar, QMenu,
    QFileDialog, QMessageBox, QProgressDialog
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction

from Canneberge.Ui.home_page import HomePage
from Canneberge.Ui.source_data_page import SourceDataPage
from Canneberge.Ui.gt_page import GTPage
from Canneberge.Ui.gpc_page import GPCPage, MAX_COLS as GPC_MAX_COLS
from Canneberge.Ui.subject_financials_page import SubjectFinancialsPage
from Canneberge.Ui.wacc_page import WACCPage
from Canneberge.Ui.dcf_page import DCFPage
from Canneberge.Ui.nwc_page import NWCPage
from Canneberge.Ui.private_financials_input_page import PrivateFinancialsInputPage
from Canneberge.Ui.projection_module_page import ProjectionModulePage
from Canneberge.app_state import PrivateFinancials, ProjectionData, Transaction
from Canneberge.utils.session import (
    save_session, load_session, list_sessions, SESSION_DIR
)
from typing import Optional


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Canneberge")
        self.setGeometry(100, 100, 1500, 850)

        # Shared state
        self._private_financials = PrivateFinancials()
        self._projection_data = ProjectionData()
        self._stockanalysis_results = {}
        self._current_session_path: Optional[Path] = None

        self.tabs = QTabWidget()

        # Pages
        self.home_page = HomePage()
        self.home_page.set_private_financials_callback(
            self._open_private_financials_dialog
        )
        self.home_page.set_projection_module_callback(
            self._open_projection_module_dialog
        )

        # Projection Years is shared between Home, DCF, and NWC.
        # Historical Years on NWC remains local/unlinked.
        self.home_page.projection_years_spin.valueChanged.connect(
            self._on_home_projection_years_changed
        )

        self.source_data_page = SourceDataPage(
            get_project_inputs_callback=self.home_page.get_project_inputs
        )

        # When Source Data finishes refreshing, NWC must recalculate
        # before DCF, because DCF pulls Change in NWC from NWC.
        self.source_data_page.all_sources_finished.connect(
            self._on_source_data_refresh_finished
        )

        self.subject_financials_page = SubjectFinancialsPage(
            get_project_inputs_callback=self.home_page.get_project_inputs,
            get_stockanalysis_results_callback=self._get_stockanalysis_results,
            get_private_financials_callback=self._get_private_financials,
            get_projection_data_callback=self._get_projection_data,
        )

        self.gt_page = GTPage(
            get_project_inputs_callback=self.home_page.get_project_inputs,
            get_stockanalysis_results_callback=self._get_stockanalysis_results,
            get_private_financials_callback=self._get_private_financials,
            get_subject_debt=self.get_subject_debt,
            get_subject_metric_value=self._get_subject_metric_value,
        )

        self.gpc_page = GPCPage(
            get_project_inputs_callback=self.home_page.get_project_inputs,
            get_stockanalysis_results_callback=self._get_stockanalysis_results,
            get_marketscreener_results_callback=self._get_marketscreener_results,
            get_private_financials_callback=self._get_private_financials,
            get_subject_debt=self.get_subject_debt,
            get_subject_metric_value=self._get_subject_metric_value,
        )

        self.wacc_page = WACCPage(
            get_project_inputs_callback=self.home_page.get_project_inputs,
            get_beta_vol_results_callback=self._get_beta_vol_results,
            get_stockanalysis_results_callback=self._get_stockanalysis_results,
            get_fred_results_callback=self._get_fred_results,
        )

        self.dcf_page = DCFPage(
            get_project_inputs_callback=self.home_page.get_project_inputs,
            get_wacc_value_callback=self._get_wacc_value,
            get_subject_financials_callback=self.subject_financials_page.get_metric_value,
            get_projection_data_callback=self._get_projection_data,
            update_projection_callback=self._update_projection_controls,
            get_nwc_change_callback=self._get_nwc_change,
        )

        self.nwc_page = NWCPage(
            get_project_inputs_callback=self.home_page.get_project_inputs,
            get_subject_financials_callback=self.subject_financials_page.get_metric_value,
            get_dcf_residual_revenue_callback=self.dcf_page.get_residual_revenue,
            get_stockanalysis_results_callback=self._get_stockanalysis_results,
            update_projection_callback=self._update_projection_controls,
        )
        # Home's GPC ticker fields control which rows exist in the
        # NWC GPC section. Refresh NWC whenever a user finishes editing
        # one of those ticker fields (Enter or clicking away).
        for ticker_edit in self.home_page.gpc_ticker_edits:
            ticker_edit.editingFinished.connect(
                self.nwc_page.refresh_gpc_section
            )    
        # NWC now exists, so let NWC refresh DCF after NWC inputs change.
        self.nwc_page.set_nwc_changed_callback(self.dcf_page.refresh)

        # Initial page calculation order matters:
        # NWC calculates first, then DCF reads NWC's Change in NWC.
        self._refresh_nwc_then_dcf()

        self.tabs.addTab(self.home_page, "Home")
        self.tabs.addTab(self.source_data_page, "Source Data")
        self.tabs.addTab(self.gt_page, "GT")
        self.tabs.addTab(self.gpc_page, "GPC")
        self.tabs.addTab(self.wacc_page, "WACC")
        self.tabs.addTab(self.dcf_page, "DCF")
        self.tabs.addTab(self.nwc_page, "NWC")
        self.tabs.addTab(self.subject_financials_page, "Subject Financials")

        self.tabs.currentChanged.connect(self._on_tab_changed)
        self.setCentralWidget(self.tabs)

        self._build_menu()

    def _get_nwc_change(self, period: str) -> Optional[float]:
        """
        Safe bridge between DCFPage and NWCPage.

        DCFPage is created before NWCPage, so during DCFPage's first
        constructor recalc self.nwc_page does not exist yet. getattr()
        safely returns None at that stage. Once NWCPage exists, this
        returns its calculated raw Change in NWC for the requested
        period.
        """
        nwc_page = getattr(self, "nwc_page", None)
        if nwc_page is None:
            return None
        return nwc_page.get_changes_in_nwc(period) 

    def _refresh_nwc_then_dcf(self):
        """
        Refresh NWC first, then DCF.

        DCF depends on NWC's calculated Change in Net Working Capital.
        Therefore DCF must not be the first page recalculated after
        source data, projection data, private financials, or projection
        year counts change.
        """
        if hasattr(self, "nwc_page"):
            # refresh_gpc_section() also recalculates the NWC page.
            # It rebuilds the GPC ticker rows only if Home's GPC ticker
            # list changed; otherwise it just recalculates existing rows.
            self.nwc_page.refresh_gpc_section(force=False)

        if hasattr(self, "dcf_page"):
            self.dcf_page.refresh()

    def _on_source_data_refresh_finished(self):
        """
        Source Data just finished refreshing. Public-company financials
        may have changed, so recalculate dependent pages. NWC must run
        before DCF.
        """
        if hasattr(self, "subject_financials_page"):
            self.subject_financials_page.refresh()

        if hasattr(self, "gt_page"):
            self.gt_page._recalculate()

        if hasattr(self, "gpc_page"):
            self.gpc_page._recalculate()

        if hasattr(self, "wacc_page"):
            self.wacc_page._recalculate()

        self._refresh_nwc_then_dcf()   

    def _on_home_projection_years_changed(self, value: int):
        """
        Home-page Projection Years changed by the user.
        Push the new shared projection-year count everywhere that is
        supposed to track it. NWC Historical Years is intentionally
        NOT touched here.
        """
        self._update_projection_controls(
            self.home_page.historical_years_spin.value(),
            value,
        )

    def _build_menu(self):
        menubar = self.menuBar()
        file_menu = menubar.addMenu("File")

        save_action = QAction("Save Session", self)
        save_action.setShortcut("Ctrl+S")
        save_action.triggered.connect(self._on_save_session)
        file_menu.addAction(save_action)

        save_as_action = QAction("Save Session As...", self)
        save_as_action.setShortcut("Ctrl+Shift+S")
        save_as_action.triggered.connect(self._on_save_session_as)
        file_menu.addAction(save_as_action)

        load_action = QAction("Load Session...", self)
        load_action.setShortcut("Ctrl+O")
        load_action.triggered.connect(self._on_load_session)
        file_menu.addAction(load_action)

        file_menu.addSeparator()

        quit_action = QAction("Quit", self)
        quit_action.setShortcut("Ctrl+Q")
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

    def _on_tab_changed(self, index: int):
        if self.tabs.widget(index) is self.subject_financials_page:
            self.subject_financials_page.refresh()
        if self.tabs.widget(index) is self.gt_page:
            self.gt_page._recalculate()
        if self.tabs.widget(index) is self.gpc_page:
            self.gpc_page._recalculate()
        if self.tabs.widget(index) is self.wacc_page:
            self.wacc_page._recalculate()
        if self.tabs.widget(index) is self.dcf_page:
            self._refresh_nwc_then_dcf()
        if self.tabs.widget(index) is self.nwc_page:
            self.nwc_page._recalculate()

    def _open_private_financials_dialog(self):
        inputs = self.home_page.get_project_inputs()
        dialog = PrivateFinancialsInputPage(
            private_financials=self._private_financials,
            hist_years=inputs.historical_years,
            last_fiscal_quarter=inputs.last_fiscal_quarter,
            parent=self,
        )
        if dialog.exec():
            self.subject_financials_page.refresh()
            self.gt_page._recalculate()
            self.gpc_page._recalculate()
            self._refresh_nwc_then_dcf()
    def _open_projection_module_dialog(self):
        dialog = ProjectionModulePage(
            projection_data=self._projection_data,
            get_project_inputs=self.home_page.get_project_inputs,
            get_marketscreener_results=self._get_marketscreener_results,
            get_subject_historical_line=self._get_subject_historical_line,
            parent=self,
        )
        if dialog.exec():
            self.subject_financials_page.refresh()
            self.gt_page._recalculate()
            self.gpc_page._recalculate()
            self._refresh_nwc_then_dcf()

    def _get_stockanalysis_results(self) -> dict:
        return self.source_data_page.all_results.get("stockanalysis", {})

    def _get_marketscreener_results(self) -> list:
        return self.source_data_page.all_results.get("marketscreener", [])

    def _get_beta_vol_results(self) -> list:
        return self.source_data_page.all_results.get("beta_vol", [])

    def _get_fred_results(self) -> list:
        return self.source_data_page.all_results.get("fred", [])

    def _get_private_financials(self) -> PrivateFinancials:
        return self._private_financials

    def _get_projection_data(self) -> ProjectionData:
        return self._projection_data

    def _update_projection_controls(self, hist_years: int, proj_years: int):
        """
        Shared sync point for projection years.

        - Home Projection Years is the shared source that ProjectInputs
          exposes to the rest of the app.
        - DCF can change it via its dialog.
        - NWC can change it via its own Projection Years spinbox.
        - NWC Historical Years remains local/unlinked and is NOT synced.
        """
        # Keep existing DCF/Home historical-years behavior untouched.
        home_hist_blocked = self.home_page.historical_years_spin.blockSignals(True)
        self.home_page.historical_years_spin.setValue(hist_years)
        self.home_page.historical_years_spin.blockSignals(home_hist_blocked)

        # Shared Projection Years -> Home
        home_proj_blocked = self.home_page.projection_years_spin.blockSignals(True)
        self.home_page.projection_years_spin.setValue(proj_years)
        self.home_page.projection_years_spin.blockSignals(home_proj_blocked)

        # Shared Projection Years -> NWC visible spinbox
        if hasattr(self, "nwc_page"):
            nwc_proj_blocked = self.nwc_page.proj_years_spin.blockSignals(True)
            self.nwc_page.proj_years_spin.setValue(proj_years)
            self.nwc_page.proj_years_spin.blockSignals(nwc_proj_blocked)

        # Rebuild/recalculate any pages whose structure depends on
        # projection-year count.
        if hasattr(self, "subject_financials_page"):
            self.subject_financials_page.refresh()

        if hasattr(self, "dcf_page"):
            self.dcf_page._recalculate()

        if hasattr(self, "nwc_page"):
            self._refresh_nwc_then_dcf()

    def get_subject_debt(self) -> float:
        return self.subject_financials_page.get_subject_debt()

    def _get_subject_historical_line(self, key: str) -> dict:
        return self.subject_financials_page.get_historical_line_values(key)

    def _get_subject_historical_line(self, key: str) -> dict:
        return self.subject_financials_page.get_historical_line_values(key)

    def _get_subject_metric_value(self, key: str, period: str):
        return self.subject_financials_page.get_metric_value(key, period)

    def _get_wacc_value(self) -> Optional[float]:
        if hasattr(self, 'wacc_page'):
            self.wacc_page._recalculate()
            return self.wacc_page.wacc_value
        return None


    # ------------------------------------------------------------------
    # SAVE / LOAD
    # ------------------------------------------------------------------

    def _collect_wacc_page_state(self) -> dict:
        return {
            "beta_type": self.wacc_page.beta_type_combo.currentText(),
            "beta_frequency": self.wacc_page.beta_frequency_combo.currentText(),
            "capital_structure": self.wacc_page.capital_structure_combo.currentText(),
            "selected_debt_tic": self.wacc_page.selected_debt_tic_input.text(),
            "selected_relevered_beta": self.wacc_page.selected_relevered_beta_input.text(),
            "equity_risk_premium": self.wacc_page.input_equity_risk_premium.text(),
            "size_premium": self.wacc_page.input_size_premium.text(),
            "csrp": self.wacc_page.input_csrp.text(),
            "pretax_debt_series": self.wacc_page.pretax_debt_combo.currentText(),
            "excluded_rows": [
                chk.isChecked() for chk in self.wacc_page.tick_exclude_checks
            ],
        }

    def _apply_wacc_page_state(self, state: dict):
        if not state:
            return
        wp = self.wacc_page

        def _set_combo(combo, text):
            if text:
                idx = combo.findText(text)
                if idx >= 0:
                    combo.setCurrentIndex(idx)

        _set_combo(wp.beta_type_combo, state.get("beta_type"))
        _set_combo(wp.beta_frequency_combo, state.get("beta_frequency"))
        _set_combo(wp.capital_structure_combo, state.get("capital_structure"))
        _set_combo(wp.pretax_debt_combo, state.get("pretax_debt_series"))

        if state.get("selected_debt_tic"):
            wp.selected_debt_tic_input.setText(state["selected_debt_tic"])
        if state.get("selected_relevered_beta"):
            wp.selected_relevered_beta_input.setText(state["selected_relevered_beta"])
        if state.get("equity_risk_premium"):
            wp.input_equity_risk_premium.setText(state["equity_risk_premium"])
        if state.get("size_premium"):
            wp.input_size_premium.setText(state["size_premium"])
        if state.get("csrp"):
            wp.input_csrp.setText(state["csrp"])

        for i, checked in enumerate(state.get("excluded_rows", [])):
            if i < len(wp.tick_exclude_checks):
                wp.tick_exclude_checks[i].setChecked(checked)

        wp._recalculate()


    def _collect_gt_page_state(self) -> dict:
        return {
            "num_multiples": self.gt_page.num_multiples_spin.value(),
            "dloc": self.gt_page.dloc_input.text(),
            "metric_selections": [
                combo.currentText()
                for combo in self.gt_page.metric_combos
            ],
            "selected_low": [
                inp.text()
                for inp in self.gt_page.selected_low_inputs
            ],
            "selected_high": [
                inp.text()
                for inp in self.gt_page.selected_high_inputs
            ],
            "weights": [
                inp.text()
                for inp in self.gt_page.weight_inputs
            ],
            "excluded_rows": [
                chk.isChecked()
                for chk in self.gt_page.tx_exclude_checks
            ],
        }

    def _apply_gt_page_state(self, state: dict):
        if not state:
            return

        n = state.get("num_multiples", 3)
        self.gt_page.num_multiples_spin.setValue(n)

        dloc = state.get("dloc", "")
        if dloc:
            self.gt_page.dloc_input.setText(dloc)

        for i, text in enumerate(state.get("metric_selections", [])):
            if i < len(self.gt_page.metric_combos):
                idx = self.gt_page.metric_combos[i].findText(text)
                if idx >= 0:
                    self.gt_page.metric_combos[i].setCurrentIndex(idx)

        for i, text in enumerate(state.get("selected_low", [])):
            if i < len(self.gt_page.selected_low_inputs):
                self.gt_page.selected_low_inputs[i].setText(text)

        for i, text in enumerate(state.get("selected_high", [])):
            if i < len(self.gt_page.selected_high_inputs):
                self.gt_page.selected_high_inputs[i].setText(text)

        for i, text in enumerate(state.get("weights", [])):
            if i < len(self.gt_page.weight_inputs):
                self.gt_page.weight_inputs[i].setText(text)

        for i, checked in enumerate(state.get("excluded_rows", [])):
            if i < len(self.gt_page.tx_exclude_checks):
                self.gt_page.tx_exclude_checks[i].setChecked(checked)

    def _collect_gpc_page_state(self) -> dict:
        return {
            "num_multiples": self.gpc_page.num_multiples_spin.value(),
            "dloc": self.gpc_page.dloc_input.text(),
            "control_premium": self.gpc_page.control_premium_input.text(),
            "metric_selections": [
                combo.currentText()
                for combo in self.gpc_page.metric_combos
            ],
            "selected_low": [
                inp.text()
                for inp in self.gpc_page.selected_low_inputs
            ],
            "selected_high": [
                inp.text()
                for inp in self.gpc_page.selected_high_inputs
            ],
            "weights": [
                inp.text()
                for inp in self.gpc_page.weight_inputs
            ],
            "excluded_rows": [
                chk.isChecked()
                for chk in self.gpc_page.tick_exclude_checks
            ],
        }

    def _apply_gpc_page_state(self, state: dict):
        if not state:
            return

        n = state.get("num_multiples", GPC_MAX_COLS)
        self.gpc_page.num_multiples_spin.setValue(n)

        dloc = state.get("dloc", "")
        if dloc:
            self.gpc_page.dloc_input.setText(dloc)

        control_premium = state.get("control_premium", "")
        if control_premium:
            self.gpc_page.control_premium_input.setText(control_premium)

        for i, text in enumerate(state.get("metric_selections", [])):
            if i < len(self.gpc_page.metric_combos):
                idx = self.gpc_page.metric_combos[i].findText(text)
                if idx >= 0:
                    self.gpc_page.metric_combos[i].setCurrentIndex(idx)

        for i, text in enumerate(state.get("selected_low", [])):
            if i < len(self.gpc_page.selected_low_inputs):
                self.gpc_page.selected_low_inputs[i].setText(text)

        for i, text in enumerate(state.get("selected_high", [])):
            if i < len(self.gpc_page.selected_high_inputs):
                self.gpc_page.selected_high_inputs[i].setText(text)

        for i, text in enumerate(state.get("weights", [])):
            if i < len(self.gpc_page.weight_inputs):
                self.gpc_page.weight_inputs[i].setText(text)

        for i, checked in enumerate(state.get("excluded_rows", [])):
            if i < len(self.gpc_page.tick_exclude_checks):
                self.gpc_page.tick_exclude_checks[i].setChecked(checked)

    def _collect_projection_page_state(self) -> dict:
        pd = self._projection_data
        return {
            "revenue":             dict(pd.revenue),
            "revenue_growth":      dict(pd.revenue_growth),
            "gross_profit":        dict(pd.gross_profit),
            "gp_improvement":      dict(pd.gp_improvement),
            "ebitda":              dict(pd.ebitda),
            "ebitda_improvement":  dict(pd.ebitda_improvement),
            "da":                  dict(pd.da),
            "da_pct":              dict(pd.da_pct),
            "capex":               dict(pd.capex),
            "capex_pct":           dict(pd.capex_pct),
            "last_edited_revenue": dict(pd.last_edited_revenue),
        }

    def _apply_projection_page_state(self, state: dict):
        if not state:
            return
        pd = self._projection_data
        pd.revenue             = {k: v for k, v in state.get("revenue", {}).items()}
        pd.revenue_growth      = {k: v for k, v in state.get("revenue_growth", {}).items()}
        pd.gross_profit        = {k: v for k, v in state.get("gross_profit", {}).items()}
        pd.gp_improvement      = {k: v for k, v in state.get("gp_improvement", {}).items()}
        pd.ebitda              = {k: v for k, v in state.get("ebitda", {}).items()}
        pd.ebitda_improvement  = {k: v for k, v in state.get("ebitda_improvement", {}).items()}
        pd.da                  = {k: v for k, v in state.get("da", {}).items()}
        pd.da_pct              = {k: v for k, v in state.get("da_pct", {}).items()}
        pd.capex                = {k: v for k, v in state.get("capex", {}).items()}
        pd.capex_pct           = {k: v for k, v in state.get("capex_pct", {}).items()}
        pd.last_edited_revenue = {k: v for k, v in state.get("last_edited_revenue", {}).items()}

    def _apply_project_inputs_to_home(self, pi: dict):
        hp = self.home_page

        def _set(widget, value):
            if value is None:
                return
            from PyQt6.QtWidgets import QLineEdit, QComboBox, QSpinBox
            if isinstance(widget, QLineEdit):
                widget.setText(str(value))
            elif isinstance(widget, QComboBox):
                idx = widget.findText(str(value))
                if idx >= 0:
                    widget.setCurrentIndex(idx)
            elif isinstance(widget, QSpinBox):
                widget.setValue(int(value))

        _set(hp.client_input,          pi.get("client"))
        _set(hp.subject_name_input,    pi.get("subject_company_name"))
        _set(hp.main_title_input,      pi.get("main_title"))
        _set(hp.valuation_date_input,  pi.get("valuation_date"))
        _set(hp.numeric_scale_combo,   pi.get("numeric_scale"))
        _set(hp.draft_final_combo,     pi.get("draft_final"))
        _set(hp.standard_value_combo,  pi.get("standard_of_value"))
        _set(hp.taxable_combo,         pi.get("taxable_nontaxable"))
        _set(hp.basis_value_combo,     pi.get("basis_of_value"))
        _set(hp.company_status_combo,  pi.get("company_status"))
        _set(hp.subject_ticker_input,  pi.get("subject_ticker"))
        _set(hp.lfy_input,             pi.get("last_fiscal_year"))
        _set(hp.fq_input,              pi.get("last_fiscal_quarter"))
        _set(hp.nfy_input,             pi.get("next_fiscal_year"))
        _set(hp.nfy_1_input,           pi.get("nfy_1"))
        _set(hp.nfy_2_input,           pi.get("nfy_2"))
        _set(hp.historical_years_spin, pi.get("historical_years"))
        _set(hp.projection_years_spin, pi.get("projection_years"))

        tax = pi.get("subject_tax_rate")
        if tax is not None:
            pct = tax * 100 if tax <= 1 else tax
            hp.tax_rate_input.setText(f"{pct:.0f}%")

        tickers = pi.get("gpc_tickers", [])
        for i, edit in enumerate(hp.gpc_ticker_edits):
            if i < len(tickers):
                edit.setText(tickers[i])
                hp.gpc_name_edits[i].setText(
                    hp._resolve_company_name(tickers[i])
                )
            else:
                edit.clear()
                hp.gpc_name_edits[i].clear()

        transactions = pi.get("gt_transactions", [])
        for i, row_widgets in enumerate(hp.gt_rows):
            if i < len(transactions):
                t = transactions[i]
                row_widgets["closing_date"].setText(t.get("closing_date", ""))
                row_widgets["target"].setText(t.get("target", ""))
                row_widgets["acquirer"].setText(t.get("acquirer", ""))
                row_widgets["bev"].setText(
                    str(t["bev"]) if t.get("bev") is not None else ""
                )
                row_widgets["ttm_revenue"].setText(
                    str(t["ttm_revenue"])
                    if t.get("ttm_revenue") is not None else ""
                )
                row_widgets["ttm_ebitda"].setText(
                    str(t["ttm_ebitda"])
                    if t.get("ttm_ebitda") is not None else ""
                )
                row_widgets["ttm_ebit"].setText(
                    str(t["ttm_ebit"])
                    if t.get("ttm_ebit") is not None else ""
                )
            else:
                for widget in row_widgets.values():
                    widget.clear()

        hp._on_company_status_changed(pi.get("company_status", ""))

    def _collect_dcf_page_state(self) -> dict:
        return self.dcf_page.collect_state()

    def _apply_dcf_page_state(self, state: dict):
        self.dcf_page.apply_state(state)

    def _collect_nwc_page_state(self) -> dict:
        return self.nwc_page.collect_state()

    def _apply_nwc_page_state(self, state: dict):
        self.nwc_page.apply_state(state)

    def _on_save_session(self):
        inputs = self.home_page.get_project_inputs()
        gt_state   = self._collect_gt_page_state()
        gpc_state  = self._collect_gpc_page_state()
        proj_state = self._collect_projection_page_state()
        wacc_state = self._collect_wacc_page_state()
        dcf_state = self._collect_dcf_page_state()
        nwc_state = self._collect_nwc_page_state()

        try:
            path = save_session(
                project_inputs=inputs,
                private_financials=self._private_financials,
                gt_page_state=gt_state,
                gpc_page_state=gpc_state,
                projection_page_state=proj_state,
                wacc_page_state=wacc_state,
                dcf_page_state=dcf_state,
                nwc_page_state=nwc_state,
                filepath=self._current_session_path,
            )
            self._current_session_path = path
            self.setWindowTitle(f"Canneberge — {path.stem}")
            QMessageBox.information(
                self, "Session Saved",
                f"Session saved to:\n{path}"
            )
        except Exception as e:
            QMessageBox.critical(
                self, "Save Failed", f"Could not save session:\n{e}"
            )

    def _on_save_session_as(self):
        path_str, _ = QFileDialog.getSaveFileName(
            self, "Save Session As", str(SESSION_DIR), "JSON files (*.json)"
        )
        if not path_str:
            return

        path = Path(path_str)
        if path.suffix.lower() != ".json":
            path = path.with_suffix(".json")

        inputs = self.home_page.get_project_inputs()
        gt_state   = self._collect_gt_page_state()
        gpc_state  = self._collect_gpc_page_state()
        proj_state = self._collect_projection_page_state()
        wacc_state = self._collect_wacc_page_state()
        dcf_state = self._collect_dcf_page_state()
        nwc_state = self._collect_nwc_page_state()
        try:
            saved_path = save_session(
                project_inputs=inputs,
                private_financials=self._private_financials,
                gt_page_state=gt_state,
                gpc_page_state=gpc_state,
                projection_page_state=proj_state,
                wacc_page_state=wacc_state,
                dcf_page_state=dcf_state,
                nwc_page_state=nwc_state,
                filepath=path,
            )
            self._current_session_path = saved_path
            self.setWindowTitle(f"Canneberge — {saved_path.stem}")
            QMessageBox.information(
                self, "Session Saved",
                f"Session saved to:\n{saved_path}"
            )
        except Exception as e:
            QMessageBox.critical(
                self, "Save Failed", f"Could not save session:\n{e}"
            )

    def _on_load_session(self):
        sessions = list_sessions()

        path_str, _ = QFileDialog.getOpenFileName(
            self, "Load Session",
            str(SESSION_DIR),
            "JSON files (*.json)"
        )
        if not path_str:
            return
        filepath = Path(path_str)

        try:
            data = load_session(filepath)
        except Exception as e:
            QMessageBox.critical(
                self, "Load Failed", f"Could not load session:\n{e}"
            )
            return

        self._apply_project_inputs_to_home(data["project_inputs_raw"])
        self._private_financials = data["private_financials"]
        self._apply_gt_page_state(data["gt_page_state"])
        self._apply_gpc_page_state(data["gpc_page_state"])
        self._apply_projection_page_state(data.get("projection_page_state", {}))
        self._apply_wacc_page_state(data.get("wacc_page_state", {}))
        self._apply_dcf_page_state(data.get("dcf_page_state", {}))
        self._apply_nwc_page_state(data.get("nwc_page_state", {}))

        self.subject_financials_page.refresh()
        self.gt_page._recalculate()
        self.gpc_page._recalculate()
        self._refresh_nwc_then_dcf()

        # Block on a full source refresh before confirming the session
        # is loaded. QProgressDialog.exec() runs its own local event
        # loop, so it does NOT freeze Qt's signal processing — the
        # SourceDataWorker QThreads keep running and their signals
        # still reach _update_progress/_on_all_done while this dialog
        # is up. No Cancel button: a partial refresh mid-batch would
        # leave some sources stale with no clear recovery path, so
        # canceling isn't offered here.
        progress_dialog = QProgressDialog(
            "Refreshing all sources...", None, 0, len(self.source_data_page.SOURCES), self
        )
        progress_dialog.setWindowTitle("Loading Session")
        progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        progress_dialog.setMinimumDuration(0)
        progress_dialog.setValue(0)

        def _update_progress(completed: int, total: int, message: str):
            progress_dialog.setValue(completed)
            pct = int((completed / total) * 100) if total else 0
            progress_dialog.setLabelText(f"{message}\n\n{completed}/{total} sources complete ({pct}%)")

        def _on_all_done():
            try:
                self.source_data_page.source_progress.disconnect(_update_progress)
                self.source_data_page.all_sources_finished.disconnect(_on_all_done)
            except TypeError:
                pass  # already disconnected — harmless

            progress_dialog.setValue(len(self.source_data_page.SOURCES))
            progress_dialog.close()

            self._current_session_path = filepath
            self.setWindowTitle(f"Canneberge — {filepath.stem}")
            QMessageBox.information(
                self, "Session Loaded",
                f"Session loaded:\n{filepath.stem}"
            )

        self.source_data_page.source_progress.connect(_update_progress)
        self.source_data_page.all_sources_finished.connect(_on_all_done)

        self.source_data_page._on_refresh_all_clicked()
        progress_dialog.exec()