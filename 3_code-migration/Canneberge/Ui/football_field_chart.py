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

RANGE_COLOR = "#8b7fd1"      # same family as the candlestick chart
SHARE_PRICE_COLOR = "#1a1a8c"
CONCLUDED_COLOR = "#e6b800"
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

        self._draw_empty("No data yet")

    def _draw_empty(self, message: str):
        self._figure.clear()
        ax = self._figure.add_subplot(111)
        ax.set_xticks([])
        ax.set_yticks([])
        ax.text(0.5, 0.5, message, ha="center", va="center",
                color="#888888", transform=ax.transAxes)
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
        plotted = [
            (label, low, high)
            for label, low, high in rows
            if low is not None and high is not None
        ]
        if not plotted:
            self._draw_empty("No method values to plot")
            return

        self._figure.clear()
        ax = self._figure.add_subplot(111)

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
                color=RANGE_COLOR, edgecolor="none", zorder=2,
            )

        ax.set_yticks(y_positions)
        ax.set_yticklabels(labels, fontsize=7)

        if share_price_marker is not None:
            ax.axvline(share_price_marker, color=SHARE_PRICE_COLOR,
                       linewidth=1.6, zorder=3)
        if concluded_fv is not None:
            ax.axvline(concluded_fv, color=CONCLUDED_COLOR,
                       linewidth=2.0, zorder=3)

        # Bottom number axis, formatted per basis.
        if basis == "$/Share":
            ax.xaxis.set_major_formatter(
                lambda x, _pos: f"{x:,.0f}")
        else:
            ax.xaxis.set_major_formatter(
                lambda x, _pos: f"{x:,.0f}")
        ax.tick_params(axis="x", labelsize=7)
        ax.xaxis.set_ticks_position("bottom")

        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.spines["left"].set_visible(False)
        ax.grid(axis="x", color="#dddddd", linewidth=0.6, zorder=0)

        legend_items = [
            Patch(facecolor=RANGE_COLOR, label="Range"),
            Line2D([0], [0], color=SHARE_PRICE_COLOR,
                   linewidth=1.6, label="Share Price"),
            Line2D([0], [0], color=CONCLUDED_COLOR,
                   linewidth=2.0, label="Concluded FV"),
        ]
        ax.legend(handles=legend_items, loc="lower right",
                  fontsize=7, frameon=False)

        self._canvas.draw()