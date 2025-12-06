# --- --- --- Imports --- --- ---
# STD
from enum import Enum, auto
from typing import Protocol, runtime_checkable, Mapping, Final
from dataclasses import dataclass
# 3RD
# --- PySide6
from PySide6.QtCore import Qt
from PySide6.QtGui import QMouseEvent, QWheelEvent, QKeyEvent, QEnterEvent, QFocusEvent, QResizeEvent
from PySide6.QtWidgets import QWidget
# Project



# --- --- --- Protocols and types --- --- ---

@runtime_checkable
class MouseGesture[W:QWidget](Protocol):
    """3-phase drag-style interaction.
    
       A concrete class implements `start -> update -> finish` and is passed to `bind_mouse()`.
       * `start()`   called on MouseButtonPress;  return **True** to mark the press as _handled_ and activate the gesture.
       * `update()`  called on every subsequent MouseMove while the gesture is active.
       * `finish()`  called on MouseButtonRelease, `leaveEvent`, `focusOutEvent`, or `Esc` if the drag is aborted.
    """

    def start(self, view:W, ev:QMouseEvent) -> bool:
        """Initial press; return True to accept the event and activate. False to let it propagate."""
        ...
    # End of def start

    def update(self, view:W, ev:QMouseEvent) -> None:
        """Called for each move while the gesture remains active."""
        ...
    # End of def update

    def finish(self, view:W, ev:QMouseEvent) -> None:
        """Cleanup when the drag ends or is cancelled."""
        ...
    # End of def finish
# End of class MouseGesture


@runtime_checkable
class MouseButtonHandler[W:QWidget](Protocol):
    """Handler for a single click (MouseButtonPress), not holding, event."""

    def __call__(self, view:W, ev:QMouseEvent) -> bool:
        """Return True to accept the event, False to let it propagate."""
        ...
    # 
# End of class MouseButtonHandler


type MouseHandler = MouseGesture | MouseButtonHandler
"""A handler for a mouse button event, either a gesture or a simple click handler."""


@runtime_checkable
class MouseDblHandler[W:QWidget](Protocol):
    """Handler for a *double-click* (MouseButtonDblClick) event."""

    def __call__(self, view:W, ev:QMouseEvent) -> bool:
        """Return True to accept the event, False to let it propagate."""
        ...
    # 
# End of class MouseDblHandler


@runtime_checkable
class WheelHandler[W:QWidget](Protocol):
    """Handles the wheel with direction +1/-1 (delta in the event) for an axis, with a specific modifier set (for zoom in/out, rotate canvas, horizontal scroll, etc...)."""

    def __call__(self, view:W, ev:QWheelEvent) -> bool:
        """Return True to accept the event, False to let it propagate."""
        ...
    #
# End of class WheelHandler


@runtime_checkable
class KeyHandler[W:QWidget](Protocol):
    """Handles a key-press or key-release matched by `bind_key()`."""

    def __call__(self, view:W, ev:QKeyEvent) -> bool:
        """Return True to accept the event, False to let it propagate."""
        ...
    #
# End of class KeyHandler


@runtime_checkable
class HoverHandler[W:QWidget](Protocol):
    """Processes enter / leave / hover-move events. Bind with `bind_hover(QEvent.Enter/Leave/HoverMove, handler)`."""

    def __call__(self, view:W, ev:QEnterEvent) -> bool:
        """Return True to accept the event, False to let it propagate."""
        ...
    #
# End of class HoverHandler


@runtime_checkable
class FocusHandler[W:QWidget](Protocol):
    """Responds to focus-in or focus-out. Use `bind_focus(QEvent.FocusIn/FocusOut, handler)`."""

    def __call__(self, view:W, ev:QFocusEvent) -> bool:
        """Return True to accept the event, False to let it propagate."""
        ...
    #
# End of class FocusHandler


@runtime_checkable
class ResizeHandler[W:QWidget](Protocol):
    """Notified after the widget has changed size. Registered via `bind_resize(handler)`. Resize events are always accepted."""
    def __call__(self, view:W, ev:QResizeEvent) -> None:
        ...
    #
# End of class ResizeHandler



# --- --- --- Mouse lookup definition --- --- ---

class _AnyBtn:
    """Type for ANY_MOUSE_BTN Sentinel."""
    __slots__ = ()
# End of class _AnyBtn


ANY_MOUSE_BTN: Final = _AnyBtn()
"""Sentinel for 'any mouse button' in mouse key tuples."""


type MouseButtonLike = Qt.MouseButton | _AnyBtn
"""Mouse button or sentinel for 'any mouse button' in mouse key tuples."""


@dataclass(frozen=True, slots=True)
class MouseKey:
    """Mouse binding key."""
    button: MouseButtonLike
    modifier: Qt.KeyboardModifier

    # --- --- --- Constructors and methods --- --- ---

    @classmethod
    def from_event(cls, ev: QMouseEvent) -> 'MouseKey':
        return MouseKey(ev.button(), ev.modifiers())
    #

    def lookup[T](self, table: Mapping['MouseKey', T], wildcard: _AnyBtn = ANY_MOUSE_BTN) -> T | None:
        """Lookup (button, modifier), then (any button, modifier) if not found."""
        return ( table.get(self) or table.get(MouseKey(wildcard, self.modifier)))
    #
# End of class MouseKey



# --- --- --- Keyboard keys lookup definition --- --- ---

class _AnyKey:
    """Type for ANY_KEY Sentinel."""
    __slots__ = ()
# End of class _AnyKey


ANY_KEY: Final = _AnyKey()
"""Sentinel for 'any key' in keyboard key tuples."""


type KeyLike = Qt.Key | _AnyKey
"""Key or sentinel for 'any key' in keyboard key tuples."""


@dataclass(frozen=True, slots=True)
class KeyKey:
    """Keyboard binding key."""
    button: KeyLike
    modifier: Qt.KeyboardModifier

    # --- --- --- Constructors and methods --- --- ---
    
    @classmethod
    def from_event(cls, ev: QKeyEvent) -> 'KeyKey':
        return KeyKey(Qt.Key(ev.key()), ev.modifiers())
    #

    def lookup(self, table: Mapping['KeyKey', KeyHandler], wildcard: _AnyKey = ANY_KEY) -> KeyHandler | None:
        """Lookup (key, modifier), then (any key, modifier) if not found."""
        return ( table.get(self) or table.get(KeyKey(wildcard, self.modifier)))
    #
# End of class KeyKey


# --- --- --- Mouse Wheel --- --- ---

class WheelAxis(Enum):
    """Physical scroll axis of the wheel/tilt sensor."""
    Vert = auto()      # vertical wheel
    Horz = auto()      # horizontal or tilt wheel
# End fo class WheelAxis


@dataclass(frozen=True, slots=True)
class WheelKey:
    """Wheel binding key."""
    axis: WheelAxis
    direction: int          # +1 or -1, scroll away/right or toward/left (this is a key, so no delta here)
    modifier: Qt.KeyboardModifier

    # --- --- --- Constructors and methods --- --- ---
    @classmethod
    def from_event(cls, ev: QWheelEvent) -> 'WheelKey':
        """ Returns WheelKey tuple (axis, +1 / -1, modifiers). Horizontal wheel counts too.
        
            axis +1 scroll away/right
            axis -1 scroll toward / left
            Axis is chosen by the delta component with the greater magnitude, falls back to vertical if equal.
        """
        d = ev.angleDelta()
        axis = WheelAxis.Vert if abs(d.y()) >= abs(d.x()) else WheelAxis.Horz
        delta_val = d.y() if axis is WheelAxis.Vert else d.x()
        direction = +1 if delta_val > 0 else -1
        return WheelKey(axis, direction, ev.modifiers())
    # End of def wheel_key
# End of class WheelKey