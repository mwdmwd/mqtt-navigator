import json
import time
from typing import Optional

from PySide2 import QtWidgets, QtCore, QtGui
from PySide2.QtCharts import QtCharts

from common import consts
from models.mqtreemodel import MqTreeNode, MqTreeModel
from models.qjsonmodel import QJsonModel
from views.resettablezoomchartview import ResettableZoomChartView
from ui.mainwindow import Ui_MainWindow


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, model: MqTreeModel, parent=None):
        super().__init__(parent)
        self._selected_topic_model: Optional[MqTreeNode] = None
        self._raw_model = model
        self._raw_model.messageReceived.connect(self._on_message)

        self._model = QtCore.QSortFilterProxyModel(self)
        self._model.setFilterKeyColumn(-1)  # All columns
        self._model.setFilterCaseSensitivity(QtCore.Qt.CaseSensitivity.CaseInsensitive)
        self._model.setRecursiveFilteringEnabled(True)
        self._model.setSourceModel(self._raw_model)

        self._ui = Ui_MainWindow()
        self._ui.setupUi(self)
        self._setup_ui()

    def _setup_ui(self):
        self._ui.tree_view.setModel(self._model)
        self._ui.tree_view.selectionModel().selectionChanged.connect(self._tree_selection_changed)
        self._ui.button_send_to_editor.clicked.connect(self._send_to_editor_clicked)
        self._ui.button_publish.clicked.connect(self._publish_clicked)
        self._ui.text_tree_search.textChanged.connect(self._search_text_changed)

        self._ui.chart_view = ResettableZoomChartView()
        self._ui.chart_view.setRubberBand(QtCharts.QChartView.RubberBand.RectangleRubberBand)
        self._ui.chart_view.setRenderHint(QtGui.QPainter.Antialiasing)
        self._chart = self._ui.chart_view.chart()  # type: QtCharts.QChart

        self._chart.legend().hide()

        self._ui.chart_layout.addWidget(self._ui.chart_view)

        if not self._raw_model.has_mqtt():
            self._ui.button_send_to_editor.hide()
            self._ui.tx_widget.hide()

    def _try_parse_and_display_json(self, payload):
        try:
            json_data = json.loads(payload)
            json_model = QJsonModel(read_only=True)
            json_model.load(json_data)
            self._ui.tree_json_rx.setModel(json_model)
            self._ui.tree_json_rx.setDisabled(False)
        except (json.JSONDecodeError, AssertionError):
            # QJsonModel will assert if it gets something other than a dict
            self._ui.tree_json_rx.setModel(None)
            self._ui.tree_json_rx.setDisabled(True)

    def _create_chart_axes(self, series):
        ax_x = QtCharts.QDateTimeAxis()
        ax_x.setFormat("HH:mm:ss")
        self._chart.addAxis(ax_x, QtCore.Qt.AlignBottom)
        series.attachAxis(ax_x)

        ax_y = QtCharts.QValueAxis()
        self._chart.addAxis(ax_y, QtCore.Qt.AlignLeft)
        series.attachAxis(ax_y)

    def _update_history_table_and_chart(self, model, *, selection_changed=False):
        # First, save the old row count in case we need to append to the table
        start_row = self._ui.table_history.rowCount()
        new_row_count = len(model.payload_history)
        added_rows = new_row_count - start_row
        self._ui.table_history.setRowCount(new_row_count)  # Resize the history table

        if selection_changed:  # We need to clear the existing views and process all history entries
            entries_to_process = model.payload_history
            start_row = 0

            # Clear the chart and add a new series
            for axis in self._chart.axes():
                self._chart.removeAxis(axis)
            self._chart.removeAllSeries()

            series = QtCharts.QLineSeries()
            self._chart.addSeries(series)

            # Add a new set of axes
            self._create_chart_axes(series)
        else:  # We only need to process the added entries
            if not added_rows:
                return  # So return if there weren't any
            entries_to_process = model.payload_history[-added_rows:]  # added_rows last entries
            series = self._chart.series()[0]  # The chart will only have one series

        for row, (payload, ptime) in enumerate(entries_to_process, start=start_row):
            self._ui.table_history.setItem(row, 0, QtWidgets.QTableWidgetItem(str(ptime)))
            self._ui.table_history.setItem(row, 1, QtWidgets.QTableWidgetItem(payload))

            try:  # Append the value to the chart series if it is numeric
                numeric_value = float(payload)
                series.append(ptime.timestamp() * 1000, numeric_value)
            except ValueError:
                pass

        if not self._chart.isZoomed():
            self._ui.chart_view.fit_axes()

    def _selected_node_updated(self, *, selection_changed=False):
        model = self._selected_topic_model

        self._ui.text_topic_rx.setText(model.full_topic())
        self._ui.text_payload_rx.setText(model.payload)

        self._try_parse_and_display_json(model.payload)
        self._update_history_table_and_chart(model, selection_changed=selection_changed)

    def _on_message(self, node: MqTreeNode):
        if node == self._selected_topic_model:  # If the change is for the selected node
            self._selected_node_updated(selection_changed=False)  # Update the view

        # Refresh the filter proxy model. This *theoretically* shouldn't be necessary,
        # but not doing it makes extra rows appear
        self._model.invalidate()

    def _tree_selection_changed(self, selected: QtCore.QItemSelectionModel, _deselected):
        selected = self._model.mapSelectionToSource(selected)
        indexes = selected.indexes()
        if not indexes:
            return

        model: MqTreeNode = indexes[0].internalPointer()
        self._selected_topic_model = model
        self._selected_node_updated(selection_changed=True)

    def _search_text_changed(self):
        text = self._ui.text_tree_search.text()
        self._model.setFilterFixedString(text)

    def _send_to_editor_clicked(self):
        self._ui.text_topic.setText(self._ui.text_topic_rx.toPlainText())
        self._ui.text_payload.setText(self._ui.text_payload_rx.toPlainText())

    def _publish_clicked(self):
        topic = self._ui.text_topic.text()
        if not topic:
            QtWidgets.QMessageBox.warning(self, "Empty topic", "Can't send message to empty topic")
            return

        payload = self._ui.text_payload.toPlainText()
        qos = self._ui.num_qos.value()
        retain = self._ui.checkbox_retain.isChecked()

        self._raw_model.mqtt_publish(topic, payload, qos, retain)

    def closeEvent(self, event):
        if self._ask_close():
            event.accept()
        else:
            event.ignore()

    def _ask_save_path(self) -> Optional[str]:
        filepath, _filetype = QtWidgets.QFileDialog.getSaveFileName(
            self, "Save session", "", consts.SESSION_FILE_TYPES
        )

        return filepath

    def _save_session(self, path: str) -> bool:
        try:
            with open(path, "w") as sessionfile:
                json.dump(self._raw_model.serialize(), sessionfile, separators=(",", ":"))
        except:
            return False

        return True

    def _ask_close(self) -> bool:
        buttons = QtWidgets.QMessageBox.StandardButtons(
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No | QtWidgets.QMessageBox.Cancel
        )

        answer = QtWidgets.QMessageBox.question(
            self, "Session save", "Do you want to save this session?", buttons
        )

        if answer == QtWidgets.QMessageBox.Cancel:
            return False
        elif answer == QtWidgets.QMessageBox.No:
            return True

        path = self._ask_save_path()
        if not path:
            return False  # Don't close if user clicked "Yes" and didn't provide a path

        if not self._save_session(path):
            QtWidgets.QMessageBox.critical(self, "Error", "Failed to save session")
            return False

        # Prevent "Internal C++ object already deleted" error
        time.sleep(0.1)

        return True
