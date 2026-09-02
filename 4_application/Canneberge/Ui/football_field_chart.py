"""
football_field_chart.py — Professional Matplotlib Football Field Chart.

Consumes bridged method rows from Dashboard and paints:
  - Horizontal range bars with exact Low - High data callouts.
  - Concluded FV vertical line with a top value badge.
  - Observed Market (EV / Market Cap / Share Price) vertical line with a top badge.
  - Basis-aware X-axis and legend formatting.
"""

from typing import Optional, List, Tuple

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QDialog
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from matplotlib.patches import Patch
from matplotlib.lines import Line2D
from matplotlib.ticker import FuncFormatter

from Canneberge.Ui.theme import theme_manager

BAR_HEIGHT = 0.45


def _fmt_val(val: Optional[float], basis: str) -> str:
    if val is None:
        return ""
    if basis == "$/Share":
        return f"${val:,.2f}"
    return f"${val:,.0f}"


class FootballFieldChart(QWidget):
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setMinimumSize(620, 320)

        self._figure = Figure(figsize=(7.0, 3.6), tight_layout=True)
        self._canvas = FigureCanvasQTAgg(self._figure)

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._canvas)
        self.setLayout(layout)

        self._last_chart_args = None
        self._draw_empty("No method values to plot")

        theme_manager.theme_changed.connect(self._on_theme_changed)

    def _on_theme_changed(self, _theme=None):
        if self._last_chart_args is not None:
            self.update_chart(*self._last_chart_args)
        else:
            self._draw_empty("No method values to plot")

    def _draw_empty(self, message: str):
        t = theme_manager.current
        self._figure.clear()
        self._figure.patch.set_facecolor(t.window_bg)
        ax = self._figure.add_subplot(111)
        ax.set_facecolor(t.window_bg)
        ax.set_xticks([])
        ax.set_yticks([])
        ax.text(
            0.5, 0.5, message,
            ha="center", va="center",
            color=t.chart_axis_label, transform=ax.transAxes,
            fontsize=10
        )
        self._canvas.draw()

    def update_chart(
        self,
        rows: List[Tuple[str, Optional[float], Optional[float]]],
        share_price_marker: Optional[float],
        concluded_fv: Optional[float],
        basis: str,
    ):
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

        # Plot top row at top of chart
        labels = [r[0] for r in plotted]
        n_rows = len(plotted)
        y_positions = list(range(n_rows - 1, -1, -1))

        all_values = []
        for _, low, high in plotted:
            all_values.extend([low, high])
        if share_price_marker is not None:
            all_values.append(share_price_marker)
        if concluded_fv is not None:
            all_values.append(concluded_fv)

        min_val = min(all_values) if all_values else 0
        max_val = max(all_values) if all_values else 100
        val_range = max_val - min_val if max_val != min_val else 1.0

        # Draw horizontal bars and data text labels
        for (label, low, high), y in zip(plotted, y_positions):
            width = high - low
            if width == 0:
                width = max(abs(high) * 0.002, 1e-9)

            ax.barh(
                y, width, left=low, height=BAR_HEIGHT,
                color=t.chart_fill, edgecolor=t.chart_edge,
                linewidth=0.8, zorder=3,
            )

            # Text callouts at ends of bar: "Low - High"
            low_str = _fmt_val(low, basis)
            high_str = _fmt_val(high, basis)

            # Low label (left of bar)
            ax.text(
                low - (val_range * 0.012), y, low_str,
                va="center", ha="right",
                color=t.default_text, fontsize=7.5, zorder=4
            )
            # High label (right of bar)
            ax.text(
                high + (val_range * 0.012), y, high_str,
                va="center", ha="left",
                color=t.default_text, fontsize=7.5, zorder=4
            )

        ax.set_yticks(y_positions)
        ax.set_yticklabels(labels, fontsize=8, color=t.default_text)

        # Vertical marker lines only (no top badges — legend carries the meaning)
        if basis == "Equity":
            marker_title = "Market Cap"
        elif basis == "$/Share":
            marker_title = "Share Price"
        else:
            marker_title = "Observed EV"

        if share_price_marker is not None:
            ax.axvline(
                share_price_marker, color=t.chart_share_price,
                linewidth=1.8, linestyle="--", zorder=4
            )

        if concluded_fv is not None:
            ax.axvline(
                concluded_fv, color=t.chart_conclude,
                linewidth=2.2, zorder=4
            )

        # Tight row spacing — no extra headroom for badges
        ax.set_ylim(-0.6, n_rows - 0.4)
        ax.set_xlim(min_val - (val_range * 0.12), max_val + (val_range * 0.12))

        # Axis styling & Formatting
        if basis == "$/Share":
            formatter = FuncFormatter(lambda x, _: f"${x:,.2f}")
        else:
            formatter = FuncFormatter(lambda x, _: f"${x:,.0f}")

        ax.xaxis.set_major_formatter(formatter)
        ax.tick_params(axis="x", labelsize=8, colors=t.chart_axis_label)
        ax.tick_params(axis="y", colors=t.default_text)
        ax.grid(axis="x", color=t.chart_grid, linestyle=":", linewidth=0.7, zorder=0)

        for spine in ax.spines.values():
            spine.set_color(t.chart_grid)

        # Legend
        legend_items = [
            Patch(facecolor=t.chart_fill, edgecolor=t.chart_edge, label="Valuation Range"),
            Line2D([0], [0], color=t.chart_share_price, linewidth=1.8, linestyle="--", label=marker_title),
            Line2D([0], [0], color=t.chart_conclude, linewidth=2.2, label="Concluded FV"),
        ]
        legend = ax.legend(
            handles=legend_items, loc="lower right",
            fontsize=7.5, frameon=True, facecolor=t.window_bg,
            edgecolor=t.chart_grid, labelcolor=t.default_text
        )

        self._canvas.draw()


class FootballFieldChartDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Football Field Chart")
        self.resize(950, 520)

        layout = QVBoxLayout(self)
        self.chart = FootballFieldChart(self)
        layout.addWidget(self.chart)

    def update_chart(self, rows, share_price_marker, concluded_fv, basis):
        self.chart.update_chart(rows, share_price_marker, concluded_fv, basis)