"""
football_field_chart.py — Reconciliation of Values football field.

Embedded widget (not a dialog) driven by the Dashboard's bridge rows.
Draws one horizontal Low->High bar per method-multiple, plus two
vertical marker lines:

  - Share Price (dark blue), converted to the active display basis:
        $/Share : price
        Equity  : price * shares  (= market cap)
        BEV     : market cap + debt - cash  (enterprise-style bridge)
  - Concluded FV (gold), already on the display basis.

Legend: Range / Share Price / Concluded FV.
Number axis on the bottom.
"""

from typing import Optional, List, Tuple

from PyQt6.QtWidgets import QWidget, QVBoxLayout
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from matplotlib.patches import Patch
from matplotlib.lines import Line2D

from Canneberge.Ui.theme import theme_manager

BAR_HEIGHT = 0.55


class FootballFieldChart(QWidget):
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setMinimumSize(600, 260)

        self._figure = Figure(figsize=(6.2, 2.8), tight_layout=True)
        self._canvas = FigureCanvasQTAgg(self._figure)

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._canvas)
        self.setLayout(layout)

        # Tracks the last real update_chart(...) call so a theme
        # switch can redraw with the same data instead of reverting
        # to the empty placeholder. None until the first real draw.
        self._last_chart_args = None

        self._draw_empty("No data yet")

        # This is an embedded, always-visible widget (unlike the GPC
        # candlestick chart, which is a popup dialog) - so it needs to
        # pick up theme switches live the whole time the Dashboard tab
        # exists, not just while a dialog happens to be open.
        theme_manager.theme_changed.connect(self._on_theme_changed)

    def _on_theme_changed(self, _theme=None):
        if self._last_chart_args is not None:
            self.update_chart(*self._last_chart_args)
        else:
            self._draw_empty("No data yet")

    def _draw_empty(self, message: str):
        t = theme_manager.current
        self._figure.clear()
        self._figure.patch.set_facecolor(t.window_bg)
        ax = self._figure.add_subplot(111)
        ax.set_facecolor(t.window_bg)
        ax.set_xticks([])
        ax.set_yticks([])
        ax.text(0.5, 0.5, message, ha="center", va="center",
                 color=t.chart_axis_label, transform=ax.transAxes)
        self._canvas.draw()

    def update_chart(
        self,
        rows: List[Tuple[str, Optional[float], Optional[float]]],
        share_price_marker: Optional[float],
        concluded_fv: Optional[float],
        basis: str,
    ):
        """
        rows: list of (label, low, high) already on the display basis,
              ordered top-to-bottom.
        share_price_marker: already converted to the display basis.
        concluded_fv: already on the display basis.
        """
        # Remember these so a theme switch can redraw identically.
        self._last_chart_args = (rows, share_price_marker, concluded_fv, basis)

        t = theme_manager.current

        plotted = [
            (label, low, high)
            for label, low, high in rows
            if low is not None and high is not None
        ]
        if not plotted:
            self._draw_empty("No method values to plot")
            return

        self._figure.clear()
        self._figure.patch.set_facecolor(t.window_bg)
        ax = self._figure.add_subplot(111)
        ax.set_facecolor(t.window_bg)

        # Top row of the data should appear at the top of the chart.
        labels = [r[0] for r in plotted]
        y_positions = list(range(len(plotted) - 1, -1, -1))

        for (label, low, high), y in zip(plotted, y_positions):
            width = high - low
            if width == 0:
                # Zero-width range still needs a visible tick.
                width = max(abs(high) * 0.002, 1e-9)
            ax.barh(
                y, width, left=low, height=BAR_HEIGHT,
                color=t.chart_fill, edgecolor="none", zorder=2,
            )

        ax.set_yticks(y_positions)
        ax.set_yticklabels(labels, fontsize=7)

        if share_price_marker is not None:
            ax.axvline(share_price_marker, color=t.chart_share_price,
                       linewidth=1.6, zorder=3)
        if concluded_fv is not None:
            ax.axvline(concluded_fv, color=t.chart_conclude,
                       linewidth=2.0, zorder=3)

        # Bottom number axis, formatted per basis.
        if basis == "$/Share":
            ax.xaxis.set_major_formatter(
                lambda x, _pos: f"{x:,.0f}")
        else:
            ax.xaxis.set_major_formatter(
                lambda x, _pos: f"{x:,.0f}")
        ax.tick_params(axis="x", labelsize=7, colors=t.chart_axis_label)
        ax.tick_params(axis="y", colors=t.default_text)
        ax.xaxis.set_ticks_position("bottom")

        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.spines["left"].set_visible(False)
        ax.spines["bottom"].set_color(t.chart_grid)
        ax.grid(axis="x", color=t.chart_grid, linewidth=0.6, zorder=0)

        legend_items = [
            Patch(facecolor=t.chart_fill, label="Range"),
            Line2D([0], [0], color=t.chart_share_price,
                   linewidth=1.6, label="Share Price"),
            Line2D([0], [0], color=t.chart_conclude,
                   linewidth=2.0, label="Concluded FV"),
        ]
        legend = ax.legend(handles=legend_items, loc="lower right",
                            fontsize=7, frameon=False)
        for text in legend.get_texts():
            text.set_color(t.default_text)

        self._canvas.draw()