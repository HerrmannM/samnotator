# --- --- --- Imports --- --- ---
# STD
from typing import Any
# 3RD
from PySide6.QtCore import Qt, QEvent, QAbstractItemModel, QModelIndex, QObject, QPersistentModelIndex, QPoint, QRect, QSize, Slot
from PySide6.QtGui import QColor, QIcon, QPainter
from PySide6.QtWidgets import QComboBox, QCompleter, QColorDialog, QHBoxLayout, QToolButton, QStyledItemDelegate, QStyleOptionViewItem, QWidget, QAbstractItemView
# Project
from .instance_table_model import ROLE_MARK_VISIBLE, ROLE_MASK_VISIBLE
from samnotator.utils_qt.contextblock import block_signals, save_painter
from samnotator.controllers.instance_controller import InstanceController


# --- --- --- Visibility Delegate with persistent Editor --- --- ---


class _VisibilityEditor(QWidget):
    """Small widget with two toggle buttons bound to a model index."""

    # --- --- --- Constructor --- --- ---

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._index: QPersistentModelIndex | None = None
        self.mark_btn = self._mk_button("X", self._on_mark_clicked, None)
        self.mask_btn = self._mk_button("M", self._on_mask_clicked, None)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(2, 0, 2, 0)
        layout.setSpacing(2)
        layout.addWidget(self.mark_btn)
        layout.addWidget(self.mask_btn)
    # End of def __init__

    def _mk_button(self, text: str, _on_clicked, icon: QIcon | None) -> QToolButton:
        btn = QToolButton(self)
        btn.setCheckable(True)
        btn.setText(text)
        if icon is not None:
            btn.setIcon(icon)
        btn.clicked.connect(_on_clicked)
        return btn
    # End of def _mk_button


    # --- --- --- Index binding --- --- ---

    def set_index(self, index: QPersistentModelIndex | None) -> None:
        """Bind this editor to a model index and sync button states from the model."""
        self._index = index
        # Sync from model
        if (index := self._index) is not None and index.isValid():
            model: QAbstractItemModel = index.model()
            with block_signals(self.mark_btn, self.mask_btn):
                self.mark_btn.setChecked(bool(model.data(index, ROLE_MARK_VISIBLE)))
                self.mask_btn.setChecked(bool(model.data(index, ROLE_MASK_VISIBLE)))
    # End of def set_index


    # --- --- --- Button handlers --- --- ---

    def _on_mark_clicked(self) -> None:
        """Toggle mark/bbox visibility via the model."""
        if (index := self._index) is not None and index.isValid():
            model = index.model()
            current = bool(model.data(index, ROLE_MARK_VISIBLE))
            model.setData(index, not current, ROLE_MARK_VISIBLE)
    # End of def _on_mark_clicked

    def _on_mask_clicked(self) -> None:
        """Toggle mask visibility via the model."""
        if (index := self._index) is not None and index.isValid():
            model =  index.model()
            current = bool(model.data(index, ROLE_MASK_VISIBLE))
            model.setData(index, not current, ROLE_MASK_VISIBLE)
    # End of def _on_mask_clicked
# End of class _VisibilityEditor


class VisibilityDelegate(QStyledItemDelegate):
    """Delegate for the visibility column using a persistent _VisibilityEditor."""

    # --- --- --- Constructor --- --- ---

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
    # End of def __init__


    # --- Delegate API ---

    def createEditor( self, parent: QWidget, option: QStyleOptionViewItem, index: QModelIndex) -> QWidget:
        editor = _VisibilityEditor(parent)
        return editor
    # End of def createEditor


    def setEditorData(self, editor: QWidget, index: QModelIndex) -> None:
        """Sync the editor from the model when data changes."""
        if index.isValid():
            assert isinstance(editor, _VisibilityEditor)
            editor.set_index(QPersistentModelIndex(index))
    # End of def setEditorData


    def setModelData(self, editor: QWidget, model: QAbstractItemModel, index: QModelIndex) -> None:
        """No-op: VisibilityEditor writes directly to the model on button clicks."""
        return None
    # End of def setModelData


    def updateEditorGeometry(self, editor: QWidget, option: QStyleOptionViewItem, index: QModelIndex,) -> None:
        """Ensure the editor fills the cell rectangle."""
        editor.setGeometry(option.rect)  # type: ignore
    # End of def updateEditorGeometry
# End of class VisibilityDelegate


# --- --- ---  Colour Delegate --- --- ---

class ColourDelegate(QStyledItemDelegate):
    """ Displays a color swatch; on edit, opens a QColorDialog.  """

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        # Paint underlying cell by default
        super().paint(painter, option, index)

        # Get color
        color_value = index.data(Qt.ItemDataRole.DisplayRole)
        color = color_value if isinstance(color_value, QColor) else QColor(str(color_value))
        if color.isValid():
            rect:QRect = option.rect # type: ignore
            rect = rect.adjusted(4, 4, -4, -4)
            with save_painter(painter):
                painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(color)
                painter.drawRect(rect)
            #
        #
    # End of def paint


    def createEditor(self, parent: QWidget, option: QStyleOptionViewItem, index: QModelIndex) -> QWidget:
        # Use a modal QColorDialog and immediately commit
        # Get current color
        color_value = index.data(Qt.ItemDataRole.EditRole)
        current_color = color_value if isinstance(color_value, QColor) else QColor(str(color_value))
        if not current_color.isValid():
            current_color = None

        # Create and show dialog, on accept, set model data
        dlg = QColorDialog(parent, currentColor=current_color)

        # optional: avoid native dialogs (which often ignore position)
        dlg.setOption(QColorDialog.ColorDialogOption.DontUseNativeDialog, True)


        # --- position near cell ---
        margin = 5
        view = option.widget
        if isinstance(view, QAbstractItemView):
            cell_rect = view.visualRect(index)
            base_global = view.viewport().mapToGlobal(cell_rect.bottomLeft())
        else:
            base_global = parent.mapToGlobal(option.rect.bottomLeft())

        pos = QPoint(base_global.x() + margin, base_global.y() + margin)

        # ---- clamp bottom/right inside window ----
        window = parent.window()
        win_geo = window.frameGeometry()  # global coords

        dlg_size = dlg.sizeHint()
        x = pos.x()
        y = pos.y()

        # keep right edge inside
        if x + dlg_size.width() > (win_geo.right()- margin):
            x = win_geo.right() - dlg_size.width() + margin

        # keep bottom edge inside
        if y + dlg_size.height() > (win_geo.bottom() - margin):
            y = win_geo.bottom() - dlg_size.height() + margin

        dlg.move(x, y)

        # --- --- ---

        if dlg.exec():
            chosen = dlg.currentColor()
            index.model().setData(index, chosen, Qt.ItemDataRole.EditRole)
        # 

        return QWidget(parent)
    # End of def createEditor


    def setEditorData(self, editor: QWidget, index: QModelIndex) -> None:
        pass # No op, editor data is set in create editor
    # End of def setEditorData


    def setModelData( self, editor: QWidget, model: QAbstractItemModel, index: QModelIndex,) -> None:
        pass # No op, model data is set in create editor
    # End of def setModelData


    def updateEditorGeometry(self, editor: QWidget, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        pass
    # End of def updateEditorGeometry
# End of class ColourDelegate



# --- --- --- Category Delegate --- --- ---

class CategoryDelegate(QStyledItemDelegate):
    """Editable delegate for the category name column. Uses combo box."""


    # --- --- --- Constructor --- --- ---

    def __init__(self, controller: InstanceController, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._controller = controller
    # End of def __init__


    def _populate_categories(self, combo: QComboBox) -> None:
        combo.clear()
        cats = self._controller.all_categories()
        combo.addItems(cats)
    # End of def _populate_categories


    # ------ --- Delegate API --- --- ---
    
    def createEditor(self, parent: QWidget, option: QStyleOptionViewItem, index: QModelIndex) -> QWidget:
        # Create and configure the combo box
        combo = QComboBox(parent)
        combo.setEditable(True)
        combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert) # No 'mutation' of the combo, update the model only in setModelData
        # Add a completer
        completer = QCompleter(combo)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        combo.setCompleter(completer)
        return combo
    # End of def createEditor


    def setEditorData(self, combo: QWidget, index: QModelIndex) -> None:
        assert isinstance(combo, QComboBox)
        # Add all items
        self._populate_categories(combo)
        # Setup current item
        value = index.data(Qt.ItemDataRole.EditRole)
        text = str(value) if value is not None else ""
        combo.setCurrentText(text)
    # End of def setEditorData


    def setModelData(self, combo: QWidget, model: QAbstractItemModel, index: QModelIndex) -> None:
        assert isinstance(combo, QComboBox)
        model.setData(index, combo.currentText(), Qt.ItemDataRole.EditRole)
    # End of def setModelData


    def updateEditorGeometry(self, editor: QWidget, option: QStyleOptionViewItem, index: QModelIndex,) -> None:
        editor.setGeometry(option.rect) # type: ignore
    # End of def updateEditorGeometry
# End of class CategoryDelegate
