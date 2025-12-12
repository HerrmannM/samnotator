# --- --- --- Imports --- --- ---
# STD
from collections import defaultdict
import logging
from pathlib import Path
from typing import Any
# 3RD
import numpy as np
from PySide6.QtCore import QObject, Signal, SignalInstance, Slot
from PySide6.QtGui import QColor
# Project
from samnotator.controllers.instance_controller import InstanceController
from samnotator.controllers.frame_controller import FrameController, FrameInfo, frame_stub_from_paths
from samnotator.controllers.annotations_controller import AnnotationsController
from samnotator.controllers.model_controller import ModelController, InferenceResult
from samnotator.datamodel import FrameID,  InstanceID, Instance, MaskHW, PointID, PointXY, PointKind, Point, PointAnnotation, InstanceDetection
from samnotator.models.interface import ModelOutput, InferenceOutput
from samnotator.utils._CUD import CUD
from samnotator.widgets.instances.instance_renderers import MaskMode

# --- --- --- logger --- --- ---
logger = logging.getLogger(__name__)


# --- --- --- App Controller --- --- ---

class AppController(QObject):

    # --- --- --- Constructors --- --- ---

    def __init__(self, parent=None):
        super().__init__(parent)

        # --- Components
        # - Annotations Controller
        self.ctl_annotations = AnnotationsController(parent=self)
        self.sig_point_changed: SignalInstance = self.ctl_annotations.point_list_changed

        # - Instances Controller
        self.ctl_instances = InstanceController(parent=self)
        self.sig_instance_changed: SignalInstance = self.ctl_instances.instance_changed
        self.sig_current_instance_changed: SignalInstance = self.ctl_instances.current_instance_changed
        
        # - Frames Controller
        self.ctl_frames = FrameController(parent=self)
        self.sig_frame_changed: SignalInstance = self.ctl_frames.current_frame_changed

        # - Model controller
        self.ctl_model = ModelController(parent=self)
        self.result_inference_signal: SignalInstance = self.ctl_model.result_inference


        # --- ui init
        self._ui_init()
    # End of def __init__


    def _ui_init(self):
        # Connect signals
        self.sig_point_changed.connect(self.on_point_changed)
        self.sig_instance_changed.connect(self.on_instance_changed)
        self.sig_current_instance_changed.connect(self.on_current_instance_changed)
        self.sig_frame_changed.connect(self.on_frame_changed)
        self.result_inference_signal.connect(self.on_inference_result)
    # End of def _ui_init


    # --- --- --- Reset --- --- ---
    def reset(self):
        # Components
        self.ctl_frames.reset(None)
        self.ctl_annotations.reset()
        #
    # End of def reset

    
    
    # --- --- --- Frame --- --- ---

    def load_frame_from_paths(self, paths:list[Path]|None):
        if paths is None:
            self.ctl_frames.reset(None)
        else:
            stubs = frame_stub_from_paths(paths, is_video=False, fps=None)
            self.ctl_frames.reset(stubs)
    # End of def load_frame_from_paths
        

    # --- --- --- Slots  --- --- ---

    @Slot(Point)
    def on_request_point_annotation(self, point:Point):
        frame_id = self.ctl_frames.get_current_frame_id()
        instance_id = self.ctl_instances.get_current_instance_id()
        if frame_id is None or instance_id is None:
            return None
        self.ctl_annotations.create_point(frame_id, instance_id, point)
    # End of def on_request_point_annotation


    @Slot(object, CUD)
    def on_point_changed(self, annotations:list[PointAnnotation], cud:CUD):
        pass
    # End of def on_point_changed


    @Slot(object, object)
    def on_instance_changed(self, instance_id:InstanceID, cud:CUD):
        if cud == CUD.DELETE:
            # Delete all annotations for this instance
            self.ctl_annotations.delete_instance(instance_id)
        #
    # End of def on_instance_changed


    @Slot(object)
    def on_current_instance_changed(self, instance_id:InstanceID|None):
        pass
    # End of def on_current_instance_changed


    @Slot(object)
    def on_frame_changed(self, frame_id:FrameID|None):
        pass
    # End of def on_frame_changed


    @Slot(InferenceResult)
    def on_inference_result(self, inf_result: InferenceResult) -> None:
        req = inf_result.request
        model_out = inf_result.result

        # Bail out on error
        if not model_out.ok or model_out.data is None:
            logger.error(f"Inference result error: {model_out.error}")
            return

        out: InferenceOutput = model_out.data
        frame_mapping: dict[int, FrameID] = req.frame_mapping
        instance_mapping: dict[int, InstanceID] = req.instance_mapping

        # detections_by_instance[InstanceID][FrameID] = InstanceDetection
        detections_by_instance: dict[InstanceID, dict[FrameID, InstanceDetection]] = defaultdict(dict)

        # Iterate over all frame outputs (image: usually just frame_index==0)
        for frame_index, frame_out in out.frame_index_results.items():
            # Map frame_index -> original FrameID
            frame_id = frame_mapping.get(frame_index)

            if frame_id is None: # No mapping: skip this frame (should not normally happen)
                logger.error(f"No FrameID mapping for frame_index={frame_index} in inference result")
                continue

            boxes = frame_out.boxes                 # (N, 4)
            n = boxes.shape[0]
            masks = frame_out.masks                 # (N, H, W) bool
            obj_ids = frame_out.instance_ids        # (N,)

            for i in range(n):
                # Map model object_id -> actual InstanceID
                obj_id_int = int(obj_ids[i])
                instance_id = instance_mapping.get(obj_id_int)

                if instance_id is None: # No mapping for this object, skip: we are not letting the model generate new instances
                    logger.error(f"No InstanceID mapping for object_id={obj_id_int} in inference result")
                    continue

                x_min, y_min, x_max, y_max = boxes[i]
                top_left: PointXY = PointXY((int(x_min), int(y_min)))
                bottom_right: PointXY = PointXY((int(x_max), int(y_max)))
                mask_hw: MaskHW = masks[i]
                det = InstanceDetection(frame_id=frame_id, top_left=top_left, bottom_right=bottom_right, mask=mask_hw)
                detections_by_instance[instance_id][frame_id] = det
        # End for each frame_index

        # Push all detections back into the instance controller
        for instance_id, detections in detections_by_instance.items():
            self.ctl_instances.update_instance(instance_id, detections=detections)
    # End of def on_inference_result


    # --- --- --- Save/Load --- --- ---
    def save_to_folder(self, dir_path:Path) -> None:
        # Create annotations folder
        data_to_save: dict[str, Any] = {}

        # Only save frames that have annotations
        annotated_frames:dict[FrameID, set[InstanceID]] = self.ctl_annotations.get_frames_with_annotations()
        if not annotated_frames:
            return

        # Frame info
        frame_data: dict[FrameID, str] = {}
        for frame_id in annotated_frames.keys():
            frame_load = self.ctl_frames.frame_load_info(frame_id)
            frame_data[frame_id] = frame_load
        data_to_save["frames"] = frame_data

        # Save all instances
        instance_data: dict[InstanceID, dict[str, Any]] = {}
        for instance_id, instance_info in self.ctl_instances.instances.items():
            instance_data[instance_id] = instance_info.instance.to_dict()
        data_to_save["instances"] = instance_data

        # Save points annotations
        point_annotation_data:dict[FrameID, list[dict]] = {}
        for frame_id in annotated_frames.keys():
            point_annotations = self.ctl_annotations.get_points_for_frame(frame_id)
            point_annotation_data[frame_id] = [pa.to_dict() for pa in point_annotations]
        data_to_save["point_annotations"] = point_annotation_data
        
        # Save bounding boxes annotations
        bounding_box_data:dict[FrameID, list[dict]] = {}
        for frame_id in annotated_frames.keys():
            boxes = self.ctl_annotations.get_bboxes_for_frame(frame_id)
            bounding_box_data[frame_id] = [bb.to_dict() for bb in boxes]
        data_to_save["bounding_boxes"] = bounding_box_data

        # Write to disk as JSON
        data_path = dir_path / "annotations.json"
        import json
        with open(data_path, "w") as f:
            json.dump(data_to_save, f, indent=4)

        # Masks
        # Only saves frames that have detections
        mask_dir = dir_path / "masks"
        mask_dir.mkdir(exist_ok=True)

        detection_frames:dict[FrameID, set[InstanceID]] = defaultdict(set)

        for instance_id, instance_info in self.ctl_instances.instances.items():
            for frame_id in instance_info.instance.detections.keys():
                detection_frames[frame_id].add(instance_id)

        for frame_id, instances in detection_frames.items():
            m = self.ctl_instances.get_mask_for_frame(frame_id)
            if m is not None:
                all_mask_path = mask_dir / f"f{frame_id}.png"
                m.save(str(all_mask_path))
            #
            for iid in instances:
                if (mask := self.ctl_instances.get_mask_for(iid, frame_id, mask_mode=MaskMode.BW)) is not None:
                    mask_path = mask_dir / f"f{frame_id}_i{iid}.png"
                    mask.save(str(mask_path))

# End of class AppController