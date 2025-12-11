# --- --- --- Imports --- --- ---
# STD
from typing import Any
# 3RD
from PySide6.QtCore import QObject, QThread, Signal, Slot
# Project
from samnotator.models.interface import ModelOutput, ModelInterface



# --- --- --- TorchWorker --- --- ---

class TorchWorker(QObject):
    result_log = Signal(str)
    result_inference = Signal(str, ModelOutput)

    # --- --- --- Constructor --- --- ---

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._model:ModelInterface | None = None
    # End of def __init_


    # --- --- --- Interface --- --- ---

    @Slot(object, str)
    def load_model(self, mi:ModelInterface, device:str) -> None:
        try:
            self._model = mi
            self._model.load(device)
        except Exception as e:
            self.result_log.emit(f"TorchWorker.load_model() exception: {e!r}")
    # End of def load_model


    @Slot()
    def unload_model(self) -> None:
        if self._model is not None and self._model.ready():
            self._model.unload()
            self._model = None
    # End of def unload_model

    
    @Slot(str, object)
    def run_inference(self, request_id: str, input_data: Any) -> None:
        if self._model is None or not self._model.ready():
            result = ModelOutput.failure("No model loaded")
            self.result_inference.emit(request_id, result)
            return
        #
        try:
            result = self._model.run(input_data)
        except Exception as e:
            result = ModelOutput.failure(f"Model run exception: {e!r}")
        self.result_inference.emit(request_id, result)
    # End of def run_inference
# End of class TorchWorker


def create_torch_worker(parent:QObject) -> tuple[TorchWorker, QThread]:
    thread = QThread(parent=parent)
    worker = TorchWorker()
    worker.moveToThread(thread)
    thread.finished.connect(worker.unload_model) # Ensure model is unloaded when thread finishes
    thread.finished.connect(worker.deleteLater) 
    thread.start()
    return worker, thread
# End of def create_torch_worker
