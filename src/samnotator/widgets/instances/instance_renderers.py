"""Positive/Negative Markers QGraphicsItems."""
# --- --- --- Imports --- --- ---
# STD
from enum import StrEnum
from typing import cast
# 3RD
import cv2
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPainter, QPixmap, QColor
import numpy as np
from numpy.typing import NDArray
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



class MaskMode(StrEnum):
    PLAIN = "plain"
    SOLID_TRANSPARENT = "solid_transparent"
    SOLID_CONTRAST = "solid_contrast"
    SOLID_BLACK = "solid_black"
    BW = "bw"
    FANCY = "fancy"
# End of class MaskMode


UInt8Array = NDArray[np.uint8]

class MaskRenderer:
    """Utility class used to render a mask"""

    def __init__(self, main_colour:QColor, contrast_colour:QColor, shape_size_ratio:float=0.9, opacity:float=0.5):
        self._main_colour = main_colour
        self._contrast_colour = contrast_colour
        self._shape_size_ratio = shape_size_ratio # Currently unused but retained
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


    def get(self, mask:MaskHW, mode:MaskMode) -> QPixmap|None:
        """
        Render a boolean HxW mask as a QPixmap based on the specified mode.
        :param mask: The 2D boolean mask.
        :param mode: The rendering style ('plain', 'solid_main', 'bw', 'fancy').
        """
        if mask.ndim != 2:
            raise ValueError("mask must be 2D (H, W) boolean")
        if not np.any(mask): # completely empty mask -> None
            return None

        match mode:
            case MaskMode.PLAIN: return MaskRenderer.mask_plain_pixmap(mask, self._main_colour, self._opacity)
            case MaskMode.SOLID_TRANSPARENT: return MaskRenderer.mask_plain_pixmap(mask, self._main_colour, 1.0)
            case MaskMode.SOLID_CONTRAST: return MaskRenderer.mask_plain_pixmap(mask, self._main_colour, 1.0, self._contrast_colour, 1.0)
            case MaskMode.SOLID_BLACK: return MaskRenderer.mask_plain_pixmap(mask,  self._main_colour, 1.0, QColor(0, 0, 0), 1.0)
            case MaskMode.BW: return MaskRenderer.mask_plain_pixmap(mask, QColor(255, 255, 255), 1.0, QColor(0, 0, 0, 0), 1.0)
            case MaskMode.FANCY: return MaskRenderer.mask_fancy_pixmap(mask, self._main_colour, self._contrast_colour, self._opacity)
            case _: raise ValueError(f"Unknown rendering mode: {mode_}")
    # End of def get 


    # --- --- --- Static Rendering Helpers --- --- ---
    
    @staticmethod
    def _color_to_rgb(color: QColor|tuple[int, int, int]) -> tuple[int, int, int]:
        """Internal helper to extract RGB from QColor or tuple."""
        if isinstance(color, QColor):
            return color.red(), color.green(), color.blue()
        return color

    @staticmethod
    def _arr_to_pixmap(rgba_arr: np.ndarray) -> QPixmap:
        """Internal helper to convert RGBA array to QPixmap."""
        h, w, _ = rgba_arr.shape
        # Ensure the array is C-contiguous for QImage to read it correctly
        img = QImage(rgba_arr.tobytes(), w, h, 4 * w, QImage.Format.Format_RGBA8888)
        return QPixmap.fromImage(img)


    @staticmethod
    def mask_plain_pixmap(mask: np.ndarray, mask_colour: QColor|tuple[int, int, int], mask_opacity: float, background_colour: QColor|tuple[int, int, int]=(0,0,0), background_opacity: float=0.0) -> QPixmap:
        """ Renders a mask as a single solid/semi-transparent colour QPixmap, with a controlled background color and opacity.
            Opacity values are clamped between 0.0 (transparent) and 1.0 (opaque).
            By default, the background is black fully transparent.
        """
        mask_arr = np.asarray(mask)
        if mask_arr.dtype != np.bool_:
            raise TypeError("mask must be boolean")
        h, w = mask_arr.shape
        rgba: UInt8Array = np.zeros((h, w, 4), dtype=np.uint8)

        # Set background colour where mask is False
        bg_r, bg_g, bg_b = MaskRenderer._color_to_rgb(background_colour)
        bg_alpha = int(max(0.0, min(1.0, background_opacity)) * 255)
        background_area = ~mask_arr
        rgba[background_area] = (bg_r, bg_g, bg_b, bg_alpha)

        # Set mask colour where mask is True
        r, g, b = MaskRenderer._color_to_rgb(mask_colour)
        alpha = int(max(0.0, min(1.0, mask_opacity)) * 255)
        rgba[mask_arr] = (r, g, b, alpha)

        return MaskRenderer._arr_to_pixmap(rgba)
    # End of staticmethod def mask_plain_pixmap


    @staticmethod
    def mask_fancy_pixmap(mask: np.ndarray, main_color: QColor, contrast_color: QColor, opacity: float) -> QPixmap:
        """Renders a mask with 3 solid borders and a semi-transparent fill inside, all strictly contained within the original mask boundary."""
        if mask.dtype != np.bool_:
            raise TypeError("mask must be boolean")
        
        # 1) Prepare colors and initial array
        main_r, main_g, main_b = MaskRenderer._color_to_rgb(main_color)
        contrast_r, contrast_g, contrast_b = MaskRenderer._color_to_rgb(contrast_color)
        alpha_fill = int(max(0.0, min(1.0, opacity)) * 255)

        h, w = mask.shape
        rgba = np.zeros((h, w, 4), dtype=np.uint8) # Fully transparent initial
        
        # Convert mask to uint8 (0 or 255) for OpenCV morphology
        mask_u8:UInt8Array = mask.astype(np.uint8) * 255
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        
        # 2) Perform sequential erosions
        M0 = mask_u8                                # Original Mask
        M1 = cast(UInt8Array, cv2.erode(M0, kernel, iterations=1))    # 1px eroded
        M2 = cast(UInt8Array, cv2.erode(M1, kernel, iterations=1))    # 2px eroded
        M3 = cast(UInt8Array, cv2.erode(M2, kernel, iterations=1))    # 3px eroded

        # 3) Define the four distinct regions (borders and interior)
        # Border 1 (Outer): M0 \ M1 --> Contrast Color (Solid)
        border_1 = (M0 == 255) & (M0 != M1)
        rgba[border_1] = (contrast_r, contrast_g, contrast_b, 255)
        
        # Border 2 (Middle): M1 \ M2 --> Main Color (Solid)
        border_2 = (M1 == 255) & (M1 != M2)
        rgba[border_2] = (main_r, main_g, main_b, 255)
        
        # Border 3 (Inner): M2 \ M3 --> Contrast Color (Solid)
        border_3 = (M2 == 255) & (M2 != M3)
        rgba[border_3] = (contrast_r, contrast_g, contrast_b, 255)
        
        # Interior Fill: M3 --> Main Color (Semi-transparent)
        interior_fill = (M3 == 255)
        rgba[interior_fill] = (main_r, main_g, main_b, alpha_fill)
        
        # 4. Convert to QPixmap
        return MaskRenderer._arr_to_pixmap(rgba)
    # End of staticmethod def mask_fancy_pixmap
# End of class MaskRenderer