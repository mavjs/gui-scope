# AGENT.md

## Project

Process-scoped macOS GUI automation via the Accessibility API. Gives an agent
read/write access to a single application — no shell, no other windows.

## Structure

```
gui-scope/
├── gui_scope.py       # GUIScope class — AX shim and tool surface
├── gui-scope         # CLI for testing all four dispatch paths
├── pyproject.toml     # deps: atomacos, pyobjc-framework-Quartz/Cocoa
├── SKILL.md           # prompt document for injecting into Claude's context
└── openwebui_tool.py  # OpenWebUI tool plugin wrapping GUIScope
```

## Running

```bash
uv run gui-scope tree  --app "Burp Suite" --depth 3
uv run gui-scope click --app "Burp Suite" --description "Next"
uv run gui-scope type  --app "Burp Suite" --description "..." --text "hello"
uv run gui-scope shot  --app "Burp Suite" --out screenshot.png
```

`--app` and all flags go **after** the subcommand name, not before.

## Tool surface

`GUIScope` exposes four methods via `dispatch(name, inputs)`:

| Tool | Returns |
|---|---|
| `get_tree` | JSON string of the AX tree |
| `click_element` | `{"ok": bool, "result": "ok" \| "not_found" \| "action_failed"}` |
| `type_into` | `{"ok": bool}` |
| `screenshot` | list of image content blocks (base64 PNG) |

Provider integration: pass `scope.tools` to the model, route responses through
`scope.dispatch(tool_name, tool_inputs)`.

## Critical gotchas

**Java/Swing apps (Burp Suite)**

- Labels live in `AXDescription`, not `AXTitle`. Always match on `--description`.
- Never use `atomacos.findFirst` — it uses its own attribute access path which
  breaks on the Java AX bridge. `GUIScope` uses a custom `_find_in` with the
  same `safe()` accessor as `_get_tree`; if an element appears in the tree it
  will be found.
- `AXPress` often silently fails on Swing buttons. `_click` falls back to a
  position-based mouse click via `Quartz.CGEventCreateMouseEvent` using the
  element's `AXPosition` + `AXSize`.

**Permissions**

- The process running `gui_scope.py` must have Accessibility permission:
  System Settings → Privacy & Security → Accessibility.
- Symptom of missing permission: `AXRole` raises `AttributeError` or the tree
  returns `{"role": "", "title": "", "value": "", "desc": "", "children": []}`.
- Toggling the permission off and back on is required when re-adding a terminal.

**App lookup**

- `GUIScope.__init__` calls `_try_connect` which enumerates `NSWorkspace`
  running apps by PID and validates with `app.AXRole` before returning.
- Pure `getAppRefByLocalizedName` is only used as a last resort — PID-based
  lookup is more reliable for Java apps.
- App is auto-launched via `open -a` if not running (pass `auto_launch=False`
  to disable). Default timeout is 30s.

**Canvas elements**

- Burp's scanner visualizations and some panes are canvas-rendered and will not
  appear as AX nodes. Use `screenshot` to observe state, then derive
  coordinates from `CGWindowBounds` if pixel-level interaction is required.

## Adding new tools

Add a method to `_dispatch` in `gui_scope.py` and a matching entry in the
`tools` property. Keep the return contract: JSON string for text results, list
of content blocks for images.

## Python version

Requires 3.11+. Pin with `uv python pin 3.12` and run `uv sync`.
