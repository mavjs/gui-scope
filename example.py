#!/usr/bin/env python3
# example.py — exercise gui_scope.py from the command line
#
# usage:
#   uv run example.py tree  --app "Burp Suite" [--depth 4]
#   uv run example.py click --app "Burp Suite" --title "Send"
#   uv run example.py type  --app "Burp Suite" --title "..." --text "hello"
#   uv run example.py shot  --app "Burp Suite" [--out screenshot.png]
#
# --app and --no-launch go after the subcommand name.
# The app is launched automatically if not already running.

import argparse
import base64
import json
import sys
from pathlib import Path

from gui_scope import GUIScope


def cmd_tree(scope: GUIScope, args: argparse.Namespace) -> None:
    result = scope.dispatch("get_tree", {"max_depth": args.depth})
    print(result)


def cmd_click(scope: GUIScope, args: argparse.Namespace) -> None:
    inputs = {}
    if args.title:       inputs["title"]       = args.title
    if args.role:        inputs["role"]        = args.role
    if args.description: inputs["description"] = args.description

    if not inputs:
        sys.exit("error: provide at least one of --title, --role, --description")

    result = json.loads(scope.dispatch("click_element", inputs))
    if result.get("ok"):
        print("ok")
    else:
        print(result.get("result", "failed"))


def cmd_type(scope: GUIScope, args: argparse.Namespace) -> None:
    inputs = {"text": args.text}
    if args.title:       inputs["title"]       = args.title
    if args.role:        inputs["role"]        = args.role
    if args.description: inputs["description"] = args.description

    result = json.loads(scope.dispatch("type_into", inputs))
    print("ok" if result.get("ok") else "element not found")


def cmd_key(scope: GUIScope, args: argparse.Namespace) -> None:
    result = json.loads(scope.dispatch("press_key", {"key": args.key}))
    print("ok" if result.get("ok") else "failed")


def cmd_shot(scope: GUIScope, args: argparse.Namespace) -> None:
    blocks = scope.dispatch("screenshot", {})
    if not isinstance(blocks, list):
        sys.exit("error: screenshot returned unexpected result")

    for block in blocks:
        if block.get("type") == "image":
            png = base64.standard_b64decode(block["source"]["data"])
            out = Path(args.out)
            out.write_bytes(png)
            print(f"saved {len(png):,} bytes → {out}")
            return

    sys.exit("error: no image block in screenshot result")


def build_parser() -> argparse.ArgumentParser:
    # Shared flags inherited by every subcommand.
    # Placing them here means they go *after* the subcommand name:
    #   uv run example.py tree --app "Burp Suite" --depth 3
    shared = argparse.ArgumentParser(add_help=False)
    shared.add_argument(
        "--app", default="Burp Suite", metavar="NAME",
        help="Localized application name (default: 'Burp Suite')",
    )
    shared.add_argument(
        "--no-launch", action="store_true",
        help="Fail instead of launching the app if it is not already running",
    )
    shared.add_argument(
        "--timeout", type=int, default=30, metavar="SEC",
        help="Seconds to wait for the app to start (default: 30)",
    )

    root = argparse.ArgumentParser(prog="example")
    sub = root.add_subparsers(dest="cmd", required=True)

    # tree
    p = sub.add_parser("tree", parents=[shared], help="Print the accessibility tree as JSON")
    p.add_argument("--depth", type=int, default=6, help="Max depth (default: 6)")

    # click
    p = sub.add_parser("click", parents=[shared], help="Click a UI element")
    p.add_argument("--title",       default=None)
    p.add_argument("--role",        default=None)
    p.add_argument("--description", default=None)

    # type
    p = sub.add_parser("type", parents=[shared], help="Type text into a UI element")
    p.add_argument("--text",        required=True)
    p.add_argument("--title",       default=None)
    p.add_argument("--role",        default=None)
    p.add_argument("--description", default=None)

    # key
    p = sub.add_parser("key", parents=[shared], help="Press a keyboard key")
    p.add_argument("key", help="Key name: return, tab, escape, space, delete, up, down, left, right")

    # shot
    p = sub.add_parser("shot", parents=[shared], help="Take a screenshot of the application window")
    p.add_argument("--out", default="screenshot.png", metavar="FILE")

    return root


def main() -> None:
    args = build_parser().parse_args()

    try:
        scope = GUIScope(
            args.app,
            auto_launch=not args.no_launch,
            timeout=args.timeout,
        )
    except RuntimeError as e:
        sys.exit(f"error: {e}")

    dispatch = {
        "tree":  cmd_tree,
        "click": cmd_click,
        "type":  cmd_type,
        "key":   cmd_key,
        "shot":  cmd_shot,
    }
    dispatch[args.cmd](scope, args)


if __name__ == "__main__":
    main()
