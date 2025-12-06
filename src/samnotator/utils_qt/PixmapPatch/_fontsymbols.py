# --- --- --- Imports --- --- ---
# STD
# 3RD
from PySide6.QtCore import Qt, QRect
from PySide6.QtGui import QPainter, QFont, QPixmap, QColor, QFontMetricsF
# Project


class PatchFontSymbolRenderer:
    """Utility class able to render a list of single-character symbols into QPixmaps with consistent sizing across symbols."""

    # --- --- --- Constructor --- --- ---

    def __init__(self, symbols:list[str], colour:QColor, font:QFont|None=None):
        if any(len(s) != 1 for s in symbols):
            raise ValueError("SymbolRenderer only supports single-character symbols.")
        self._symbols = symbols
        self._colour = colour
        self._font = font
    #

    # --- --- --- Public Helpers --- --- ---

    @staticmethod
    def get_symbols_sizes(symbols:list[str], target_size_px:int, font:QFont|None=None) -> list[int]:
        # Prepare font
        if font is None: font = QFont()
        else: font = QFont(font)  # make a copy
        font.setPixelSize(max(1, target_size_px))
        fm = QFontMetricsF(font)

        results:list[int] = []
        for symbol in symbols:
            rect = fm.tightBoundingRect(symbol)
            if (w:=rect.width()) > 0 and (h:=rect.height()) > 0:
                scale_w = target_size_px/w
                scale_h = target_size_px/h
                scale = min(scale_w, scale_h)
            else:
                scale = 1.0
            #
            final_size_px = max(1, int(target_size_px * scale))
            results.append(final_size_px)
        #

        return results
    # End of staticmethod def _get_symbols_sizes

    
    @staticmethod
    def render_symbols(symbols:list[str], pixmap_size_px:int, symbol_size_px:int, color:QColor, font:QFont|None=None) -> list[QPixmap]:
        # Prepare font
        if font is None: font = QFont()
        else: font = QFont(font)  # make a copy
        font.setPixelSize(max(1, symbol_size_px))

        # Painter:
        p = QPainter()
        draw_rect = QRect(0, 0, pixmap_size_px, pixmap_size_px)

        # Result list:
        pixmaps:list[QPixmap] = []

        for symbol in symbols:
            # Get a pixmap
            pix = QPixmap(pixmap_size_px, pixmap_size_px)
            pix.fill(Qt.GlobalColor.transparent)
            # Setup painter: whole state does reset at begin()
            p.begin(pix)
            p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing)
            p.setPen(color)
            p.setFont(font)
            # Draw the text centered (both H and V) within the rectangle.
            p.drawText(draw_rect, Qt.AlignmentFlag.AlignCenter, symbol)
            p.end()
            # Store result
            pixmaps.append(pix)
        #
        
        return pixmaps
    # End of staticmethod def render_symbols


    # --- --- --- Public methods --- --- ---

    def get(self, pixmap_size_px:int, symbol_size_px:int)->tuple[int, list[QPixmap]]:
        """Return symbol size used and list of QPixmaps. Also return the actually used symbol size."""
        # Special case for size 0
        if pixmap_size_px == 0:
            return (pixmap_size_px, [QPixmap()] * len(self._symbols))

        # Adjust size based on symbols, so that all symbols fit, at least 1px
        smb_size_px = max(1, min(PatchFontSymbolRenderer.get_symbols_sizes(self._symbols, symbol_size_px, self._font)))

        # Create pixmaps
        pixmaps = PatchFontSymbolRenderer.render_symbols(self._symbols, pixmap_size_px, smb_size_px, self._colour, self._font)
        return (smb_size_px, pixmaps)
    # End of def get
# End of class SymbolRenderer
