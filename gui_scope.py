# gui_scope.py — process-scoped macOS AX shim
#
# deps:
#   pip install atomacos pyobjc-framework-Quartz pyobjc-framework-Cocoa
#
# permissions:
#   System Settings → Privacy & Security → Accessibility → grant your terminal
#
# usage:
#   scope = GUIScope("Burp Suite")            # launches app if not running
#   scope = GUIScope("Burp Suite", auto_launch=False)  # fail if not running
#   pass scope.tools to your model/provider
#   call scope.dispatch(tool_name, tool_inputs) when the model requests a tool

import base64
import json
import subprocess
import time

import AppKit
import atomacos
import Quartz


class GUIScope:
    """
    Read/write access to a single macOS application via the Accessibility API.
    Launches the application automatically if it is not already running.
    Exposes a provider-agnostic tool surface: pass self.tools to any model,
    route calls through self.dispatch().
    """

    def __init__(self, app_name: str, auto_launch: bool = True, timeout: int = 30):
        self._app = self._connect(app_name, auto_launch, timeout)
        self._pid: int = self._app.pid

    def _connect(self, app_name: str, auto_launch: bool, timeout: int):
        # Try to find the app (running or after launch) and return a usable AX ref.
        app = self._try_connect(app_name)
        if app:
            return app

        if not auto_launch:
            raise RuntimeError(f"'{app_name}' not found — is it running?")

        print(f"launching '{app_name}'...", flush=True)
        subprocess.Popen(["open", "-a", app_name])

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            time.sleep(0.5)
            app = self._try_connect(app_name)
            if app:
                return app

        raise RuntimeError(
            f"'{app_name}' did not become available within {timeout}s — "
            "check the app name and Accessibility permissions"
        )

    def _try_connect(self, app_name: str):
        """
        Attempt to get a usable AX ref for the named app.
        Tries name-based lookup first, then falls back to PID via NSWorkspace
        (needed for Java/Electron apps whose AX name can differ from their
        display name, or when the name-based ref returns an empty tree).
        """
        import AppKit  # already a dep via pyobjc-framework-Cocoa

        # Collect all running candidates — exact match, then case-insensitive
        candidates: list[int] = []
        for running in AppKit.NSWorkspace.sharedWorkspace().runningApplications():
            name = running.localizedName() or ""
            if name == app_name:
                candidates.insert(0, running.processIdentifier())
            elif name.lower() == app_name.lower():
                candidates.append(running.processIdentifier())

        for pid in candidates:
            try:
                app = atomacos.getAppRefByPid(pid)
                # Confirm the AX bridge is active: role must be non-empty
                if app and app.AXRole:
                    return app
            except Exception:
                continue

        # Last resort: atomacos name lookup (catches apps with display names
        # that NSWorkspace reports differently)
        try:
            app = atomacos.getAppRefByLocalizedName(app_name)
            if app and app.AXRole:
                return app
        except (ValueError, Exception):
            pass

        return None

    # ── tool definitions (JSON Schema — provider-agnostic) ───────────────────

    @property
    def tools(self) -> list[dict]:
        return [
            {
                "name": "get_tree",
                "description": (
                    "Return the application's full UI accessibility tree as JSON. "
                    "Call this first to understand current state before acting."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "max_depth": {
                            "type": "integer",
                            "description": "Depth limit (default 6). Use 3-4 for a quick overview.",
                            "default": 6,
                        }
                    },
                },
            },
            {
                "name": "click_element",
                "description": "Find a UI element by role and/or title and press it.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "role":        {"type": "string", "description": "AXRole, e.g. AXButton"},
                        "title":       {"type": "string", "description": "AXTitle, e.g. 'Send'"},
                        "description": {"type": "string", "description": "AXDescription"},
                    },
                },
            },
            {
                "name": "type_into",
                "description": "Focus a UI element and type text into it.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "text":        {"type": "string", "description": "Text to type"},
                        "role":        {"type": "string"},
                        "title":       {"type": "string"},
                        "description": {"type": "string"},
                    },
                    "required": ["text"],
                },
            },
            {
                "name": "screenshot",
                "description": (
                    "Capture the application window as a PNG. "
                    "Use when the AX tree is ambiguous or a canvas element is not in the tree."
                ),
                "input_schema": {"type": "object", "properties": {}},
            },
            {
                "name": "press_key",
                "description": (
                    "Press a keyboard key. Use after type_into to submit a form or confirm "
                    "input (e.g. press 'return' after typing a URL)."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "key": {
                            "type": "string",
                            "description": (
                                "Key name: return, tab, escape, space, delete, "
                                "up, down, left, right. Also accepts a raw macOS "
                                "virtual key code as a decimal integer string."
                            ),
                        }
                    },
                    "required": ["key"],
                },
            },
        ]

    # ── dispatch ─────────────────────────────────────────────────────────────

    def dispatch(self, name: str, inputs: dict) -> str | list[dict]:
        """
        Route a tool call and return a result.
        Returns a JSON string for text results, or a list of content blocks for images.
        Your agent loop decides how to package this into the provider's tool_result format.
        """
        if name == "get_tree":
            return json.dumps(self._get_tree(inputs.get("max_depth", 6)), indent=2)

        elif name == "click_element":
            result = self._click(
                role=inputs.get("role"),
                title=inputs.get("title"),
                description=inputs.get("description"),
            )
            return json.dumps({"ok": result == "ok", "result": result})

        elif name == "type_into":
            ok = self._type_into(
                text=inputs["text"],
                role=inputs.get("role"),
                title=inputs.get("title"),
                description=inputs.get("description"),
            )
            return json.dumps({"ok": ok})

        elif name == "screenshot":
            png = self._screenshot()
            b64 = base64.standard_b64encode(png).decode()
            return [{"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": b64}}]

        elif name == "press_key":
            ok = self._press_key(inputs["key"])
            return json.dumps({"ok": ok})

        return json.dumps({"error": f"unknown tool: {name}"})

    # ── internals ─────────────────────────────────────────────────────────────

    def _get_tree(self, max_depth: int) -> dict:
        return self._node(self._app, 0, max_depth)

    def _node(self, el, depth: int, max_depth: int) -> dict:
        def safe(attr):
            try:
                v = getattr(el, attr)
                return v if v is not None else ""
            except Exception:
                return ""

        out = {
            "role":  safe("AXRole"),
            "title": safe("AXTitle"),
            "value": str(safe("AXValue"))[:300],
            "desc":  safe("AXDescription"),
        }
        if depth < max_depth:
            try:
                out["children"] = [self._node(c, depth + 1, max_depth) for c in (el.AXChildren or [])]
            except Exception:
                out["children"] = []
        return out

    def _find(self, role: str = None, title: str = None, description: str = None):
        kwargs = {}
        if role:        kwargs["AXRole"]        = role
        if title:       kwargs["AXTitle"]       = title
        if description: kwargs["AXDescription"] = description
        if not kwargs:
            raise ValueError("Provide at least one search criterion")
        return self._find_in(self._app, **kwargs)

    def _find_all(self, role: str = None, title: str = None, description: str = None) -> list:
        kwargs = {}
        if role:        kwargs["AXRole"]        = role
        if title:       kwargs["AXTitle"]       = title
        if description: kwargs["AXDescription"] = description
        if not kwargs:
            raise ValueError("Provide at least one search criterion")
        results = []
        self._collect_in(self._app, kwargs, results)
        return results

    def _find_in(self, el, **criteria):
        """
        Recursive search using the same safe accessor as _get_tree.
        atomacos.findFirst uses its own attribute access which breaks on
        Java/Swing apps; this avoids that entirely.
        """
        def safe(attr):
            try:
                v = getattr(el, attr)
                return v if v is not None else ""
            except Exception:
                return ""

        if all(safe(k) == v for k, v in criteria.items()):
            return el

        try:
            for child in (el.AXChildren or []):
                result = self._find_in(child, **criteria)
                if result is not None:
                    return result
        except Exception:
            pass

        return None

    def _collect_in(self, el, criteria: dict, out: list) -> None:
        """Collect all elements matching criteria (DFS). Same safe accessor as _find_in."""
        def safe(attr):
            try:
                v = getattr(el, attr)
                return v if v is not None else ""
            except Exception:
                return ""

        if all(safe(k) == v for k, v in criteria.items()):
            out.append(el)

        try:
            # AXTabs exposes tab buttons separately from AXChildren (tab pages).
            tabs = []
            try:
                tabs = el.AXTabs or []
            except Exception:
                pass
            seen = set()
            for tab in tabs:
                seen.add(id(tab))
                self._collect_in(tab, criteria, out)
            for child in (el.AXChildren or []):
                if id(child) not in seen:
                    self._collect_in(child, criteria, out)
        except Exception:
            pass

    def _click(self, role: str = None, title: str = None, description: str = None) -> str:
        """
        Returns 'ok', 'not_found', or 'action_failed'.
        Tries every matching element in DFS order. For each candidate, tries
        AXPress first then a Quartz position-based click. Moves on to the next
        candidate only if the element has no usable position (i.e. it is a
        non-interactive label). This handles Java/Swing UIs where the same
        description text appears on both a label and the real interactive control.
        """
        candidates = self._find_all(role=role, title=title, description=description)
        if not candidates:
            return "not_found"

        for el in candidates:
            # AXEnabled=False means the element is inert — skip it.
            try:
                if el.AXEnabled is False:
                    continue
            except Exception:
                pass

            # Try AXPress first, then every action the element actually declares.
            # Java/Swing elements often register non-standard names like 'Pick'
            # rather than 'AXPress', so el.Press() silently fails while
            # el.performAction('Pick') works.
            tried = set()
            try:
                el.Press()
                return "ok"
            except Exception:
                tried.add("AXPress")

            try:
                for action in (el.getActions() or []):
                    if action in tried:
                        continue
                    tried.add(action)
                    try:
                        el.performAction(action)
                        return "ok"
                    except Exception:
                        pass
            except Exception:
                pass

            # Position-based mouse click — only when the element has a real hit area.
            try:
                pos  = el.AXPosition
                size = el.AXSize
                if size.width > 0 or size.height > 0:
                    x = pos.x + size.width  / 2
                    y = pos.y + size.height / 2
                    self._mouse_click(x, y)
                    return "ok"
            except Exception:
                pass

        # Fallback for Java/Swing tabs: find the AXTabGroup that owns a child
        # matching the criteria and select it by setting AXValue on the group.
        if self._try_tab_select(role=role, title=title, description=description):
            return "ok"

        return "action_failed"

    def _try_tab_select(self, role: str = None, title: str = None, description: str = None) -> bool:
        """
        Java/Swing JTabbedPane tabs have no AXActions and zero geometry, so
        AXPress and position clicks both fail. The AX way to select a tab is to
        set AXValue on the parent AXTabGroup to the desired child element.
        """
        kwargs = {}
        if role:        kwargs["AXRole"]        = role
        if title:       kwargs["AXTitle"]       = title
        if description: kwargs["AXDescription"] = description
        return self._tab_select_in(self._app, kwargs)

    def _tab_select_in(self, el, criteria: dict) -> bool:
        def safe(node, attr):
            try:
                v = getattr(node, attr)
                return v if v is not None else ""
            except Exception:
                return ""

        try:
            if safe(el, "AXRole") == "AXTabGroup":
                # AXTabs holds the clickable tab buttons; AXChildren holds pages.
                # Try both. For each candidate: Press() first, then AXValue fallback.
                candidates = []
                try:
                    candidates += list(el.AXTabs or [])
                except Exception:
                    pass
                try:
                    candidates += list(el.AXChildren or [])
                except Exception:
                    pass

                for tab in candidates:
                    if all(safe(tab, k) == v for k, v in criteria.items()):
                        try:
                            tab.Press()
                            return True
                        except Exception:
                            pass
                        try:
                            el.AXValue = tab
                            return True
                        except Exception:
                            pass

            for child in (el.AXChildren or []):
                if self._tab_select_in(child, criteria):
                    return True
        except Exception:
            pass

        return False

    _KEY_CODES: dict[str, int] = {
        "return": 36, "enter": 36,
        "tab": 48,
        "escape": 53, "esc": 53,
        "space": 49,
        "delete": 51, "backspace": 51,
        "up": 126, "down": 125, "left": 123, "right": 124,
    }

    def _press_key(self, key: str) -> bool:
        code = self._KEY_CODES.get(key.lower())
        if code is None:
            try:
                code = int(key)
            except ValueError:
                return False
        down = Quartz.CGEventCreateKeyboardEvent(None, code, True)
        up   = Quartz.CGEventCreateKeyboardEvent(None, code, False)
        # Post directly to the scoped process so the key lands regardless of
        # which app has focus when the script runs.
        Quartz.CGEventPostToPid(self._pid, down)
        Quartz.CGEventPostToPid(self._pid, up)
        return True

    def _mouse_click(self, x: float, y: float) -> None:
        """Post a left-click at absolute screen coordinates via Quartz."""
        point = (x, y)
        down = Quartz.CGEventCreateMouseEvent(
            None, Quartz.kCGEventLeftMouseDown, point, Quartz.kCGMouseButtonLeft
        )
        up = Quartz.CGEventCreateMouseEvent(
            None, Quartz.kCGEventLeftMouseUp, point, Quartz.kCGMouseButtonLeft
        )
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, down)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, up)

    def _type_into(self, text: str, role: str = None, title: str = None, description: str = None) -> bool:
        el = self._find(role=role, title=title, description=description)
        if el is None:
            return False
        try:
            el.AXFocused = True
            el.typeString(text)
            return True
        except Exception:
            try:
                el.AXValue = text
                return True
            except Exception:
                return False

    def _screenshot(self) -> bytes:
        def _find_wid(flags):
            window_list = Quartz.CGWindowListCopyWindowInfo(flags, Quartz.kCGNullWindowID)
            # Prefer normal app windows (layer 0); fall back to any PID match
            matches = [w for w in window_list if w.get("kCGWindowOwnerPID") == self._pid]
            layer0 = [w for w in matches if w.get("kCGWindowLayer", -1) == 0]
            chosen = layer0[0] if layer0 else (matches[0] if matches else None)
            return chosen["kCGWindowNumber"] if chosen else None

        wid = _find_wid(
            Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements
        )
        if wid is None:
            # Fallback: include minimised / off-screen windows
            wid = _find_wid(Quartz.kCGWindowListOptionAll)
        if wid is None:
            raise RuntimeError(
                "No window found for scoped application — "
                "ensure the app has at least one open window"
            )

        cg_image = Quartz.CGWindowListCreateImage(
            Quartz.CGRectNull,
            Quartz.kCGWindowListOptionIncludingWindow,
            wid,
            Quartz.kCGWindowImageBoundsIgnoreFraming,
        )
        bmp = AppKit.NSBitmapImageRep.alloc().initWithCGImage_(cg_image)
        png = bmp.representationUsingType_properties_(AppKit.NSBitmapImageFileTypePNG, None)
        return bytes(png)
