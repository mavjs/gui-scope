---
description: Drive Burp Suite's GUI for authorised web application security testing via the gui-scope CLI — Burp-specific navigation patterns and Java/Swing quirks baked in.
argument-hint: '[task description, e.g. "start Burp, open the built-in browser, and navigate to https://target.example.com/"]'
hooks:
  PostToolUse:
    - matcher: "Bash"
      hooks:
        - type: command
          command: "uv run gui-scope hook-post-tool-use"
          timeout: 10
---

You are helping with **authorised web application security testing** using Burp Suite.
You have full control of the Burp Suite GUI via the `gui-scope` CLI in this project.
All tool calls must go through `uv run gui-scope` using the Bash tool.

---

## Tool → CLI mapping

| What you want to do | Bash command |
|---|---|
| See current UI state | `uv run gui-scope tree  --app "Burp Suite" --depth 3` |
| Click a button or tab | `uv run gui-scope click --app "Burp Suite" --description "..."` |
| Click a tab (AXRadioButton) | `uv run gui-scope click --app "Burp Suite" --role AXRadioButton --description "..."` |
| Type into a field | `uv run gui-scope type  --app "Burp Suite" --description "..." --text "..."` |
| Press a key | `uv run gui-scope key   --app "Burp Suite" return` |
| Take a screenshot | `uv run gui-scope shot  --app "Burp Suite"` |

All flags go **after** the subcommand name. `shot` saves into
`./.gui-scope/screenshots/` by default, pruned to the 20 most recent — no
need to pick an `--out` path yourself.
Use `--description` for every click and type — never `--title` (Burp is Java/Swing; labels are in AXDescription, not AXTitle).

Use `tree --flat --role ROLE --query TEXT` instead of a full `tree` dump to
find one specific element (e.g. a JTabbedPane tab, a Repeater button).
`click`/`type`/`key` calls also auto-inject a follow-up flat tree of Burp's
state as context once they complete (this skill's own `PostToolUse` hook) —
check that before manually re-running `tree` to see whether an action
worked.

The CLI/tool contract is identical on macOS and Linux (Wayland or X11) — the
same `--role`/`--title`/`--description` flags work regardless of OS. On Linux
the "always use description" rule below is unverified — fall back to
`--title` if `--description` keeps returning `not_found`.

**Linux note — Burp Suite is currently NOT usable on Linux.** Confirmed on
real hardware (CentOS Stream 10/GNOME/Wayland, 2026-07): a running Burp
Suite process never registers with AT-SPI at all, because Java's
accessibility bridge (`java-atk-wrapper`) isn't active. That package isn't
packaged for EL10/current EPEL, and even where available it must be
manually wired into the *specific* JRE an app uses — Burp bundles its own
private JRE, so this can't be fixed with a simple system package install.
Everything in this skill describing Burp's AX/AT-SPI tree therefore does
not currently apply on Linux — treat this skill as macOS-only until that's
resolved. The rest of GUIScope's Linux backend (AT-SPI tree walk, click,
type, press_key, screenshot) is confirmed working end-to-end against
native GTK apps — the blocker is Java accessibility support specifically,
not the backend.

---

## Starting Burp Suite

Run these in order. Wait for each to succeed before proceeding.

```bash
uv run gui-scope tree  --app "Burp Suite" --depth 3
uv run gui-scope click --app "Burp Suite" --description "Next"
uv run gui-scope click --app "Burp Suite" --description "Start Burp"
```

After "Start Burp" the main UI is ready.

---

## Critical rule: always use `--description`, never `--title`

Burp Suite is a Java/Swing app. The AX bridge exposes labels via `AXDescription`,
not `AXTitle`. Using `--title` will always return `not_found`.

---

## Opening the built-in browser

Try the direct path first:

```bash
uv run gui-scope click --app "Burp Suite" --description "Open browser"
```

If that returns `not_found`, navigate explicitly:

```bash
uv run gui-scope click --app "Burp Suite" --role AXRadioButton --description "Proxy"
uv run gui-scope click --app "Burp Suite" --role AXRadioButton --description "Intercept"
uv run gui-scope click --app "Burp Suite" --description "Open browser"
```

Always pair `--role AXRadioButton` with `--description` when clicking tabs to avoid
matching the same label text that appears elsewhere in the UI.

---

## Navigating to a URL in the browser

```bash
uv run gui-scope click --app "Burp Suite" --role AXTextField --description "Address and search bar"
uv run gui-scope type  --app "Burp Suite" --role AXTextField --description "Address and search bar" --text "https://target.example.com/"
uv run gui-scope key   --app "Burp Suite" return
```

---

## General navigation pattern

1. Run `tree --depth 3` to see the current state.
2. If the target element is visible, click it by description.
3. If not, navigate to the tab or panel that contains it first.
4. If the pane appears empty (canvas-rendered — common in scanner views), use `shot` to observe state visually.

---

## AX tree tips for Burp

- Tab labels are `AXRadioButton` inside an `AXTabGroup` — always specify both `--role` and `--description`.
- Input fields are `AXTextField` — use `type` with `--description` to target them.
- Buttons that silently ignore AXPress are handled automatically via a Quartz position-based click fallback — no special action needed from you.
- Scanner visualisations and some panels are canvas-rendered; they will not appear as AX nodes. Use `shot` to inspect them.

---

## Authorization reminder

Only test applications and systems you own or have **written authorisation** to test.
Never run active scans or send payloads against out-of-scope targets.
Treat any intercepted credentials or tokens according to the engagement's rules of engagement.

---

Now proceed with the task the user described: $ARGUMENTS
