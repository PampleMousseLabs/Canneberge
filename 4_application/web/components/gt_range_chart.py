"""
Plotly range chart for GT transaction multiples.

Equivalent to the desktop GPCCandlestickChart:
Open = Q3
High = Maximum
Low = Minimum
Close = Q1
"""

from __future__ import annotations

from typing import Optional, List

import plotly.graph_objects as go


def gt_range_chart(
    labels: List[str],
    q3: List[Optional[float]],
    max_vals: List[Optional[float]],
    min_vals: List[Optional[float]],
    q1: List[Optional[float]],
    title: str = "Range of Selected Transaction Multiples",
):
    usable = [
        (label, o, h, l, c)
        for label, o, h, l, c in zip(
            labels or [],
            q3 or [],
            max_vals or [],
            min_vals or [],
            q1 or [],
        )
        if any(value is not None for value in (o, h, l, c))
    ]

    figure = go.Figure()

    if usable:
        figure.add_trace(
            go.Candlestick(
                x=[row[0] for row in usable],
                open=[row[1] for row in usable],
                high=[row[2] for row in usable],
                low=[row[3] for row in usable],
                close=[row[4] for row in usable],
                increasing={
                    "line": {"color": "#e5c07b", "width": 2},
                    "fillcolor": "#c678dd",
                },
                decreasing={
                    "line": {"color": "#e5c07b", "width": 2},
                    "fillcolor": "#c678dd",
                },
                whiskerwidth=0.5,
                name="Multiple Range",
            )
        )
    else:
        figure.add_annotation(
            text="No usable transaction multiples",
            xref="paper",
            yref="paper",
            x=0.5,
            y=0.5,
            showarrow=False,
            font={"color": "#9fb3c8", "size": 13},
        )

    figure.update_layout(
        title={
            "text": title,
            "font": {"color": "#e6e6e6", "size": 16},
        },
        paper_bgcolor="#1e1e1e",
        plot_bgcolor="#1e1e1e",
        font={"color": "#9fb3c8"},
        height=500,
        margin={"l": 60, "r": 30, "t": 55, "b": 80},
        xaxis={
            "gridcolor": "#3a4553",
            "rangeslider": {"visible": False},
            "tickangle": -30,
        },
        yaxis={
            "title": "Multiple (x)",
            "gridcolor": "#3a4553",
            "zerolinecolor": "#3a4553",
        },
        showlegend=False,
    )

    return figure