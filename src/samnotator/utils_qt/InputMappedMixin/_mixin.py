# --- --- --- Imports --- --- ---
# STD
from typing import Mapping, Any
from typing import TYPE_CHECKING
# 3RD
# --- PySide6
from PySide6.QtCore import Qt, QEvent
from PySide6.QtGui import QMouseEvent, QWheelEvent, QKeyEvent, QEnterEvent, QFocusEvent, QResizeEvent
from PySide6.QtWidgets import QWidget
# Project
from ._basis import *


# --- --- --- Core dispatcher class --- --- ---

if TYPE_CHECKING:
    BaseForMixin = QWidget        # For static type checker
else:
    BaseForMixin = object         # For real runtime MRO


class InputMappedMixin(BaseForMixin):
    """Drop-in widget with table-driven input mapping."""

    # --- --- --- Subclassing checks --- --- ---

    def __init_subclass__(cls, **kwargs):
        """Ensure that we are mixed into a QWidget subclass and that QWidget appears after this mixin in the Method Resolution Order (MRO)."""
        super().__init_subclass__(**kwargs)

        # 1) Must be used together with QWidget (or subclass)
        if not issubclass(cls, QWidget):
            raise TypeError( f"{cls.__name__}: InputMappedMixin must be mixed into a QWidget subclass")

        # 2) QWidget must appear after the mixin in the MRO
        mro = cls.mro()
        mixin_idx = mro.index(InputMappedMixin)

        if not any(issubclass(c, QWidget) for c in mro[mixin_idx + 1:]):
            raise TypeError( f"{cls.__name__}: QWidget (or subclass) must come after InputMappedMixin in the base class list")
        #
    #

    # --- --- --- Constructor --- --- ---

    def __init__(self, *a: Any, **kw: Any):
        super().__init__(*a, **kw)

        # Define all the input maps as empty dictionaries
        self._mouse_map: dict[MouseKey, MouseHandler] = {}
        self._mouse_dbl_map: dict[MouseKey, MouseDblHandler] = {}
        self._wheel_map: dict[WheelKey, WheelHandler] = {}
        self._key_map: dict[KeyKey, KeyHandler] = {}
        self._hover_map: dict[int, HoverHandler] = {}
        self._focus_map: dict[int, FocusHandler] = {}

        # Resize handlers are a list, as they are called in order
        self._resize_handlers:list[ResizeHandler] = []

        # Currently active gesture, if any
        self._active: MouseGesture | None = None
    # End of def __init__

    
    # --- --- --- Puiblic API --- --- ---

    def bind_mouse(self, key: MouseKey, handler: MouseHandler) -> None:
        self._mouse_map[key] = handler
    #
    
    def bind_mouse_many(self, mapping: Mapping[MouseKey, MouseHandler]) -> None:
        self._mouse_map.update(mapping)
    #
    
    def bind_mouse_dbl(self, key: MouseKey, handler: MouseDblHandler) -> None:
        self._mouse_dbl_map[key] = handler
    #
    
    def bind_wheel(self, key: WheelKey, handler: WheelHandler) -> None:
        self._wheel_map[key] = handler
    #
    
    def bind_wheel_many(self, mapping: Mapping[WheelKey, WheelHandler]) -> None:
        self._wheel_map.update(mapping)
    #
    
    def bind_key(self, key: KeyKey, handler: KeyHandler) -> None:
        self._key_map[key] = handler
    #
    
    def bind_key_many(self, mapping: Mapping[KeyKey, KeyHandler]) -> None:
        self._key_map.update(mapping)
    #
    
    def bind_hover(self, ev_type: int, handler: HoverHandler) -> None:
        self._hover_map[ev_type] = handler
    #
    
    def bind_focus(self, ev_type: int, handler: FocusHandler) -> None:
        self._focus_map[ev_type] = handler
    #
    
    def bind_resize(self, handler: ResizeHandler) -> None:
        self._resize_handlers.append(handler)
    #
    
    
    # --- --- --- Private Methods --- --- ---

    @staticmethod
    def _dummy_release(widget: QWidget) -> QMouseEvent:
        """Synthetic release when a drag is aborted without real event."""
        return QMouseEvent(
            QEvent.Type.MouseButtonRelease,
            widget.mapFromGlobal(widget.cursor().pos()),
            Qt.MouseButton.NoButton, Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
        )
    # End of def _dummy_release 

    def _finish_active(self, ev: QMouseEvent | None = None) -> None:
        """Finish the currently active gesture, if any."""
        if self._active:
            self._active.finish(self, ev or InputMappedMixin._dummy_release(self))
            self._active = None
        #
    # End of def _finish_active


    # --- --- --- Qt overrides  --- --- ---
    # Boilerplate once: overrides a bunch of Qt event handlers

    def mousePressEvent(self, ev: QMouseEvent) -> None:
        handler = MouseKey.from_event(ev).lookup(self._mouse_map)
        accepted = False
        if isinstance(handler, MouseGesture):
            accepted = handler.start(self, ev)
            if accepted:
                self._active = handler
        elif handler is not None:
            accepted = handler(self, ev)
        ev.accept() if accepted else super().mousePressEvent(ev)
    # End of def mousePressEvent

    def mouseMoveEvent(self, ev: QMouseEvent) -> None:
        if self._active:
            self._active.update(self, ev); ev.accept()
        else:
            super().mouseMoveEvent(ev)
    # End of def mouseMoveEvent

    def mouseReleaseEvent(self, ev: QMouseEvent) -> None:
        if self._active:
            self._active.finish(self, ev); self._active = None; ev.accept()
        else:
            super().mouseReleaseEvent(ev)
    # End of def mouseReleaseEvent

    def mouseDoubleClickEvent(self, ev: QMouseEvent) -> None:
        handler = MouseKey.from_event(ev).lookup(self._mouse_dbl_map)
        ev.accept() if handler and handler(self, ev) else super().mouseDoubleClickEvent(ev)
    # End of def mouseDoubleClickEvent

    def wheelEvent(self, ev: QWheelEvent) -> None:
        handler = self._wheel_map.get(WheelKey.from_event(ev))
        ev.accept() if handler and handler(self, ev) else super().wheelEvent(ev)
    # End of def wheelEvent

    def keyPressEvent(self, ev: QKeyEvent) -> None:
        if ev.key() == Qt.Key.Key_Escape:
            self._finish_active()
            ev.accept()
        else:
            handler = KeyKey.from_event(ev).lookup(self._key_map)
            ev.accept() if handler and handler(self, ev) else super().keyPressEvent(ev)
        #
    # End of def keyPressEvent

    def keyReleaseEvent(self, ev: QKeyEvent) -> None:
        handler = KeyKey.from_event(ev).lookup(self._key_map)
        ev.accept() if handler and handler(self, ev) else super().keyReleaseEvent(ev)
    # End of def keyReleaseEvent

    def enterEvent(self, ev: QEnterEvent) -> None:
        if (h := self._hover_map.get(QEvent.Type.Enter)) and h(self, ev):
            ev.accept()
        else:
            super().enterEvent(ev)
    # End of def enterEvent
    
    def leaveEvent(self, ev: QEvent) -> None:
        self._finish_active()
        if (h := self._hover_map.get(QEvent.Type.Leave)) and h(self, ev):
            ev.accept()
        else:
            super().leaveEvent(ev)
    # End of def leaveEvent
    
    def focusOutEvent(self, ev: QFocusEvent) -> None:
        self._finish_active()
        if (h := self._focus_map.get(QEvent.Type.FocusOut)) and h(self, ev):
            ev.accept()
        else:
            super().focusOutEvent(ev)
    # End of def focusOutEvent
    
    def focusInEvent(self, ev: QFocusEvent) -> None:
        if (h := self._focus_map.get(QEvent.Type.FocusIn)) and h(self, ev):
            ev.accept()
        else:
            super().focusInEvent(ev)
    # End of def focusInEvent
    
    def resizeEvent(self, ev: QResizeEvent) -> None:
        for h in self._resize_handlers:
            h(self, ev)
        super().resizeEvent(ev)
    # End of def resizeEvent
# End of class InputMappedWidget