# backends/linux_wayland.py — input synthesis + screenshot via
# xdg-desktop-portal's RemoteDesktop and Screenshot D-Bus interfaces.
#
# deps: PyGObject (gi.repository.Gio, GLib), Pillow
#
# REQUIRES an active, logged-in graphical session with xdg-desktop-portal +
# xdg-desktop-portal-gnome running. Cannot function on a headless box — the
# portal calls block waiting for a compositor-brokered response.
#
# First run (or first run after the cached token is invalidated) blocks on a
# GNOME "Allow input control?" consent dialog that a human must approve.
# Subsequent runs reuse backends/wayland_token.py's cached restore_token to
# skip that dialog — PENDING LIVE VERIFICATION on the target box.
#
# NOTE: there is no true absolute pointer-positioning call available without
# an active ScreenCast session (NotifyPointerMotionAbsolute requires a
# PipeWire stream id). _mouse_click uses a corner-warp + relative-move
# technique instead — best-effort, not a guaranteed-precise absolute move.
# Verify click precision and any HiDPI/multi-monitor coordinate drift by hand.

import io
import time
import urllib.parse

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib  # noqa: E402

from PIL import Image  # noqa: E402

from .linux_common import LinuxCommonBackend, keysym_for_key
from . import wayland_token

_PORTAL_BUS_NAME = "org.freedesktop.portal.Desktop"
_PORTAL_OBJECT_PATH = "/org/freedesktop/portal/desktop"

_BTN_LEFT = 272  # Linux evdev BTN_LEFT

_DEVICE_KEYBOARD = 1
_DEVICE_POINTER = 2


class _PortalError(RuntimeError):
    pass


class LinuxWaylandBackend(LinuxCommonBackend):
    def __init__(self, app_name: str, auto_launch: bool = True, timeout: int = 30, launch_cmd: str | None = None):
        super().__init__(app_name, auto_launch, timeout, launch_cmd)
        self._bus = None
        self._rd_session_handle = None  # RemoteDesktop session object path
        self._req_counter = 0

    # ── D-Bus plumbing ───────────────────────────────────────────────────────

    def _session_bus(self):
        if self._bus is None:
            self._bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        return self._bus

    def _proxy(self, interface_name: str) -> Gio.DBusProxy:
        return self._object_proxy(_PORTAL_OBJECT_PATH, interface_name)

    def _object_proxy(self, object_path: str, interface_name: str) -> Gio.DBusProxy:
        return Gio.DBusProxy.new_sync(
            self._session_bus(),
            Gio.DBusProxyFlags.NONE,
            None,
            _PORTAL_BUS_NAME,
            object_path,
            interface_name,
            None,
        )

    def _call_and_wait(self, proxy: Gio.DBusProxy, method: str, args: GLib.Variant, timeout: float = 30.0) -> dict:
        """
        Every portal method call returns a Request object path; the actual
        result arrives asynchronously via a Request.Response signal on that
        path. This blocks (via a nested GLib.MainLoop) until that signal
        fires or `timeout` elapses.
        """
        result = proxy.call_sync(method, args, Gio.DBusCallFlags.NONE, -1, None)
        handle = result.unpack()[0]

        loop = GLib.MainLoop()
        response = {}

        def on_response(_connection, _sender, _path, _iface, _signal, params):
            code, results = params.unpack()
            response["code"] = code
            response["results"] = results
            loop.quit()

        sub_id = self._session_bus().signal_subscribe(
            _PORTAL_BUS_NAME,
            "org.freedesktop.portal.Request",
            "Response",
            handle,
            None,
            Gio.DBusSignalFlags.NONE,
            on_response,
        )

        def on_timeout():
            loop.quit()
            return False

        timeout_id = GLib.timeout_add(int(timeout * 1000), on_timeout)

        try:
            loop.run()
        finally:
            self._session_bus().signal_unsubscribe(sub_id)
            GLib.source_remove(timeout_id)

        if "code" not in response:
            raise _PortalError(
                f"portal call {method!r} timed out after {timeout}s waiting for a Response — "
                "check that a graphical session with xdg-desktop-portal(-gnome) is active"
            )
        if response["code"] != 0:
            raise _PortalError(f"portal call {method!r} was denied or cancelled (code={response['code']})")
        return response["results"]

    def _new_request_token(self) -> str:
        self._req_counter += 1
        return f"guiscope{self._req_counter}"

    # ── RemoteDesktop session (lazy, cached) ────────────────────────────────

    def _remote_desktop_session(self) -> str:
        if self._rd_session_handle is not None:
            return self._rd_session_handle

        proxy = self._proxy("org.freedesktop.portal.RemoteDesktop")

        create_opts = {
            "handle_token": GLib.Variant("s", self._new_request_token()),
            "session_handle_token": GLib.Variant("s", self._new_request_token()),
        }
        results = self._call_and_wait(
            proxy, "CreateSession", GLib.Variant("(a{sv})", (create_opts,))
        )
        session_handle = results["session_handle"]

        restore_token = wayland_token.load_token() or ""
        select_opts = {
            "handle_token": GLib.Variant("s", self._new_request_token()),
            "types": GLib.Variant("u", _DEVICE_KEYBOARD | _DEVICE_POINTER),
            "persist_mode": GLib.Variant("u", 2),
        }
        if restore_token:
            select_opts["restore_token"] = GLib.Variant("s", restore_token)

        self._call_and_wait(
            proxy, "SelectDevices", GLib.Variant("(oa{sv})", (session_handle, select_opts))
        )

        start_opts = {"handle_token": GLib.Variant("s", self._new_request_token())}
        # Blocks here on first run / invalidated token until a human clicks "Allow".
        start_results = self._call_and_wait(
            proxy, "Start", GLib.Variant("(osa{sv})", (session_handle, "", start_opts)), timeout=120.0
        )

        new_token = start_results.get("restore_token")
        if new_token:
            wayland_token.save_token(new_token)

        self._rd_session_handle = session_handle
        return session_handle

    def _rd_call(self, method: str, args: GLib.Variant) -> None:
        proxy = self._proxy("org.freedesktop.portal.RemoteDesktop")
        proxy.call_sync(method, args, Gio.DBusCallFlags.NONE, -1, None)

    # ── input synthesis ─────────────────────────────────────────────────────

    def _mouse_click(self, x: float, y: float) -> None:
        session_handle = self._remote_desktop_session()
        empty_opts = {}

        # Best-effort absolute positioning: warp to the virtual desktop's
        # top-left corner (clamped by the compositor), then move by the
        # target's absolute screen offset. Not a true absolute move — verify
        # precision and multi-monitor/HiDPI behavior on real hardware.
        self._rd_call(
            "NotifyPointerMotion",
            GLib.Variant("(oa{sv}dd)", (session_handle, empty_opts, -100000.0, -100000.0)),
        )
        self._rd_call(
            "NotifyPointerMotion",
            GLib.Variant("(oa{sv}dd)", (session_handle, empty_opts, float(x), float(y))),
        )

        self._rd_call(
            "NotifyPointerButton",
            GLib.Variant("(oa{sv}iu)", (session_handle, empty_opts, _BTN_LEFT, 1)),
        )
        time.sleep(0.05)
        self._rd_call(
            "NotifyPointerButton",
            GLib.Variant("(oa{sv}iu)", (session_handle, empty_opts, _BTN_LEFT, 0)),
        )

    def _key_event(self, keysym: int, down: bool) -> None:
        session_handle = self._remote_desktop_session()
        self._rd_call(
            "NotifyKeyboardKeysym",
            GLib.Variant("(oa{sv}iu)", (session_handle, {}, keysym, 1 if down else 0)),
        )

    def _press_key(self, key: str) -> bool:
        keysym = keysym_for_key(key)
        if keysym is None:
            return False
        self._key_event(keysym, True)
        self._key_event(keysym, False)
        return True

    # ── screenshot ───────────────────────────────────────────────────────────

    def _screenshot(self) -> bytes:
        # Confirmed on real hardware (GNOME Remote Desktop/mutter headless
        # session, 2026-07): Atspi.Component position is always (0, 0)
        # regardless of coordinate type or the window's true on-screen
        # position — cropping to "frame extents" would crop to the wrong
        # region whenever the window isn't literally at the desktop origin.
        # Until a reliable absolute-position source is confirmed (GetWindows
        # needs a full ScreenCast+PipeWire session, not just RemoteDesktop —
        # untested whether that would even help under a headless/RDP mutter
        # session), return the full screen uncropped rather than silently
        # cropping to a coordinate we can't trust. Still validate the app has
        # a window at all.
        self._frame_extents()

        proxy = self._proxy("org.freedesktop.portal.Screenshot")
        opts = {
            "handle_token": GLib.Variant("s", self._new_request_token()),
            "interactive": GLib.Variant("b", False),
        }
        # Confirmed: `interactive: false` suppresses the crop-picker dialog
        # on this xdg-desktop-portal-gnome version.
        results = self._call_and_wait(proxy, "Screenshot", GLib.Variant("(sa{sv})", ("", opts)))
        uri = results["uri"]

        parsed = urllib.parse.urlparse(uri)
        path = urllib.parse.unquote(parsed.path)

        img = Image.open(path)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    # ── lifecycle ────────────────────────────────────────────────────────────

    def close(self) -> None:
        if self._rd_session_handle is not None:
            try:
                proxy = self._object_proxy(self._rd_session_handle, "org.freedesktop.portal.Session")
                proxy.call_sync("Close", GLib.Variant("()", ()), Gio.DBusCallFlags.NONE, -1, None)
            except Exception:
                pass
            self._rd_session_handle = None
