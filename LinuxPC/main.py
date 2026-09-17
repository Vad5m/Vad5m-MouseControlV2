#!/usr/bin/env python3
import socket
from flask import Flask, request, jsonify
from werkzeug.serving import WSGIRequestHandler
import mouse

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

def main():
    PORT = 42000
    mouse.init_uinput()
    mouse.start_worker()
    ip = get_local_ip()
    print(f"{ip}:{PORT}")
    app.run(host='0.0.0.0', port=PORT, debug=False, use_reloader=False,
            threaded=True, request_handler=SilentHandler)

if __name__ == '__main__':
    main()