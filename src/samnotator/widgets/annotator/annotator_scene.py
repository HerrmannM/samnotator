"""Define the annotator scene (holding the data) to be de displayed in a view."""
# --- --- --- Imports --- --- ---
# STD
from typing import cast
from dataclasses import dataclass
# 3RD
from PySide6.QtCore import Qt, QObject, Signal, Slot, QRect, QRectF, QPointF, QPoint
from PySide6.QtGui import QPixmap, QPainter
from PySide6.QtGui import QPainterPath, QPainter, QPen, QBrush
from PySide6.QtGui import QKeyEvent, QEnterEvent, QFocusEvent, QResizeEvent
from PySide6.QtWidgets import QGraphicsScene, QGraphicsPixmapItem, QGraphicsItem, QGraphicsSceneMouseEvent
# Project
from samnotator.controllers.annotations_controller import AnnotationsController
from samnotator.controllers.instance_controller import InstanceController
from samnotator.datamodel import FrameID, InstanceID, BBoxID, BBox, BBoxAnnotation
from samnotator.datamodel import PointAnnotation, PointKind, PointID, PointXY, Point
from samnotator.utils._CUD import CUD
from .items.qxitempoint import QXItemPoint
from .items.bbox import QXItemBox, QXItemRect
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
        # Bbox drag fields
        self._drag_button: Qt.MouseButton | None = None
        self._drag_start_scene_pos: QPointF | None = None
        self._drag_current_scene_pos: QPointF | None = None
        self._drag_box_preview: QXItemRect | None = None
        self._selected_items_on_press: set[QGraphicsItem]|None = None
        
        #
        self.instance_layers:dict[InstanceID, Layer] = {}

        # Setup
        self._init_ui()
    # End of def __init__


    def _init_ui(self) -> None:
        self.setSceneRect(self.qpixmap.rect())
        # Connect: controller -> scene
        self.annotations_controller.point_list_changed.connect(self.on_point_list_changed)
        self.annotations_controller.bbox_list_changed.connect(self.on_bbox_list_changed)
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
    def on_bbox_list_changed(self, bbox_annotations:list[BBoxAnnotation], cud:CUD) -> None:
        match cud:
            case CUD.CREATE:
                for ba in bbox_annotations:
                    self.add_bbox_annotation(ba)
            case CUD.UPDATE:
                for ba in bbox_annotations:
                    self.update_bbox_annotation(ba)
            case CUD.DELETE:
                for ba in bbox_annotations:
                    self.delete_bbox_annotation(ba)
            #
        #
    # End of def on_bbox_list_changed


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
                instance_layer.layer_bbox.setVisible(instance.show_markers)
                # - Update marks
                mark_pixmaps_request:list[QPixmap] = instance.point_marks
                if mark_pixmaps_request != instance_layer.markers:
                    for item in instance_layer.point_items.values():
                        item.set(mark_pixmaps_request[item.point_kind], None)

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
        self.clearSelection()
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
        kind = pa.point.kind
        mark:QPixmap = self.instance_controller.get(pa.instance_id).point_marks[kind]
        self.instance_layers[pa.instance_id].point_items[pa.point_id].set(pixmap=mark, kind=kind, point_xy=pa.point.position)
    # End of def update_point_annotation


    def delete_point_annotation(self, pid:PointID, iid:InstanceID) -> None:
        layer = self.instance_layers[iid]
        assert pid in layer.point_items, f"Point ID {pid} does not exist in the scene."
        point_item = layer.point_items.pop(pid)
        self.removeItem(point_item)
    # End of def delete_point_annotation


    def add_bbox_annotation(self, ba:BBoxAnnotation) -> None:
        bid, iid = ba.bbox_id, ba.instance_id
        bbox = ba.bbox
        # Set visibility according to instance settings
        instance = self.instance_controller.get(iid)
        if not instance.show_markers:
            self.instance_controller.update_instance(iid, show_markers=True)
        # Create item in its layer
        layer = self.instance_layers[iid]
        assert bid not in layer.bbox_items, f"BBox ID {bid} already exists in the scene."
        rect = QRect(QPoint(*bbox.top_left), QPoint(*bbox.bottom_right))
        instance_info = self.instance_controller.get(iid)
        box_item = QXItemBox(box_id=bid, kind=bbox.kind, instance_info=instance_info, bbox=rect, parent=layer.layer_bbox)
        layer.bbox_items[bid] = box_item
    # End of def add_bbox_annotation


    
    def update_bbox_annotation(self, ba:BBoxAnnotation) -> None:
        bbox = ba.bbox
        kind = bbox.kind
        rect = QRect(QPoint(*bbox.top_left), QPoint(*bbox.bottom_right))
        iinfo = self.instance_controller.get(ba.instance_id)
        self.instance_layers[ba.instance_id].bbox_items[ba.bbox_id].set(rect, kind, iinfo)
    # End of def update_bbox_annotation

    
    def delete_bbox_annotation(self, ba:BBoxAnnotation) -> None:
        bid = ba.bbox_id
        layer = self.instance_layers[ba.instance_id]
        assert bid in layer.bbox_items, f"BBox ID {bid} does not exist in the scene."
        box_item = layer.bbox_items.pop(bid)
        self.removeItem(box_item)
    # End of def delete_bbox_annotation


    # --- --- --- Overrides --- --- ---

    def _reset_drag(self) -> None:
        if self._drag_box_preview is not None:
            self.removeItem(self._drag_box_preview)
        self._drag_box_preview = None
        self._drag_button = None
        self._drag_start_scene_pos = None
        self._drag_current_scene_pos = None
    # End of def reset_drag


    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        # 1) Store select states: allow to tune behaviour when "click on empty" in release button
        self._selected_items_on_press = set(self.selectedItems())

        # 2) Let existing items (points, background, etc.) handle the event first
        super().mousePressEvent(event)

        # 3) Start potential box drag; we decide "box vs point" on release
        btn = event.button()
        if btn in (Qt.MouseButton.LeftButton, Qt.MouseButton.RightButton) and not event.isAccepted():
            self._drag_button = btn
            scene_pos = event.scenePos()
            self._drag_start_scene_pos = scene_pos
            self._drag_current_scene_pos = scene_pos
            event.accept()
    # End of def mousePressEvent

    
    def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        # Process existing items first
        super().mouseMoveEvent(event)

        # Check if we are dragging a box
        # event.buttons() & self._drag_button -> check that the drag button is still pressed
        if (self._drag_button is None or self._drag_start_scene_pos is None or not (event.buttons() & self._drag_button)):
            return self._reset_drag()

        # Get current instance info: none -> cannot draw box
        iinfo = self.instance_controller.get_current_instance_info()
        if iinfo is None:
            return self._reset_drag()

        # Update current position
        self._drag_current_scene_pos = event.scenePos()
        start = self._drag_start_scene_pos
        current = self._drag_current_scene_pos

        dx = current.x() - start.x()
        dy = current.y() - start.y()

        # Only consider it a box drag if we exceed min size in BOTH directions
        if abs(dx) < QXItemBox.MIN_SIZE or abs(dy) < QXItemBox.MIN_SIZE:
            if self._drag_box_preview is not None: # This is not the end of the drag, just too small to show
                self.removeItem(self._drag_box_preview)
                self._drag_box_preview = None
            return

        # Create/update preview rectangle (real box is created on release via controller)
        rect = QRectF(start, current).normalized()
        kind = PointKind.POSITIVE if self._drag_button == Qt.MouseButton.LeftButton else PointKind.NEGATIVE
        if self._drag_box_preview is None:
            self._drag_box_preview = QXItemRect(rect, main_colour=iinfo.main_colour, contrast_colour=iinfo.contrast_colour, kind=kind)
            self._drag_box_preview.setZValue(ZValues.DRAG_BOX_PREVIEW)
            self.addItem(self._drag_box_preview)
        else:
            self._drag_box_preview.setRect(rect)
        #

        event.accept()
    # End of def mouseMoveEvent


    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        super().mouseReleaseEvent(event)

        # Get button; if not left/right, ignore, reset drag state
        btn = event.button()
        if btn not in (Qt.MouseButton.LeftButton, Qt.MouseButton.RightButton):
            return self._reset_drag()

        # No drag state: treat as normal scene release. ensure drag state is reset
        if self._drag_button is None or self._drag_start_scene_pos is None:
            return self._reset_drag()

        # Get current instance info: none -> cannot draw box
        iinfo = self.instance_controller.get_current_instance_info()
        if iinfo is None:
            return self._reset_drag()
        iid = iinfo.instance.instance_id

        # Determine if it was a drag or a click
        start = self._drag_start_scene_pos.toPoint()
        end = event.scenePos().toPoint()
        dx = end.x() - start.x()
        dy = end.y() - start.y()
        is_drag = abs(dx) >= QXItemBox.MIN_SIZE and abs(dy) >= QXItemBox.MIN_SIZE

        # Clear drag state
        self._reset_drag()

        # If something was selected deselect it and return if not a drag: allow 'deselect on click'
        if self._selected_items_on_press is not None and self._selected_items_on_press:
            self._selected_items_on_press = None
            self.clearSelection()
            if not is_drag:
                return

        # If it wasn't a "big enough" drag, treat it as a point click (old behaviour)
        if not is_drag:
            scene_pos = event.scenePos()
            xy = PointXY((int(scene_pos.x()), int(scene_pos.y())))
            kind = PointKind.POSITIVE if btn == Qt.MouseButton.LeftButton else PointKind.NEGATIVE
            point = Point(position=xy, kind=kind)
            self.annotations_controller.create_point(self.frame_id, iid, point)
            event.accept()
        else:
            rect = QRect(start, end).normalized()
            top_left = PointXY(rect.topLeft().toTuple())
            bottom_right = PointXY(rect.bottomRight().toTuple())
            kind = PointKind.POSITIVE if btn == Qt.MouseButton.LeftButton else PointKind.NEGATIVE
            bbox = BBox(top_left=top_left, bottom_right=bottom_right, kind=kind)
            self.annotations_controller.create_bbox(self.frame_id, iid, bbox)

        event.accept()
    # End of def mouseReleaseEvent

    
    def keyPressEvent(self, event: QKeyEvent) -> None:
        # Delete selected points on Delete/Backspace
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            did_delete:bool = False
            for item in self.selectedItems():
                if isinstance(item, QXItemPoint):
                    did_delete = True
                    self.annotations_controller.delete_point(item.point_id)
                elif isinstance(item, QXItemBox):
                    did_delete = True
                    self.annotations_controller.delete_bbox(item.box_id)
            if did_delete: # If we deleted something, accept the event and stop propagation
                event.accept()
                return
        # Anything else (or nothing selected): normal behavior
        super().keyPressEvent(event)
    # End of def keyPressEvent
# End of AnnotatorScene

