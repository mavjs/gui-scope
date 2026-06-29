# GUIScope — Burp Suite Skill

Inject this document into your context when using GUIScope to drive Burp Suite.

---

## Setup: starting Burp Suite

Run these in order. Wait for each to succeed before proceeding.

```
get_tree          max_depth=3        # connect + confirm Burp is up
click_element     description="Next"
click_element     description="Start Burp"
```

After "Start Burp" the main UI is ready.

---

## Critical rule: always use `description`, never `title`

Burp Suite is a Java/Swing app. The AX bridge exposes labels via `AXDescription`,
not `AXTitle`. Every `click_element` and `type_into` call must use the
`description` field. Using `title` will always return `not_found`.

---

## Opening the built-in browser

Try the direct path first — "Open browser" is visible on the Proxy/Intercept
pane and sometimes survives tab switches:

```
click_element     description="Open browser"
```

If that returns `not_found`, navigate explicitly:

```
click_element     role="AXRadioButton"  description="Proxy"       # main tab
click_element     role="AXRadioButton"  description="Intercept"   # sub-tab
click_element     description="Open browser"
```

Burp's top-level tabs live inside an `AXTabGroup`; their AX role is
`AXRadioButton`. Always pair `role="AXRadioButton"` with the tab description
to avoid ambiguity — several elements share the same description text across
different parts of the UI.

---

## General navigation pattern

1. Call `get_tree max_depth=3` to see the current state.
2. If the target element is visible in the tree, click it directly by description.
3. If not, find the tab or panel that contains it and navigate there first.
4. If the AX tree shows a canvas or an empty pane with no children, use
   `screenshot` to observe state, then derive coordinates if needed.

---

## AX tree tips for Burp

- Tab labels are `AXRadioButton` inside an `AXTabGroup`. Always specify both
  `role="AXRadioButton"` and `description` when clicking a tab — description
  alone is ambiguous because the same string appears elsewhere in the UI.
- Input fields are `AXTextField`; use `type_into description="..."` to target them.
- Buttons that silently ignore `AXPress` (common in Swing) are automatically
  handled by GUIScope via a Quartz position-based fallback — no special action needed.
- Scanner visualisations and some panels are canvas-rendered and will not appear
  as AX nodes; use `screenshot` to inspect them.

---

## Tool quick-reference

| Goal | Tool | Key field |
|---|---|---|
| See current UI state | `get_tree` | `max_depth` (3 for overview, 6 for detail) |
| Click a button or tab | `click_element` | `description` |
| Type into a field | `type_into` | `description` + `text` |
| Submit / confirm input | `press_key` | `key` = `return` |
| Navigate between fields | `press_key` | `key` = `tab` |
| Dismiss a dialog | `press_key` | `key` = `escape` |
| Observe canvas / visual state | `screenshot` | — |

## Navigating to a URL in the built-in browser

Typing a URL does not navigate until Enter is pressed:

```
click_element   role="AXTextField"  description="Address and search bar"
type_into       role="AXTextField"  description="Address and search bar"  text="https://example.com"
press_key       key="return"
```
