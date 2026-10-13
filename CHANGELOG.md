# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/aeriondyseti/claude-speaks/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/aeriondyseti/claude-speaks/releases/tag/v0.1.0
