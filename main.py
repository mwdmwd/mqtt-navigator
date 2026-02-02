#!/usr/bin/env python3
import sys
import argparse

from PySide6 import QtWidgets

from views.startupwindow import StartupWindow


def main(argv):
    parser = argparse.ArgumentParser(description="MQTT Navigator")
    parser.add_argument("host", nargs="?")
    parser.add_argument("port", nargs="?", type=int, default=1883)
    parser.add_argument("-u", "--username")
    parser.add_argument("-p", "--password")
    parser.add_argument("-l", "--load-session", help="Saved session file to load")

    args, rest = parser.parse_known_args(argv[1:])
    app = QtWidgets.QApplication([argv[0]] + rest)

    window = StartupWindow(
        host=args.host,
        port=args.port,
        username=args.username,
        password=args.password,
        load_session=args.load_session,
    )
    window.show()

    app.exec()


if __name__ == "__main__":
    main(sys.argv)
