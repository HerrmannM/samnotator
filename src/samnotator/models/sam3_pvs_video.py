# --- --- --- Imports --- --- ---
# STD
from pathlib import Path
from typing import Callable, cast
import logging
# 3RD
import numpy as np
from numpy.typing import NDArray
from PIL import Image
import torch
from transformers import Sam3TrackerVideoModel, Sam3TrackerVideoProcessor, Sam3TrackerVideoInferenceSession
# Project
from .interface import MaskOutputOptions, ModelInterface, ModelOutput, PVSTask, PVSFramePrompt, InferenceInput, InferenceOutput, FrameInferenceOutput, TaskType
from .sam3_utils import build_prompt_batches_for_frame, sort_and_flatten_masks_and_scores

logger = logging.getLogger(__name__)

class Sam3TrackerVideoImplementation(ModelInterface):
    """
    Video SAM3 tracker implementation of ModelInterface, using Sam3TrackerVideoModel / Sam3TrackerVideoProcessor.

    This implementation:
      - Supports only TaskType.PVS.
      - Expects multi-frame video input as a list of frame_paths.
      - Uses PVSTask.frame_prompts (one or more frames) + PVSTask.video_options
      - Clears HF inference session on each run and re-applies *all* prompts.
    """

    # --- --- --- Constructor --- --- ---

    def __init__(self, model_dir: Path) -> None:
        self._model_dir: Path = model_dir.resolve()
        self._name: str = "sam3_pvs_video"
        self._model: Sam3TrackerVideoModel | None = None
        self._processor: Sam3TrackerVideoProcessor | None = None
        self._device: torch.device | None = None
        self._loaded: bool = False
        self._progress_callback: Callable[[float, str|None], None] = lambda progress, msg: None

        # HF video session + signature of the underlying frames
        self._video_session: Sam3TrackerVideoInferenceSession | None = None
        self._video_signature: tuple[str, ...] | None = None
    # End of def __init__


    # --- --- --- ModelInterface implementation --- --- ---

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
        if self._loaded and self._device is not None and str(self._device) == device:
            return
        if self._loaded:
            self.unload()

        self._device = torch.device(device)
        self._model = Sam3TrackerVideoModel.from_pretrained(str(self._model_dir))
        self._model.to(self._device)  # type: ignore[arg-type]
        self._processor = Sam3TrackerVideoProcessor.from_pretrained(str(self._model_dir))
        self._loaded = True

        # Reset video session on load
        self._video_session = None
        self._video_signature = None
    # End of def load


    def unload(self) -> None:
        self._model = None
        self._processor = None
        self._device = None
        self._loaded = False
        self._video_session = None
        self._video_signature = None
        torch.cuda.empty_cache()
    # End of def unload


    def run(self, input_data: InferenceInput) -> ModelOutput:
        """
        Video PVS entrypoint.

        Expects:
          - task_type == TaskType.PVS
          - len(frame_paths) >= 1
          - task.video_options is not None
        """
        if not self.ready():
            return ModelOutput.failure("Sam3TrackerVideoImplementation: model is not loaded or not ready")

        if self._device is None or self._model is None or self._processor is None:
            return ModelOutput.failure("Sam3TrackerVideoImplementation: internal state is inconsistent")

        if input_data.task_type is not TaskType.PVS:
            return ModelOutput.failure(
                f"Sam3TrackerVideoImplementation: unsupported task_type {input_data.task_type!r}"
            )

        task: PVSTask = input_data.task
        frame_paths = input_data.frame_paths

        if not frame_paths:
            return ModelOutput.failure("Sam3TrackerVideoImplementation: no frame_paths provided")

        if task.video_options is None:
            return ModelOutput.failure("Sam3TrackerVideoImplementation: video_options is None, but this is the video implementation")

        # 1) Ensure HF video session matches these frames
        try:
            self._ensure_video_session(frame_paths)
        except Exception as e:
            return ModelOutput.failure(f"Sam3TrackerVideoImplementation: failed to init video session: {e!r}")

        # 2) Clear prompts / state for this inference
        assert self._video_session is not None
        self._video_session.reset_inference_session()

        # 3) Add prompts for all frames from PVSTask.frame_prompts
        try:
            self._apply_all_frame_prompts(task.frame_prompts)
        except Exception as e:
            return ModelOutput.failure(f"Sam3TrackerVideoImplementation: failed to apply frame prompts: {e!r}")

        # 4) Run propagation according to video_options
        try:
            inference_output = self._run_video_propagation(task)
        except Exception as e:
            return ModelOutput.failure(f"Sam3TrackerVideoImplementation: exception during propagation: {e!r}")

        return ModelOutput.success(inference_output)
    # End of def run


    # --- --- --- Video session management --- --- ---

    def _ensure_video_session(self, frame_paths: list[Path]) -> None:
        """
        Ensure that self._video_session is initialized for the given list of frame_paths.

        If a session already exists for exactly the same sequence of paths, it is reused.
        Otherwise, frames are reloaded and a new session is created.
        """
        assert self._processor is not None
        assert self._device is not None

        signature = tuple(str(p.resolve()) for p in frame_paths)
        if self._video_session is not None and self._video_signature == signature:
            return  # reuse existing video_session

        # Load frames as HxWx3 uint8 arrays
        video_frames: list[NDArray[np.uint8]] = []
        for p in frame_paths:
            img = Image.open(p).convert("RGB")
            arr = np.array(img)  # (H, W, 3), uint8
            video_frames.append(arr)

        # Init new video session, use bfloat16 on CUDA by default, fall back to float32 otherwise.
        # dtype = torch.bfloat16 if self._device.type == "cuda" else torch.float32
        dtype = torch.float32
        self._video_session = self._processor.init_video_session(video=video_frames, inference_device=self._device, dtype=dtype)
        self._video_signature = signature
    # End of def _ensure_video_session


    # --- --- --- Prompt application --- --- ---

    def _apply_all_frame_prompts(self, frame_prompts: list[PVSFramePrompt]) -> None:
        """Assume inference_session has just been reset; apply all prompts described in frame_prompts."""
        assert self._processor is not None
        assert self._video_session is not None
        for fp in frame_prompts:
            if not fp.instances: continue
            batches = build_prompt_batches_for_frame(frame_index=fp.frame_index, instances=fp.instances)
            if not batches: continue
            for batch in batches.values():
                self._processor.add_inputs_to_inference_session(
                    inference_session=self._video_session,
                    frame_idx=batch.frame_index,
                    obj_ids=batch.instance_ids.tolist(),
                    input_points=batch.input_points,
                    input_labels=batch.input_labels,
                    input_boxes=batch.input_boxes,
                )
        #
    # End of def _apply_all_frame_prompts


    # --- --- --- Propagation --- --- ---

    def _run_video_propagation(self, task: PVSTask) -> InferenceOutput:
        """
        Run SAM3 propagation across the video using propagate_in_video_iterator,
        respecting task.video_options and task.output_options.

        Returns:
            InferenceOutput with one FrameInferenceOutput per tracked frame_index.
        """
        assert self._model is not None
        assert self._processor is not None
        assert self._video_session is not None

        video_options = task.video_options
        assert video_options is not None

        if self._video_session.num_frames is None or self._video_session.num_frames == 0:
            return InferenceOutput(frame_index_results={})


        # --- Option to args
        start_idx = 0
        if video_options.start_frame_index is not None:
            start_idx = video_options.start_frame_index
        #
        if (max_to_track := video_options.max_frames) is None:
            max_to_track = self._video_session.num_frames
        #
        reverse = video_options.reverse
        #
        total_frames = max_to_track - start_idx


        # --- Post processing data
        # Height/width for post-processing
        original_size = [(self._video_session.video_height, self._video_session.video_width)]
        # obj_ids are the global SAM3 object IDs corresponding to masks order
        obj_ids_np: NDArray[np.int32] = np.asarray(self._video_session.obj_ids, dtype=np.int32)


        # --- Collect per-frame results
        frame_results: dict[int, FrameInferenceOutput] = {}


        # ---Run Model iterator
        iterator = self._model.propagate_in_video_iterator( self._video_session, start_frame_idx=start_idx, max_frame_num_to_track=max_to_track, reverse=reverse)
        for idx, out in enumerate(iterator):
            if out.frame_idx is None:
                continue
            frame_idx: int = out.frame_idx
            self._progress_callback( (idx+1)/total_frames, None)
            # out.pred_masks: raw logits or probabilities in model space
            pred_masks = out.pred_masks

            # HF example: post_process_masks expects a *list* of pred_masks
            post_masks = self._processor.post_process_masks( [pred_masks.detach().cpu()], original_sizes=original_size)[0]

            if isinstance(post_masks, torch.Tensor):
                masks_np: NDArray[np.bool] = post_masks.numpy()  # (num_objects, num_masks, H, W)
            else:
                masks_np = cast(NDArray[np.bool], post_masks)

            # Scores: use out.iou_scores if available, else ones
            if getattr(out, "iou_scores", None) is not None:
                scores_raw = out.iou_scores.detach().cpu().numpy()
                # handle possible batch dimension
                if scores_raw.ndim == 3:
                    # (batch, num_objects, num_masks) -> take batch 0
                    scores_np: NDArray[np.float32] = scores_raw[0].astype(np.float32)
                else:
                    scores_np = scores_raw.astype(np.float32)
            else:
                num_objects, num_masks, _, _ = masks_np.shape
                scores_np = np.ones((num_objects, num_masks), dtype=np.float32)

            # Sort/top-k/flatten and compute boxes
            frame_res = sort_and_flatten_masks_and_scores(
                masks=masks_np,
                scores=scores_np,
                instance_ids=obj_ids_np,
                output_options=task.output_options,
            )

            if frame_res.masks.size == 0:
                frame_results[frame_idx] = FrameInferenceOutput.empty(
                    frame_index=frame_idx,
                    meta={"message": "No masks after sorting/flattening"},
                )
            else:
                frame_results[frame_idx] = FrameInferenceOutput(
                    frame_index=frame_idx,
                    masks=frame_res.masks,
                    scores=frame_res.scores,
                    boxes=frame_res.boxes,
                    instance_ids=frame_res.instance_ids,
                    meta={},
                )

        if not frame_results:
            # No frames produced; return empty structure
            return InferenceOutput(frame_index_results={})

        return InferenceOutput(frame_index_results=frame_results)
    # End of _run_video_propagation
# End of class Sam3TrackerVideoImplementation


def builder(path: Path) -> ModelInterface | None:
    """Must be named 'builder' to be discoverable by ModelController."""
    try:
        return Sam3TrackerVideoImplementation(model_dir=path)
    except Exception:
        return None
