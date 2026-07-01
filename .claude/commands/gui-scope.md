---
description: Drive any GUI application (macOS, or Linux/Wayland) via the gui-scope CLI — general-purpose, not tied to one app. Use for any task that needs to click, type, or read the UI of a desktop application.
argument-hint: '[task description, e.g. "open TextEdit and create a new document"]'
---

You are driving a GUI application via the `gui-scope` CLI in this project.
All tool calls must go through `uv run gui-scope` using the Bash tool. This
works the same way regardless of which application or OS you're targeting.

---

## Tool → CLI mapping

| What you want to do | Bash command |
|---|---|
| See current UI state | `uv run gui-scope tree  --app "APP_NAME" --depth 3` |
| Click a button or tab | `uv run gui-scope click --app "APP_NAME" --description "..."` |
| Click by role (avoid ambiguous matches) | `uv run gui-scope click --app "APP_NAME" --role ROLE --description "..."` |
| Type into a field | `uv run gui-scope type  --app "APP_NAME" --description "..." --text "..."` |
| Press a key | `uv run gui-scope key   --app "APP_NAME" return` |
| Take a screenshot | `uv run gui-scope shot  --app "APP_NAME"` |

All flags go **after** the subcommand name. Replace `APP_NAME` with whatever
application the user names — this skill isn't tied to any one app.
`shot` with no `--out` saves into `./.gui-scope/screenshots/` (pruned
automatically to the 20 most recent) — don't pass `--out` unless you
specifically need to keep one screenshot permanently at a fixed path.

---

## Step 1: figure out the right `--app` value

- **macOS**: use the app's localized display name as shown in the menu bar
  (e.g. `"Safari"`, `"Xcode"`).
- **Linux (Wayland)**: AT-SPI registers apps under their **executable
  name**, not the friendly display name — e.g. `"gnome-text-editor"`, not
  `"Text Editor"`. If a name doesn't connect, check `ps aux | grep -i
  <app>` for the real process name. If the app still won't launch
  automatically, pass `--launch-cmd "actual command"` to override both the
  `.desktop`-entry and executable-name lookups.

Run `tree --depth 3` first — if it returns a populated tree, you've got the
right name and the app is reachable.

---

## Step 2: general navigation pattern

1. `tree --depth 3` (or up to `--depth 6` for more detail) to see current state.
2. If the target element is visible, click or type into it by `--description`
   (or `--title` if `--description` doesn't match — see below).
3. If it's not visible, navigate to the containing tab/panel/menu first, then
   retry.
4. If a pane looks empty or is canvas-rendered (common in editors, IDEs,
   games, and complex custom widgets), use `shot` to look at it visually and
   reason about what to click next.
5. After typing into a field, `key return` (or `tab`/`escape` as needed) to
   submit or move on — typing alone does not submit forms.

---

## `--description` vs `--title`

Different toolkits put labels in different places. There's no universal
rule — if one field returns `not_found`, try the other:

- **macOS**: Java/Swing apps put labels in `AXDescription`; most native
  Cocoa apps use `AXTitle`. Try `--description` first for cross-platform
  toolkit apps, `--title` for native ones.
- **Linux (AT-SPI)**: `--title` maps to `get_name()`, `--description` maps
  to `get_description()`. Confirmed working on native GTK apps with labels
  in `--description` (e.g. a button named "New Tab" had description "New
  Tab"). Behavior for other toolkits (Qt, Java/Swing) is unverified — try
  both.

---

## Known Linux (Wayland) limitations — read before troubleshooting

- **Screenshots are full-screen, not cropped to the app window.** AT-SPI
  doesn't reliably report a window's true on-screen position in this
  backend — `shot` returns the whole screen so you don't get a confidently
  wrong crop. Locate the target app visually in the image. **Once the app
  is open, ask the user to set it "Always on Top"** (most GNOME apps: right
  click the title bar, or check the window's own menu) — this keeps it
  visible and unoccluded in every full-screen capture instead of getting
  covered by whatever else is on screen (e.g. the terminal).
- **The click position-fallback (for elements with no working `Action`
  interface) is unreliable for the same reason.** In practice this rarely
  matters — most buttons expose a working `Action` and click correctly via
  that path.
- **First use of `click`/`type`/`key` in a session may show a GNOME "Allow
  input control?" dialog.** Check **"Remember this decision"** and approve
  it — later runs will skip the dialog. If it keeps reappearing, that
  checkbox likely wasn't checked.
- **Java/Swing apps need `java-atk-wrapper` to be reachable at all.**
  Without it, the app simply won't show up in `tree` regardless of the
  `--app` name used. This is a known, currently-hard-to-resolve gap on
  several distros (not packaged for EL10/current EPEL as of 2026-07).
- X11 sessions are not yet supported — Wayland only for now.

---

## Tips

- Buttons/tabs that silently fail via the standard click path are retried
  automatically via a position-based fallback — no special action needed
  from you, just be aware of the Linux caveat above.
- If several elements share the same `--description` text, pair it with
  `--role` to disambiguate (e.g. tabs are often a distinct role from
  regular buttons).
- Prefer `tree --depth 3` for quick orientation; go deeper only when you
  need to find a specific nested element.
- **Keep the target app visible on screen rather than minimized or fully
  hidden, on any OS.** The person running Claude Code often wants to watch
  the automation happen live — e.g. Claude Code running in one window while
  the GUI being driven is visible in another. Don't minimize the app or
  otherwise hide it "to keep things tidy" unless the user asks for that.

---

Now proceed with the task the user described: $ARGUMENTS
