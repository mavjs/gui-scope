# backends/__init__.py — picks a backend class for the current platform.
# gui_scope.py delegates to whatever this returns; no OS-specific module is
# imported until a backend is actually selected.

import os
import platform


def get_backend_class():
    system = platform.system()

    if system == "Darwin":
        from .macos import MacOSBackend
        return MacOSBackend

    if system == "Linux":
        session_type = os.environ.get("XDG_SESSION_TYPE", "").lower()
        if session_type == "wayland":
            from .linux_wayland import LinuxWaylandBackend
            return LinuxWaylandBackend
        if session_type == "x11":
            from .linux_x11 import LinuxX11Backend
            return LinuxX11Backend
        if not session_type and os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
            # XDG_SESSION_TYPE isn't always set (e.g. `startx` without a full
            # session manager) — fall back to $DISPLAY as the X11 signal.
            from .linux_x11 import LinuxX11Backend
            return LinuxX11Backend
        raise RuntimeError(
            "gui-scope: could not detect a supported Linux session "
            f"(XDG_SESSION_TYPE={session_type!r}, DISPLAY={os.environ.get('DISPLAY')!r}, "
            f"WAYLAND_DISPLAY={os.environ.get('WAYLAND_DISPLAY')!r}) — "
            "gui-scope supports Wayland and X11 graphical sessions only"
        )

    raise RuntimeError(f"gui-scope: unsupported platform {system!r}")
