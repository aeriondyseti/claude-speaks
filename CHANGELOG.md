# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.3.1] - 2026-10-13

### Fixed

- The daemon is replaced automatically when the plugin updates. `speak.py` checks the running
  daemon's code fingerprint (a hash of `speak.py` and `daemon.py`) with a `hello` before
  each reply and at session start. A stale daemon, including one from 0.2.0 or 0.3.0 that
  doesn't answer the handshake, is shut down and a current one started. No manual
  `claude-speaks shutdown` is needed after an update; editing either file in development
  restarts it too.

## [0.3.0] - 2026-10-13

### Added

- `http_split_sentences` (on by default): one request per sentence, fetched ahead of
  playback. First audio from Kokoro-FastAPI dropped from ~3.7 s to ~0.3 s for a paragraph.
  If a later sentence fails, Pocket speaks the rest.
- `debug_log_text`: log the exact text each engine is given, for pronunciation troubleshooting.
- `daemon.log` records time to first audio, and is created readable only by the user.

## [0.2.0] - 2026-10-13

### Added

- Plugin options for everything, including an OpenAI-style TTS server: URL, API key (a
  sensitive option), extra headers, model, voice, sample rate, timeout, extra body JSON,
  and which text rules it gets. Options override `config.json`.
- `${VAR}` / `${VAR:-default}` in any `http_*` setting, read from Claude Code's environment
  per reply and expanded only when the request is built.
- `replacements`: user-editable `find => replace` rules (whole words or `/regex/`),
  pre-filled with the light rules.
- A light `kokoro` text profile for servers like Kokoro-FastAPI, which keeps only what
  Kokoro's own pronunciation gets wrong.

- `audio_backend`: play through `paplay` or the cross-platform sounddevice (PortAudio), so
  macOS works; `auto` prefers `paplay`.
- Toasts while Pocket TTS installs (first run) and loads.

### Changed

- Pocket TTS loads on the first reply that needs it, not at session start; the session-start
  warm-up only starts the (now light) daemon, and `uv run` installs dependencies on first use.
- `uv` is the only Python requirement: the plugin, CLI and classic hook run `speak.py` with
  `uv run --no-project`.
- A failed server request (an HTTP error or no audio, not only unreachable) falls back
  to Pocket TTS. `daemon.log` records which engine spoke.
- The daemon cleans up each reply per engine. Its socket and state directory are
  private to the user.

### Fixed

- The daemon socket works under deeply nested state directories (AF_UNIX's ~108-character
  limit); playback errors are logged instead of swallowed.
- `stop()` no longer adds a sentence-end pause; ALL_CAPS parts of identifiers are read as words.

## [0.1.0] - 2026-10-13

### Added

- `speaks` plugin: a `turn.complete` hook reads the main loop's final answer aloud
  with Pocket TTS on the CPU, through a background daemon that keeps the model loaded.
- Session-start warm-up that installs Pocket TTS (CPU-only torch, ~1 GB) on first use
  and preloads the model, so no reply waits on it.
- `/speaks on|off|stop|status`.
- Speech-friendly text: paths, hashes, numbers, units, versions, abbreviations and
  file types rewritten as words; code blocks and tables skipped; a user lexicon.
- Optional OpenAI-compatible HTTP engine (raw PCM or vLLM-Omni SSE) with Pocket fallback,
  and a Voxtral 4B compose file for a GPU server.

[Unreleased]: https://github.com/aeriondyseti/claude-speaks/compare/v0.3.1...HEAD
[0.3.1]: https://github.com/aeriondyseti/claude-speaks/compare/v0.3.0...v0.3.1
[0.3.0]: https://github.com/aeriondyseti/claude-speaks/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/aeriondyseti/claude-speaks/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/aeriondyseti/claude-speaks/releases/tag/v0.1.0
