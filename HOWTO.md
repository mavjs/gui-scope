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

# Screenshot
uv run gui-scope shot  --app "Burp Suite" --out /tmp/burp.png
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

## Troubleshooting

**`tree` returns empty nodes or raises `AttributeError`**
Accessibility permission is missing or stale. System Settings → Privacy &
Security → Accessibility → remove your terminal and re-add it.

**`click` returns `not_found` for every element**
You are using `--title`. Burp Suite is a Java/Swing app — labels live in
`AXDescription`, not `AXTitle`. Always use `--description`.

**`click` returns `action_failed`**
The element exists but the standard AX action was rejected. `gui_scope.py`
falls back to a Quartz position-based click automatically. If `action_failed`
persists, run `tree --depth 6` to confirm the element is currently on screen —
it may be hidden behind a dialog or off-screen pane.

**Screenshot is blank or shows the wrong window**
Bring Burp to the front first by clicking any element in it, then retake the
screenshot.

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
