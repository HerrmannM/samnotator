"""Graphic view for the annotator, containing the annotator scene."""
# --- --- --- Imports --- --- ---
# STD
from typing import Callable
# 3RD
from PySide6.QtCore import Qt, QTimer, Signal, Slot, QPoint, QPointF, QRectF, QRect, QSize, QSizeF
from PySide6.QtGui import QMouseEvent, QWheelEvent, QTransform, QPainter, QPen
from PySide6.QtWidgets import QGraphicsScene, QGraphicsView
# Project
from .annotator_scene import AnnotatorScene
from .zoom import ViewZoomState, ZoomInfo
from samnotator.utils_qt.InputMappedMixin import InputMappedMixin
from samnotator.utils_qt.InputMappedMixin import MouseGesture, MouseKey
from samnotator.utils_qt.InputMappedMixin import WheelAxis, WheelHandler, WheelKey
from samnotator.datamodel import Point


# --- --- --- Binding Handlers --- --- ---

class PanGesture(MouseGesture[QGraphicsView]):
    def start(self, v:QGraphicsView, ev:QMouseEvent) -> bool:
        v.setCursor(Qt.CursorShape.ClosedHandCursor)
        self._origin = ev.pos()
        self._h0 = v.horizontalScrollBar().value()
        self._v0 = v.verticalScrollBar().value()
        return True
    # End of def start
    
    def update(self, v:QGraphicsView, ev:QMouseEvent) -> None:
        d = ev.pos() - self._origin
        v.horizontalScrollBar().setValue(self._h0 - d.x())
        v.verticalScrollBar().setValue  (self._v0 - d.y())
    # End of def update
    
    def finish(self, v:QGraphicsView, ev:QMouseEvent) -> None:
        v.unsetCursor()
    # End of def finish
# End of class PanGesture


class ZoomHandlerWheel(WheelHandler['AnnotatorView']):
    def __call__(self, v:AnnotatorView, ev:QWheelEvent) -> bool:
        """Zoom with cursor-anchor, clamped between MIN_SCALE and MAX_SCALE. Snap to fit when too small. Always return True (accept the event)."""
        angle = ev.angleDelta().y()
        if angle != 0: # Check direction
            if angle > 0: zi = v._zoom_state.info_for_zoom_in()
            else: zi = v._zoom_state.info_for_zoom_out()
            v.zoom_to_anchor(zi, ev.position().toPoint())
        # Accept the event
        return True
    # End of def __call__
# End of class ZoomHandlerWheel


# --- --- --- Image View Widget --- --- ---
# Order of inheritance matters here:
# InputMappedWidget must be first to ensure it can handle input events before QGraphicsView processes them.
class AnnotatorView(InputMappedMixin, QGraphicsView):

    zoom_changed = Signal(ZoomInfo)
    mouse_position = Signal(object) # tuple[int, int]|None

    # --- --- --- Constructor --- --- ---
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # --- --- --- Widget Settings --- --- ---
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.NoAnchor)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)

        # --- --- --- Zoom --- --- ---
        self._zoom_state = ViewZoomState(zoom_changed=self.zoom_changed, parent=self)
        self._zoom_handler = ZoomHandlerWheel()

        # --- --- --- Pan --- --- ---
        self._pan_handler = PanGesture()

        # --- --- --- Transform tracking --- --- ---
        self._new_transform = False

        # --- --- --- Mouse Tracking --- --- ---
        self.setMouseTracking(True)
        # Tracking at fixed rate
        self._pending_mouse_pos:QPointF | None = None
        self._hl_update_timer = QTimer(self)
        self._hl_update_timer.setSingleShot(True)
        self._hl_update_timer.setInterval(15) # 60 FPS
        self._hl_update_timer.timeout.connect(self._hl_process_move)
        # Tracking position in scene and corresponding rectangle in the view
        self._hl_scene_pos: QPoint | None = None
        self._hl_view_rect: QRect | None = None
        # Compute once Highlight pens
        self._hl_width_bg:int = 3
        self._hl_pen_bg = QPen(Qt.GlobalColor.black)
        self._hl_pen_bg.setWidth(self._hl_width_bg)
        self._hl_pen_bg.setCosmetic(True)
        self._hl_width_fg:int = 1
        self._hl_pen_fg = QPen(Qt.GlobalColor.white)
        self._hl_pen_fg.setWidth(self._hl_width_fg)
        self._hl_pen_fg.setCosmetic(True)


        #self._mouse_hover_ms = 20 #  50 FPS
        #self._mouse_hover_last_pos:QPoint | None = None

        # --- --- --- Input Mapping --- --- ---
        self.bind_mouse(MouseKey(Qt.MouseButton.MiddleButton, Qt.KeyboardModifier.NoModifier), self._pan_handler)
        self.bind_wheel(WheelKey(WheelAxis.Vert, +1, Qt.KeyboardModifier.NoModifier), self._zoom_handler)
        self.bind_wheel(WheelKey(WheelAxis.Vert, -1, Qt.KeyboardModifier.NoModifier), self._zoom_handler)
    # End of def __init__

    
    # --- --- --- Zoom Management --- --- ---

    @Slot(ZoomInfo)
    def zoom_set(self, zi:ZoomInfo)->None:
        s = zi.wanted_level / 100.0
        self.setTransform(QTransform().scale(s, s))
        self._zoom_state.set(zi)
        self._new_transform = True
    # End of def zoom_set_scale


    @Slot(ZoomInfo, object) # QPoint|None
    def zoom_to_anchor(self, zi:ZoomInfo, anchor_view_position: QPoint|None)->None:
        if anchor_view_position is None:
            self.zoom_set(zi)
        else:
            # Cursor position in viewport -> scene
            v0 = anchor_view_position
            s0 = self.mapToScene(v0)
            # Zoom
            self.zoom_set(zi)
            # Calculate drift for position in scene after zoom
            v1 = self.mapFromScene(s0)
            delta = v1 - v0
            # Adjust scrollbars to keep the cursor position under the mouse
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() + delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() + delta.y())
        #
    # End of def zoom_at


    # --- --- --- Highlight management --- --- ---

    def _hl_map_rect_from_scene(self, scene_rect:QRectF) -> QRect:
        top_left = self.mapFromScene(scene_rect.topLeft())
        bottom_right = self.mapFromScene(scene_rect.bottomRight())
        return QRect(top_left, bottom_right).normalized()


    def _hl_process_move(self):
        new_position = self._pending_mouse_pos
        if new_position is None:
            return
        
        # Reset pending
        self._pending_mouse_pos = None

        # Old rectangle must be repainted
        dirty_rect = self._hl_view_rect

        # New info
        new_scene_pos = self.mapToScene(new_position.toPoint())
        if not self.sceneRect().contains(new_scene_pos):
            self._hl_scene_pos = None
            self._hl_view_rect = None
        else:
            self._hl_scene_pos = QPoint(int(new_scene_pos.x()), int(new_scene_pos.y()))
            self._hl_view_rect = self._hl_map_rect_from_scene(QRectF(self._hl_scene_pos, QSize(1, 1)))

        # Dirty rect made of the old and new highlight rectangles
        if dirty_rect is None:
            dirty_rect = self._hl_view_rect
        elif self._hl_view_rect is not None:
            dirty_rect = dirty_rect.united(self._hl_view_rect)

        # Request repaint
        if self._new_transform:
            self.viewport().update()
            self._new_transform = False
        elif dirty_rect is not None:
            # Expand dirty rect to account for pen width
            expand_by = self._hl_width_bg
            dirty_rect = dirty_rect.adjusted(-expand_by, -expand_by, expand_by, expand_by)
            self.viewport().update(dirty_rect)

        # Signal
        sp = self._hl_scene_pos
        self.mouse_position.emit( (sp.x(), sp.y()) if sp is not None else None)


    def _hl_draw(self, painter:QPainter)->None:
        if self._hl_scene_pos is not None:
            scene_rect = QRectF(self._hl_scene_pos, QSize(1, 1))
            painter.save()
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(self._hl_pen_bg)
            painter.drawRect(scene_rect)
            painter.setPen(self._hl_pen_fg)
            painter.drawRect(scene_rect)
            painter.restore()


    # --- --- --- Custom behaviour --- --- ---

    def drawForeground(self, painter:QPainter, rect:QRectF | QRect):
        super().drawForeground(painter, rect)
        self._hl_draw(painter)


    def setScene(self, scene: AnnotatorScene | None) -> None:
        super().setScene(scene)
        self._zoom_state.set(ZoomInfo.default())
        if scene is not None:
            self._zoom_state.compute_fit_level_for_view(self)
            self._zoom_state.set_want_to_fit(True)
            self.zoom_set(self._zoom_state.info())
        #
    # End of def setScene


    def mouseMoveEvent(self, ev: QMouseEvent) -> None:
        if not self._hl_update_timer.isActive():
            self._hl_update_timer.start()
        self._pending_mouse_pos = ev.position()
        # --- Mixin behaviour
        super().mouseMoveEvent(ev)
    # End of def mouseMoveEvent


    def mousePressEvent(self, ev: QMouseEvent) -> None:
        is_handled = False
        # Custom behaviour here
        #match ev.button():
        #    case Qt.MouseButton.LeftButton: pass
        #    case Qt.MouseButton.RightButton: pass
        #    case _: pass
        ## End of match
        if is_handled: ev.accept()
        # Mixin behaviour if not handled
        else: super().mousePressEvent(ev)
    # End of def mousePressEvent

    
    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._zoom_state.compute_fit_level_for_view(self)
        if self._zoom_state.info().want_to_fit:
            self.zoom_set(self._zoom_state.info())
    # End of def resizeEvent


    

    # --- --- --- Connection helpers --- --- ---

    def connect_zoom_changed(self, slot: Callable[[ZoomInfo], None]) -> None:
        """Connect a slot to receive zoom change updates from the view. Init with current zoom info."""
        self.zoom_changed.connect(slot)
        slot(self._zoom_state.info())
