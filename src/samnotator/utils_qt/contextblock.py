# --- --- --- Imports --- --- ---
# STD
from collections.abc import Iterator
from contextlib import contextmanager
# 3RD
from PySide6.QtCore import QObject
from PySide6.QtGui import QPainter


@contextmanager
def block_signals(*qobjects:QObject) -> Iterator[None]:
    for obj in qobjects:
        obj.blockSignals(True)
    try:
        yield
    finally:
        for obj in qobjects:
            obj.blockSignals(False)
# End of def block_signals


@contextmanager
def save_painter(painter:QPainter) -> Iterator[QPainter]:
    painter.save()
    try:
        yield painter
    finally:
        painter.restore()
# End of def save_painter
