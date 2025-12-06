# --- --- --- Imports --- --- ---
# STD
# 3RD
from PySide6.QtCore import QSize, QModelIndex
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTableView
# Project
from samnotator.controllers.instance_controller import InstanceController
from samnotator.utils_qt.colours import ColourGenerator
from .instance_table_model import InstanceTableModel, Columns
from .delegates import VisibilityDelegate, CategoryDelegate, ColourDelegate


class InstanceWidget(QWidget):

    # --- --- --- Constructor --- --- ---
    
    def __init__(self, controller: InstanceController, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        # Fields
        self._controller = controller
        self._model = InstanceTableModel(controller, self)
        self._view = QTableView(self)
        self._add_btn = QPushButton("Add instance")
        self._del_btn = QPushButton("Delete instance")
        self._colour_generator = ColourGenerator()

        self._init_ui()
    # End of def __init__

    
    def _init_ui(self) -> None:
        # Controller bindings
        self._controller.instance_changed.connect(self._model.handle_instance_changed)

        # View setup
        self._view.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self._view.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self._view.verticalHeader().setVisible(False)
        self._view.setAlternatingRowColors(True)
        self._view.horizontalHeader().setStretchLastSection(True)

        # - Model
        self._view.setModel(self._model)
        # Selection -> controller wiring
        sel_model = self._view.selectionModel()
        sel_model.currentRowChanged.connect(self._on_current_row_changed)
        # Controller -> view selection sync
        self._controller.current_instance_changed.connect(self._on_current_instance_changed)

        # - Delegates
        self._view.setItemDelegateForColumn(Columns.VISIBLE, VisibilityDelegate(self._view))
        self._view.setItemDelegateForColumn(Columns.CATEGORY, CategoryDelegate(self._controller, self._view))
        self._view.setItemDelegateForColumn(Columns.COLOR, ColourDelegate(self._view))

        # Delegate visibility persistent editors for initial rows
        # + keep persistent editors for new rows
        self._open_visibility_editors_for_all_rows()
        self._model.rowsInserted.connect(self._on_rows_inserted)

        # Buttons
        self._add_btn.clicked.connect(self._on_add)
        self._del_btn.clicked.connect(self._on_delete)

        # Layout
        btn_layout = QHBoxLayout()
        btn_layout.addWidget(self._add_btn)
        btn_layout.addWidget(self._del_btn)
        btn_layout.addStretch()

        layout = QVBoxLayout(self) # Set as main layout on self
        layout.addWidget(self._view)
        layout.addLayout(btn_layout)
    # End of def _init_ui


    def sizeHint(self) -> QSize:
        layout = self.layout()
        if layout is None:
            return super().sizeHint()

        # Width needed so that all columns fit without a horizontal scrollbar
        width_for_cols = self._view.horizontalHeader().length()
        if width_for_cols <= 0:
            width_for_cols = self._view.sizeHint().width()

        # Add vertical header width (0 if hidden)
        width_for_cols += self._view.verticalHeader().width()

        # Add table frame and potential vertical scrollbar
        width_for_cols += 2 * self._view.frameWidth()
        width_for_cols += self._view.verticalScrollBar().sizeHint().width()

        # Add layout margins around the table
        margins = layout.contentsMargins()
        width_for_cols += margins.left() + margins.right()

        # Check minimum sizes required by the layout for other components (buttons)
        width = max(width_for_cols, layout.sizeHint().width())
        height = layout.sizeHint().height()

        return QSize(width, height)
    # End of def sizeHint

    
    # --- --- --- Handlers --- --- ---
        
    def _on_add(self) -> None:
        default_name = "unnamed"
        default_color = self._colour_generator.next()
        default_category = None

        #
        iid = self._controller.create_instance(default_name, default_color, default_category)
        self._controller.set_current_instance(iid)

        # handle_instance_changed(CREATE) has already inserted the row
        row = self._model._instance_ids.index(iid)
        idx = self._model.index(row, 0)

        self._view.selectRow(idx.row())
        self._view.scrollTo(idx, QTableView.ScrollHint.PositionAtCenter)
    # End of def _on_add


    def _on_delete(self) -> None:
        idx = self._view.currentIndex()
        if not idx.isValid():
            return
        row = idx.row()
        instance_id = self._model.instance_id_at_row(row)
        self._controller.delete_instance(instance_id)
    # End of def _on_delete

    
    def _on_current_row_changed(self, current: QModelIndex, previous: QModelIndex) -> None:
        """View selection changed: update controller current instance."""
        if not current.isValid():
            # nothing selected
            self._controller.set_current_instance(None)
            return

        row = current.row()
        instance_id = self._model.instance_id_at_row(row)
        self._controller.set_current_instance(instance_id)
    # End of def _on_current_row_changed

    
    def _on_current_instance_changed(self, instance_id) -> None:
        """Controller current instance changed -> select corresponding row in view."""
        if (sel_model := self._view.selectionModel()) is not None:
            if instance_id is None:
                sel_model.clearSelection()
            elif (row := self._model.row_of_instance_id(instance_id)) is not None:
                index = self._model.index(row, 0)
                if self._view.currentIndex() != index:
                    self._view.selectRow(row)
                    self._view.scrollTo(index, QTableView.ScrollHint.PositionAtCenter)
            #
        #
    # End of def _on_current_instance_changed



    def _open_visibility_editors_for_all_rows(self) -> None:
        for row in range(self._model.rowCount()):
            idx = self._model.index(row, Columns.VISIBLE)
            self._view.openPersistentEditor(idx)
    #


    def _on_rows_inserted(self, parent: QModelIndex, first: int, last: int) -> None:
        for row in range(first, last + 1):
            idx = self._model.index(row, Columns.VISIBLE)
            self._view.openPersistentEditor(idx)
    #



# End of class InstanceWidget