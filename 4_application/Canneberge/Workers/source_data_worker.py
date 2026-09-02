import traceback

from PyQt6.QtCore import QThread, pyqtSignal

from Canneberge.Services.source_data_service import SourceDataService


class SourceDataWorker(QThread):
    progress = pyqtSignal(str)
    error = pyqtSignal(str)
    results = pyqtSignal(str, object)  # source_name, results

    def __init__(self, project_inputs, source_name, **kwargs):
        super().__init__()
        self.project_inputs = project_inputs
        self.source_name = source_name
        self.kwargs = kwargs

    def run(self):
        try:
            service = SourceDataService(
                project_inputs=self.project_inputs,
                progress_callback=self.progress.emit
            )
            method = getattr(service, f"refresh_{self.source_name}")
            results = method(**self.kwargs)
            self.results.emit(self.source_name, results)
        except Exception as e:
            traceback.print_exc()
            self.error.emit(str(e))