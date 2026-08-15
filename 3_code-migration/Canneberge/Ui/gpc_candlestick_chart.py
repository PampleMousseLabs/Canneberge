"""
gpc_candlestick_chart.py
Canneberge — GPC Multiples Range chart.

Renders an OHLC-style candlestick chart, one "candle" per selected GPC
multiple column, where:
    Open  = Third Quartile
    High  = Maximum
    Low   = Minimum
    Close = First Quartile

This is not a time-series chart — categories are metric names (e.g.
"TTM Revenue", "NFY EBITDA"), not dates. Mirrors the "Range of Selected
Multiples" chart from the Excel Dashboard.

Live-bound: GPCPage calls update_data() at the end of every
_recalculate(), so toggling an Exclude checkbox or changing the
multiple count redraws this chart automatically if it's open.
"""

from typing import List, Optional

from PyQt6.QtWidgets import QDialog, QVBoxLayout
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure

from Canneberge.Ui.theme import theme_manager

BODY_WIDTH = 0.5
WICK_WIDTH = 1.5


class GPCCandlestickChart(QDialog):
    """
    Generic OHLC-style candlestick chart for a set of "Range of
    Selected Multiples"-style columns. Despite the module/class name
    (kept as-is to avoid touching GPCPage's existing import), nothing
    in here is GPC-specific — GTPage reuses this same class with its
    own window_title/chart_title rather than a duplicated file.
    """

    def __init__(self, parent=None, window_title: str = "GPC Multiples Range",
                 chart_title: str = "Range of Selected Multiples"):
        super().__init__(parent)
        self.setWindowTitle(window_title)
        self._chart_title = chart_title
        self.setMinimumSize(900, 500)

        self.figure = Figure(figsize=(9, 5))
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.ax = self.figure.add_subplot(111)
        self._apply_theme_colors()  # background only at construction; full redraw happens in update_data

        layout = QVBoxLayout()
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addWidget(self.canvas)
        self.setLayout(layout)

        self._last_data = None

        # Redraw fully on theme switch — matplotlib has no equivalent
        # of a Qt stylesheet that live-updates, so this just re-runs
        # update_data() with whatever was last plotted (same pattern
        # showEvent already uses below).
        theme_manager.theme_changed.connect(self._on_theme_changed)

    def _on_theme_changed(self, _theme=None):
        self._apply_theme_colors()
        if self._last_data is not None:
            self.update_data(*self._last_data)

    def _apply_theme_colors(self):
        t = theme_manager.current
        self.figure.patch.set_facecolor(t.window_bg)
        self.ax.set_facecolor(t.window_bg)

    def update_data(
        self,
        labels: List[str],
        opens: List[Optional[float]],
        highs: List[Optional[float]],
        lows: List[Optional[float]],
        closes: List[Optional[float]],
    ):
        """
        Redraws the chart. Any column where all four of
        open/high/low/close are None is skipped entirely (an excluded
        column, or a metric with no data — nothing to plot).
        """
        self._last_data = (labels, opens, highs, lows, closes)

        t = theme_manager.current
        self.ax.clear()
        self._apply_theme_colors()

        plotted_labels = []
        x = 0

        for label, o, h, l, c in zip(labels, opens, highs, lows, closes):
            if o is None and h is None and l is None and c is None:
                continue

            plotted_labels.append(label)

            if h is not None and l is not None:
                self.ax.plot(
                    [x, x], [l, h],
                    color=t.chart_edge, linewidth=WICK_WIDTH, zorder=2,
                )

            if o is not None and c is not None:
                body_bottom = min(o, c)
                body_height = abs(o - c)
                if body_height == 0:
                    body_height = (h - l) * 0.02 if (h is not None and l is not None and h != l) else 0.01
                self.ax.bar(
                    x, body_height, bottom=body_bottom, width=BODY_WIDTH,
                    color=t.chart_fill, edgecolor=t.chart_edge, zorder=3,
                )

            x += 1

        self.ax.set_xticks(range(len(plotted_labels)))
        self.ax.set_xticklabels(plotted_labels, rotation=30, ha="right", fontsize=8)
        self.ax.set_ylabel("Multiple (x)", color=t.default_text)
        self.ax.set_title(self._chart_title, color=t.default_text)
        self.ax.axhline(0, color=t.chart_grid, linewidth=0.8, zorder=1)
        self.ax.grid(True, axis="y", alpha=0.3, zorder=0, color=t.chart_grid)
        self.ax.tick_params(colors=t.chart_axis_label)
        for spine in self.ax.spines.values():
            spine.set_color(t.chart_grid)

        self.figure.tight_layout()
        self.canvas.draw()

    def showEvent(self, event):
        super().showEvent(event)
        if self._last_data is not None:
            self.update_data(*self._last_data)