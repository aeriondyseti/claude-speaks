# claude-speaks

Reads Claude Code's replies aloud on WSL, using a Stop hook.

`speak.py` (the hook) cleans the reply up for speech and passes it to `daemon.py`, a background process started on demand. The daemon tries these in order:

1. **A GPU TTS server.** Any OpenAI-style `/v1/audio/speech` endpoint set in `~/.config/claude-speaks/config.json` (see `config.example.json`). It accepts raw PCM or vLLM-Omni's SSE stream.
2. **Pocket TTS on the CPU.** Used when no server is set up or reachable. The model is loaded once and stays in memory.
3. **Windows SAPI.** Only with `CLAUDE_SPEAKS_ENGINE=sapi`.

- Removes markdown before speaking. Code blocks become "Code block omitted", tables are skipped, and links are read by their label.
- Each new reply cuts off the one still playing. Long replies are cut short at about 600 characters.

## Install

    uv sync        # pocket-tts with CPU-only torch (~1 GB)
    ./install.sh   # adds the Stop hook to ~/.claude/settings.json (backup saved), links bin/claude-speaks into ~/.local/bin

## Use

    claude-speaks off|on      # mute or unmute
    claude-speaks stop        # cut off the current speech
    claude-speaks say "hi"    # test it
    claude-speaks shutdown    # unload the daemon (it restarts on the next reply)

Env: `CLAUDE_SPEAKS_MAX_CHARS` (0 = no limit), `CLAUDE_SPEAKS_POCKET_VOICE` (default `alba`).
Config is re-read on every reply, so you can switch servers or voices without restarting anything.

## GPU server: Voxtral 4B (manual trial)

`deploy/voxtral/compose.yaml` runs Mistral's Voxtral-4B-TTS in vLLM-Omni on the RTX 5060 Ti, at `127.0.0.1:18090`.

    hf download mistralai/Voxtral-4B-TTS-2603
    docker compose -f deploy/voxtral/compose.yaml up -d    # ~4 min to load; the first request is slow while the GPU warms up

Measured on the 5060 Ti:
- Uses ~11.4 GB of VRAM.
- First audio arrives in ~0.4 s once warm.
- Generates speech about 1.7x faster than real time.

English voices: `casual_female`, `casual_male`, `cheerful_female`, `neutral_female`, `neutral_male`.

Gotchas on WSL:
- The container sees every GPU no matter what `device_ids` says, so the card is pinned with `CUDA_VISIBLE_DEVICES=<uuid>`.
- Offline repo-ID lookup fails for Mistral-format models, so the model is given as its local snapshot path.

Not managed by Quartermaster yet: that needs its Docker lifecycle and container GPU mapping (Milestones 9.2/9.5).
