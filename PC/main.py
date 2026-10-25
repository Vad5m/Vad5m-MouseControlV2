import platform
import sys
import os


def main():
    system = platform.system()
    if system == 'Linux':
        import mouse
        import socket
        from flask import Flask, request, jsonify
        from werkzeug.serving import WSGIRequestHandler
        import threading

        from PyQt5.QtWidgets import (
            QApplication, QMainWindow, QLabel, QVBoxLayout, QWidget,
            QSystemTrayIcon, QMenu, QAction
        )
        from PyQt5.QtGui import QIcon
        from PyQt5.QtCore import Qt

        ICON_PATH = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "data", "icon.png"
        )

        app = Flask(__name__)

        class SilentHandler(WSGIRequestHandler):
            def log_request(self, code='-', size='-'):
                pass

            def log_message(self, format, *args):
                pass

        @app.route('/')
        def index():
            return (
                "<h1>Virtual Mouse Server</h1>"
                f"<p>Mouse device: {'OK' if mouse.is_available() else 'NOT AVAILABLE'}</p>"
            )

        @app.route('/mouse/move', methods=['POST'])
        def mouse_move():
            payload = request.get_json(silent=True) or {}
            result, status = mouse.handle_move(payload)
            return jsonify(result), status

        @app.route('/mouse/scroll', methods=['POST'])
        def mouse_scroll():
            payload = request.get_json(silent=True) or {}
            result, status = mouse.handle_scroll(payload)
            return jsonify(result), status

        @app.route('/mouse/click', methods=['POST'])
        def mouse_click():
            payload = request.get_json(silent=True) or {}
            result, status = mouse.handle_click(payload)
            return jsonify(result), status

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

        PORT = 42000
        local_ip = get_local_ip()

        def start_flask():
            app.run(host='0.0.0.0', port=PORT, debug=False, use_reloader=False,
                    threaded=True, request_handler=SilentHandler)

        class MouseWindow(QMainWindow):
            def __init__(self):
                super().__init__()
                self.setWindowTitle("Virtual Mouse Server")
                self.setWindowIcon(QIcon(ICON_PATH))
                self.setFixedSize(500, 200)

                central = QWidget()
                layout = QVBoxLayout(central)
                layout.setContentsMargins(0, 0, 0, 0)

                ip_label = QLabel(local_ip)
                ip_label.setStyleSheet("font-size: 64px; font-weight: bold; color: white;")
                ip_label.setAlignment(Qt.AlignCenter)
                ip_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
                layout.addWidget(ip_label)

                self.setCentralWidget(central)

                self._setup_tray()
                self._closing = False

            def _setup_tray(self):
                self.tray = QSystemTrayIcon(QIcon(ICON_PATH), self)
                self.tray.setToolTip(f"Virtual Mouse Server — {local_ip}:{PORT}")

                menu = QMenu()

                show_action = QAction("Show window", self)
                show_action.triggered.connect(self.show_window)
                menu.addAction(show_action)

                ip_action = QAction(f"IP: {local_ip}", self)
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

        def run_gui():
            mouse.init_uinput()
            mouse.start_worker()

            flask_thread = threading.Thread(target=start_flask, daemon=True)
            flask_thread.start()

            print(f"{local_ip}:{PORT}")

            qt_app = QApplication(sys.argv)
            qt_app.setQuitOnLastWindowClosed(False)
            qt_app.setWindowIcon(QIcon(ICON_PATH))

            window = MouseWindow()
            window.show()

            sys.exit(qt_app.exec_())

        run_gui()

    elif system == 'Windows':
        import importlib
        win_mouse = importlib.import_module('win-mouse')
        win_mouse.main()

    else:
        print(f"Unsupported system: {system}")
        sys.exit(1)


if __name__ == '__main__':
    main()
