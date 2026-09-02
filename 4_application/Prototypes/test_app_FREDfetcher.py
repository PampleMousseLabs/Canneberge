import sys
import requests
import os
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QTableWidget, QTableWidgetItem
)
from PyQt6.QtCore import Qt, pyqtSignal, QThread
from PyQt6.QtGui import QFont

# =========================================================
# WORKER THREAD FOR FRED DATA FETCHING
# =========================================================
class FREDWorker(QThread):
    finished = pyqtSignal()
    error = pyqtSignal(str)
    results = pyqtSignal(list)  # List of dicts
    progress = pyqtSignal(str)
    
    def __init__(self, series_ids, api_key, label_map):
        super().__init__()
        self.series_ids = series_ids
        self.api_key = api_key
        self.label_map = label_map
    
    def run(self):
        """Fetch FRED data for all series"""
        try:
            print("DEBUG: FRED run() method called")
            self.progress.emit("Starting FRED data fetch...")
            
            all_results = []
            
            for idx, series_id in enumerate(self.series_ids):
                print(f"DEBUG: Processing series {series_id}")
                self.progress.emit(f"Fetching {series_id} ({idx + 1}/{len(self.series_ids)})...")
                
                try:
                    result = self._fetch_series(series_id)
                    
                    if result:
                        all_results.append(result)
                        self.progress.emit(f"  {series_id}: {result['LatestValue']} as of {result['AsOfDate']}")
                    else:
                        self.progress.emit(f"  {series_id}: No data found")
                
                except Exception as e:
                    print(f"DEBUG: Series error for {series_id}: {str(e)}")
                    self.progress.emit(f"  {series_id}: Error - {str(e)}")
            
            self.results.emit(all_results)
            self.finished.emit()
        except Exception as e:
            print(f"DEBUG: FATAL ERROR in FRED run(): {str(e)}")
            self.error.emit(f"Fatal error: {str(e)}")
    
    def _fetch_series(self, series_id):
        """Fetch latest observation for a series"""
        try:
            url = (
                f"https://api.stlouisfed.org/fred/series/observations?"
                f"series_id={series_id}"
                f"&api_key={self.api_key}"
                f"&sort_order=desc&limit=1&file_type=json"
            )
            
            print(f"DEBUG: Fetching {url}")
            
            headers = {
                'Accept': 'application/json'
            }
            
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            
            # Check for FRED API errors
            if 'error_code' in data:
                print(f"DEBUG: FRED API error: {data.get('error_message', 'Unknown error')}")
                self.progress.emit(f"  {series_id}: API Error - {data.get('error_message')}")
                return None
            
            # Extract latest observation
            observations = data.get('observations', [])
            if not observations:
                print(f"DEBUG: No observations found for {series_id}")
                return None
            
            latest = observations[0]
            
            result = {
                'SeriesID': series_id,
                'DisplayLabel': self.label_map.get(series_id, series_id),
                'AsOfDate': latest.get('date'),
                'LatestValue': latest.get('value')
            }
            
            print(f"DEBUG: Got result: {result}")
            return result
            
        except requests.exceptions.RequestException as e:
            print(f"DEBUG: Request error for {series_id}: {str(e)}")
            return None
        except Exception as e:
            print(f"DEBUG: Exception in _fetch_series: {str(e)}")
            return None

# =========================================================
# MAIN WINDOW
# =========================================================
class FREDFetcherApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("FRED Data Fetcher")
        self.setGeometry(100, 100, 1400, 600)
        
        # Hardwired configuration
        self.api_key = os.environ.get("FRED_API_KEY", "")
        self.series_ids = ["DFF", "SOFR", "WPRIME", "BAMLC0A0CMEY", "BAMLC0A1CAAAEY", 
                           "BAMLC0A2CAAEY", "BAMLC0A3CAEY", "BAMLC0A4CBBBEY", "DGS20"]
        
        # Series ID to display label mapping
        self.label_map = {
            "DFF": "Federal Funds Rate",
            "SOFR": "Overnight SOFR",
            "WPRIME": "Bank Prime Loan Rate",
            "BAMLC0A0CMEY": "ICE BofA US Corporate Master",
            "BAMLC0A1CAAAEY": "ICE BofA AAA US Corporate",
            "BAMLC0A2CAAEY": "ICE BofA AA US Corporate",
            "BAMLC0A3CAEY": "ICE BofA A US Corporate",
            "BAMLC0A4CBBBEY": "ICE BofA BBB US Corporate",
            "DGS20": "US Treasury 20yr Constant Maturity"
        }
        
        self.worker = None
        self.init_ui()
    
    def init_ui(self):
        """Initialize UI"""
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout()
        
        # Control panel
        control_layout = QHBoxLayout()
        
        self.fetch_btn = QPushButton("FETCH FRED DATA")
        self.fetch_btn.clicked.connect(self.on_fetch_clicked)
        control_layout.addWidget(self.fetch_btn)
        
        control_layout.addStretch()
        layout.addLayout(control_layout)
        
        # Results table
        self.results_table = QTableWidget()
        layout.addWidget(self.results_table)
        
        # Status label
        self.status_label = QLabel("Ready")
        layout.addWidget(self.status_label)
        
        main_widget.setLayout(layout)
    
    def on_fetch_clicked(self):
        """Handle Fetch button"""
        if self.worker and self.worker.isRunning():
            self.status_label.setText("Fetch already in progress...")
            return
        
        self.status_label.setText(f"Fetching {len(self.series_ids)} series...")
        self.fetch_btn.setEnabled(False)
        
        print(f"DEBUG: Starting FRED fetch with series: {self.series_ids}")
        self.worker = FREDWorker(self.series_ids, self.api_key, self.label_map)
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
        
        columns = ['SeriesID', 'DisplayLabel', 'AsOfDate', 'LatestValue']
        
        self.results_table.setColumnCount(len(columns))
        self.results_table.setHorizontalHeaderLabels(columns)
        self.results_table.setRowCount(len(results))
        
        for row_idx, result in enumerate(results):
            for col_idx, col in enumerate(columns):
                value = result.get(col, '')
                self.results_table.setItem(row_idx, col_idx, QTableWidgetItem(str(value) if value else ""))
        
        self.results_table.resizeColumnsToContents()
        self.status_label.setText(f"Fetched {len(results)} series")
    
    def _on_progress(self, message):
        """Handle progress updates"""
        self.status_label.setText(message)
    
    def _on_error(self, error_msg):
        """Handle error"""
        self.status_label.setText(f"Error: {error_msg}")
        self.fetch_btn.setEnabled(True)
    
    def _on_finished(self):
        """Handle completion"""
        self.fetch_btn.setEnabled(True)

# =========================================================
# MAIN
# =========================================================
if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = FREDFetcherApp()
    window.show()
    sys.exit(app.exec())