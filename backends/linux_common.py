# backends/linux_common.py — AT-SPI2 accessibility layer, shared across every
# Linux display server (Wayland, and later X11). Only input synthesis and
# screenshot capture differ per display server — those are left as abstract
# seams (`_mouse_click`, `_key_event`, `_screenshot`) for subclasses to fill.
#
# deps: PyGObject (gi.repository.Atspi, gi.repository.Gio), psutil
#
# NOTE: whether Java/Swing labels (via java-atk-wrapper, e.g. Burp Suite) land
# in get_name() or get_description() is unverified on real hardware — treat
# the title->get_name()/description->get_description() mapping below as a
# starting hypothesis, not a settled fact. Likewise, whether JTabbedPane tabs
# expose a working Action interface (so no macOS-style tab-select fallback is
# needed) is unverified.

import shlex
import subprocess
import time

import gi

gi.require_version("Atspi", "2.0")
gi.require_version("Gio", "2.0")
from gi.repository import Atspi, Gio  # noqa: E402

from .base import GUIScopeBackend  # noqa: E402

try:
    import psutil
except ImportError:  # pragma: no cover - psutil is a hard dep on Linux, but degrade gracefully
    psutil = None


def _safe(acc, attr: str):
    """Call an Atspi.Accessible getter defensively — stale/defunct refs raise."""
    try:
        v = getattr(acc, attr)()
        return v if v is not None else ""
    except Exception:
        return ""


def _iface(acc, getter_name: str):
    """Return an interface proxy (e.g. get_action_iface) or None if unsupported."""
    try:
        return getattr(acc, getter_name)()
    except Exception:
        return None


class LinuxCommonBackend(GUIScopeBackend):
    def __init__(self, app_name: str, auto_launch: bool = True, timeout: int = 30, launch_cmd: str | None = None):
        self._acc = self._connect(app_name, auto_launch, timeout, launch_cmd)
        self._pid = None
        try:
            self._pid = self._acc.get_process_id()
        except Exception:
            pass

    # ── connection ───────────────────────────────────────────────────────────

    def _connect(self, app_name: str, auto_launch: bool, timeout: int, launch_cmd: str | None):
        acc = self._try_connect(app_name)
        if acc:
            return acc

        if not auto_launch:
            raise RuntimeError(f"'{app_name}' not found — is it running?")

        self._launch(app_name, launch_cmd)

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            time.sleep(0.5)
            acc = self._try_connect(app_name)
            if acc:
                return acc

        raise RuntimeError(
            f"'{app_name}' did not become available within {timeout}s — "
            "check the app name and that AT-SPI (at-spi2-registryd) is running"
        )

    def _try_connect(self, app_name: str):
        """
        Enumerate AT-SPI-registered applications (Atspi.get_desktop(0)'s
        children) and match by name — exact, then case-insensitive — mirroring
        macOS's NSWorkspace matching order. Falls back to PID cross-reference
        via psutil for apps whose AT-SPI name differs from their process name.
        """
        desktop = Atspi.get_desktop(0)
        n = desktop.get_child_count()

        exact, ci = None, None
        candidates = []
        for i in range(n):
            try:
                app = desktop.get_child_at_index(i)
            except Exception:
                continue
            candidates.append(app)
            name = _safe(app, "get_name")
            if name == app_name:
                exact = app
            elif ci is None and name.lower() == app_name.lower():
                ci = app

        for app in (exact, ci):
            if app is not None and self._is_alive(app):
                return app

        # PID fallback: find a running process whose name/cmdline matches
        # app_name, then find the AT-SPI application with that PID.
        if psutil is not None:
            target_pids = set()
            for proc in psutil.process_iter(["pid", "name", "cmdline"]):
                try:
                    if proc.info["name"] == app_name or app_name in (proc.info["cmdline"] or []):
                        target_pids.add(proc.info["pid"])
                except Exception:
                    continue
            for app in candidates:
                try:
                    if app.get_process_id() in target_pids and self._is_alive(app):
                        return app
                except Exception:
                    continue

        return None

    def _is_alive(self, acc) -> bool:
        try:
            return bool(_safe(acc, "get_role_name"))
        except Exception:
            return False

    def _launch(self, app_name: str, launch_cmd: str | None) -> None:
        print(f"launching '{app_name}'...", flush=True)

        if launch_cmd:
            self._spawn_detached(shlex.split(launch_cmd))
            return

        # 1. Look for a matching .desktop entry (exact name, then case-insensitive).
        try:
            app_infos = Gio.AppInfo.get_all()
        except Exception:
            app_infos = []

        exact, ci = None, None
        for info in app_infos:
            name = info.get_display_name() or info.get_name() or ""
            if name == app_name:
                exact = info
                break
            if ci is None and name.lower() == app_name.lower():
                ci = info

        info = exact or ci
        if info is not None:
            try:
                info.launch(None, None)
                return
            except Exception:
                pass  # fall through to literal executable

        # 2. Fallback: treat app_name as a literal executable on $PATH.
        self._spawn_detached([app_name])

    def _spawn_detached(self, argv: list[str]) -> None:
        """
        Launch a long-lived GUI app without tying its stdio to ours — a plain
        subprocess.Popen(argv) inherits our stdout/stderr fds, so if we're
        running inside a shell pipeline (e.g. `gui-scope tree | head`), the
        launched app holds the pipe open for its entire lifetime and every
        downstream reader blocks forever waiting for EOF that never comes.
        """
        subprocess.Popen(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )

    # ── tree ─────────────────────────────────────────────────────────────────

    def _get_tree(self, max_depth: int) -> dict:
        return self._node(self._acc, 0, max_depth)

    def _node(self, acc, depth: int, max_depth: int) -> dict:
        out = {
            "role":  _safe(acc, "get_role_name"),
            "title": _safe(acc, "get_name"),
            "value": str(self._value_of(acc))[:300],
            "desc":  _safe(acc, "get_description"),
        }
        if depth < max_depth:
            children = []
            try:
                n = acc.get_child_count()
                for i in range(n):
                    try:
                        child = acc.get_child_at_index(i)
                        if child is not None:
                            children.append(self._node(child, depth + 1, max_depth))
                    except Exception:
                        continue
            except Exception:
                pass
            out["children"] = children
        return out

    def _value_of(self, acc):
        value_iface = _iface(acc, "get_value_iface")
        if value_iface is not None:
            try:
                return value_iface.get_current_value()
            except Exception:
                pass
        try:
            text_iface = acc.get_text_iface()
            if text_iface is not None:
                return text_iface.get_text(0, -1)
        except Exception:
            pass
        return ""

    # ── find ─────────────────────────────────────────────────────────────────

    def _criteria(self, role, title, description) -> dict:
        kwargs = {}
        if role:        kwargs["role"]        = role
        if title:       kwargs["title"]       = title
        if description: kwargs["description"] = description
        if not kwargs:
            raise ValueError("Provide at least one search criterion")
        return kwargs

    def _matches(self, acc, criteria: dict) -> bool:
        getters = {"role": "get_role_name", "title": "get_name", "description": "get_description"}
        return all(_safe(acc, getters[k]) == v for k, v in criteria.items())

    def _find(self, role: str = None, title: str = None, description: str = None):
        criteria = self._criteria(role, title, description)
        return self._find_in(self._acc, criteria)

    def _find_all(self, role: str = None, title: str = None, description: str = None) -> list:
        criteria = self._criteria(role, title, description)
        results = []
        self._collect_in(self._acc, criteria, results)
        return results

    def _find_in(self, acc, criteria: dict):
        if self._matches(acc, criteria):
            return acc
        try:
            for i in range(acc.get_child_count()):
                child = acc.get_child_at_index(i)
                if child is None:
                    continue
                result = self._find_in(child, criteria)
                if result is not None:
                    return result
        except Exception:
            pass
        return None

    def _collect_in(self, acc, criteria: dict, out: list) -> None:
        if self._matches(acc, criteria):
            out.append(acc)
        try:
            for i in range(acc.get_child_count()):
                child = acc.get_child_at_index(i)
                if child is not None:
                    self._collect_in(child, criteria, out)
        except Exception:
            pass

    # ── click ────────────────────────────────────────────────────────────────

    def _click(self, role: str = None, title: str = None, description: str = None) -> str:
        candidates = self._find_all(role=role, title=title, description=description)
        if not candidates:
            return "not_found"

        for acc in candidates:
            try:
                states = acc.get_state_set()
                # STATE_ENABLED is unreliable on GTK4/AT-SPI — many fully
                # clickable widgets never set it even though they're
                # sensitive and actionable. Only gate on SENSITIVE.
                if not states.contains(Atspi.StateType.SENSITIVE):
                    continue
            except Exception:
                pass

            action_iface = _iface(acc, "get_action_iface")
            if action_iface is not None:
                try:
                    n = action_iface.get_n_actions()
                    # Index 0 is *usually* the default/primary action, but
                    # GTK tree-table cells (e.g. Thunar's file list) are a
                    # confirmed exception: they expose "expand or contract"
                    # at index 0 and the actual open/click behavior as a
                    # separate "activate" action — do_action(0) there
                    # returns True (successfully toggles a nonexistent
                    # expander on a leaf row) without doing what a real
                    # click does. Prefer an action literally named
                    # "activate" if one exists, then fall back to trying
                    # every action by index.
                    order = list(range(n))
                    try:
                        names = [action_iface.get_action_name(i) for i in order]
                        if "activate" in names:
                            order.remove(names.index("activate"))
                            order.insert(0, names.index("activate"))
                    except Exception:
                        pass
                    for i in order:
                        try:
                            if action_iface.do_action(i):
                                return "ok"
                        except Exception:
                            continue
                except Exception:
                    pass

            # Position-based click fallback — only if the element has real geometry.
            comp_iface = _iface(acc, "get_component_iface")
            if comp_iface is not None:
                try:
                    extents = comp_iface.get_extents(Atspi.CoordType.SCREEN)
                    if extents.width > 0 or extents.height > 0:
                        x = extents.x + extents.width / 2
                        y = extents.y + extents.height / 2
                        self._mouse_click(x, y)
                        return "ok"
                except Exception:
                    pass

        return "action_failed"

    # ── type ─────────────────────────────────────────────────────────────────

    def _type_into(self, text: str, role: str = None, title: str = None, description: str = None) -> bool:
        acc = self._find(role=role, title=title, description=description)
        if acc is None:
            return False

        comp_iface = _iface(acc, "get_component_iface")
        if comp_iface is not None:
            try:
                comp_iface.grab_focus()
            except Exception:
                pass

        edit_iface = _iface(acc, "get_editable_text_iface")
        if edit_iface is not None:
            try:
                # insert_text at the caret, not set_text_contents — the latter
                # replaces the *entire* buffer, which silently destroys any
                # text already in the field (confirmed on real hardware:
                # typing a second line into Mousepad after the first wiped the
                # first line out). Mirrors macOS's typeString(), which types
                # at the cursor rather than replacing the field's value.
                text_iface = _iface(acc, "get_text_iface")
                offset = None
                if text_iface is not None:
                    try:
                        offset = text_iface.get_caret_offset()
                    except Exception:
                        offset = None
                if offset is None or offset < 0:
                    try:
                        offset = text_iface.get_character_count() if text_iface is not None else 0
                    except Exception:
                        offset = 0
                edit_iface.insert_text(offset, text, len(text))
                if text_iface is not None:
                    try:
                        text_iface.set_caret_offset(offset + len(text))
                    except Exception:
                        pass
                return True
            except Exception:
                pass

        # Last-resort fallback: synthesize keystrokes one character at a time.
        try:
            for ch in text:
                self._type_char(ch)
            return True
        except Exception:
            return False

    def _type_char(self, ch: str) -> None:
        keysym = keysym_for_char(ch)
        self._key_event(keysym, True)
        self._key_event(keysym, False)

    # ── abstract seams for display-server-specific subclasses ──────────────────

    def _mouse_click(self, x: float, y: float) -> None:
        raise NotImplementedError

    def _key_event(self, keysym: int, down: bool) -> None:
        raise NotImplementedError

    def _press_key(self, key: str) -> bool:
        keysym = keysym_for_key(key)
        if keysym is None:
            return False
        self._key_event(keysym, True)
        self._key_event(keysym, False)
        return True

    def _screenshot(self) -> bytes:
        raise NotImplementedError

    # ── screenshot geometry helper (shared) ─────────────────────────────────────

    def _frame_extents(self):
        """Find the app's top-level Atspi.Role.FRAME and return (x, y, w, h) in screen coords."""
        frame = self._find_frame(self._acc)
        if frame is None:
            raise RuntimeError(
                "No window found for scoped application — "
                "ensure the app has at least one open window"
            )
        comp_iface = frame.get_component_iface()
        extents = comp_iface.get_extents(Atspi.CoordType.SCREEN)
        return extents.x, extents.y, extents.width, extents.height

    def _find_frame(self, acc):
        try:
            if _safe(acc, "get_role_name") == "frame":
                return acc
            for i in range(acc.get_child_count()):
                child = acc.get_child_at_index(i)
                if child is not None:
                    found = self._find_frame(child)
                    if found is not None:
                        return found
        except Exception:
            pass
        return None


# X11 keysym constants for named keys, mirroring macOS's _KEY_CODES table.
_NAMED_KEYSYMS: dict[str, int] = {
    "return": 0xFF0D, "enter": 0xFF0D,
    "tab": 0xFF09,
    "escape": 0xFF1B, "esc": 0xFF1B,
    "space": 0x0020,
    "delete": 0xFF08, "backspace": 0xFF08,
    "up": 0xFF52, "down": 0xFF54, "left": 0xFF51, "right": 0xFF53,
}


def keysym_for_char(ch: str) -> int:
    """
    Map a single character to an X11 keysym. Printable Latin-1 characters
    have keysym values numerically identical to their code point; other
    Unicode characters use the standard 0x01000000+codepoint convention.
    """
    code = ord(ch)
    if 0x20 <= code <= 0xFF:
        return code
    return 0x01000000 + code


def keysym_for_key(key: str) -> int | None:
    """Resolve a press_key tool 'key' argument (name or raw int string) to a keysym."""
    named = _NAMED_KEYSYMS.get(key.lower())
    if named is not None:
        return named
    try:
        return int(key)
    except ValueError:
        return None
