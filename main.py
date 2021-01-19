#!/usr/bin/env python3
import sys

from PySide2 import QtWidgets
import paho.mqtt.client as mqtt
from pytestqt.modeltest import ModelTester

from mq_client import MqTreeModel
from mainwindow import MainWindow


def main(argv):
    app = QtWidgets.QApplication(argv)

    mqttc = mqtt.Client()
    model = MqTreeModel(mqttc, app)
    ModelTester(None).check(model)

    model.mqtt_connect("192.168.1.10")

    window = MainWindow(model)

    window.show()
    app.exec_()


if __name__ == "__main__":
    main(sys.argv)