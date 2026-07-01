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
        raise RuntimeError(
            "gui-scope: Linux X11 sessions are not yet supported "
            f"(XDG_SESSION_TYPE={session_type!r}) — Wayland support ships first, "
            "X11 is planned as a follow-up"
        )

    raise RuntimeError(f"gui-scope: unsupported platform {system!r}")
