# --- --- --- Imports --- --- ---
# STD
from dataclasses import replace
# 3RD
from PySide6.QtCore import QObject, Signal, Slot
# Project
from samnotator.datamodel import FrameID, InstanceID
from samnotator.datamodel import PointAnnotation, PointID, Point, PointXY
from samnotator.utils import CUD


class _PerFrame:
    """Internal per-frame point annotation controller."""
    
    def __init__(self, frame_id:FrameID) -> None:
        self.frame_id:FrameID = frame_id
        self.annotations:dict[PointID, PointAnnotation] = {}
        self.occupancy:dict[PointXY, PointID] = {}
    #

    def is_free(self, point_xy:PointXY) -> bool:
        return point_xy not in self.occupancy
    #

    def create(self, annotation:PointAnnotation) -> None:
        assert annotation.frame_id == self.frame_id, "Annotation frame ID does not match controller frame ID"
        position = annotation.point.position
        assert self.is_free(position), "Point position is already occupied"
        self.annotations[annotation.point_id] = annotation
        self.occupancy[position] = annotation.point_id
    #

    def delete(self, point_id:PointID) -> PointAnnotation:
        annotation = self.annotations.pop(point_id, None)
        assert annotation is not None, "Point ID not found"
        del self.occupancy[annotation.point.position]
        return annotation
    #

    def update_move(self, point_id:PointID, new_position:PointXY) -> PointAnnotation|None:
        """Moving a point to a new position. Moving on itseld is not an error. Return updated annotaiton if moved, else None."""
        annotation = self.annotations.pop(point_id, None)
        assert annotation is not None, "Point ID not found"
        position = annotation.point.position
        # No move
        if position == new_position:
            self.annotations[point_id] = annotation
            return None
        else: # Move somewhere else
            assert self.is_free(new_position), "New point position is already occupied"
            del self.occupancy[position]
            new_point = replace(annotation.point, position=new_position)
            new_annotation = replace(annotation, point=new_point)
            self.annotations[point_id] = new_annotation
            self.occupancy[new_position] = point_id
            return new_annotation
        #
    #


    def __len__(self) -> int:
        return len(self.annotations)
    #
# End of class _PerFrame


class AnnotationsController(QObject):

    point_list_changed = Signal(object, CUD) #list[PointAnnotation], CUD

    # --- --- --- Init --- --- ---

    def __init__(self, parent:QObject|None=None) -> None:
        super().__init__(parent)
        self.per_frame:dict[FrameID, _PerFrame] = {}
        self.annotations:dict[PointID, PointAnnotation] = {}
        self._next_point_id:int = 0
    # End of def __init__

    
    def reset(self) -> None:
        annotations = list(self.annotations.values())
        self.per_frame = {}
        self.annotations = {}
        self._next_point_id = 0
        if len(annotations) > 0:
            self.point_list_changed.emit(annotations, CUD.DELETE)
    # End of def reset


    # --- --- --- Private helpers --- --- ---
    
    def _get_next_id(self) -> PointID:
        point_id = PointID(self._next_point_id)
        self._next_point_id += 1
        return point_id
    # End of def _get_id


    # --- --- --- Point CUD & getters --- --- ---
    
    def create_point(self, frame_id:FrameID, instance_id:InstanceID, point:Point) -> PointAnnotation|None:
        frame = self.per_frame.setdefault(frame_id, _PerFrame(frame_id))
        if not frame.is_free(point.position):
            return None
        #
        point_id = self._get_next_id()
        annotation = PointAnnotation(point_id=point_id, frame_id=frame_id, instance_id=instance_id, point=point)
        frame.create(annotation)
        self.annotations[point_id] = annotation
        self.point_list_changed.emit([annotation], CUD.CREATE)
        return annotation
    # End of def create_point


    def delete_point_list(self, point_ids:list[PointID]) -> list[PointAnnotation]:
        deleted_annotations: list[PointAnnotation] = []
        for pid in point_ids:
            if (annotation := self.annotations.pop(pid, None)) is not None:
                frame = self.per_frame.get(annotation.frame_id, None)
                assert frame is not None, "Inconsistent state: annotation frame not found"
                frame.delete(pid)
                if len(frame) == 0:
                    del self.per_frame[annotation.frame_id]
                deleted_annotations.append(annotation)
        if len(deleted_annotations) > 0:
            self.point_list_changed.emit(deleted_annotations, CUD.DELETE)
        return deleted_annotations
    # End of def delete_point_list


    def delete_point(self, point_id:PointID) -> PointAnnotation|None:
        deleted:list[PointAnnotation] = self.delete_point_list([point_id])
        if len(deleted) == 0:
            return None
        return deleted[0]
    # End of def delete_point

    
    def update_move_point(self, point_id:PointID, new_position:PointXY) -> PointAnnotation|None:
        if (annotation := self.annotations.get(point_id, None)) is None:
            return None
        #
        frame = self.per_frame[annotation.frame_id]
        updated_annotation = frame.update_move(point_id, new_position)
        if updated_annotation is not None:
            self.annotations[point_id] = updated_annotation
            self.point_list_changed.emit([updated_annotation], CUD.UPDATE)
        #
        return updated_annotation
    # End of def update_move_point


    def get_point_annotation(self, point_id:PointID) -> PointAnnotation|None:
        return self.annotations.get(point_id, None)
    # End of def get_point_annotation
        

    def get_instance_points(self, instance_id:InstanceID) -> list[PointAnnotation]:
        """Return list of point annotations for the given instance ID."""
        return [pa for pa in self.annotations.values() if pa.instance_id == instance_id]
    # End of def get_instance_points


    def get_frame_points(self, frame_id:FrameID) -> list[PointAnnotation]:
        """Return list of point annotations for the given frame ID."""
        frame = self.per_frame.get(frame_id, None)
        if frame is None:
            return []
        return list(frame.annotations.values())
    # End of def get_frame_points


    def point_can_move(self, point_id:PointID, frame_id:FrameID, xy:PointXY) -> bool:
        return self.per_frame[frame_id].occupancy.get(xy, point_id) == point_id
    # End of def point_can_move

    
    # --- --- --- BBOX CUD & getters --- --- ---
    # TODO: Implement BBOX annotations management

    
    # --- --- --- Helpers --- --- ---

    def delete_instance(self, instance_id:InstanceID) -> None:
        """Slot to delete all point annotations for a given instance ID."""
        to_delete:list[PointID] = [pa.point_id for pa in self.annotations.values() if pa.instance_id == instance_id]
        self.delete_point_list(to_delete)

    def delete_frame(self, frame_id:FrameID) -> None:
        """Slot to delete all point annotations for a given frame ID."""
        to_delete:list[PointID] = [pa.point_id for pa in self.annotations.values() if pa.frame_id == frame_id]
        self.delete_point_list(to_delete)

# End of class AnnotationsController