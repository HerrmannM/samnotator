"""Positive/Negative Markers QGraphicsItems."""
# --- --- --- Imports --- --- ---
# STD
# 3RD
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPainter, QPixmap, QColor
import numpy as np
# Project
from samnotator.utils_qt.PixmapPatch import PatchBackgroundRenderer, PatchFontSymbolRenderer
from samnotator.datamodel import MaskHW





class MarkRenderer:
    """Utility class used to render marker symbols with backgrounds"""

    def __init__(self, symbols:list[str], main_colour:QColor, contrast_colour:QColor, shape_size_ratio:float=0.9, symbol_size_ratio:float=0.85, aa_margin:int=1):
        self._symbols = symbols
        self._main_colour = main_colour
        self._contrast_colour = contrast_colour
        self._shape_size_ratio = shape_size_ratio
        self._symbol_size_ratio = symbol_size_ratio
        self._aa_margin = aa_margin
        # Init renderers
        self._symbol_renderer = PatchFontSymbolRenderer(self._symbols, self._contrast_colour)
        self._background_renderer = PatchBackgroundRenderer(self._main_colour, self._contrast_colour, self._shape_size_ratio, self._aa_margin)
    #


    # --- --- --- Public helpers --- --- ---

    @staticmethod
    def get_adjusted_size(size_px:int) -> int:
        """ Ensure that size_px is odd (adjust by -1 if even) or 0 """
        if size_px < 1:
            return 0
        elif size_px % 2 == 0:
            return size_px - 1
        else:
            return size_px
    # End of staticmethod def get_adjusted_size


    # --- --- --- Public methods --- --- ---

    def set_colors(self, *, main:QColor|None=None, contrast:QColor|None=None, ):
        if main is not None:
            self._main_colour = main
        if contrast is not None:
            self._contrast_colour = contrast
        #
        self._symbol_renderer = PatchFontSymbolRenderer(self._symbols, self._contrast_colour)
        self._background_renderer = PatchBackgroundRenderer(self._main_colour, self._contrast_colour, self._shape_size_ratio, self._aa_margin)
    # End of def set_colors


    def get(self, pixmap_size_px:int) -> list[QPixmap]:

        # Adjust sizing
        pixmap_size_px = MarkRenderer.get_adjusted_size(pixmap_size_px)
        if pixmap_size_px == 0:
            return [QPixmap()] * len(self._symbols)

        # Target size
        symbol_size_px = max(1, int(pixmap_size_px * self._symbol_size_ratio))

        # Get symbol pixmaps
        smb_size, symbol_pixmaps = self._symbol_renderer.get(pixmap_size_px, symbol_size_px)

        # Get background pixmap
        background_pixmap = self._background_renderer.get(pixmap_size_px)

        # Compose final pixmaps
        final_pixmaps = []
        for symbol_pixmap in symbol_pixmaps:
            final_pixmap = QPixmap(pixmap_size_px, pixmap_size_px)
            final_pixmap.fill(Qt.GlobalColor.transparent)
            p = QPainter(final_pixmap)
            p.drawPixmap(0, 0, background_pixmap)
            p.drawPixmap(0, 0, symbol_pixmap)
            p.end()
            final_pixmaps.append(final_pixmap)

        return final_pixmaps
    # End of def get
# End of class MarkerRenderer






class MaskRenderer:
    """Utility class used to render a mask"""

    def __init__(self, main_colour:QColor, contrast_colour:QColor, shape_size_ratio:float=0.9, opacity:float=0.5):
        self._main_colour = main_colour
        self._contrast_colour = contrast_colour
        self._shape_size_ratio = shape_size_ratio
        self._opacity = opacity
    #


    # --- --- --- Public methods --- --- ---

    def set_colors(self, *, main:QColor|None=None, contrast:QColor|None=None, opacity:float|None=None):
        if main is not None:
            self._main_colour = main
        if contrast is not None:
            self._contrast_colour = contrast
        if opacity is not None:
            self._opacity = opacity
    # End of def set_colors


    def get(self, mask:MaskHW, plain_mask:bool) -> QPixmap|None:
        """
        Render a boolean HxW mask as a QPixmap.
        """
        if mask.ndim != 2:
            raise ValueError("mask must be 2D (H, W) boolean")
        if not np.any(mask): # completely empty mask -> None
            return None

        return MaskRenderer.mask_plain_pixmap(mask, self._main_colour, self._opacity)
    # End of def get 
    
    
    @staticmethod
    def mask_plain_pixmap(mask: np.ndarray, color: QColor|tuple[int, int, int], opacity: float) -> QPixmap:
        mask_arr = np.asarray(mask)
        if mask_arr.dtype != np.bool_:
            raise TypeError("mask must be boolean")
        if mask_arr.ndim != 2:
            raise ValueError("mask must be 2D")

        if isinstance(color, QColor):
            r, g, b = color.red(), color.green(), color.blue()
        else:
            r, g, b = color

        h, w = mask_arr.shape
        rgba = np.zeros((h, w, 4), dtype=np.uint8)          # Initialize transparent RGBA array -> 0 means transparent
        alpha = int(max(0.0, min(1.0, opacity)) * 255)
        rgba[mask_arr] = (r, g, b, alpha)

        img = QImage(rgba.data, w, h, 4 * w, QImage.Format.Format_RGBA8888)
        return QPixmap.fromImage(img)
    # End of staticmethod def mask_plain_pixmap   
    
    
    
    
# End of class MaskRenderer