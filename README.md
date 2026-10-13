# claude-speaks

Reads Claude Code's replies aloud on WSL, using a Stop hook and the Windows built-in speech engine (SAPI).

- Removes markdown before speaking. Code blocks become "Code block omitted", tables are skipped, and links are read by their label.
- Speech runs in the background, and each new reply cuts off the one still playing.
- Long replies are cut short at about 600 characters.

## Install

    ./install.sh   # adds the Stop hook to ~/.claude/settings.json (backup saved), links bin/claude-speaks into ~/.local/bin

Restart Claude Code (or open `/hooks`) to pick up the hook.

## Use

    claude-speaks off|on      # mute or unmute
    claude-speaks stop        # cut off the current speech
    claude-speaks say "hi"    # test it

Env: `CLAUDE_SPEAKS_MAX_CHARS` (0 = no limit), `CLAUDE_SPEAKS_VOICE` (e.g. `Microsoft Zira Desktop`), `CLAUDE_SPEAKS_RATE` (-10..10).
