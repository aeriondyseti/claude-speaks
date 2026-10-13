# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.5.1] - 2026-10-13

### Added

- The letter `a` is read as "ey" (not the article) when it's alone in inline code or beside a math
  operator: `a >= b`, `x + a`, `a*b`. A default replacement, so add it to your own list if you keep
  one.

### Fixed

- Regex replacements no longer add a space after an opening bracket or before an operator
  ("( ey + b)", "ey *b"), and keep the space a match ate (`(a + b) * c` -> "... times c").

## [0.5.0] - 2026-10-13

### Added

- Spoken forms as default replacements. Each is a rule in `replacements` that you can edit or remove:
  - `x * y` and `x ** 2` become "x times y" and "x to the power of 2"
  - `helpers.ts:42` becomes "helpers.ts, line 42"
  - `3:1` becomes "3 to 1"
  - `kevin@example.com` becomes "kevin at example.com"
  - `#45` becomes "number 45"
  - `$5` becomes "5 dollars"
  - `>=`, `<=`, `!=` and `==` are said in words
  - `__init__` becomes "dunder init"
  - `*.py` becomes "star dot py"
  - task boxes `[x]` and `[ ]` become "done" and "to do"
- `/regex/` replacements can use `\1` backreferences.
- Clock times are read as times: `9:05` is "nine oh five", `14:00` is "fourteen hundred", `7:30 pm`
  is "seven thirty p m".
- Tables are read aloud, one row per sentence with a pause between cells, instead of being skipped.
- A test suite for the text cleanup: `uv run --no-project --with pytest pytest`.

### Changed

- Regex replacements only add a space where the replacement would otherwise run into the next
  character. Before, they always added one on both sides.
- Markdown structure is removed before any rule runs.
- A long first sentence is sent to the TTS server in clauses. In one test, Kokoro's first audio
  came after 1.07 s instead of 2.7 s.
- Your own `replacements` list replaces the defaults, so copy the new rules into it if you keep one.

### Fixed

- Numbered lists are no longer read as numbers: "1. first" was spoken "one. first".
- No stray asterisk is spoken: `***bold***`, bold across a line break, spaced rules (`* * *`)
  and `*.py` globs are all handled.
- A sentence-ending period after a path is no longer read as "dot".
- URLs no longer swallow the punctuation after them.
- Dotfiles such as `.env` are read as paths, and the space before them is kept.
- `#1` at the start of a line is no longer taken for a heading.
- Setext underlines, closing hashes and a leading `>=` are no longer spoken.
- UUIDs are no longer split by the `9–12` range rule.
- `now.Right` is read as two sentences.
- "Mr. Smith" and "e.g. this" are no longer sent as two requests.
- HTML tags, entities, terminal colour codes, emoji, autolinks and footnote markers are no longer
  spoken. Tags are only removed when they are certainly HTML, so `<path>` and `Vec<String>` stay.

## [0.4.0] - 2026-10-13

### Changed

- All pronunciation comes from the config. The built-in lexicon, `lexicon.json` and the
  `http_text_profile` setting (`kokoro`/`pocket`) are gone: every word swap is a
  `replacements` rule, and each rule that needs code has its own setting (`speak_hashes`,
  `speak_paths`, `speak_snake_case`, `speak_versions`, `speak_numbers`, `spell_letter_digits`,
  `spell_abbreviations`). The defaults reproduce the old `kokoro` profile, and every engine,
  Pocket TTS included, gets the same text. For the old Pocket behaviour, turn on the two
  `spell_*` settings and add replacements such as `py => pie` and `json => jay sohn`.

### Fixed

- The "… and more on screen" ending is spoken by the TTS server, not Pocket TTS. Sentence
  splitting made a bare "..." its own request, which Kokoro answers with no audio, so the
  daemon fell back to Pocket for the rest. A piece with no words now joins its neighbour.

## [0.3.2] - 2026-10-13

### Fixed

- A whole-word replacement no longer splits a file name: with `daemon => daymun`,
  `daemon.py` reads "daymun dot py" instead of losing its "dot". Only `/regex/` rules are
  padded with spaces now.

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

[Unreleased]: https://github.com/aeriondyseti/claude-speaks/compare/v0.5.1...HEAD
[0.5.1]: https://github.com/aeriondyseti/claude-speaks/compare/v0.5.0...v0.5.1
[0.5.0]: https://github.com/aeriondyseti/claude-speaks/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/aeriondyseti/claude-speaks/compare/v0.3.2...v0.4.0
[0.3.2]: https://github.com/aeriondyseti/claude-speaks/compare/v0.3.1...v0.3.2
[0.3.1]: https://github.com/aeriondyseti/claude-speaks/compare/v0.3.0...v0.3.1
[0.3.0]: https://github.com/aeriondyseti/claude-speaks/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/aeriondyseti/claude-speaks/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/aeriondyseti/claude-speaks/releases/tag/v0.1.0
