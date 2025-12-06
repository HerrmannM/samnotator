# --- --- --- Imports --- --- ---
# STD
from dataclasses import dataclass
import importlib
from pathlib import Path
from typing import Any
# 3RD
from PySide6.QtCore import QObject, QThread, Signal, Slot
from PySide6.QtWidgets import QApplication
# Project
from samnotator.models.interface import ModelInterface, ModelOutput, ModelInterfaceBuilder, InferenceInput
from samnotator.models.torch_worker import create_torch_worker, TorchWorker
from samnotator.datamodel import InstanceID, FrameID


@dataclass(frozen=True, slots=True)
class InferenceRequest:
    request_id: str                             # unique ID for this inference request
    frame_id: FrameID                           # original frame ID (for reference)
    instance_mapping: dict[int, InstanceID]     # Mapping from trask instance_id as int to actual InstanceID
    input_data: InferenceInput                  # input data for inference
# End of dataclass InferenceRequest


@dataclass(frozen=True, slots=True)
class InferenceResult:
    request: InferenceRequest
    result: ModelOutput
# End of dataclass InferenceResponse


class ModelController(QObject):

    # --- --- --- Signals --- --- ---
    # Controller -> worker
    request_model_load = Signal(object, str)        # -> TorchWorker.load_model(model: ModelInterface, device:str)
    request_model_inference = Signal(str, object)   # -> TorchWorker.run_inference(request_id, input_data)
    request_model_unload = Signal()                 # -> TorchWorker.unload_model()

    # Worker -> controller -> OUTSIDE
    result_inference = Signal(InferenceResult)
    result_log = Signal(str)

    
    # --- --- --- Constructor --- --- ---

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        # Fields
        self._worker_thread: tuple[TorchWorker, QThread] | None = None
        self._model_base_packages: list[str] = [ "samnotator.models" ]  # Search order for model modules. Edit/extend this list as needed.
        self._builder_cache: dict[str, ModelInterfaceBuilder] = {}      # Cache model_type -> builder to avoid repeated imports
        self._active_requests:dict[str, InferenceRequest] = {}           # Active inference requests

        # Init
        if (app := QApplication.instance()) is not None:
            app.aboutToQuit.connect(self.unload_model)
        else:
            raise RuntimeError("No QApplication instance found")
    # End of def __init__

    
    # --- --- --- Private Methods --- --- ---

    def _start_worker(self) -> None:
        self._worker_thread = create_torch_worker(self)
        worker = self._worker_thread[0]

        # Controller -> worker
        self.request_model_inference.connect(worker.run_inference)
        self.request_model_unload.connect(worker.unload_model)
        self.request_model_load.connect(worker.load_model)

        # Worker -> controller
        worker.result_inference.connect(self._on_worker_result)
        worker.result_log.connect(self._on_worker_log)
    # End of def _start_worker


    def _stop_worker(self) -> None:
        """Stop current worker and thread, clear references."""
        if self._worker_thread is not None:
            #
            if self._active_requests:
                for req in self._active_requests.values():
                    self.result_log.emit(f"Aborting active inference request {req.request_id} due to model unload")
                self._active_requests.clear()
            #
            worker, thread = self._worker_thread
            # Queued call into worker thread and wait for it. Quit will trigger worker.deleteLater() (see create_torch_worker)
            self.request_model_unload.emit()
            thread.quit()
            thread.wait()
            thread.deleteLater()
            # At this point worker is destroyed, connections are auto-disconnected
            self._worker_thread = None
    # End of def _stop_worker


    def _reset_worker(self) -> None:
        self._stop_worker()
        self._start_worker()
    # End of def _reset_worker

    
    def _get_builder_for_model_type(self, model_type: str) -> ModelInterfaceBuilder:
        """
        Lazily import a model module from the first base package where it exists.

        Tries:
            <base0>.<model_type>
            <base1>.<model_type>
            ...
        and returns its top-level `builder` attribute.
        """
        if model_type in self._builder_cache:
            return self._builder_cache[model_type]

        last_import_error: Exception | None = None

        for base_pkg in self._model_base_packages:
            module_name = f"{base_pkg}.{model_type}"
            print(f"ModelController: trying to import model module '{module_name}'")
            try:
                module = importlib.import_module(module_name)
            except ImportError as e:
                print(e)
                # remember last error, but keep trying others
                last_import_error = e
                continue

            # module imported successfully -> get builder
            try:
                builder_obj = getattr(module, "builder")
            except AttributeError as e:
                raise ValueError(f"Model module '{module_name}' does not define a 'builder' attribute") from e
            if not callable(builder_obj):
                raise TypeError( f"'builder' in module '{module_name}' is not callable")

            builder: ModelInterfaceBuilder = builder_obj  # type: ignore[assignment]
            self._builder_cache[model_type] = builder
            return builder
        #

        # If we get here, no module was found in any base package
        msg = f"Unable to find model module for type '{model_type}'. Tried: {[f'{b}.{model_type}' for b in self._model_base_packages]}"
        if last_import_error is not None:
            msg += f" (last ImportError: {last_import_error!r})"
        raise ValueError(msg)
    # End of def _get_builder_for_model_type


    @Slot(str, ModelOutput)
    def _on_worker_result(self, request_id: str, result: ModelOutput) -> None:
        if request_id in self._active_requests:
            request = self._active_requests.pop(request_id)
            inf_result = InferenceResult(request=request, result=result)
            self.result_inference.emit(inf_result)
        else:
            self.result_log.emit(f"Received inference result for unknown request ID '{request_id}'")
    # End of def _on_worker_result


    @Slot(str)
    def _on_worker_log(self, message: str) -> None:
        self.result_log.emit(f"Worker log: {message}")
    # End of def _on_worker_log

    
    # --- --- --- Public Methods --- --- ---

    def load_model(self, model_type:str, path: Path, device:str) -> None:
        self._reset_worker()
        builder = self._get_builder_for_model_type(model_type)
        if (mi := builder(path)) is not None:
            self.request_model_load.emit(mi, device)
        else:
            raise RuntimeError(f"ModelInterface builder failed for type {model_type} at path {path}")
    # End of def load_model


    def unload_model(self) -> None:
        if self._worker_thread is not None:
            self._stop_worker()
    # End of def unload_model


    def run_inference(self, inference_requested:InferenceRequest) -> None | str:
        """Public inference: emit signal so worker does the work in its thread."""
        if self._worker_thread is None:
            return "No model loaded"
        #
        else:
            self._active_requests[inference_requested.request_id] = inference_requested
            self.request_model_inference.emit(inference_requested.request_id, inference_requested.input_data)
    # End of def run_inference
# End of class ModelController