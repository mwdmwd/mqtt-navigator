import json
from typing import Optional

from PySide2 import QtWidgets, QtCore, QtGui
from PySide2.QtCharts import QtCharts
from pytestqt.modeltest import ModelTester

from mq_client import MqTreeNode, MqTreeModel
from qjsonmodel import QJsonModel
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

        self._ui.table_history.setColumnCount(2)

        self._ui.chart_view = QtCharts.QChartView()
        self._ui.chart_view.setRubberBand(QtCharts.QChartView.RubberBand.RectangleRubberBand)
        #self._ui.chart_view.mouseReleaseEvent.connect(self._chart_mouse_released)
        self._chart = self._ui.chart_view.chart()

        self._chart.legend().hide()
        self._chart.addSeries(QtCharts.QLineSeries())
        self._chart.createDefaultAxes()
        self._chart.removeAllSeries()

        self._ui.chart_layout.addWidget(self._ui.chart_view)

    def _try_parse_and_display_json(self, payload):
        try:
            json_data = json.loads(payload)
            json_model = QJsonModel()
            json_model.load(json_data)
            self._ui.tree_json_rx.setModel(json_model)
            self._ui.tree_json_rx.setDisabled(False)
        except (json.JSONDecodeError, AssertionError):
            # QJsonModel will assert if it gets something other than a dict
            self._ui.tree_json_rx.setModel(None)
            self._ui.tree_json_rx.setDisabled(True)

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
            self._chart.removeAllSeries()
            series = QtCharts.QLineSeries()
            # self._chart.addSeries(series)
        else:  # We only need to process the added entries
            entries_to_process = model.payload_history[-added_rows:]  # added_rows last entries
            series = self._chart.series()[0]  # The chart will only have one series

        for row, (payload, time) in enumerate(entries_to_process, start=start_row):
            self._ui.table_history.setItem(row, 0, QtWidgets.QTableWidgetItem(str(time)))
            self._ui.table_history.setItem(row, 1, QtWidgets.QTableWidgetItem(payload))

            try:  # Append the value to the chart series if it is numeric
                numeric_value = float(payload)
                series.append(time.timestamp() * 1000, numeric_value)
            except ValueError:
                pass

        # Create or update the chart's axes
        self._chart.addSeries(series)
        self._chart.createDefaultAxes()

    def _selected_node_updated(self, *, selection_changed=False):
        model = self._selected_topic_model

        self._ui.text_topic_rx.setText(model.full_topic())
        self._ui.text_payload_rx.setText(model.payload)

        self._try_parse_and_display_json(model.payload)
        self._update_history_table_and_chart(model, selection_changed=selection_changed)

    def _on_message(self, node: MqTreeNode):
        if node == self._selected_topic_model:  # If the change is for the selected node
            self._selected_node_updated(selection_changed=False)  # Update the view

    def _tree_selection_changed(self, selected: QtCore.QItemSelectionModel, _deselected):
        selected = self._model.mapSelectionToSource(selected)
        model: MqTreeNode = selected.indexes()[0].internalPointer()
        self._selected_topic_model = model
        self._selected_node_updated(selection_changed=True)

    def _search_text_changed(self):
        text = self._ui.text_tree_search.text()
        self._model.setFilterFixedString(text)

    def _chart_mouse_released(self, mouse_event: QtGui.QMouseEvent):
        print(mouse_event)

    def _send_to_editor_clicked(self):
        self._ui.text_topic.setText(self._ui.text_topic_rx.toPlainText())
        self._ui.text_payload.setText(self._ui.text_payload_rx.toPlainText())

    def _publish_clicked(self):
        topic = self._ui.text_topic.text()
        payload = self._ui.text_payload.toPlainText()
        qos = self._ui.num_qos.value()
        retain = self._ui.checkbox_retain.isChecked()

        self._raw_model.mqtt_publish(topic, payload, qos, retain)
