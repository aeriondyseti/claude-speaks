#!/usr/bin/env bash
# Registers speak.py as a Stop hook in ~/.claude/settings.json and links the CLI.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
settings="$HOME/.claude/settings.json"
cmd="python3 $here/speak.py"

cp "$settings" "$settings.bak.claude-speaks"
jq --arg cmd "$cmd" '
  .hooks.Stop = ((.hooks.Stop // []) | map(select(.hooks | all(.command != $cmd))))
                + [{"hooks": [{"type": "command", "command": $cmd, "timeout": 10}]}]
' "$settings.bak.claude-speaks" > "$settings"

mkdir -p "$HOME/.local/bin"
ln -sf "$here/bin/claude-speaks" "$HOME/.local/bin/claude-speaks"
echo "Installed Stop hook: $cmd"
