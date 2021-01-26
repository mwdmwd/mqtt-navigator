import json
from typing import Optional

from PySide2 import QtWidgets, QtCore

import consts
from mq_client import MqttListener, MqTreeModel
from ui.startupwindow import Ui_StartupWindow
from mainwindow import MainWindow


class StartupWindow(QtWidgets.QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)

        self._mainwindow: Optional[MainWindow] = None
        self._mainwindow_model: Optional[MqTreeModel] = None
        self._saved_state = {}

        self._ui = Ui_StartupWindow()
        self._ui.setupUi(self)
        self._setup_ui()

    def _setup_ui(self):
        self._ui.button_connect.clicked.connect(self._connect_clicked)
        self._ui.button_browse_session.clicked.connect(self._load_session)

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

        # Don't restore state if the checkbox was unchecked after loading it
        if self._ui.group_loadsession.isChecked():
            state = self._saved_state
        else:
            state = None

        self._mainwindow_model = MqTreeModel(self, mqtt_listener=mqtt_listener, saved_state=state)
        mqtt_listener.connect()
        self._connected()  # FIXME

    def _load_session_file(self) -> Optional[dict]:
        filepath, _filetype = QtWidgets.QFileDialog.getOpenFileName(
            self, "Open session", "", consts.SESSION_FILE_TYPES
        )

        if not filepath:
            return

        try:
            with open(filepath) as session_file:
                session = json.load(session_file)
        except:
            QtWidgets.QMessageBox.critical(self, "Error", "Failed to open session file.")
            return

        self._ui.text_session_path.setText(filepath)
        return session

    def _count_history_entries(self, state):
        entries = len(state[consts.SESSION_HISTORY_KEY])
        if state[consts.SESSION_CHILDREN_KEY]:
            entries += sum(
                self._count_history_entries(c) for c in state[consts.SESSION_CHILDREN_KEY]
            )

        return entries

    def _load_session(self):
        session = self._load_session_file()
        if not session:
            return

        config = session["config"]
        state = session["state"]

        self._saved_state = state

        self._ui.text_host.setText(config["host"])
        self._ui.num_port.setValue(config["port"])
        self._ui.label_num_history_entries.setText(
            f"Session contains {self._count_history_entries(state)} history entries."
        )

        username = config["username"]
        if username:
            self._ui.group_useauthn.setChecked(True)
            self._ui.text_username.setText(username)
            self._ui.text_password.setText(config["password"])
        else:
            self._ui.group_useauthn.setChecked(False)
            self._ui.text_username.setText("")
            self._ui.text_password.setText("")

        self._ui.status_bar.showMessage("Loaded session.")

    def _connection_failed(self):
        self._ui.status_bar.showMessage("Connection failed!")

    def _connected(self):
        print("connd")
        self._mainwindow = MainWindow(self._mainwindow_model)
        self._mainwindow.show()
        self.close()
