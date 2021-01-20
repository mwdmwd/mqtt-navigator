from typing import Optional

from PySide2 import QtWidgets, QtCore

from mq_client import MqttListener, MqTreeModel
from ui.startupwindow import Ui_StartupWindow
from mainwindow import MainWindow


class StartupWindow(QtWidgets.QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)

        self._mainwindow: Optional[MainWindow] = None
        self._mainwindow_model: Optional[MqTreeModel] = None

        self._ui = Ui_StartupWindow()
        self._ui.setupUi(self)
        self._setup_ui()

    def _setup_ui(self):
        self._ui.button_connect.clicked.connect(self._connect_clicked)

    def _connect_clicked(self):
        host = self._ui.text_host.text()
        port = self._ui.num_port.value()

        if self._ui.group_useauthn.isChecked():
            username = self._ui.text_username.text()
            password = self._ui.text_password.text()
            mqtt_listener = MqttListener(host, port, username, password)
        else:
            mqtt_listener = MqttListener(host, port)

        mqtt_listener.add_connect_fail_listener(self._connection_failed)
        mqtt_listener.add_connect_listener(self._connected)

        self._ui.status_bar.showMessage("Connecting...")

        self._mainwindow_model = MqTreeModel(self, mqtt_listener=mqtt_listener)
        mqtt_listener.connect()
        self._connected() # FIXME


    def _connection_failed(self):
        self._ui.status_bar.showMessage("Connection failed!")

    def _connected(self):
        print("connd")
        self._mainwindow = MainWindow(self._mainwindow_model)
        self._mainwindow.show()
        self.close()

