# --- --- --- Imports --- --- ---
# STD
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol
# 3RD
from PySide6.QtCore import QObject, Signal, QSize
from PySide6.QtGui import QImageReader, QImage
# Project
from samnotator.datamodel import FrameID



# --- --- --- Frame Loading --- --- ---


@dataclass(frozen=True, slots=True)
class ImageInfo:
    width:int
    height:int


@dataclass(frozen=True, slots=True)
class FrameInfoVideo:
    frame_index:int
    frame_count:int
    fps:float|None = None


class FrameStub(Protocol):
    def load_data(self) -> QImage: ...
    """Load on call and return the frame image data."""

    def load_info(self) -> str: ...
    """Loading information, e.g. path or video path with frame number."""

    def image_info(self) -> ImageInfo: ...
    """Get info about the image, potentially without loading full data."""

    def video_info(self) -> FrameInfoVideo | None: ...
    """Get video-related info if applicable, else None."""
# End of class FrameStub


@dataclass(frozen=True, slots=True)
class FrameSubImplPath(FrameStub):
    path:Path
    iinfo:ImageInfo
    viinfo:FrameInfoVideo | None = None

    def load_data(self) -> QImage:
        return QImage(self.path)
    
    def load_info(self) -> str:
        return f"{str(self.path)}"
    
    def image_info(self) -> ImageInfo:
        return self.iinfo
    
    def video_info(self) -> FrameInfoVideo | None:
        return self.viinfo
# End of class FrameSubImplPath


def frame_stub_from_paths(paths: list[Path], is_video: bool, fps: float | None) -> list[FrameStub]:
    """Load frames from given image paths, maintaining order.  Skip unreadable images. Return a list of FrameStub."""
    # 1) Collect readable images
    # Header check (no full load, can still fail): https://doc.qt.io/qt-6/qimagereader.html#canRead
    valid: list[tuple[Path, QSize]] = []
    for path in paths:
        reader = QImageReader(str(path))
        if not reader.canRead():
            continue
        size = reader.size()
        if size.isEmpty() or not size.isValid():
            continue
        valid.append((path, size))

    # 2) Build stubs from valid images only 
    frame_count = len(valid)
    stubs: list[FrameStub] = []
    for idx, (path, size) in enumerate(valid):
        image_info = ImageInfo(width=size.width(), height=size.height())
        video_info = None
        if is_video:
            video_info = FrameInfoVideo(frame_index=idx, frame_count=frame_count, fps=fps)
        stub = FrameSubImplPath(path=path, iinfo=image_info, viinfo=video_info)
        stubs.append(stub)

    return stubs
#



# --- --- --- Frame Controller --- --- ---

@dataclass(frozen=True, slots=True)
class FrameInfo:
    frame_id: FrameID
    width: int
    height: int
# End of class FrameInfo


class FrameController(QObject):

    current_frame_changed = Signal(object) # FrameID|None

    def __init__(self, parent:QObject|None=None):
        super().__init__(parent)
        # Fields
        self.frameid_2_stub_index:dict[FrameID, tuple[FrameStub, int]] = {}
        self.frame_sequence: list[FrameID] = []
        self.current_frame_index: int | None = None  # Index in frame_sequence, not FrameID!
        # Reset
        self.reset(None)
    # End of def __init__


    # --- --- --- Private helpers --- --- ---

    def _id_to_index(self, frame_id:FrameID) -> int:
        if (stub_index := self.frameid_2_stub_index.get(frame_id)) is None:
            raise ValueError(f"Frame ID {frame_id} not found.")
        return stub_index[1]
    # End of def _id_to_index


    def _set_current_frame_index(self, index:int|None) -> FrameID|None:
        """Set the current frame index to the given index, or None to clear. Emit frame_changed signal if changed."""
        if index is not None:
            if index < 0 or index >= len(self.frame_sequence):
                raise IndexError(f"Frame index {index} out of range.")
        # Also handles 'None' cases
        if self.current_frame_index != index:
            self.current_frame_index = index
            fid = self.get_current_frame_id()
            self.current_frame_changed.emit(fid)
        else:
            fid = self.get_current_frame_id()
        return fid
        #
    # End of def _set_current_frame_index
    

    # --- --- --- Public methods --- --- ---

    def __len__(self) -> int:
        """ Return the number of frames loaded. No signal emitted."""
        return len(self.frame_sequence)
    # End of def __len__


    def reset(self, stubs:list[FrameStub]|None):
        """Reset the frame controller with the given list of FrameStubs, or None to clear all frames. Emit frame_changed signal."""
        self.frameid_2_stub_index:dict[FrameID, tuple[FrameStub, int]] = {}
        self.frame_sequence: list[FrameID] = []
        self.current_frame_index = None
        #
        if stubs is not None:
            for i, stub in enumerate(stubs, start=0):
                frame_id = FrameID(i)
                self.frameid_2_stub_index[frame_id] = stub, len(self.frame_sequence) # store stub and its index (without relying on it 'i' if we late change how we generate IDs, have an offset, etc...)
                self.frame_sequence.append(frame_id)
            if len(self.frame_sequence) > 0: # Set to first frame, else is None
                self.current_frame_index = 0
        #
        self.current_frame_changed.emit(self.get_current_frame_id())
    # End of def reset

    
    def set_current_frame_id(self, frame_id:FrameID|None) -> None:
        """ Set the current frame to the given frame ID, or None to clear. Emit frame_changed signal if changed."""
        if frame_id is None:
            self._set_current_frame_index(None)
        else:
            self._set_current_frame_index(self._id_to_index(frame_id))
    # End of def set_current_frame_id


    def get_current_frame_id(self) -> FrameID | None:
        """ Return the current frame info, or None if no frame loaded. No signal emitted."""
        if self.current_frame_index is None:
            return None
        return self.frame_sequence[self.current_frame_index]
    # End of def get_current_frame_id


    def get_frame_data(self, frame_id:FrameID) -> QImage:
        """ Load and return the image data for the given frame ID, or None if not found. No signal emitted."""
        if (stub_tuple := self.frameid_2_stub_index.get(frame_id)) is None:
            raise ValueError(f"Frame ID {frame_id} not found.")
        return stub_tuple[0].load_data()
    # End of def get_frame_data

    
    def get_frame_path(self, frame_id:FrameID) -> Path|None:
        """ Return the file path for the given frame ID, or None if not applicable. No signal emitted."""
        if (stub_tuple := self.frameid_2_stub_index.get(frame_id)) is None:
            raise ValueError(f"Frame ID {frame_id} not found.")
        stub = stub_tuple[0]
        if isinstance(stub, FrameSubImplPath):
            return stub.path
        return None
    # End of def get_frame_path


    def frame_info(self, frame_id:FrameID) -> FrameInfo:
        """ Return the FrameInfo for the given frame ID, or None if not found. No signal emitted."""
        if (stub_tuple := self.frameid_2_stub_index.get(frame_id)) is None:
            raise ValueError(f"Frame ID {frame_id} not found.")
        stub_info =stub_tuple[0].image_info()
        frame_info = FrameInfo(frame_id=frame_id, width=stub_info.width, height=stub_info.height)
        return frame_info
    # End of def frame_info


    def frame_load_info(self, frame_id:FrameID) -> str:
        """ Return a string representation for the given frame ID, or None if not found. No signal emitted."""
        if (stub_indx := self.frameid_2_stub_index.get(frame_id)) is None:
            raise ValueError(f"Frame ID {frame_id} not found.")
        return stub_indx[0].load_info()
    # End of def frame_load_info

    # --- --- --- Navigation helpers --- --- ---

    def next_frame(self) -> FrameID|None:
        """ Move to the next frame if possible. Emit frame_changed signal if changed."""
        if self.current_frame_index is None:
            return None
        new_index = self.current_frame_index + 1
        if new_index < len(self.frame_sequence):
            return self._set_current_frame_index(new_index)
        return self.get_current_frame_id()
    # End of def next_frame


    def previous_frame(self) -> FrameID|None:
        """ Move to the previous frame if possible. Emit frame_changed signal if changed."""
        if self.current_frame_index is None:
            return None
        new_index = self.current_frame_index - 1
        if new_index >= 0:
            return self._set_current_frame_index(new_index)
        return self.get_current_frame_id()
    # End of def previous_frame
    

    # --- --- --- File/Folder helper --- --- ---
    
    def open_images(self, paths:list[Path], image_extensions:set[str]|Literal["ALLEXT"] | None=None):
        """
        Open the given list of file paths as frames. Reset current frames. Emit frame_changed signal.

        By default (image_extensions=None), filter for common image extensions : {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif", ".gif", ".webp"}
        Else, provide a set of extensions (with leading dot) to filter - filering is case-insensitive.
        Use image_extensions="ALLEXT" to load all files in the folder without filtering.
        """
        if image_extensions != "ALLEXT":
            if image_extensions is None:
                image_extensions = {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif", ".gif", ".webp"}
            else:
                image_extensions = set(ext.lower() for ext in image_extensions)
            #
            paths = [p for p in paths if p.suffix.lower() in image_extensions and p.is_file()]
        # Make stubs
        stubs = frame_stub_from_paths(paths, is_video=False, fps=None)
        self.reset(stubs)
    # End of def open_images


    def open_folder(self, folder_path:Path, image_extensions:set[str]|Literal["ALLEXT"] | None=None):
        """
        Open all images in the given folder path as frames, sorting them alphabetically. Reset current frames. Emit frame_changed signal.

        See open_images() for image_extensions parameter.
        """
        paths = [p for p in sorted(folder_path.iterdir()) if p.is_file()]
        self.open_images(paths, image_extensions=image_extensions)
    # End of def open_folder


    
# End of class FrameController