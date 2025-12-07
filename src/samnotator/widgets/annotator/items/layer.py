# --- --- --- Imports --- --- ---
# STD
from dataclasses import dataclass
# 3RD
from PySide6.QtCore import QRectF
from PySide6.QtGui import QPixmap, QPainter
from PySide6.QtWidgets import QGraphicsPixmapItem, QGraphicsItem
# Project
from samnotator.datamodel import InstanceID
from samnotator.datamodel import PointID
from ..base import ZValues



# --- --- --- LayerItem --- --- ---

class LayerItem(QGraphicsItem):
    """A layer item able to hold other items as children, without visual contents itself."""
    def __init__(self, isntance_id:InstanceID, parent=None):
        super().__init__(parent)
        self.instance_id = isntance_id
        # No visual contents: this item only serves as a container
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemHasNoContents, True)

    def boundingRect(self) -> QRectF:
        # Not used (no painting), but must be implemented
        return QRectF()

    def paint(self, painter:QPainter, option, widget=None):
        # No painting
        pass
    #
#



# --- --- --- Layer bundle per instance --- --- ---

@dataclass(slots=True)
class Layer:
    instance_id:InstanceID
    # Layers:
    layer_points:LayerItem
    layer_bbox:LayerItem
    layer_mask:LayerItem
    #
    point_items:dict[PointID, QXItemPoint]
    markers:list[QPixmap]
    mask:QGraphicsPixmapItem|None
    #

    # --- --- --- Helpers --- --- ---

    @classmethod
    def default(cls, instance_id:InstanceID) -> Layer:
        lp = LayerItem(instance_id)
        lp.setZValue(ZValues.POINTS)
        #
        lb = LayerItem(instance_id)
        lb.setZValue(ZValues.BBOX)
        #
        lm = LayerItem(instance_id)
        lm.setZValue(ZValues.MASK)
        #
        return cls(instance_id = instance_id, layer_points = lp, layer_bbox = lb, layer_mask = lm, point_items = {}, markers = [], mask = None)
    # End of classmethod def default
#

