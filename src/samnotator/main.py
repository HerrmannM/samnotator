# --- --- --- Import --- --- ---
# STD
import argparse
from pathlib import Path
import sys
from typing import Literal
# 3RD
from PySide6.QtCore import QSettings, QByteArray
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication, QMainWindow, QStatusBar
# Project
from .app import AppController, AppWidget, StatusBarController


# --- --- --- Constants --- --- ---

__ORGNAME__ = "SamNotator"
__APPNAME__ = "SamNotator"


# --- --- --- Main Window --- --- ---

class MainWindow(QMainWindow):


    def __init__(self, app_widget: AppWidget):
        super().__init__()
        # Admin
        self.settings = QSettings(__ORGNAME__, __APPNAME__)

        # Components
        self.status_bar = QStatusBar(self)
        self.status_bar_controller = StatusBarController(self.status_bar, self)
        self.app_widget = app_widget

        # UI setup
        self._init_uit()

        # Sizing
        self._geom_restore()
    #

    
    # --- --- --- Component Setup --- --- ---

    def _init_uit(self):
        self.setWindowTitle(__APPNAME__)
        self.setCentralWidget(self.app_widget)
        self.setStatusBar(self.status_bar)
        #
        self.app_widget.connect_position_update(self.status_bar_controller.update_position)



    # --- --- --- Geometry --- --- ---

    def _geom_win_state(self) -> Literal["max", "normal"]:
        if self.isMaximized():
            return "max"
        else:
            return "normal"
    #

    def _geom_init(self):
        """Compute initial "normal" size geometry"""
        screen = self.screen() or QGuiApplication.primaryScreen()
        available = screen.availableGeometry()
        w = int(available.width() * 0.8)
        h = int(available.height() * 0.8)
        self.resize(w, h)
        # Try to move in center
        frame = self.frameGeometry()
        frame.moveCenter(available.center())
        self.move(frame.topLeft())
    #

    def _geom_save(self):
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("windowState", self._geom_win_state())
    #

    def _geom_restore(self):
        self._geom_init()  # Default geometry
        pass
        #geom:QByteArray|None = self.settings.value("geometry")
        #win_state:str|None = self.settings.value("windowState") 

        #if geom is not None:
        #    self.restoreGeometry(geom)
        #    if win_state == "max": self.showMaximized()
        #    else: self.showNormal()
        #else:
        #    self._geom_init()
    #


    # --- --- --- Events --- --- ---

    def closeEvent(self, event):
        self._geom_save()
        super().closeEvent(event)
    #
# End of class MainWindow






if __name__ == "__main__":

    # Parse arguments
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", type=Path, default=None, help="Input file or folder path")

    # known: our current args; unknown: passed to Qt
    args, qt_args = parser.parse_known_args()


    app = QApplication(qt_args)


    input_path: Path | None = args.path
    if input_path is not None:
        if not input_path.exists():
            print(f"Error: path '{input_path}' does not exist.", file=sys.stderr)
            sys.exit(1)

    controller = AppController(app)
    controller.load_frame_from_paths([input_path] if input_path is not None else None)

    app_widget = AppWidget(controller)

    main_window = MainWindow(app_widget)
    main_window.show()

    sys.exit(app.exec())

#