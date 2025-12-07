"""Define the annotator scene (holding the data) to be de displayed in a view."""
# --- --- --- Imports --- --- ---
# STD
from typing import cast
from dataclasses import dataclass
# 3RD
from PySide6.QtCore import Qt, QObject, Signal, Slot, QRectF, QPointF
from PySide6.QtGui import QPixmap, QPainter
from PySide6.QtGui import QPainterPath, QPainter, QPen
from PySide6.QtGui import QKeyEvent, QEnterEvent, QFocusEvent, QResizeEvent
from PySide6.QtWidgets import QGraphicsScene, QGraphicsPixmapItem, QGraphicsItem, QGraphicsSceneMouseEvent
# Project
from samnotator.controllers.annotations_controller import AnnotationsController
from samnotator.controllers.instance_controller import InstanceController
from samnotator.datamodel import FrameID, InstanceID
from samnotator.datamodel import PointAnnotation, PointKind, PointID, PointXY, Point
from samnotator.utils._CUD import CUD
from .items.qxitempoint import QXItemPoint
from .items.layer import Layer, LayerItem
from .base import ZValues, AnnotatorSceneProtocol


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
        self.instance_layers:dict[InstanceID, Layer] = {}

        # Setup
        self._init_ui()
    # End of def __init__


    def _init_ui(self) -> None:
        self.setSceneRect(self.qpixmap.rect())
        # Connect: controller -> scene
        self.annotations_controller.point_list_changed.connect(self.on_point_list_changed)
        self.instance_controller.instance_changed.connect(self.on_instance_changed)
        self.instance_controller.current_instance_changed.connect(self.on_current_instance_changed)
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
                self.instance_layers[instance_id] = Layer.default(instance_id=instance_id)
                self.addItem(self.instance_layers[instance_id].layer_mask)
                self.addItem(self.instance_layers[instance_id].layer_bbox)
                self.addItem(self.instance_layers[instance_id].layer_points)

            case CUD.UPDATE:
                instance = self.instance_controller.get(instance_id)
                instance_layer = self.instance_layers[instance_id]

                # --- Marks
                # - Visibility
                instance_layer.layer_points.setVisible(instance.show_markers)
                # - Update marks
                mark_pixmaps_request:list[QPixmap] = instance.point_marks
                if mark_pixmaps_request != instance_layer.markers:
                    for item in instance_layer.point_items.values():
                        item.update(mark_pixmaps_request[item.point_kind], None)

                # --- Mask
                # - Visbility
                instance_layer.layer_mask.setVisible(instance.show_mask)
                # - Update mask: for now, full re update
                mask = self.instance_controller.get_mask_for(instance_id, self.frame_id, instance.show_plain_mask)
                if mask is not None:
                    if instance_layer.mask is None: # New mask
                        mask_item = QGraphicsPixmapItem(mask, parent = instance_layer.layer_mask)
                        mask_item.setZValue(ZValues.MASK)  # behind points
                        instance_layer.mask = mask_item
                    else: # Update existing mask
                        instance_layer.mask.setPixmap(mask)
                    #
                #
                    
            case CUD.DELETE:
                instance_layer = self.instance_layers.pop(instance_id)
                self.removeItem(instance_layer.layer_points)
                self.removeItem(instance_layer.layer_bbox)
                self.removeItem(instance_layer.layer_mask)
            #
        #
    #


    @Slot(object)
    def on_current_instance_changed(self, instance_id:InstanceID|None) -> None:
        """Set the instance with `instance_id` as selected (or None for no selection), updating Z values accordingly."""
        for iid, layer in self.instance_layers.items():
            if iid == instance_id:
                layer.layer_points.setZValue(ZValues.SELECTED_POINTS)
                layer.layer_bbox.setZValue(ZValues.SELECTED_BBOX)
            else:
                layer.layer_points.setZValue(ZValues.POINTS)
                layer.layer_bbox.setZValue(ZValues.BBOX)
            #
    # End of def select_layer


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
        # Set visibility according to instance settings
        instance = self.instance_controller.get(iid)
        if not instance.show_markers:
            self.instance_controller.update_instance(iid, show_markers=True)
        # Create item in its layer
        layer = self.instance_layers[iid]
        assert pid not in layer.point_items, f"Point ID {pid} already exists in the scene."
        mark:QPixmap = self.instance_controller.get(iid).point_marks[kind]
        point_item = QXItemPoint(pid, kind, iid, mark, pa.point.position, parent=layer.layer_points)
        layer.point_items[pid] = point_item
    # End of def add_point_annotation

    
    def update_point_annotation(self, pa:PointAnnotation) -> None:
        mark:QPixmap = self.instance_controller.get(pa.instance_id).point_marks[pa.point.kind]
        self.instance_layers[pa.instance_id].point_items[pa.point_id].update(mark, pa.point.position)
    # End of def update_point_annotation


    def delete_point_annotation(self, pid:PointID, iid:InstanceID) -> None:
        layer = self.instance_layers[iid]
        assert pid in layer.point_items, f"Point ID {pid} does not exist in the scene."
        point_item = layer.point_items.pop(pid)
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