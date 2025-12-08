# --- --- --- Imports --- --- ---
# STD
from typing import cast
from enum import IntEnum, auto
# 3RD
from PySide6.QtCore import Qt, QRect, QRectF, QPoint, QPointF
from PySide6.QtGui import QPen, QBrush, QColor, QPainter
from PySide6.QtWidgets import QGraphicsItem, QGraphicsRectItem, QGraphicsSceneMouseEvent, QStyleOptionGraphicsItem, QWidget
# Project
from samnotator.datamodel import InstanceID, Instance, BBox, BBoxID, PointKind, PointXY
from samnotator.controllers.instance_controller import InstanceInfo
from ..base import AnnotatorSceneProtocol


# --- --- --- Anchor --- --- ---

class _HandleAnchor(IntEnum):
    TopLeft = auto()
    TopCenter = auto()
    TopRight = auto()
    Right = auto()
    BottomRight = auto()
    BottomCenter = auto()
    BottomLeft = auto()
    Left = auto()

    def get_rect(self, hs: float) -> QRectF:
        """Return a rect of side "handle size" `hs`, offset so that putting the origin (0,0) of the anchor A at is place on a box B (corner or edge) places A outside of B."""
        match self:
            case _HandleAnchor.TopLeft:      return QRectF(-hs, -hs, hs, hs)
            case _HandleAnchor.TopCenter:    return QRectF(-hs / 2, -hs, hs, hs)
            case _HandleAnchor.TopRight:     return QRectF(0, -hs, hs, hs)
            case _HandleAnchor.Right:        return QRectF(0, -hs / 2, hs, hs)
            case _HandleAnchor.BottomRight:  return QRectF(0, 0, hs, hs)
            case _HandleAnchor.BottomCenter: return QRectF(-hs / 2, 0, hs, hs)
            case _HandleAnchor.BottomLeft:   return QRectF(-hs, 0, hs, hs)
            case _HandleAnchor.Left:         return QRectF(-hs, -hs / 2, hs, hs)
            case _: return QRectF(0, 0, hs, hs)
    # End of def get_rect
# End of class _HandleAnchor


# --- --- --- Custom Rect Item --- --- ---

class QXItemRect(QGraphicsRectItem):

    # --- --- --- Init --- --- ---

    def __init__(self, rect: QRectF|QRect, main_colour: QColor, contrast_colour: QColor, kind:PointKind, parent: QGraphicsItem | None = None) -> None:
        super().__init__(rect, parent)
        self.main_colour = main_colour
        self.contrast_colour = contrast_colour
        self.kind = kind
    # End of def __init__


    # --- --- --- Custom painting --- --- ---


    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget: QWidget | None = None) -> None:
        
        # --- Common Setup ---
        
        # 1. Define the contrast pen
        contrast_pen = QPen(self.contrast_colour)
        contrast_pen.setCosmetic(True)

        # 2. Define the main color pen
        main_pen = QPen(self.main_colour)
        main_pen.setCosmetic(True)

        # 3. Determine base width based on selection
        base_width = 1 if self.isSelected() else 2


        if self.kind == PointKind.POSITIVE:
            # --- POSITIVE KIND: Outline only (Contrast + Color edge) ---
            # Draw the first (outer/thicker) edge in contrast color
            # Width = 2*base_width ensures the contrast edge is thicker than the color edge
            contrast_pen.setWidth(2 * base_width) 
            painter.setPen(contrast_pen)
            
            # Set brush to NoBrush for no fill
            painter.setBrush(Qt.BrushStyle.NoBrush) 
            painter.drawRect(self.rect())
            
            # Draw the second (inner/thinner) edge in main color
            main_pen.setWidth(base_width)
            painter.setPen(main_pen)

            # Drawing again automatically overlays the previous path
            painter.drawRect(self.rect())

        else:
            # --- NON-POSITIVE KIND: Filled (Original Logic) ---
            
            # Set the single contrast pen width
            contrast_pen.setWidth(base_width)

            # Brush style depending on kind
            fill_color = QColor(self.main_colour)
            fill_color.setAlpha(255) # Assume non-positive is the original opacity
            style = Qt.BrushStyle.DiagCrossPattern # From original logic
            brush = QBrush(fill_color, style)

            # Draw with the single pen and fill
            painter.setPen(contrast_pen)
            painter.setBrush(brush)
            painter.drawRect(self.rect())
            
    # End of def paint
    

# End of class QXItemRect


# --- --- --- Handle Item --- --- ---

class _QXBoxHandle(QGraphicsRectItem):
    """
    A resize handle for QXItemBox.
    - Child of the box
    - Fixed screen size via ItemIgnoresTransformations
    - Not selectable
    - Dragging it resizes the parent box
    """

    MIN_HANDLE_SIZE: int = 4
    MIN_BORDER_SIZE: int = 2

    # --- --- --- Init --- --- ---

    def __init__(self, anchor: _HandleAnchor, parent_box: QXItemBox) -> None:
        super().__init__(parent_box)
        # Fields
        self.anchor = anchor
        self.parent_box = parent_box
        self._dragging: bool = False

        # Behaviour: in screen space; we do not use ItemIsMovable; we handle drag manually.
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, True)
        self.setAcceptedMouseButtons(Qt.MouseButton.LeftButton)
        self.setVisible(False)

        # Init
        self.set(parent_box.instance_info)
    # End of def __init__

    
    def set(self, instance_info: InstanceInfo) -> None:
        # Size
        current_size = int(self.rect().width())
        new_handle_size = instance_info.bbox_handle_size
        if new_handle_size is not None and new_handle_size != current_size:
            new_handle_size = max(new_handle_size, self.MIN_HANDLE_SIZE)
            self.setRect(self.anchor.get_rect(new_handle_size))
        else:
            new_handle_size = current_size
        #

        # Style
        pen = QPen(instance_info.contrast_colour)
        pen.setWidth(max(self.MIN_BORDER_SIZE, int(new_handle_size*0.33)))
        pen.setCosmetic(True)
        self.setPen(pen)
        brush = QBrush(instance_info.main_colour)
        self.setBrush(brush)
        #
    #  End of def set


    # --- --- --- Mouse overrides --- --- ---
    # Capture mouse event here for simplicity but handle the logic in the parent box

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self.parent_box.begin_handle_drag()
            event.accept()
        else:
            event.ignore()
    # End of def mousePressEvent


    def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if self._dragging:
            self.parent_box.on_handle_dragged(self.anchor, event.scenePos())
            event.accept()
        else:
            event.ignore()
    # End of def mouseMoveEvent


    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if self._dragging and event.button() == Qt.MouseButton.LeftButton:
            self._dragging = False
            self.parent_box.end_handle_drag()
            event.accept()
        else:
            event.ignore()
    # End of def mouseReleaseEvent
# End of class _QXBoxHandle


# --- --- --- Box Item --- --- ---

class QXItemBox(QXItemRect):
    """Interactive bounding box representing a rect in scene/image coordinates, with 8 resize handles."""

    MIN_SIZE:int = 2
    
    # --- --- --- Init --- --- ---

    def __init__(self, box_id: BBoxID, kind: PointKind, instance_info: InstanceInfo, bbox: QRect, parent:QGraphicsItem | None = None) -> None:
        """bbox must be in scene coordinates."""
        # Adapt geometry: pos() is in scene coords (bbox.topLeft()), rect is in local coords (0,0,w,h) so local origin is always (0,0)
        local_rect = QRect(0, 0, bbox.width(), bbox.height())
        super().__init__(local_rect, main_colour=instance_info.main_colour, contrast_colour=instance_info.contrast_colour, parent=parent, kind=kind)

        # Fields
        self.box_id: BBoxID = box_id
        self.instance_info: InstanceInfo = instance_info
        self.kind: PointKind = kind
        self._dragging_start_bbox: QRect | None = None
        self._handles: dict[_HandleAnchor, _QXBoxHandle] = {}

        # Behaviour flags
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)

        # Init
        self.setPos(bbox.topLeft())
        self._create_handles()
        self._update_handles_positions()
        self._set_handles_visible(False)
    # End of def __init__


    def _create_handles(self) -> None:
        for role in _HandleAnchor:
            handle = _QXBoxHandle(role, self)
            self._handles[role] = handle
    # End of def _create_handles

    
    # --- --- --- Update --- --- ---

    def set(self, rect_scene_coordinate:QRect|None=None, kind:PointKind|None=None, instance_info:InstanceInfo|None=None) -> None:
        # Position
        if rect_scene_coordinate is not None:
            self._updated_bbox(rect_scene_coordinate)

        # Kind
        if kind is not None:
            self.kind = kind
            self.update()

        # Instance info
        if instance_info is not None:
            self.instance_info = instance_info
            self.main_colour = instance_info.main_colour
            self.contrast_colour = instance_info.contrast_colour
            self.update()
    # End of def set


    # --- -- ---- Private helpers --- --- ---

    def _set_handles_visible(self, visible: bool) -> None:
        zvalue = self.zValue() + 1 # Always on top of the box
        for h in self._handles.values():
            h.setVisible(visible)
            h.setZValue(zvalue)
    # End of def _set_handles_visible


    def _updated_bbox(self, bbox: QRect) -> None:
        """Update local rect/pos from a bbox in scene coordinates and update handles."""
        # Always work with a normalised rect as the original geometry
        original = bbox.normalized()
        scene_rect = self.scene().sceneRect().toRect()
        # Scene geometry
        scene_left = scene_rect.left()
        scene_top = scene_rect.top()
        scene_w = scene_rect.width()
        scene_h = scene_rect.height()
        # Desired sizes: respect MIN_* but never exceed scene size
        desired_w = max(original.width(), self.MIN_SIZE)
        desired_h = max(original.height(), self.MIN_SIZE)
        # Target sizes clamped to scene size
        width = min(desired_w, scene_w)
        height = min(desired_h, scene_h)

        # Clamp top-left so that the box stays inside the scene with target width/height (clamped to scene size)
        min_left = scene_left
        max_left = scene_left + scene_w - width  # == scene_right - width
        if max_left < min_left:
            left = scene_left
        else:
            left = min(max(original.left(), min_left), max_left)

        min_top = scene_top
        max_top = scene_top + scene_h - height
        if max_top < min_top:
            top = scene_top
        else:
            top = min(max(original.top(), min_top), max_top)

        # Apply: pos = top-left, local rect = (0,0,w,h)
        self.setPos(left, top)
        self.setRect(QRect(0, 0, width, height))

        # Update handle anchors
        self._update_handles_positions()
    # End of def _updated_bbox


    def _update_handles_positions(self) -> None:
        """Position handles around the box, fully outside."""
        r: QRectF = self.rect()
        xleft, ytop = r.left(), r.top()
        xright, ybottom = r.right(), r.bottom()
        xcenter = (xleft + xright) * 0.5
        ycenter = (ytop + ybottom) * 0.5

        # Anchors are in local (box) coordinates
        anchors: dict[_HandleAnchor, QPointF] = {
            _HandleAnchor.TopLeft: QPointF(xleft, ytop),
            _HandleAnchor.TopCenter: QPointF(xcenter, ytop),
            _HandleAnchor.TopRight: QPointF(xright, ytop),
            _HandleAnchor.Right: QPointF(xright, ycenter),
            _HandleAnchor.BottomRight: QPointF(xright, ybottom),
            _HandleAnchor.BottomCenter: QPointF(xcenter, ybottom),
            _HandleAnchor.BottomLeft: QPointF(xleft, ybottom),
            _HandleAnchor.Left: QPointF(xleft, ycenter),
        }

        for role, handle in self._handles.items():
            handle.setPos(anchors[role])
    # End of def _update_handles_positions


    def _commit_rect_change(self) -> None:
        new_rect = self.mapRectToScene(self.rect()).toRect()
        new_top_left = PointXY(new_rect.topLeft().toTuple())
        new_bottom_right = PointXY(new_rect.bottomRight().toTuple())
        new_bbox = BBox(top_left=new_top_left, bottom_right=new_bottom_right, kind=self.kind)
        scene = cast(AnnotatorSceneProtocol, self.scene())
        scene.annotations_controller.update_move_box(self.box_id, new_bbox)
    # End of def _commit_rect_change


    # --- --- --- Selection / item changes --- --- ---

    def itemChange(self, change: QGraphicsItem.GraphicsItemChange, value):
        scene = cast(AnnotatorSceneProtocol, self.scene())

        # 1) Handle selection
        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged:
            selected = bool(value)
            self._set_handles_visible(selected)
            scene.instance_controller.set_current_instance(self.instance_info.instance.instance_id)

        # 2) Position changed: clamp movement to sceneRect
        elif change == QGraphicsItem.GraphicsItemChange.ItemPositionChange:
            scene_rect = scene.sceneRect()
            new_pos = cast(QPointF, value)
            # clamp so the whole box stays inside scene rect
            min_x = scene_rect.left()
            min_y = scene_rect.top()
            max_x = scene_rect.right() - self.rect().width()
            max_y = scene_rect.bottom() - self.rect().height()
            clamped_x = min(max(new_pos.x(), min_x), max_x)
            clamped_y = min(max(new_pos.y(), min_y), max_y)
            return QPointF(clamped_x, clamped_y)

        return super().itemChange(change, value)
    # End of def itemChange


    # --- RESIZE: Handle drag protocol ---

    def begin_handle_drag(self) -> None:
        """Called by handles on mouse press."""
        # Store starting bbox in scene coordinates
        self._dragging_start_bbox = self.mapRectToScene(self.rect()).toRect()
    # End of def begin_handle_drag


    def on_handle_dragged(self, role: _HandleAnchor, anchor_scene: QPointF) -> None:
        """Called by handles during mouse move. Compute and apply new rect."""
        if self._dragging_start_bbox is None:
            return

        # Starting rectangle remains the reference during the drag
        # Do not update it until drag ends/do not use self.rect() during drag (it would accumulate changes instead)
        r0 = self._dragging_start_bbox
        left0, right0 = r0.left(), r0.right()
        top0, bottom0 = r0.top(), r0.bottom()

        # Current anchor position in scene coords: delta to starting rect
        x = int(anchor_scene.x())
        y = int(anchor_scene.y())

        # Init value = pre drag rect, then adjust according to handle role and anchor scene position
        left, right = left0, right0
        top, bottom = top0, bottom0

        # X axis: anchor on left or right edge
        # Don't let left/right edges cross each other: clamp to opposite edges adjusted by +- MIN_SIZE
        if role in (_HandleAnchor.Left, _HandleAnchor.TopLeft, _HandleAnchor.BottomLeft):
            right_fixed = right0 - self.MIN_SIZE
            left = min(x, right_fixed)
        if role in (_HandleAnchor.Right, _HandleAnchor.TopRight, _HandleAnchor.BottomRight):
            left_fixed = left0 + self.MIN_SIZE
            right = max(x, left_fixed)
        #

        # Y axis: anchor on top or bottom edge
        # Don't let top/bottom edges cross each other: clamp to opposite edges adjusted by +- MIN_SIZE
        if role in (_HandleAnchor.TopCenter, _HandleAnchor.TopLeft, _HandleAnchor.TopRight):
            bottom_fixed = bottom0 - self.MIN_SIZE
            top = min(y, bottom_fixed)
        if role in (_HandleAnchor.BottomCenter, _HandleAnchor.BottomLeft, _HandleAnchor.BottomRight):
            top_fixed = top0 + self.MIN_SIZE
            bottom = max(y, top_fixed)
        #

        new_scene_rect = QRect(QPoint(left, top), QPoint(right, bottom))
        self._updated_bbox(new_scene_rect)
    # End of def on_handle_dragged


    def end_handle_drag(self) -> None:
        """Called by handles on release. Commit final rect to controller."""
        if self._dragging_start_bbox is None:
            return
        self._dragging_start_bbox = None
        self._commit_rect_change()
    # End of def end_handle_drag


    # --- MOVE: Mouse release for whole-box moves: commit move ---

    def mouseReleaseEvent(self, event:QGraphicsSceneMouseEvent) -> None:
        super().mouseReleaseEvent(event)
        if event.button() == Qt.MouseButton.LeftButton:
            self._commit_rect_change()
    # End of def mouseReleaseEvent
# End of class QXItemBox