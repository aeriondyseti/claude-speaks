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
- [`uv`](https://docs.astral.sh/uv/), the only Python requirement: everything runs through `uv run`
- Linux, WSL2 or macOS (on Windows, use WSL2)
- Audio out: `paplay` (PulseAudio or PipeWire; WSLg provides it), or [sounddevice](https://python-sounddevice.readthedocs.io/), whose macOS wheel bundles PortAudio (on Linux it needs `libportaudio2`). `audio_backend` picks between them; `auto` prefers `paplay`.

Then run:

    /plugin install speaks --marketplace aeriondyseti/aeriondyseti-plugins

At each session start, the plugin starts a small background daemon. On the very first start, `uv run` installs Pocket TTS with CPU-only PyTorch (~1 GB, into `~/.local/share/claude-speaks/venv`); a toast says so if a reply arrives while that's still running. Pocket TTS itself loads only for the first reply that needs it, with a "Loading Pocket TTS" toast (about 5 s). Replies spoken by a TTS server never load it.

## Use

- **Plugin:** `/speaks on|off|stop|status`.
- **Shell:** `bin/claude-speaks on|off|stop|status|say <text>|shutdown`.

### Settings

As a plugin, everything is a plugin option, set when you install it or later in `/config`. Plugin options override `~/.config/claude-speaks/config.json`, which uses the same keys (see `config.example.json`) and is the place to set them when you run without the plugin. The config is re-read on every reply, so changes apply immediately.

| Option | Default | Meaning |
|---|---|---|
| `pocket_voice` | `eponine` | Pocket voice: `eponine`, `azelma`, `eve`, `jane`, `vera`, `jean`, `marius`, … (`alba` is male) |
| `volume_db` | `6` | Gain through a soft limiter |
| `max_chars` | `600` | Characters spoken per reply (0 means no limit) |
| `audio_backend` | `auto` | `paplay`, `sounddevice`, or `auto` (`paplay` if installed) |
| `replacements` | the light rules | Every word-level fix: `find => replace`, one per entry, applied first and the same for every engine. A plain word matches whole words (any case when written in lowercase); `/regex/` is a pattern. Defaults: `Ti => tee eye`, `~/` and `$HOME` → home, `~` before a number → about, `9–12` → 9 to 12, and dropping empty `()`. Add your own, e.g. `kubectl => cube control`, or `py => pie` and `json => jay sohn` for Pocket TTS. |
| `speak_hashes` | on | Commit hashes and UUIDs read as "hash ending with" plus their last four characters |
| `speak_paths` | on | Slashes, dots, dashes and underscores read inside paths and file names: `a/b.py` → "a slash b dot py" |
| `speak_snake_case` | on | `debug_log_text` → "debug underscore log underscore text"; vowelless parts are spelled out |
| `speak_versions` | on | `v0.3.2` → "vee zero point three point two" |
| `speak_numbers` | on | Numbers, units, multipliers and negatives as words: `8 GB`, `-5 dB`, `2x`, `1,234` |
| `spell_letter_digits` | off | `p99`, `x86` → "pee 99", "ex 86" |
| `spell_abbreviations` | off | Vowelless words (`db`, `cfg`, `RTX`) and all-caps ones like `TTY` spelled letter by letter. Add a replacement for any you want said as a word, e.g. `St => street`. |
| `http_url` | empty | An OpenAI-style `/v1/audio/speech` endpoint. Empty means Pocket only. |
| `http_api_key` | empty | Sent as `Authorization: Bearer <key>`. A sensitive option, kept in secure storage; or `${ENV_VAR}` |
| `http_headers` | empty | Extra headers, `Name: value` each |
| `http_model`, `http_voice` | empty | The request's `model` and `voice` |
| `http_sample_rate`, `http_timeout` | `24000`, `10` | The PCM rate in Hz, and the seconds to wait before falling back |
| `http_extra` | empty | JSON merged into the request body |
| `http_split_sentences` | on | One request per sentence, fetched ahead of playback. The first audio comes after one sentence's synthesis (≈0.3 s with Kokoro-FastAPI on a GPU, against ≈3.7 s for a whole paragraph). If a later sentence fails, Pocket speaks the rest. |
| `debug_log_text` | off | Logs the exact text each engine is given to `daemon.log`, for troubleshooting pronunciation. The log is readable only by you. |

Nothing about pronunciation is hidden in code: every word swap is a replacement, and each rule that needs code is a setting above. Only Markdown cleanup is fixed (code blocks become "Code block omitted", tables are skipped, links read as their label or "a link"). The defaults suit Kokoro; for Pocket TTS on its own, turn on the two spelling settings and add replacements for the file types and jargon you hear wrong.

### Using a TTS server

Any `http_*` setting can name environment variables as `${VAR}` or `${VAR:-default}`, as in Claude Code's `.mcp.json`, e.g. `http_api_key` = `${OPENAI_API_KEY}`. They're read from Claude Code's environment on each reply and expanded only when the request is built. Only the variables a setting names are passed along, and an unset one with no default expands to empty (`daemon.log` names it, never a value).

With `http_url` set, speech goes to the server, which can return raw PCM or vLLM-Omni's SSE stream. A request that fails (unreachable, an HTTP error, or no audio) falls back to Pocket TTS for that reply. `~/.local/state/claude-speaks/daemon.log` records which engine spoke and how long the first audio took.

[Kokoro-FastAPI](https://github.com/remsky/Kokoro-FastAPI) works as-is:

    docker run --gpus all -p 127.0.0.1:8880:8880 ghcr.io/remsky/kokoro-fastapi-gpu:latest   # use :latest-cu128 on RTX 50-series

Use `http_url` `http://127.0.0.1:8880/v1/audio/speech`, `http_model` `kokoro`, `http_voice` `af_heart`, and `http_extra` `{"normalization_options": {"normalize": false}}`, so the server doesn't rewrite the text a second time.

## Without the plugin

`./install.sh` registers `speak.py` as a classic `Stop` hook in `~/.claude/settings.json` instead.

## GPU server: Voxtral 4B (optional)

`deploy/voxtral/compose.yaml` runs Mistral's Voxtral-4B-TTS in vLLM-Omni on port 18090:

    hf download mistralai/Voxtral-4B-TTS-2603
    GPU_UUID=GPU-... docker compose -f deploy/voxtral/compose.yaml up -d    # see `nvidia-smi -L`; ~4 min to load

On an RTX 5060 Ti it uses ~11.4 GB of VRAM, and the first audio arrives in ~0.4 s once warm.

Gotchas on WSL:
- The container sees every GPU no matter what `device_ids` says, so the card is pinned with `CUDA_VISIBLE_DEVICES=<uuid>`.
- Offline repo-ID lookup fails for Mistral-format models, so the model is given as its local snapshot path.

## Development

The text cleanup has its own tests, which need no audio device, model or daemon:

    uv run --no-project --with pytest pytest

## License

MIT
