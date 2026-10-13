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

### Settings

As a plugin, everything is a plugin option, set when you install it or later in `/config`. Plugin options override `~/.config/claude-speaks/config.json`, which uses the same keys (see `config.example.json`) and is the place to set them when you run without the plugin. The config is re-read on every reply, so changes apply immediately.

| Option | Default | Meaning |
|---|---|---|
| `pocket_voice` | `eponine` | Pocket voice: `eponine`, `azelma`, `eve`, `jane`, `vera`, `jean`, `marius`, … (`alba` is male) |
| `volume_db` | `6` | Gain through a soft limiter |
| `max_chars` | `600` | Characters spoken per reply (0 means no limit) |
| `replacements` | the light rules | `find => replace`, one per entry, applied first under every profile. A plain word matches whole words (any case when written in lowercase); `/regex/` is a pattern. Defaults: `Ti => tee eye`, `~/` and `$HOME` → home, `~` before a number → about, `9–12` → 9 to 12, and dropping empty `()`. Add your own, e.g. `kubectl => cube control`. |
| `http_url` | empty | An OpenAI-style `/v1/audio/speech` endpoint. Empty means Pocket only. |
| `http_api_key` | empty | Sent as `Authorization: Bearer <key>`. A sensitive option, kept in secure storage; or `${ENV_VAR}` |
| `http_headers` | empty | Extra headers, `Name: value` each |
| `http_model`, `http_voice` | empty | The request's `model` and `voice` |
| `http_sample_rate`, `http_timeout` | `24000`, `10` | The PCM rate in Hz, and the seconds to wait before falling back |
| `http_extra` | empty | JSON merged into the request body |
| `http_text_profile` | `kokoro` | `kokoro` keeps only what Kokoro's pronunciation gets wrong; `pocket` spells everything out |

The rules that need code rather than a find-and-replace are built in: numbers, units and versions as words, hashes as "hash ending with …", and dots, dashes, slashes and underscores read inside paths and names. Under the `pocket` profile, `~/.config/claude-speaks/lexicon.json` (`{"word": "spoken"}`) still adds whole-word fixes.

### Using a TTS server

Any `http_*` setting can name environment variables as `${VAR}` or `${VAR:-default}`, as in Claude Code's `.mcp.json`, e.g. `http_api_key` = `${OPENAI_API_KEY}`. They're read from Claude Code's environment on each reply and expanded only when the request is built. Only the variables a setting names are passed along, and an unset one with no default expands to empty (`daemon.log` names it, never a value).

With `http_url` set, speech goes to the server, which can return raw PCM or vLLM-Omni's SSE stream. A request that fails (unreachable, an HTTP error, or no audio) falls back to Pocket TTS for that reply. `~/.local/state/claude-speaks/daemon.log` records which engine spoke.

[Kokoro-FastAPI](https://github.com/remsky/Kokoro-FastAPI) works as-is:

    docker run --gpus all -p 127.0.0.1:8880:8880 ghcr.io/remsky/kokoro-fastapi-gpu:latest   # use :latest-cu128 on RTX 50-series

Use `http_url` `http://127.0.0.1:8880/v1/audio/speech`, `http_model` `kokoro`, `http_voice` `af_heart`, and `http_extra` `{"normalization_options": {"normalize": false}}`, so the server doesn't rewrite the text a second time.

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
