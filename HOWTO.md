# HOWTO: gui-scope as a Claude Code skill

gui-scope gives Claude Code shell-level control over any macOS GUI application
via the Accessibility API. There is no server, no daemon, and no API key beyond
the one Claude Code already uses. Claude drives the app by running
`uv run gui-scope` shell commands through its built-in Bash tool.

---

## Fresh install (single command)

```bash
curl -fsSL https://raw.githubusercontent.com/YOUR_USER/gui-scope/main/install.sh | sh
```

That one command:
1. Installs **uv** if missing (uv manages Python 3.12 automatically — no separate Python install needed)
2. Clones this repo to `~/.local/share/gui-scope`
3. Pre-installs the Python dependencies (`atomacos`, `pyobjc`)
4. Drops the slash command into `~/.claude/commands/`

**Then one manual step** — this cannot be automated:

> **System Settings → Privacy & Security → Accessibility → add your terminal app**
>
> If the entry already exists, toggle it off and back on. The permission binds to
> a specific binary path and goes stale when you switch terminals or reinstall.

---

## If you already cloned the repo

```bash
cd gui-scope
bash setup.sh
```

`setup.sh` does steps 3–4 above (sync deps + install slash command) and prints
the Accessibility permission reminder.

---

## Using the skill in Claude Code

Open Claude Code in **any** directory and type:

```
/burp-suite-security-testing
```

Claude gets the full Burp Suite playbook injected as context. Then describe your task:

```
/burp-suite-security-testing Start Burp, open the built-in browser, and navigate to https://target.example.com/
```

Or activate the skill first, then give the task as a follow-up message:

```
/burp-suite-security-testing

Go to Proxy → HTTP history and show me the last five requests as a table.
```

---

## Example prompts for authorised security testing

Obtain **written authorisation** from the system owner before any of the following.

| Task | Prompt |
|---|---|
| Start Burp and confirm it's ready | `/burp-suite-security-testing` → "Start Burp Suite and take a screenshot when the main UI is up." |
| Open browser to target | "Open the built-in browser and navigate to `https://target.example.com/`." |
| Intercept a login request | "Enable Proxy intercept, open the browser, navigate to the login page, submit the form, then show me the intercepted POST request." |
| Check HTTP history | "Go to Proxy → HTTP history and summarise the last 10 requests." |
| Navigate to a specific Burp tool | "Go to the Repeater tab and show me what's there." |
| Observe a canvas-rendered view | "Take a screenshot of the current Scanner results." |
| Run a passive scan | "Navigate to the Target tab, right-click `https://target.example.com/` in the site map, and start a passive scan." |

---

## What Claude actually runs

Every action is a plain shell command. You can run any of them yourself to
verify or debug what Claude is doing:

```bash
# See the current UI state
uv run gui-scope tree  --app "Burp Suite" --depth 3

# Click a button (always use --description for Java/Swing apps)
uv run gui-scope click --app "Burp Suite" --description "Next"

# Click a tab (pair --role with --description to avoid ambiguity)
uv run gui-scope click --app "Burp Suite" --role AXRadioButton --description "Proxy"

# Type into a field
uv run gui-scope type  --app "Burp Suite" --description "Address and search bar" --text "https://example.com/"

# Press a key
uv run gui-scope key   --app "Burp Suite" return

# Screenshot — saved under ./.gui-scope/screenshots/shot-<timestamp>.png by
# default, pruned to the 20 most recent (--keep N to change, --out FILE for
# an explicit path instead, which disables pruning)
uv run gui-scope shot  --app "Burp Suite"
```

All flags go **after** the subcommand name. Run from the `gui-scope` directory
(or from anywhere after `setup.sh` has been run, since the slash command embeds
the absolute install path).

---

## Using with a different application

Replace `"Burp Suite"` with any macOS app name as shown in the menu bar:

```bash
uv run gui-scope tree --app "Finder" --depth 3
uv run gui-scope tree --app "Xcode"  --depth 3
```

Write a new `.claude/commands/<your-app>.md` following the same structure as
`burp-suite-security-testing.md`, substituting the app-specific navigation
patterns and known quirks. Re-run `setup.sh` to install it.

---

## Linux (Wayland) setup

Linux support currently targets **Wayland only** (e.g. GNOME/mutter, such as
CentOS Stream 10's default desktop). X11 is a planned follow-up and is not
yet implemented — `gui-scope` will raise a clear error if `XDG_SESSION_TYPE`
isn't `wayland`.

**Prerequisites:**
- `xdg-desktop-portal` and `xdg-desktop-portal-gnome` (or your compositor's
  portal backend) installed and running:
  ```bash
  systemctl --user status xdg-desktop-portal xdg-desktop-portal-gnome
  ```
- An **active, logged-in graphical session**. Portal calls are brokered
  through the desktop shell over D-Bus — this cannot work on a headless box
  with no logged-in session, unlike the macOS backend's one-time permission
  grant.
- AT-SPI accessible support for your target app. Confirmed: native GTK4 apps
  (e.g. gnome-text-editor) register with AT-SPI without needing the
  `toolkit-accessibility` gsetting enabled — that's *not* a hard requirement
  for GTK apps in practice, despite older guidance suggesting otherwise.
  **Java/Swing apps (e.g. Burp Suite) are a different story: confirmed
  currently unreachable via AT-SPI entirely**, because they need
  `java-atk-wrapper`, which as of 2026-07 is not packaged for EL10/current
  EPEL, and even where available needs manual per-JRE wiring (a real
  blocker if the target app bundles its own private JRE, as Burp Suite
  does). Check `busctl --user list | grep a11y` to confirm the AT-SPI bus
  itself is up.
- `PyGObject` (and its `pycairo` dependency) build from source via `uv`/pip,
  so they need system dev headers — `gcc`/`cmake` alone are **not** enough.
  `setup.sh` prints this same list before running `uv sync`, so it isn't a
  surprise failure. Target distros:

  **CentOS Stream 10 / Fedora / RHEL (dnf) — confirmed on real hardware:**
  ```bash
  sudo dnf install -y cairo-devel cairo-gobject-devel glib2-devel python3-devel
  ```
  (`girepository-2.0.pc` — what PyGObject's meson build actually looks for —
  ships inside `glib2-devel` on CentOS Stream 10/GLib 2.80+, not a separate
  `gobject-introspection-devel` package, which doesn't exist for EL10;
  `pkgconf-pkg-config` is typically already installed.)

  **Ubuntu LTS / Debian / Kali (apt) — best-effort, not yet verified on real
  hardware:**
  ```bash
  sudo apt install -y libcairo2-dev libgirepository-2.0-dev gobject-introspection \
    python3-dev pkg-config
  ```
  Older releases may not have split out `libgirepository-2.0-dev` yet — if
  `apt` reports it missing, try `libgirepository1.0-dev` instead (the
  pre-GObject-Introspection-1.80 package name). Kali is Debian-based, so the
  same guidance applies; confirm the exact package name with
  `apt-cache search girepository` if either fails.

  Plus the AT-SPI typelib at runtime (`gir1.2-atspi-2.0`, or your distro's
  equivalent — usually pulled in automatically alongside `at-spi2-core`).

**First-run consent dialog (CONFIRMED working):**
The first time gui-scope presses a key or clicks (via the mouse-position
fallback path), a GNOME "Allow input control?" dialog appears — **you must
check "Remember this decision"** in that dialog, then approve it. Confirmed
on real hardware: after doing that once, subsequent `press_key`/click calls
skip the dialog entirely via the cached token at
`~/.config/gui-scope/wayland_token`. If runs keep prompting, delete that
file and re-approve, making sure to check the remember box this time.

**Screenshot (confirmed, with a caveat):**
Uses a separate, stateless portal call (`interactive: false`) — confirmed
this suppresses the crop-picker dialog on GNOME. **However, `screenshot`
returns the full, uncropped screen, not just the target app's window** — on
real hardware, AT-SPI never reported the window's true on-screen position
(always `(0, 0)` regardless of where the window actually was), so cropping
to "the app's bounds" was confidently wrong rather than just imprecise.
Locate the target app visually in the returned image. **Tip:** once the
target app is open, set it to "Always on Top" (most GNOME apps: right-click
the title bar or check the window's own menu) so it stays visible and
unoccluded in every capture instead of being covered by other windows.

**Observing the automation live:**
On any OS, it's worth keeping the target app visible on screen rather than
minimized — that way you can watch the automation happen in real time
alongside Claude Code, instead of only seeing it after the fact via
`screenshot`. This is especially useful when running Claude Code in one
window while the driven GUI is visible in another.

**Screenshot storage and cleanup (all OSes):**
`shot` with no `--out` writes a timestamped PNG under
`./.gui-scope/screenshots/` (relative to the current working directory,
i.e. project-scoped, not a shared `/tmp` location), and prunes that
directory down to the `--keep` most recent files (default 20) each time —
screenshots taken across a session accumulate without growing unbounded.
Pass `--out FILE` for an explicit path when you want to keep one
permanently; that opts out of pruning entirely. `.gui-scope/` is
`.gitignore`d by default.

---

## Troubleshooting

**`tree` returns empty nodes or raises `AttributeError`** (macOS)
Accessibility permission is missing or stale. System Settings → Privacy &
Security → Accessibility → remove your terminal and re-add it.

**`click` returns `not_found` for every element**
You are using `--title`. Burp Suite is a Java/Swing app — on macOS, labels
live in `AXDescription`, not `AXTitle`. Always use `--description`. On
Linux, which AT-SPI field carries Burp's labels is unverified — if
`--description` keeps returning `not_found`, try `--title`.

**`click` returns `action_failed`**
The element exists but the standard action was rejected. On macOS,
`gui_scope.py` falls back to a Quartz position-based click automatically. On
Linux it falls back to an AT-SPI `Component`-extents-based click via the
portal — **this fallback is likely unreliable** since AT-SPI doesn't report
true absolute window position in the tested environment (see the position
limitation above); it's only confirmed working for elements with a working
`Action` interface, which don't need this fallback. If `action_failed`
persists, run `tree --depth 6` to confirm the element is currently on
screen — it may be hidden behind a dialog or off-screen pane.

**Screenshot is blank or shows the wrong window (macOS)**
Bring the app to the front first by clicking any element in it, then retake
the screenshot.

**Linux: screenshot shows the whole desktop, not just the target app**
Expected — confirmed on real hardware that AT-SPI never reports a window's
true on-screen position (always `(0, 0)`), so cropping to "the app's
bounds" was confidently wrong rather than just imprecise (it showed whatever
window actually occupied that screen region). `screenshot` now
intentionally returns the full, uncropped screen; locate the target app
visually in the image.

**Linux: `--app "Some Display Name"` never connects / times out**
AT-SPI's app name is the **process/executable name**, not the friendly
display name shown in menus — e.g. use `--app "gnome-text-editor"`, not
`--app "Text Editor"`. Check with `ps aux` or query
`Atspi.get_desktop(0)`'s children directly if unsure.

**Linux: `click` always returns `action_failed` even on obviously clickable buttons**
Fixed as of this backend's initial implementation — a bug required both
`Atspi.StateType.ENABLED` and `SENSITIVE`, but `ENABLED` is unreliably set
by GTK4 even on fully clickable widgets. `_click` now only gates on
`SENSITIVE`. If you still see this on a current checkout, the element
likely has neither a working `Action` interface nor real `Component`
geometry — run `tree` to confirm it's actually the element you expect.

**Linux: Java/Swing apps (e.g. Burp Suite) never show up in `tree`, or `--app` never connects**
Confirmed: without `java-atk-wrapper`, Java's Swing UI never registers with
AT-SPI at all — the app is invisible to `Atspi.get_desktop(0)` (the
`toolkit-accessibility` gsetting does not affect this either way — confirmed
not required for native GTK apps, and irrelevant to Java's own bridge). As
of 2026-07, `java-atk-wrapper` is **not packaged
for EL10/current EPEL**, and even where it exists, it requires manually
symlinking its jar/`.so` into the *specific* JRE you're using and editing
that JRE's `accessibility.properties` — a system package wouldn't
automatically apply to an app bundling its own private JRE (as Burp Suite
does). This is a currently-unresolved blocker for Burp specifically; native
GTK/Qt apps are unaffected.

**Linux: portal calls hang or time out**
No active graphical session, or `xdg-desktop-portal`/`xdg-desktop-portal-gnome`
isn't running. Check `systemctl --user status xdg-desktop-portal`.

**Linux: the "Allow input control?" dialog keeps reappearing on every run**
You (or whoever approved it) needs to check **"Remember this decision"** in
that dialog — confirmed this is required for the cached
`~/.config/gui-scope/wayland_token` to actually skip future prompts; without
checking it, GNOME re-prompts every time regardless of the `persist_mode`
we request in code.

**Linux: screenshot still shows a picker dialog**
Confirmed working (`interactive: false` suppresses it) on this project's
tested `xdg-desktop-portal-gnome` version — if you see one on yours, check
its version and any relevant upstream issues.

**Linux: clicks land at the wrong spot**
Possible coordinate-space mismatch between AT-SPI's reported extents and the
portal's pointer-motion space (e.g. under HiDPI scaling or multi-monitor
setups) — unverified so far (testing to date has been on a single
non-scaled display); see AGENT.md's Linux gotchas.

**`uv: command not found`**
Re-run the install:
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh && source ~/.local/bin/env
```

---

## Authorization and responsible use

- Obtain **written authorisation** before testing any application or system.
- Limit scope to agreed targets, ports, and testing windows.
- Never run active scans or send payloads to out-of-scope targets.
- Treat intercepted credentials, tokens, and request data according to your
  engagement's rules of engagement and applicable law.
