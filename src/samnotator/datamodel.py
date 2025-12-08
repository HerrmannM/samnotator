# --- --- --- Imports --- --- ---
# STD
from dataclasses import dataclass
from enum import IntEnum
from typing import Any, NewType
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
    category_name:str|None
    #
    detections:dict[FrameID, InstanceDetection]

    def to_dict(self) -> dict[str, Any]:
        return {
            "instance_id": self.instance_id,
            "instance_name": self.instance_name,
            "category_name": self.category_name,
        }
    

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

    def to_dict(self) -> dict[str, Any]:
        return {
            "point_id": self.point_id,
            "frame_id": self.frame_id,
            "instance_id": self.instance_id,
            "position": list(self.point.position),
            "kind": int(self.point.kind),
        }
# End of class PointAnnotation
   

   
# --- --- --- Boxes Annotations --- --- ---

BBoxID = NewType("BBoxID", int)

@dataclass(frozen=True, slots=True)
class BBox:
    top_left:PointXY
    bottom_right:PointXY
    kind:PointKind

    
@dataclass(frozen=True, slots=True)
class BBoxAnnotation:
    bbox_id:BBoxID
    frame_id:FrameID
    instance_id:InstanceID
    bbox:BBox

    def to_dict(self) -> dict[str, Any]:
        return {
            "bbox_id": self.bbox_id,
            "frame_id": self.frame_id,
            "instance_id": self.instance_id,
            "top_left": list(self.bbox.top_left),
            "bottom_right": list(self.bbox.bottom_right),
            "kind": int(self.bbox.kind),
        }