# --- --- --- Imports --- --- ---
# STD
from typing import cast
# 3RD
from coloraide import Color
from PySide6.QtGui import QColor
# 


def pick_contrast_colour(bg: QColor, threshold: float=0.6) -> QColor:
    """Choose black/white text based on OKLab lightness (L in 0-1). Return black if bg is light enough (above threshold), else white."""
    r, g, b, _ = cast(tuple[float, float, float, float], bg.getRgbF())
    L = Color("srgb", [r, g, b]).convert("oklab").coords()[0]  # 0..1
    return QColor("black") if L > threshold else QColor("white")
# End of def pick_contrast_color


def qcolor_from_coloraide(c: Color) -> QColor:
    # Ensure we’re in sRGB gamut and get floats in 0..1
    c2 = c.fit("srgb").convert("srgb")
    r, g, b = (float(x) for x in c2.coords())
    # Clamp to [0..1]
    r = min(max(r, 0.0), 1.0)
    g = min(max(g, 0.0), 1.0)
    b = min(max(b, 0.0), 1.0)
    return QColor.fromRgbF(r, g, b, 1.0)
# End of def _qcolor_from_coloraide


def golden_oklch(index: int) -> QColor:
    """
    Deterministic colour generation in OKLCH using a golden-ratio walk.
    Two lightness bands (dark / light), with chroma auto-fitted to sRGB.
    """
    PHI = 0.618033988749895
    base = (1+index) * PHI

    # We multiply base by different constants to decorrelate L, C, h
    base_L = 5*base
    base_C = 7*base

    # Hue walk (degrees)
    h = (133*base) % 360.0

    # Lightness bands (OKLab L: 0..1)
    if index % 2 == 1:
        # dark: ~[0.45, 0.55]
        span = 0.1
        L = 0.45 + base_L % span
    else:
        # light: ~[0.75, 0.90]
        span = 0.15
        L = 0.75 + base_L % span

    # Whroma band for sRGB usually safe 0.10–0.20 for many (L, h).
    c_span = 0.10
    C0 = 0.10 + base_C % c_span
    col = Color("oklch", [L, C0, h])

    return qcolor_from_coloraide(col)
# End of def golden_oklch



class ColourGenerator:

    def __init__(self) -> None:
        self._colour_sequence: int = 0
    #

    def next(self, used_colours:set[str]|None=None) -> QColor:
        c = golden_oklch(self._colour_sequence)
        # Ensure colour is not already used
        if used_colours is not None:
            while c.name() in used_colours:
                self._colour_sequence += 1
                c = golden_oklch(self._colour_sequence)
        #
        self._colour_sequence += 1
        return c
    #

    def from_str(self, colour_str: str | None, used_colours:set[str]|None=None) -> QColor:
        """Get a colour from a string, or generate a new one if invalid/None."""
        c = None
        if colour_str is not None:
            qc = QColor(colour_str)
            c = qc if qc.isValid() else None
        if c is None:
            return self.next(used_colours=used_colours)
        return c
    #
# End of class ColourGenerator


