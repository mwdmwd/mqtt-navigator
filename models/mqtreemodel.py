from __future__ import annotations
from typing import List, Optional
import collections
from dataclasses import dataclass, field
from datetime import datetime

from PySide6 import QtCore
from PySide6.QtCore import Qt

from common import consts


MqHistoricalPayload = collections.namedtuple("MqHistoricalPayload", ["payload", "timestamp"])


@dataclass
class MqTreeNode:
    topic_fragment: str
    payload: str
    payload_history: List[MqHistoricalPayload] = field(default_factory=list)

    _parent: Optional[MqTreeNode] = field(default=None, repr=False)
    _children: List[MqTreeNode] = field(default_factory=list)

    def full_topic(self):
        node = self
        frags = []
        while node:
            frags.append(node.topic_fragment)
            node = node.parent()
        return "/".join(frags[:-1][::-1])  # Skip root

    def child_count(self, leaves=False) -> int:
        return sum(1 for c in self._children if c.payload) if leaves else len(self._children)

    def recursive_child_count(self, leaves=False) -> int:
        return self.child_count(leaves) + sum(c.recursive_child_count(leaves) for c in self._children)

    def recursive_message_count(self) -> int:
        return len(self.payload_history) + sum(c.recursive_message_count() for c in self._children)

    def child(self, row: int) -> Optional[MqTreeNode]:
        if row >= 0 and row < self.child_count():
            return self._children[row]
        return None

    def append_child(self, child: MqTreeNode):
        child._parent = self
        self._children.append(child)
        return child

    def data(self, column: int):
        if column == 0:
            return self.topic_fragment
        elif column == 1:
            return self.payload
        elif column == 2:
            recursive = self.recursive_child_count(leaves=True)
            direct = self.child_count(leaves=True)
            return self._format_recursive_direct(recursive, direct)
        elif column == 3:
            recursive = self.recursive_message_count()
            direct = len(self.payload_history)
            return self._format_recursive_direct(recursive, direct)

    def parent(self):
        return self._parent

    def row(self) -> int:
        if self._parent:
            return self._parent._children.index(self)
        # The root is always row 0
        return 0

    def find_child(self, topic_frag: str):
        for child in self._children:
            if child.topic_fragment == topic_frag:
                return child
        return None

    def asdict(self):
        return {
            consts.SESSION_TOPIC_FRAGMENT_KEY: self.topic_fragment,
            consts.SESSION_HISTORY_KEY: [
                MqHistoricalPayload(payload, timestamp.timestamp())
                for (payload, timestamp) in self.payload_history
            ],
            consts.SESSION_CHILDREN_KEY: [child.asdict() for child in self._children],
        }

    @staticmethod
    def parse(node_dict: dict) -> MqTreeNode:
        topic = node_dict[consts.SESSION_TOPIC_FRAGMENT_KEY]
        payload = ""

        # Convert timestamps to Python representation
        for hist_item in node_dict[consts.SESSION_HISTORY_KEY]:
            hist_item[1] = datetime.fromtimestamp(hist_item[1])

        history = [MqHistoricalPayload(*pl) for pl in node_dict[consts.SESSION_HISTORY_KEY]]
        if history:
            payload = history[-1].payload

        # Reconstitute node
        node = MqTreeNode(topic, payload, history)
        node._children = [
            MqTreeNode.parse(child) for child in node_dict[consts.SESSION_CHILDREN_KEY]
        ]

        # Reconnect children
        for child in node._children:
            child._parent = node

        return node

    @staticmethod
    def _format_recursive_direct(recursive: int, direct: int) -> Optional[str]:
        if recursive > 0:
            if direct > 0 and recursive > 1 and recursive != direct:
                return f"{recursive} ({direct})"
            return f"{recursive}"
        return None


class MqTreeModel(QtCore.QAbstractItemModel):
    # Emitted whenever a message is received on a node through an active MQTT listener
    messageReceived = QtCore.Signal(MqTreeNode)

    def __init__(
        self,
        parent=None,
        *,
        mqtt_listener: Optional[MqttListener] = None,
        saved_state: Optional[dict] = None,
    ):
        super().__init__(parent)

        self._entries = {}
        if saved_state:
            self._root_item = MqTreeNode.parse(saved_state)
        else:
            self._root_item = MqTreeNode("", "")

        self._mqtt = mqtt_listener
        if self._mqtt:
            self._mqtt.add_connect_listener(self.on_connect)
            self._mqtt.add_message_listener(self.on_message)

    def columnCount(self, _parent=QtCore.QModelIndex()):
        return 4

    def rowCount(self, parent=QtCore.QModelIndex()):
        if parent.column() > 0:
            return 0

        if not parent.isValid():
            return self._root_item.child_count()
        return parent.internalPointer().child_count()

    def headerData(self, section, orientation, role):
        if role == QtCore.Qt.DisplayRole and orientation == QtCore.Qt.Horizontal:
            if section == 0:
                return "Topic"
            if section == 1:
                return "Payload"
            if section == 2:
                return "Subtopics"
            if section == 3:
                return "Messages"
        return None

    def flags(self, index: QtCore.QModelIndex) -> Qt.ItemFlags:
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags

        return Qt.ItemFlag.ItemIsEnabled | Qt.ItemIsSelectable

    def index(self, row, column, parent=QtCore.QModelIndex()):
        if column > 3:
            return QtCore.QModelIndex()

        if not parent.isValid():
            parent_item = self._root_item
        else:
            parent_item = parent.internalPointer()

        child_item = parent_item.child(row)
        if child_item:
            return self.createIndex(row, column, child_item)

        # Return an invalid index
        return QtCore.QModelIndex()

    def index_for_model(self, model: MqTreeNode) -> QtCore.QModelIndex:
        if not model.parent():
            return QtCore.QModelIndex()

        parent_index = self.index_for_model(model.parent())
        return self.index(model.row(), 0, parent_index)

    def data(self, index, role):
        if not index.isValid():
            return None

        item: MqTreeNode = index.internalPointer()

        if role == QtCore.Qt.DisplayRole:
            return item.data(index.column())
        elif role == consts.FULL_TOPIC_ROLE:
            return item.full_topic()

    def parent(self, index):
        if not index.isValid():
            return QtCore.QModelIndex()

        childItem: MqTreeNode = index.internalPointer()
        parentItem = childItem.parent()

        if parentItem == self._root_item:
            return QtCore.QModelIndex()

        return self.createIndex(parentItem.row(), 0, parentItem)

    def has_mqtt(self):
        return self._mqtt is not None

    def mqtt_publish(self, topic, payload=None, qos=0, retain=False, properties=None):
        return self._mqtt.publish(
            topic, payload=payload, qos=qos, retain=retain, properties=properties
        )

    def on_connect(self, client, _userdata, _flags, _rc):
        client.subscribe("#")

    def find_node(self, topic_path: List[str]) -> (MqTreeNode, List[str]):
        node = self._root_item
        nextNode = self._root_item
        while nextNode and topic_path:
            nextNode = nextNode.find_child(topic_path[0])
            if nextNode:
                topic_path = topic_path[1:]
                node = nextNode
        return (node, topic_path)

    def on_message(self, _client, _userdata, msg):
        path = msg.topic.split("/")
        node, remain = self.find_node(path)

        if remain:
            # Find index for deepest existing node in this subtree
            parent_index = self.index_for_model(node)
            # This could be more specific for slightly better performance
            self.layoutAboutToBeChanged.emit()

            for frag in remain:
                idx = node.child_count()
                self.beginInsertRows(parent_index, idx, idx)
                node = node.append_child(MqTreeNode(frag, ""))
                self.endInsertRows()
                parent_index = self.index(idx, 0, parent_index)

        payload = self.decode_payload(msg.payload)
        if node.payload != payload:  # Don't add to history if the payload hasn't changed
            node.payload_history.append(MqHistoricalPayload(payload, datetime.now()))
            node.payload = payload

        if remain:
            self.layoutChanged.emit()  # Again, could be more specific
        else:
            base_index = self.index_for_model(node)
            self.dataChanged.emit(base_index.siblingAtColumn(1), base_index.siblingAtColumn(3))

            # Update column 3 (messages) for ancestors
            parent = node.parent()
            while parent:
                p_idx = self.index_for_model(parent)
                if p_idx.isValid():
                    self.dataChanged.emit(p_idx.siblingAtColumn(3), p_idx.siblingAtColumn(3))
                parent = parent.parent()

        self.messageReceived.emit(node)  # Emit the signal with the updated node

    def _serialize_state(self) -> dict:
        return self._root_item.asdict()

    def serialize(self) -> dict:
        return {
            "config": self._mqtt.to_config(),
            "state": self._serialize_state(),
        }

    @staticmethod
    def decode_payload(payload: bytes):
        try:
            return payload.decode("UTF-8")
        except UnicodeDecodeError:
            return repr(payload)
