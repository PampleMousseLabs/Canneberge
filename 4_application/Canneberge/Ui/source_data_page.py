import pandas as pd

from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QDoubleSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QButtonGroup,
)
from PyQt6.QtCore import Qt, pyqtSignal

from Canneberge.Workers.source_data_worker import SourceDataWorker
from Canneberge.Ui.theme import theme_manager


class SourceDataPage(QWidget):
    SOURCES = ["stockanalysis", "marketscreener", "fred", "beta_vol"]
    SOURCE_LABELS = {
        "stockanalysis": "StockAnalysis",
        "marketscreener": "MarketScreener",
        "fred": "FRED",
        "beta_vol": "Beta/Vol (Yahoo)",
        "live_marks": "Live Marks (yfinance + FRED)",
    }

    # Emitted every time any single worker reports a progress message,
    # while a "refresh all" batch is in flight. Args: (completed_count,
    # total_count, latest_status_message). Used by callers (e.g. the
    # session-load progress dialog in main_window.py) that need to
    # show batch-level progress, not just per-source status.
    source_progress = pyqtSignal(int, int, str)

    # Emitted once, when every source in a "refresh all" batch has
    # finished (success or error) — not emitted for a single-source
    # refresh triggered via one of the individual Refresh buttons.
    all_sources_finished = pyqtSignal()

    def __init__(self, get_project_inputs_callback):
        super().__init__()
        self.get_project_inputs_callback = get_project_inputs_callback
        self.workers = {}
        self.all_results = {}
        self.current_source = "stockanalysis"
        self.current_statement = "IS"
        self._pending_batch_sources = set()
        self._build_ui()
        theme_manager.theme_changed.connect(self._apply_theme)
        self._apply_theme(theme_manager.current)

    def _build_ui(self):
        layout = QVBoxLayout()

        # Refresh buttons
        refresh_layout = QHBoxLayout()
        self.refresh_buttons = {}

        # Refresh All button
        refresh_all_btn = QPushButton("Refresh All Sources")
        refresh_all_btn.clicked.connect(self._on_refresh_all_clicked)
        refresh_layout.addWidget(refresh_all_btn)

        # Live Marks Button
        self.btn_live_marks = QPushButton("⚡ Update Live Marks (2s)")
        self.btn_live_marks.clicked.connect(self._on_refresh_live_marks_clicked)
        refresh_layout.addWidget(self.btn_live_marks)

        for source in self.SOURCES:
            btn = QPushButton(f"Refresh {self.SOURCE_LABELS[source]}")
            btn.clicked.connect(
                lambda checked, s=source: self._on_refresh_clicked(s)
            )
            self.refresh_buttons[source] = btn
            refresh_layout.addWidget(btn)

        refresh_layout.addStretch()
        layout.addLayout(refresh_layout)

        # View controls
        view_layout = QHBoxLayout()
        view_layout.addWidget(QLabel("View:"))

        self.view_group = QButtonGroup(self)
        self.view_group.setExclusive(True)
        self.view_buttons = {}
        for source in self.SOURCES:
            btn = QPushButton(self.SOURCE_LABELS[source])
            btn.setCheckable(True)
            if source == "stockanalysis":
                btn.setChecked(True)
            btn.clicked.connect(
                lambda checked, s=source: self._on_source_view_toggle(s)
            )
            self.view_group.addButton(btn)
            self.view_buttons[source] = btn
            view_layout.addWidget(btn)

        view_layout.addWidget(QLabel("Statement:"))
        self.statement_group = QButtonGroup(self)
        self.statement_group.setExclusive(True)
        self.statement_buttons = {}
        for stmt in ["IS", "BS", "CFS", "Ratios"]:
            btn = QPushButton(stmt)
            btn.setCheckable(True)
            if stmt == "IS":
                btn.setChecked(True)
            btn.clicked.connect(
                lambda checked, s=stmt: self._on_statement_toggle(s)
            )
            self.statement_group.addButton(btn)
            self.statement_buttons[stmt] = btn
            view_layout.addWidget(btn)

        # Vol term (beta_vol only)
        self.vol_term_label = QLabel("Vol Term (years):")
        view_layout.addWidget(self.vol_term_label)
        self.vol_term_input = QDoubleSpinBox()
        self.vol_term_input.setMinimum(0.25)
        self.vol_term_input.setMaximum(10.0)
        self.vol_term_input.setSingleStep(0.25)
        self.vol_term_input.setValue(3.0)
        view_layout.addWidget(self.vol_term_input)

        view_layout.addStretch()
        layout.addLayout(view_layout)

        self.results_table = QTableWidget()
        layout.addWidget(self.results_table)

        self.status_label = QLabel("Ready")
        layout.addWidget(self.status_label)

        self.setLayout(layout)
        self._sync_controls_visibility()

    def _apply_theme(self, theme=None):
        t = theme or theme_manager.current
        btn_css = t.button_style()
        accent_css = t.accent_button_style()

        # Refresh toolbar + view/statement toggles
        for btn in self.findChildren(QPushButton):
            if btn is getattr(self, "btn_live_marks", None):
                btn.setStyleSheet(accent_css)
            else:
                btn.setStyleSheet(btn_css)

        self.results_table.setStyleSheet(t.table_style())
        self.results_table.horizontalHeader().setStyleSheet("")  # inherit from table QSS
        self.results_table.verticalHeader().setStyleSheet(
            f"QHeaderView::section {{"
            f" background-color: {t.header_bg}; color: {t.default_text};"
            f" font-weight: bold; border: 1px solid {t.border_color}; padding: 2px 4px;"
            f"}}"
        )
        self.status_label.setStyleSheet(f"color: {t.default_text};")

    def _sync_controls_visibility(self):
        show_sa = self.current_source == "stockanalysis"
        for btn in self.statement_buttons.values():
            btn.setVisible(show_sa)

        show_beta_vol = self.current_source == "beta_vol"
        self.vol_term_label.setVisible(show_beta_vol)
        self.vol_term_input.setVisible(show_beta_vol)

    def _on_refresh_all_clicked(self):
        self._pending_batch_sources = set(self.SOURCES)
        for source in self.SOURCES:
            self._on_refresh_clicked(source)

    def _on_refresh_live_marks_clicked(self):
        worker = self.workers.get("live_marks")
        if worker and worker.isRunning():
            self.status_label.setText("Live marks refresh already running...")
            return

        project_inputs = self.get_project_inputs_callback()
        if not project_inputs.active_public_tickers:
            self.status_label.setText("No public tickers configured on Home page.")
            return

        self.status_label.setText("Updating Live Market Marks via yfinance & FRED...")

        # Pass current StockAnalysis cache for surgical overlay
        kwargs = {"existing_sa_results": self.all_results.get("stockanalysis", {})}

        worker = SourceDataWorker(project_inputs, "live_marks", **kwargs)
        worker.progress.connect(self._on_progress)
        worker.error.connect(lambda msg: self._on_error("live_marks", msg))
        worker.results.connect(self._on_live_marks_results)
        worker.finished.connect(lambda: None)  # status + dialog handled in _on_live_marks_results
        self.workers["live_marks"] = worker
        worker.start()

    def _on_live_marks_results(self, source, results):
        from PyQt6.QtWidgets import QMessageBox
        from PyQt6.QtCore import QTimer

        if "stockanalysis" in results:
            self.all_results["stockanalysis"] = results["stockanalysis"]
        if "fred" in results:
            self.all_results["fred"] = results["fred"]
        self._redraw()
        self.status_label.setText("Live market marks updated successfully.")
        # Recalc dependent pages (WACC / GPC / DCF / etc.)
        self.all_sources_finished.emit()

        # Confirmation after worker teardown so it isn't suppressed
        QTimer.singleShot(
            0,
            lambda: QMessageBox.information(
                self,
                "Live Marks Complete",
                "Live market marks updated.\n\n"
                "Market Cap, Enterprise Value, Last Close, and FRED rates "
                "were refreshed. Fundamentals (IS / BS / CFS) were left unchanged.",
            ),
        )

    def _on_refresh_clicked(self, source):
        worker = self.workers.get(source)
        if worker and worker.isRunning():
            self.status_label.setText(
                f"{self.SOURCE_LABELS[source]} refresh already running..."
            )
            return

        project_inputs = self.get_project_inputs_callback()

        if source in ("stockanalysis", "marketscreener") and \
                not project_inputs.active_public_tickers:
            self.status_label.setText(
                "No public tickers configured on Home page."
            )
            return

        self.refresh_buttons[source].setEnabled(False)
        self.status_label.setText(
            f"Refreshing {self.SOURCE_LABELS[source]}..."
        )

        kwargs = {}
        if source == "beta_vol":
            kwargs["vol_term"] = self.vol_term_input.value()

        worker = SourceDataWorker(project_inputs, source, **kwargs)
        worker.progress.connect(self._on_progress)
        worker.error.connect(
            lambda msg, s=source: self._on_error(s, msg)
        )
        worker.results.connect(self._on_results)
        worker.finished.connect(
            lambda s=source: self._on_finished(s)
        )
        self.workers[source] = worker
        worker.start()

    def _on_source_view_toggle(self, source):
        self.current_source = source
        self._sync_controls_visibility()
        self._redraw()

    def _on_statement_toggle(self, statement):
        self.current_statement = statement
        self._redraw()

    def _on_progress(self, message):
        self.status_label.setText(message)
        if self._pending_batch_sources:
            completed = len(self.SOURCES) - len(self._pending_batch_sources)
            self.source_progress.emit(completed, len(self.SOURCES), message)

    def _on_error(self, source, message):
        self.status_label.setText(
            f"{self.SOURCE_LABELS[source]} error: {message}"
        )
        self.refresh_buttons[source].setEnabled(True)

    def _on_results(self, source, results):
        self.all_results[source] = results
        if source == self.current_source:
            self._redraw()
        row_count = self._count_rows(source, results)
        self.status_label.setText(
            f"{self.SOURCE_LABELS[source]} complete. {row_count} rows."
        )

    def _on_finished(self, source):
        self.refresh_buttons[source].setEnabled(True)
        if source in self._pending_batch_sources:
            self._pending_batch_sources.discard(source)
            completed = len(self.SOURCES) - len(self._pending_batch_sources)
            self.source_progress.emit(
                completed, len(self.SOURCES),
                f"{self.SOURCE_LABELS[source]} complete."
            )
            if not self._pending_batch_sources:
                self.all_sources_finished.emit()

    def _count_rows(self, source, results):
        if source == "stockanalysis":
            return sum(len(rows) for rows in results.values())
        return len(results) if results else 0

    def _redraw(self):
        source = self.current_source
        results = self.all_results.get(source)
        if not results:
            self.results_table.setRowCount(0)
            self.results_table.setColumnCount(0)
            self.status_label.setText(
                f"No data for {self.SOURCE_LABELS[source]}"
            )
            return

        if source == "stockanalysis":
            self._display_stockanalysis(
                results.get(self.current_statement, [])
            )
        else:
            self._display_flat(results)

    def _display_stockanalysis(self, results):
        if not results:
            self.results_table.setRowCount(0)
            self.results_table.setColumnCount(0)
            return

        project_inputs = self.get_project_inputs_callback()
        hist_years = project_inputs.historical_years

        all_cols = []
        for row in results:
            for key in row.keys():
                if key not in all_cols:
                    all_cols.append(key)

        fy_cols = ["LFY", "LFY-1", "LFY-2", "LFY-3", "LFY-4"]
        allowed_fy_cols = fy_cols[:hist_years]

        preferred_order = (
            ["Ticker", "Line Item", "TTM"] + allowed_fy_cols + ["Key"]
        )
        columns = [col for col in preferred_order if col in all_cols]
        columns += [
            c for c in all_cols
            if c not in preferred_order and c not in fy_cols
        ]

        self._fill_table(results, columns)

    def _display_flat(self, results):
        if not results:
            self.results_table.setRowCount(0)
            self.results_table.setColumnCount(0)
            return

        columns = []
        for row in results:
            for key in row.keys():
                if key not in columns:
                    columns.append(key)

        self._fill_table(results, columns)

    def _fill_table(self, results, columns):
        self.results_table.setColumnCount(len(columns))
        self.results_table.setHorizontalHeaderLabels(columns)
        self.results_table.setRowCount(len(results))

        for row_idx, result in enumerate(results):
            for col_idx, col in enumerate(columns):
                value = result.get(col, "")
                display_value = self._clean_display_value(value)
                self.results_table.setItem(
                    row_idx, col_idx, QTableWidgetItem(display_value)
                )

        self.results_table.resizeColumnsToContents()

    def _clean_display_value(self, value):
        if value is None:
            return ""
        try:
            if pd.isna(value):
                return ""
        except Exception:
            pass
        if isinstance(value, str):
            if value.strip().lower() in ("nan", "none", "nat"):
                return ""
            return value.strip()
        return str(value)