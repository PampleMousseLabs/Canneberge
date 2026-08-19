"""
Canneberge/Ui/font_scale.py

Central font-size source of truth for the whole application, separate
from theme.py's color system on purpose: font size is a readability
preference, not a color-theme choice. A person should be able to run
One Dark Pro at a larger text size, or Slate & Gold at a smaller one -
coupling the two would mean re-picking a color theme just to get
bigger text, which is not what "make the font bigger" means.

Every font-size role in the app is defined here as a BASE_PX constant
representing 100% scale. Pages call font_scale.px(ROLE_BASE_PX) instead
of writing a literal pixel number - that's the whole rule. A literal
"font-size: 11px" anywhere in a page file is exactly the kind of
per-page drift this module exists to prevent (see dcf_page.py's
get_note_style() vs nwc_page.py's period-header treatment before this
was centralized - same semantic role, different sizes, because each
page had its own hardcoded number).

Usage in a page file:
    from Canneberge.Ui.font_scale import font_scale, BODY_BASE_PX

    def get_something_style() -> str:
        return f"font-size: {font_scale.px(BODY_BASE_PX)}px; ..."
"""

from PyQt6.QtCore import QObject, pyqtSignal, QSettings
from PyQt6.QtGui import QFont

# =============================================================
# SEMANTIC FONT-SIZE ROLES (base px @ 100% scale)
#
# Every distinct font-size need in the app should map to ONE of
# these, not a new locally-invented number. If an existing role
# doesn't fit, add a new named role here - don't hardcode a px
# value in a page file.
# =============================================================
BODY_BASE_PX = 12            # default/unstyled widget text app-wide
SECTION_HEADER_BASE_PX = 10  # DCF/GPC/GT/WACC/NWC/NWC's canonical section-divider bars (theme.header_style())
PANEL_HEADER_BASE_PX = 11    # Dashboard's larger panel-title bars (Income Approach, Market Approach, etc.)
NOTE_BASE_PX = 10            # muted/secondary text - period-column headers, footnotes

MIN_SCALE = 0.75
MAX_SCALE = 1.5
SCALE_STEP = 0.1


class FontScaleManager(QObject):
    """
    Singleton. Holds the current scale factor, persists it via
    QSettings, and applies it app-wide via QApplication.setFont() so
    plain/unstyled widget text (which has no explicit CSS font-size
    anywhere) is included in "bigger/smaller text" - not just the
    handful of roles above that happen to have explicit styling.

    Deliberately reuses theme_manager's existing theme_changed signal
    network rather than adding a second, parallel signal that every
    page would need its own subscription wiring for. Every page
    already listens for theme_changed and reapplies its get_*_style()
    calls on that signal (for color-theme switching) - since those
    same get_*_style() calls will now read the live font scale too,
    re-emitting theme_changed on a font-scale change gets every
    already-migrated page's fonts to refresh for free, with zero new
    per-page subscription code.
    """

    _ORG = "PampleMousseLabs"
    _APP = "Canneberge"
    _SETTINGS_KEY = "ui/font_scale"

    def __init__(self):
        super().__init__()
        self._settings = QSettings(self._ORG, self._APP)
        try:
            self.scale: float = float(self._settings.value(self._SETTINGS_KEY, 1.0))
        except (TypeError, ValueError):
            self.scale = 1.0
        self.scale = max(MIN_SCALE, min(MAX_SCALE, self.scale))
        self._app = None  # set by apply_to_app()

    def px(self, base_px: int) -> int:
        return round(base_px * self.scale)

    def apply_to_app(self, app):
        """Call once at startup (see main.py), and again internally
        on every scale change. Sets the QApplication-wide base font
        so plain widget text scales too, not just the explicitly-
        styled roles above."""
        self._app = app
        font = QFont()
        font.setPointSize(max(1, round(self.px(BODY_BASE_PX) * 0.75)))
        # Qt point size vs our px roles: point size is used here
        # because QFont.setPixelSize() disables Qt's own DPI scaling,
        # which would make the app render wrong on high-DPI displays.
        # The 0.75 factor is the standard 96-DPI px->pt conversion
        # (pt = px * 72/96) so BODY_BASE_PX still means what it says
        # at 100% scale on a typical display.
        app.setFont(font)

    def set_scale(self, scale: float):
        self.scale = max(MIN_SCALE, min(MAX_SCALE, round(scale, 2)))
        self._settings.setValue(self._SETTINGS_KEY, self.scale)
        if self._app is not None:
            self.apply_to_app(self._app)
        # Re-emit theme_changed so every already-subscribed widget/
        # factory across every migrated page reapplies its
        # get_*_style() calls, which now reflect the new scale. Color
        # is unchanged; this is intentionally piggybacking on the
        # same network rather than building a parallel one.
        from Canneberge.Ui.theme import theme_manager
        theme_manager.theme_changed.emit(theme_manager.current)

    def increase(self):
        self.set_scale(self.scale + SCALE_STEP)

    def decrease(self):
        self.set_scale(self.scale - SCALE_STEP)

    def reset(self):
        self.set_scale(1.0)


font_scale = FontScaleManager()