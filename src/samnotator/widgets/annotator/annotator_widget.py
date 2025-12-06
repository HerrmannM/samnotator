"""Main annotator widget"""
# --- --- --- Imports --- --- ---
# STD
from dataclasses import replace
# 3RD
from PySide6.QtCore import Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QWidget, QComboBox, QVBoxLayout, QHBoxLayout, QPushButton, QSizePolicy
# Project
from samnotator.app.app_controller import AppController
from samnotator.controllers.frame_controller import FrameID
from samnotator.utils_qt.contextblock import block_signals
from .annotator_view import AnnotatorView
from .annotator_scene import AnnotatorScene
from .zoom import ZoomInfo




class ZoomSelector(QWidget):
    
    zoom_change_requested: Signal = Signal(ZoomInfo)

    def __init__(self, parent:QWidget|None = None):
        super().__init__(parent)
        # State
        self.zoom_info:ZoomInfo = ZoomInfo.default()
        # Components
        self.cbb = QComboBox()
        self.always_fit_btn = QPushButton()
        # Init
        self._init_ui()
    #
    

    def _init_ui(self):
        # Init components
        # - Zoom levels combo box:
        self.cbb.setEditable(False)
        self.cbb.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.cbb.activated.connect(self._on_cbb_activated)
        self.cbb.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.cbb.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        # - Fit toggle button
        self.always_fit_btn.setText("Fit")
        self.always_fit_btn.setCheckable(True) 
        self.always_fit_btn.setChecked(False)
        self.always_fit_btn.toggled.connect(self._on_fit_toggle)

        # Make layout
        layout = QHBoxLayout()
        layout.addWidget(self.cbb)
        layout.addWidget(self.always_fit_btn)
        self.setLayout(layout)
    #


    def set(self, new_zoom_info: ZoomInfo):
        """Set current zoom information, rebuild menu if list of level changed"""
        cbb = self.cbb
        with block_signals(cbb):
            # Rebuild combo list if zoom levels changed
            if self.zoom_info.zoom_levels != new_zoom_info.zoom_levels:
                cbb.clear()
                for i, level in enumerate(new_zoom_info.zoom_levels):
                    txt = f"{level}%"
                    if i == new_zoom_info.fit_index: txt += " (Fit)"
                    cbb.addItem(txt, i)
                #

            # Set wanted index (current or fit)
            cbb.setCurrentIndex(new_zoom_info.wanted_index)
        
        with block_signals(self.always_fit_btn):
            self.always_fit_btn.setChecked(new_zoom_info.want_to_fit)

        self.zoom_info = new_zoom_info
    # End def zoom_set_info


    def _on_cbb_activated(self, index:int):
        self.cbb.hidePopup()    # force-close popup
        zi = replace(self.zoom_info, current_index=index, want_to_fit=False)
        with block_signals(self.always_fit_btn):
            self.always_fit_btn.setChecked(False)
        self.zoom_change_requested.emit(zi)
    # End def _on_cbb_activated


    def _on_fit_toggle(self, checked:bool):
        zi = replace(self.zoom_info, want_to_fit=checked)
        self.zoom_change_requested.emit(zi)
    # End def _on_fit_toggle
# End of class ZoomSelector


class AnnotatorWidget(QWidget):

    def __init__(self, app_controller:AppController, parent:QWidget|None = None):
        super().__init__(parent)

        # Controllers
        self.ctl_app = app_controller

        # Widget components
        self.view: AnnotatorView = AnnotatorView(parent=self)
        self.scene: AnnotatorScene|None = None

        # Build UI
        self._init_ui()
    #
    
    def _init_ui(self):
        # Components
        # - Frame controller
        self.set_frame(self.ctl_app.ctl_frames.get_current_frame_id())
        self.ctl_app.ctl_frames.current_frame_changed.connect(self.set_frame)
        # - View:
        self.view.setScene(self.scene)

        # Layouts
        central_layout = QVBoxLayout()
        central_layout.addWidget(self.view)
        self.setLayout(central_layout)
    # End of def _init_ui
    

    # --- --- --- Public methods/slots --- --- ---

    def clear_scene(self):
        self.view.setScene(None)
        if self.scene is not None:
            self.scene.deleteLater()
            self.scene = None
    # End of def clear_scene
            

    def set_frame(self, frame_id:FrameID|None):
        self.clear_scene()
        if frame_id is not None:
            pixmap = QPixmap(self.ctl_app.ctl_frames.get_frame_data(frame_id))
            self.scene = AnnotatorScene(annotations_controller=self.ctl_app.ctl_annotations, instance_controller=self.ctl_app.ctl_instances, frame_id=frame_id, qpixmap=pixmap, parent=self)
            self.view.setScene(self.scene)
    # End of def set_frame

    
    def zoom_connect(self, zoom_selector:ZoomSelector):
        """Connect a slot to receive zoom change requests from the zoom selector."""
        self.view.connect_zoom_changed(zoom_selector.set)
        zoom_selector.zoom_change_requested.connect(self.view.zoom_set)
    # End of def zoom_connect
# End of class AnnotatorWidget