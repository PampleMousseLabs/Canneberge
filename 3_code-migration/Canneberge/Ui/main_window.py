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

        self.source_data_page = SourceDataPage(
            get_project_inputs_callback=self.home_page.get_project_inputs
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
        )

        self.tabs.addTab(self.home_page, "Home")
        self.tabs.addTab(self.source_data_page, "Source Data")
        self.tabs.addTab(self.gt_page, "GT")
        self.tabs.addTab(self.gpc_page, "GPC")
        self.tabs.addTab(self.wacc_page, "WACC")
        self.tabs.addTab(self.subject_financials_page, "Subject Financials")

        self.tabs.currentChanged.connect(self._on_tab_changed)
        self.setCentralWidget(self.tabs)

        self._build_menu()

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

    def _get_stockanalysis_results(self) -> dict:
        return self.source_data_page.all_results.get("stockanalysis", {})

    def _get_marketscreener_results(self) -> list:
        return self.source_data_page.all_results.get("marketscreener", [])

    def _get_beta_vol_results(self) -> list:
        return self.source_data_page.all_results.get("beta_vol", [])

    def _get_private_financials(self) -> PrivateFinancials:
        return self._private_financials

    def _get_projection_data(self) -> ProjectionData:
        return self._projection_data

    def get_subject_debt(self) -> float:
        return self.subject_financials_page.get_subject_debt()

    def _get_subject_historical_line(self, key: str) -> dict:
        return self.subject_financials_page.get_historical_line_values(key)

    def _get_subject_historical_line(self, key: str) -> dict:
        return self.subject_financials_page.get_historical_line_values(key)

    def _get_subject_metric_value(self, key: str, period: str):
        return self.subject_financials_page.get_metric_value(key, period)

    # ------------------------------------------------------------------
    # SAVE / LOAD
    # ------------------------------------------------------------------

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

    def _on_save_session(self):
        inputs = self.home_page.get_project_inputs()
        gt_state   = self._collect_gt_page_state()
        gpc_state  = self._collect_gpc_page_state()
        proj_state = self._collect_projection_page_state()

        try:
            path = save_session(
                project_inputs=inputs,
                private_financials=self._private_financials,
                gt_page_state=gt_state,
                gpc_page_state=gpc_state,
                projection_page_state=proj_state,
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

        try:
            saved_path = save_session(
                project_inputs=inputs,
                private_financials=self._private_financials,
                gt_page_state=gt_state,
                gpc_page_state=gpc_state,
                projection_page_state=proj_state,
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

        self.subject_financials_page.refresh()
        self.gt_page._recalculate()
        self.gpc_page._recalculate()

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