# --- --- --- Imports --- --- ---
# STD
from enum import IntEnum
from typing import Protocol
# 3RD
from PySide6.QtCore import QRectF
# Project
from samnotator.datamodel import FrameID
from samnotator.controllers.annotations_controller import AnnotationsController
from samnotator.controllers.instance_controller import InstanceController

class ZValues(IntEnum):
    BACKGROUND = 0
    MASK = 1
    BBOX = 2
    POINTS = 3
    SELECTED_BBOX = 4
    SELECTED_POINTS = 5
#



class AnnotatorSceneProtocol(Protocol):
    frame_id: FrameID
    annotations_controller: AnnotationsController
    instance_controller: InstanceController

    def sceneRect(self) -> QRectF: ...