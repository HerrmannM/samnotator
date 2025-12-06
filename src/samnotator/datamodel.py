# --- --- --- Imports --- --- ---
# STD
from dataclasses import dataclass
from enum import IntEnum
from typing import NewType
# 3RD
import numpy as np
from numpy.typing import NDArray
# Project

# --- --- --- Utils --- --- ---
PointXY = NewType("PointXY", tuple[int, int])
MaskHW = NDArray[np.bool_]   # 2D boolean mask: (H, W) by convention


# --- --- --- Frames --- --- ---

FrameID = NewType("FrameID", int)

    
# --- --- --- Instances --- --- ---

InstanceID = NewType("InstanceID", int)

@dataclass(frozen=True, slots=True)
class InstanceDetection:
    frame_id:FrameID
    top_left:PointXY
    bottom_right:PointXY
    mask:MaskHW|None


@dataclass(frozen=True, slots=True)
class Instance:
    instance_id:InstanceID
    instance_name:str
    instance_colour:str
    category_name:str|None
    #
    detections:dict[FrameID, InstanceDetection]
    

# --- --- --- Points Annotations --- --- ---

PointID = NewType("PointID", int)

class PointKind(IntEnum):
    NEGATIVE=0
    POSITIVE=1


@dataclass(frozen=True, slots=True)
class Point:
    position:PointXY
    kind:PointKind


@dataclass(frozen=True, slots=True)
class PointAnnotation:
    point_id:PointID
    frame_id:FrameID
    instance_id:InstanceID
    point:Point
   