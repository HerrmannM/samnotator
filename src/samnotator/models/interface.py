# --- --- --- Imports --- --- ---
# STD
from pathlib import Path
from typing import Any, Protocol, Callable
from dataclasses import dataclass
from pathlib import Path
# 3RD
import numpy as np
# Project


# --- --- --- Input Task DataClasses --- --- ---

@dataclass(frozen=True, slots=True)
class ClickPrompt:
    """ 
    One user click in image pixel coordinates.  (0, 0) is top-left corner of the image.
    `instance_id` groups clicks that refer to the same object instance.
    """
    x: int                      # pixel coordinate from left
    y: int                      # pixel coordinate from top
    is_positive: bool           # True = positive click, False = negative
    instance_id: int            # integer object identifier (0, 1, 2, ...)
# End of class ClickPrompt


@dataclass(frozen=True, slots=True)
class MaskOutputOptions:
    """
    Options controlling how masks are produced/filtered.
    All are optional at call-site, but you must pass explicit values
    (no dataclass defaults).
    """
    multimask_output: bool              # HF model multimask_output flag
    mask_threshold: float | None        # probability threshold for bbox computation
    max_masks_per_object: int | None    # slice top-k masks per object
# End of class MaskOutputOptions


@dataclass(frozen=True, slots=True)
class ClickSegmentationTask:
    """
    Promptable segmentation with user clicks (multi-object).

    - Each ClickPrompt has an object_id; all clicks with the same object_id
      define one object instance.
    - Supports both positive and negative clicks per object.
    """
    prompts: list[ClickPrompt]
    output_options: MaskOutputOptions
# End of class ClickSegmentationTask




type Task = ClickSegmentationTask


@dataclass(frozen=True, slots=True)
class InferenceInput:
    """
    High-level input for a single inference request.
    One image path (for data access) + one task
    """
    image_path: Path                        # path to local image file (opened as RGB)
    task: Task                              # exactly one of the three task variants above
# End of class InferenceInput



# --- --- --- Output type --- --- ---


@dataclass(frozen=True, slots=True)
class InferenceOutput:
    """
    - input:   original InferenceInput used for this inference
    - masks:   (N, H, W) float32 probabilities in [0, 1]
    - scores:  (N,)      float32 mask quality scores (e.g. IoU)
    - boxes:   (N, 4)    float32 [x_min, y_min, x_max, y_max] in pixels
    - instance_object_ids: (N,) int32 mapping each mask to its object_id
    - meta:    free-form metadata
    """
    masks: np.ndarray
    scores: np.ndarray
    boxes: np.ndarray
    instance_object_ids: np.ndarray
    meta: dict[str, Any]
# End of class InferenceOutput



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

