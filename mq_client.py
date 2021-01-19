import time
import threading
import sys
import json
import uuid
from typing import Union, List, Optional, Tuple
import collections
from dataclasses import dataclass, field
from datetime import datetime

import paho.mqtt.client as mqtt
from PySide2 import QtWidgets, QtCore
from PySide2.QtCore import Qt
from PySide2.QtCharts import QtCharts

from qjsonmodel import QJsonModel
from ui.mainwindow import Ui_MainWindow
import consts

from pytestqt.modeltest import ModelTester


MqHistoricalPayload = collections.namedtuple("MqHistoricalPayload", ["payload", "timestamp"])


@dataclass
class MqTreeNode:
    topic_fragment: str
    payload: str
    payload_history: List[MqHistoricalPayload] = field(default_factory=list)

    _parent: Optional["MqTreeNode"] = field(default=None, repr=False)
    _childItems: List["MqTreeNode"] = field(default_factory=list)

    def fullTopic(self):
        node = self
        frags = []
        while node:
            frags.append(node.topic_fragment)
            node = node.parent()
        return "/".join(frags[:-1][::-1])  # Skip root

    def childCount(self) -> int:
        return len(self._childItems)

    def child(self, row: int) -> Optional["MqTreeNode"]:
        if row >= 0 and row < self.childCount():
            return self._childItems[row]

    def appendChild(self, child: "MqTreeNode"):
        child._parent = self
        self._childItems.append(child)
        return child

    def data(self, column: int):
        if column == 0:
            return self.topic_fragment
        elif column == 1:
            return self.payload

    def parent(self):
        return self._parent

    def row(self) -> int:
        if self._parent:
            return self._parent._childItems.index(self)
        return 0

    def findChild(self, topic_frag: str):
        for child in self._childItems:
            if child.topic_fragment == topic_frag:
                return child
        return None


class MqttListener:
    def __init__(self, mqtt_client: mqtt.Client):
        self._mqtt = mqtt_client

class MqTreeModel(QtCore.QAbstractItemModel):
    def __init__(self, mqtt_client: mqtt.Client, parent=None):
        super().__init__(parent)

        self._mqtt = mqtt_client
        self._mqtt.on_connect = self.on_connect
        self._mqtt.on_message = self.on_message
        self._entries = {}

        self._rootItem = MqTreeNode("", "")

    def columnCount(self, _parent=QtCore.QModelIndex()):
        return 2

    def rowCount(self, parent=QtCore.QModelIndex()):
        if parent.column() > 0:
            return 0

        if not parent.isValid():
            return self._rootItem.childCount()
        return parent.internalPointer().childCount()

    def headerData(self, _section, orientation, role):
        if role != QtCore.Qt.DisplayRole:
            return None

        if orientation == QtCore.Qt.Horizontal:
            return ""

    def index(self, row, column, parent=QtCore.QModelIndex()):
        if not self.hasIndex(row, column, parent):
            return QtCore.QModelIndex()

        if not parent.isValid():
            parentItem = self._rootItem
        else:
            parentItem = parent.internalPointer()

        childItem = parentItem.child(row)
        if childItem:
            return self.createIndex(row, column, childItem)
        else:
            return QtCore.QModelIndex()

    def indexForModel(self, model: MqTreeNode) -> Optional[QtCore.QModelIndex]:
        if not model.parent():
            return QtCore.QModelIndex()

        hits = self.match(
            self.index(0, 0),
            consts.FULL_TOPIC_ROLE,
            model.fullTopic(),
            hits=1,
            flags=Qt.MatchRecursive | Qt.MatchExactly | Qt.MatchFixedString,
        )

        if not hits:
            return None
        return hits[0]

    def data(self, index, role):
        if not index.isValid():
            return None

        item: MqTreeNode = index.internalPointer()

        if role == QtCore.Qt.DisplayRole:
            if index.column() == 0:
                return item.topic_fragment

            if index.column() == 1:
                return item.payload
        elif role == consts.FULL_TOPIC_ROLE:
            return item.fullTopic()

    def parent(self, index):
        if not index.isValid():
            return QtCore.QModelIndex()

        childItem: MqTreeNode = index.internalPointer()
        parentItem = childItem.parent()

        if parentItem == self._rootItem:
            return QtCore.QModelIndex()

        return self.createIndex(parentItem.row(), 0, parentItem)

    def mqtt_connect(self, host, port=1883, properties=None):
        self._mqtt.connect_async(host, port=port, properties=properties)
        self._mqtt.loop_start()

    def mqtt_disconnect(self):
        self._mqtt.loop_stop()
        self._mqtt.disconnect()

    def mqtt_publish(self, topic, payload=None, qos=0, retain=False, properties=None):
        return self._mqtt.publish(
            topic, payload=payload, qos=qos, retain=retain, properties=properties
        )

    @staticmethod
    def on_connect(client, userdata, flags, rc):
        client.subscribe("#")

    def find_node(self, topic_path: List[str]) -> (MqTreeNode, List[str]):
        node = self._rootItem
        next = self._rootItem
        while next and topic_path:
            next = next.findChild(topic_path[0])
            if next:
                topic_path = topic_path[1:]
                node = next
        return (node, topic_path)

    def on_message(self, client, userdata, msg):
        print(msg.topic)
        path = msg.topic.split("/")
        node, remain = self.find_node(path)

        if remain:
            parentIndex = self.indexForModel(node)
            self.layoutAboutToBeChanged.emit()  # TODO more specific

            for frag in remain:
                idx = node.childCount()
                parentIndex = self.indexForModel(node)
                self.beginInsertRows(parentIndex, idx, idx + 1)
                node = node.appendChild(MqTreeNode(frag, ""))
                self.endInsertRows()
                # parentIndex = self.index(idx, 0, parentIndex)

        payload = self.decode_payload(msg.payload)
        if node.payload != payload:  # Don't add to history if the payload hasn't changed
            node.payload_history.append(MqHistoricalPayload(payload, datetime.now()))
            node.payload = payload

        if not remain:
            index = self.indexForModel(node).siblingAtColumn(1)
            print(index.row(), index.column())
            self.dataChanged.emit(index, index)
        else:
            self.layoutChanged.emit()  # TODO more specific

    @staticmethod
    def decode_payload(payload: bytes):
        try:
            return payload.decode("UTF-8")
        except UnicodeDecodeError:
            return repr(payload)


# page_chart = window.ui.page_chart

# chart_view = QtCharts.QChartView()

# series = QtCharts.QLineSeries()
# series.append(0, 6)
# series.append(2, 4)

# chart_view.chart().addSeries(series)
# chart_view.chart().createDefaultAxes()
# window.ui.chart_layout.addWidget(chart_view)