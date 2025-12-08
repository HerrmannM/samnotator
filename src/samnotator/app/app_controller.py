# --- --- --- Imports --- --- ---
# STD
from collections import defaultdict
from pathlib import Path
from typing import Any
# 3RD
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
    def on_inference_result(self, inf_result:InferenceResult):
        req = inf_result.request
        model_out = inf_result.result

        # Bail out on error
        if not model_out.ok or model_out.data is None:
            return

        out: InferenceOutput = model_out.data
        frame_id: FrameID = req.frame_id
        instance_mapping: dict[int, InstanceID] = req.instance_mapping

        # Get mask threshold from task options if present, else default
        task = req.input_data.task
        mask_threshold = task.output_options.mask_threshold
        if mask_threshold is None:
            mask_threshold = 0.5

        boxes = out.boxes              # (N, 4)
        masks = out.masks              # (N, H, W) float32
        obj_ids = out.instance_object_ids  # (N,)

        n = boxes.shape[0]

        detections_by_instance: dict[InstanceID, dict[FrameID, InstanceDetection]] = defaultdict(dict)

        for i in range(n):
            obj_id_int = int(obj_ids[i])

            # Map model object_id -> actual InstanceID
            instance_id = instance_mapping.get(obj_id_int)
            if instance_id is None:
                # No mapping for this object, skip
                continue

            x_min, y_min, x_max, y_max = boxes[i]

            top_left: PointXY = PointXY((int(x_min), int(y_min)))
            bottom_right: PointXY = PointXY((int(x_max), int(y_max)))

            mask_hw: MaskHW | None = None
            if masks is not None:
                # (H, W) bool mask
                mask_hw = masks[i] >= mask_threshold

            det = InstanceDetection( frame_id=frame_id, top_left=top_left, bottom_right=bottom_right, mask=mask_hw)
            detections_by_instance[instance_id][frame_id] = det
        # 

        for instance_id, detections in detections_by_instance.items():
            self.ctl_instances.update_instance(instance_id, detections=detections)
    # End of def on_inference_result

    
    # --- --- --- Save/Load --- --- ---
    def save_to_folder(self, dir_path:Path) -> None:
        # Create annotations folder
        data_to_save: dict[str, Any] = {}

        # Only save frames that have annotations
        frame_data: dict[FrameID, str] = {}
        for frame_id in self.ctl_annotations.get_frames_with_annotations():
            frame_load = self.ctl_frames.frame_load_info(frame_id)
            frame_data[frame_id] = frame_load
        data_to_save["frames"] = frame_data

        # Save all instances
        instance_data: dict[InstanceID, dict[str, Any]] = {}
        for instance_id, instance_info in self.ctl_instances.instances.items():
            instance_data[instance_id] = instance_info.instance.to_dict()
        data_to_save["instances"] = instance_data

        # Save annotations
        point_annotation_data:dict[FrameID, list[dict]] = {}
        for frame_id in frame_data.keys():
            point_annotations = self.ctl_annotations.get_points_for_frame(frame_id)
            point_annotation_data[frame_id] = [pa.to_dict() for pa in point_annotations]
        data_to_save["point_annotations"] = point_annotation_data

        # Write to disk as JSON
        data_path = dir_path / "annotations.json"
        import json
        with open(data_path, "w") as f:
            json.dump(data_to_save, f, indent=4)

# End of class AppController