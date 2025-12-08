# --- --- --- Imports --- --- ---
# STD
from dataclasses import replace
# 3RD
from PySide6.QtCore import QObject, Signal, Slot
# Project
from samnotator.datamodel import BBox, FrameID, InstanceID
from samnotator.datamodel import PointAnnotation, PointID, Point, PointXY, PointKind
from samnotator.datamodel import BBoxAnnotation, BBoxID
from samnotator.utils import CUD


class _PerFrame:
    """Internal per-frame point annotation controller."""
    
    def __init__(self, frame_id:FrameID) -> None:
        self.frame_id:FrameID = frame_id
        self.occupancy:dict[PointXY, PointID] = {}
    # End of def __init__
    

    def is_free(self, point_xy:PointXY) -> bool:
        return point_xy not in self.occupancy
    # End of def is_free


    def create(self, annotation:PointAnnotation) -> None:
        position = annotation.point.position
        assert annotation.frame_id == self.frame_id, "Annotation frame ID does not match controller frame ID"
        assert self.is_free(position), "Point position is already occupied"
        self.occupancy[position] = annotation.point_id
    # End of def create
    

    def delete(self, annotation:PointAnnotation) -> None:
        pid = self.occupancy.pop(annotation.point.position, None)
        assert pid == annotation.point_id, "Point ID does not match occupancy record"
    # End of def delete


    def update_move(self, annotation:PointAnnotation, new_position:PointXY) -> bool:
        """Moving a point to a new position. Moving on itself is not an error. Return True if moved, else False."""
        old_position = annotation.point.position
        point_id = annotation.point_id
        assert self.occupancy.get(old_position, None) == point_id, "Point ID does not match occupancy record"
        # No move
        if old_position == new_position:
            return False
        else: # Move somewhere else
            assert self.is_free(new_position), "New point position is already occupied"
            del self.occupancy[old_position]
            self.occupancy[new_position] = point_id
            return True
        #
    # End of def update_move

    
    def __len__(self) -> int:
        return len(self.occupancy)
    # End of def __len__
# End of class _PerFrame


class AnnotationsController(QObject):

    point_list_changed = Signal(object, CUD) #list[PointAnnotation], CUD
    bbox_list_changed = Signal(object, CUD) #list[BBoxAnnotation], CUD

    # --- --- --- Init --- --- ---

    def __init__(self, parent:QObject|None=None) -> None:
        super().__init__(parent)
        self.per_frame:dict[FrameID, _PerFrame] = {}
        self.annotations:dict[PointID, PointAnnotation] = {}
        self.bboxes:dict[BBoxID, BBoxAnnotation] = {}
        self._next_point_id:int = 0
    # End of def __init__

    
    def reset(self) -> None:
        annotations = list(self.annotations.values())
        self.per_frame = {}
        self.annotations = {}
        self.bboxes = {}
        self._next_point_id = 0
        if len(annotations) > 0:
            self.point_list_changed.emit(annotations, CUD.DELETE)
    # End of def reset


    # --- --- --- Private helpers --- --- ---
    
    def _get_next_pid(self) -> PointID:
        point_id = PointID(self._next_point_id)
        self._next_point_id += 1
        return point_id
    # End of def _get_next_pid

    def _get_next_bid(self) -> BBoxID:
        bbox_id = BBoxID(self._next_point_id)
        self._next_point_id += 1
        return bbox_id
    # End of def _get_next_bid



    # --- --- --- Point CUD --- --- ---
    
    def create_point(self, frame_id:FrameID, instance_id:InstanceID, point:Point) -> PointAnnotation|None:
        frame = self.per_frame.setdefault(frame_id, _PerFrame(frame_id))
        if not frame.is_free(point.position):
            return None
        #
        point_id = self._get_next_pid()
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
                frame.delete(annotation)
                if len(frame) == 0:
                    del self.per_frame[annotation.frame_id]
                deleted_annotations.append(annotation)
        if len(deleted_annotations) > 0:
            self.point_list_changed.emit(deleted_annotations, CUD.DELETE)
        return deleted_annotations
    # End of def delete_point_list


    def delete_point(self, point_id:PointID) -> PointAnnotation|None:
        deleted:list[PointAnnotation] = self.delete_point_list([point_id])
        if len(deleted) == 1:
            return deleted[0]
    # End of def delete_point

    
    def update_point_move(self, point_id:PointID, new_position:PointXY) -> PointAnnotation|None:
        if (annotation := self.annotations.get(point_id, None)) is None:
            return None
        #
        frame = self.per_frame[annotation.frame_id]
        if frame.update_move(annotation, new_position):
            new_point = replace(annotation.point, position=new_position)
            new_annotation = replace(annotation, point=new_point)
            self.annotations[point_id] = new_annotation
            self.point_list_changed.emit([new_annotation], CUD.UPDATE)
            return new_annotation
        else:
            return annotation
    # End of def update_point_move


    def update_point_kind(self, point_id:PointID, new_kind:PointKind|None = None) -> PointAnnotation|None:
        if (annotation := self.annotations.get(point_id, None)) is None:
            return None
        #
        current_kind = annotation.point.kind
        if new_kind is None:
            new_kind = PointKind.POSITIVE if current_kind == PointKind.NEGATIVE else PointKind.NEGATIVE
        elif new_kind == current_kind:
            return annotation
        #
        new_point = replace(annotation.point, kind=new_kind)
        new_annotation = replace(annotation, point=new_point)
        self.annotations[point_id] = new_annotation
        self.point_list_changed.emit([new_annotation], CUD.UPDATE)
        return new_annotation
    # End of def update_point_kind

    
    # --- --- --- BBOX CUD --- --- ---

    def create_bbox(self, frame_id:FrameID, instance_id:InstanceID, bbox:BBox) -> BBoxAnnotation|None:
        bbox_id = self._get_next_bid()
        # For now, one bbox only
        if (b:=self.get_bbox_for_instance(instance_id)) is not None:
            print("Warning: overwriting existing bbox ID")
            self.delete_bbox(b.bbox_id)
        #
        ba = BBoxAnnotation(bbox_id=bbox_id, frame_id=frame_id, instance_id=instance_id, bbox=bbox)
        self.bboxes[bbox_id] = ba
        self.bbox_list_changed.emit([ba], CUD.CREATE)
        return ba
    # End of def create_bbox


    def delete_bbox_list(self, bbox_ids:list[BBoxID]) -> list[BBoxAnnotation]:
        deleted_annotations: list[BBoxAnnotation] = []
        for bid in bbox_ids:
            if (annotation := self.bboxes.pop(bid, None)) is not None:
                deleted_annotations.append(annotation)
        if len(deleted_annotations) > 0:
            self.bbox_list_changed.emit(deleted_annotations, CUD.DELETE)
        return deleted_annotations
    # End of def delete_bbox_list


    def delete_bbox(self, bbox_id:BBoxID) -> BBoxAnnotation|None:
        deleted:list[BBoxAnnotation] = self.delete_bbox_list([bbox_id])
        if len(deleted) == 1:
            return deleted[0]
    # End of def delete_bbox

    
    def update_move_box(self, bbox_id:BBoxID, new_bbox:BBox) -> BBoxAnnotation|None:
        if (annotation := self.bboxes.get(bbox_id, None)) is None:
            return None
        #
        new_annotation = replace(annotation, bbox=new_bbox)
        self.bboxes[bbox_id] = new_annotation
        self.bbox_list_changed.emit([new_annotation], CUD.UPDATE)
        return new_annotation
    # End of def update_move_box
    

    # --- --- --- Getters --- --- ---

    def get_point(self, point_id:PointID) -> PointAnnotation|None:
        return self.annotations.get(point_id, None)
    # End of def get_point
        

    def get_points_for_instance(self, instance_id:InstanceID) -> list[PointAnnotation]:
        """Return list of point annotations for the given instance ID."""
        return [pa for pa in self.annotations.values() if pa.instance_id == instance_id]
    # End of def get_points_for_instance


    def get_points_for_frame(self, frame_id:FrameID) -> list[PointAnnotation]:
        """Return list of point annotations for the given frame ID."""
        frame = self.per_frame.get(frame_id, None)
        if frame is None:
            return []
        else:
            result:list[PointAnnotation] = []
            for _, pid in frame.occupancy.items():
                annotation = self.annotations.get(pid, None)
                if annotation is not None:
                    result.append(annotation)
            return result
    # End of def get_points_for_frame


    def point_can_move(self, point_id:PointID, frame_id:FrameID, xy:PointXY) -> bool:
        return self.per_frame[frame_id].occupancy.get(xy, point_id) == point_id
    # End of def point_can_move


    def get_bbox_for_instance(self, instance_id:InstanceID) -> BBoxAnnotation|None:
        """Return the bbox annotation for the given instance ID, if any."""
        for ba in self.bboxes.values():
            if ba.instance_id == instance_id:
                return ba
        return None
    # End of def get_bbox_for_instance


    def get_bboxes_for_frame(self, frame_id:FrameID) -> list[BBoxAnnotation]:
        """Return list of bbox annotations for the given frame ID."""
        return [ba for ba in self.bboxes.values() if ba.frame_id == frame_id]
    # End of def get_bboxes_for_frame


    # --- --- --- Helpers --- --- ---

    def delete_instance(self, instance_id:InstanceID) -> None:
        """Slot to delete all  annotations for a given instance ID."""
        points_to_delete:list[PointID] = [pa.point_id for pa in self.annotations.values() if pa.instance_id == instance_id]
        self.delete_point_list(points_to_delete)
        bbox_to_delete:list[BBoxID] = [ba.bbox_id for ba in self.bboxes.values() if ba.instance_id == instance_id]
        self.delete_bbox_list(bbox_to_delete)
    # End of def delete_instance


    def delete_frame(self, frame_id:FrameID) -> None:
        """Slot to delete all  annotations for a given frame ID."""
        points_to_delete:list[PointID] = [pa.point_id for pa in self.annotations.values() if pa.frame_id == frame_id]
        self.delete_point_list(points_to_delete)
        bbox_to_delete:list[BBoxID] = [ba.bbox_id for ba in self.bboxes.values() if ba.frame_id == frame_id]
        self.delete_bbox_list(bbox_to_delete)
    # End of def delete_frame


    def get_frames_with_annotations(self) -> list[FrameID]:
        """Return list of frame IDs that have at least one annotation (point or bbox)."""
        return list(set(self.per_frame.keys()) | set({ba.frame_id for ba in self.bboxes.values()}))
    # End of def get_frames_with_annotations

# End of class AnnotationsController