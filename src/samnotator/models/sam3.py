# --- --- --- Imports --- --- ---
# STD
from pathlib import Path
from typing import Any, cast
import logging
# 3RD
import numpy as np
from numpy.typing import NDArray
from PIL import Image
import torch
from transformers import Sam3TrackerModel, Sam3TrackerProcessor
from transformers.models.sam3_tracker.modeling_sam3_tracker import Sam3TrackerImageSegmentationOutput
#frtransformers.models.sam3_tracker.modeling_sam3_tracker.Sam3TrackerImageSegmentationOutput
# Project
from .interface import MaskOutputOptions, ModelInterface, ModelOutput, PVSTask, InferenceInput, InferenceOutput

logger = logging.getLogger(__name__)

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
            return InferenceOutput.empty(meta={"message": "No instances provided in task"})

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
             return InferenceOutput.empty(meta={"message": "No valid instances found"})
        
        # Concatenate all numpy arrays
        total_masks = np.concatenate([r.masks for r in results_list], axis=0)
        total_scores = np.concatenate([r.scores for r in results_list], axis=0)
        total_boxes = np.concatenate([r.boxes for r in results_list], axis=0)
        total_ids = np.concatenate([r.instance_object_ids for r in results_list], axis=0)

        return InferenceOutput(masks=total_masks, scores=total_scores, boxes=total_boxes, instance_object_ids=total_ids, meta=extra_meta)
    # End of def _run_pvs_task


    def _run_single_batch(self, pil_image: Image.Image, instances: list, use_boxes: bool, task_options: MaskOutputOptions) -> InferenceOutput:
        """ Helper to run one specific batch configuration.  """
        assert self._model is not None
        assert self._processor is not None
        assert self._device is not None
        # --- Prepare Data Layout ---
        # input_points: (batch=1, num_objects, num_points_per_object, 2)
        # input_labels: (batch=1, num_objects, num_points_per_object)
        # input_boxes:  (batch=1, num_objects, 4) OR None

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

        multimask_flag = task_options.max_masks_per_object > 1
        with torch.no_grad():
            outputs: Sam3TrackerImageSegmentationOutput = self._model(**inputs, multimask_output=multimask_flag)

        # Validate outputs: must have pred_masks
        if outputs.pred_masks is None:
            logger.warning("Sam3TrackerImplementation: No pred_masks in model output; returning empty result")
            return InferenceOutput.empty(meta={"message": "No masks predicted by model"})

        # Must have iou_scores
        if outputs.iou_scores is None:
            logger.warning("Sam3TrackerImplementation: No iou_scores in model output; returning empty result")
            return InferenceOutput.empty(meta={"message": "No scores predicted by model"})


        # --- Post Processing ---
        original_sizes = inputs["original_sizes"]
        
        # Processor handles resizing back to original image size
        # shapes: (batch, num_objects, num_masks, H, W) -> extract batch=0 -> (num_objects, num_masks_per_obj, H, W)
        post_masks = cast(NDArray[np.bool], self._processor.post_process_masks(outputs.pred_masks.cpu(), original_sizes))
        masks_np: NDArray[np.bool] = post_masks[0].numpy() if isinstance(post_masks[0], torch.Tensor) else post_masks[0] # (num_objects, num_masks, H, W)
        scores_np: NDArray[np.float32] = outputs.iou_scores.detach().cpu().numpy()[0].astype(np.float32) # (num_obj, num_masks)
        num_objects, num_masks, H, W = masks_np.shape

        # 1. Sort masks per object by descending score
        # sort_idx[i] is a permutation [0..num_masks-1] for object i
        sort_idx = np.argsort(-scores_np, axis=1)  # descending along num_masks

        # Build row indices for indexing (':' along num_masks alone does not work with advanced indexing of sort_idx)
        obj_idx = np.arange(num_objects)[:, None]  # shape (num_objects, 1)

        # Reorder masks and scores using the same permutation
        masks_np = masks_np[obj_idx, sort_idx, :, :]   # still (num_objects, num_masks, H, W)
        scores_np = scores_np[obj_idx, sort_idx]       # still (num_objects, num_masks)

        # 2. Optional Top-K per object (after sorting)
        k = task_options.max_masks_per_object
        if k < num_masks:
            masks_np = masks_np[:, :k, :, :]          # (num_objects, k, H, W)
            scores_np = scores_np[:, :k]              # (num_objects, k)
            num_masks = k                             # now each object has k masks

        # 3. Flatten: objects × masks_per_object -> total masks (N_total, H, W)
        N_total = num_objects * num_masks
        final_masks = masks_np.reshape(N_total, H, W)   # (N_total, H, W)
        final_scores = scores_np.reshape(N_total)       # (N_total,)

        # 4. Replicate instance IDs per object (same number of masks per object)
        batch_ids_arr = np.array(batch_ids, dtype=np.int32)  # (num_objects,)
        final_ids = np.repeat(batch_ids_arr, num_masks)      # (N_total,)

        # 5. Compute boxes from flattened masks
        final_boxes = self._compute_bboxes_from_masks(final_masks)

        return InferenceOutput(masks=final_masks, scores=final_scores, boxes=final_boxes, instance_object_ids=final_ids, meta={})
    # End of def _run_single_batch


    # --- --- --- Internal helpers --- --- ---

    @staticmethod
    def _compute_bboxes_from_masks(masks: NDArray[np.bool]) -> NDArray[np.int32]:
        if masks.size == 0:
            return np.zeros((0, 4), dtype=np.int32)
        N, _, _ = masks.shape
        boxes = np.zeros((N, 4), dtype=np.int32)
        for i in range(N):
            ys, xs = np.where(masks[i])
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