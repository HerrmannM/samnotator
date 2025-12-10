# --- --- --- Imports --- --- ---
# STD
from pathlib import Path
from typing import Any, Protocol, Callable
from dataclasses import dataclass
from pathlib import Path
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
class PVSTask:
    """ Promptable Visual Segmentation Task, SAM2/SAM3 tracker style. """
    instances: list[PVSInstancePrompt]
    output_options: MaskOutputOptions
# End of class PVSTask


type Task = PVSTask


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
    - masks:   (N, H, W)    bool masks
    - scores:  (N,)         float32 mask quality scores (e.g. IoU)
    - boxes:   (N, 4)       float32 [x_min, y_min, x_max, y_max] in pixels
    - instance_object_ids: (N,) int32 mapping each mask to its object_id
    - meta:    free-form metadata
    """
    masks: NDArray[np.bool]
    scores: NDArray[np.float32]
    boxes: NDArray[np.int32]
    instance_object_ids: NDArray[np.int32]
    meta : dict[str, Any]

    @classmethod
    def empty(cls, meta: dict[str, Any]) -> InferenceOutput:
        return InferenceOutput(
            masks=np.zeros((0, 0, 0), dtype=bool),
            scores=np.zeros((0,), dtype=np.float32),
            boxes=np.zeros((0, 4), dtype=np.int32),
            instance_object_ids=np.zeros((0,), dtype=np.int32),
            meta=meta
        )
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

