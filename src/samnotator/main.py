# --- --- --- Import --- --- ---
# STD
import argparse
from pathlib import Path
import sys
from typing import Literal
# 3RD
from PySide6.QtCore import QSettings, QDir
from PySide6.QtGui import QGuiApplication, QAction, QKeySequence
from PySide6.QtWidgets import QApplication, QMainWindow, QStatusBar, QMenuBar, QFileDialog
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
        self.menubar = QMenuBar(self)
        self.statusbar = QStatusBar(self)
        self.status_bar_controller = StatusBarController(self.statusbar, self)
        self.app_widget = app_widget
        self.app_controller = app_widget.controller

        self.current_save_dir: Path | None = None

        # UI setup
        self._init_uit()

        # Sizing
        self._geom_restore()
    #


    def _init_uit(self):
        self.setWindowTitle(__APPNAME__)
        self.setCentralWidget(self.app_widget)
        self.setMenuBar(self.menubar)
        self.setStatusBar(self.statusbar)
        self._create_menus()
        #
        self.app_widget.connect_position_update(self.status_bar_controller.update_position)
    # End of def _init_uit

    
    # --- --- --- Component Setup --- --- ---


    # --- --- --- Menu bar --- --- ---
    
    def _create_menus(self) -> None:
        menu_bar = self.menuBar()
        file_menu = menu_bar.addMenu("&File")

        act_open_file = QAction("Open File(s)...", self)
        act_open_dir = QAction("Open Directory...", self)
        act_save = QAction("Save", self)
        act_save_as = QAction("Save As...", self)

        # Standard shortcuts
        act_open_file.setShortcut(QKeySequence.StandardKey.Open)      # Ctrl+O / Cmd+O
        act_save.setShortcut(QKeySequence.StandardKey.Save)           # Ctrl+S / Cmd+S
        act_save_as.setShortcut(QKeySequence.StandardKey.SaveAs)      # Ctrl+Shift+S / Cmd+Shift+S

        # No standard for "open directory": pick one
        act_open_dir.setShortcut(QKeySequence("Ctrl+Shift+O"))

        act_open_file.triggered.connect(self.open_files)
        act_open_dir.triggered.connect(self.open_directory)
        act_save.triggered.connect(self.save)
        act_save_as.triggered.connect(self.save_as)

        file_menu.addAction(act_open_file)
        file_menu.addAction(act_open_dir)
        file_menu.addSeparator()
        file_menu.addAction(act_save)
        file_menu.addAction(act_save_as)


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

    
    # --- --- --- Actions --- --- ---


    def open_files(self) -> None:
        dialog = QFileDialog(self, "Open File(s)")
        dialog.setFileMode(QFileDialog.FileMode.ExistingFiles)
        if dialog.exec() == QFileDialog.DialogCode.Accepted:
            paths = [Path(url.toLocalFile()) for url in dialog.selectedUrls()]
            if paths:
                self.app_controller.ctl_frames.open_images(paths)
    # End of def open_files


    #def open_directory(self) -> None:
    #    dir_str = QFileDialog.getExistingDirectory(self, "Open Directory")
    #    if dir_str:
    #        self.app_controller.ctl_frames.open_folder(Path(dir_str))
    ## End of def open_directory

    
    
    def open_directory(self) -> None:
        start_dir = str(self.current_save_dir or Path.cwd())

        dialog = QFileDialog(self, "Open folder", start_dir)

        # 1) select folders, not files
        dialog.setFileMode(QFileDialog.FileMode.Directory)

        # 2) allow files to be shown in the list (right pane)
        dialog.setOption(QFileDialog.Option.ShowDirsOnly, False)

        # 3) optional but often helps to get the full Qt dialog with a files view
        dialog.setOption(QFileDialog.Option.DontUseNativeDialog, True)

        # 4) show both files and directories, hide . and ..
        dialog.setFilter(QDir.Filter.AllEntries | QDir.Filter.NoDotAndDotDot)

        if dialog.exec() != QFileDialog.DialogCode.Accepted:
            return

        # with FileMode.Directory, the selection will be a folder
        folder = Path(dialog.selectedFiles()[0])
        self.current_save_dir = folder
        self.app_controller.ctl_frames.open_folder(folder)
    #



    def save(self) -> None:
        if self.current_save_dir is None:
            self.save_as()
        else:
            self._write_to_dir(self.current_save_dir)
        #
    # End of def save


    def save_as(self) -> None:
        # starting location: current folder if we have one, else CWD
        start_dir = str(self.current_save_dir or Path.cwd())
        base_dir_str = QFileDialog.getExistingDirectory(self, "Select folder to save in", start_dir,)
        if base_dir_str:
            base_dir = Path(base_dir_str)
            self.current_save_dir = base_dir
            self._write_to_dir(base_dir)
    # End of def save_as

    
    def _pick_dir(self, legend:str, start_dir:str) -> Path|None:
        dialog = QFileDialog(self, legend, start_dir)

        # 1) select folders, not files
        dialog.setFileMode(QFileDialog.FileMode.Directory)

        # 2) allow files to be shown in the list (right pane)
        dialog.setOption(QFileDialog.Option.ShowDirsOnly, False)

        # 3) optional but often helps to get the full Qt dialog with a files view
        dialog.setOption(QFileDialog.Option.DontUseNativeDialog, True)

        # 4) show both files and directories, hide . and ..
        dialog.setFilter(QDir.Filter.AllEntries | QDir.Filter.NoDotAndDotDot)

        if dialog.exec() != QFileDialog.DialogCode.Accepted:
            return

        # with FileMode.Directory, the selection will be a folder
        folder = Path(dialog.selectedFiles()[0])
        self.current_save_dir = folder

    
    def _write_to_dir(self, dir_path:Path) -> None:
        self.app_controller.save_to_folder(dir_path)
    # End of def _write_to_dir


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