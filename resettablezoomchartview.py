from PySide2 import QtGui
from PySide2.QtCharts import QtCharts


class ResettableZoomChartView(QtCharts.QChartView):
    def mouseReleaseEvent(self, event: QtGui.QMouseEvent):
        if event.button() == QtGui.Qt.RightButton:
            self.chart().zoomReset()
        else:
            super().mouseReleaseEvent(event)