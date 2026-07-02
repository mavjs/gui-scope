# gui_scope.py — process-scoped GUI automation shim, macOS + Linux (Wayland/X11)
#
# deps: see pyproject.toml (platform-specific via sys_platform markers)
#
# permissions:
#   macOS         — System Settings → Privacy & Security → Accessibility → grant your terminal
#   Linux/Wayland — active graphical session with xdg-desktop-portal(-gnome)
#                   running; first run needs one-time consent via a GNOME dialog
#   Linux/X11     — no consent needed; EWMH-compliant window manager required
#                   so gui-scope can raise/focus the target app's window
#
# usage:
#   scope = GUIScope("Burp Suite")            # launches app if not running
#   scope = GUIScope("Burp Suite", auto_launch=False)  # fail if not running
#   pass scope.tools to your model/provider
#   call scope.dispatch(tool_name, tool_inputs) when the model requests a tool

import json
import base64

from backends import get_backend_class


class GUIScope:
    """
    Read/write access to a single application via the OS accessibility API.
    Launches the application automatically if it is not already running.
    Exposes a provider-agnostic tool surface: pass self.tools to any model,
    route calls through self.dispatch().
    """

    def __init__(self, app_name: str, auto_launch: bool = True, timeout: int = 30, launch_cmd: str | None = None):
        backend_cls = get_backend_class()
        self._backend = backend_cls(app_name, auto_launch, timeout, launch_cmd)

    def close(self) -> None:
        self._backend.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.close()

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
                                "up, down, left, right. Also accepts a raw "
                                "platform-specific key code as a decimal integer string."
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
            return json.dumps(self._backend._get_tree(inputs.get("max_depth", 6)), indent=2)

        elif name == "click_element":
            result = self._backend._click(
                role=inputs.get("role"),
                title=inputs.get("title"),
                description=inputs.get("description"),
            )
            return json.dumps({"ok": result == "ok", "result": result})

        elif name == "type_into":
            ok = self._backend._type_into(
                text=inputs["text"],
                role=inputs.get("role"),
                title=inputs.get("title"),
                description=inputs.get("description"),
            )
            return json.dumps({"ok": ok})

        elif name == "screenshot":
            png = self._backend._screenshot()
            b64 = base64.standard_b64encode(png).decode()
            return [{"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": b64}}]

        elif name == "press_key":
            ok = self._backend._press_key(inputs["key"])
            return json.dumps({"ok": ok})

        return json.dumps({"error": f"unknown tool: {name}"})
