# --- --- --- Imports --- --- ---
# STD
from collections import defaultdict
from pathlib import Path
from typing import Any
# 3RD
import numpy as np
from PIL import Image
import torch
from transformers import Sam3TrackerModel, Sam3TrackerProcessor
# Project
from .interface import ModelInterface, ModelOutput, PVSTask, InferenceInput, InferenceOutput


class Sam3TrackerImplementation(ModelInterface):
    """
    SAM3 Tracker implementation of ModelInterface, using the Sam3TrackerModel/Sam3TrackerProcessor pair from transformers.
    """
    
    # --- --- --- Constructor --- --- ---

    def __init__(self, model_dir: Path) -> None:
        """
        `model_dir` is a local directory containing the SAM3 weights/config
        (suitable for `from_pretrained(str(model_dir))`).

        No heavy initialization here; everything important is done in load().
        """
        self._model_dir: Path = model_dir.resolve()
        self._name: str = "sam3-tracker"
        self._model: Sam3TrackerModel|None = None
        self._processor: Sam3TrackerProcessor|None = None
        self._device: torch.device|None = None
        self._loaded: bool = False
    # End of def __init__

    
    # --- --- --- Model Interface Implementation --- --- ---


    def name(self) -> str:
        return self._name
    # End of def name


    def ready(self) -> bool:
        return self._loaded and self._model is not None and self._processor is not None
    # End of def ready


    def load(self, device: str) -> None:
        """ Called only from the worker thread.  Must setup all heavy resources on the given device."""
        if self._loaded and self._device is not None and str(self._device) == device:
            return
        if self._loaded:
            self.unload()

        self._device = torch.device(device)
        self._model = Sam3TrackerModel.from_pretrained(str(self._model_dir))
        self._model.to(self._device) # type: ignore
        self._processor = Sam3TrackerProcessor.from_pretrained(str(self._model_dir))
        self._loaded = True
    # End of def load


    def unload(self) -> None:
        """ Called only from the worker thread. Must free heavy resources."""
        self._model = None
        self._processor = None
        self._device = None
        self._loaded = False
        torch.cuda.empty_cache()
    # End of def unload


    def run(self, input_data: InferenceInput) -> ModelOutput:
        """ Called only from the worker thread.  Must return an InferenceResult.  """
        # State check
        if not self.ready():
            return ModelOutput.failure("Sam3 model is not loaded or not ready")

        if self._device is None or self._model is None or self._processor is None:
            return ModelOutput.failure("Sam3 internal state is inconsistent")

        # Open image
        try:
            pil_image = Image.open(input_data.image_path).convert("RGB")
        except Exception as e:
            return ModelOutput.failure(f"Failed to open image: {e!r}")

        width, height = pil_image.size
        task = input_data.task

        print(f"Sam3TrackerImplementation.run: Task: {type(task)!r} Image: {input_data.image_path} ({width}x{height})")
        if isinstance(task, PVSTask):
            output = self._run_pvs_task( pil_image=pil_image, width=width, height=height, task=task, extra_meta={})
        # Other tasks can be added here
        else:
            return ModelOutput.failure(f"Unknown Sam3 task type: {type(task)!r}")
        #
        print(f"Sam3TrackerImplementation.run: done: output masks.shape={output.masks.shape}, scores.shape={output.scores.shape}, boxes.shape={output.boxes.shape}, instance_object_ids={output.instance_object_ids}")
        return ModelOutput.success(output)
    # End of def run


    # --- --- --- Core Logic --- --- ---

    def _run_pvs_task(self, pil_image: Image.Image, width: int, height: int, task: PVSTask, extra_meta: dict[str, Any]) -> InferenceOutput:
        """ Split the task into two batches (Boxed vs Unboxed) and merge results. """
        assert self._model is not None

        instances = task.instances
        if not instances:
            return self._default_output(width, height, extra_meta)

        # 1. Bucket the instances
        instances_with_box = []
        instances_without_box = []

        for inst in instances:
            # We allow instances with NO points if they have a box. 
            # We skip instances with NO points AND NO box (invalid prompt).
            if not inst.points and inst.box is None:
                continue
            if inst.box is not None:
                instances_with_box.append(inst)
            else:
                instances_without_box.append(inst)
        #

        # 2. Run batches
        results_list = []
        if instances_with_box:
            results_list.append(self._run_single_batch(pil_image, instances_with_box, use_boxes=True, task_options=task.output_options))
        if instances_without_box:
            results_list.append(self._run_single_batch(pil_image, instances_without_box, use_boxes=False, task_options=task.output_options))
        #

        # 3. Merge Results
        if not results_list:
             return self._default_output(width, height, {"message": "No valid instances found"})
        
        # Concatenate all numpy arrays
        total_masks = np.concatenate([r.masks for r in results_list], axis=0)
        total_scores = np.concatenate([r.scores for r in results_list], axis=0)
        total_boxes = np.concatenate([r.boxes for r in results_list], axis=0)
        total_ids = np.concatenate([r.instance_object_ids for r in results_list], axis=0)

        return InferenceOutput(masks=total_masks, scores=total_scores, boxes=total_boxes, instance_object_ids=total_ids, meta=extra_meta)
    # End of def _run_pvs_task


    def _run_single_batch(self, pil_image: Image.Image, instances: list, use_boxes: bool, task_options: Any) -> InferenceOutput:
        """ Helper to run one specific batch configuration.  """
        assert self._model is not None
        assert self._processor is not None
        assert self._device is not None
        # --- Prepare Data Layout ---
        # input_points: [batch=1, num_objects, num_points_per_object, 2]
        # input_labels: [batch=1, num_objects, num_points_per_object]
        # input_boxes:  [batch=1, num_objects, 4] OR None

        points_per_object = []
        labels_per_object = []
        boxes_per_object = [] # Only used if use_boxes=True
        
        # Track IDs to preserve assignment later
        batch_ids = [] 

        for inst in instances:
            batch_ids.append(inst.instance_id)

            # Points
            pts = [[float(p.x), float(p.y)] for p in inst.points]
            lbls = [1 if p.is_positive else 0 for p in inst.points]
            
            # EDGE CASE: HF Processor often crashes if `input_points` is empty list, 
            # even if `input_boxes` is provided. 
            # We pad with a dummy [0,0] negative point if empty.
            if not pts:
                pts = [[0.0, 0.0]]
                lbls = [-1] # -1 usually means "padding/ignore" in SAM, or use 0 (negative)

            points_per_object.append(pts)
            labels_per_object.append(lbls)

            # Boxes
            if use_boxes:
                b = inst.box
                boxes_per_object.append([float(b.x_min), float(b.y_min), float(b.x_max), float(b.y_max)])

        # Construct Processor Inputs
        # Note: we wrap in an extra list [] to create the batch_size=1 dimension
        input_points = [points_per_object] 
        input_labels = [labels_per_object]
        input_boxes = [boxes_per_object] if use_boxes else None

        # --- Inference ---
        inputs = self._processor( images=pil_image, input_points=input_points, input_labels=input_labels, input_boxes=input_boxes, return_tensors="pt")
        inputs = inputs.to(self._device)

        with torch.no_grad():
            outputs = self._model( **inputs, multimask_output=task_options.multimask_output)

        # --- Post Processing ---
        # shapes: outputs.pred_masks is [batch, num_objects, num_masks, H, W] usually
        original_sizes = inputs["original_sizes"]
        
        # Processor handles resizing back to original image size
        post_masks = self._processor.post_process_masks(outputs.pred_masks.cpu(), original_sizes)
        
        # Extract batch 0
        # masks_np shape: (num_objects, num_masks_per_obj, H, W)
        masks_np = post_masks[0].numpy() if isinstance(post_masks[0], torch.Tensor) else post_masks[0]
        
        # Scores
        if hasattr(outputs, "iou_scores"):
            scores_np = outputs.iou_scores.detach().cpu().numpy()[0] # [num_obj, num_masks]
        else:
            # Fallback
            n_obj, n_mask = masks_np.shape[:2]
            scores_np = np.zeros((n_obj, n_mask), dtype=np.float32)

        # --- Flattening & Filtering ---
        # We need to flatten [Num_Objects, Num_Masks, H, W] -> [Total_Masks, H, W]
        # And replicate IDs accordingly.
        
        num_objects, num_masks, H, W = masks_np.shape
        
        # 1. Handle Top-K filtering per object
        k = task_options.max_masks_per_object
        if k is not None and k < num_masks:
             masks_np = masks_np[:, :k, :, :]
             scores_np = scores_np[:, :k]
             num_masks = k

        # 2. Flatten
        # Reshape masks to (N_total, H, W)
        final_masks = masks_np.reshape(-1, H, W)
        
        # Reshape scores to (N_total)
        final_scores = scores_np.reshape(-1)

        # 3. Replicate IDs
        # If we have 2 masks per object, object_id 5 becomes [5, 5]
        batch_ids_arr = np.array(batch_ids, dtype=np.int32)
        final_ids = np.repeat(batch_ids_arr, num_masks)

        # 4. Compute BBoxes from masks (standard helper)
        final_boxes = self._compute_bboxes_from_masks( final_masks, threshold=(task_options.mask_threshold or 0.5))

        return InferenceOutput(masks=final_masks.astype(np.float32), scores=final_scores.astype(np.float32), boxes=final_boxes, instance_object_ids=final_ids, meta={})
    # End of def _run_single_batch


    # --- --- --- Internal helpers --- --- ---

    def _default_output(self, width: int, height: int, meta: dict[str, Any]) -> InferenceOutput:
        """ No model call; return an empty, but well-formed, result. """
        masks = np.zeros((0, height, width), dtype=np.float32)
        scores = np.zeros((0,), dtype=np.float32)
        boxes = np.zeros((0, 4), dtype=np.float32)
        instance_object_ids = np.zeros((0,), dtype=np.int32)
        return InferenceOutput(masks=masks, scores=scores, boxes=boxes, instance_object_ids=instance_object_ids, meta=meta)
    # End of def _default_output


    @staticmethod
    def _compute_bboxes_from_masks(masks: np.ndarray, threshold: float) -> np.ndarray:
        if masks.size == 0:
            return np.zeros((0, 4), dtype=np.float32)

        N, _, _ = masks.shape
        boxes = np.zeros((N, 4), dtype=np.float32)
        
        # Simple boolean conversion
        bin_masks = masks >= threshold

        for i in range(N):
            ys, xs = np.where(bin_masks[i])
            if xs.size > 0:
                boxes[i] = [xs.min(), ys.min(), xs.max(), ys.max()]
            # else 0,0,0,0

        return boxes
    # End of def _compute_bboxes_from_masks
    
    
# End of class Sam3TrackerImplementation



def builder(path: Path) -> ModelInterface|None:
    """Must be named 'builder' to be discoverable by ModelController."""
    try:
        return Sam3TrackerImplementation(model_dir=path)
    except Exception:
        return None
# End of def builder