# --- --- --- Imports --- --- ---
# STD
from dataclasses import dataclass
# 3RD
import numpy as np
from numpy.typing import NDArray
# Project
from .interface import PVSInstancePrompt, MaskOutputOptions


# --- --- --- Sam3 Prompt Batch and Utilities --- --- ---

@dataclass(frozen=True, slots=True)
class Sam3PromptBatch:
    """
    Unified prompt batch for SAM3 (image or video).

    - frame_index: 0 for image; actual frame index for video.
    - input_points: (1, num_objects, num_points_per_object, 2)
    - input_labels: (1, num_objects, num_points_per_object)
    - input_boxes:  (1, num_objects, 4) or None (no boxes in this batch)
    - instance_ids: (num_objects,) int32, object IDs (used as obj_ids in video)
    """
    frame_index: int
    input_points: list
    input_labels: list
    input_boxes: list | None
    instance_ids: NDArray[np.int32]
# End of class Sam3PromptBatch


@dataclass(frozen=True, slots=True)
class Sam3FrameResult:
    masks: NDArray[np.bool]
    scores: NDArray[np.float32]
    boxes: NDArray[np.int32]
    instance_ids: NDArray[np.int32]

    @classmethod
    def empty(cls) -> "Sam3FrameResult":
        return cls( masks=np.zeros((0, 0, 0), dtype=bool), scores=np.zeros((0,), dtype=np.float32), boxes=np.zeros((0, 4), dtype=np.int32), instance_ids=np.zeros((0,), dtype=np.int32))
# End of class Sam3FrameResult


def build_prompt_batches_for_frame( frame_index: int, instances: list[PVSInstancePrompt]) -> dict[str, Sam3PromptBatch]:
    """
    Build up to two Sam3PromptBatch objects for a given frame, from a list of PVSInstancePrompt.

    Instances with neither points nor box are ignored, remaining ones are split into two groups:
      - "with_box":    instances that have a box
      - "without_box": instances that have no box
    """
    # Bucket the instances, skipping instance with no points and no box
    instances_with_box:list[PVSInstancePrompt] = []
    instances_without_box: list[PVSInstancePrompt] = []
    for inst in instances:
        if not inst.points and inst.box is None: continue
        if inst.box is not None: instances_with_box.append(inst)
        else: instances_without_box.append(inst)
    #

    # Batch builder
    def _make_batch(instances: list[PVSInstancePrompt], use_boxes: bool) -> Sam3PromptBatch:
        # Data Layout without batch dimension
        points_per_object: list[list[list[float]]] = [] # (batch=1| num_objects, num_points_per_object, 2)
        labels_per_object: list[list[int]] = []         # (batch=1| num_objects, num_points_per_object)
        boxes_per_object: list[list[float]] = []        # (batch=1| num_objects, 4) OR empty/None
        instance_ids: list[int] = []                    # (batch=1| num_objects) Track IDs to preserve assignment

        # Gather data
        for inst in instances:
            # Instance ID
            instance_ids.append(inst.instance_id)
            # Points & Labels

            # If no points, pad with dummy negative
            pts = [[float(p.x), float(p.y)] for p in inst.points]
            lbls = [1 if p.is_positive else 0 for p in inst.points]
            if not pts:
                pts = [[0.0, 0.0]]
                lbls = [-1]
            points_per_object.append(pts)
            labels_per_object.append(lbls)

            # Boxes
            if use_boxes:
                assert inst.box is not None, "Instance box missing in 'with_box' batch"
                b = inst.box
                boxes_per_object.append([float(b.x_min), float(b.y_min), float(b.x_max), float(b.y_max)])
        #

        # Construct Processor Inputs, wrap in [] for batch dimension
        input_points = [points_per_object]
        input_labels = [labels_per_object]
        input_boxes = [boxes_per_object] if use_boxes else None
        instance_ids_arr = np.asarray(instance_ids, dtype=np.int32)
        return Sam3PromptBatch( frame_index=frame_index, input_points=input_points, input_labels=input_labels, input_boxes=input_boxes, instance_ids=instance_ids_arr)
    # End of internal def _make_batch(

    batches: dict[str, Sam3PromptBatch] = {}
    if instances_with_box:
        batches["with_box"] = _make_batch(instances_with_box, use_boxes=True)

    if instances_without_box:
        batches["without_box"] = _make_batch(instances_without_box, use_boxes=False)

    return batches
# End of function build_prompt_batches_for_frame


def compute_bboxes_from_masks(masks: NDArray[np.bool]) -> NDArray[np.int32]:
    """
    Compute tight axis-aligned bounding boxes from binary masks.

    Args: masks: (N, H, W) boolean array
    Returns: boxes: (N, 4) int32, [x_min, y_min, x_max, y_max]
    """
    if masks.size == 0:
        return np.zeros((0, 4), dtype=np.int32)

    N, H, W = masks.shape
    boxes = np.zeros((N, 4), dtype=np.int32)

    for i in range(N):
        ys, xs = np.where(masks[i])
        if xs.size > 0:
            boxes[i] = [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())]
        # else keep [0, 0, 0, 0]

    return boxes
# End of function compute_bboxes_from_masks


def sort_and_flatten_masks_and_scores(masks: NDArray[np.bool], scores: NDArray[np.float32], instance_ids: NDArray[np.int32], output_options: MaskOutputOptions) -> Sam3FrameResult:
    """
    Sort masks per object by score, apply top-k per object, and flatten.

    Args:
        masks:        (num_objects, num_masks, H, W)
        scores:       (num_objects, num_masks)
        instance_ids: (num_objects,)
        output_options: MaskOutputOptions

    Returns a Sam3FrameResult with:
        masks:  (N_total, H, W) bool
        scores: (N_total,) float32
        boxes:  (N_total, 4) int32
        instance_ids:    (N_total,) int32
    
    where N_total = num_objects * (mask per objects = min(num_masks, max_masks_per_object))
    """
    if masks.size == 0 or scores.size == 0 or instance_ids.size == 0:
        return Sam3FrameResult.empty()

    num_objects, num_masks, H, W = masks.shape

    # 1) sort masks per object by descending score
    sort_idx = np.argsort(-scores, axis=1)  # (num_objects, num_masks)
    obj_idx = np.arange(num_objects)[:, None]
    masks_sorted = masks[obj_idx, sort_idx, :, :]
    scores_sorted = scores[obj_idx, sort_idx]

    # 2) top-k per object
    k = output_options.max_masks_per_object
    if k < num_masks:
        masks_sorted = masks_sorted[:, :k, :, :]
        scores_sorted = scores_sorted[:, :k]
        num_masks = k

    # 3) flatten over objects × masks_per_object, replicate instance ids
    N_total = num_objects * num_masks
    final_masks = masks_sorted.reshape(N_total, H, W)
    final_scores = scores_sorted.reshape(N_total)
    final_ids = np.repeat(instance_ids, num_masks)

    # 4) compute boxes
    final_boxes = compute_bboxes_from_masks(final_masks)

    return Sam3FrameResult(masks=final_masks, scores=final_scores, boxes=final_boxes, instance_ids=final_ids)
# End of function sort_and_flatten_masks_and_scores
