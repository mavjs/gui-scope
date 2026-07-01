# cli.py — CLI entry point for gui_scope.py (installed as the `gui-scope` script)
#
# usage:
#   uv run gui-scope tree  --app "Burp Suite" [--depth 4]
#   uv run gui-scope click --app "Burp Suite" --description "Next"
#   uv run gui-scope type  --app "Burp Suite" --description "..." --text "hello"
#   uv run gui-scope shot  --app "Burp Suite" [--out FILE] [--keep N]
#
# --app and --no-launch go after the subcommand name.
# The app is launched automatically if not already running.
#
# `shot` with no --out writes into a project-scoped scratch directory
# (./.gui-scope/screenshots/, relative to the current working directory) with
# a timestamped filename, then prunes that directory down to the --keep most
# recent files (default 20) — screenshots accumulate across a session without
# growing unbounded. Passing --out explicitly opts out of pruning: that's an
# intentional destination the caller controls.

import argparse
import base64
import json
import sys
from datetime import datetime
from pathlib import Path

from gui_scope import GUIScope

DEFAULT_SCREENSHOT_KEEP = 20


def default_screenshot_dir() -> Path:
    d = Path.cwd() / ".gui-scope" / "screenshots"
    d.mkdir(parents=True, exist_ok=True)
    return d


def prune_screenshots(directory: Path, keep: int) -> None:
    shots = sorted(directory.glob("shot-*.png"), key=lambda p: p.stat().st_mtime, reverse=True)
    for stale in shots[keep:]:
        stale.unlink(missing_ok=True)


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

            if args.out:
                out = Path(args.out)
            else:
                stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
                out = default_screenshot_dir() / f"shot-{stamp}.png"

            out.write_bytes(png)
            print(f"saved {len(png):,} bytes → {out}")

            if not args.out:
                prune_screenshots(out.parent, args.keep)
            return

    sys.exit("error: no image block in screenshot result")


def build_parser() -> argparse.ArgumentParser:
    # Shared flags inherited by every subcommand.
    # Placing them here means they go *after* the subcommand name:
    #   uv run gui-scope tree --app "Burp Suite" --depth 3
    shared = argparse.ArgumentParser(add_help=False)
    shared.add_argument(
        "--app", default="Burp Suite", metavar="NAME",
        help=(
            "Application name (default: 'Burp Suite'). On macOS this is the "
            "localized display name. On Linux this is matched against the "
            "AT-SPI-registered app name, then a .desktop entry, then a literal "
            "executable on $PATH — use --launch-cmd if none of those match."
        ),
    )
    shared.add_argument(
        "--no-launch", action="store_true",
        help="Fail instead of launching the app if it is not already running",
    )
    shared.add_argument(
        "--timeout", type=int, default=30, metavar="SEC",
        help="Seconds to wait for the app to start (default: 30)",
    )
    shared.add_argument(
        "--launch-cmd", default=None, metavar="CMD",
        help="Linux only: explicit command to launch the app with, if --app doesn't match a .desktop entry or executable",
    )

    root = argparse.ArgumentParser(prog="gui-scope")
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
    p.add_argument(
        "--out", default=None, metavar="FILE",
        help=(
            "Output path. Default: a timestamped file under "
            "./.gui-scope/screenshots/ (pruned to --keep most recent). "
            "Passing --out explicitly disables pruning."
        ),
    )
    p.add_argument(
        "--keep", type=int, default=DEFAULT_SCREENSHOT_KEEP, metavar="N",
        help=f"How many screenshots to retain in the default scratch dir (default: {DEFAULT_SCREENSHOT_KEEP})",
    )

    return root


def main() -> None:
    args = build_parser().parse_args()

    try:
        scope = GUIScope(
            args.app,
            auto_launch=not args.no_launch,
            timeout=args.timeout,
            launch_cmd=args.launch_cmd,
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
