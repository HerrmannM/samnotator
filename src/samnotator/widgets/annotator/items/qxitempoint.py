# --- --- --- Imports --- --- ---
# STD
from typing import cast
# 3RD
from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QGraphicsPixmapItem, QGraphicsItem, QGraphicsSceneMouseEvent
# Project
from samnotator.datamodel import InstanceID
from samnotator.datamodel import PointKind, PointID, PointXY
from ..base import AnnotatorSceneProtocol


class QXItemPoint(QGraphicsPixmapItem):

    def __init__(self, pid:PointID, kind:PointKind, iid:InstanceID, pixmap:QPixmap, position:PointXY, parent:QGraphicsItem|None=None) -> None:
        super().__init__(pixmap, parent)
        self.point_id = pid
        self.instance_id = iid

        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)

        # If we have perf issue... we should not with the amount of mark/scene
        #self.setShapeMode(QGraphicsPixmapItem.ShapeMode.BoundingRectShape)

        self.set(pixmap, kind, position)
    # End of def __init__


    def set(self, pixmap:QPixmap|None, kind:PointKind|None=None, point_xy:PointXY|None=None) -> None:
        if pixmap is not None:
            self.setPixmap(pixmap)

        if kind is not None:
            self.point_kind = kind

        if point_xy is not None:
            center = self.pixmap().rect().center()
            x,y = point_xy
            self.setPos(x+0.5, y+0.5)
            self.setOffset(-center.x(), -center.y())
    # End of def set


    def itemChange(self, change: QGraphicsItem.GraphicsItemChange, value):
        scene = cast(AnnotatorSceneProtocol, self.scene())

        # 1) Selection change: tell controller which instance is current
        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged:
            scene.instance_controller.set_current_instance(self.instance_id)

        # 2) Position change: clamp to scene rect and check for collisions
        elif change == QGraphicsItem.GraphicsItemChange.ItemPositionChange and scene is not None:
            new_pos = cast(QPointF, value)
            scene_rect: QRectF = scene.sceneRect()

            # 1) Clamp to scene rect (keep center inside) and centre on pixel
            x = int(max(scene_rect.left(),  min(new_pos.x(), scene_rect.right())))
            y = int(max(scene_rect.top(),   min(new_pos.y(), scene_rect.bottom())))

            # 2) Collision check
            if scene.annotations_controller.point_can_move(point_id=self.point_id, frame_id=scene.frame_id, xy=PointXY((x, y))):
                return QPointF(x+0.5, y+0.5)
            else: # Position is already occupied: reject the move, stay where we are
                return self.pos()

        return super().itemChange(change, value)
    # End of def itemChange


    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        super().mouseReleaseEvent(event)

        # Check for left button release
        if event.button() == Qt.MouseButton.LeftButton:
            # distinguish drag from click
            down_pos = event.buttonDownScenePos(Qt.MouseButton.LeftButton)
            up_pos = event.scenePos()
            if down_pos == up_pos:
                return

            scene = cast(AnnotatorSceneProtocol, self.scene())

            # final scene pos was already clamped/snaped in itemChange
            final_pos: QPointF = self.pos()
            x_int = int(final_pos.x())
            y_int = int(final_pos.y())

            # commit the move to the controller
            scene.annotations_controller.update_point_move(self.point_id, PointXY((x_int, y_int)))
    # End of def mouseReleaseEvent
    
    def mouseDoubleClickEvent(self, event):
        super().mouseDoubleClickEvent(event)
        scene = cast(AnnotatorSceneProtocol, self.scene())
        scene.annotations_controller.update_point_kind(self.point_id, None) # Toggle kind
    # End of def mouseDoubleClickEvent
# End of class QXItemPoint

