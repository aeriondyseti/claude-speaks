# speaks

A Claude Code plugin that reads Claude's replies aloud using [Pocket TTS](https://github.com/kyutai-labs/pocket-tts), a small text-to-speech model that runs locally on the CPU. Speech starts about 0.1 s after a reply finishes.

Before speaking, it rewrites the reply so it sounds natural:

| Written | Spoken |
|---|---|
| `~/.config/app/config.json` | home slash dot config slash app slash config dot jay sohn |
| `b81be46c3777f8…cb970` | hash ending with bee nine seven zero |
| `1.5×`, `0.12 s`, `~11.4 GB`, `9–12` | one point five times, zero point one two seconds, about eleven point four gigabytes, nine to twelve |
| `RTX 5060 Ti`, `p99`, `v1.0`, `2.14.1` | ar tee ex fifty sixty tee eye, pee ninety nine, vee one point zero, two point fourteen point one |
| `volume_db`, `db`, `TTY` | volume underscore dee bee, dee bee, tee tee why |

Code blocks and tables are skipped, links are read by their label, and long replies are cut off at about 600 characters.

## Install

Requirements:
- Linux or WSL2 with PulseAudio `paplay` (WSLg provides it)
- `python3`
- [`uv`](https://docs.astral.sh/uv/)

Then run:

    /plugin install speaks --marketplace aeriondyseti/aeriondyseti-plugins

On the first session start, the plugin installs Pocket TTS with CPU-only PyTorch (~1 GB, into `~/.local/share/claude-speaks/venv`) in the background, then preloads the model. After that, each session's warm-up takes a few seconds.

## Use

- **Plugin:** `/speaks on|off|stop|status`.
- **Shell:** `bin/claude-speaks on|off|stop|status|say <text>|shutdown`.

`~/.config/claude-speaks/config.json` is re-read on every reply, so changes take effect immediately (see `config.example.json`):
- **`pocket_voice`:** `eponine`, `azelma`, `eve`, `jane`, `vera`, `jean`, `marius` and others. Despite the name, `alba` (the default) is a male voice.
- **`volume_db`:** gain applied through a soft limiter. 6 is a good start.
- **`max_chars`:** the cutoff for long replies (default 600; 0 means no limit).

### Using a TTS server

Set `http_url` to any OpenAI-style `/v1/audio/speech` endpoint, and speech goes there. It accepts raw PCM or vLLM-Omni's SSE stream. If `http_url` isn't set, or a request fails (unreachable, an HTTP error, or no audio), that reply falls back to Pocket TTS. `~/.local/state/claude-speaks/daemon.log` records which engine spoke.

| Key | Meaning |
|---|---|
| `http_url`, `http_model`, `http_voice`, `http_sample_rate` | Where to send speech, and with what model, voice and sample rate |
| `http_text_profile` | The text rules the server gets. `kokoro` (the default) keeps only what Kokoro's own pronunciation gets wrong, such as hashes, `~`, numbers, units and the separators in paths. `pocket` spells everything out. |
| `http_extra` | Merged into the request body, e.g. `{"normalization_options": {"normalize": false}}` so Kokoro-FastAPI doesn't rewrite the text a second time |

[Kokoro-FastAPI](https://github.com/remsky/Kokoro-FastAPI) works as-is:

    docker run --gpus all -p 127.0.0.1:8880:8880 ghcr.io/remsky/kokoro-fastapi-gpu:latest   # use :latest-cu128 on RTX 50-series

`config.example.json` holds matching settings, using the `af_heart` voice.

`~/.config/claude-speaks/lexicon.json` maps whole words to how they should be spoken, e.g. `{"kubectl": "cube control"}`. Your entries are merged over the built-ins. Lowercase keys match any case; other keys match exactly.

## Without the plugin

`uv sync && ./install.sh` registers `speak.py` as a classic `Stop` hook in `~/.claude/settings.json` instead.

## GPU server: Voxtral 4B (optional)

`deploy/voxtral/compose.yaml` runs Mistral's Voxtral-4B-TTS in vLLM-Omni on port 18090:

    hf download mistralai/Voxtral-4B-TTS-2603
    GPU_UUID=GPU-... docker compose -f deploy/voxtral/compose.yaml up -d    # see `nvidia-smi -L`; ~4 min to load

On an RTX 5060 Ti it uses ~11.4 GB of VRAM, and the first audio arrives in ~0.4 s once warm.

Gotchas on WSL:
- The container sees every GPU no matter what `device_ids` says, so the card is pinned with `CUDA_VISIBLE_DEVICES=<uuid>`.
- Offline repo-ID lookup fails for Mistral-format models, so the model is given as its local snapshot path.

## License

MIT
