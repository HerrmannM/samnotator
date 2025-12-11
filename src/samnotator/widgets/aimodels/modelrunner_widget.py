"""Model selection + inference widget"""
# --- --- --- Imports --- --- ---
# STD
from collections import defaultdict
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
# 3RD
from PySide6.QtCore import Signal, Slot
from PySide6.QtWidgets import QWidget, QComboBox, QVBoxLayout, QHBoxLayout, QPushButton, QLabel
# Project
from samnotator.app.app_controller import AppController
from samnotator.datamodel import FrameID, PointKind, InstanceID
from samnotator.models.interface import InferenceInput, MaskOutputOptions, PVSBoxPrompt, PVSInstancePrompt, PVSPointPrompt, PVSFramePrompt, PVSTask, TaskType
from samnotator.controllers.model_controller import InferenceRequest, InferenceResult


class ModelKind(StrEnum):
    IMAGE = "image"
    VIDEO = "video"
# End of class ModelKind


@dataclass(frozen=True, slots=True)
class ModelInfo:
    kind:ModelKind
    name:str
    wrapper_name:str
    model_path:Path
# End of class ModelInfo

    

class ModelRunnerWidget(QWidget):

    # --- --- --- Signals --- --- ---
    result_inference_started = Signal(str)                      # request_id
    result_inference_finished = Signal(InferenceResult)         # inference result
    result_log = Signal(str)                                    # log message

    
    # --- --- --- Constructor --- --- ---

    def __init__(self, app_controller: AppController, models:list[ModelInfo], parent: QWidget | None = None):
        super().__init__(parent)

        # Controllers
        self.ctl_app = app_controller
        self.ctl_model = app_controller.ctl_model
        self.ctl_frames = app_controller.ctl_frames
        self.ctl_annotations = app_controller.ctl_annotations

        # Model registry
        self.models:dict[str, list[ModelInfo]] = defaultdict(list)
        for m in models:
            self.models[m.kind.value].append(m)
        #

        # Internal state
        self._model_loaded: bool = False
        self._model_running:bool = False
        self._next_request_id: int = 0

        # Widgets
        self.cbb_kind: QComboBox = QComboBox()
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

        # Kind combo
        self.cbb_kind.setEditable(False)
        self.cbb_kind.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.cbb_kind.addItems([ModelKind.IMAGE, ModelKind.VIDEO])
        self.cbb_kind.setCurrentIndex(0)
        self.cbb_kind.currentIndexChanged.connect(self._on_select_kind_changed)
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

        # Model selection layout
        m_layout = QHBoxLayout()
        m_layout.addWidget(QLabel("Model:"))
        m_layout.addWidget(self.cbb_kind)
        m_layout.addWidget(self.cbb_model)
        m_layout.addStretch(1)
        # Run Layout
        r_layout = QHBoxLayout()
        r_layout.addWidget(self.btn_load)
        r_layout.addWidget(self.btn_unload)
        r_layout.addWidget(self.btn_run)
        r_layout.addStretch(1)

        outer = QVBoxLayout()
        outer.addLayout(m_layout)
        outer.addLayout(r_layout)
        self.setLayout(outer)
    # End of def _init_ui



    # --- --- --- Private helpers --- --- ---

    def _log(self, msg:str) -> None:
        print("ModelRunnerWidget:", msg)
        self.result_log.emit(msg)
    # End of def _log


    def _rebuild_model_list(self) -> None:
        """Populate combo"""
        self.cbb_model.clear()
        models = self.models.get(self.cbb_kind.currentText(), [])
        for m in models:
            txt = f"{m.name}"
            self.cbb_model.addItem(txt)
        #
        if models:
            self.cbb_model.setCurrentIndex(0)
            self.btn_load.setEnabled(True)
        else:
            self.btn_load.setEnabled(False)
        #
    # End of def _rebuild_model_list


    def _set_loaded_state(self, loaded: bool) -> None:
        self.cbb_kind.setEnabled(not loaded)
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
    def _on_select_kind_changed(self) -> None:
        self._rebuild_model_list()
    # End of def _on_select_kind_changed


    @Slot()
    def _on_load_clicked(self) -> None:
        # Get selected model
        model_type_path = self.get_selected_model()
        if model_type_path is None:
            self._log("ModelRunnerWidget: no model selected.")
            return
        wrapper_name = model_type_path.wrapper_name
        path = model_type_path.model_path

        # Delegate to model controller
        try:
            self._set_loaded_state(loaded=True)
            self.ctl_model.load_model(path=path, wrapper_name=wrapper_name, device="cuda")
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
        model_info = self.get_selected_model()
        if model_info is None:
            self._log("No model selected")
            return

        frame_id = self.ctl_frames.get_current_frame_id()
        if frame_id is None:
            self._log("No frame")
            return

        try:
            request_id = self._make_request_id(model_info.name)
            request = self._build_image_inference_request(request_id, frame_id)
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


    def _build_image_inference_request(self, request_id: str, frame_id: FrameID) -> InferenceRequest | str:
        # Image path for this frame
        if (image_path := self.ctl_frames.get_frame_path(frame_id)) is None:
            raise RuntimeError("Frame controller returned no image path for requested frame")

        # --- collect point prompts per instance ---
        points_by_inst: dict[InstanceID, list[PVSPointPrompt]] = defaultdict(list)
        for pa in self.ctl_annotations.get_points_for_frame(frame_id):
            x, y = pa.point.position
            is_positive = (pa.point.kind == PointKind.POSITIVE)
            inst_id: InstanceID = pa.instance_id
            points_by_inst[inst_id].append( PVSPointPrompt(x=x, y=y, is_positive=is_positive))
        # End for pa in ...


        # --- collect at-most-one box per instance ---
        boxes_by_inst: dict[InstanceID, PVSBoxPrompt] = {}
        for ba in self.ctl_annotations.get_bboxes_for_frame(frame_id):
            if ba.bbox.kind == PointKind.POSITIVE:
                inst_id: InstanceID = ba.instance_id
                if inst_id in boxes_by_inst:
                    raise ValueError( f"More than one bbox for instance {int(inst_id)} on frame {int(frame_id)} (PVS expects at most one box per instance).")
                x_min, y_min = ba.bbox.top_left
                x_max, y_max = ba.bbox.bottom_right
                boxes_by_inst[inst_id] = PVSBoxPrompt(x_min=x_min, y_min=y_min, x_max=x_max, y_max=y_max)
            else:
                self._log(f"Warning: ignoring negative bbox for instance {int(inst_id)} on frame {int(frame_id)}")
        # End for ba in ...


        # --- combine into PVS instance prompts ---
        instances: list[PVSInstancePrompt] = []
        imap: dict[int, InstanceID] = {}  # numeric_id -> InstanceID
        all_inst_ids: set[InstanceID] = set(points_by_inst.keys()) | set(boxes_by_inst.keys())
        if not all_inst_ids:
            return "No clicks or bounding boxes on this frame"

        # Sort instances by 'str' id for stable ordering
        for numeric_id, inst_id in enumerate(sorted(all_inst_ids, key=str)):
            imap[numeric_id] = inst_id
            instances.append( PVSInstancePrompt( instance_id=numeric_id, points=points_by_inst.get(inst_id, []), box=boxes_by_inst.get(inst_id)))

        # --- build Task -> InferenceInput -> InferenceRequest ---
        # For now, simple default output options (TODO: make configurable in UI)
        output_options = MaskOutputOptions()

        # Image mode: one frame prompt, frame_index = 0 by convention
        frame_prompt = PVSFramePrompt(frame_index=0, instances=instances)

        # No video options for this widget (image-only)
        task = PVSTask(frame_prompts=[frame_prompt], video_options=None, output_options=output_options)

        print("Inference request built with", sum(len(p.points) for p in instances), "points and", sum(1 for p in instances if p.box is not None), "bboxes on frame", frame_id)
        print("  image path:", image_path)
        print("  instance mapping:", imap)

        input_data = InferenceInput(task_type=TaskType.PVS, task=task, frame_paths=[image_path])

        return InferenceRequest(request_id=request_id, frame_mapping={0: frame_id}, instance_mapping=imap, input_data=input_data)
    # End of def _build_image_inference_request


    # --- --- --- Public helpers --- --- ---

    def get_selected_model(self) -> ModelInfo | None:
        """Return the selected model_type,path string, or None if nothing selected."""
        models = self.models.get(self.cbb_kind.currentText(), [])
        idx = self.cbb_model.currentIndex()
        if idx < 0 or idx >= len(models):
            return None
        return models[idx]
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