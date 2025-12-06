"""Staus bar for SAMNotator application."""
# --- --- --- Import --- --- ---
# STD
# 3RD
from PySide6.QtCore import Qt, QObject, Slot
from PySide6.QtWidgets import QStatusBar, QLabel
# Project


class StatusBarController(QObject):

    # --- --- --- Init --- --- ---
    
    def __init__(self, status_bar: QStatusBar, parent=None):
        super().__init__(parent)
        self._bar = status_bar
        # Components
        self._pos_label = QLabel(parent=status_bar)
        # Init UI
        self._init_ui()
    # End def __init__

    def _init_ui(self):
        # Position Label
        self.update_position(None)
        self._bar.addPermanentWidget(self._pos_label)
    #
    
    # --- --- --- Slots --- --- ---

    @Slot(object)
    def update_position(self, pos: tuple[int, int] | None) -> None:
        if pos is not None:
            self._pos_label.setText(f"XY: {pos[0]}, {pos[1]}")
        else:
            self._pos_label.setText("XY: -, -")
