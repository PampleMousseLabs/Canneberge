import sys
import traceback

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