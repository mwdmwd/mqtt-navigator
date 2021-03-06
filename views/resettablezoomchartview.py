from typing import List
import math

from PySide2 import QtGui, QtCore
from PySide2.QtCharts import QtCharts


class ResettableZoomChartView(QtCharts.QChartView):
    def mouseReleaseEvent(self, event: QtGui.QMouseEvent):
        if event.button() == QtGui.Qt.RightButton:
            self.fit_axes()
            self.chart().zoomReset()
        else:
            super().mouseReleaseEvent(event)

    def fit_axes(self):
        chart = self.chart()
        points: List[QtCore.QPointF] = chart.series()[0].points()

        ax_x = chart.axisX()
        ax_y = chart.axisY()

        min_x, max_x, min_y, max_y = math.inf, -math.inf, math.inf, -math.inf
        for point in points:
            x = point.x()
            if x < min_x:
                min_x = x
            if x > max_x:
                max_x = x

            y = point.y()
            if y < min_y:
                min_y = y
            if y > max_y:
                max_y = y

        if all(v != math.inf for v in (min_x, max_x, min_y, max_y)):
            ax_x.setRange(
                QtCore.QDateTime.fromMSecsSinceEpoch(min_x),
                QtCore.QDateTime.fromMSecsSinceEpoch(max_x),
            )
            ax_y.setRange(min_y, max_y)