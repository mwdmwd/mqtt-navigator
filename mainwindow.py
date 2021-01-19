import json
from typing import Optional

from PySide2 import QtWidgets, QtCore
from PySide2.QtCharts import QtCharts
from pytestqt.modeltest import ModelTester

from mq_client import MqTreeNode, MqTreeModel
from qjsonmodel import QJsonModel
from ui.mainwindow import Ui_MainWindow


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, model: MqTreeModel):
        super().__init__()
        self._selected_topic_model: Optional[MqTreeNode] = None
        self.raw_model = model

        self.model = QtCore.QSortFilterProxyModel(self)
        self.model.setFilterKeyColumn(-1)  # All columns
        self.model.setFilterCaseSensitivity(QtCore.Qt.CaseSensitivity.CaseInsensitive)
        self.model.setRecursiveFilteringEnabled(True)
        self.model.setSourceModel(self.raw_model)
        self.model = self.raw_model  # TODO FIXME

        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)
        self.setupUi()

    def setupUi(self):
        self.ui.tree_view.setModel(self.model)
        self.ui.tree_view.selectionModel().selectionChanged.connect(self.tree_selection_changed)
        self.ui.button_send_to_editor.clicked.connect(self.send_to_editor_clicked)
        self.ui.button_publish.clicked.connect(self.publish_clicked)
        self.ui.text_tree_search.textChanged.connect(self.search_text_changed)

        self.ui.table_history.setColumnCount(2)

        self.ui.chart_view = QtCharts.QChartView()
        self.chart = self.ui.chart_view.chart()

        self.chart.legend().hide()
        self.chart.addSeries(QtCharts.QLineSeries())
        self.chart.createDefaultAxes()
        self.chart.removeAllSeries()
        self.ui.chart_layout.addWidget(self.ui.chart_view)

    def _try_parse_and_display_json(self, payload):
        try:
            json_data = json.loads(payload)
            json_model = QJsonModel()
            json_model.load(json_data)
            self.ui.tree_json_rx.setModel(json_model)
            self.ui.tree_json_rx.setDisabled(False)
        except (json.JSONDecodeError, AssertionError):
            # QJsonModel will assert if it gets something other than a dict
            self.ui.tree_json_rx.setModel(None)
            self.ui.tree_json_rx.setDisabled(True)

    def _update_history_table_and_chart(self, model, *, selection_changed=False):
        # First, update the history table's row count
        self.ui.table_history.setRowCount(len(model.payload_history))

        if selection_changed:  # We need to process all history entries and clear the existing views
            entries_to_process = model.payload_history
            self.chart.removeAllSeries()
            series = QtCharts.QLineSeries()
            self.chart.addSeries(series)
            start_row = 0
        else:  # We need to process the last entry, the others will have been processed already
            entries_to_process = [model.payload_history[-1]]
            series = self.chart.series()[0]  # The chart will only have one series
            start_row = self.ui.table_history.rowCount()

        for row, (payload, timestamp) in enumerate(entries_to_process, start=start_row):
            self.ui.table_history.setItem(row, 0, QtWidgets.QTableWidgetItem(str(timestamp)))
            self.ui.table_history.setItem(row, 1, QtWidgets.QTableWidgetItem(payload))

            try:  # Append the value to the chart series if it is numeric
                numeric_value = float(payload)
                series.append(timestamp.timestamp() * 1000, numeric_value)
            except ValueError:
                pass

        # Create or update the chart's axes
        self.chart.createDefaultAxes()

    def _selected_node_updated(self):
        model = self._selected_topic_model

        self.ui.text_topic_rx.setText(model.fullTopic())
        self.ui.text_payload_rx.setText(model.payload)

        self._try_parse_and_display_json(model.payload)
        self._update_history_table_and_chart(model, selection_changed=True)

    def tree_selection_changed(self, selected: QtCore.QItemSelectionModel, _deselected):
        model: MqTreeNode = selected.indexes()[0].internalPointer()
        self._selected_topic_model = model
        self._selected_node_updated()

    def search_text_changed(self):
        text = self.ui.text_tree_search.text()
        self.model.setFilterFixedString(text)

    def send_to_editor_clicked(self):
        self.ui.text_topic.setText(self.ui.text_topic_rx.toPlainText())
        self.ui.text_payload.setText(self.ui.text_payload_rx.toPlainText())

    def publish_clicked(self):
        topic = self.ui.text_topic.text()
        payload = self.ui.text_payload.toPlainText()
        qos = self.ui.num_qos.value()
        retain = self.ui.checkbox_retain.isChecked()

        self.raw_model.mqtt_publish(topic, payload, qos, retain)