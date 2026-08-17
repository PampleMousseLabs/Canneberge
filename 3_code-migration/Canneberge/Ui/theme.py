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

    # --- Whole-app foundation ---
    # These two apply everywhere via QPalette (see apply_to_app below),
    # so every widget without its own explicit stylesheet inherits the
    # right background/text color automatically. Everything else in
    # this dataclass is an OVERRIDE on top of these two for specific
    # roles (inputs, headers, links, etc).
    window_bg: str      # page/window background, whole app
    default_text: str   # default body text color, whole app

    # --- Core UI ---
    input_bg: str
    input_text: str
    header_bg: str
    bold_text: str            # color used alongside font-weight: bold labels
    link_color: str
    border_color: str
    emphasis_border: str      # purple-toned border marking a special/subtotal row (NWC total row, etc.) - distinct from plain border_color
    disabled_bg: str
    disabled_text: str
    note_text: str            # italic/muted helper text (e.g. "Pro" nulled notes)
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
        """
        THE canonical section-header treatment for the whole app -
        bold text on a colored background bar, DCF's original look.
        Every page's wide section-divider bars ("Statistics",
        "Cost of Equity...", etc.) route through this ONE method.
        No page gets its own variant - if a page's header looks wrong
        with this, fix header_bg/default_text, don't fork a new style.
        """
        return (
            f"font-weight: bold; font-size: 11px; "
            f"background-color: {self.header_bg}; color: {self.default_text};"
        )

    def emphasis_border_above_style(self, width_px: int = 1) -> str:
        return f"border-top: {width_px}px solid {self.emphasis_border};"

    def emphasis_border_below_style(self, width_px: int = 3) -> str:
        return f"border-bottom: {width_px}px solid {self.emphasis_border};"

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

    def tab_bar_style(self) -> str:
        """
        QPalette does not reliably drive QTabBar's drawn tab shapes
        across styles/platforms - that's the "text recolors but the
        tab background stays beige" gap. QSS targeting QTabBar::tab
        pseudo-states directly is the actual mechanism. Apply via
        self.tabs.setStyleSheet(theme.tab_bar_style()) and reapply on
        theme_changed - QSS does not auto-update from QPalette changes.
        """
        return f"""
            QTabWidget::pane {{
                border: 1px solid {self.border_color};
                background-color: {self.window_bg};
            }}
            QTabBar::tab {{
                background-color: {self.header_bg};
                color: {self.default_text};
                padding: 6px 16px;
                border: 1px solid {self.border_color};
                border-bottom: none;
            }}
            QTabBar::tab:selected {{
                background-color: {self.window_bg};
                font-weight: bold;
            }}
            QTabBar::tab:!selected:hover {{
                background-color: {self.input_bg};
                color: {self.input_text};
            }}
        """

    def apply_to_app(self, app) -> None:
        """
        Sets window background + default text color for the WHOLE app,
        not just DCF. This is the mechanism that closes the "background
        is unaffected" gap: any widget that does NOT have its own
        explicit setStyleSheet() call inherits these two colors from
        Qt's QPalette automatically. Widgets that DO have an explicit
        stylesheet (inputs, headers, etc.) are unaffected by this and
        keep using their own theme.* fields as before.

        Call this once at app startup, and again every time
        theme_manager.theme_changed fires.
        """
        from PyQt6.QtGui import QPalette, QColor
        from PyQt6.QtWidgets import QStyleFactory

        # Fusion renders identically across Windows/macOS/Linux and is
        # the style QPalette color roles are most reliably respected
        # by — native styles sometimes ignore palette overrides for
        # certain roles depending on OS theme.
        app.setStyle(QStyleFactory.create("Fusion"))

        palette = QPalette()
        window = QColor(self.window_bg)
        text = QColor(self.default_text)

        palette.setColor(QPalette.ColorRole.Window, window)
        palette.setColor(QPalette.ColorRole.WindowText, text)
        palette.setColor(QPalette.ColorRole.Base, window)
        palette.setColor(QPalette.ColorRole.AlternateBase, window)
        palette.setColor(QPalette.ColorRole.Text, text)
        palette.setColor(QPalette.ColorRole.ButtonText, text)
        palette.setColor(QPalette.ColorRole.ToolTipBase, window)
        palette.setColor(QPalette.ColorRole.ToolTipText, text)

        app.setPalette(palette)


# =============================================================
# THEME 1 — Slate & Gold (current palette, unchanged baseline)
# =============================================================
SLATE_AND_GOLD = Theme(
    name="Slate & Gold",
    # NOTE: window_bg/default_text did not exist before this change —
    # there was no app-wide background set anywhere in the codebase.
    # #ffffff is a neutral guess matching typical unstyled Qt/Windows
    # rendering. This is the one thing in Theme 1 that is NOT a
    # preserved "current" value — check it against what the app
    # actually looked like before and correct if it doesn't match.
    window_bg="#ffffff",
    default_text="#1a1a1a",
    input_bg="#dce9f7",
    input_text="#1a4a8a",
    header_bg="#f0f0f0",
    bold_text="#000000",
    link_color="#1a4a8a",
    border_color="#000000",
    emphasis_border="#4b1f7a",
    disabled_bg="#f0f0f0",
    disabled_text="#9a9a9a",
    note_text="#555555",
    dark_header_bg="#2f2fa0",
    dark_header_fg="#ffffff",
    grey_disabled_bg="#f0f0f0",
    grey_disabled_text="#444444",
    chart_fill="#8b7fd1",
    chart_edge="#3509b9",
    chart_range="#8b7fd1",
    chart_conclude="#e6b800",
    chart_share_price="#1a1a8c",
    chart_grid="#cccccc",
    chart_axis_label="#888888",
)


# =============================================================
# THEME 2 — One Dark Pro (dark mode)
# =============================================================
ONE_DARK_PRO = Theme(
    name="One Dark Pro",
    window_bg="#282c34",
    default_text="#abb2bf",
    input_bg="#3b4048",
    input_text="#61afef",
    header_bg="#3e4451",
    bold_text="#abb2bf",
    link_color="#61afef",
    border_color="#181a1f",
    emphasis_border="#c678dd",
    disabled_bg="#33383f",
    disabled_text="#7f8794",
    note_text="#33ff00",
    dark_header_bg="#3a3d91",
    dark_header_fg="#ffffff",
    grey_disabled_bg="#33383f",
    grey_disabled_text="#7f8794",
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
    window_bg="#ffffff",
    default_text="#24292f",
    input_bg="#ddf4ff",
    input_text="#0969da",
    header_bg="#f6f8fa",
    bold_text="#24292f",
    link_color="#0969da",
    border_color="#d0d7de",
    emphasis_border="#8250df",
    disabled_bg="#f6f8fa",
    disabled_text="#8c959f",
    note_text="#57606a",
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

        # Apply window_bg/default_text app-wide immediately. Doing this
        # here (not leaving it to each page) means background/text
        # theming works for every page automatically, including the 12
        # not yet migrated to the per-widget theme system.
        from PyQt6.QtWidgets import QApplication
        app = QApplication.instance()
        if app is not None:
            self.current.apply_to_app(app)

        self.theme_changed.emit(self.current)

    def theme_names(self) -> list[str]:
        return list(THEMES.keys())


# Module-level singleton. Import this, don't instantiate ThemeManager yourself.
theme_manager = ThemeManager()