# backends/linux_x11.py — input synthesis + screenshot for X11 sessions, via
# the XTEST extension and raw Xlib calls (python-xlib).
#
# deps: python-xlib, Pillow
#
# Unlike the Wayland backend, X11 needs no portal, no human consent dialog,
# and no restore-token cache: XTEST gives true absolute pointer positioning
# and key synthesis directly against the X server. AT-SPI's SCREEN-coordinate
# extents are also real absolute desktop coordinates here (confirmed against
# `xdotool getwindowgeometry` — matches to within a window-decoration inset),
# unlike Wayland where they're always (0, 0) — so _screenshot() below crops
# to the app's frame instead of falling back to the full screen.
#
# CONFIRMED on real hardware (Kali/XFCE/xfwm4, 2026-07): X11 input synthesis
# and screen capture are purely hardware/screen-position based — they are NOT
# routed through the accessibility tree the way AT-SPI's do_action() is. If
# the scoped app's window is not actually the topmost window on screen (e.g.
# covered by a terminal), XTEST clicks/keystrokes land on whatever window IS
# on top at those coordinates, and _screenshot()'s crop captures that same
# wrong window. _ensure_active() below raises + focuses the scoped app's
# window (via EWMH _NET_ACTIVE_WINDOW, matched by PID) before every input or
# screenshot call to guarantee it's actually the one receiving them. This is
# a real, load-bearing fix, not defensive dead code — reproduced directly by
# typing into a background app and finding the keystrokes landed in whatever
# terminal was on top instead.
#
# Caveat: _ensure_active() depends on an EWMH-compliant window manager
# exposing _NET_CLIENT_LIST / _NET_ACTIVE_WINDOW (true for xfwm4, mutter,
# KWin, most others). Without EWMH support it silently no-ops — clicks/keys
# still work if the window already happens to be topmost.
#
# Caveat carried over from the Wayland backend: this assumes a single,
# non-Xinerama X screen. Multi-monitor/HiDPI coordinate drift is unverified.

import io
import time

from Xlib import X, display
from Xlib.ext import xtest
from Xlib.protocol import event as xevent

from PIL import Image

from .linux_common import LinuxCommonBackend


class LinuxX11Backend(LinuxCommonBackend):
    def __init__(self, app_name: str, auto_launch: bool = True, timeout: int = 30, launch_cmd: str | None = None):
        self._display = display.Display()
        self._window = None  # resolved + cached top-level window, see _resolve_window
        super().__init__(app_name, auto_launch, timeout, launch_cmd)

    # ── window activation (see module docstring) ────────────────────────────

    def _resolve_window(self):
        """Find the scoped app's top-level window by matching _NET_WM_PID against our AT-SPI pid."""
        if self._window is not None:
            return self._window
        if self._pid is None:
            return None

        root = self._display.screen().root
        try:
            client_list = root.get_full_property(self._display.intern_atom("_NET_CLIENT_LIST"), X.AnyPropertyType)
        except Exception:
            client_list = None
        if client_list is None:
            return None

        net_wm_pid = self._display.intern_atom("_NET_WM_PID")
        for wid in client_list.value:
            win = self._display.create_resource_object("window", wid)
            try:
                pid_prop = win.get_full_property(net_wm_pid, X.AnyPropertyType)
                if pid_prop and pid_prop.value and pid_prop.value[0] == self._pid:
                    self._window = win
                    return win
            except Exception:
                continue
        return None

    def _ensure_active(self) -> None:
        """Raise and focus the scoped app's window if it isn't already the active one."""
        win = self._resolve_window()
        if win is None:
            return

        root = self._display.screen().root
        net_active_window = self._display.intern_atom("_NET_ACTIVE_WINDOW")
        try:
            active = root.get_full_property(net_active_window, X.AnyPropertyType)
            if active and active.value and active.value[0] == win.id:
                return
        except Exception:
            pass

        try:
            ev = xevent.ClientMessage(
                window=win,
                client_type=net_active_window,
                data=(32, [1, X.CurrentTime, 0, 0, 0]),
            )
            root.send_event(ev, event_mask=X.SubstructureRedirectMask | X.SubstructureNotifyMask)
            win.configure(stack_mode=X.Above)
            self._display.sync()
            time.sleep(0.1)  # give the WM a beat to actually raise/focus before we act
        except Exception:
            pass

    # ── input synthesis ─────────────────────────────────────────────────────

    def _mouse_click(self, x: float, y: float) -> None:
        self._ensure_active()
        xtest.fake_input(self._display, X.MotionNotify, x=int(x), y=int(y))
        self._display.sync()
        xtest.fake_input(self._display, X.ButtonPress, 1)
        self._display.sync()
        time.sleep(0.05)
        xtest.fake_input(self._display, X.ButtonRelease, 1)
        self._display.sync()

    def _keycode_for_keysym(self, keysym: int) -> int:
        keycode = self._display.keysym_to_keycode(keysym)
        if keycode:
            return keycode
        # Not bound in the current keyboard mapping (e.g. a Unicode character
        # outside the active layout) — temporarily bind it to the highest
        # keycode, the same scratch-slot trick xdotool uses for `type`.
        scratch = self._display.display.info.max_keycode
        self._display.change_keyboard_mapping(scratch, [[keysym, 0, 0, 0]])
        self._display.sync()
        return scratch

    def _key_event(self, keysym: int, down: bool) -> None:
        self._ensure_active()
        keycode = self._keycode_for_keysym(keysym)
        xtest.fake_input(self._display, X.KeyPress if down else X.KeyRelease, keycode)
        self._display.sync()

    # ── screenshot ───────────────────────────────────────────────────────────

    def _screenshot(self) -> bytes:
        self._ensure_active()
        screen = self._display.screen()
        root = screen.root

        try:
            x, y, w, h = self._frame_extents()
            x, y, w, h = int(x), int(y), int(w), int(h)
            # Clamp to the root window — AT-SPI's extents can run slightly
            # off-screen (e.g. a maximized window's decoration inset).
            x = max(0, min(x, screen.width_in_pixels - 1))
            y = max(0, min(y, screen.height_in_pixels - 1))
            w = max(1, min(w, screen.width_in_pixels - x))
            h = max(1, min(h, screen.height_in_pixels - y))
        except RuntimeError:
            geom = root.get_geometry()
            x, y, w, h = 0, 0, geom.width, geom.height

        raw = root.get_image(x, y, w, h, X.ZPixmap, 0xFFFFFFFF)
        img = Image.frombytes("RGB", (w, h), raw.data, "raw", "BGRX")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    # ── lifecycle ────────────────────────────────────────────────────────────

    def close(self) -> None:
        try:
            self._display.close()
        except Exception:
            pass
