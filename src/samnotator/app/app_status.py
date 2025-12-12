"""Staus bar for SAMNotator application."""
# --- --- --- Import --- --- ---
# STD
# 3RD
from PySide6.QtCore import Qt, QObject, Slot, Signal, QSignalBlocker
from PySide6.QtWidgets import QStatusBar, QLabel, QWidget, QSpinBox
# Project
from samnotator.controllers.frame_controller import FrameController
from samnotator.datamodel import FrameID
from samnotator.utils_qt.contextblock import block_signals


class StatusBarController(QObject):

    request_frame_index = Signal(int)  # Emitted when the user changes the frame index spinbox

    # --- --- --- Init --- --- ---
    
    def __init__(self, status_bar: QStatusBar, ctl_frame: FrameController, parent=None):
        super().__init__(parent)
        # Components
        self._bar = status_bar
        self.ctl_frame = ctl_frame
        # Frame management
        self._frame_index_spinbox = QSpinBox(parent=status_bar)
        self._frame_total_label = QLabel(parent=status_bar)
        self._frame_info_label = QLabel(parent=status_bar)
        # Position Label
        self._pos_label = QLabel(parent=status_bar)
        # Init UI
        self._init_ui()
    # End def __init__

    def _init_ui(self):
        # Frame management
        self._bar.addWidget(self._frame_index_spinbox)
        self._bar.addWidget(self._frame_total_label)
        self._bar.addPermanentWidget(self._frame_info_label, 1)
        # Configure
        self._frame_index_spinbox.setMinimum(0)
        self._frame_index_spinbox.setMaximum(0)
        self._frame_index_spinbox.setKeyboardTracking(False) # Only emit valueChanged when user finishes editing
        # Connect
        self._frame_index_spinbox.valueChanged.connect(self._on_frame_index_changed)
        self.request_frame_index.connect(self.ctl_frame._set_current_frame_index)
        self.ctl_frame.current_frame_changed.connect(self.set_frame)
        # Init
        self.set_frame(self.ctl_frame.get_current_frame_id())

        # Position Label
        self._bar.addPermanentWidget(self._pos_label)
        # Init
        self.update_position(None)
    #
    
    # --- --- --- Slots --- --- ---

    @Slot(object)
    def update_position(self, pos: tuple[int, int] | None) -> None:
        if pos is not None:
            self._pos_label.setText(f"XY: {pos[0]}, {pos[1]}")
        else:
            self._pos_label.setText("XY: -, -")
    # End of Slot def update_position
    

    @Slot(object)
    def set_frame(self, frame:FrameID|None) -> None:
        with block_signals(self._frame_index_spinbox, self._frame_total_label, self._frame_info_label):
            if frame is None:
                self._frame_index_spinbox.setMaximum(0)
                self._frame_index_spinbox.setValue(0)
                self._frame_total_label.setText("/ 0")
                self._frame_info_label.setText("No frame loaded")
                self._frame_info_label.setToolTip("")
            else:
                current_index = self.ctl_frame.current_frame_index
                assert current_index is not None
                total_frames = self.ctl_frame.__len__()
                frame_path = self.ctl_frame.get_frame_path(frame)
                if frame_path is None:
                    frame_info = str(frame)
                    tooltip = "Frame path not available"
                else:
                    frame_info = frame_path.name
                    tooltip = str(frame_path)
                self._frame_index_spinbox.setMaximum(max(1, total_frames))
                self._frame_index_spinbox.setValue(current_index+1)
                self._frame_total_label.setText(f"/ {total_frames}")
                self._frame_info_label.setText(frame_info)
                self._frame_info_label.setToolTip(tooltip)
            #
        #
    #



    @Slot(int)
    def _on_frame_index_changed(self, index: int) -> None:
        assert index >= 0
        self.request_frame_index.emit(index - 1)  # Convert to 0-based index
    #




    # --- --- --- Public API --- --- ---
    
    def set_frame_info(self, current_index: int, total_frames: int, frame_info: str) -> None:
        self._frame_index_spinbox.setMaximum(max(0, total_frames))
        self._frame_index_spinbox.setValue(current_index+1)
        self._frame_total_label.setText(f"/ {total_frames}")
        self._frame_info_label.setText(frame_info)
        self._frame_info_label.setToolTip(frame_info)
    # End def set_frame_info

    
