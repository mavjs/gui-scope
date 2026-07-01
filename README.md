# gui-scope

> [!WARNING]
> This is a AI created application to show case how using the operating system's Accessibility API can allow us to create a tool call without using an mcp server.
> This is only tested with a very minimal use of Burp Suite - a web application security assessment and penetration testing tool.

Process-scoped GUI automation via the OS accessibility API. Gives Claude Code
read/write access to a single application — no shell escape, no other windows.

Designed for authorised web application security testing with Burp Suite, but should
work with any application. macOS is fully supported; Linux support targets
Wayland first (GNOME/mutter, via xdg-desktop-portal) — X11 is a planned
follow-up, not yet implemented.

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
/burp-suite-security-testing
```

Then describe your task:

```
/burp-suite-security-testing Start Burp, open the built-in browser, and navigate to https://target.example.com/
```

Claude reads the injected skill context and drives Burp Suite by running
`uv run gui-scope` shell commands through its built-in Bash tool. No daemon,
no server, no extra API key.

---

## CLI (standalone / debugging)

```bash
uv run gui-scope tree  --app "Burp Suite" --depth 3   # read the AX tree
uv run gui-scope click --app "Burp Suite" --description "Next"
uv run gui-scope type  --app "Burp Suite" --description "Search" --text "hello"
uv run gui-scope key   --app "Burp Suite" return
uv run gui-scope shot  --app "Burp Suite" --out /tmp/burp.png
```

Works with any app — replace `"Burp Suite"` with any name shown in the menu bar.

---

## How it works

```
/burp-suite-security-testing  →  .claude/commands/burp-suite-security-testing.md
                                  (skill context injected into Claude's prompt)
                                          │
                                          ▼
                               Claude runs Bash commands:
                               uv run gui-scope tree --app "Burp Suite" ...
                                          │
                                          ▼
                               gui-scope → gui_scope.py → backend → app
                                                              │
                                              ┌───────────────┴───────────────┐
                                              ▼                               ▼
                                     macOS: atomacos/Quartz        Linux: AT-SPI2 (gi.Atspi)
                                                                    + xdg-desktop-portal (Wayland)
```

`gui_scope.py` is a thin facade over a per-OS backend (`backends/`). On
macOS, `backends/macos.py` finds the target process by PID and dispatches
actions via the Accessibility API with a Quartz fallback for Java/Swing
buttons that ignore `AXPress`. On Linux, `backends/linux_common.py` walks
the AT-SPI2 tree over D-Bus, and `backends/linux_wayland.py` synthesizes
input/screenshots via `xdg-desktop-portal`'s RemoteDesktop and Screenshot
interfaces (X11 support is planned but not yet implemented).

---

## Requirements

- **macOS** — Accessibility permission granted to your terminal; or
- **Linux (Wayland only, e.g. GNOME/mutter)** — targeting CentOS Stream 10,
  Ubuntu LTS, and Debian-based distros (Kali included); X11 is not yet
  supported. Needs an active, logged-in graphical session with
  `xdg-desktop-portal` + `xdg-desktop-portal-gnome` running, AT-SPI enabled
  (`java-atk-wrapper` for Java/Swing apps like Burp Suite — currently
  unreachable via AT-SPI regardless, see `HOWTO.md`), and system dev headers
  for `PyGObject`/`pycairo` to build (`setup.sh` prints the exact packages
  per distro). This backend cannot run headless — portals require a live
  desktop session. See [`HOWTO.md`](HOWTO.md) for full setup steps.
- [uv](https://docs.astral.sh/uv/) — manages Python 3.12 and all deps automatically
- [Claude Code](https://claude.ai/code)
- Target application installed

---

## Extending to other applications

Write a new `.claude/commands/<your-app>.md` following the structure of
[`burp-suite-security-testing.md`](.claude/commands/burp-suite-security-testing.md),
substituting the app-specific navigation patterns. Run `bash setup.sh` to
install it. See [`SKILL.md`](SKILL.md) for the Burp-specific reference and
[`HOWTO.md`](HOWTO.md) for the full setup guide.

---

## Authorization and responsible use

Only test applications and systems you own or have written authorisation to test.
Never run active scans or send payloads against out-of-scope targets.
