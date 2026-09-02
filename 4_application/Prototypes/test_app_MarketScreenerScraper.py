import sys
import re
from datetime import datetime

import requests
from bs4 import BeautifulSoup
import pandas as pd
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QTableWidget, QTableWidgetItem, QSpinBox
)
from PyQt6.QtCore import Qt, pyqtSignal, QThread
from PyQt6.QtGui import QFont

# =========================================================
# WORKER THREAD FOR MARKETSCREENER SCRAPING
# =========================================================
class MarketScreenerScraper(QThread):
    finished = pyqtSignal()
    error = pyqtSignal(str)
    results = pyqtSignal(list)  # List of dicts
    progress = pyqtSignal(str)
    
    def __init__(self, tickers, next_fiscal_year):
        super().__init__()
        self.tickers = tickers
        self.next_fiscal_year = next_fiscal_year
        # Map site labels to output labels
        self.line_items = {
            'MS Revenue': ['Net Sales', 'Revenue'],  # Search for either
            'MS EBITDA': ['EBITDA'],
            'MS EBIT': ['EBIT'],
            'MS Net Income': ['Net Income']
        }
    
    def run(self):
        """Scrape all tickers"""
        try:
            print("DEBUG: run() method called")
            self.progress.emit("Starting scrape...")
            
            all_results = []
            
            for idx, ticker in enumerate(self.tickers):
                print(f"DEBUG: Processing ticker {ticker}")
                self.progress.emit(f"Processing {ticker} ({idx + 1}/{len(self.tickers)})...")
                
                try:
                    # Step 1: Resolve slug
                    self.progress.emit(f"  {ticker}: Resolving slug...")
                    slug = self._resolve_slug(ticker)
                    
                    if not slug:
                        self.progress.emit(f"  {ticker}: Slug not found")
                        continue
                    
                    self.progress.emit(f"  {ticker}: Slug = {slug}")
                    
                    # Step 2: Fetch finance page
                    self.progress.emit(f"  {ticker}: Fetching finance page...")
                    html = self._get_finance_page(slug)
                    
                    if not html:
                        self.progress.emit(f"  {ticker}: Finance page not found")
                        continue
                    
                    # Step 3: Parse all years
                    all_years = self._get_all_year_headers(html)
                    if not all_years:
                        self.progress.emit(f"  {ticker}: No years found")
                        continue
                    
                    # Step 4: Find NFY index and get next 3 columns
                    nfy_str = str(self.next_fiscal_year)
                    nfy_index = -1
                    for i, year in enumerate(all_years):
                        if year == nfy_str:
                            nfy_index = i
                            break
                    
                    if nfy_index == -1:
                        self.progress.emit(f"  {ticker}: NFY {nfy_str} not found in headers {all_years}")
                        continue
                    
                    # Get next 3 years starting from NFY
                    target_years = all_years[nfy_index:nfy_index+3]
                    if len(target_years) < 3:
                        self.progress.emit(f"  {ticker}: Not enough years after NFY")
                        continue
                    
                    self.progress.emit(f"  {ticker}: Years = {target_years}")
                    
                    # Step 5: Extract line items for NFY, NFY+1, NFY+2
                    # Step 5: Extract line items for NFY, NFY+1, NFY+2
                    for output_label, search_labels in self.line_items.items():
                        try:
                            if output_label == 'EBIT':
                                values = self._get_row_values_ebit(html, len(all_years))
                            else:
                                # Try each possible label for this line item
                                values = None
                                for search_label in search_labels:
                                    values = self._get_row_values(html, search_label, len(all_years))
                                    if values:
                                        print(f"DEBUG: Found {output_label} using label '{search_label}'")
                                        break
                            
                            if values and len(values) >= nfy_index + 3:
                                # Extract only NFY, NFY+1, NFY+2
                                nfy_values = values[nfy_index:nfy_index+3]
                                
                                # Create record with OUTPUT label (Revenue, not Net Sales)
                                record = {
                                    'Ticker': ticker.lower(),
                                    'Line Item': output_label,  # Use the output label
                                    'Key': f"{ticker.lower()}|{output_label.lower()}",
                                    'NFY': nfy_values[0],
                                    'NFY+1': nfy_values[1],
                                    'NFY+2': nfy_values[2]
                                }
                                all_results.append(record)
                                self.progress.emit(f"    {output_label}: {nfy_values}")
                            else:
                                self.progress.emit(f"    {output_label}: Not found or insufficient values")
                        except Exception as e:
                            print(f"DEBUG: Line item error for {output_label}: {str(e)}")
                            self.progress.emit(f"    {output_label}: Error - {str(e)}")
                
                except Exception as e:
                    print(f"DEBUG: Ticker error for {ticker}: {str(e)}")
                    self.progress.emit(f"  {ticker}: Error - {str(e)}")
            
            self.results.emit(all_results)
            self.finished.emit()
        except Exception as e:
            print(f"DEBUG: FATAL ERROR in run(): {str(e)}")
            self.error.emit(f"Fatal error: {str(e)}")
    
    def _resolve_slug(self, ticker):
        """POST to quick search to resolve slug"""
        try:
            print(f"DEBUG: _resolve_slug() called for {ticker}")
            url = "https://www.marketscreener.com/async/search/quick"
            body = f"search={ticker}&search-type=1"
        
            headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'X-Requested-With': 'XMLHttpRequest',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Origin': 'https://www.marketscreener.com',
            'Referer': 'https://www.marketscreener.com/'
        }
        
            print(f"DEBUG: Posting to {url} with body: {body}")
            response = requests.post(url, data=body, headers=headers, timeout=10)
            print(f"DEBUG: Response status code: {response.status_code}")
            response.raise_for_status()
            
            # Parse JSON response
            data = response.json()
            print(f"DEBUG: Parsed JSON, keys: {data.keys()}")
            
            # The HTML is in the 'data' field
            if 'data' in data:
                html_content = data['data']
                
                # Parse HTML to find the first stock result
                soup = BeautifulSoup(html_content, 'html.parser')
                
                # Find all table rows with data-href
                rows = soup.find_all('tr', attrs={'data-href': True})
                print(f"DEBUG: Found {len(rows)} rows")
                
                for row in rows:
                    href = row.get('data-href', '')
                    print(f"DEBUG: Checking href: {href}")
                    
                    # Extract slug from /quote/stock/SLUG/ or /quote/etf/SLUG/
                    if '/quote/stock/' in href:
                        # Extract the slug (everything between /quote/stock/ and the trailing /)
                        slug = href.split('/quote/stock/')[1].rstrip('/')
                        print(f"DEBUG: Found stock slug: {slug}")
                        self.progress.emit(f"    Found slug: {slug}")
                        return slug
                
                print(f"DEBUG: No stock found in results")
                self.progress.emit(f"    No stock result found (only ETFs returned)")
                return None
            else:
                print(f"DEBUG: 'data' key not found in response")
                return None
            
        except requests.exceptions.RequestException as e:
            print(f"DEBUG: Request exception in _resolve_slug: {str(e)}")
            self.progress.emit(f"    Slug resolution request error: {str(e)}")
            return None
        except Exception as e:
            print(f"DEBUG: Exception in _resolve_slug: {str(e)}")
            self.progress.emit(f"    Slug resolution error: {str(e)}")
            return None
        
    def _get_finance_page(self, slug):
        """GET the finance page HTML"""
        try:
            url = f"https://www.marketscreener.com/quote/stock/{slug}/finances/"
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Referer': 'https://www.marketscreener.com/'
            }
            
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            return response.text
        except Exception as e:
            self.progress.emit(f"    Finance page error: {str(e)}")
            return None
    
    def _get_all_year_headers(self, html):
        """Extract ALL year headers from HTML in order (20XX format)"""
        try:
            # Find EBITDA section
            ebitda_pos = html.upper().find('EBITDA')
            if ebitda_pos == -1:
                return []
            
            # Search 12000 chars before EBITDA
            search_start = max(0, ebitda_pos - 12000)
            header_search = html[search_start:ebitda_pos]
            
            # Find all 4-digit years (20XX format) in order
            pattern = r'20[0-9]{2}'
            matches = re.findall(pattern, header_search)
            
            # Keep unique years between 2015-2030, maintaining order
            years = []
            seen = set()
            for match in matches:
                year = int(match)
                if 2015 <= year <= 2030 and year not in seen:
                    years.append(str(year))
                    seen.add(year)
            
            return years
        except Exception as e:
            self.progress.emit(f"    Year extraction error: {str(e)}")
            return []
    
    def _get_row_values(self, html, label, expected_count):
        """Extract row values by label (Revenue, EBITDA, Net Income)"""
        try:
            # Find label position (case insensitive)
            label_pos = html.upper().find(label.upper())
            if label_pos == -1:
                return []
            
            # Find next "bg-grey-light" section or 60000 chars out
            next_row_pos = html.find('bg-grey-light', label_pos + len(label))
            if next_row_pos == -1:
                next_row_pos = min(label_pos + 60000, len(html))
            
            # Extract segment
            row_segment = html[label_pos:next_row_pos]
            
            # Remove <sup> tags
            cleaned = re.sub(r'<sup[^>]*>.*?</sup>', '', row_segment, flags=re.DOTALL)
            
            # Extract numbers: >[\s]*(\-?[0-9][0-9,\.]*|\-)[\s]*<
            pattern = r'>[\s]*(\-?[0-9][0-9,\.]*|\-)[\s]*<'
            matches = re.findall(pattern, cleaned)
            
            values = []
            for match in matches:
                values.append(match)
                if len(values) >= expected_count:
                    break
            
            return values
        except Exception as e:
            self.progress.emit(f"    Row extraction error: {str(e)}")
            return []
    
    def _get_row_values_ebit(self, html, expected_count):
        """Extract EBIT row specifically (avoid EBITDA confusion)"""
        try:
            # Find "EBIT" but not "EBITDA"
            search_pos = 0
            ebit_pos = -1
            
            while True:
                pos = html.upper().find('EBIT', search_pos)
                if pos == -1:
                    break
                # Check if it's not "EBITDA"
                if html[pos:pos+6].upper() != 'EBITDA':
                    ebit_pos = pos
                    break
                search_pos = pos + 1
            
            if ebit_pos == -1:
                return []
            
            # Find next "bg-grey-light" or 60000 chars out
            next_row_pos = html.find('bg-grey-light', ebit_pos + 4)
            if next_row_pos == -1:
                next_row_pos = min(ebit_pos + 60000, len(html))
            
            # Extract segment
            row_segment = html[ebit_pos:next_row_pos]
            
            # Remove <sup> tags
            cleaned = re.sub(r'<sup[^>]*>.*?</sup>', '', row_segment, flags=re.DOTALL)
            
            # Extract numbers
            pattern = r'>[\s]*(\-?[0-9][0-9,\.]*|\-)[\s]*<'
            matches = re.findall(pattern, cleaned)
            
            values = []
            for match in matches:
                values.append(match)
                if len(values) >= expected_count:
                    break
            
            return values
        except Exception as e:
            self.progress.emit(f"    EBIT extraction error: {str(e)}")
            return []

# =========================================================
# MAIN WINDOW
# =========================================================
class MarketScreenerScraperApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Test: MarketScreener Forward Estimates Scraper")
        self.setGeometry(100, 100, 1400, 700)
        
        self.worker = None
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
        
        input_layout.addWidget(QLabel("Next Fiscal Year:"))
        self.nfy_input = QSpinBox()
        self.nfy_input.setValue(2026)
        self.nfy_input.setMinimum(2020)
        self.nfy_input.setMaximum(2030)
        input_layout.addWidget(self.nfy_input)
        
        self.scrape_btn = QPushButton("SCRAPE ALL")
        self.scrape_btn.clicked.connect(self.on_scrape_clicked)
        input_layout.addWidget(self.scrape_btn)
        
        input_layout.addStretch()
        layout.addLayout(input_layout)
        
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
        nfy = self.nfy_input.value()
    
        if not tickers:
            self.status_label.setText("Enter at least one ticker")
            return
    
        self.status_label.setText(f"Scraping {len(tickers)} tickers...")
        self.scrape_btn.setEnabled(False)
    
        print(f"DEBUG: Starting worker with tickers: {tickers}, NFY: {nfy}")
    
        # SINGLE WORKER CREATION with debug print above it
        self.worker = MarketScreenerScraper(tickers, nfy)
        self.worker.results.connect(self._display_results)
        self.worker.error.connect(self._on_error)
        self.worker.progress.connect(self._on_progress)
        self.worker.finished.connect(self._on_finished)
        self.worker.start()


    def _display_results(self, results):
        """Display results in table"""
        if not results:
            self.results_table.setRowCount(0)
            self.status_label.setText("No data returned")
            return
        
        # Get column names
        columns = ['Ticker', 'Line Item', 'NFY', 'NFY+1', 'NFY+2', 'Key']
        
        self.results_table.setColumnCount(len(columns))
        self.results_table.setHorizontalHeaderLabels(columns)
        self.results_table.setRowCount(len(results))
        
        for row_idx, result in enumerate(results):
            for col_idx, col in enumerate(columns):
                value = result.get(col, '')
                self.results_table.setItem(row_idx, col_idx, QTableWidgetItem(str(value) if value else ""))
        
        self.results_table.resizeColumnsToContents()
        self.status_label.setText(f"Scraped {len(results)} records")
    
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
    window = MarketScreenerScraperApp()
    window.show()
    sys.exit(app.exec())
