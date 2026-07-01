# backends/wayland_token.py — cache the RemoteDesktop portal's restore_token
# so gui-scope only needs the one-time GNOME consent dialog on first run.

import os
from pathlib import Path

_TOKEN_PATH = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "gui-scope" / "wayland_token"


def load_token() -> str | None:
    try:
        return _TOKEN_PATH.read_text().strip() or None
    except FileNotFoundError:
        return None


def save_token(token: str) -> None:
    if not token:
        return
    _TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    _TOKEN_PATH.write_text(token)
    _TOKEN_PATH.chmod(0o600)
