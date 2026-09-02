import os
import sys
import traceback

# Force X11 backend on Linux (ChromeOS/Crostini Wayland compatibility fix)
if sys.platform.startswith("linux") and "QT_QPA_PLATFORM" not in os.environ:
    os.environ["QT_QPA_PLATFORM"] = "xcb"

from PyQt6.QtWidgets import QApplication
from Canneberge.Ui.main_window import MainWindow


def main():
    app = QApplication(sys.argv)

    from Canneberge.Ui.theme import theme_manager
    theme_manager.current.apply_to_app(app)

    from Canneberge.Ui.font_scale import font_scale
    font_scale.apply_to_app(app)

    try:
        window = MainWindow()
        window.show()
        sys.exit(app.exec())
    except Exception:
        traceback.print_exc()


if __name__ == "__main__":
    main()