# --- --- --- Imports --- --- ---
# STD
from pathlib import Path
from typing import Callable
# 3RD
from PySide6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QPushButton, QSplitter, QSizePolicy, QFileDialog
from PySide6.QtGui import  QAction, QKeySequence, QShortcut
from PySide6.QtCore import Qt, Signal, Slot
# Project
from samnotator.widgets.annotator.annotator_widget import AnnotatorWidget, ZoomSelector
from samnotator.widgets.instances.instance_widget import InstanceWidget
from samnotator.widgets.aimodels.modelrunner_widget import ModelRunnerWidget
from .app_controller import AppController

        
class FileOrDirSelector(QWidget):
    files_selected = Signal(list)  # list[Path]

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        btn_files = QPushButton("Open files...", self)
        btn_dir = QPushButton("Open directory...", self)
        layout.addWidget(btn_files)
        layout.addWidget(btn_dir)

        btn_files.clicked.connect(self._open_files)
        btn_dir.clicked.connect(self._open_dir)

    @Slot()
    def _open_files(self) -> None:
        dialog = QFileDialog(self, "Select files")
        dialog.setFileMode(QFileDialog.FileMode.ExistingFiles)
        dialog.setOption(QFileDialog.Option.DontUseNativeDialog, True)

        if dialog.exec() != QFileDialog.DialogCode.Accepted:
            return

        files = [Path(url.toLocalFile()) for url in dialog.selectedUrls()]
        self.files_selected.emit(files)

    @Slot()
    def _open_dir(self) -> None:
        dialog = QFileDialog(self, "Select directory")
        dialog.setFileMode(QFileDialog.FileMode.Directory)
        dialog.setOption(QFileDialog.Option.ShowDirsOnly, True)
        dialog.setOption(QFileDialog.Option.DontUseNativeDialog, True)

        if dialog.exec() != QFileDialog.DialogCode.Accepted:
            return

        # only first dir
        dir_path = Path(dialog.selectedUrls()[0].toLocalFile())
        files = sorted(p for p in dir_path.iterdir() if p.is_file())
        self.files_selected.emit(files)




class AppWidget(QWidget):

    # --- --- --- App init --- --- ---

    def __init__(self, controller:AppController, parent=None):
        super().__init__(parent)
        self._controller = controller
        # Components
        self.annotator: AnnotatorWidget = AnnotatorWidget(controller, parent=self)
        self.instance_widget: InstanceWidget = InstanceWidget(controller.ctl_instances, parent=self)
        self.runner_widget: ModelRunnerWidget = ModelRunnerWidget( app_controller=controller, model_paths={"sam3": Path("models/sam3").resolve()}, parent=self,)
        self.zoom_selector: ZoomSelector = ZoomSelector(parent=self)
        self.file_selector: FileOrDirSelector = FileOrDirSelector(parent=self)
        # Init
        self._init_ui()
    #
    
    def _init_ui(self):
        # - Control bar
        controls_bar = QWidget(self)
        controls_layout = QHBoxLayout(controls_bar)
        controls_layout.addWidget(self.file_selector)
        controls_layout.addStretch(1) 
        controls_layout.addWidget(self.zoom_selector)

        # - Central layout

        # Left panel
        left_panel = QWidget(self)
        vlayout = QVBoxLayout(left_panel)
        vlayout.setContentsMargins(0, 0, 0, 0)
        vlayout.setSpacing(0)
        vlayout.addWidget(controls_bar)
        vlayout.addWidget(self.annotator)

        # Right panel
        right_panel = QWidget(self)
        vlayout = QVBoxLayout(right_panel)
        vlayout.setContentsMargins(0, 0, 0, 0)
        vlayout.setSpacing(0)
        vlayout.addWidget(self.instance_widget)
        vlayout.addWidget(self.runner_widget)

        # Splitter
        left_panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        right_panel.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel) 
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(splitter)


        #  Connections
        self.annotator.zoom_connect(self.zoom_selector)
        self.file_selector.files_selected.connect(self._controller.load_frame_from_paths)
        self.qs_prev_image = QShortcut(QKeySequence(Qt.Key.Key_Left), self)
        self.qs_prev_image.activated.connect(self.prev_frame)
        self.qs_next_image = QShortcut(QKeySequence(Qt.Key.Key_Right), self)
        self.qs_next_image.activated.connect(self.next_frame)
    # End of def _init_ui


    # --- --- --- Connection Helpers --- --- ---

    def connect_position_update(self, slot: Callable[[tuple[int, int]|None], None]) -> None:
        """Connect a slot to receive mouse position updates from the annotator view."""
        self.annotator.view.mouse_position.connect(slot)
    # End of def connect_position_update
    

    @Slot()
    def next_frame(self) -> None:
        self._controller.ctl_frames.next_frame()
    # End of def next_frame
    

    @Slot()
    def prev_frame(self) -> None:
        self._controller.ctl_frames.previous_frame()
    # End of def prev_frame
    