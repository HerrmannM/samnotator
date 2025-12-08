"""Model selection + inference widget"""
# --- --- --- Imports --- --- ---
# STD
from collections import defaultdict
from pathlib import Path
# 3RD
from PySide6.QtCore import Signal, Slot
from PySide6.QtWidgets import QWidget, QComboBox, QVBoxLayout, QHBoxLayout, QPushButton, QLabel
# Project
from samnotator.app.app_controller import AppController
from samnotator.datamodel import FrameID, PointKind, InstanceID
from samnotator.models.interface import InferenceInput, MaskOutputOptions, PVSBoxPrompt, PVSInstancePrompt, PVSPointPrompt, PVSTask, Task
from samnotator.controllers.model_controller import InferenceRequest, InferenceResult


class ModelRunnerWidget(QWidget):

    # --- --- --- Signals --- --- ---
    result_inference_started = Signal(str)                      # request_id
    result_inference_finished = Signal(InferenceResult)         # inference result
    result_log = Signal(str)                                    # log message

    
    # --- --- --- Constructor --- --- ---

    def __init__(self, app_controller: AppController, model_paths: dict[str, Path], parent: QWidget | None = None):
        super().__init__(parent)

        # Controllers
        self.ctl_app = app_controller
        self.ctl_model = app_controller.ctl_model
        self.ctl_frames = app_controller.ctl_frames
        self.ctl_annotations = app_controller.ctl_annotations

        # Model registry
        self._model_paths: dict[str, Path] = model_paths
        self._model_types: list[str] = list(model_paths.keys())  # keep deterministic order

        # Internal state
        self._model_loaded: bool = False
        self._model_running:bool = False
        self._next_request_id: int = 0

        # Widgets
        self.cbb_model: QComboBox = QComboBox()
        self.btn_load: QPushButton = QPushButton("Load")
        self.btn_unload: QPushButton = QPushButton("Unload")
        self.btn_run: QPushButton = QPushButton("Run")

        # Build UI
        self._init_ui()
    # End of def __init__


    def _init_ui(self) -> None:
        # Connect to model controller
        self.ctl_model.result_inference.connect(self._on_inference_finished)

        # Model combo
        self.cbb_model.setEditable(False)
        self.cbb_model.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self._rebuild_model_list()

        # Buttons
        self.btn_load.clicked.connect(self._on_load_clicked)
        self.btn_unload.clicked.connect(self._on_unload_clicked)
        self.btn_run.clicked.connect(self._on_run_clicked)

        # Initial state: no model loaded
        self._set_loaded_state(False)

        # Layout
        layout = QHBoxLayout()
        layout.addWidget(QLabel("Model:"))
        layout.addWidget(self.cbb_model)
        layout.addWidget(self.btn_load)
        layout.addWidget(self.btn_unload)
        layout.addWidget(self.btn_run)
        layout.addStretch(1)

        outer = QVBoxLayout()
        outer.addLayout(layout)
        self.setLayout(outer)
    # End of def _init_ui



    # --- --- --- Private helpers --- --- ---

    def _log(self, msg:str) -> None:
        print("ModelRunnerWidget:", msg)
        self.result_log.emit(msg)
    # End of def _log


    def _rebuild_model_list(self) -> None:
        """Populate combo from self._model_types / self._model_paths."""
        self.cbb_model.clear()
        self._model_types:list[str] = list(self._model_paths.keys())
        for mtype in self._model_types:
            txt = f"{mtype} {self._model_paths[mtype].name}"
            self.cbb_model.addItem(txt)
        #
        if self._model_types:
            self.cbb_model.setCurrentIndex(0)
        #
    # End of def _rebuild_model_list


    def _set_loaded_state(self, loaded: bool) -> None:
        self.cbb_model.setEnabled(not loaded)
        self.btn_load.setEnabled(not loaded)
        self.btn_unload.setEnabled(loaded)
        self.btn_run.setEnabled(loaded)
        #
        self._model_loaded = loaded
    # End of def _set_loaded_state

    def _set_running_state(self, running: bool) -> None:
        # Can't run without a model, but disable if already running
        active = self._model_loaded and not running
        self.btn_run.setEnabled(active)
        self.btn_unload.setEnabled(active)
        #
        self._model_running = not active
    # End of def _set_loaded_state

    # --- --- --- Slots / callbacks --- --- ---

    @Slot()
    def _on_load_clicked(self) -> None:
        # Get selected model
        model_type_path = self.get_selected_model()
        if model_type_path is None:
            self._log("ModelRunnerWidget: no model selected.")
            return
        model_type, path = model_type_path

        # Delegate to model controller
        try:
            self._set_loaded_state(loaded=True)
            self.ctl_model.load_model(path=path, model_type=model_type, device="cuda")
        except Exception as e:
            self._set_loaded_state(loaded=False)
            self._log(f"ModelRunnerWidget: failed to load model: {e!r}")
            return
    # End of def _on_load_clicked


    @Slot()
    def _on_unload_clicked(self) -> None:
        self.ctl_model.unload_model()
        self._set_loaded_state(loaded=False)
    # End of def _on_unload_clicked


    @Slot()
    def _on_run_clicked(self) -> None:
        model_type_path = self.get_selected_model()
        if model_type_path is None:
            self._log("No model selected")
            return

        frame_id = self.ctl_frames.get_current_frame_id()
        if frame_id is None:
            self._log("No frame")
            return

        try:
            request_id = self._make_request_id(model_type_path[0])
            request = self._build_inference_request(request_id, frame_id)
        except Exception as e:
            self._log(f"ModelRunnerWidget: failed to build InferenceInput: {e!r}")
            return

        if isinstance(request, str):
            self._log(request)
            return

        # Indicate running state and emit started signal
        if (msg := self.ctl_model.run_inference(request)) is not None:
            self._log(f"ModelRunnerWidget: inference request failed: {msg}")
            return
        else:
            self.result_inference_started.emit(request.request_id)
            self._set_running_state(running=True)
    # End of def _on_run_clicked


    @Slot(InferenceResult)
    def _on_inference_finished(self, inf_result: InferenceResult) -> None:
        self._set_running_state(running=False)
        self.result_inference_finished.emit(inf_result)
    # End of def _on_inference_finished


    def _make_request_id(self, model_type: str) -> str:
        rid = self._next_request_id
        self._next_request_id += 1
        return f"{model_type}:{rid}"
    # End of def _make_request_id


    def _build_inference_request(self, request_id: str, frame_id: FrameID) -> InferenceRequest | str:
        # Image path for this frame
        if (image_path := self.ctl_frames.get_frame_path(frame_id)) is None:
            raise RuntimeError("Frame controller returned no image path for requested frame")

        # --- collect point prompts per instance ---
        points_by_inst: dict[InstanceID, list[PVSPointPrompt]] = defaultdict(list)
        for pa in self.ctl_annotations.get_points_for_frame(frame_id): 
            x, y = pa.point.position
            is_positive = (pa.point.kind == PointKind.POSITIVE)
            inst_id: InstanceID = pa.instance_id
            points_by_inst[inst_id].append(PVSPointPrompt(x=x, y=y, is_positive=is_positive))
        # End for pa in ...

        # --- collect at-most-one box per instance ---
        boxes_by_inst: dict[InstanceID, PVSBoxPrompt] = {}
        for ba in self.ctl_annotations.get_bboxes_for_frame(frame_id):
            inst_id: InstanceID = ba.instance_id
            if inst_id in boxes_by_inst:
                raise ValueError(
                    f"More than one bbox for instance {int(inst_id)} on frame {int(frame_id)} "
                    "(SAM2/SAM3 PVS expects at most one box per instance)."
                )

            if ba.bbox.kind == PointKind.POSITIVE:
                x_min, y_min = ba.bbox.top_left
                x_max, y_max = ba.bbox.bottom_right
                boxes_by_inst[inst_id] = PVSBoxPrompt(x_min=x_min, y_min=y_min, x_max=x_max, y_max=y_max)
        # End for ba in ...

        # --- combine into PVS instance prompts ---
        instances: list[PVSInstancePrompt] = []
        imap: dict[int, InstanceID] = {}            # Also create the mapping  numeric_id -> InstanceID
        all_inst_ids: set[InstanceID] = set(points_by_inst.keys()) | set(boxes_by_inst.keys())
        if not all_inst_ids:
            return "No clicks or bounding boxes on this frame"

        # Sort instances by 'str' id for stable ordering
        for numeric_id, inst_id in enumerate(sorted(all_inst_ids, key=str)):
            imap[numeric_id] = inst_id
            instances.append(PVSInstancePrompt(instance_id=numeric_id, points=points_by_inst.get(inst_id, []), box=boxes_by_inst.get(inst_id)))

        # --- build Task -> InferenceInput -> InferenceRequest ---
        # For now, simple default output options (TODO: make configurable in UI)
        output_options = MaskOutputOptions(multimask_output=False, mask_threshold=None, max_masks_per_object=None)
        task: Task = PVSTask(instances=instances, output_options=output_options)

        print( "Inference request built with", sum(len(p.points) for p in instances), "points and", sum(1 for p in instances if p.box is not None), "bboxes on frame", frame_id,)
        print("  image path:", image_path)
        print("  instance mapping:", imap)

        input_data = InferenceInput(image_path=image_path, task=task)
        return InferenceRequest(request_id=request_id, frame_id=frame_id, instance_mapping=imap, input_data=input_data)
    # End of def _build_inference_request


    # --- --- --- Public helpers --- --- ---

    def get_selected_model(self) -> tuple[str, Path] | None:
        """Return the selected model_type,path string, or None if nothing selected."""
        idx = self.cbb_model.currentIndex()
        if idx < 0 or idx >= len(self._model_types):
            return None
        mtype = self._model_types[idx]
        return mtype, self._model_paths[mtype]
    # End of def get_selected_model


    def set_model_selection(self, model_paths: dict[str, Path]) -> None:
        """ Replace the model registry at runtime and rebuild the combo.  Keys = model_type, values = Path.  """
        self._model_paths = model_paths
        self._rebuild_model_list()
    # End of def set_model_selection

    def is_model_loaded(self) -> bool:
        return self._model_loaded
    #

# End of class ModelRunnerWidget