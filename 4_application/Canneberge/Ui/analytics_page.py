"""
analytics_page.py — PLACEHOLDER

Capital-structure / analytics UI intentionally cleared.
Revisit when optimal-vs-actual capital structure chart is defined.
"""

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel


class AnalyticsPage(QWidget):
    """Stub so MainWindow can import and addTab without crashing."""

    def __init__(self, *args, **kwargs):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel(
                "Analytics — placeholder.\n"
                "Previous FCFF/FCFE / PVGO tooling removed."
            )
        )

    def refresh(self):
        pass