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
from samnotator.widgets.aimodels.modelrunner_widget import ModelRunnerWidget, ModelKind, ModelInfo
from .app_controller import AppController


# --- --- --- Model Paths --- --- ---

MODELS:list[ModelInfo] = [
    ModelInfo(kind=ModelKind.IMAGE, name="SAM3 Image", wrapper_name="sam3_pvs_image", model_path=Path("models/sam3").resolve()),
]
        
class AppWidget(QWidget):

    # --- --- --- App init --- --- ---

    def __init__(self, controller:AppController, parent=None):
        super().__init__(parent)
        self.controller = controller
        # Components
        self.annotator: AnnotatorWidget = AnnotatorWidget(controller, parent=self)
        self.instance_widget: InstanceWidget = InstanceWidget(controller.ctl_instances, parent=self)
        self.runner_widget: ModelRunnerWidget = ModelRunnerWidget(app_controller=controller, models=MODELS.copy(), parent=self,)
        self.zoom_selector: ZoomSelector = ZoomSelector(parent=self)
        # Init
        self._init_ui()
    #
    
    def _init_ui(self):
        # - Control bar
        controls_bar = QWidget(self)
        controls_layout = QHBoxLayout(controls_bar)
        # other controls here
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
        #
        self.qs_prev_image = QShortcut(QKeySequence(Qt.Key.Key_Left), self)
        self.qs_prev_image.activated.connect(self.prev_frame)
        #
        self.qs_next_image = QShortcut(QKeySequence(Qt.Key.Key_Right), self)
        self.qs_next_image.activated.connect(self.next_frame)
        #
        self.qs_deselect_all = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        self.qs_deselect_all.activated.connect(self.deselect_all)
    # End of def _init_ui


    # --- --- --- Connection Helpers --- --- ---

    def connect_position_update(self, slot: Callable[[tuple[int, int]|None], None]) -> None:
        """Connect a slot to receive mouse position updates from the annotator view."""
        self.annotator.view.mouse_position.connect(slot)
    # End of def connect_position_update
    

    @Slot()
    def next_frame(self) -> None:
        self.controller.ctl_frames.next_frame()
    # End of def next_frame
    

    @Slot()
    def prev_frame(self) -> None:
        self.controller.ctl_frames.previous_frame()
    # End of def prev_frame

    
    @Slot()
    def deselect_all(self) -> None:
        self.controller.ctl_instances.set_current_instance(None)
    # End of def deselect_all
# End of class AppWidget