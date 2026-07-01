#!/usr/bin/env bash
# setup.sh — install the gui-scope Claude Code slash command
#
# Run once from inside this repo after cloning:
#   cd gui-scope && bash setup.sh
#
# Re-run any time you update the repo to refresh the slash command.
set -euo pipefail

SCOPE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMMANDS_DIR="${HOME}/.claude/commands"
TEMPLATE="$SCOPE_DIR/.claude/commands/burp-suite-security-testing.md"
OUT="$COMMANDS_DIR/burp-suite-security-testing.md"

# Verify uv is available
if ! command -v uv &>/dev/null; then
  echo "uv not found. Install it first:"
  echo "  curl -LsSf https://astral.sh/uv/install.sh | sh"
  exit 1
fi

# On Linux, PyGObject/pycairo build from source and need system dev headers —
# `uv sync` below will fail with an opaque meson/cairo error without them.
# Print this *before* attempting sync so the failure mode is never a surprise.
if [[ "$(uname -s)" == "Linux" ]]; then
  echo "▶ Linux build prerequisites for PyGObject/pycairo (gcc/cmake alone are NOT enough):"
  echo "   Confirmed on CentOS Stream 10 / Fedora / RHEL (dnf):"
  echo "     sudo dnf install -y cairo-devel cairo-gobject-devel glib2-devel python3-devel"
  echo "   Best-effort, not yet verified on real hardware, for Ubuntu LTS / Debian / Kali (apt):"
  echo "     sudo apt install -y libcairo2-dev libgirepository-2.0-dev gobject-introspection \\"
  echo "       python3-dev pkg-config"
  echo "     (older releases may not have libgirepository-2.0-dev yet — if apt reports it"
  echo "     missing, try libgirepository1.0-dev instead)"
  echo "   Plus gir1.2-atspi-2.0 (or distro equivalent — usually pulled in with at-spi2-core)"
  echo ""
fi

# Pre-install Python deps so the first tool call is instant
echo "▶ Syncing Python dependencies..."
uv --project "$SCOPE_DIR" sync --quiet

# Install the slash command, embedding the absolute install path via
# `uv --project` so it works from any Claude Code working directory.
echo "▶ Installing Claude Code slash command..."
mkdir -p "$COMMANDS_DIR"
sed "s|uv run gui-scope|uv --project '$SCOPE_DIR' run gui-scope|g" \
  "$TEMPLATE" > "$OUT"

echo ""
echo "✅ Done."
echo ""

if [[ "$(uname -s)" == "Darwin" ]]; then
  echo "⚠️  One manual step: grant Accessibility permission to your terminal app"
  echo "   System Settings → Privacy & Security → Accessibility → add $(basename "$TERM_PROGRAM" 2>/dev/null || echo 'your terminal')"
  echo "   (Toggle it off and back on if you already added it previously.)"
elif [[ "$(uname -s)" == "Linux" ]]; then
  echo "⚠️  Linux (Wayland only — X11 is not yet supported):"
  echo "   - Requires an active, logged-in graphical session with"
  echo "     xdg-desktop-portal + xdg-desktop-portal-gnome running."
  echo "   - The first click/key action will show a GNOME 'Allow input"
  echo "     control?' dialog — approve it once. The session is then cached"
  echo "     at ~/.config/gui-scope/wayland_token."
  echo "   - For Java/Swing apps (e.g. Burp Suite): install java-atk-wrapper"
  echo "     and ensure AT-SPI accessibility is enabled."
  echo "   See HOWTO.md's 'Linux (Wayland) setup' section for details."
fi

echo ""
echo "Then open Claude Code and type:"
echo "   /burp-suite-security-testing"
