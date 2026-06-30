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

# Pre-install Python deps so the first tool call is instant
echo "▶ Syncing Python dependencies..."
uv --project "$SCOPE_DIR" sync --quiet

# Install the slash command, embedding the absolute install path so it works
# from any Claude Code working directory.
echo "▶ Installing Claude Code slash command..."
mkdir -p "$COMMANDS_DIR"
sed "s|uv run gui-scope|cd '$SCOPE_DIR' \&\& uv run gui-scope|g" \
  "$TEMPLATE" > "$OUT"

echo ""
echo "✅ Done."
echo ""
echo "⚠️  One manual step: grant Accessibility permission to your terminal app"
echo "   System Settings → Privacy & Security → Accessibility → add $(basename "$TERM_PROGRAM" 2>/dev/null || echo 'your terminal')"
echo "   (Toggle it off and back on if you already added it previously.)"
echo ""
echo "Then open Claude Code and type:"
echo "   /burp-suite-security-testing"
