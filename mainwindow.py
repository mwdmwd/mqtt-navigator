import json

from PySide2 import QtWidgets, QtCore
from pytestqt.modeltest import ModelTester

from mq_client import MqTreeNode, MqTreeModel
from ui.mainwindow import Ui_MainWindow


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, model: MqTreeModel):
        super().__init__()
        self.raw_model = model

        self.model = QtCore.QSortFilterProxyModel(self)
        self.model.setSourceModel(self.raw_model)
        self.model = self.raw_model  # FIXME TODO

        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)
        self.setupUi()

    def setupUi(self):
        self.ui.tree_view.setModel(self.model)
        self.ui.tree_view.selectionModel().selectionChanged.connect(self.tree_selection_changed)
        self.ui.button_send_to_editor.clicked.connect(self.send_to_editor_clicked)
        self.ui.button_publish.clicked.connect(self.publish_clicked)
        self.ui.text_tree_search.textChanged.connect(self.search_text_changed)

    def tree_selection_changed(self, selected: QtCore.QItemSelectionModel, _deselected):
        model: MqTreeNode = selected.indexes()[0].internalPointer()

        self.ui.text_topic_rx.setText(model.fullTopic())
        self.ui.text_payload_rx.setText(model.payload)

        try:
            json_data = json.loads(model.payload)
            json_model = QJsonModel()
            json_model.load(json_data)
            global fpm
            fpm = QtCore.QSortFilterProxyModel(self)
            fpm.setFilterKeyColumn(-1)  # All columns
            fpm.setFilterCaseSensitivity(QtCore.Qt.CaseSensitivity.CaseInsensitive)
            fpm.setRecursiveFilteringEnabled(True)
            fpm.setSourceModel(json_model)
            self.ui.tree_json_rx.setModel(fpm)
            self.ui.tree_json_rx.setDisabled(False)
            ModelTester(None).check(json_model, force_py=True)
        except json.JSONDecodeError:
            self.ui.tree_json_rx.setModel(None)
            self.ui.tree_json_rx.setDisabled(True)

        self.ui.table_history.setColumnCount(2)
        self.ui.table_history.setRowCount(len(model.payload_history))
        for i, (payload, timestamp) in enumerate(model.payload_history):
            self.ui.table_history.setItem(i, 0, QtWidgets.QTableWidgetItem(str(timestamp)))
            self.ui.table_history.setItem(i, 1, QtWidgets.QTableWidgetItem(payload))

    def search_text_changed(self):
        text = self.ui.text_tree_search.text()
        fpm.setFilterFixedString(text)
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