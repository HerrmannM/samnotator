# --- --- --- Imports --- --- ---
# STD
from dataclasses import dataclass
# 3RD
from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QColor, QPixmap
# Project
from samnotator.datamodel import InstanceDetection, InstanceID, Instance, FrameID
from samnotator.utils import CUD
from samnotator.utils_qt.colours import pick_contrast_colour
from samnotator.widgets.instances.instance_renderers import MarkRenderer, MaskRenderer


# --- --- --- Internal helpers --- --- ---

@dataclass(frozen=True, slots=True)
class InstanceInfo:
    instance:Instance
    # Render data
    point_marks:list[QPixmap]
    main_colour:QColor
    contrast_colour:QColor
    marker_size: int = 23
    bbox_handle_size: int = 8
    # Display options
    show_markers: bool = True
    show_mask: bool = True
    show_plain_mask: bool = False
# End of dataclass _InstanceState


def _make_point_marker_renderer(symbols:list[str], main_colour:QColor, contrast_colour:QColor) -> MarkRenderer:
    if not main_colour.isValid():
        main_colour = QColor("red")
        contrast_colour = pick_contrast_colour(main_colour)
    if not contrast_colour.isValid():
        contrast_colour = pick_contrast_colour(main_colour)
    #
    return MarkRenderer(symbols = symbols, main_colour=main_colour, contrast_colour=contrast_colour, shape_size_ratio=0.9, symbol_size_ratio=0.75, aa_margin=1)
# End of def _make_point_marker_renderer



@dataclass
class InstanceRenderer:
    mark_renderer:MarkRenderer
    mask_renderer:MaskRenderer
# End of dataclass InstanceRenderer
    

# --- --- --- Instance Controller --- --- ---

class InstanceController(QObject):

    instance_changed = Signal(object, CUD) # InstanceID, CUD
    
    current_instance_changed = Signal(object) # InstanceID|None


    def __init__(self, parent:QObject|None=None) -> None:
        super().__init__(parent)
        # Fields
        self.instances:dict[InstanceID, InstanceInfo] = {}
        self.renderers:dict[InstanceID, InstanceRenderer] = {}
        self.current_instance_id:InstanceID|None = None
        self._next_instance_id:int=0
    # End of def __init__


    # --- --- --- Private helpers --- --- ---
    
    def _get_id(self) -> InstanceID:
        iid = InstanceID(self._next_instance_id)
        self._next_instance_id += 1
        return iid
    # En of def _get_id
    

    # --- --- --- Instance CUD --- --- ---

    def create_instance(self, name:str, main_colour:QColor, category_name:str|None) -> InstanceID:
        # Instance
        instance_id = self._get_id()
        instance = Instance(
            instance_id=instance_id,
            instance_name=name,
            category_name=category_name,
            detections={}
        )
        # Point mark renderer
        # Order of symbols must match PointKind enum (see datamodel.py): NEGATIVE=0, POSITIVE=1
        contrast_colour = pick_contrast_colour(main_colour)
        point_mark_renderer = _make_point_marker_renderer(symbols=["-", "+"], main_colour=main_colour, contrast_colour=contrast_colour)
        mask_renderer = MaskRenderer(main_colour=main_colour, contrast_colour=pick_contrast_colour(main_colour))
        self.renderers[instance_id] = InstanceRenderer(mark_renderer=point_mark_renderer, mask_renderer=mask_renderer)
        marks = point_mark_renderer.get(pixmap_size_px=23)
        # Store
        self.instances[instance_id] = InstanceInfo(instance=instance, point_marks=marks, main_colour=main_colour, contrast_colour=contrast_colour)
        self.instance_changed.emit(instance_id, CUD.CREATE)
        return instance_id
    # End of def create_instance

    
    def delete_instance(self, instance_id:InstanceID) -> InstanceInfo:
        instance = self.instances.pop(instance_id)
        self.instance_changed.emit(instance_id, CUD.DELETE)
        return instance
    # End of def delete_instance


    def update_instance(
        self,
        instance_id: InstanceID,
        *,
        name: str | None = None,
        colour: QColor | None = None,
        category_name: str | None = None,
        marker_size: int | None = None,
        show_markers: bool | None = None,
        show_mask: bool | None = None,
        show_plain_mask: bool | None = None,
        detections: dict[FrameID, InstanceDetection] | None = None,
    ) -> None:
        """Update metadata and UI state for an instance."""
        info = self.instances[instance_id]
        inst = info.instance

        do_update = False
        do_mark_update = False

        # Name
        if name is not None and name != inst.instance_name:
            do_update = True
            new_name = name
        else:
            new_name = inst.instance_name
        #

        # Category
        if category_name is not None and category_name != inst.category_name:
            do_update = True
            new_cat = category_name
        else:
            new_cat = inst.category_name
        #

        # Size
        if marker_size is not None and marker_size != info.marker_size:
            do_update = True
            do_mark_update = True
            new_marker_size = marker_size
        else:
            new_marker_size = info.marker_size
        #

        # Colour
        if colour is not None and colour.isValid() and colour != info.main_colour:
            do_update = True
            do_mark_update = True
            new_main_colour = colour
            new_contrast_colour = pick_contrast_colour(colour)
            # Mark and mask
            self.renderers[instance_id].mark_renderer.set_colors(main=new_main_colour, contrast=new_contrast_colour)
            self.renderers[instance_id].mask_renderer.set_colors(main=new_main_colour, contrast=new_contrast_colour)
        else:
            new_main_colour = info.main_colour
            new_contrast_colour = info.contrast_colour
        #

        
        # Show markers
        if show_markers is not None and show_markers != info.show_markers:
            do_update = True
            new_show_markers = show_markers
        else:
            new_show_markers = info.show_markers
        #

        
        # Show mask
        if show_mask is not None and show_mask != info.show_mask:
            do_update = True
            new_show_mask = show_mask
        else:
            new_show_mask = info.show_mask
        #

        # Show plain mask
        if show_plain_mask is not None and show_plain_mask != info.show_plain_mask:
            do_update = True
            new_show_plain_mask = show_plain_mask
        else:
            new_show_plain_mask = info.show_plain_mask
        #

        # Detections
        if detections is not None:
            do_update = True
            new_detections = detections
        else:
            new_detections = inst.detections
        

        
        # --- Apply updates ---
        if do_mark_update:
            mark_renderer = self.renderers[instance_id].mark_renderer
            new_marks = mark_renderer.get(pixmap_size_px=new_marker_size)
        else:
            new_marks = info.point_marks

            

        # --- Update
        if do_update:
            new_instance = Instance(instance_id=instance_id, instance_name=new_name, category_name=new_cat, detections=new_detections)
            new_info = InstanceInfo(
                instance=new_instance,
                point_marks=new_marks,
                main_colour=new_main_colour,
                contrast_colour=new_contrast_colour,
                marker_size=new_marker_size,
                show_markers=new_show_markers,
                show_mask=new_show_mask,
                show_plain_mask=new_show_plain_mask
            )
            self.instances[instance_id] = new_info
            self.instance_changed.emit(instance_id, CUD.UPDATE)
        # Else, no changes
    # End of def update_instance


    # --- ---- --- Instance selection --- --- ---

    def set_current_instance(self, instance_id:InstanceID|None) -> None:
        if instance_id is None:
            self.current_instance_id = None
            self.current_instance_changed.emit(None)
            return None
        else:
            assert instance_id in self.instances, f"Instance ID {instance_id} does not exist."
            if instance_id != self.current_instance_id:
                self.current_instance_id = instance_id
                self.current_instance_changed.emit(instance_id)
    # End of def set_current_instance


    # --- --- --- Getters --- --- ---

    def get_current_instance_id(self) -> InstanceID|None:
        return self.current_instance_id
    # End of def get_current_instance_id


    def get_current_instance_info(self) -> InstanceInfo|None:
        if self.current_instance_id is None:
            return None
        return self.instances[self.current_instance_id]
    # End of def get_current_instance_info


    def get(self, instance_id:InstanceID) -> InstanceInfo:
        return self.instances[instance_id]
    # End of def get


    def all_instance_ids(self) -> list[InstanceID]:
        return list(self.instances.keys())
    # End of def all_instance_ids


    def all_categories(self) -> list[str]:
        """Convenience getters for categories"""
        cats:set[str] = set()
        for info in self.instances.values():
            if (cat:=info.instance.category_name) is not None:
                cats.add(cat)
        return sorted(cats)
    # End of def all_categories
    

    def get_mask_for(self, instance_id:InstanceID, frame_id:FrameID, plain_mask:bool) -> QPixmap|None:
        renderer = self.renderers.get(instance_id)
        assert renderer is not None, f"Instance ID {instance_id} does not have a renderer."
        instance = self.instances.get(instance_id)
        assert instance is not None, f"Instance ID {instance_id} does not exist."
        detection = instance.instance.detections.get(frame_id)
        if detection is None or detection.mask is None:
            return None
        return renderer.mask_renderer.get(detection.mask, plain_mask)
    # End of def get_mask_for
# End of class InstanceController