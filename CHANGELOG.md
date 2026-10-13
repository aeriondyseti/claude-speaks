# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html), with a
leading `0.` to mark it as pre-release, use-at-your-own-risk software: `0.MAJOR.MINOR.PATCH`. A
breaking change goes from 0.1.5.2 to 0.2.0.0. Releases up to 0.5.2 used three parts; 0.5.2
corresponds to 0.1.5.1 in this scheme, and any four-part version is newer than any three-part one.

## [Unreleased]

## [0.1.9.0] - 2026-10-13

### Added

- ISO dates are read as dates: `2026-10-13` is "October thirteenth, twenty twenty six". Before,
  the `9–12` range rule turned the dashes into "to".
- Default replacements:
  - `localhost:3000` and `127.0.0.1:8880` say "port". Before, the ratio rule said "to".
  - `Ctrl` and `Cmd` become "control" and "command". With the spelling settings on, `Ctrl` was
    spelled out.
  - `C#` and `F#` become "see sharp" and "eff sharp". Kokoro dropped the `#`.
  - `w/` and `w/o` become "with" and "without".
  - `→` and spaced `->` become "to". `p->x` is left alone.
  - `^` between operands is "to the power of".
  - `1/2` is "one slash two". Kokoro dropped the slash. A real fraction rule is still to come.
  - `===` is "strictly equals" and `!==` is "strictly not equal to".
  - `<` and `>` before a number say "less than" and "greater than", so `Vec<String>` is left alone.

### Fixed

- `~$0.03` says "about".
- Comparison operators work without spaces, as in `>=3.10` or `a===b`.
- A regex replacement after a comma gets a space: `>=3.10,<3.15`.

If you keep your own `replacements` list, copy the new default rules into it.

## [0.1.8.0] - 2026-10-13

### Added

- Repo file names that Kokoro spells out letter by letter in capitals are lowercased, as default
  replacements: `README`, `CHANGELOG`, `TODO`, `TODOS`, `FIXME`, `CODEOWNERS`, `CHEATSHEET`,
  `MAKEFILE`, `DOCKERFILE`, `GEMFILE`, `RAKEFILE`, `PROCFILE`, `JUSTFILE`, `VAGRANTFILE`, and
  `STYLEGUIDE` ("style guide"). `README.md` is now "readme dot md". Names it already reads as
  words, like `ROADMAP` and `LICENSE`, are left alone. Copy the new rules into your own
  `replacements` list if you keep one.

## [0.1.7.0] - 2026-10-13

### Added

- Dice notation, as default replacements: `22d6` is "twenty two dee six", `d20` "dee twenty",
  `2d8-1` "two dee eight minus one", `4d6kh3` / `2d20kl1` "keep highest three" / "keep lowest
  one". Each side is at most three digits, so a short hash isn't taken for a roll.
- Letter ranges, as default replacements: `a–f`, `A-Z` are "eigh to f", "eigh to Z". Single
  letters only, so x-ray and e-mail are left alone.
- `a-ha` is replaced with "aha": in some sentences Kokoro said "eigh-ha".

### Fixed

- Short hashes (7 to 11 hex characters, like git's `86441d4`) are spelled out instead of reaching
  the voice raw, where Kokoro read them as one big number.

If you keep your own `replacements` list, copy the new default rules into it.

## [0.1.6.2] - 2026-10-13

### Changed

- A number read as a quantity says "zero": `0 errors` is "zero errors", `0.5s` "zero point five
  seconds". A number read digit by digit says "oh": versions (`v0.3` "vee oh dot three"), hashes,
  version folders in paths (`speaks/0.3.0/`) and times (`10:05` "ten oh five").

## [0.1.6.1] - 2026-10-13

### Changed

- Decimal numbers say "zero" again: `0.5s` is "zero point five seconds", `2.05` "two point zero
  five". Everything else keeps "oh": versions (`v0.3` "vee oh dot three"), hashes, path digits,
  times and plain counts.

## [0.1.6.0] - 2026-10-13

### Changed

- Zero is read "oh" everywhere: `v0.3` is "vee oh dot three", `0.5s` "oh point five seconds", and
  hashes and path digits likewise.
- Only a decimal number says "point" (`3.14`, `2.0`). Versions, and any number with more than one
  dot, say "dot": `1.2.3` is "one dot two dot three".

## [0.1.5.2] - 2026-10-13

### Fixed

- Two Claude Code sessions on different plugin versions no longer cut off each other's speech.
  A session only replaces a daemon that is older than itself; a newer one is left running and
  serves it too. `hello` now reports the plugin version as well as the code fingerprint.
- A daemon replaced at session start finishes the reply it's speaking before it exits. The new
  daemon starts at once, and a new reply or `/speaks stop` still cuts the old one off, so the two
  never talk over each other. A session with a reply waiting replaces an older daemon at once, as
  before.

### Changed

- Versions are now `0.MAJOR.MINOR.PATCH` (see the top of this file).

## [0.5.2] - 2026-10-13

### Fixed

- The letter A is spelled "eigh", which Kokoro says as the letter. "ey" and "ay" both came out as
  "eye", in the letter rule and in spelled-out hashes and abbreviations. Spellings are checked
  against Kokoro-FastAPI's `/dev/phonemize`. If you keep your own replacements, change `=> ey` to
  `=> eigh`.
- "am" in a time was read as the article; it's now spelled out like "pm".
- "7:30 pm." no longer swallows the sentence's period.

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

[Unreleased]: https://github.com/aeriondyseti/claude-speaks/compare/v0.1.9.0...HEAD
[0.1.9.0]: https://github.com/aeriondyseti/claude-speaks/compare/v0.1.8.0...v0.1.9.0
[0.1.8.0]: https://github.com/aeriondyseti/claude-speaks/compare/v0.1.7.0...v0.1.8.0
[0.1.7.0]: https://github.com/aeriondyseti/claude-speaks/compare/v0.1.6.2...v0.1.7.0
[0.1.6.2]: https://github.com/aeriondyseti/claude-speaks/compare/v0.1.6.1...v0.1.6.2
[0.1.6.1]: https://github.com/aeriondyseti/claude-speaks/compare/v0.1.6.0...v0.1.6.1
[0.1.6.0]: https://github.com/aeriondyseti/claude-speaks/compare/v0.1.5.2...v0.1.6.0
[0.1.5.2]: https://github.com/aeriondyseti/claude-speaks/compare/v0.5.2...v0.1.5.2
[0.5.2]: https://github.com/aeriondyseti/claude-speaks/compare/v0.5.1...v0.5.2
[0.5.1]: https://github.com/aeriondyseti/claude-speaks/compare/v0.5.0...v0.5.1
[0.5.0]: https://github.com/aeriondyseti/claude-speaks/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/aeriondyseti/claude-speaks/compare/v0.3.2...v0.4.0
[0.3.2]: https://github.com/aeriondyseti/claude-speaks/compare/v0.3.1...v0.3.2
[0.3.1]: https://github.com/aeriondyseti/claude-speaks/compare/v0.3.0...v0.3.1
[0.3.0]: https://github.com/aeriondyseti/claude-speaks/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/aeriondyseti/claude-speaks/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/aeriondyseti/claude-speaks/releases/tag/v0.1.0
