# --- --- --- Imports --- --- ---
# STD
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol, Callable
# 3RD
import numpy as np
from numpy.typing import NDArray
# Project



# --- --- --- Mask Output Options --- --- ---
@dataclass(frozen=True, slots=True)
class MaskOutputOptions:
    """ Options controlling how masks are produced/filtered.  """
    max_masks_per_object: int = 1   # slice top-k masks per object
# End of class MaskOutputOptions



# --- --- --- PVS --- --- ---
# Promptable Visual Segmentation (PVS)
# "Classic" SAM2/SAM3 worflow with positive/negative clicks and optional box
@dataclass(frozen=True, slots=True)
class PVSPointPrompt:
    """Positive or negative point in image pixel coordinates from top left corner (0,0)."""
    x: int                      # pixel coordinate from left
    y: int                      # pixel coordinate from top
    is_positive: bool           # True = positive click, False = negative
# End of class PVSPointPrompt


@dataclass(frozen=True, slots=True)
class PVSBoxPrompt:
    """Bounding box (assumed positive) in image pixel coordinates from top left corner (0,0)."""
    x_min: int
    y_min: int
    x_max: int
    y_max: int
# End of class PVSBoxPrompt


@dataclass(frozen=True, slots=True)
class PVSInstancePrompt:
    """ Prompt for one object instance in Promptable Visual Segmentation (PVS). """
    instance_id: int                    # integer object identifier (0, 1, 2, ...)
    points: list[PVSPointPrompt]        # zero or more point prompts
    box: PVSBoxPrompt | None            # at most one box per instance
# End of class PVSInstancePrompt


@dataclass(frozen=True, slots=True)
class PVSFramePrompt:
    """ Prompt for one frame in video PVS (SAM2/SAM3 tracker style). """
    frame_index: int                    # zero-based frame index in video. Index, not FrameID! Always 0 for image.
    instances: list[PVSInstancePrompt]  # zero or more instance prompts for this frame
# End of class PVSFramePrompt


@dataclass(frozen=True, slots=True)
class PVSVideoOption:
    """ Options specific to video PVS mode. """
    start_frame_index: int|None = None
    max_frames: int|None = None
    reverse: bool = False
# End of class PVSVideoOption


@dataclass(frozen=True, slots=True)
class PVSTask:
    """ Promptable Visual Segmentation Task, SAM2/SAM3 tracker style. Both for images and videos."""
    frame_prompts: list[PVSFramePrompt]        # one or more frame prompts (for images, just one frame)
    video_options: PVSVideoOption | None       # video-specific options (None = image PVS)
    output_options: MaskOutputOptions
# End of class PVSTask


    
class TaskType(StrEnum):
    PVS = "PVSTask"


@dataclass(frozen=True, slots=True)
class InferenceInput:
    """High-level input for a single inference request. One or more frames (image or video) + one task."""
    task_type: TaskType
    task: PVSTask
    frame_paths:list[Path]
# End of class InferenceInput


# --- --- --- Output type --- --- ---


@dataclass(frozen=True, slots=True)
class FrameInferenceOutput:
    """
    - frame_index: int   zero-based frame index (not FrameID) in video. Always 0 for image.
    - masks:   (N, H, W)    bool masks
    - scores:  (N,)         float32 mask quality scores
    - boxes:   (N, 4)       int32 [x_min, y_min, x_max, y_max] in pixels
    - instance_ids: (N,)    int32 mapping each mask to its object_id
    - meta:    free-form metadata
    """
    frame_index:int
    masks: NDArray[np.bool]
    scores: NDArray[np.float32]
    boxes: NDArray[np.int32]
    instance_ids: NDArray[np.int32]
    meta : dict[str, Any]

    @classmethod
    def empty(cls, frame_index: int, meta: dict[str, Any]) -> FrameInferenceOutput:
        return FrameInferenceOutput(
            frame_index=frame_index,
            masks=np.zeros((0, 0, 0), dtype=bool),
            scores=np.zeros((0,), dtype=np.float32),
            boxes=np.zeros((0, 4), dtype=np.int32),
            instance_ids=np.zeros((0,), dtype=np.int32),
            meta=meta
        )
# End of class InferenceOutput


@dataclass(frozen=True, slots=True)
class InferenceOutput:
    """ High-level output for a single inference request. One output per frame index (not FrameID)."""
    frame_index_results: dict[int, FrameInferenceOutput]

# --- --- --- Model Interface --- --- ---


@dataclass(frozen=True, slots=True)
class ModelOutput:
    error: str|None
    data: InferenceOutput | None

    @property
    def ok(self) -> bool:
        return self.error is None

    @staticmethod
    def success(data: InferenceOutput) -> ModelOutput:
        return ModelOutput(error=None, data=data)

    @staticmethod
    def failure(error: str) -> ModelOutput:
        return ModelOutput(error=error, data=None)
# End of class InferenceResult


class ModelInterface(Protocol):
    
    def name(self) -> str:
        ...
    #


    def ready(self) -> bool:
        ...
    #


    def load(self, device:str) -> None:
        """Called only from the worker thread. Must setup all heavy resources on the given device."""
        ...
    #


    def unload(self) -> None: 
        """Called only from the worker thread. Must free heavy resources (drop model refs, tokenizer, etc.)."""
        ...
    #


    def run(self, input:InferenceInput) -> ModelOutput:
        """Called only from the worker thread.  Must return an InferenceResult."""
        ...
    #
# End of class Protocol ModelInterface


type ModelInterfaceBuilder = Callable[[Path], ModelInterface|None]

