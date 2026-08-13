"""
Canneberge/Ui/theme.py

Central color/style source of truth for the whole application.

Every page should import `theme_manager` (the singleton at the bottom of this
file) and read colors from `theme_manager.current` instead of defining local
INPUT_STYLE / HEADER_STYLE / hex-literal constants.

Do not hardcode hex values in any Ui/*.py file going forward. If a role is
missing from the Theme dataclass below, ADD THE FIELD HERE first, then use it
everywhere it's needed. Do not patch around a missing field with a local
literal - that's exactly the drift pattern this file exists to kill.
"""

from dataclasses import dataclass
from PyQt6.QtCore import QObject, pyqtSignal, QSettings


# =============================================================
# THEME SCHEMA
# =============================================================
@dataclass(frozen=True)
class Theme:
    name: str

    # --- Core UI ---
    input_bg: str
    input_text: str
    header_bg: str
    header_fg: str
    bold_text: str            # color used alongside font-weight: bold labels
    link_color: str
    border_color: str
    disabled_bg: str
    disabled_text: str
    note_text: str            # italic/muted helper text (e.g. "Pro" nulled notes)
    section_header_accent: str  # the purple #6912b0 role on WACC/GPC/etc.
    dark_header_bg: str       # dashboard DARK_HEADER_BG role
    dark_header_fg: str       # dashboard DARK_HEADER_FG role
    grey_disabled_bg: str     # the separate #f0f0f0 / #9a9a9a "greyed out" role
    grey_disabled_text: str

    # --- Charts (football field + GPC candlestick) ---
    chart_fill: str           # candlestick fill / range bar fill
    chart_edge: str           # candlestick edge
    chart_range: str          # football-field range bar
    chart_conclude: str       # football-field concluded-value marker
    chart_share_price: str    # football-field share price line
    chart_grid: str           # gridlines / axhline, both charts
    chart_axis_label: str     # muted axis/annotation text (#888888 role)

    # --- Style-string helpers -----------------------------------------
    # Centralizing these means pages call theme.input_style() instead of
    # rebuilding "background-color: ...; color: ...;" strings by hand.

    def input_style(self) -> str:
        return f"background-color: {self.input_bg}; color: {self.input_text};"

    def header_style(self) -> str:
        return f"font-weight: bold; color: {self.section_header_accent};"

    def bold_style(self) -> str:
        return f"font-weight: bold; color: {self.bold_text};"

    def link_style(self) -> str:
        return (
            f"border: none; color: {self.link_color}; "
            "text-decoration: underline; background: transparent;"
        )

    def disabled_style(self) -> str:
        return f"background-color: {self.disabled_bg}; color: {self.disabled_text};"

    def grey_disabled_style(self) -> str:
        return f"background-color: {self.grey_disabled_bg}; color: {self.grey_disabled_text};"

    def note_style(self) -> str:
        return f"color: {self.note_text}; font-style: italic;"

    def dark_header_style(self) -> str:
        return f"background-color: {self.dark_header_bg}; color: {self.dark_header_fg};"


# =============================================================
# THEME 1 — Slate & Gold (current palette, unchanged baseline)
# =============================================================
SLATE_AND_GOLD = Theme(
    name="Slate & Gold",
    input_bg="#dce9f7",
    input_text="#1a4a8a",
    header_bg="#f0f0f0",
    header_fg="#1a1a1a",
    bold_text="#000000",
    link_color="#1a4a8a",
    border_color="#000000",
    disabled_bg="#f0f0f0",
    disabled_text="#9a9a9a",
    note_text="#555555",
    section_header_accent="#6912b0",
    dark_header_bg="#2f2fa0",
    dark_header_fg="#ffffff",
    grey_disabled_bg="#f0f0f0",
    grey_disabled_text="#444444",
    chart_fill="#8b7fd1",
    chart_edge="#3509b9",
    chart_range="#8b7fd1",
    chart_conclude="#e6b800",
    chart_share_price="#1a1a8c",
    chart_grid="#dddddd",
    chart_axis_label="#888888",
)


# =============================================================
# THEME 2 — One Dark Pro (dark mode)
# =============================================================
ONE_DARK_PRO = Theme(
    name="One Dark Pro",
    input_bg="#3b4048",
    input_text="#61afef",
    header_bg="#282c34",
    header_fg="#abb2bf",
    bold_text="#abb2bf",
    link_color="#61afef",
    border_color="#181a1f",
    disabled_bg="#2c313a",
    disabled_text="#5c6370",
    note_text="#98c379",
    section_header_accent="#c678dd",
    dark_header_bg="#21252b",
    dark_header_fg="#e5c07b",
    grey_disabled_bg="#2c313a",
    grey_disabled_text="#5c6370",
    chart_fill="#c678dd",
    chart_edge="#e5c07b",
    chart_range="#61afef",
    chart_conclude="#e5c07b",
    chart_share_price="#e06c75",
    chart_grid="#3e4451",
    chart_axis_label="#5c6370",
)


# =============================================================
# THEME 3 — GitHub Light (alternate light)
# =============================================================
GITHUB_LIGHT = Theme(
    name="GitHub Light",
    input_bg="#ddf4ff",
    input_text="#0969da",
    header_bg="#f6f8fa",
    header_fg="#24292f",
    bold_text="#24292f",
    link_color="#0969da",
    border_color="#d0d7de",
    disabled_bg="#f6f8fa",
    disabled_text="#8c959f",
    note_text="#57606a",
    section_header_accent="#8250df",
    dark_header_bg="#24292f",
    dark_header_fg="#f6f8fa",
    grey_disabled_bg="#f6f8fa",
    grey_disabled_text="#8c959f",
    chart_fill="#8250df",
    chart_edge="#6639ba",
    chart_range="#54aeff",
    chart_conclude="#bf8700",
    chart_share_price="#cf222e",
    chart_grid="#d0d7de",
    chart_axis_label="#8c959f",
)


THEMES: dict[str, Theme] = {
    SLATE_AND_GOLD.name: SLATE_AND_GOLD,
    ONE_DARK_PRO.name: ONE_DARK_PRO,
    GITHUB_LIGHT.name: GITHUB_LIGHT,
}

DEFAULT_THEME_NAME = SLATE_AND_GOLD.name


# =============================================================
# THEME MANAGER — singleton, QSettings-backed, emits theme_changed
# =============================================================
class ThemeManager(QObject):
    """
    Single source of truth for "which theme is active right now."

    Usage in a page:
        from Canneberge.Ui.theme import theme_manager

        theme_manager.theme_changed.connect(self._apply_theme)
        self._apply_theme(theme_manager.current)

        def _apply_theme(self, theme):
            self.some_input.setStyleSheet(theme.input_style())
    """

    theme_changed = pyqtSignal(object)  # emits the new Theme instance

    _ORG = "PampleMousseLabs"
    _APP = "Canneberge"
    _SETTINGS_KEY = "ui/theme_name"

    def __init__(self):
        super().__init__()
        self._settings = QSettings(self._ORG, self._APP)
        saved_name = self._settings.value(self._SETTINGS_KEY, DEFAULT_THEME_NAME)
        self.current: Theme = THEMES.get(saved_name, SLATE_AND_GOLD)

    def set_theme(self, name: str):
        if name not in THEMES:
            raise ValueError(f"Unknown theme '{name}'. Valid: {list(THEMES.keys())}")
        self.current = THEMES[name]
        self._settings.setValue(self._SETTINGS_KEY, name)
        self.theme_changed.emit(self.current)

    def theme_names(self) -> list[str]:
        return list(THEMES.keys())


# Module-level singleton. Import this, don't instantiate ThemeManager yourself.
theme_manager = ThemeManager()