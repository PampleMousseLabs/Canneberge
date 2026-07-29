from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QLineEdit,
    QComboBox,
    QGroupBox,
    QGridLayout,
    QLabel,
    QSpinBox,
    QPushButton,
)
from PyQt6.QtCore import Qt
from typing import Optional

import yfinance as yf

from Canneberge.app_state import ProjectInputs, Transaction, parse_ticker_text

INPUT_STYLE = "background-color: #dce9f7; color: #1a4a8a;"


class HomePage(QWidget):
    def __init__(self):
        super().__init__()
        self._private_financials_callback = None
        self._projection_module_callback = None   # ADD THIS LINE
        self._build_ui()

    def set_private_financials_callback(self, callback):
        """Called by MainWindow to wire the private financials dialog opener."""
        self._private_financials_callback = callback

    def set_projection_module_callback(self, callback):
        """Called by MainWindow to wire the projection module dialog opener."""
        self._projection_module_callback = callback
    
    def _build_ui(self):
        main_layout = QVBoxLayout()
        top_layout = QHBoxLayout()

        # -------------------------------------------------
        # GENERAL
        # -------------------------------------------------
        general_box = QGroupBox("GENERAL")
        general_form = QFormLayout()

        self.client_input = QLineEdit("Ted & Co.")
        self.subject_name_input = QLineEdit("SpaceX")
        self.main_title_input = QLineEdit("Sensitivity Analysis of SpaceX")
        self.valuation_date_input = QLineEdit("7/21/2026")

        self.numeric_scale_combo = QComboBox()
        self.numeric_scale_combo.addItems(["Millions", "Thousands", "Actual"])

        self.draft_final_combo = QComboBox()
        self.draft_final_combo.addItems(["Draft", "Final"])

        self.standard_value_combo = QComboBox()
        self.standard_value_combo.addItems([
            "Fair Market Value",
            "Investment Value",
            "Intrinsic Value"
        ])

        self.taxable_combo = QComboBox()
        self.taxable_combo.addItems([
            "Taxable/Nontaxable",
            "Taxable",
            "Nontaxable"
        ])

        self.basis_value_combo = QComboBox()
        self.basis_value_combo.addItems([
            "BEV / Equity Value",
            "Business Enterprise Value",
            "Equity Value"
        ])

        general_form.addRow("Client", self.client_input)
        general_form.addRow("Subject Company Name", self.subject_name_input)
        general_form.addRow("Main Title", self.main_title_input)
        general_form.addRow("Valuation Date", self.valuation_date_input)
        general_form.addRow("Numeric Scale", self.numeric_scale_combo)
        general_form.addRow("Draft/Final", self.draft_final_combo)
        general_form.addRow("Standard of Value", self.standard_value_combo)
        general_form.addRow("Taxable/Nontaxable", self.taxable_combo)
        general_form.addRow("Basis of Value", self.basis_value_combo)

        general_box.setLayout(general_form)
        top_layout.addWidget(general_box)

        # -------------------------------------------------
        # SUBJECT COMPANY
        # -------------------------------------------------
        subject_box = QGroupBox("Subject Company")
        subject_form = QFormLayout()

        self.company_status_combo = QComboBox()
        self.company_status_combo.addItems([
            "Private Company",
            "Publicly Traded"
        ])
        self.company_status_combo.currentTextChanged.connect(
            self._on_company_status_changed
        )

        self.subject_ticker_input = QLineEdit("SPCX")
        self.tax_rate_input = QLineEdit("21%")

        self.lfy_input = QLineEdit("12/31/2025")
        self.fq_input = QLineEdit("3/31/2026")
        self.nfy_input = QLineEdit("12/31/2026")
        self.nfy_1_input = QLineEdit("12/31/2027")
        self.nfy_2_input = QLineEdit("12/31/2028")

        # Private financials link button (shown when Private Company)
        self.private_financials_btn = QPushButton("Enter Financial Data →")
        self.private_financials_btn.setStyleSheet(
            "border: none; color: #1a4a8a; text-decoration: underline; "
            "text-align: left; background: transparent;"
        )
        self.private_financials_btn.setCursor(
            Qt.CursorShape.PointingHandCursor
        )
        self.private_financials_btn.clicked.connect(
            self._open_private_financials
        )

        # Projection module link button (shown when Private Company,
        # positioned below Enter Financial Data)
        self.projection_module_btn = QPushButton("Projection Module →")
        self.projection_module_btn.setStyleSheet(
            "border: none; color: #1a4a8a; text-decoration: underline; "
            "text-align: left; background: transparent;"
        )
        self.projection_module_btn.setCursor(
            Qt.CursorShape.PointingHandCursor
        )
        self.projection_module_btn.clicked.connect(
            self._open_projection_module
        )

        subject_form.addRow("Company Status", self.company_status_combo)
        subject_form.addRow("Subject Ticker", self.subject_ticker_input)
        subject_form.addRow("", self.private_financials_btn)
        subject_form.addRow("", self.projection_module_btn)
        subject_form.addRow("Tax Rate", self.tax_rate_input)
        subject_form.addRow("Last Fiscal Year", self.lfy_input)
        subject_form.addRow("Last Fiscal Quarter", self.fq_input)
        subject_form.addRow("Next Fiscal Year End", self.nfy_input)
        subject_form.addRow("Next Fiscal Year End + 1", self.nfy_1_input)
        subject_form.addRow("Next Fiscal Year End + 2", self.nfy_2_input)

        subject_box.setLayout(subject_form)
        top_layout.addWidget(subject_box)

        main_layout.addLayout(top_layout)

        # =========================================================
        # MARKET INPUTS
        # =========================================================
        market_box = QGroupBox("MARKET INPUTS")
        market_layout = QVBoxLayout()
        top_row = QHBoxLayout()

        # --- GPC ---
        gpc_group = QGroupBox("GPC")
        gpc_layout = QVBoxLayout()
        gpc_grid = QGridLayout()
        gpc_grid.setColumnStretch(0, 0)
        gpc_grid.setColumnStretch(1, 0)
        gpc_grid.setColumnStretch(2, 1)

        gpc_grid.addWidget(QLabel("#"), 0, 0)
        gpc_grid.addWidget(QLabel("Entered Ticker"), 0, 1)
        gpc_grid.addWidget(QLabel("Company Name"), 0, 2)

        self.gpc_ticker_edits = []
        self.gpc_name_edits = []

        default_tickers = [
            "RKLB", "AMZN", "FLY", "ASTS", "GOOG",
            "IRDM", "PLTR", "SOUN", "NBIS"
        ]

        for row in range(15):
            row_num = QLabel(str(row + 1))
            ticker_edit = QLineEdit()
            ticker_edit.setFixedWidth(90)
            name_edit = QLineEdit()
            name_edit.setReadOnly(True)
            name_edit.setMinimumWidth(200)

            if row < len(default_tickers):
                ticker_edit.setText(default_tickers[row])
                name_edit.setText(
                    self._resolve_company_name(default_tickers[row])
                )

            ticker_edit.editingFinished.connect(
                lambda checked=False, r=row: self._update_company_name(r)
            )

            self.gpc_ticker_edits.append(ticker_edit)
            self.gpc_name_edits.append(name_edit)

            gpc_grid.addWidget(row_num, row + 1, 0)
            gpc_grid.addWidget(ticker_edit, row + 1, 1)
            gpc_grid.addWidget(name_edit, row + 1, 2)

        gpc_layout.addLayout(gpc_grid)
        gpc_layout.addStretch()
        gpc_group.setLayout(gpc_layout)

        # --- GT ---
        gt_group = QGroupBox("GT")
        gt_layout = QVBoxLayout()
        gt_grid = QGridLayout()

        headers = ["#", "Closing Date", "Target Company", "Acquirer",
                   "BEV", "TTM Revenue", "TTM EBITDA", "TTM EBIT"]
        for col, header in enumerate(headers):
            lbl = QLabel(header)
            lbl.setStyleSheet("font-weight: bold;")
            gt_grid.addWidget(lbl, 0, col)

        self.gt_rows = []

        default_gt = [
            {
                "closing_date": "6/29/2026",
                "target": "Iridium Communications Lab",
                "acquirer": "Rocket Lab",
                "bev": "8000",
                "ttm_revenue": "871.7",
                "ttm_ebitda": "495",
                "ttm_ebit": "236",
            },
            {
                "closing_date": "6/15/2026",
                "target": "Comtech Satellite & Space",
                "acquirer": "Gilat Satellite Networks",
                "bev": "157.5",
                "ttm_revenue": "195.2",
                "ttm_ebitda": "16.8",
                "ttm_ebit": "",
            },
            {
                "closing_date": "8/15/2024",
                "target": "Terran Orbital",
                "acquirer": "Lockheed Martin",
                "bev": "450",
                "ttm_revenue": "94.2",
                "ttm_ebitda": "",
                "ttm_ebit": "",
            },
        ]

        for row in range(5):
            row_num = QLabel(str(row + 1))
            closing_date_edit = QLineEdit()
            target_edit = QLineEdit()
            acquirer_edit = QLineEdit()
            bev_edit = QLineEdit()
            revenue_edit = QLineEdit()
            ebitda_edit = QLineEdit()
            ebit_edit = QLineEdit()

            closing_date_edit.setFixedWidth(80)
            bev_edit.setFixedWidth(70)
            revenue_edit.setFixedWidth(80)
            ebitda_edit.setFixedWidth(80)
            ebit_edit.setFixedWidth(70)

            if row < len(default_gt):
                closing_date_edit.setText(default_gt[row]["closing_date"])
                target_edit.setText(default_gt[row]["target"])
                acquirer_edit.setText(default_gt[row]["acquirer"])
                bev_edit.setText(default_gt[row]["bev"])
                revenue_edit.setText(default_gt[row]["ttm_revenue"])
                ebitda_edit.setText(default_gt[row]["ttm_ebitda"])
                ebit_edit.setText(default_gt[row]["ttm_ebit"])

            self.gt_rows.append({
                "closing_date": closing_date_edit,
                "target": target_edit,
                "acquirer": acquirer_edit,
                "bev": bev_edit,
                "ttm_revenue": revenue_edit,
                "ttm_ebitda": ebitda_edit,
                "ttm_ebit": ebit_edit,
            })

            gt_grid.addWidget(row_num,           row + 1, 0)
            gt_grid.addWidget(closing_date_edit, row + 1, 1)
            gt_grid.addWidget(target_edit,       row + 1, 2)
            gt_grid.addWidget(acquirer_edit,     row + 1, 3)
            gt_grid.addWidget(bev_edit,          row + 1, 4)
            gt_grid.addWidget(revenue_edit,      row + 1, 5)
            gt_grid.addWidget(ebitda_edit,       row + 1, 6)
            gt_grid.addWidget(ebit_edit,         row + 1, 7)

        gt_grid.setColumnStretch(0, 0)
        gt_grid.setColumnStretch(1, 0)
        gt_grid.setColumnStretch(2, 2)
        gt_grid.setColumnStretch(3, 2)
        gt_grid.setColumnStretch(4, 0)
        gt_grid.setColumnStretch(5, 0)
        gt_grid.setColumnStretch(6, 0)
        gt_grid.setColumnStretch(7, 0)

        gt_layout.addLayout(gt_grid)
        gt_layout.addStretch()
        gt_group.setLayout(gt_layout)

        top_row.addWidget(gpc_group, 1)
        top_row.addWidget(gt_group, 1)
        market_layout.addLayout(top_row)
        market_box.setLayout(market_layout)
        main_layout.addWidget(market_box)

        # =========================================================
        # PROJECTION CONTROLS
        # =========================================================
        projection_box = QGroupBox("PROJECTION CONTROLS")
        projection_form = QFormLayout()

        self.historical_years_spin = QSpinBox()
        self.historical_years_spin.setMinimum(0)
        self.historical_years_spin.setMaximum(5)
        self.historical_years_spin.setValue(5)
        self.historical_years_spin.setFixedWidth(60)
        self.historical_years_spin.setStyleSheet(INPUT_STYLE)

        self.projection_years_spin = QSpinBox()
        self.projection_years_spin.setMinimum(1)
        self.projection_years_spin.setMaximum(20)
        self.projection_years_spin.setValue(5)
        self.projection_years_spin.setFixedWidth(60)
        self.projection_years_spin.setStyleSheet(INPUT_STYLE)

        projection_form.addRow("Historical Years", self.historical_years_spin)
        projection_form.addRow("Projection Years", self.projection_years_spin)

        projection_box.setLayout(projection_form)
        main_layout.addWidget(projection_box)

        main_layout.addStretch()
        self.setLayout(main_layout)

        # Set initial visibility state
        self._on_company_status_changed(
            self.company_status_combo.currentText()
        )

    def _on_company_status_changed(self, status: str):
        is_private = status.strip().lower() == "private company"
        self.subject_ticker_input.setVisible(not is_private)
        self.private_financials_btn.setVisible(is_private)
        self.projection_module_btn.setVisible(True)  

    def _open_projection_module(self):
        if self._projection_module_callback:
            self._projection_module_callback()

    def _open_private_financials(self):
        if self._private_financials_callback:
            self._private_financials_callback()

    def _parse_float(self, text: str) -> Optional[float]:
        text = text.strip().replace(",", "")
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            return None

    def _parse_tax_rate(self) -> float:
        text = self.tax_rate_input.text().strip().replace("%", "")
        try:
            val = float(text)
            if val > 1:
                return val / 100
            return val
        except ValueError:
            return 0.21

    def _resolve_company_name(self, ticker: str) -> str:
        ticker = ticker.strip().upper()
        if not ticker:
            return ""
        try:
            info = yf.Ticker(ticker).info
            return info.get("longName") or info.get("shortName") or ""
        except Exception:
            return ""

    def _update_company_name(self, row: int):
        ticker = self.gpc_ticker_edits[row].text().strip().upper()
        if not ticker:
            self.gpc_name_edits[row].clear()
            return
        self.gpc_name_edits[row].setText(
            self._resolve_company_name(ticker)
        )

    def get_project_inputs(self) -> ProjectInputs:
        gt_transactions = []
        for row_widgets in self.gt_rows:
            closing_date = row_widgets["closing_date"].text().strip()
            target = row_widgets["target"].text().strip()
            acquirer = row_widgets["acquirer"].text().strip()
            bev = self._parse_float(row_widgets["bev"].text())
            ttm_revenue = self._parse_float(row_widgets["ttm_revenue"].text())
            ttm_ebitda = self._parse_float(row_widgets["ttm_ebitda"].text())
            ttm_ebit = self._parse_float(row_widgets["ttm_ebit"].text())

            if any([closing_date, target, acquirer, bev]):
                gt_transactions.append(Transaction(
                    closing_date=closing_date,
                    target=target,
                    acquirer=acquirer,
                    bev=bev,
                    ttm_revenue=ttm_revenue,
                    ttm_ebitda=ttm_ebitda,
                    ttm_ebit=ttm_ebit,
                ))

        gpc_company_names = {}
        for ticker_edit, name_edit in zip(self.gpc_ticker_edits, self.gpc_name_edits):
            ticker = ticker_edit.text().strip().upper()
            name = name_edit.text().strip()
            if ticker and name:
                gpc_company_names[ticker] = name

        return ProjectInputs(
            client=self.client_input.text().strip(),
            subject_company_name=self.subject_name_input.text().strip(),
            main_title=self.main_title_input.text().strip(),
            valuation_date=self.valuation_date_input.text().strip(),
            numeric_scale=self.numeric_scale_combo.currentText(),
            draft_final=self.draft_final_combo.currentText(),
            standard_of_value=self.standard_value_combo.currentText(),
            taxable_nontaxable=self.taxable_combo.currentText(),
            basis_of_value=self.basis_value_combo.currentText(),
            company_status=self.company_status_combo.currentText(),
            subject_ticker=self.subject_ticker_input.text().strip().upper(),
            subject_tax_rate=self._parse_tax_rate(),
            last_fiscal_year=self.lfy_input.text().strip(),
            last_fiscal_quarter=self.fq_input.text().strip(),
            next_fiscal_year=self.nfy_input.text().strip(),
            nfy_1=self.nfy_1_input.text().strip(),
            nfy_2=self.nfy_2_input.text().strip(),
            gpc_tickers=parse_ticker_text(
                "\n".join(
                    edit.text().strip() for edit in self.gpc_ticker_edits
                )
            ),
            gpc_company_names=gpc_company_names,
            gt_transactions=gt_transactions,
            historical_years=self.historical_years_spin.value(),
            projection_years=self.projection_years_spin.value(),
        )