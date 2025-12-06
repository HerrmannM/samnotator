"""Zoom levels controller, for use with an QGraphicsView displaying a QGraphicsScene."""
# --- --- --- Imports --- --- ---
# STD
from bisect import bisect_left
from dataclasses import dataclass, replace
# 3RD
from PySide6.QtCore import QObject, SignalInstance
from PySide6.QtWidgets import QGraphicsView

# --- --- --- Constants --- --- ---
# Zoom level in %
_ZOOM_LEVELS:list[int] = [5, 10, 15, 20, 25, 30, 40, 50, 60, 75, 80, 85, 90, 95, 100, 110, 125, 133, 150, 200, 300, 400, 600, 800, 1000, 1200, 1600, 3200, 6400, 12800, 25600, 51200, 102400, 128000]
_MIN_ZOOM_LEVEL:int = _ZOOM_LEVELS[0]
_MAX_ZOOM_LEVEL:int = _ZOOM_LEVELS[-1]
_DEFAULT_LEVEL:int = 100


# --- --- --- Dataclass ZoomInfo --- --- ---

@dataclass(frozen=True, slots=True)
class ZoomInfo:
    zoom_levels:list[int]
    current_index:int
    fit_index:int
    want_to_fit:bool

    @property
    def current_level(self)->int:
        return self.zoom_levels[self.current_index]
    #

    @property
    def fit_level(self)->int:
        return self.zoom_levels[self.fit_index]
    #

    @property
    def is_fit(self)->bool:
        return self.current_index == self.fit_index
    #

    @property
    def wanted_index(self)->int:
        if self.want_to_fit: return self.fit_index
        else: return self.current_index
    #

    @property
    def wanted_level(self)->int:
        return self.zoom_levels[self.wanted_index]
    #

    @classmethod
    def default(cls)->"ZoomInfo":
        return cls(zoom_levels=[_DEFAULT_LEVEL], current_index=0, fit_index=0, want_to_fit=False)
# End of dataclass ZoomInfo


class ViewZoomState(QObject):
    """
    A Zoom controller for a given QGraphicsView and 'zoom changed' signal to piggy back on.

    In essence, a view is its own zoom controller (its transform matrix is the ground truth).
    We use a provided zoom_changed signal instance to notify about zoom changes instead of building our own signal here:
    this is because this state will be part of a view which will want to expose its own zoom_changed signal.
    We may as well use it directly!
    """

    # --- --- --- Init --- --- ---

    def __init__(self, zoom_changed:SignalInstance, parent:QGraphicsView):
        super().__init__(parent)
        self.zoom_changed = zoom_changed
        self._info:ZoomInfo = ZoomInfo.default()
    # End of def __init__


    @classmethod
    def _levels_with_fit(cls, fit_level:int)->tuple[list[int], int]:
        """Return the list of zoom levels including the 'fit level', with its index."""
        zooms = _ZOOM_LEVELS.copy()
        fit_idx = bisect_left(zooms, fit_level)
        # Insert fit level if not present
        if fit_idx == len(zooms) or zooms[fit_idx] != fit_level:
            zooms.insert(fit_idx, fit_level)
        return zooms, fit_idx
    #


    # --- --- --- Private Helpers --- --- ---
    
    def _level_to_index(self, level:int, zoom_levels:list[int]) -> int:
        "Find the index of level (or closest towards 0), capped to bounds, in zoom_levels"
        if level < _MIN_ZOOM_LEVEL: return 0
        if level > _MAX_ZOOM_LEVEL: return len(zoom_levels) - 1
        return bisect_left(zoom_levels, level)
    # End of def level_to_index


    def _info_for_index(self, target_index:int)->ZoomInfo:
        """Compute ZoomInfo for the given target index. DOES NOT EMIT."""
        target_index = max(0, min(target_index, len(self._info.zoom_levels) - 1))
        if target_index != self._info.current_index:
            self._info = replace(self._info, current_index=target_index, want_to_fit=False)
        #
        return self._info
    # End of def _set_index

    
    # --- --- --- Public Core Methods --- --- ---

    def info(self) -> ZoomInfo:
        return self._info
    #
    
    
    def set(self, info: ZoomInfo) -> ZoomInfo:
        self._info = info
        self.zoom_changed.emit(self._info)
        return self._info
    #


    def set_current_level(self, target_level:int)->ZoomInfo:
        """ Set the zoom to the given level if possible, or select the closest one towards 0. Fires only on change, if init (called reset before)"""
        if target_level != self._info.current_level:
            target_index = self._level_to_index(target_level, self._info.zoom_levels)
            if target_index != self._info.current_index:
                self._info = replace(self._info, current_index=target_index, want_to_fit=False)
                self.zoom_changed.emit(self._info)
        #
        return self._info
    #
    
    
    def set_fit_level(self, fit_level:int)->ZoomInfo:
        """ Set a new fit level, adjusting the zoom levels list accordingly. Fires zoom_changed signal."""
        zoom_levels, fit_index = self._levels_with_fit(fit_level)
        #
        if self._info.want_to_fit: target_index = fit_index
        else: target_index = self._level_to_index(self._info.current_level, zoom_levels)
        #
        self._info = replace(self._info, zoom_levels=zoom_levels, current_index=target_index, fit_index=fit_index)
        self.zoom_changed.emit(self._info)
        return self._info
    #


    def set_want_to_fit(self, want_to_fit:bool)->ZoomInfo:
        """ Set whether to want to fit or not."""
        if want_to_fit:
            target_index = self._info.fit_index
        self._info = replace(self._info, current_index=target_index, want_to_fit=want_to_fit)
        self.zoom_changed.emit(self._info)
        return self._info
    #

    
    # --- --- --- Public Advanced Methods --- --- ---

    def info_for_zoom_in(self)->ZoomInfo:
        """Compute a ZoomInfo for zooming in (next zoom level). Does not emit signal."""
        return self._info_for_index(self._info.current_index+1)
    #


    def info_for_zoom_out(self)->ZoomInfo:
        """Compute a ZoomInfo for zooming out (previous zoom level). Does not emit signal."""
        return self._info_for_index(self._info.current_index-1)
    #

    
    def compute_fit_level_for_view(self, view:QGraphicsView) -> ZoomInfo:
        """Set the fit level for a view and its scene. Does emit"""
        scene_rect = view.sceneRect()
        view_rect = view.viewport().rect()

        if (not scene_rect.isNull()) and (not view_rect.isNull()):
            sx = view_rect.width()  / scene_rect.width()    # how much we can scale in X
            sy = view_rect.height() / scene_rect.height()   # how much we can scale in Y
            target_fit_level = int(min(sx, sy)*100)                        # pick the smaller to keep aspect, convert to int %
            self.set_fit_level(target_fit_level)
        
        return self._info
    # End of def set_fit_level_for_view