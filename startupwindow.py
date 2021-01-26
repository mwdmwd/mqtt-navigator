import json
from typing import Optional

from PySide2 import QtWidgets, QtCore

import consts
from mq_client import MqttListener, MqTreeModel
from ui.startupwindow import Ui_StartupWindow
from mainwindow import MainWindow


class StartupWindow(QtWidgets.QMainWindow):
    connected = QtCore.Signal()
    connection_failed = QtCore.Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self.connected.connect(self._connected)
        self.connection_failed.connect(self._connection_failed)

        self._mainwindow: Optional[MainWindow] = None
        self._mainwindow_model: Optional[MqTreeModel] = None
        self._saved_state = {}

        self._ui = Ui_StartupWindow()
        self._ui.setupUi(self)
        self._setup_ui()

    def _setup_ui(self):
        self._ui.button_connect.clicked.connect(self._connect_clicked)
        self._ui.button_browse_session.clicked.connect(self._load_session)

    def _get_host_and_state(self) -> (str, dict):
        # Don't restore state if the checkbox was unchecked after loading it
        if self._ui.group_loadsession.isChecked():
            state = self._saved_state
            if not state:
                QtWidgets.QMessageBox.information(
                    self, "Session", 'Please select a session file or uncheck "Load saved session".'
                )
                return
        else:
            state = None

        host = self._ui.text_host.text()

        return host, state

    def _connect_clicked(self):
        host, state = self._get_host_and_state()
        if not state and not host:
            QtWidgets.QMessageBox.warning(
                self,
                "Invalid settings",
                "Please enter a host to connect to, or load a saved session to browse it without connecting.",
            )
            return

        if host:
            port = self._ui.num_port.value()
            if self._ui.group_useauthn.isChecked():
                username = self._ui.text_username.text()
                password = self._ui.text_password.text()
                mqtt_listener = MqttListener(host, port, username, password)
            else:
                mqtt_listener = MqttListener(host, port)

            mqtt_listener.add_connect_fail_listener(self._on_connection_failed)
            mqtt_listener.add_connect_listener(self._on_connected)

            self._ui.status_bar.showMessage("Connecting...")
            self._mainwindow_model = MqTreeModel(
                self, mqtt_listener=mqtt_listener, saved_state=state
            )
            mqtt_listener.connect()  # Will end up calling _connected or _connection_failed
        else:
            self._mainwindow_model = MqTreeModel(self, saved_state=state)
            self._connected()  # Call _connected directly to proceed to the main window

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

    def _on_connection_failed(self):
        self.connection_failed.emit()

    def _connection_failed(self):
        self._ui.status_bar.showMessage("Connection failed!")

    def _on_connected(self, *_args):
        self.connected.emit()

    def _connected(self):
        self._mainwindow = MainWindow(self._mainwindow_model)
        self._mainwindow.show()
        self.close()
