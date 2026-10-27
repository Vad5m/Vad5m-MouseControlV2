import platform
import sys
import os
import socket
import threading
import importlib

from flask import Flask, request, jsonify
from werkzeug.serving import WSGIRequestHandler

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QLabel, QVBoxLayout, QWidget,
    QSystemTrayIcon, QMenu, QAction
)
from PyQt5.QtGui import QIcon
from PyQt5.QtCore import Qt


ICON_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "data", "icon.png"
)

PORT = 42000


class LinuxMouseBackend:
    def __init__(self):
        import mouse
        self._mouse = mouse

    def is_available(self):
        return self._mouse.is_available()

    def init(self):
        self._mouse.init_uinput()
        self._mouse.start_worker()

    def handle_move(self, payload):
        return self._mouse.handle_move(payload)

    def handle_scroll(self, payload):
        return self._mouse.handle_scroll(payload)

    def handle_click(self, payload):
        return self._mouse.handle_click(payload)


class WinMouseBackend:
    def __init__(self):
        self._mouse = importlib.import_module("win-mouse")

    def is_available(self):
        fn = getattr(self._mouse, "is_available", None)
        return fn() if fn else True

    def init(self):
        for name in ("init", "init_mouse", "start_worker"):
            fn = getattr(self._mouse, name, None)
            if fn:
                fn()

    def handle_move(self, payload):
        return self._mouse.handle_move(payload)

    def handle_scroll(self, payload):
        return self._mouse.handle_scroll(payload)

    def handle_click(self, payload):
        return self._mouse.handle_click(payload)


def create_backend():
    system = platform.system()
    if system == "Linux":
        return LinuxMouseBackend()
    if system == "Windows":
        return WinMouseBackend()
    raise RuntimeError(f"Unsupported system: {system}")


class SilentHandler(WSGIRequestHandler):
    def log_request(self, code='-', size='-'):
        pass

    def log_message(self, format, *args):
        pass


def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip


def build_app(backend):
    app = Flask(__name__)

    @app.route('/')
    def index():
        return (
            "<h1>Virtual Mouse Server</h1>"
            f"<p>Mouse device: {'OK' if backend.is_available() else 'NOT AVAILABLE'}</p>"
        )

    @app.route('/mouse/move', methods=['POST'])
    def mouse_move():
        payload = request.get_json(silent=True) or {}
        result, status = backend.handle_move(payload)
        return jsonify(result), status

    @app.route('/mouse/scroll', methods=['POST'])
    def mouse_scroll():
        payload = request.get_json(silent=True) or {}
        result, status = backend.handle_scroll(payload)
        return jsonify(result), status

    @app.route('/mouse/click', methods=['POST'])
    def mouse_click():
        payload = request.get_json(silent=True) or {}
        result, status = backend.handle_click(payload)
        return jsonify(result), status

    return app


class MouseWindow(QMainWindow):
    def __init__(self, local_ip: str, port: int):
        super().__init__()
        self._local_ip = local_ip
        self._port = port
        self.setWindowTitle("Virtual Mouse Server")
        self.setWindowIcon(QIcon(ICON_PATH))
        self.setFixedSize(500, 200)

        self.setStyleSheet("background-color: #2b2b2b;")

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)

        ip_label = QLabel(local_ip)
        ip_label.setStyleSheet(
            "font-size: 54px; font-weight: bold; color: #ffffff; background-color: transparent;"
        )
        ip_label.setAlignment(Qt.AlignCenter)
        
        layout.addWidget(ip_label)

        self.setCentralWidget(central)

        self._setup_tray()
        self._closing = False

    def _setup_tray(self):
        self.tray = QSystemTrayIcon(QIcon(ICON_PATH), self)
        self.tray.setToolTip(
            f"Virtual Mouse Server — {self._local_ip}:{self._port}"
        )

        menu = QMenu()

        show_action = QAction("Show window", self)
        show_action.triggered.connect(self.show_window)
        menu.addAction(show_action)

        ip_action = QAction(f"IP: {self._local_ip}", self)
        ip_action.setEnabled(False)
        menu.addAction(ip_action)

        menu.addSeparator()

        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(self.quit_app)
        menu.addAction(quit_action)

        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

    def _on_tray_activated(self, reason):
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self.show_window()

    def show_window(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, event):
        if self._closing:
            event.accept()
            return
        event.ignore()
        self.hide()

    def quit_app(self):
        self._closing = True
        self.tray.hide()
        QApplication.quit()


def main():
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    system = platform.system()
    if system not in ("Linux", "Windows"):
        print(f"Unsupported system: {system}")
        sys.exit(1)

    backend = create_backend()
    backend.init()

    local_ip = get_local_ip()
    app = build_app(backend)

    def start_flask():
        app.run(
            host='0.0.0.0',
            port=PORT,
            debug=False,
            use_reloader=False,
            threaded=True,
            request_handler=SilentHandler,
        )

    flask_thread = threading.Thread(target=start_flask, daemon=True)
    flask_thread.start()

    print(f"{local_ip}:{PORT}")

    qt_app = QApplication(sys.argv)
    qt_app.setQuitOnLastWindowClosed(False)
    qt_app.setWindowIcon(QIcon(ICON_PATH))

    window = MouseWindow(local_ip, PORT)
    window.show()

    sys.exit(qt_app.exec_())


if __name__ == '__main__':
    main()