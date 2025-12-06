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
from .interface import ModelInterface, ModelOutput, ClickSegmentationTask, InferenceInput, InferenceOutput


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
        if self._loaded and self._device is not None and self._device == device:
            return

        if self._loaded:
            self.unload()

        self._device = torch.device(device)

        self._model = Sam3TrackerModel.from_pretrained(str(self._model_dir))
        self._model.to(self._device)

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
        if isinstance(task, ClickSegmentationTask):
            output = self._run_click_task( pil_image=pil_image, width=width, height=height, task=task, extra_meta={})
        # Other tasks can be added here
        else:
            return ModelOutput.failure(f"Unknown Sam3 task type: {type(task)!r}")
        #
        print(f"Sam3TrackerImplementation.run: done: output masks.shape={output.masks.shape}, scores.shape={output.scores.shape}, boxes.shape={output.boxes.shape}, instance_object_ids={output.instance_object_ids}")
        return ModelOutput.success(output)
    # End of def run


    # --- --- --- Internal helpers --- --- ---

    def _default_output(self, width: int, height: int, meta: dict[str, Any]) -> InferenceOutput:
        """ No model call; return an empty, but well-formed, result. """
        masks = np.zeros((0, height, width), dtype=np.float32)
        scores = np.zeros((0,), dtype=np.float32)
        boxes = np.zeros((0, 4), dtype=np.float32)
        instance_object_ids = np.zeros((0,), dtype=np.int32)
        return InferenceOutput(masks=masks, scores=scores, boxes=boxes, instance_object_ids=instance_object_ids, meta=meta)
    # End of def _default_output


    def _run_click_task( self, pil_image: Image.Image, width: int, height: int, task: ClickSegmentationTask, extra_meta: dict[str, Any],) -> InferenceOutput:
        """Promptable segmentation with user clicks (multi-object)."""
        assert self._model is not None
        assert self._processor is not None
        assert self._device is not None

        prompts = task.prompts
        if not prompts:
            return self._default_output( width=width, height=height, meta=extra_meta)

        # Group clicks by object_id
        obj_points: dict[int, list[list[float]]] = defaultdict(list)
        obj_labels: dict[int, list[int]] = defaultdict(list)
        for p in prompts:
            obj_points[p.instance_id].append([float(p.x), float(p.y)])
            obj_labels[p.instance_id].append(1 if p.is_positive else 0)

        # Deterministic ordering of objects
        ordered_object_ids: list[int] = sorted(obj_points.keys())
        num_objects = len(ordered_object_ids)

        points_per_object: list[list[list[float]]] = []
        labels_per_object: list[list[int]] = []

        for oid in ordered_object_ids:
            points_per_object.append(obj_points[oid])
            labels_per_object.append(obj_labels[oid])

        # Shape: [batch, num_objects, num_points_per_object, 2]
        input_points = [points_per_object]
        # Shape: [batch, num_objects, num_points_per_object]
        input_labels = [labels_per_object]

        # Task options
        mopts = task.output_options
        multimask_output = mopts.multimask_output
        mask_threshold = 0.5 if mopts.mask_threshold is None else mopts.mask_threshold
        max_masks_per_object = mopts.max_masks_per_object

        # Build HF inputs and run model
        inputs = self._processor(images=pil_image, input_points=input_points, input_labels=input_labels, return_tensors="pt")
        inputs = inputs.to(self._device)
        with torch.no_grad():
            outputs = self._model(**inputs, multimask_output=multimask_output)

        # Post-process to original image size
        # HF returns a list over batch; we have batch size 1.
        post_masks_list = self._processor.post_process_masks(outputs.pred_masks.cpu(), inputs["original_sizes"])

        # Tensor: shapes like [num_objects, num_masks_per_object, H, W] or [N, H, W]
        masks_t = post_masks_list[0]
        if isinstance(masks_t, torch.Tensor):
            masks_np = masks_t.numpy()
        else:
            masks_np = np.asarray(masks_t)

        # IoU / quality scores: shape [batch, num_objects, num_masks_per_object]
        # (based on SAM2 tracker API; SAM3 is designed to be compatible)
        iou_scores_t = getattr(outputs, "iou_scores", None)
        if iou_scores_t is not None:
            iou_scores_np = iou_scores_t.detach().cpu().numpy()[0]  # drop batch
        else:
            # If for some reason not present, fall back to zeros
            if masks_np.ndim == 4:
                _, num_masks_per_object, _, _ = masks_np.shape
                iou_scores_np = np.zeros((num_objects, num_masks_per_object), dtype=np.float32)
            elif masks_np.ndim == 3:
                N, _, _ = masks_np.shape
                iou_scores_np = np.zeros((1, N), dtype=np.float32)
            else:
                iou_scores_np = np.zeros((0, 0), dtype=np.float32)

        # Optionally slice top-k masks per object (assuming HF outputs are sorted by quality)
        if masks_np.ndim == 4:
            n_obj, n_masks_obj, H, W = masks_np.shape
            assert n_obj == num_objects
            if max_masks_per_object is not None and max_masks_per_object < n_masks_obj:
                k = max_masks_per_object
                masks_np = masks_np[:, :k, :, :]
                iou_scores_np = iou_scores_np[:, :k]
                n_masks_obj = k
        elif masks_np.ndim == 3:
            # Shape [N, H, W]; treat as n_obj=1, n_masks_obj=N
            n_obj = 1
            n_masks_obj = masks_np.shape[0]
        else:
            # Unexpected shape; return empty result
            return self._default_output(width=width, height=height, meta={"message": f"Unexpected mask tensor shape {masks_np.shape}"})

        # Flatten masks and scores to instance-level
        if masks_np.ndim == 4:
            # [num_objects, num_masks_per_object, H, W] -> [N, H, W]
            _, _, H, W = masks_np.shape
            instance_masks = masks_np.reshape(-1, H, W)
            # [num_objects, num_masks_per_object] -> [N]
            instance_scores = iou_scores_np.reshape(-1).astype(np.float32)
            # Build instance_object_ids mapping
            ordered_object_ids_np = np.asarray(ordered_object_ids, dtype=np.int32)
            instance_object_ids = np.repeat(ordered_object_ids_np, repeats=masks_np.shape[1])
        else:
            # [N, H, W], single object_id=0 for all instances
            N, H, W = masks_np.shape
            instance_masks = masks_np
            instance_scores = ( iou_scores_np.reshape(-1).astype(np.float32) if iou_scores_np.size == N else np.zeros((N,), dtype=np.float32))
            instance_object_ids = np.zeros((N,), dtype=np.int32)

        # Compute bounding boxes from masks using thresholded probabilities
        boxes = self._compute_bboxes_from_masks(instance_masks, threshold=mask_threshold)

        return InferenceOutput(masks=instance_masks.astype(np.float32), scores=instance_scores, boxes=boxes, instance_object_ids=instance_object_ids, meta={})
    # End of def _run_click_task


    @staticmethod
    def _compute_bboxes_from_masks( masks: np.ndarray, threshold: float) -> np.ndarray:
        """ Compute bounding boxes [x_min, y_min, x_max, y_max] in pixel coordinates from probability masks.

            masks: (N, H, W) float32 in [0, 1]
        """
        if masks.size == 0:
            return np.zeros((0, 4), dtype=np.float32)

        N, H, W = masks.shape
        boxes = np.zeros((N, 4), dtype=np.float32)

        for i in range(N):
            prob = masks[i]
            bin_mask = prob >= threshold
            ys, xs = np.where(bin_mask)
            if xs.size == 0 or ys.size == 0:
                # No foreground pixels at this threshold; keep zeros for this box
                continue
            x_min = float(xs.min())
            x_max = float(xs.max())
            y_min = float(ys.min())
            y_max = float(ys.max())
            boxes[i] = np.array([x_min, y_min, x_max, y_max], dtype=np.float32)

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