I read your rules in `~/.claude/settings.json` (Kokoro profile, with `debug_log_text` on).
The daemon is up; `stop()` gets called. Startup takes ~3.7s, first audio in 0.3s.
Files: `~/dev/claude-speaks/daemon.py`, `$HOME/.config/claude-speaks/config.json`, and $HOME alone.
Plugin at `~/.claude/plugins/cache/aeriondyseti-plugins/speaks/0.3.2/`, so v0.3.2. Commit 77522be1a2b3c and 3cb8f78.
The RTX 5060 Ti has 8 GB of VRAM; 9–12 sentences keep p99 under 400 ms at -5 dB. Use x86 db cfg HTML TTY.
See src/components/App.tsx and README.md, MAX_CHARS too. 1,234,567 items, 2x faster, 45%.
- **Bold** item with [a link](https://x.y) and https://example.com/a
```
code
```
