"""
Canneberge/Ui/shared_input_widgets.py

Consolidates MultipleInputEdit, PctInputEdit, and CurrencyInputEdit -
previously two byte-identical, independently-maintained copies of the
first two classes living in gpc_page.py and gt_page.py, flagged as a
duplication risk when GPC was first migrated and finally resolved
here. Same failure class as the copy-pasted color constants from
earlier in this project (INPUT_STYLE existing separately in 5+ files)
- just at the class level instead of the string level.

Width was NOT identical between the two pages (gpc_page.py's
W_METRIC = 110, gt_page.py's W_METRIC = 120), so it's a constructor
parameter here rather than a hardcoded page-specific constant baked
into the shared class body - each page passes its own local width.

_parse_float/_parse_pct also existed as two separate copies with a
real behavioral difference, not just a cosmetic one: gpc_page.py's
versions explicitly rejected nan/inf ("if math.isnan(val) or
math.isinf(val): return None"), gt_page.py's did not guard against
that at all. GPC's stricter version is canonical here - same
poison-value class this project has hit repeatedly (e.g. gpc_multiples.py's
_to_float has the identical guard, with the identical rationale).
"""

import math
from typing import Optional

from PyQt6.QtWidgets import QLineEdit
from PyQt6.QtCore import Qt

from Canneberge.Ui.theme import theme_manager


def get_input_style() -> str:
    return theme_manager.current.input_style()


def _parse_float(text: str) -> Optional[float]:
    text = str(text).strip().replace(",", "").replace("x", "")
    if not text:
        return None
    try:
        val = float(text)
    except ValueError:
        return None
    if math.isnan(val) or math.isinf(val):
        return None
    return val


def _parse_pct(text: str) -> Optional[float]:
    text = str(text).strip().replace(",", "")
    if not text:
        return None
    try:
        if "%" in text:
            val = float(text.replace("%", "")) / 100
        else:
            val = float(text)
            val = val / 100 if val > 1 else val
    except ValueError:
        return None
    if math.isnan(val) or math.isinf(val):
        return None
    return val


class MultipleInputEdit(QLineEdit):
    """Input field that formats its value as ##.##x on focus-out."""
    def __init__(self, placeholder="", width: int = 100, parent=None):
        super().__init__(parent)
        self.setPlaceholderText(placeholder)
        self.setStyleSheet(get_input_style())
        self.setFixedWidth(width)
        self.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.editingFinished.connect(self._format_value)
        # Self-subscribing to theme changes (rather than requiring the
        # page to track every grid instance in a list) means this
        # restyles correctly no matter how many of these exist or
        # where they're placed - removes an entire class of "did I
        # remember to add this widget to the restyle loop" bugs.
        # isEnabled() check preserves whatever disabled/greyed-out
        # state a page put this widget into (e.g. dashboard_page.py's
        # rows beyond "How Many Multiples") instead of unconditionally
        # forcing the enabled look back on every theme switch - this
        # exact gap existed here unnoticed until dashboard_page.py's
        # own _value_line()/_small_spin()/_combo() factories needed
        # the identical fix and this class didn't have it yet.
        theme_manager.theme_changed.connect(
            lambda _t: self.setStyleSheet(
                get_input_style() if self.isEnabled() else theme_manager.current.grey_disabled_style()
            )
        )

    def _format_value(self):
        val = _parse_float(self.text())
        if val is not None:
            self.setText(f"{val:.2f}x")
        # if empty/invalid, leave as-is so placeholder shows


class PctInputEdit(QLineEdit):
    """Input field that formats its value as ##.#% on focus-out."""
    def __init__(self, placeholder="", width: int = 100, parent=None):
        super().__init__(parent)
        self.setPlaceholderText(placeholder)
        self.setStyleSheet(get_input_style())
        self.setFixedWidth(width)
        self.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.editingFinished.connect(self._format_value)
        theme_manager.theme_changed.connect(
            lambda _t: self.setStyleSheet(
                get_input_style() if self.isEnabled() else theme_manager.current.grey_disabled_style()
            )
        )

    def _format_value(self):
        val = _parse_pct(self.text())
        if val is not None:
            self.setText(f"{val*100:.1f}%")


class CurrencyInputEdit(QLineEdit):
    """
    Used when a GPC column is set to Custom Multiple - the Subject
    Company Financial Data cell for that column needs to accept a
    typed number (no metric to pull), formatted like currency rather
    than a multiple. GT never needed this (its transaction data is
    entered on the Home page grid, not here).
    """
    def __init__(self, placeholder="", width: int = 100, parent=None):
        super().__init__(parent)
        self.setPlaceholderText(placeholder)
        self.setStyleSheet(get_input_style())
        self.setFixedWidth(width)
        self.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.editingFinished.connect(self._format_value)
        theme_manager.theme_changed.connect(
            lambda _t: self.setStyleSheet(
                get_input_style() if self.isEnabled() else theme_manager.current.grey_disabled_style()
            )
        )

    def _format_value(self):
        val = _parse_float(self.text())
        if val is not None:
            self.setText(f"{val:,.0f}")