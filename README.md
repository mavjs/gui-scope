# gui-scope

> [!WARNING]
> This is a AI created application to show case how using the operating system's Accessibility API can allow us to create a tool call without using an mcp server.
> Testing so far has been minimal: Burp Suite on macOS, a native GTK app (gnome-text-editor) on Linux/Wayland, and a native GTK app (mousepad) on Linux/X11. Several things are confirmed working end-to-end, but treat this as early and narrowly verified rather than production-ready — see AGENT.md/HOWTO.md for the specific confirmed-vs-open-question findings.

Process-scoped GUI automation via the OS accessibility API. Gives Claude Code
read/write access to a single application — no shell escape, no other windows.

This started as a narrow experiment in authorised web application security
testing with Burp Suite, but the underlying mechanism (walk the OS
accessibility tree, click/type/screenshot through it) isn't Burp-specific at
all — it works with any application. It's since grown into a general-purpose
GUI automation tool, with the Burp-specific playbook kept as one example of
an app-specific skill built on top of the same generic CLI. macOS is fully
supported; Linux supports both Wayland (GNOME/mutter, via xdg-desktop-portal)
and X11 (XFCE/xfwm4 and others, via XTEST) — session type is auto-detected.

---

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/YOUR_USER/gui-scope/main/install.sh | sh
```

Then one manual step — this cannot be scripted:

> **System Settings → Privacy & Security → Accessibility → add your terminal app**

If you already cloned the repo:

```bash
bash setup.sh
```

---

## Usage

Open Claude Code in any directory and type:

```
/gui-scope
```

Then describe your task, naming whatever application you want to drive:

```
/gui-scope Open TextEdit, create a new document, and type "hello world"
```

For Burp Suite specifically, there's also a dedicated skill with Burp's
known navigation patterns and quirks baked in:

```
/burp-suite-security-testing Start Burp, open the built-in browser, and navigate to https://target.example.com/
```

Claude reads the injected skill context and drives the target application by
running `uv run gui-scope` shell commands through its built-in Bash tool. No
daemon, no server, no extra API key.

---

## CLI (standalone / debugging)

```bash
uv run gui-scope tree  --app "Burp Suite" --depth 3   # read the AX tree
uv run gui-scope click --app "Burp Suite" --description "Next"
uv run gui-scope type  --app "Burp Suite" --description "Search" --text "hello"
uv run gui-scope key   --app "Burp Suite" return
uv run gui-scope shot  --app "Burp Suite"             # saved under ./.gui-scope/screenshots/
```

Works with any app — replace `"Burp Suite"` with any name shown in the menu bar.
`shot` writes a timestamped PNG under `./.gui-scope/screenshots/` by default,
pruned to the 20 most recent (`--keep N` to change that); pass `--out FILE`
for an explicit path instead, which disables pruning.

---

## How it works

```
/gui-scope (or /burp-suite-security-testing)  →  .claude/commands/<name>.md
                                  (skill context injected into Claude's prompt)
                                          │
                                          ▼
                               Claude runs Bash commands:
                               uv run gui-scope tree --app "SOME_APP" ...
                                          │
                                          ▼
                               gui-scope → gui_scope.py → backend → app
                                                              │
                                              ┌───────────────┴───────────────┐
                                              ▼                               ▼
                                     macOS: atomacos/Quartz        Linux: AT-SPI2 (gi.Atspi)
                                                          + xdg-desktop-portal (Wayland) or XTEST/Xlib (X11)
```

`gui_scope.py` is a thin facade over a per-OS backend (`backends/`). On
macOS, `backends/macos.py` finds the target process by PID and dispatches
actions via the Accessibility API with a Quartz fallback for Java/Swing
buttons that ignore `AXPress`. On Linux, `backends/linux_common.py` walks
the AT-SPI2 tree over D-Bus; `backends/linux_wayland.py` synthesizes
input/screenshots via `xdg-desktop-portal`'s RemoteDesktop and Screenshot
interfaces, and `backends/linux_x11.py` does the same directly against the X
server via the XTEST extension.

---

## Requirements

- **macOS** — Accessibility permission granted to your terminal; or
- **Linux (Wayland or X11)** — targeting CentOS Stream 10, Ubuntu LTS, and
  Debian-based distros (Kali included). Both need AT-SPI enabled
  (`java-atk-wrapper` for Java/Swing apps like Burp Suite — currently
  unreachable via AT-SPI regardless, see `HOWTO.md`) and system dev headers
  for `PyGObject`/`pycairo` to build (`setup.sh` prints the exact packages
  per distro). Wayland additionally needs an active, logged-in graphical
  session with `xdg-desktop-portal` + `xdg-desktop-portal-gnome` running,
  and cannot run headless; X11 additionally needs `python3-xlib` (installed
  automatically) and an EWMH-compliant window manager. See
  [`HOWTO.md`](HOWTO.md) for full setup steps.
- [uv](https://docs.astral.sh/uv/) — manages Python 3.12 and all deps automatically
- [Claude Code](https://claude.ai/code)
- Target application installed

---

## Extending to other applications

For most apps, [`/gui-scope`](.claude/commands/gui-scope.md) is all you
need — it's app-agnostic and covers the general navigation pattern plus the
platform-specific gotchas (macOS `AXTitle`/`AXDescription`, Linux AT-SPI
app-name matching, the Wayland screenshot/click-precision caveats).

If an application has enough of its own quirks to be worth documenting
separately (as Burp Suite's Java/Swing UI did), write a new
`.claude/commands/<your-app>.md` following the structure of
[`burp-suite-security-testing.md`](.claude/commands/burp-suite-security-testing.md),
add it to `COMMAND_NAMES` in `setup.sh`, and re-run `bash setup.sh` to
install it. See [`HOWTO.md`](HOWTO.md) for the full setup guide.

---

## Authorization and responsible use

Only test applications and systems you own or have written authorisation to test.
Never run active scans or send payloads against out-of-scope targets.
