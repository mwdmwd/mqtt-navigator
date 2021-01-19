from __future__ import annotations
from typing import List, Optional
import collections
import dataclasses
from dataclasses import dataclass, field
from datetime import datetime

import paho.mqtt.client as mqtt
from PySide2 import QtCore
from PySide2.QtCore import Qt

import consts


MqHistoricalPayload = collections.namedtuple("MqHistoricalPayload", ["payload", "timestamp"])


@dataclass
class MqTreeNode:
    topic_fragment: str
    payload: str
    payload_history: List[MqHistoricalPayload] = field(default_factory=list)

    _parent: Optional[MqTreeNode] = field(default=None, repr=False)
    _childItems: List[MqTreeNode] = field(default_factory=list)

    def fullTopic(self):
        node = self
        frags = []
        while node:
            frags.append(node.topic_fragment)
            node = node.parent()
        return "/".join(frags[:-1][::-1])  # Skip root

    def childCount(self) -> int:
        return len(self._childItems)

    def child(self, row: int) -> Optional[MqTreeNode]:
        if row >= 0 and row < self.childCount():
            return self._childItems[row]

    def appendChild(self, child: MqTreeNode):
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


@dataclass
class MqttListenerConfiguration:
    host: str
    port: int = 1883

    username: Optional[str] = None
    password: Optional[str] = None


class MqttListener:
    def __init__(
        self, host, port=1883, username: Optional[str] = None, password: Optional[str] = None
    ):
        self._mqtt = mqtt.Client()
        self._host = host
        self._port = port

        self._connect_listeners = []
        self._disconnect_listeners = []
        self._message_listeners = []

        if username:
            self._mqtt.username_pw_set(username, password)

    @staticmethod
    def from_config(config: MqttListenerConfiguration) -> MqttListener:
        return MqttListener(**dataclasses.asdict(config))

    def connect(self):
        self._mqtt.on_connect = self._connect_listener
        self._mqtt.on_message = self._message_listener
        self._mqtt.on_disconnect = self._disconnect_listener

        self._mqtt.connect_async(self._host, self._port)
        self._mqtt.loop_start()
        print("conn")

    def disconnect(self):
        self._mqtt.disconnect()
        self._mqtt.loop_stop()

    def publish(self, topic, payload=None, qos=0, retain=False, properties=None):
        self._mqtt.publish(topic, payload, qos, retain, properties)

    def add_connect_listener(self, connect_listener):
        self._connect_listeners.append(connect_listener)

    def add_disconnect_listener(self, disconnect_listener):
        self._disconnect_listeners.append(disconnect_listener)

    def add_message_listener(self, message_listener):
        self._message_listeners.append(message_listener)

    def _connect_listener(self, client: mqtt.Client, *args):
        client.subscribe("#")  # Subscribe to all topics
        for listener in self._connect_listeners:  # Notify all other listeners
            listener(client, *args)

    def _disconnect_listener(self, *args):
        for listener in self._disconnect_listeners:  # Notify all other listeners
            listener(*args)

    def _message_listener(self, *args):
        for listener in self._message_listeners:  # Notify all other listeners
            listener(*args)


class MqTreeModel(QtCore.QAbstractItemModel):
    # Emitted whenever a message is received on a node through an active MQTT listener
    messageReceived = QtCore.Signal(MqTreeNode)

    def __init__(
        self,
        parent=None,
        *,
        mqtt_listener: Optional[MqttListener] = None,
        saved_state: Optional[dict] = None
    ):
        super().__init__(parent)

        self._entries = {}
        self._rootItem = MqTreeNode("", "")

        self._mqtt = mqtt_listener
        if self._mqtt:
            self._mqtt.add_connect_listener(self.on_connect)
            self._mqtt.add_message_listener(self.on_message)

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

    def mqtt_publish(self, topic, payload=None, qos=0, retain=False, properties=None):
        return self._mqtt.publish(
            topic, payload=payload, qos=qos, retain=retain, properties=properties
        )

    def on_connect(self, client, _userdata, _flags, _rc):
        client.subscribe("#")

    def find_node(self, topic_path: List[str]) -> (MqTreeNode, List[str]):
        node = self._rootItem
        nextNode = self._rootItem
        while nextNode and topic_path:
            nextNode = nextNode.findChild(topic_path[0])
            if nextNode:
                topic_path = topic_path[1:]
                node = nextNode
        return (node, topic_path)

    def on_message(self, _client, _userdata, msg):
        print(msg.topic)
        path = msg.topic.split("/")
        node, remain = self.find_node(path)

        if remain:
            # Find index for deepest existing node in this subtree
            parentIndex = self.indexForModel(node)
            # This could be more specific for slightly better performance
            self.layoutAboutToBeChanged.emit()

            for frag in remain:
                idx = node.childCount()
                self.beginInsertRows(parentIndex, idx, idx)
                node = node.appendChild(MqTreeNode(frag, ""))
                self.endInsertRows()
                parentIndex = self.index(idx, 0, parentIndex)

        payload = self.decode_payload(msg.payload)
        if node.payload != payload:  # Don't add to history if the payload hasn't changed
            node.payload_history.append(MqHistoricalPayload(payload, datetime.now()))
            node.payload = payload

        if not remain:
            index = self.indexForModel(node).siblingAtColumn(1)
            print(index.row(), index.column())
            self.dataChanged.emit(index, index)
        else:
            self.layoutChanged.emit()  # Again, could be more specific

        self.messageReceived.emit(node)  # Emit the signal with the updated node

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