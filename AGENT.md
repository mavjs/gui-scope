# AGENT.md

## Project

Process-scoped GUI automation via the OS accessibility API. Gives an agent
read/write access to a single application — no shell, no other windows.

macOS is fully supported. Linux supports both Wayland (GNOME/mutter, via
xdg-desktop-portal) and X11 (via XTEST/Xlib) — session type is auto-detected
from `XDG_SESSION_TYPE`/`$DISPLAY`.

## Documentation conventions

Keep every markdown file an agent needs to read (`AGENT.md`/`CLAUDE.md`,
`SKILL.md`, `HOWTO.md`, `README.md`, `.claude/commands/*.md`) under 500
lines. If one grows past that, split it rather than letting it keep
growing — e.g. move a large "what we learned" section into its own doc and
link to it, instead of appending indefinitely.

## Structure

```
gui-scope/
├── gui_scope.py            # GUIScope facade — picks a backend, keeps tool surface/dispatch
├── backends/
│   ├── base.py               # GUIScopeBackend contract every backend implements
│   ├── macos.py               # AX/atomacos/Quartz backend
│   ├── linux_common.py         # AT-SPI2 tree/find/click/type — shared X11+Wayland
│   ├── linux_wayland.py         # xdg-desktop-portal input + screenshot
│   ├── linux_x11.py             # XTEST/Xlib input + screenshot, EWMH window activation
│   └── wayland_token.py          # caches the RemoteDesktop consent token
├── cli.py                    # argparse CLI, installed as the `gui-scope` console script
├── pyproject.toml            # deps + [project.scripts] entry point, platform-gated via sys_platform markers
└── SKILL.md                  # prompt document for injecting into Claude's context
```

## Backend architecture

`gui_scope.py` is a thin facade: `GUIScope.__init__` calls
`backends.get_backend_class()` (dispatches on `platform.system()` and, on
Linux, `XDG_SESSION_TYPE`) and delegates all internal calls to
`self._backend`. `tools`/`dispatch()` are shared and never change per
platform — only the private `_get_tree`/`_click`/`_type_into`/`_press_key`/
`_screenshot` implementations differ, per `backends/base.py`'s contract.

`gui_scope.py` must never import an OS-specific module at file scope —
backend selection (and its imports) happens lazily inside
`get_backend_class()`, so the facade stays importable regardless of platform.

## Running

```bash
uv run gui-scope tree  --app "Burp Suite" --depth 3
uv run gui-scope tree  --app "Burp Suite" --flat --role ROLE --query TEXT
uv run gui-scope click --app "Burp Suite" --description "Next"
uv run gui-scope type  --app "Burp Suite" --description "..." --text "hello"
uv run gui-scope shot  --app "Burp Suite"
```

`--app` and all flags go **after** the subcommand name, not before. `shot`
with no `--out` writes into `./.gui-scope/screenshots/` (project-scoped
scratch dir, `.gitignore`d), pruned to the 20 most recent files by default
(`--keep N` to change); `--out FILE` opts out of pruning for an explicit
path. See `cli.py`'s `cmd_shot`/`default_screenshot_dir`/`prune_screenshots`.

`tree --flat` returns a flat `role`/`title`/`desc`/`path` list of
interactive/labeled elements instead of the full nested tree —
`--role`/`--query` narrow it by case-insensitive substring. This exists
specifically to replace writing a one-off Python script to grep the nested
JSON for one element (a recurring pattern before this existed — e.g.
finding a specific file row in a `GtkTreeView`-based file manager listing).
See `gui_scope.py`'s `_flatten_tree`/`_is_interactive_role`.

## Tool surface

`GUIScope` exposes five methods via `dispatch(name, inputs)`:

| Tool | Returns |
|---|---|
| `get_tree` | JSON string of the accessibility tree (or a flat array if `flat: true`, see above) |
| `click_element` | `{"ok": bool, "result": "ok" \| "not_found" \| "action_failed"}` |
| `type_into` | `{"ok": bool}` |
| `press_key` | `{"ok": bool}` |
| `screenshot` | list of image content blocks (base64 PNG) |

Provider integration: pass `scope.tools` to the model, route responses through
`scope.dispatch(tool_name, tool_inputs)`.

## Critical gotchas

**Java/Swing apps (Burp Suite) — macOS**

- Labels live in `AXDescription`, not `AXTitle`. Always match on `--description`.
- Never use `atomacos.findFirst` — it uses its own attribute access path which
  breaks on the Java AX bridge. `MacOSBackend` uses a custom `_find_in` with
  the same `safe()` accessor as `_get_tree`; if an element appears in the tree
  it will be found.
- `AXPress` often silently fails on Swing buttons. `_click` falls back to a
  position-based mouse click via `Quartz.CGEventCreateMouseEvent` using the
  element's `AXPosition` + `AXSize`.

**Permissions — macOS**

- The process running gui-scope must have Accessibility permission:
  System Settings → Privacy & Security → Accessibility.
- Symptom of missing permission: `AXRole` raises `AttributeError` or the tree
  returns `{"role": "", "title": "", "value": "", "desc": "", "children": []}`.
- Toggling the permission off and back on is required when re-adding a terminal.

**App lookup — macOS**

- `MacOSBackend._try_connect` enumerates `NSWorkspace` running apps by PID and
  validates with `app.AXRole` before returning.
- Pure `getAppRefByLocalizedName` is only used as a last resort — PID-based
  lookup is more reliable for Java apps.
- App is auto-launched via `open -a` if not running (pass `auto_launch=False`
  to disable). Default timeout is 30s.

**Canvas elements — macOS**

- Burp's scanner visualizations and some panes are canvas-rendered and will not
  appear as AX nodes. Use `screenshot` to observe state, then derive
  coordinates from `CGWindowBounds` if pixel-level interaction is required.

**Linux/Wayland — headless limitation**

- `LinuxWaylandBackend` needs an active, logged-in graphical session with
  `xdg-desktop-portal` + `xdg-desktop-portal-gnome` running. Portal calls
  block waiting for the compositor to broker a response — this backend
  **cannot run on a headless box with no logged-in session**, unlike the
  macOS/X11 stories.

**Linux/Wayland — consent dialog + token cache (CONFIRMED working)**

- First run (or first run after the cached token is invalidated) of any
  click/key action blocks on a GNOME "Allow input control?" dialog that a
  human must approve. **The "Remember this decision" checkbox in that
  dialog must be checked** — that's the UI-side counterpart to requesting
  `persist_mode=2` in code; without it, GNOME may keep prompting even though
  we request persistence.
- `backends/wayland_token.py` caches the RemoteDesktop `restore_token` at
  `~/.config/gui-scope/wayland_token` (mode 0600). **Confirmed on real
  hardware (CentOS Stream 10/GNOME/mutter, 2026-07-01): after checking
  "Remember this decision" once, subsequent `press_key`/`click_element`
  calls skip the dialog entirely** — no more prompting. If runs keep
  prompting, delete that file and re-approve, making sure to check the
  remember box this time.
- The `Screenshot` portal's consent dialog is a separate, stateless call
  (no session/token) from RemoteDesktop's — whether it re-prompts on every
  `screenshot` call or is remembered per-session is **not yet verified**
  (we've only exercised it once so far); assume it may prompt each time
  until confirmed otherwise.

**Linux/Wayland — click precision**

- There is no true absolute pointer-positioning portal call without an
  active ScreenCast/PipeWire session. `_mouse_click` uses a corner-warp +
  relative-move workaround (`NotifyPointerMotion` to a clamped corner, then a
  relative move to the target). This is best-effort — verify precision,
  especially on multi-monitor or HiDPI-scaled setups, before relying on it
  for small UI targets. X11 does not have this limitation — see the X11
  section below.

**Linux — AT-SPI field mapping (still unverified for Burp/Java specifically)**

- `linux_common.py` maps `title → get_name()` and `description →
  get_description()`, mirroring the macOS `AXTitle`/`AXDescription` split.
  Confirmed working against a native GTK4 app (gnome-text-editor): buttons'
  labels land in `get_description()` (e.g. "New Tab", "Main Menu"), matching
  the hypothesis. Whether Burp's Swing labels would land the same way is
  **still unverified — Burp Suite is currently unreachable via AT-SPI at
  all** (see the java-atk-wrapper gotcha below), so this remains open.
- Similarly, whether JTabbedPane tabs expose a working `Atspi.Action`
  interface is unverified (untested — no tab-group widget was exercised).

**Linux — Java/Swing apps (Burp Suite) are currently unreachable via AT-SPI**

- Confirmed on real hardware: a running Burp Suite process does not appear
  in `Atspi.get_desktop(0)`'s children at all — Java's accessibility bridge
  never activates without `java-atk-wrapper`.
- `java-atk-wrapper` is **not packaged for EL10 / current EPEL** as of
  2026-07 — `sudo dnf install epel-release && sudo dnf install
  java-atk-wrapper` fails because the package doesn't exist for this distro
  version. It's also unmaintained upstream since ~2019.
- Even if built from source, Fedora/EPEL's packaging convention installs it
  JRE-independently — each JRE needs the wrapper's `.jar`/`.so` manually
  symlinked in and its own `accessibility.properties` edited. Burp Suite
  ships its own bundled private JRE (not the system one), so a system-wide
  install wouldn't automatically apply to it regardless.
- **Net effect: Burp Suite specifically cannot be automated via this
  Wayland/AT-SPI backend today.** The rest of the backend (AT-SPI tree
  walk, click, type, press_key, screenshot, portal consent/token flow) is
  confirmed working end-to-end against a native GTK4 app
  (gnome-text-editor) — the blocker is Java accessibility support, not the
  backend implementation.

**Linux — `toolkit-accessibility` gsetting is NOT actually required (correction)**

- Earlier testing assumed GTK apps need
  `gsettings set org.gnome.desktop.interface toolkit-accessibility true` to
  register with AT-SPI at all. **Disproven on real hardware**: with that
  setting explicitly reset to `false`, a freshly-launched gnome-text-editor
  still registered with AT-SPI and `tree`/`click`/`type` all worked
  identically. The actual root cause of the original connection failures
  was the app-name mismatch below, not this setting. It may still matter for
  other toolkits/older GNOME versions, but don't assume it's required.

**Linux — AT-SPI app-name matching uses the executable name, not the display name**

- Confirmed: AT-SPI's `get_name()` for an app returns its process/executable
  name (e.g. `"gnome-text-editor"`), **not** the human-friendly display name
  shown in menus (`"Text Editor"`). Passing `--app "Text Editor"` returns
  `not_found`/times out; `--app "gnome-text-editor"` works. When in doubt,
  check the actual process name (`ps aux`) or query
  `Atspi.get_desktop(0)`'s children directly.

**Linux — click requires only SENSITIVE, not ENABLED (fixed bug)**

- `Atspi.StateType.ENABLED` is unreliable on GTK4 — confirmed a fully
  clickable, sensitive button reported `ENABLED=False` while
  `SENSITIVE=True`. `_click` in `linux_common.py` now gates only on
  `SENSITIVE`; requiring both caused every click to fall through to
  `action_failed` even when a working `Action` interface existed.

**Linux — RemoteDesktop CreateSession needs `session_handle_token` (fixed bug)**

- `CreateSession`'s options dict needs **both** `handle_token` (for the
  Request object) and `session_handle_token` (for the Session object) —
  omitting the latter causes a `Missing token` D-Bus error. Fixed in
  `linux_wayland.py`.

**Linux — AT-SPI never reports true absolute window position (confirmed limitation, downgrades screenshot)**

- Confirmed on real hardware: `Atspi.Component.get_position()`/
  `get_extents()` return `(0, 0)` for a top-level frame's position
  **regardless of `CoordType` (`SCREEN`, `WINDOW`, `PARENT`) and regardless
  of the window's true on-screen position** (moved the window away from the
  origin and re-checked — still `(0, 0)`). Only size is accurate. This
  environment was GNOME Remote Desktop (RDP) into a headless/virtual-monitor
  mutter session — **unconfirmed whether this is specific to that headless
  RDP topology or a general Wayland/mutter limitation**; re-verify on a
  normal (non-RDP) GNOME/Wayland session or VM.
- Tried unlocking real position via `org.gnome.Shell.Introspect.GetWindows`
  (the modern, safer replacement for the old `Shell.Eval`) — denied even
  with an active RemoteDesktop session (`AccessDenied: GetWindows is not
  allowed`). This API likely requires an active **ScreenCast** session too
  (same pattern as `NotifyPointerMotionAbsolute`), which we deliberately
  don't implement (avoids PipeWire/GStreamer bindings for what would
  otherwise just be a one-shot geometry read). Not attempted further given
  the added uncertainty of a second screen-cast session competing with
  `gnome-remote-desktop`'s own in a headless RDP topology.
- **Consequence for `screenshot`**: since window position can't be trusted,
  `_screenshot()` returns the **full, uncropped screen** rather than
  cropping to (unreliable) frame extents — cropping previously produced
  confidently-wrong images (captured an unrelated window at the coordinates
  AT-SPI claimed, twice, in two different tests). Callers must visually
  locate the target app in the returned image. Mitigation worth suggesting
  to users: set the target app "Always on Top" once it's open, so it stays
  visible and unoccluded in every full-screen capture.
- **Consequence for `click_element`**: the position-based click fallback
  (used only when an element has no working `Action` interface) computes
  its target the same way (`extents.x + width/2`) and is very likely
  equally unreliable — **not yet confirmed broken in practice** since every
  button tested so far had a working `Action` interface and never needed
  this fallback path.

**Linux — key/type primitives**

- Each display-server backend's `_key_event(keysym, down)` is the shared
  primitive `linux_common.py`'s character-by-character `type_into` fallback
  calls into (via `keysym_for_char`); `_press_key` itself is a concrete
  method on `LinuxCommonBackend` built on top of that seam, not something
  each backend reimplements — only `_mouse_click`/`_key_event`/`_screenshot`
  are display-server-specific.

**Linux/X11 — no portal, no consent dialog, true absolute positioning (CONFIRMED working)**

- Confirmed on real hardware (Kali/XFCE/xfwm4, 2026-07-02): `LinuxX11Backend`
  uses the XTEST extension (via python-xlib) directly against the X server —
  no `xdg-desktop-portal`, no human consent dialog, no restore-token cache.
  `XTestFakeMotionEvent`/`XTestFakeButtonEvent`/`XTestFakeKeyEvent` give true
  absolute pointer positioning and key synthesis, unlike Wayland's
  corner-warp workaround.
- AT-SPI's `SCREEN`-coordinate extents are real absolute desktop coordinates
  on X11 — confirmed by cross-checking against `xdotool getwindowgeometry`
  (matched to within a window-decoration inset). This is the opposite of the
  Wayland finding above (`(0, 0)` always) — so `_screenshot()` on X11 crops
  to the app's frame instead of falling back to the full screen.
- Unmapped keysyms (e.g. a Unicode character outside the active keyboard
  layout) are handled via the same scratch-keycode remap trick `xdotool`
  uses: bind the keysym to the highest keycode with
  `XChangeKeyboardMapping`, then synthesize against that keycode.

**Linux/X11 — window must be raised + focused before input or screenshot (CONFIRMED bug, fixed)**

- Confirmed on real hardware: X11 input synthesis and screen capture are
  purely hardware/screen-position based — **not** routed through the
  accessibility tree the way AT-SPI's `do_action()` is. Reproduced directly:
  with the scoped app's window covered by a terminal, `click_element`'s
  position-fallback and `screenshot`'s crop both silently operated on the
  terminal instead, because a mouse click and a screen-region capture at a
  given (x, y) hit whichever window is actually topmost there — the AT-SPI
  tree has no bearing on it. Keyboard focus turned out to be independent of
  stacking order (a covered window can still hold input focus), which is
  why `type_into`'s keystroke fallback partially worked while the click and
  screenshot did not — an inconsistency that would have been very confusing
  to debug blind.
- Fixed via `_ensure_active()` in `linux_x11.py`: before every
  `_mouse_click`/`_key_event`/`_screenshot` call, resolve the scoped app's
  top-level window (match `_NET_WM_PID` against the AT-SPI pid across
  `_NET_CLIENT_LIST`) and raise + focus it with an EWMH `_NET_ACTIVE_WINDOW`
  client message if it isn't already active. No-ops cheaply once the window
  is already active (single property read), so it's safe to call on every
  keystroke during `type_into`'s char-by-char fallback.
- Depends on an EWMH-compliant window manager (xfwm4, mutter, KWin, most
  others all qualify). Without EWMH support `_ensure_active()` silently
  no-ops — input still works if the window already happens to be topmost.

**Linux — launching an app leaks stdio fds into a shell pipeline (CONFIRMED bug, fixed)**

- Confirmed on real hardware: `linux_common.py._launch`'s literal-executable
  fallback used a bare `subprocess.Popen([app_name])`, which inherits the
  parent's stdout/stderr. When gui-scope itself is run inside a shell
  pipeline (e.g. `gui-scope tree --app foo | head`) and `foo` isn't running
  yet, the newly-launched long-lived GUI app holds that pipe open for its
  entire lifetime — `uv run gui-scope` exits, but the pipe's write end never
  closes, so `head` (and any other downstream reader) blocks forever waiting
  for an EOF that never comes. Fixed by routing both the literal-executable
  and `launch_cmd` spawn paths through `_spawn_detached()`, which redirects
  stdin/stdout/stderr to `DEVNULL` and sets `start_new_session=True`.

**Linux — app launch (`launch_cmd`)**

- No `open -a` equivalent. `linux_common.py._launch` tries a matching
  `.desktop` entry first (via `Gio.AppInfo`), then falls back to treating
  `app_name` as a literal executable on `$PATH`. Pass `launch_cmd` (CLI:
  `--launch-cmd`) to override both when neither matches what should actually
  be run.

**`PostToolUse` hook — auto-refreshes state after actions (skill-scoped, not global)**

- `.claude/commands/gui-scope.md` and `.claude/commands/burp-suite-security-testing.md`
  each declare a `hooks: PostToolUse: [...]` block in their YAML frontmatter,
  pointing at `uv run gui-scope hook-post-tool-use`. Per Claude Code's
  "Configuration Levels" (Skill/Agent frontmatter → scoped to "while
  active"), this only fires while that skill is actually in use in the
  current session — **not** a global `~/.claude/settings.json` hook running
  on every Bash call in every project. It requires zero install-script
  changes: `setup.sh`'s existing `sed` templating (`uv run gui-scope` → `uv
  --project '$SCOPE_DIR' run gui-scope`) already rewrites the frontmatter's
  command line the same way it rewrites the rest of the file.
- `cli.py`'s `cmd_hook_post_tool_use` reads the hook-input JSON from stdin
  (not CLI flags), checks whether the just-completed Bash command was a
  `gui-scope click/type/key` call, and if so calls `dispatch("get_tree",
  {"flat": True})` **in-process** (no subprocess) for the target app,
  emitting the result as `additionalContext`. This directly replaces
  manually re-running `tree`/`shot` after every action to see what
  happened — a pattern that recurred constantly before this existed.
- Deliberately fails silent/exit-0 on anything unexpected (app already
  closed, wrong project, malformed input) — this runs alongside the real
  tool result on every matching Bash call, so it must never block, error,
  or visibly interfere with it.
- No new dependency: pure Python (`json`/`re`), reuses the existing
  `GUIScope`/`dispatch()` path — deliberately not a standalone bash+`jq`
  script (an earlier draft of this design), so it's exercised by the same
  code as everything else and needs no separate install step.

## Adding new tools

Add a method to the backend contract in `backends/base.py`, implement it in
**every** backend (`macos.py`, `linux_common.py`/`linux_wayland.py`/
`linux_x11.py`), then wire it into `dispatch()` and the `tools` property in
`gui_scope.py`. Keep the return contract: JSON string for text results, list
of content blocks for images.

## Python version

Requires 3.11+. Pin with `uv python pin 3.12` and run `uv sync`.
