# --- --- --- Imports --- --- ---
# STD
from pathlib import Path
from typing import Any, cast, Callable
import logging
# 3RD
import numpy as np
from numpy.typing import NDArray
from PIL import Image
import torch
from transformers import Sam3TrackerModel, Sam3TrackerProcessor
from transformers.models.sam3_tracker.modeling_sam3_tracker import Sam3TrackerImageSegmentationOutput
# Project
from .interface import MaskOutputOptions, ModelInterface, ModelOutput, PVSTask, InferenceInput, InferenceOutput, FrameInferenceOutput, TaskType, PVSFramePrompt
from .sam3_utils import Sam3PromptBatch, build_prompt_batches_for_frame, sort_and_flatten_masks_and_scores


# --- --- --- Logger --- --- ---

logger = logging.getLogger(__name__)


# --- --- --- Sam3 Tracker Implementation --- --- ---

class Sam3TrackerImplementation(ModelInterface):
    """ Image-only SAM3 tracker implementation of ModelInterface, using Sam3TrackerModel / Sam3TrackerProcessor from transformers.

    This implementation:
      - Supports only TaskType.PVS
      - Supports only single-frame inputs (len(frames) == 1)
      - Does NOT support video_options (video PVS).
    """

    # --- --- --- Constructor --- --- ---

    def __init__(self, model_dir: Path) -> None:
        """
        `model_dir` is a local directory containing the SAM3 weights/config (suitable for `from_pretrained(str(model_dir))`).
        No heavy initialization here; everything important is done in load().
        """
        self._model_dir: Path = model_dir.resolve()
        self._name: str = "sam3_pvs_image"
        self._model: Sam3TrackerModel | None = None
        self._processor: Sam3TrackerProcessor | None = None
        self._device: torch.device | None = None
        self._loaded: bool = False
        self._progress_callback: Callable[[float, str|None], None] = lambda progress, msg: None
    # End of def __init__


    # --- --- --- Model Interface Implementation --- --- ---

    def name(self) -> str:
        return self._name
    # End of def name


    def ready(self) -> bool:
        return self._loaded and self._model is not None and self._processor is not None
    # End of def ready


    def set_progress_callback(self, callback:Callable[[float, str|None], None]) -> None:
        self._progress_callback = callback
    # End of def set_progress_callback


    def load(self, device: str) -> None:
        """Called only from the worker thread. Must setup all heavy resources on the given device."""
        if self._loaded and self._device is not None and str(self._device) == device:
            return
        if self._loaded:
            self.unload()

        self._device = torch.device(device)
        self._model = Sam3TrackerModel.from_pretrained(str(self._model_dir))
        self._model.to(self._device)  # type: ignore
        self._processor = Sam3TrackerProcessor.from_pretrained(str(self._model_dir))
        self._loaded = True
    # End of def load


    def unload(self) -> None:
        """ Called only from the worker thread. Must free heavy resources.  """
        self._model = None
        self._processor = None
        self._device = None
        self._loaded = False
        torch.cuda.empty_cache()
    # End of def unload


    def run(self, input_data: InferenceInput) -> ModelOutput:
        """
        Called only from the worker thread. Must return a ModelOutput.
        This implementation only supports TaskType.PVS with len(frames) == 1 and task.video_options=None
        """
        try:
            # State check
            if not self.ready():
                return ModelOutput.failure("Sam3TrackerImplementation: model is not loaded or not ready")

            if self._device is None or self._model is None or self._processor is None:
                return ModelOutput.failure("Sam3TrackerImplementation: internal state is inconsistent")

            # Task type
            if input_data.task_type is not TaskType.PVS:
                return ModelOutput.failure(f"Sam3TrackerImplementation: unsupported task_type {input_data.task_type!r}")

            task: PVSTask = input_data.task
            frame_paths = input_data.frame_paths

            # Enforce image-only usage
            if len(frame_paths) != 1:
                return ModelOutput.failure( "Sam3TrackerImplementation: only single-frame PVS is supported in this implementation")

            if task.video_options is not None:
                return ModelOutput.failure( "Sam3TrackerImplementation: video_options are not supported (image-only implementation)")

            image_path = frame_paths[0]

            # Open image
            try:
                pil_image = Image.open(image_path).convert("RGB")
            except Exception as e:
                return ModelOutput.failure(f"Sam3TrackerImplementation: failed to open image: {e!r}")

            width, height = pil_image.size

            # Find frame prompts for this image (frame_index == 0 by convention)
            frame_prompt: PVSFramePrompt | ModelOutput = self._select_frame_prompt_for_image(task)
            if isinstance(frame_prompt, ModelOutput):
                return frame_prompt

            # Run PVS on this frame
            logger.debug("Sam3TrackerImplementation.run: image=%s (%dx%d), frame_index=%d, instances=%d", image_path, width, height, frame_prompt.frame_index, len(frame_prompt.instances))
            frame_output = self._run_pvs_image_frame(pil_image=pil_image, frame_prompt=frame_prompt, output_options=task.output_options, extra_meta={})
            logger.debug( "Sam3TrackerImplementation.run: done, frame_index=%d, masks.shape=%s, scores.shape=%s, boxes.shape=%s", frame_output.frame_index, frame_output.masks.shape, frame_output.scores.shape, frame_output.boxes.shape)

            inference_output = InferenceOutput(frame_index_results={frame_output.frame_index: frame_output})
            return ModelOutput.success(inference_output)
        except Exception as e:
            return ModelOutput.failure(f"Sam3TrackerImplementation: exception during run: {e!r}")
    # End of def run


    # --- --- --- Core Logic --- --- ---

    @staticmethod
    def _select_frame_prompt_for_image(task: PVSTask) -> PVSFramePrompt | ModelOutput:
        """Image input expects one and only one frame prompt with frame index==0. Get it or return ModelOutput failure if find none or more than one."""
        candidates:list[PVSFramePrompt] = [fp for fp in task.frame_prompts if fp.frame_index==0]
        nc = len(candidates)
        match nc:
            case 0: return ModelOutput.failure("Sam3TrackerImplementation: no acceptable frame prompt found (with frame index == 0, expected for image input)")
            case 1: return candidates[0]
            case _: return ModelOutput.failure(f"Sam3TrackerImplementation: multiple ({nc}) frame prompts found with frame index == 0; ambiguous for image input")
    # End of def _select_frame_prompt_for_image


    def _run_pvs_image_frame(self, pil_image: Image.Image, frame_prompt: PVSFramePrompt, output_options: MaskOutputOptions, extra_meta: dict[str, Any] | None = None,) -> FrameInferenceOutput:
        """Run PVS on a single image frame using all instances in the given frame_prompt."""
        # We:
        #  - Build one or two Sam3PromptBatch (with boxes / without boxes) via utils.
        #  - Run one SAM3 forward per batch.
        #  - Concatenate all masks/scores/boxes/ids into a single FrameInferenceOutput.
        assert self._model is not None
        assert self._processor is not None
        assert self._device is not None

        frame_index = frame_prompt.frame_index

        # Check instances
        instances = frame_prompt.instances
        if not instances:
            return FrameInferenceOutput.empty(frame_index=frame_index, meta={"message": "No instances provided in frame prompt"})

        # Build prompt batches and run
        batches = build_prompt_batches_for_frame(frame_index=frame_index, instances=instances)
        if not batches:
            return FrameInferenceOutput.empty( frame_index=frame_index, meta={"message": "No valid instances found after preprocessing"})

        results:list[FrameInferenceOutput] = []
        for name, batch in batches.items():
            logger.info("Sam3TrackerImplementation: running batch '%s', with %d instances", name, len(batch.instance_ids))
            print("Running batch:", name, "with", len(batch.instance_ids), "instances")
            out = self._run_single_batch(pil_image=pil_image, batch=batch, output_options=output_options)
            if out.masks.size == 0:
                continue
            results.append(out)
        #

        # Merge results
        if not results:
            return FrameInferenceOutput.empty(frame_index=frame_index, meta={"message": "No masks produced by model"},)
        total_masks = np.concatenate([r.masks for r in results], axis=0)
        total_scores = np.concatenate([r.scores for r in results], axis=0)
        total_boxes = np.concatenate([r.boxes for r in results], axis=0)
        total_ids = np.concatenate([r.instance_ids for r in results], axis=0)

        meta = extra_meta or {}
        return FrameInferenceOutput(frame_index=frame_index, masks=total_masks, scores=total_scores, boxes=total_boxes, instance_ids=total_ids, meta=meta)
    # End of def _run_pvs_image_frame


    def _run_single_batch(self, pil_image: Image.Image, batch: Sam3PromptBatch, output_options: MaskOutputOptions) -> FrameInferenceOutput:
        """ Helper to run one specific batch configuration (with or without boxes). Returns a FrameInferenceOutput for this frame and this subset of instances. """
        assert self._model is not None
        assert self._processor is not None
        assert self._device is not None

        inputs = self._processor(images=pil_image, input_points=batch.input_points, input_labels=batch.input_labels, input_boxes=batch.input_boxes, return_tensors="pt")
        inputs = inputs.to(self._device)
        multimask_flag = output_options.max_masks_per_object > 1

        with torch.no_grad():
            outputs: Sam3TrackerImageSegmentationOutput = self._model( **inputs, multimask_output=multimask_flag)

        # Validate outputs
        if outputs.pred_masks is None or outputs.iou_scores is None:
            msg = "no pred_masks" if outputs.pred_masks is None else "no iou_scores"
            message = f"Sam3TrackerImplementation: model output is missing required fields: {msg}"
            logger.error(message)
            print("ERROR:", message)
            return FrameInferenceOutput.empty(frame_index=batch.frame_index, meta={"message": message})
        #

        # post_process_masks returns a list-like indexed by batch
        original_sizes = inputs["original_sizes"]
        # Return Batched masks in batch_size, num_channels, height, width) format, where (height, width) is given by original_size.
        post_masks = self._processor.post_process_masks(outputs.pred_masks.detach().cpu(), original_sizes=original_sizes)
        masks_0 = post_masks[0]
        if isinstance(masks_0, torch.Tensor):
            masks_np: NDArray[np.bool] = masks_0.numpy()  # (num_objects, num_masks, H, W)
        else:
            masks_np = cast(NDArray[np.bool], masks_0)

        scores_np: NDArray[np.float32] = ( outputs.iou_scores.detach().cpu().numpy()[0].astype(np.float32))  # (num_objects, num_masks)

        # sort, top-k, flatten, compute boxes
        result = sort_and_flatten_masks_and_scores(masks=masks_np, scores=scores_np, instance_ids=batch.instance_ids, output_options=output_options)
        if result.masks.size == 0:
            return FrameInferenceOutput.empty( frame_index=batch.frame_index, meta={"message": "No masks after sorting/flattening"})

        return FrameInferenceOutput(frame_index=batch.frame_index, masks=result.masks, scores=result.scores, boxes=result.boxes, instance_ids=result.instance_ids, meta={})
    # End of def _run_single_batch
# End of class Sam3TrackerImplementation



def builder(path: Path) -> ModelInterface | None:
    """
    Must be named 'builder' to be discoverable by ModelController.
    Returns the image-only SAM3 tracker implementation.
    """
    try:
        return Sam3TrackerImplementation(model_dir=path)
    except Exception:
        return None
# End of def builder

