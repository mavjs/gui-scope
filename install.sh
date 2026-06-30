#!/usr/bin/env bash
# install.sh — one-command setup for gui-scope on a fresh macOS machine
#
# curl -fsSL https://raw.githubusercontent.com/YOUR_USER/gui-scope/main/install.sh | sh
#
# What it does:
#   1. Installs uv (if missing) — handles Python 3.12 automatically
#   2. Clones the repo to ~/.local/share/gui-scope
#   3. Pre-installs Python dependencies (atomacos, pyobjc)
#   4. Installs the Claude Code slash command to ~/.claude/commands/
#   5. Prints the Accessibility permission step (cannot be automated)
set -euo pipefail

REPO_URL="https://github.com/YOUR_USER/gui-scope"   # ← update before publishing
INSTALL_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/gui-scope"

# ── 1. uv ────────────────────────────────────────────────────────────────────
if ! command -v uv &>/dev/null; then
  echo "▶ Installing uv..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  # Source the env update written by the uv installer
  # shellcheck disable=SC1091
  source "${HOME}/.local/bin/env" 2>/dev/null \
    || export PATH="${HOME}/.local/bin:$PATH"
fi
echo "✓ uv $(uv --version)"

# ── 2. Clone or update ───────────────────────────────────────────────────────
if [[ -d "$INSTALL_DIR/.git" ]]; then
  echo "▶ Updating gui-scope..."
  git -C "$INSTALL_DIR" pull --ff-only --quiet
else
  echo "▶ Cloning gui-scope to $INSTALL_DIR..."
  git clone --depth 1 "$REPO_URL" "$INSTALL_DIR"
fi

# ── 3 + 4. Delegate to setup.sh inside the cloned repo ───────────────────────
bash "$INSTALL_DIR/setup.sh"
