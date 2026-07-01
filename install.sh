#!/usr/bin/env bash
# install.sh — one-command setup for gui-scope on a fresh machine (macOS,
# or Linux/Wayland — see AGENT.md/HOWTO.md for X11's current status)
#
# curl -fsSL https://raw.githubusercontent.com/YOUR_USER/gui-scope/main/install.sh | sh
#
# What it does:
#   1. Installs uv (if missing) — handles Python 3.12 automatically
#   2. Clones the repo to ~/.local/share/gui-scope
#   3. Pre-installs platform-specific Python dependencies (see pyproject.toml)
#   4. Installs the Claude Code slash command to ~/.claude/commands/
#   5. Prints the platform-specific permission/setup step (cannot be automated)
set -euo pipefail

REPO_URL="https://github.com/mavjs/gui-scope"   # ← update before publishing
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

if [[ "$(uname -s)" == "Linux" ]]; then
  echo "▶ Linux prerequisites (not installable by this script — install via your package manager):"
  echo "   - xdg-desktop-portal + xdg-desktop-portal-gnome (Wayland only; X11 not yet supported)"
  echo "   - PyGObject/pycairo build headers, e.g. on dnf-based distros (CentOS Stream/Fedora/RHEL):"
  echo "       sudo dnf install -y cairo-devel cairo-gobject-devel glib2-devel python3-devel"
  echo "     (girepository-2.0.pc ships inside glib2-devel on GLib 2.80+, no separate"
  echo "     gobject-introspection-devel package needed)"
  echo "     or on apt-based distros:"
  echo "       sudo apt install -y libcairo2-dev libgirepository-2.0-dev gobject-introspection \\"
  echo "         python3-dev pkg-config"
  echo "   - gir1.2-atspi-2.0 (or distro equivalent, usually pulled in with at-spi2-core)"
  echo "   - java-atk-wrapper (only needed for Java/Swing apps like Burp Suite)"
fi

# ── 3 + 4. Delegate to setup.sh inside the cloned repo ───────────────────────
bash "$INSTALL_DIR/setup.sh"
