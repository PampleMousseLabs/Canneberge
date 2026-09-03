"""
web/lib/ui_layout.py

Shared layout + DataTable style tokens for dense read-only grids.

House rules:
  1. Never hardcode style_header / style_cell / style_table on page DataTables.
     Import builders from this module.
  2. dash_table does NOT honor height: "100%" reliably — always use
     grid_table_style() which sets explicit calc(100vh - Npx).
  3. Theme swap later = change COLORS (or load from a theme manager).
     Pages should not need edits.

Home page editable GT table is intentionally NOT covered here yet.
"""

from typing import List, Optional

# ---------------------------------------------------------------------------
# Color tokens (dark / Slate-adjacent defaults)
# When web theming lands, swap this dict (or inject from theme_manager).
# ---------------------------------------------------------------------------
COLORS = {
    "header_bg": "#2b3e50",
    "header_text": "#ffffff",
    "cell_bg": "#1e1e1e",
    "cell_text": "#ffffff",
    "border": "#333333",
    "header_border": "#555555",
    "table_border": "#444444",
    "bold_row_bg": "#242d38",
    "bold_row_text": "#e0e6ed",
    "filter_bg": "#111111",
    "filter_text": "#ffffff",
}

# Viewport chrome offsets
GRID_VIEWPORT_ONE_TOOLBAR = "calc(100vh - 220px)"   # navbar + 1 toolbar + card header
GRID_VIEWPORT_TWO_TOOLBARS = "calc(100vh - 300px)"  # navbar + 2 toolbars (Source Data)


def grid_table_style(chrome: str = "one") -> dict:
    """style_table for a full-bleed dense grid."""
    h = GRID_VIEWPORT_TWO_TOOLBARS if chrome == "two" else GRID_VIEWPORT_ONE_TOOLBAR
    return {
        "height": h,
        "maxHeight": h,
        "overflowY": "auto",
        "overflowX": "auto",
        "border": f"1px solid {COLORS['table_border']}",
    }


def grid_header_style() -> dict:
    return {
        "backgroundColor": COLORS["header_bg"],
        "color": COLORS["header_text"],
        "fontWeight": "bold",
        "border": f"1px solid {COLORS['header_border']}",
        "textAlign": "center",
    }


def grid_cell_style(
    *,
    font_size: str = "12px",
    text_align: str = "right",
    min_width: str = "90px",
    width: str = "110px",
    padding: str = "5px 10px",
) -> dict:
    return {
        "backgroundColor": COLORS["cell_bg"],
        "color": COLORS["cell_text"],
        "fontSize": font_size,
        "textAlign": text_align,
        "padding": padding,
        "minWidth": min_width,
        "width": width,
        "border": f"1px solid {COLORS['border']}",
    }


def grid_filter_style() -> dict:
    return {
        "backgroundColor": COLORS["filter_bg"],
        "color": COLORS["filter_text"],
    }


def grid_data_style() -> dict:
    """Optional style_data mirror of cell bg/text (some tables set both)."""
    return {
        "backgroundColor": COLORS["cell_bg"],
        "color": COLORS["cell_text"],
    }


def grid_line_item_col_conditional(
    column_id: str = "Line Item",
    *,
    min_width: str = "240px",
    width: str = "300px",
    max_width: str = "360px",
) -> list:
    """style_cell_conditional: widen + left-align the label column."""
    return [
        {
            "if": {"column_id": column_id},
            "minWidth": min_width,
            "width": width,
            "maxWidth": max_width,
            "textAlign": "left",
            "paddingLeft": "12px",
        }
    ]


def grid_bold_row_conditional(bold_indices: Optional[List[int]] = None) -> list:
    """style_data_conditional: bold/highlight subtotal rows by row_index."""
    bold_indices = bold_indices or []
    return [
        {
            "if": {"row_index": idx},
            "fontWeight": "bold",
            "backgroundColor": COLORS["bold_row_bg"],
            "color": COLORS["bold_row_text"],
        }
        for idx in bold_indices
    ]


def grid_style_data_conditional(
    bold_indices: Optional[List[int]] = None,
    *,
    line_item_col: str = "Line Item",
) -> list:
    """Combine bold rows + left-align line-item cells in style_data_conditional."""
    rules = grid_bold_row_conditional(bold_indices)
    rules.append({
        "if": {"column_id": line_item_col},
        "textAlign": "left",
        "paddingLeft": "12px",
    })
    return rules