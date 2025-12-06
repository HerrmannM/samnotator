# --- --- --- Imports --- --- ---
# STD
from typing import Literal, Generator
from contextlib import contextmanager
# 3RD
from PySide6.QtCore import QPointF, Qt, QRectF
from PySide6.QtGui import QPainter, QPixmap, QColor, QBrush
# Project



class PatchBackgroundRenderer:
    """Utility class used to render background circles for symbols."""

    def __init__(self, main:QColor, border:QColor, ratio:float=0.9, aa_margin:int=1, type:Literal['circle']='circle'):
        self.border_color = border
        self.main_color = main
        self._ratio = ratio
        self._aa_margin = aa_margin
        self._type = type
        self.brush = QBrush(Qt.BrushStyle.SolidPattern)
    #

    # --- --- --- Common helper --- --- ---

    @staticmethod
    @contextmanager
    def _prepare(pixmap_size_px: int) -> Generator[tuple[QPointF, QPixmap, QPainter]]:
        center = QPointF(pixmap_size_px * 0.5, pixmap_size_px * 0.5)
        #
        pix = QPixmap(pixmap_size_px, pixmap_size_px)
        pix.fill(Qt.GlobalColor.transparent)
        #
        p = QPainter(pix)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)

        try:
            yield center, pix, p
        finally:
            p.end()
    # End of staticmethod contextmanager def _prepare

    def _get_patch_info(self, pixmap_size:int, fg_fraction:float, aa_margin:int)->list[tuple[float, QColor]]:
        """Compute borde size to main size, and create a list of size, colours. Account for anti-aliasing margin if any."""
        border_patch:float = max(0.0, (pixmap_size / 2.0) - aa_margin)
        main_patch:float = border_patch * fg_fraction
        return [(border_patch, self.border_color), (main_patch, self.main_color)]
    # End of staticmethod def get_radii
    

    # --- --- --- Circle helper --- --- ---

    @staticmethod
    def render_circle(pixmap_size_px:int, radii_colors:list[tuple[float, QColor]], brush:QBrush) -> QPixmap:
        with PatchBackgroundRenderer._prepare(pixmap_size_px) as (center, pix, p):
            for radius, color in radii_colors:
                brush.setColor(color)
                p.setBrush(brush)
                p.drawEllipse(center, radius, radius)
            #
        return pix
    # End of staticmethod def render_circle


    # --- --- --- Square helper --- --- ---
    
    @staticmethod
    def render_square(pixmap_size_px: int, halfsizes_colors: list[tuple[float, QColor]], brush:QBrush) -> QPixmap:
        with PatchBackgroundRenderer._prepare(pixmap_size_px) as (center, pix, p):
            cx, cy = center.x(), center.y()
            for half_size, color in halfsizes_colors:
                # half_size = half of the square side length
                left, top = cx - half_size, cy - half_size
                length = half_size * 2.0
                #
                brush.setColor(color)
                p.setBrush(brush)
                p.drawRect(QRectF(left, top, length, length))
            #
        return pix
    # End of staticmethod def render_square


    # --- --- --- Public methods --- --- ---

    def get(self, pixmap_size:int)->QPixmap:
        pi = self._get_patch_info(pixmap_size, self._ratio, self._aa_margin)
        if self._type == "circle":
            return PatchBackgroundRenderer.render_circle(pixmap_size, pi, self.brush)
        elif self._type == "square":
            return PatchBackgroundRenderer.render_square(pixmap_size, pi, self.brush)
        else:
            raise ValueError(f"Unsupported background type: {self._type}")
    # End of def get
# End of class BackgroundRenderer

