"""Define the annotator scene (holding the data) to be de displayed in a view."""
# --- --- --- Imports --- --- ---
# STD
from typing import cast
# 3RD
from PySide6.QtCore import Qt, QObject, Signal, Slot, QRectF, QPointF
from PySide6.QtGui import QPixmap, QPainter
from PySide6.QtGui import QPainterPath, QPainter, QPen
from PySide6.QtGui import QKeyEvent, QEnterEvent, QFocusEvent, QResizeEvent
from PySide6.QtWidgets import QGraphicsScene, QGraphicsPixmapItem, QGraphicsItem, QGraphicsSceneMouseEvent
# Project
from samnotator.controllers.annotations_controller import AnnotationsController
from samnotator.controllers.frame_controller import FrameController
from samnotator.controllers.instance_controller import InstanceController
from samnotator.datamodel import FrameID, InstanceID
from samnotator.datamodel import PointAnnotation, PointKind, PointID, PointXY, Point
from samnotator.utils._CUD import CUD


class QXItemPoint(QGraphicsPixmapItem):

    def __init__(self, pid:PointID, kind:PointKind, iid:InstanceID, pixmap:QPixmap, position:PointXY, parent=None) -> None:
        super().__init__(pixmap, parent)
        self.point_id = pid
        self.point_kind = kind
        self.instance_id = iid

        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)

        # If we have perf issue... we should not with the amount of mark/scene
        #self.setShapeMode(QGraphicsPixmapItem.ShapeMode.BoundingRectShape)

        self.update(pixmap, position)
    # End of def __init__


    def update(self, pixmap:QPixmap|None, point_xy:PointXY|None, visible=True) -> None:
        if pixmap is not None:
            self.setPixmap(pixmap)

        if point_xy is not None:
            center = pixmap.rect().center()
            x,y = point_xy
            self.setPos(x+0.5, y+0.5)
            self.setOffset(-center.x(), -center.y())

        self.setVisible(visible)
    # End of def update


    def itemChange(self, change: QGraphicsItem.GraphicsItemChange, value):
        scene = cast(AnnotatorScene, self.scene())

        # 1) Selection change: tell controller which instance is current
        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged:
            scene.instance_controller.set_current_instance(self.instance_id)

        # 2) Position change: clamp to scene rect and check for collisions
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange and scene is not None:
            new_pos: QPointF = value
            scene_rect: QRectF = scene.sceneRect()

            # 1) Clamp to scene rect (keep center inside) and centre on pixel
            x = int(max(scene_rect.left(),  min(new_pos.x(), scene_rect.right())))
            y = int(max(scene_rect.top(),   min(new_pos.y(), scene_rect.bottom())))

            # 2) Collision check
            if scene.frame_id is None:
                return self.pos()
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

            scene = self.scene()
            assert isinstance(scene, AnnotatorScene)
            if scene.frame_id is None:
                return

            # final scene pos was already clamped/snaped in itemChange
            final_pos: QPointF = self.pos()
            x_int = int(final_pos.x())
            y_int = int(final_pos.y())

            # commit the move to the controller
            scene.annotations_controller.update_move_point(self.point_id, PointXY((x_int, y_int)))
# End of class QXItemPoint



class AnnotatorScene(QGraphicsScene):

    # --- --- --- Init --- --- ---

    def __init__(self,
                 annotations_controller:AnnotationsController,
                 instance_controller:InstanceController,
                 frame_id:FrameID,
                 qpixmap:QPixmap,
                 parent=None
    ) -> None:
        super().__init__(parent)

        # Fields
        self.annotations_controller = annotations_controller
        self.instance_controller = instance_controller
        self.frame_id:FrameID = frame_id
        self.qpixmap:QPixmap = qpixmap
        #
        self.point_items:dict[PointID, QXItemPoint] = {}
        self.instance_points:dict[InstanceID, set[PointID]] = {}
        self.instance_mask:dict[InstanceID, QGraphicsPixmapItem] = {}

        # Setup
        self._init_ui()
    # End of def __init__


    def _init_ui(self) -> None:
        self.setSceneRect(self.qpixmap.rect())
        # Connect: controller -> scene
        self.annotations_controller.point_list_changed.connect(self.on_point_list_changed)
        self.instance_controller.instance_changed.connect(self.on_instance_changed)
    # End of def _init_ui

    
    # --- --- --- Slots --- --- ---


    @Slot(object, CUD)
    def on_point_list_changed(self, point_annotations:list[PointAnnotation], cud:CUD) -> None:
        match cud:
            case CUD.CREATE:
                for pa in point_annotations:
                    self.add_point_annotation(pa)
            case CUD.UPDATE:
                for pa in point_annotations:
                    self.update_point_annotation(pa)
            case CUD.DELETE:
                for pa in point_annotations:
                    self.delete_point_annotation(pa.point_id, pa.instance_id)
            #
        #
    #


    @Slot(object, CUD)
    def on_instance_changed(self, instance_id:InstanceID, cud:CUD) -> None:
        match cud:
            case CUD.CREATE:
                pass

            case CUD.UPDATE:
                instance = self.instance_controller.get(instance_id)
                # Marks
                mark_visible = instance.show_markers
                marks:list[QPixmap] = self.instance_controller.get(instance_id).point_marks
                for pid in self.instance_points.get(instance_id, set()):
                    item = self.point_items[pid]
                    item.update(marks[item.point_kind], None, visible=mark_visible)
                # Mask - not the best but ok for now (re-render entire mask on any change)
                if instance.show_mask:
                    if (m := self.instance_controller.get_mask_for(instance_id, self.frame_id, instance.show_plain_mask)) is not None:
                        if instance_id in self.instance_mask:
                            item = self.instance_mask[instance_id]
                            item.setPixmap(m)
                            item.setVisible(True)
                        else:
                            mask_item = QGraphicsPixmapItem(m)
                            mask_item.setZValue(-1)  # behind points
                            self.addItem(mask_item)
                            self.instance_mask[instance_id] = mask_item
                else:
                    if instance_id in self.instance_mask:
                        item = self.instance_mask[instance_id]
                        item.setVisible(False)
            #

            case CUD.DELETE:
                # Marker
                for pid in list(self.instance_points.get(instance_id, set())): # make a copy as a list since we modify the set
                    self.delete_point_annotation(pid, instance_id)
                # Mask
                if instance_id in self.instance_mask:
                    item = self.instance_mask.pop(instance_id)
                    self.removeItem(item)
            #
        #
    #


    # --- --- --- Display --- --- ---

    def drawBackground(self, painter: QPainter, rect: QRectF):
        if not self.qpixmap.isNull():
            # No smoothing for pixel-perfect display
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
            painter.drawPixmap(0, 0, self.qpixmap)
    # End of def drawBackground


    def add_point_annotation(self, pa:PointAnnotation) -> None:
        pid, iid = pa.point_id, pa.instance_id
        kind = pa.point.kind
        assert pid not in self.point_items, f"Point ID {pid} already exists in the scene."
        # Set visibility according to instance settings
        instance = self.instance_controller.get(iid)
        if not instance.show_markers:
            self.instance_controller.update_instance(iid, show_markers=True)
        # Create item
        mark:QPixmap = self.instance_controller.get(iid).point_marks[kind]
        point_item = QXItemPoint(pid, kind, iid, mark, pa.point.position)
        self.point_items[pid] = point_item
        self.instance_points.setdefault(iid, set()).add(pid)
        self.addItem(point_item)

    # End of def add_point_annotation

    
    def update_point_annotation(self, pa:PointAnnotation) -> None:
        mark:QPixmap = self.instance_controller.get(pa.instance_id).point_marks[pa.point.kind]
        self.point_items[pa.point_id].update(mark, pa.point.position)
    # End of def update_point_annotation


    def delete_point_annotation(self, pid:PointID, iid:InstanceID) -> None:
        assert pid in self.point_items, f"Point ID {pid} does not exist in the scene."
        point_item = self.point_items.pop(pid)
        self.instance_points[iid].remove(pid)
        self.removeItem(point_item)
    # End of def delete_point_annotation
    

    # --- --- --- Overrides --- --- ---

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        # 1) Let existing items (points, background, etc.) handle the event first
        super().mousePressEvent(event)

        # 2) If nothing handled the click, create a point here
        btn = event.button()
        if btn in (Qt.MouseButton.LeftButton, Qt.MouseButton.RightButton) and not event.isAccepted():
            if (iid := self.instance_controller.get_current_instance_id()) is not None:
                scene_pos = event.scenePos()
                xy = PointXY((int(scene_pos.x()), int(scene_pos.y())))
                kind = PointKind.POSITIVE if btn == Qt.MouseButton.LeftButton else PointKind.NEGATIVE
                point = Point(position=xy, kind=kind)
                self.annotations_controller.create_point(self.frame_id, iid, point)
                event.accept()
    # End of def mousePressEvent

    
    def keyPressEvent(self, event: QKeyEvent) -> None:
        # Delete selected points on Delete/Backspace
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            did_delete:bool = False
            for item in self.selectedItems():
                if isinstance(item, QXItemPoint):
                    did_delete = True
                    self.annotations_controller.delete_point(item.point_id)
            if did_delete: # If we deleted something, accept the event and stop propagation
                event.accept()
                return
        # Anything else (or nothing selected): normal behavior
        super().keyPressEvent(event)
    # End of def keyPressEvent
# End of AnnotatorScene