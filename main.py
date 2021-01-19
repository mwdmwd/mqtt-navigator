#!/usr/bin/env python3
import sys

from PySide2 import QtWidgets

from mq_client import MqTreeModel, MqttListener
from mainwindow import MainWindow


def main(argv):
    app = QtWidgets.QApplication(argv)

    mqtt_listener = MqttListener("192.168.1.10")
    model = MqTreeModel(app, mqtt_listener=mqtt_listener)

    mqtt_listener.connect()

    window = MainWindow(model)

    window.show()
    app.exec_()


if __name__ == "__main__":
    main(sys.argv)