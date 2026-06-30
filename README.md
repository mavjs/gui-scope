# gui-scope

Process-scoped macOS GUI automation via the Accessibility API. Gives Claude Code
read/write access to a single application — no shell escape, no other windows.

Designed for authorised web application security testing with Burp Suite, but
works with any macOS application.

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
                               gui-scope → gui_scope.py → macOS AX API → app
```

`gui_scope.py` is a pure Python shim over `atomacos` and `pyobjc`. It finds the
target process by PID, traverses the accessibility tree, and dispatches actions
(click, type, key press, screenshot) using the AX API with a Quartz fallback
for Java/Swing buttons that ignore `AXPress`.

---

## Requirements

- macOS (Accessibility API is macOS-only)
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
