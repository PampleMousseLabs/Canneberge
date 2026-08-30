"""
valuation_surface_chart.py
Canneberge — 3D Valuation Surface Chart (Pattern B: Interactive Slicers).

Renders a valuation surface mesh plot for Gordon Growth or H-Model:
    X axis = WACC (%)
    Y axis = LTGR / Gn (%)
    Z axis = Fair Value

Includes interactive sliders for Short-Term Growth (Ga) and Transition Years (H)
when in H-Model mode.
"""

from typing import Optional, Dict, Any, Callable

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QSlider, QDoubleSpinBox, QGroupBox, QFrame
)
from PyQt6.QtCore import Qt
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from mpl_toolkits.mplot3d import Axes3D  # noqa: F401
import numpy as np

from Canneberge.Ui.theme import theme_manager


class GGSurfaceChart(QDialog):
    def __init__(self, parent=None, fv_evaluator: Optional[Callable] = None):
        super().__init__(parent)
        self.setWindowTitle("Valuation Surface — 3D Sensitivity")
        self.setMinimumSize(950, 720)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

        self._fv_evaluator = fv_evaluator
        self._last_data: Optional[Dict[str, Any]] = None

        self.figure = Figure(figsize=(9, 5.5))
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.ax: Axes3D = self.figure.add_subplot(111, projection="3d")

        self._apply_theme_colors()

        layout = QVBoxLayout()
        layout.setContentsMargins(10, 10, 10, 10)

        # 1. Info header row (Center FV, High, Low)
        info_row = QHBoxLayout()
        self._lbl_model_badge = QLabel("Model: —")
        self._lbl_center = QLabel("Center FV: —")
        self._lbl_high   = QLabel("High FV: —")
        self._lbl_low    = QLabel("Low FV: —")
        
        info_row.addWidget(self._lbl_model_badge)
        info_row.addSpacing(20)
        for lbl in [self._lbl_center, self._lbl_high, self._lbl_low]:
            info_row.addWidget(lbl)
        info_row.addStretch()
        layout.addLayout(info_row)

        # 2. Main 3D Canvas
        layout.addWidget(self.canvas, 1)

        # 3. Pattern B: Interactive Slicers Panel (Ga & H Sliders)
        self.controls_box = QGroupBox("H-Model Dimension Slicers (Multi-Dimensional Control)")
        controls_layout = QHBoxLayout()
        controls_layout.setContentsMargins(10, 8, 10, 8)

        # --- Ga Slicer (Short-Term Growth) ---
        ga_layout = QHBoxLayout()
        ga_layout.addWidget(QLabel("ST Growth (Ga):"))
        self.slider_ga = QSlider(Qt.Orientation.Horizontal)
        self.slider_ga.setRange(0, 600)  # 0.0% to 60.0%
        self.slider_ga.setValue(200)       # default 20.0%
        self.slider_ga.setFixedWidth(140)

        self.spin_ga = QDoubleSpinBox()
        self.spin_ga.setRange(0.0, 60.0)
        self.spin_ga.setSingleStep(0.5)
        self.spin_ga.setSuffix("%")
        self.spin_ga.setValue(20.0)
        self.spin_ga.setFixedWidth(75)

        ga_layout.addWidget(self.slider_ga)
        ga_layout.addWidget(self.spin_ga)
        controls_layout.addLayout(ga_layout)

        controls_layout.addSpacing(20)

        # --- H Slicer (Transition Period Years) ---
        h_layout = QHBoxLayout()
        h_layout.addWidget(QLabel("Transition Years (H):"))
        self.slider_h = QSlider(Qt.Orientation.Horizontal)
        self.slider_h.setRange(10, 200)  # 1.0 to 20.0 years
        self.slider_h.setValue(50)        # default 5.0 years
        self.slider_h.setFixedWidth(140)

        self.spin_h = QDoubleSpinBox()
        self.spin_h.setRange(1.0, 20.0)
        self.spin_h.setSingleStep(0.5)
        self.spin_h.setSuffix(" yrs")
        self.spin_h.setValue(5.0)
        self.spin_h.setFixedWidth(75)

        h_layout.addWidget(self.slider_h)
        h_layout.addWidget(self.spin_h)
        controls_layout.addLayout(h_layout)

        controls_layout.addStretch()
        self.controls_box.setLayout(controls_layout)
        layout.addWidget(self.controls_box)

        # Sync sliders <-> spinboxes
        self.slider_ga.valueChanged.connect(lambda v: self.spin_ga.setValue(v / 10.0))
        self.spin_ga.valueChanged.connect(lambda v: self.slider_ga.setValue(int(v * 10.0)))
        self.slider_h.valueChanged.connect(lambda v: self.spin_h.setValue(v / 10.0))
        self.spin_h.valueChanged.connect(lambda v: self.slider_h.setValue(int(v * 10.0)))

        # Live recalculation on control changes
        self.spin_ga.valueChanged.connect(self._on_slicer_changed)
        self.spin_h.valueChanged.connect(self._on_slicer_changed)

        self.setLayout(layout)
        self._apply_styles()
        theme_manager.theme_changed.connect(self._on_theme_changed)

    def _apply_styles(self):
        t = theme_manager.current
        bold_fmt = f"font-weight: bold; color: {t.bold_text};"
        self._lbl_model_badge.setStyleSheet(f"font-weight: bold; padding: 2px 6px; border-radius: 4px; background: {t.chart_fill}; color: {t.default_text};")
        self._lbl_center.setStyleSheet(bold_fmt)
        self._lbl_high.setStyleSheet(bold_fmt)
        self._lbl_low.setStyleSheet(bold_fmt)
        self.controls_box.setStyleSheet(f"QGroupBox {{ font-weight: bold; color: {t.default_text}; border: 1px solid {t.border_color}; margin-top: 6px; }} QGroupBox::title {{ subcontrol-origin: margin; left: 8px; padding: 0 4px; }}")

    def _on_theme_changed(self, _theme=None):
        self._apply_theme_colors()
        self._apply_styles()
        if self._last_data is not None:
            self.update_data(self._last_data)

    def _apply_theme_colors(self):
        t = theme_manager.current
        self.figure.patch.set_facecolor(t.window_bg)
        self.ax.set_facecolor(t.window_bg)

    def set_evaluator(self, fv_evaluator: Callable):
        self._fv_evaluator = fv_evaluator

    def _on_slicer_changed(self):
        """Triggered live when user drags Ga or H sliders in H-Model mode."""
        if not self._last_data or not self._fv_evaluator:
            return

        model_name = self._last_data.get("model_name", "Gordon Growth")
        if model_name != "H-Model":
            return

        ga_val = self.spin_ga.value() / 100.0
        h_val  = self.spin_h.value()

        wacc_vals = self._last_data["wacc_values"]
        ltgr_vals = self._last_data["ltgr_values"]

        # Recompute grid in memory (0.001 seconds)
        from Canneberge.Calculations.valuation_surface import compute_gg_surface_data_from_explicit
        
        def fv_func(w, l):
            return self._fv_evaluator(w, l, ga_override=ga_val, h_override=h_val)

        new_surface = compute_gg_surface_data_from_explicit(
            fv_func=fv_func,
            wacc_values=wacc_vals,
            ltgr_values=ltgr_vals,
            model_name="H-Model",
        )
        self.update_data(new_surface)

    def update_data(self, surface_result: Dict[str, Any]):
        self._last_data = surface_result
        t = theme_manager.current

        model_name = surface_result.get("model_name", "Gordon Growth")
        self.setWindowTitle(f"{model_name} — Valuation Surface")
        self._lbl_model_badge.setText(f"Model: {model_name}")

        # Enable/Disable Pattern B sliders based on active model
        is_h_model = (model_name == "H-Model")
        self.controls_box.setEnabled(is_h_model)
        if not is_h_model:
            self.controls_box.setTitle("H-Model Dimension Slicers (Disabled — Active Model is Gordon Growth)")
        else:
            self.controls_box.setTitle("H-Model Dimension Slicers (Multi-Dimensional Control)")

        self.figure.clear()
        self.ax = self.figure.add_subplot(111, projection="3d")
        self._apply_theme_colors()

        wacc_vals = surface_result["wacc_values"]
        ltgr_vals = surface_result["ltgr_values"]
        fv_grid   = surface_result["fv_grid"]
        center_fv = surface_result["center_fv"]
        grid_size = surface_result["grid_size"]

        W = np.array(wacc_vals) * 100
        G = np.array(ltgr_vals) * 100
        WW, GG = np.meshgrid(W, G, indexing="ij")

        Z = np.full((grid_size, grid_size), np.nan)
        for i in range(grid_size):
            for j in range(grid_size):
                v = fv_grid[i][j]
                if v is not None:
                    Z[i, j] = v

        surf = self.ax.plot_surface(
            WW, GG, Z,
            cmap="coolwarm",
            alpha=0.85,
            edgecolor="none",
            antialiased=True,
        )

        cbar = self.figure.colorbar(surf, ax=self.ax, shrink=0.5, pad=0.1)
        cbar.ax.yaxis.set_tick_params(color=t.chart_axis_label)
        cbar.ax.tick_params(colors=t.chart_axis_label, labelsize=7)
        cbar.set_label("Fair Value", color=t.default_text, fontsize=8)

        conc_high = surface_result.get("conclusion_high", {})
        conc_low  = surface_result.get("conclusion_low", {})

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

        self.ax.set_xlabel("Discount Rate / WACC (%)", color=t.default_text, fontsize=9, labelpad=8)
        self.ax.set_ylabel("LTGR / Gn (%)", color=t.default_text, fontsize=9, labelpad=8)
        self.ax.set_zlabel("Fair Value", color=t.default_text, fontsize=9, labelpad=8)
        self.ax.set_title(
            f"{model_name} — Fair Value Surface\n(WACC × LTGR)",
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

        self._lbl_center.setText(f"Center FV: {center_fv:,.0f}" if center_fv else "Center FV: —")
        self._lbl_high.setText(f"FV High: {conc_high['fv']:,.0f}" if conc_high.get("fv") else "FV High: —")
        self._lbl_low.setText(f"FV Low: {conc_low['fv']:,.0f}" if conc_low.get("fv") else "FV Low: —")

        self.figure.tight_layout()
        self.canvas.draw()