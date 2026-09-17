#!/usr/bin/env python3
"""MOUSE"""

import json
import queue
import threading
import time
import traceback
import urllib.request

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.graphics import Color, RoundedRectangle
from kivy.logger import Logger
from kivy.metrics import dp
from kivy.storage.jsonstore import JsonStore
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget

try:
    from android.permissions import request_permissions, Permission
    ANDROID = True
except ImportError:
    ANDROID = False

    class Permission:
        INTERNET = 'android.permission.INTERNET'
        ACCESS_NETWORK_STATE = 'android.permission.ACCESS_NETWORK_STATE'
        ACCESS_WIFI_STATE = 'android.permission.ACCESS_WIFI_STATE'
        CHANGE_WIFI_STATE = 'android.permission.CHANGE_WIFI_STATE'
        CHANGE_NETWORK_STATE = 'android.permission.CHANGE_NETWORK_STATE'
        ACCESS_FINE_LOCATION = 'android.permission.ACCESS_FINE_LOCATION'
        ACCESS_COARSE_LOCATION = 'android.permission.ACCESS_COARSE_LOCATION'
        WRITE_EXTERNAL_STORAGE = 'android.permission.WRITE_EXTERNAL_STORAGE'
        READ_EXTERNAL_STORAGE = 'android.permission.READ_EXTERNAL_STORAGE'
        MANAGE_EXTERNAL_STORAGE = 'android.permission.MANAGE_EXTERNAL_STORAGE'
        CAMERA = 'android.permission.CAMERA'
        RECORD_AUDIO = 'android.permission.RECORD_AUDIO'
        READ_PHONE_STATE = 'android.permission.READ_PHONE_STATE'
        READ_PHONE_NUMBERS = 'android.permission.READ_PHONE_NUMBERS'
        CALL_PHONE = 'android.permission.CALL_PHONE'
        READ_CALL_LOG = 'android.permission.READ_CALL_LOG'
        WRITE_CALL_LOG = 'android.permission.WRITE_CALL_LOG'
        PROCESS_OUTGOING_CALLS = 'android.permission.PROCESS_OUTGOING_CALLS'
        READ_CONTACTS = 'android.permission.READ_CONTACTS'
        WRITE_CONTACTS = 'android.permission.WRITE_CONTACTS'
        GET_ACCOUNTS = 'android.permission.GET_ACCOUNTS'
        READ_CALENDAR = 'android.permission.READ_CALENDAR'
        WRITE_CALENDAR = 'android.permission.WRITE_CALENDAR'
        POST_NOTIFICATIONS = 'android.permission.POST_NOTIFICATIONS'
        BLUETOOTH_SCAN = 'android.permission.BLUETOOTH_SCAN'
        BLUETOOTH_CONNECT = 'android.permission.BLUETOOTH_CONNECT'
        BLUETOOTH_ADVERTISE = 'android.permission.BLUETOOTH_ADVERTISE'
        NEARBY_WIFI_DEVICES = 'android.permission.NEARBY_WIFI_DEVICES'
        BLUETOOTH = 'android.permission.BLUETOOTH'
        BLUETOOTH_ADMIN = 'android.permission.BLUETOOTH_ADMIN'
        WAKE_LOCK = 'android.permission.WAKE_LOCK'
        VIBRATE = 'android.permission.VIBRATE'
        RECEIVE_BOOT_COMPLETED = 'android.permission.RECEIVE_BOOT_COMPLETED'
        FOREGROUND_SERVICE = 'android.permission.FOREGROUND_SERVICE'

    def request_permissions(perms, callback=None):
        Logger.info(f'Permissions: пропущено (не Android): {perms}')
        if callback:
            callback(perms, [True] * len(perms))


PERMISSIONS_TO_REQUEST = [
    Permission.INTERNET,
    Permission.ACCESS_NETWORK_STATE,
    Permission.ACCESS_WIFI_STATE,
    Permission.CHANGE_WIFI_STATE,
    Permission.CHANGE_NETWORK_STATE,
    Permission.NEARBY_WIFI_DEVICES,
    Permission.ACCESS_FINE_LOCATION,
    Permission.ACCESS_COARSE_LOCATION,
    Permission.READ_EXTERNAL_STORAGE,
    Permission.WRITE_EXTERNAL_STORAGE,
    Permission.CAMERA,
    Permission.RECORD_AUDIO,
    Permission.READ_PHONE_STATE,
    Permission.READ_PHONE_NUMBERS,
    Permission.CALL_PHONE,
    Permission.READ_CALL_LOG,
    Permission.WRITE_CALL_LOG,
    Permission.PROCESS_OUTGOING_CALLS,
    Permission.READ_CONTACTS,
    Permission.WRITE_CONTACTS,
    Permission.GET_ACCOUNTS,
    Permission.READ_CALENDAR,
    Permission.WRITE_CALENDAR,
    Permission.POST_NOTIFICATIONS,
    Permission.BLUETOOTH_SCAN,
    Permission.BLUETOOTH_CONNECT,
    Permission.BLUETOOTH_ADVERTISE,
    Permission.BLUETOOTH,
    Permission.BLUETOOTH_ADMIN,
    Permission.WAKE_LOCK,
    Permission.VIBRATE,
    Permission.RECEIVE_BOOT_COMPLETED,
    Permission.FOREGROUND_SERVICE,
]


def _on_permissions_result(permissions, grants):
    for perm, granted in zip(permissions, grants):
        status = 'OK' if granted else 'DENIED'
        Logger.info(f'Permissions: {perm} -> {status}')


DEFAULT_HOST = "192.168.1.42"
DEFAULT_PORT = 42000
API_PREFIX = '/mouse'

TAP_MAX_DURATION = 0.25
DOUBLE_TAP_WINDOW = 0.30
SCROLL_DIV = 12.0

CONFIG_FILE = 'vmconnect_config.json'


def show_error(message, title='Error', duration=3.0):
    def _show(dt):
        try:
            popup = Popup(
                title=title,
                content=Label(text=str(message)[:500], halign='center',
                              valign='middle'),
                size_hint=(0.85, 0.4),
                auto_dismiss=True,
            )
            popup.content.bind(size=lambda w, s: setattr(w, 'text_size', s))
            popup.open()
            if duration:
                Clock.schedule_once(lambda _dt: popup.dismiss(), duration)
        except Exception as e:
            Logger.error(f'show_error failed: {e}')

    Clock.schedule_once(_show, 0)


class HttpSender:
    def __init__(self, base_url_provider, on_error=None):
        self._base_url_provider = base_url_provider
        self._on_error = on_error
        self._queue = queue.Queue(maxsize=256)
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()

    def send(self, endpoint, payload):
        try:
            self._queue.put_nowait((endpoint, payload))
        except queue.Full:
            try:
                self._queue.get_nowait()
                self._queue.put_nowait((endpoint, payload))
            except (queue.Empty, queue.Full):
                pass

    def stop(self):
        self._stop.set()
        try:
            self._queue.put_nowait((None, None))
        except queue.Full:
            pass

    def _worker(self):
        while not self._stop.is_set():
            try:
                endpoint, payload = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue
            except Exception as e:
                Logger.error(f'HttpSender worker: {e}')
                continue

            if endpoint is None:
                break

            if endpoint == '/move':
                dx = float(payload.get('dx', 0.0))
                dy = float(payload.get('dy', 0.0))
                while True:
                    try:
                        nxt_ep, nxt_pl = self._queue.get_nowait()
                    except queue.Empty:
                        break
                    if nxt_ep == '/move':
                        dx += float(nxt_pl.get('dx', 0.0))
                        dy += float(nxt_pl.get('dy', 0.0))
                    else:
                        try:
                            self._queue.put_nowait((nxt_ep, nxt_pl))
                        except queue.Full:
                            pass
                        break
                payload = {'dx': dx, 'dy': dy}

            try:
                url = self._base_url_provider() + endpoint
            except Exception as e:
                self._report(f'bad base url: {e}')
                continue

            self._post(url, payload)

    def _post(self, url, payload):
        try:
            data = json.dumps(payload).encode('utf-8')
            req = urllib.request.Request(
                url, data=data,
                headers={'Content-Type': 'application/json'},
                method='POST',
            )
            urllib.request.urlopen(req, timeout=1.5)
        except Exception as e:
            Logger.warning(f'HttpSender: {url} -> {e}')
            self._report(f'{type(e).__name__}: {e}')

    def _report(self, msg):
        if not self._on_error:
            return
        try:
            Clock.schedule_once(lambda dt: self._on_error(msg), 0)
        except Exception:
            pass


class RoundedButton(Widget):
    def __init__(self, on_press=None,
                 bg_color=(0.23, 0.23, 0.24, 1),
                 pressed_color=(0.36, 0.36, 0.38, 1),
                 radius=None, **kwargs):
        super().__init__(**kwargs)
        self._on_press_cb = on_press
        self.bg_color = bg_color
        self.pressed_color = pressed_color
        if radius is None:
            radius = dp(20)
        with self.canvas:
            self._color = Color(*bg_color)
            self._rect = RoundedRectangle(pos=self.pos, size=self.size,
                                          radius=[radius])
        self.bind(pos=self._update_rect, size=self._update_rect)

    def _update_rect(self, *args):
        self._rect.pos = self.pos
        self._rect.size = self.size

    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos):
            touch.grab(self)
            self._color.rgba = self.pressed_color
            return True
        return False

    def on_touch_up(self, touch):
        if touch.grab_current is self:
            touch.ungrab(self)
            self._color.rgba = self.bg_color
            if self.collide_point(*touch.pos) and self._on_press_cb:
                try:
                    self._on_press_cb()
                except Exception as e:
                    Logger.error(f'button press: {e}')
                    show_error(str(e), title='Button error')
            return True
        return False


class RoundedTextInput(AnchorLayout):
    """
    Поле ввода в стиле RoundedButton: серый закруглённый фон,
    внутри — прозрачный TextInput без рамок и белого прямоугольника.
    """

    def __init__(self,
                 text='',
                 on_text=None,
                 input_filter=None,
                 bg_color=(0.23, 0.23, 0.24, 1),
                 fg_color=(0.95, 0.95, 0.95, 1),
                 cursor_color=(0.95, 0.95, 0.95, 1),
                 hint_text='',
                 radius=None,
                 **kwargs):
        super().__init__(**kwargs)
        self._on_text_cb = on_text
        if radius is None:
            radius = dp(20)
        self._radius = radius

        with self.canvas.before:
            self._color = Color(*bg_color)
            self._rect = RoundedRectangle(pos=self.pos, size=self.size,
                                          radius=[radius])
        self.bind(pos=self._update_rect, size=self._update_rect)

        self._input = TextInput(
            text=text,
            hint_text=hint_text,
            multiline=False,
            input_filter=input_filter,
            background_color=(0, 0, 0, 0),
            background_normal='',
            background_active='',
            foreground_color=fg_color,
            cursor_color=cursor_color,
            cursor_width=dp(1.5),
            font_size=dp(16),
            halign='center',
            padding=(dp(8), dp(8)),
            size_hint=(1, 1),
        )
        self.add_widget(self._input)
        if self._on_text_cb:
            self._input.bind(text=lambda inst, val: self._on_text_cb(val))

    def _update_rect(self, *args):
        self._rect.pos = self.pos
        self._rect.size = self.size

    @property
    def text(self):
        return self._input.text

    @text.setter
    def text(self, value):
        self._input.text = value


class Touchpad(Widget):
    def __init__(self, on_send, on_long_tap=None,
                 tap_max_distance=None, **kwargs):
        super().__init__(**kwargs)
        self._on_send = on_send
        self._on_long_tap = on_long_tap
        self.tap_max_distance = (tap_max_distance
                                 if tap_max_distance is not None
                                 else dp(15))
        self._touches = {}
        self._two_finger = False
        self._last_scroll_avg_y = None
        self._scroll_accum = 0.0
        self._last_tap_time = None
        self._long_tap_event = None

        with self.canvas.before:
            Color(0.17, 0.17, 0.18, 1)
            self._bg = RoundedRectangle(pos=self.pos, size=self.size,
                                        radius=[dp(28)])
        self.bind(pos=self._update_bg, size=self._update_bg)

    def _update_bg(self, *args):
        self._bg.pos = self.pos
        self._bg.size = self.size

    def _safe_send(self, endpoint, payload):
        try:
            self._on_send(endpoint, payload)
        except Exception as e:
            Logger.error(f'send {endpoint}: {e}')
            show_error(f'{endpoint}: {e}', title='Send error')

    def on_touch_down(self, touch):
        if not self.collide_point(*touch.pos):
            return False
        touch.grab(self)
        self._touches[touch.uid] = {
            'start': touch.pos, 'last': touch.pos,
            'time': time.time(), 'moved': False,
        }
        if len(self._touches) == 1:
            if self._on_long_tap:
                self._long_tap_event = Clock.schedule_once(
                    lambda dt: self._fire_long_tap(touch.uid), 0.7)
        if len(self._touches) == 2:
            self._cancel_long_tap()
            for info in self._touches.values():
                info['moved'] = True
            self._two_finger = True
            ys = [i['last'][1] for i in self._touches.values()]
            self._last_scroll_avg_y = sum(ys) / len(ys)
            self._scroll_accum = 0.0
        return True

    def _fire_long_tap(self, uid):
        self._long_tap_event = None
        if uid in self._touches and not self._touches[uid]['moved']:
            if self._on_long_tap:
                try:
                    self._on_long_tap()
                except Exception as e:
                    Logger.error(f'long tap: {e}')
                    show_error(str(e), title='Settings error')

    def _cancel_long_tap(self):
        if self._long_tap_event is not None:
            self._long_tap_event.cancel()
            self._long_tap_event = None

    def on_touch_move(self, touch):
        if touch.uid not in self._touches:
            return False
        info = self._touches[touch.uid]
        prev_x, prev_y = info['last']

        if self._two_finger and len(self._touches) >= 2:
            info['last'] = touch.pos
            ys = [i['last'][1] for i in self._touches.values()]
            avg_y = sum(ys) / len(ys)
            if self._last_scroll_avg_y is not None:
                delta = -(avg_y - self._last_scroll_avg_y) / SCROLL_DIV
                self._scroll_accum += delta
                whole = int(self._scroll_accum)
                if whole != 0:
                    self._scroll_accum -= whole
                    self._safe_send('/scroll', {'delta': whole})
                self._last_scroll_avg_y = avg_y
            return True

        if len(self._touches) == 1:
            sx, sy = info['start']
            if (abs(touch.x - sx) > self.tap_max_distance or
                    abs(touch.y - sy) > self.tap_max_distance):
                info['moved'] = True
                self._cancel_long_tap()

            dx = touch.x - prev_x
            dy = touch.y - prev_y
            info['last'] = touch.pos
            if dx != 0 or dy != 0:
                self._safe_send('/move', {'dx': dx, 'dy': -dy})
        else:
            info['last'] = touch.pos
        return True

    def on_touch_up(self, touch):
        if touch.uid not in self._touches:
            return False
        touch.ungrab(self)
        info = self._touches.pop(touch.uid)
        self._cancel_long_tap()

        duration = time.time() - info['time']
        was_two_finger = self._two_finger

        if len(self._touches) < 2:
            self._two_finger = False
            self._last_scroll_avg_y = None
            self._scroll_accum = 0.0

        if (not was_two_finger and not info['moved']
                and duration < TAP_MAX_DURATION):
            now = time.time()
            if (self._last_tap_time is not None
                    and now - self._last_tap_time < DOUBLE_TAP_WINDOW):
                self._last_tap_time = None
                self._safe_send('/click', {'button': 'right'})
            else:
                self._last_tap_time = now
                Clock.schedule_once(
                    lambda dt, t=now: self._maybe_left_click(t),
                    DOUBLE_TAP_WINDOW,
                )
        return True

    def _maybe_left_click(self, tap_time):
        if self._last_tap_time == tap_time:
            self._last_tap_time = None
            self._safe_send('/click', {'button': 'left'})


class SettingsPopup(Popup):
    def __init__(self, current_host, current_port, on_save, **kwargs):
        super().__init__(**kwargs)
        self.title = 'Server settings'
        self.size_hint = (0.9, 0.5)
        self.auto_dismiss = False

        layout = BoxLayout(orientation='vertical', spacing=dp(10),
                           padding=dp(12))

        layout.add_widget(Label(text='Host (IP or domain):',
                                size_hint=(1, None), height=dp(24)))
        self.host_input = TextInput(text=current_host, multiline=False,
                                    size_hint=(1, None), height=dp(44))
        layout.add_widget(self.host_input)

        layout.add_widget(Label(text='Port:', size_hint=(1, None),
                                height=dp(24)))
        self.port_input = TextInput(text=str(current_port), multiline=False,
                                    input_filter='int',
                                    size_hint=(1, None), height=dp(44))
        layout.add_widget(self.port_input)

        btns = BoxLayout(size_hint=(1, None), height=dp(48), spacing=dp(10))
        cancel = Button(text='Cancel')
        save = Button(text='Save')
        cancel.bind(on_release=lambda *_: self.dismiss())
        save.bind(on_release=self._save)
        btns.add_widget(cancel)
        btns.add_widget(save)
        layout.add_widget(btns)

        self.add_widget(layout)
        self._on_save = on_save

    def _save(self, *_):
        try:
            host = self.host_input.text.strip() or DEFAULT_HOST
            try:
                port = int(self.port_input.text.strip() or DEFAULT_PORT)
            except ValueError:
                port = DEFAULT_PORT
            self._on_save(host, port)
            self.dismiss()
        except Exception as e:
            Logger.error(f'save settings: {e}')
            show_error(str(e), title='Settings error')


class MouseApp(App):
    title = 'VMConnect'

    def build(self):
        try:
            Window.clearcolor = (0.10, 0.10, 0.10, 1)

            try:
                self.store = JsonStore(CONFIG_FILE)
                if self.store.exists('server'):
                    cfg = self.store.get('server')
                    self.host = cfg.get('host', DEFAULT_HOST)
                    self.port = cfg.get('port', DEFAULT_PORT)
                else:
                    self.host = DEFAULT_HOST
                    self.port = DEFAULT_PORT
                    self.store.put('server', host=self.host, port=self.port)
            except Exception as e:
                Logger.error(f'config: {e}')
                show_error(f'config: {e}', title='Config error')
                self.host = DEFAULT_HOST
                self.port = DEFAULT_PORT

            self.sender = HttpSender(
                base_url_provider=self._base_url,
                on_error=self._on_http_error,
            )

            root = BoxLayout(orientation='vertical', padding=dp(16),
                             spacing=dp(12))

            self.ip_input = RoundedTextInput(
                text=self.host,
                on_text=self._on_ip_changed,
                input_filter=self._ip_filter,
                hint_text='192.168.1.42',
                size_hint=(1, None),
                height=dp(48),
            )
            root.add_widget(self.ip_input)

            self.touchpad = Touchpad(
                on_send=self._send,
                on_long_tap=self._open_settings,
                tap_max_distance=dp(15),
                size_hint=(1, 1),
            )
            root.add_widget(self.touchpad)

            buttons = BoxLayout(orientation='horizontal',
                                size_hint=(1, None), height=dp(110),
                                spacing=dp(16))
            buttons.add_widget(RoundedButton(
                on_press=lambda: self._press_button('left')))
            buttons.add_widget(RoundedButton(
                on_press=lambda: self._press_button('right')))
            root.add_widget(buttons)

            Clock.schedule_once(
                lambda dt: self._request_android_permissions(), 0.5)

            return root

        except Exception as e:
            tb = traceback.format_exc()
            Logger.error(f'build failed: {e}\n{tb}')
            show_error(f'{type(e).__name__}: {e}', title='Startup error',
                       duration=6.0)
            fallback = BoxLayout(orientation='vertical', padding=dp(16))
            fallback.add_widget(Label(text=f'Startup error:\n{e}',
                                      halign='center', valign='middle'))
            return fallback

    def _ip_filter(self, substring, from_undo):
        return ''.join(c for c in substring if c.isdigit() or c == '.')

    def _on_ip_changed(self, value):
        try:
            host = value.strip()
            if not host:
                return
            self.host = host
            self.store.put('server', host=self.host, port=self.port)
        except Exception as e:
            Logger.error(f'on_ip_changed: {e}')

    def _request_android_permissions(self):
        try:
            Logger.info('Permissions: запрашиваю набор разрешений...')
            request_permissions(PERMISSIONS_TO_REQUEST, _on_permissions_result)
        except Exception as e:
            Logger.error(f'request_permissions: {e}')
            show_error(str(e), title='Permissions error')

    def _base_url(self):
        return f'http://{self.host}:{self.port}{API_PREFIX}'

    def _open_settings(self):
        try:
            SettingsPopup(
                current_host=self.host,
                current_port=self.port,
                on_save=self._apply_settings,
            ).open()
        except Exception as e:
            Logger.error(f'open settings: {e}')
            show_error(str(e), title='Settings error')

    def _apply_settings(self, host, port):
        try:
            self.host = host
            self.port = port
            self.store.put('server', host=host, port=port)
            if self.ip_input.text != host:
                self.ip_input.text = host
        except Exception as e:
            Logger.error(f'apply settings: {e}')
            show_error(str(e), title='Settings error')

    def _send(self, endpoint, payload):
        try:
            self.sender.send(endpoint, payload)
        except Exception as e:
            Logger.error(f'send {endpoint}: {e}')
            show_error(f'{endpoint}: {e}', title='Send error')

    def _on_http_error(self, err):
        Logger.warning(f'HTTP error: {err}')
        show_error(err, title='Connection error', duration=2.5)

    def _press_button(self, button):
        self._send('/click', {'button': button})

    def on_stop(self):
        try:
            self.sender.stop()
        except Exception:
            pass


if __name__ == '__main__':
    def _excepthook(exc_type, exc_value, exc_tb):
        msg = ''.join(traceback.format_exception_only(exc_type, exc_value))
        Logger.error(f'Unhandled: {msg}')
        try:
            show_error(msg, title='Unhandled error', duration=5.0)
        except Exception:
            pass

    import sys as _sys
    _sys.excepthook = _excepthook

    try:
        MouseApp().run()
    except Exception as e:
        tb = traceback.format_exc()
        print(tb, file=_sys.stderr)
        try:
            from kivy.logger import Logger as _L
            _L.error(f'Fatal: {e}\n{tb}')
        except Exception:
            pass
