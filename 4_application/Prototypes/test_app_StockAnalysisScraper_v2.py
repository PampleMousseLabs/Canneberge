import sys
import threading
from datetime import datetime

import requests
from bs4 import BeautifulSoup
import pandas as pd
import openpyxl
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QTableWidget, QTableWidgetItem, QSpinBox
)
from PyQt6.QtCore import Qt, pyqtSignal, QThread
from PyQt6.QtGui import QFont

# =========================================================
# WORKER THREAD FOR DATA PULLING (ALL STATEMENTS)
# =========================================================
class MultiStatementScraper(QThread):
    finished = pyqtSignal()
    error = pyqtSignal(str)
    results = pyqtSignal(dict, list)  # (all_results_by_statement, statement_list)
    progress = pyqtSignal(str)
    
    def __init__(self, tickers, historical_years):
        super().__init__()
        self.tickers = tickers
        self.historical_years = historical_years
        self.lfy = self._calculate_lfy()
        self.statements = ['IS', 'BS', 'CFS', 'Ratios']
    
    def _calculate_lfy(self):
        """Calculate Last Fiscal Year from Excel"""
        try:
            drive_path = r"G:\My Drive\PampleMousseLabs\Project Canneberge"
            wb = openpyxl.load_workbook(f"{drive_path}/Project_Canneberge.xlsm")
            ws = wb['Control']
            fy_end = ws['F21'].value
            if fy_end:
                return fy_end.year
        except:
            pass
        return datetime.now().year
    
    def run(self):
        """Scrape all statements for all tickers"""
        all_results = {stmt: [] for stmt in self.statements}
        
        for idx, ticker in enumerate(self.tickers):
            self.progress.emit(f"Scraping {ticker} ({idx + 1}/{len(self.tickers)})...")
            
            for stmt in self.statements:
                try:
                    df = self._scrape_statement(ticker, stmt)
                    if df is not None and not df.empty:
                        all_results[stmt].extend(df.to_dict('records'))
                        self.progress.emit(f"  {ticker} {stmt}: {len(df)} rows")
                    else:
                        self.progress.emit(f"  {ticker} {stmt}: No data")
                except Exception as e:
                    self.progress.emit(f"  {ticker} {stmt}: Error - {str(e)}")
        
        self.results.emit(all_results, self.statements)
        self.finished.emit()
    
    def _scrape_statement(self, ticker, statement_type):
        """Scrape a single statement for a ticker"""
        # Build URL
        if statement_type == 'IS':
            url = f"https://stockanalysis.com/stocks/{ticker.lower()}/financials/"
        elif statement_type == 'BS':
            url = f"https://stockanalysis.com/stocks/{ticker.lower()}/financials/balance-sheet/"
        elif statement_type == 'CFS':
            url = f"https://stockanalysis.com/stocks/{ticker.lower()}/financials/cash-flow-statement/"
        elif statement_type == 'Ratios':
            url = f"https://stockanalysis.com/stocks/{ticker.lower()}/financials/ratios/"
        else:
            return None
        
        # Fetch and parse
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        tables = soup.find_all('table')
        
        if not tables:
            return None
        
        # Select first suitable table
        raw_table = None
        for table in tables:
            rows = table.find_all('tr')
            cols = table.find_all('th')
            if len(rows) > 5 and len(cols) > 2:
                raw_table = table
                # DEBUG: Print table structure
                print(f"\n=== DEBUG: {ticker} {statement_type} ===")
                print(f"Headers found: {len(table.find_all('th'))}")
                print(f"Rows found: {len(table.find_all('tr'))}")
                first_row = table.find('tr')
                if first_row:
                    first_cells = first_row.find_all(['td', 'th'])
                    print(f"First row cell count: {len(first_cells)}")
                    print(f"First row content: {[cell.get_text(strip=True)[:20] for cell in first_cells[:8]]}")
                break
        
        if raw_table is None:
            return None
        
        # Parse and clean
        df = self._parse_table_to_dataframe(raw_table)
        if df.empty:
            return None
        
        df = self._clean_financial_table(df)
        
        # Rename first column to 'Line Item'
        first_col = df.columns[0]
        df.rename(columns={first_col: 'Line Item'}, inplace=True)
        
        # Map columns by actual header content dynamically, not position
        rename_map = {}
        fy_cols = {}

        for col in df.columns[1:]:
            header = str(col).strip()
            upper_hdr = header.upper()

            # "Current" is used on the Ratios page instead of TTM/LTM
            if upper_hdr in ('TTM', 'LTM', 'CURRENT'):
                rename_map[col] = 'TTM'
            elif header.startswith('FY'):
                # Extract year and keep for sorting
                try:
                    year = int(header.replace('FY', '').strip())
                    fy_cols[year] = col
                except ValueError:
                    pass

        # Sort FY years descending: highest = LFY
        for idx, year in enumerate(sorted(fy_cols.keys(), reverse=True)):
            col = fy_cols[year]
            if idx == 0:
                rename_map[col] = 'LFY'
            else:
                rename_map[col] = f'LFY-{idx}'

        if rename_map:
            df.rename(columns=rename_map, inplace=True)
        
        # Add metadata
        df['Ticker'] = ticker.lower()
        df['Key'] = df['Ticker'] + '|' + df['Line Item'].str.lower()
        
        return df
    
    def _parse_table_to_dataframe(self, table):
        """Parse HTML table including header + data cells."""
        html_rows = table.find_all('tr')
        if not html_rows:
            return pd.DataFrame()

        # Real header row (usually <th>)
        header_cells = html_rows[0].find_all(['th', 'td'])
        headers = [c.get_text(strip=True) for c in header_cells]
        if len(headers) < 2:
            return pd.DataFrame()

        data = []
        for tr in html_rows[1:]:
            # Include both th/td so first line items are not dropped
            cells = tr.find_all(['th', 'td'])
            row = [c.get_text(strip=True) for c in cells]
            if not row:
                continue

            # Skip metadata rows
            first = row[0].strip().lower()
            if first in {'fiscal year', 'period ending'}:
                continue

            # Normalize width
            if len(row) < len(headers):
                row.extend([None] * (len(headers) - len(row)))
            elif len(row) > len(headers):
                row = row[:len(headers)]

            data.append(row)

        if not data:
            return pd.DataFrame()

        print(f"DEBUG: Headers={len(headers)}, First data row={len(data[0])}, First line item={data[0][0]}")
        return pd.DataFrame(data, columns=headers)
    
    def _clean_financial_table(self, df):
        """Clean junk values"""
        junk_values = ['-', 'N/A', 'NA', '', '—', None]
        
        for col in df.columns:
            df[col] = df[col].replace(junk_values, None)
            if df[col].dtype == 'object':
                df[col] = df[col].apply(lambda x: x.strip() if isinstance(x, str) else x)
        
        return df
       
# =========================================================
# MAIN WINDOW
# =========================================================
class StockAnalysisScraperApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Test: StockAnalysis.com Scraper (All Statements)")
        self.setGeometry(100, 100, 1400, 700)
        
        self.worker = None
        self.all_results = {}  # {statement: [rows]}
        self.current_statement = 'IS'
        self.statement_buttons = {}
        
        self.init_ui()
    
    def init_ui(self):
        """Initialize UI"""
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout()
        
        # Input panel
        input_layout = QHBoxLayout()
        
        input_layout.addWidget(QLabel("Tickers (comma-separated):"))
        self.tickers_input = QLineEdit()
        self.tickers_input.setText("AAPL, MSFT, NVDA, GOOG, AMZN")
        input_layout.addWidget(self.tickers_input)
        
        input_layout.addWidget(QLabel("Historical Years:"))
        self.hist_years_input = QSpinBox()
        self.hist_years_input.setValue(5)
        self.hist_years_input.setMinimum(0)
        self.hist_years_input.setMaximum(5)
        self.hist_years_input.valueChanged.connect(self._on_hist_years_changed)
        input_layout.addWidget(self.hist_years_input)
        
        self.scrape_btn = QPushButton("SCRAPE ALL")
        self.scrape_btn.clicked.connect(self.on_scrape_clicked)
        input_layout.addWidget(self.scrape_btn)
        
        input_layout.addStretch()
        layout.addLayout(input_layout)
        
        # Statement toggle buttons
        toggle_layout = QHBoxLayout()
        toggle_layout.addWidget(QLabel("View:"))
        for stmt in ['IS', 'BS', 'CFS', 'Ratios']:
            btn = QPushButton(stmt)
            btn.setCheckable(True)
            btn.clicked.connect(lambda checked, s=stmt: self._on_statement_toggle(s))
            if stmt == 'IS':
                btn.setChecked(True)
            self.statement_buttons[stmt] = btn
            toggle_layout.addWidget(btn)
        toggle_layout.addStretch()
        layout.addLayout(toggle_layout)
        
        # Results table
        self.results_table = QTableWidget()
        layout.addWidget(self.results_table)
        
        # Status label
        self.status_label = QLabel("Ready")
        layout.addWidget(self.status_label)
        
        main_widget.setLayout(layout)
    
    def on_scrape_clicked(self):
        """Handle Scrape button"""
        if self.worker and self.worker.isRunning():
            self.status_label.setText("Scrape already in progress...")
            return
        
        tickers_str = self.tickers_input.text()
        tickers = [t.strip() for t in tickers_str.split(",") if t.strip()]
        hist_years = self.hist_years_input.value()
        
        if not tickers:
            self.status_label.setText("Enter at least one ticker")
            return
        
        self.status_label.setText(f"Scraping {len(tickers)} tickers for all statements (IS, BS, CFS, Ratios)...")
        self.scrape_btn.setEnabled(False)
        
        self.worker = MultiStatementScraper(tickers, hist_years)
        self.worker.results.connect(self._display_results)
        self.worker.error.connect(self._on_error)
        self.worker.progress.connect(self._on_progress)
        self.worker.finished.connect(self._on_finished)
        self.worker.start()
    
    def _on_statement_toggle(self, statement):
        """Handle statement toggle button click"""
        # Uncheck others
        for stmt, btn in self.statement_buttons.items():
            if stmt != statement:
                btn.setChecked(False)
        
        self.current_statement = statement
        
        # Re-display current statement if data exists
        if self.all_results:
            self._display_statement(self.all_results[statement])
    
    def _on_hist_years_changed(self):
        """Refresh display only; do not re-scrape."""
        if self.all_results and self.current_statement in self.all_results:
            self._display_statement(self.all_results[self.current_statement])

    def _display_results(self, all_results, statements):
        """Store results and display current statement"""
        self.all_results = all_results
        
        # Display the current statement (IS by default)
        self._display_statement(self.all_results[self.current_statement])
        
        # Update status
        total_rows = sum(len(rows) for rows in all_results.values())
        self.status_label.setText(f"Scraped {total_rows} total rows across all statements. Viewing: {self.current_statement}")
    
    def _display_statement(self, results):
        """Display results for a single statement"""
        if not results:
            self.results_table.setRowCount(0)
            self.status_label.setText(f"No data for {self.current_statement}")
            return
        
        all_cols = []
        for r in results:
            for k in r.keys():
                if k not in all_cols:
                    all_cols.append(k)
        
        # Build column list respecting historical_years setting
        hist_years = self.hist_years_input.value()
        fy_cols = ['LFY', 'LFY-1', 'LFY-2', 'LFY-3', 'LFY-4']
        allowed_fy = fy_cols[:hist_years]
        
        preferred_order = ['Ticker', 'Line Item', 'TTM'] + allowed_fy + ['Key']
        columns = [c for c in preferred_order if c in all_cols]
        columns += [c for c in all_cols if c not in preferred_order and c not in fy_cols]

        self.results_table.setColumnCount(len(columns))
        self.results_table.setHorizontalHeaderLabels(columns)
        self.results_table.setRowCount(len(results))
        
        for row_idx, result in enumerate(results):
            for col_idx, col in enumerate(columns):
                value = result.get(col, "")
                # Catch None, float NaN, and string "nan"
                if value is None or (isinstance(value, float) and pd.isna(value)) or (isinstance(value, str) and value.strip().lower() == 'nan'):
                    display_val = ""
                else:
                    display_val = str(value) if value != "" else ""
                
                self.results_table.setItem(row_idx, col_idx, QTableWidgetItem(display_val))
        
        self.results_table.resizeColumnsToContents()
    
    def _on_progress(self, message):
        """Handle progress updates"""
        self.status_label.setText(message)
    
    def _on_error(self, error_msg):
        """Handle error"""
        self.status_label.setText(f"Error: {error_msg}")
        self.scrape_btn.setEnabled(True)
    
    def _on_finished(self):
        """Handle completion"""
        self.scrape_btn.setEnabled(True)

# =========================================================
# MAIN
# =========================================================
if __name__ == '__main__':
    app = QApplication(sys.argv)
    try:
        window = StockAnalysisScraperApp()
        window.show()
        sys.exit(app.exec())
    except Exception as e:
        print(f"Application crashed: {e}")