"""Instance table model for the Instances component.
Models the data to be displayed in the instance table view, associated logic and custom roles.
"""
# --- --- --- Imports --- --- ---
# STD
from typing import Any
from enum import IntEnum
# 3RD
from PySide6.QtCore import Qt, QAbstractTableModel, QModelIndex, QObject, Slot
from PySide6.QtGui import QColor
# Project
from samnotator.controllers.instance_controller import InstanceController, InstanceID, InstanceInfo, Instance
from samnotator.utils._CUD import CUD


# --- --- --- Constants --- --- ---

# Columns Indexes
class Columns(IntEnum):
    VISIBLE = 0
    NAME = 1
    CATEGORY = 2
    COLOR = 3
# End of class Columns


# Column Header Labels
HEADER_LABELS:dict[int, str] = {
    Columns.VISIBLE: "Visible",
    Columns.NAME: "Instance",
    Columns.CATEGORY: "Category",
    Columns.COLOR: "Colour",
}


# Custom roles for the visibility delegate, to be defined 'after' UserRole
ROLE_MARK_VISIBLE = int(Qt.ItemDataRole.UserRole) + 1
ROLE_MASK_VISIBLE = int(Qt.ItemDataRole.UserRole) + 2


# --- --- --- InstanceTableModel --- --- ---

class InstanceTableModel(QAbstractTableModel):

    # --- --- --- Constructor --- --- ---

    def __init__(self, controller: InstanceController, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._controller = controller
        self._instance_ids: list[InstanceID] = self._controller.all_instance_ids()
    # End of def __init__


    # --- --- --- Helpers --- --- ---

    def instance_id_at_row(self, row: int) -> InstanceID:
        return self._instance_ids[row]
    # End of def instance_id_at_row

    def instance_info_at_row(self, row: int) -> InstanceInfo:
        return self._controller.get(self._instance_ids[row])
    # End of def instance_info_for_row

    def row_of_instance_id(self, instance_id: InstanceID) -> int | None:
        try:
            return self._instance_ids.index(instance_id)
        except ValueError:
            return None
    # End of def row_of_instance_id
    
    # --- --- --- Controller callbacks --- --- ---

    @Slot(object, CUD)
    def handle_instance_changed(self, instance_id: InstanceID, cud: CUD) -> None:
        """
        - CREATE: insert one row at the right sorted position
        - DELETE: remove that row
        - UPDATE: emit dataChanged for that row (no structural change)
        """
        match cud:

            case CUD.CREATE:
                # recompute sorted IDs and find where the new one ends up
                new_ids = self._controller.all_instance_ids()
                row = new_ids.index(instance_id)
                self.beginInsertRows(QModelIndex(), row, row)
                self._instance_ids = new_ids
                self.endInsertRows()
            #

            case CUD.DELETE if instance_id in self._instance_ids:
                row = self._instance_ids.index(instance_id)
                self.beginRemoveRows(QModelIndex(), row, row)
                self._instance_ids.pop(row)
                self.endRemoveRows()
            #

            case CUD.UPDATE if instance_id in self._instance_ids:
                row = self._instance_ids.index(instance_id)
                top_left = self.index(row, 0)
                bottom_right = self.index(row, self.columnCount() - 1)
                # reflect external updates (e.g. from other widgets)
                self.dataChanged.emit(top_left, bottom_right)
            #

            case _:
                return None
    # End of def handle_instance_changed

    
    # --- --- --- Qt model API/overrids --- --- ---

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid(): return 0 # No child rows
        return len(self._instance_ids)
    # End of def rowCount


    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid(): return 0 # No child columns
        return 4
    #


    def index(self, row: int, column: int, parent: QModelIndex = QModelIndex()) -> QModelIndex:
        """Creates a QModelIndex (a pointer) for a given row and column, which views use to request specific data points."""
        if parent.isValid(): return QModelIndex() # No child items
        if not (0 <= row < self.rowCount()): return QModelIndex()
        if not (0 <= column < self.columnCount()): return QModelIndex()
        return self.createIndex(row, column)
    # End of def index


    def data(self, index: QModelIndex, role:Qt.ItemDataRole|int = Qt.ItemDataRole.DisplayRole) -> Any:
        """The core method for providing data. Returns the value for a specific cell and a specific data role (display text, edit value, custom visibility state, etc...)."""
        # Check Index
        if not index.isValid():
            return None

        row = index.row()
        col = index.column()
        if not (0 <= row < len(self._instance_ids)):
            return None

        # Get instance info
        info:InstanceInfo = self.instance_info_at_row(row)
        instance:Instance = info.instance

        # Per column/role data
        match col:
            case Columns.VISIBLE:
                if int(role) == ROLE_MARK_VISIBLE:
                    return bool(info.show_markers)
                if int(role) == ROLE_MASK_VISIBLE:
                    return bool(info.show_mask)
                return None
            #

            case Columns.NAME:
                if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole):
                    return instance.instance_name
                return None
            #

            case Columns.CATEGORY:
                if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole):
                    return instance.category_name
                return None
            #

            case Columns.COLOR:
                if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole):
                    return QColor(instance.instance_colour)
                return None
            #

            case _: return None
        # End of match col
    # End of def data


    def setData(self, index: QModelIndex, value: Any, role: Qt.ItemDataRole|int = Qt.ItemDataRole.EditRole) -> bool:
        """Allows the view to modify the underlying data source when a user edits a cell in an editable column."""
        # Check index
        if not index.isValid():
            return False
        row = index.row()
        col = index.column()
        if not (0 <= row < len(self._instance_ids)):
            return False

        instance_id = self._instance_ids[row]

        # Visibility toggles
        match col:
            case Columns.VISIBLE:
                if role == ROLE_MARK_VISIBLE:
                    self._controller.update_instance(instance_id, show_markers=bool(value))
                    self.dataChanged.emit(index, index, [ROLE_MARK_VISIBLE])
                    return True
                if role == ROLE_MASK_VISIBLE:
                    self._controller.update_instance(instance_id, show_mask=bool(value))
                    self.dataChanged.emit(index, index, [ROLE_MASK_VISIBLE])
                    return True
                return False
            #

            case Columns.NAME if role == Qt.ItemDataRole.EditRole:
                self._controller.update_instance(instance_id, name=str(value))
                self.dataChanged.emit(index, index, [int(Qt.ItemDataRole.DisplayRole), int(Qt.ItemDataRole.EditRole)])
                return True
            #

            case Columns.CATEGORY if role == int(Qt.ItemDataRole.EditRole):
                self._controller.update_instance(instance_id, category_name=str(value))
                self.dataChanged.emit(index, index, [int(Qt.ItemDataRole.DisplayRole), int(Qt.ItemDataRole.EditRole)])
                return True
            #

            case Columns.COLOR if role == int(Qt.ItemDataRole.EditRole):
                if isinstance(value, QColor):
                    self._controller.update_instance(instance_id, colour=value)
                    self.dataChanged.emit(index, index, [int(Qt.ItemDataRole.DisplayRole), int(Qt.ItemDataRole.EditRole)])
                    return True
                return False
            #
        return False
    # End of def setData


    def flags(self, index: QModelIndex) -> Qt.ItemFlag:
        """Defines the capabilities of each cell (e.g., can it be selected, enabled, or edited?)"""
        # Check index
        if not index.isValid(): return Qt.ItemFlag.NoItemFlags
        # Base flag for all cells
        base = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        # Per-column flags
        match index.column():
            case Columns.VISIBLE | Columns.NAME | Columns.CATEGORY | Columns.COLOR:
                return base | Qt.ItemFlag.ItemIsEditable
            case _: return base
    # End of def flags


    def headerData(self, section: int, orientation: Qt.Orientation, role:Qt.ItemDataRole|int = Qt.ItemDataRole.DisplayRole) -> Any:
        """Provides the text labels for the horizontal headers ("Vis", "Instance", "Category", "Color")."""
        if role != int(Qt.ItemDataRole.DisplayRole): return None
        if orientation == Qt.Orientation.Horizontal: return HEADER_LABELS.get(section, None)
        return None
    # End of def headerData
# End of class InstanceTableModel