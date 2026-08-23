"""
valuation_surface_chart.py
Canneberge — 3D Valuation Surface Chart.

Renders a Gordon Growth fair value surface as a 3D mesh plot:
    X axis = WACC
    Y axis = LTGR
    Z axis = Fair Value

High and Low FV points are marked as distinct colored dots with labels.
Theme-aware: redraws on theme_changed signal.
Non-modal: opened with show(), not exec().

Pattern mirrors gpc_candlestick_chart.py exactly.
"""

from typing import Optional, Dict, Any

from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton
from PyQt6.QtCore import Qt
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from mpl_toolkits.mplot3d import Axes3D  # noqa: F401 — registers 3D projection
import numpy as np

from Canneberge.Ui.theme import theme_manager


class GGSurfaceChart(QDialog):
    """
    3D Gordon Growth valuation surface.
    Call update_data(surface_result) to draw/redraw.
    surface_result is the dict returned by compute_gg_surface_data().
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Gordon Growth — Valuation Surface")
        self.setMinimumSize(900, 650)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

        self._last_data: Optional[Dict[str, Any]] = None

        self.figure = Figure(figsize=(9, 6))
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.ax: Axes3D = self.figure.add_subplot(111, projection="3d")

        self._apply_theme_colors()

        layout = QVBoxLayout()
        layout.setContentsMargins(8, 8, 8, 8)

        # Info row: center FV, high, low
        info_row = QHBoxLayout()
        self._lbl_center = QLabel("Center FV: —")
        self._lbl_high   = QLabel("High FV: —")
        self._lbl_low    = QLabel("Low FV: —")
        for lbl in [self._lbl_center, self._lbl_high, self._lbl_low]:
            lbl.setStyleSheet(f"font-weight: bold; color: {theme_manager.current.bold_text};")
            info_row.addWidget(lbl)
        info_row.addStretch()
        layout.addLayout(info_row)
        layout.addWidget(self.canvas)
        self.setLayout(layout)

        theme_manager.theme_changed.connect(self._on_theme_changed)

    def _on_theme_changed(self, _theme=None):
        self._apply_theme_colors()
        if self._last_data is not None:
            self.update_data(self._last_data)

    def _apply_theme_colors(self):
        t = theme_manager.current
        self.figure.patch.set_facecolor(t.window_bg)
        self.ax.set_facecolor(t.window_bg)

    def update_data(self, surface_result: Dict[str, Any]):
        self._last_data = surface_result
        t = theme_manager.current

        self.figure.clear()
        self.ax = self.figure.add_subplot(111, projection="3d")
        self._apply_theme_colors()

        wacc_vals = surface_result["wacc_values"]
        ltgr_vals = surface_result["ltgr_values"]
        fv_grid   = surface_result["fv_grid"]
        high_pt   = surface_result["high_point"]
        low_pt    = surface_result["low_point"]
        center_fv = surface_result["center_fv"]
        grid_size = surface_result["grid_size"]

        # Build numpy arrays for surface plot
        # fv_grid[i][j] = FV at wacc_vals[i], ltgr_vals[j]
        W = np.array(wacc_vals) * 100   # convert to % for display
        G = np.array(ltgr_vals) * 100
        WW, GG = np.meshgrid(W, G, indexing="ij")

        # Build Z — replace None with nan for matplotlib
        Z = np.full((grid_size, grid_size), np.nan)
        for i in range(grid_size):
            for j in range(grid_size):
                v = fv_grid[i][j]
                if v is not None:
                    Z[i, j] = v

        # Surface plot
        surf = self.ax.plot_surface(
            WW, GG, Z,
            cmap="coolwarm",
            alpha=0.85,
            edgecolor="none",
            antialiased=True,
        )

        # Colorbar
        cbar = self.figure.colorbar(surf, ax=self.ax, shrink=0.5, pad=0.1)
        cbar.ax.yaxis.set_tick_params(color=t.chart_axis_label)
        cbar.ax.tick_params(colors=t.chart_axis_label, labelsize=7)
        cbar.set_label("Fair Value", color=t.default_text, fontsize=8)

        conc_high = surface_result.get("conclusion_high", {})
        conc_low  = surface_result.get("conclusion_low", {})

        # Conclusion High marker (one step in from corner — matches table)
        if conc_high.get("fv") is not None:
            self.ax.scatter(
                conc_high["wacc"] * 100,
                conc_high["ltgr"] * 100,
                conc_high["fv"],
                color=t.chart_conclude,
                s=100, zorder=5, marker="^",
            )
            self.ax.text(
                conc_high["wacc"] * 100,
                conc_high["ltgr"] * 100,
                conc_high["fv"],
                f"  FV High\n  {conc_high['fv']:,.0f}",
                color=t.chart_conclude,
                fontsize=7,
            )

        # Conclusion Low marker (one step in from corner — matches table)
        if conc_low.get("fv") is not None:
            self.ax.scatter(
                conc_low["wacc"] * 100,
                conc_low["ltgr"] * 100,
                conc_low["fv"],
                color=t.chart_share_price,
                s=100, zorder=5, marker="v",
            )
            self.ax.text(
                conc_low["wacc"] * 100,
                conc_low["ltgr"] * 100,
                conc_low["fv"],
                f"  FV Low\n  {conc_low['fv']:,.0f}",
                color=t.chart_share_price,
                fontsize=7,
            )

        # Axes
        self.ax.set_xlabel("WACC (%)", color=t.default_text, fontsize=9, labelpad=8)
        self.ax.set_ylabel("LTGR (%)", color=t.default_text, fontsize=9, labelpad=8)
        self.ax.set_zlabel("Fair Value", color=t.default_text, fontsize=9, labelpad=8)
        self.ax.set_title(
            "Gordon Growth — Fair Value Surface\n(WACC × LTGR)",
            color=t.default_text, fontsize=10,
        )
        self.ax.tick_params(colors=t.chart_axis_label, labelsize=7)
        self.ax.xaxis.pane.fill = False
        self.ax.yaxis.pane.fill = False
        self.ax.zaxis.pane.fill = False
        self.ax.xaxis.pane.set_edgecolor(t.chart_grid)
        self.ax.yaxis.pane.set_edgecolor(t.chart_grid)
        self.ax.zaxis.pane.set_edgecolor(t.chart_grid)
        self.ax.grid(True, color=t.chart_grid, alpha=0.3)

        # Info labels — conclusion High/Low match sensitivity table
        conc_high = surface_result.get("conclusion_high", {})
        conc_low  = surface_result.get("conclusion_low", {})
        self._lbl_center.setText(f"Center FV: {center_fv:,.0f}" if center_fv else "Center FV: —")
        self._lbl_high.setText(f"FV High: {conc_high['fv']:,.0f}" if conc_high.get("fv") else "FV High: —")
        self._lbl_low.setText(f"FV Low: {conc_low['fv']:,.0f}" if conc_low.get("fv") else "FV Low: —")

        self.figure.tight_layout()
        self.canvas.draw()

    def showEvent(self, event):
        super().showEvent(event)
        if self._last_data is not None:
            self.update_data(self._last_data)