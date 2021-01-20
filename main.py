#!/usr/bin/env python3
import sys

from PySide2 import QtWidgets

from startupwindow import StartupWindow


def main(argv):
    app = QtWidgets.QApplication(argv)

    window = StartupWindow()
    window.show()

    app.exec_()


if __name__ == "__main__":
    main(sys.argv)