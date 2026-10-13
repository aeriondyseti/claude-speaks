# Text cleanup sprint: plan

Status: done (sections 1–5c), 2026-10-13. Section 5d is for a later sprint.

## Decisions (2026-10-13)

- **Scope:** sections 1–5c, with one commit per section, each with its tests. Released once at the end as 0.5.0. Section 5d waits for a later sprint.
- **Code blocks:** keep "Code block omitted." No setting.
- **Tables:** read rows aloud, header included, with a pause between cells (a comma) and between rows (a sentence end). The `|---|` separator row is skipped.
- **Number colons:** a valid clock time (`H:MM` or `HH:MM`, hours 0–23, minutes 00–59, optional `:SS`, optional am/pm) is read as a time: `10:30` → "ten thirty", `9:05` → "nine oh five". Anything else (`3:1`, `16:9`, `25:00`) reads "x to y".
- **Dunders:** `__init__` → "dunder init", with "dunder" as a config rule.
- **`max_chars`:** keeps counting after expansion; document it.
- **Default replacements:** add all of section 5c's candidates, plus task-list words. Copy them into the user's own `settings.json` list, which overrides the defaults.
 Comes from comparing `to_speech` (`speak.py`) with other open-source reply readers on 2026-10-13. Each item lists the input, what 0.4.0 says now, and what it should say. Work them in order: item 1 is the safety net for the rest.

## 1. A test suite for `to_speech`

There are no Python tests. Add `tests/test_speech.py` (pytest, run with `uv run --with pytest pytest`): a table of Markdown input → exact spoken output, under the default config and under a Pocket-style config (both `spell_*` settings on). It needs no audio device, model or daemon.

- **Seed it with today's behaviour** before changing anything: the sample passage used for the 0.4.0 refactor (paths, hashes, versions, units, snake_case, abbreviations), so later fixes can't silently change it.
- **Add each case below as a failing test first**, then fix it.
- **Cover `split_sentences`** too: `x. ... and more on screen.` must not produce a wordless sentence (the 0.4.0 fix). It moved from `daemon.py` to `speak.py` so the tests need no numpy.

Done: `tests/test_speech.py` and `tests/sample.md`, 40 tests in under a tenth of a second.

## 2. Markdown cleanup bugs

Found by running [berga-a/claude-speak](https://github.com/berga-a/claude-speak)'s `tests/test_markdown.py` inputs through ours.

| Input | Now | Should be | Cause |
|---|---|---|---|
| `1. first` ↵ `2. second` | "one. first. two. second." | "first. second." | `NUMBER` runs before list markers are stripped. Strip block markers (headings, lists, quotes) first. |
| `***Both*** here.` | "\*Both\* here." | "Both here." | One pass of the emphasis regex. Loop it, or match `\*{1,3}`. |
| `**Bold spanning` ↵ `two lines** here.` | "\*\*Bold spanning. two lines\*\* here." | "Bold spanning. two lines here." | Emphasis is matched within a line. |
| `Math 2 * 3 stays.` | "two * three stays." | "two times three stays." | No rule for `*` between numbers. |
| `Before.` ↵ `* * *` ↵ `After.` | "Before. \* \*. After." | "Before. After." | The rule regex only knows `***`/`---`, not spaced ones. |
| ``Glob `*.py` and a footnote*`` | "Glob.py and a footnote." | "Glob star dot py and a footnote." | The two `*` pair up as emphasis across the backticks, then the space before `.py` is eaten by the punctuation tidy-up. Protect inline code before emphasis runs. "star" itself is a word swap, so it belongs in the default `replacements` (e.g. `/\*(?=\.\w)/ => star`), not in code. |

**Safety net:** after all rules, drop any `*` still left (berga-a's catch-all). A literal asterisk is never meant to be spoken; `2 * 3` and globs are handled before it.

Done: Markdown structure (rules, headings, list markers, quotes, links, emphasis) is now removed first, in `strip_markup`, with emphasis skipping `inline code` and never matching inside a word. "times" and "star dot" are default replacements. `>=` at the start of a line is no longer taken for a quote (from 5a). 23 new tests; a test also keeps `plugin.json`'s default replacements equal to `DEFAULT_REPLACEMENTS`. The user's own `replacements` list in `settings.json` gets the new defaults at the end of the sprint.

## 3. Sentence-by-sentence latency: split long sentences at clauses

With `http_split_sentences`, first audio waits for the first sentence's synthesis. A 300-character first sentence delays it by seconds. berga-a renders sentences over 100 characters in clause-sized pieces, split after `,;:—–`, keeping the text identical when joined. Apply the same in `split_sentences`:

- Only split sentences longer than a threshold (start at 120 characters).
- Never produce a wordless piece (keep the 0.4.0 rule).
- Splitting changes prosody at the join; listen to a few with Kokoro before settling the threshold.
- **Don't split after abbreviations** (from alphabet/speak): `Mr. Smith arrived.` is sent as "Mr." and "Smith arrived.", and `e.g. this, i.e. that` likewise. Keep a small list (e.g., i.e., Mr., Mrs., Dr., vs., etc.) that never ends a sentence.

Done, narrowed: only the **first** sentence is split, into pieces of up to 100 characters (`FIRST_CLAUSES`), because later ones are synthesised while earlier ones play. Measured against Kokoro-FastAPI: a 212-character first sentence gave first audio after 2.7 s; its 104-character first clause, after 1.07 s. Abbreviations never end a sentence ("no" is left off the list: "The answer is no." is far more common than "No. 5").

## 4. Smaller ideas (decide, then do or drop)

- ~~Silence instead of "Code block omitted."~~ Decided against: the sentence stays.
- **Length limit counted after expansion.** `max_chars` applies to the expanded text, so a path-heavy reply ("slash", "dot") is cut sooner. That's intended, since it bounds speaking time. Document it in the README.

## 5. From the other projects

Surveyed 2026-10-13: praneybehl/claude-code-voice-hook, alphabet/speak, antonyjaen/claude-speak, CareyScott/speak, CharlesAdewumi2004/Claude-Code-Speech-, ~cg/claude-code-tts, pcamarajr/claude-spoken-briefs, renjfk/opencode-voice, livekit/agents-js (`text_transforms.ts`), and the example inputs in AutoBot-AI#13102. Every "Now" below is verbatim 0.4.0 output under the default config. Each fix is marked **code** (a built-in rule, or a new `TEXT_RULES` setting) or **config** (a default `replacements` entry), keeping 0.4.0's rule that word swaps live in config.

### 5a. Bugs in existing rules (code)

| Input | Now | Should be | Note |
|---|---|---|---|
| `Saved to /tmp/out.txt.` | "…out dot txt dot." | "…out dot txt." | `PATH` swallows a sentence-ending period. Also `look in /tmp.` |
| `Visit https://x.com, then go` | "Visit a link then go." | "Visit a link, then go." | The URL regex eats trailing `.,!?)`. `Docs (see https://x.com/a).` loses its `)` too. End on `[^\s).,!?]` (cg). |
| `the .env file`, `Edit .gitignore`, `x != y` | "the.env file", "Edit.gitignore", "x!= y" | "the dot env file", "Edit dot gitignore", "x != y" | The final `\s+([.,;:!?])` tidy-up only exists for `speak_path` padding; limit it to that. Dotfiles also aren't recognised as paths. |
| `Contact kevin@example.com today.` | "kevin@ example dot com" | "kevin at example dot com" | Emails need their own rule before `PATH`. Also `first_last@example.com`. |
| `#1 priority`, `PR #45` | "one priority", "PR #forty five" | "number one priority", "PR number forty five" | Headings must need a space after `#`. "number" itself is **config**: `/#(?=\d)/ => number`. |
| `- [x] done`, `- [ ] todo` | "[x] done", "[ ] todo" | "done", "to do" | Task-list boxes. |
| `1) first` | "one) first." | "first." | Same cause as the `1.` list bug in section 2. |
| `Setext` ↵ `======`, `# Title #` | "Setext. ======.", "Title #." | "Setext.", "Title." | Setext underlines and closing hashes. |
| `>= 3` at the start of a line | "= three." | "greater than or equal to three" | The quote marker must not match `>=`. The words are **config** (`>= =>`, `<=`, `!=`, `==`). |
| `__dunder_method__ stays`, `__init__` | "dunder_method stays" | "dunder method stays" or kept intact | `speak_snake_case` runs before emphasis stripping; dunders need a rule of their own. |
| `x**2 + y**2`, `a *** b`, `**bold***italic*`, `see ***** here` | "xtwo + ytwo", "a * b", "bolditalic", "see * here" | left as written, minus stray `*` | Use livekit's emphasis rule: never match inside a word, runs of 1–3 only. Pairs with the safety net in section 2; their table-driven tests are worth porting. |
| `helpers.ts:42` | "helpers dot ts:forty two" | "helpers dot ts, line forty two" | `file:line` references. |
| `3:1`, `10:30` | "three:one", "ten:thirty" | "three to one", "ten thirty" | A bare colon between numbers. Times vs ratios is ambiguous; pick one default and make the word **config**. |
| `id 123e4567-e89b-12d3-a456-426614174000` | "id 123e4567-e89b-12d3-a456 to four hundred twenty six billion…" | "id hash ending with four zero zero zero" | The default range rule (`9–12` → "to") runs before UUID detection and splits the UUID. Hashes and UUIDs must be protected before replacements run. |
| `now.Right`, `make.Then test` | "now dot Right" | "now. Right" | A missing space after a period looks like `file.ext`. Treat an extension that starts with a capital followed by lowercase letters as a sentence break. `Node.js` and `3.14` must still pass. |

Done, with every word in config: regex replacements gained backreferences (`\1`, from 5c) and pad only where the replacement would run into a neighbour, so `helpers.ts:42` → `\1, line \2` stays attached to its file. "at", "line", "to", "number", "dollars", the operator words, "dunder", "done"/"to do", and (at the user's request) "times" and "to the power of" for `*`/`**` between operands are default replacements. Code changes: paths don't end on a sentence's period, dotfiles are paths, URLs stop before trailing punctuation, the space-before-punctuation tidy-up only applies before whitespace, `#1` isn't a heading, setext underlines and closing hashes go, `__init__` isn't bold, `now.Right` gets a space, UUIDs are read before replacements, and clock times (`9:05`, `14:00`, `7:30 pm`) are read in `speak_numbers`. Known gaps: `src/**/*.ts` (a `**` glob inside a path) reads "src// star dot ts"; `localhost:8080` and `1:2:3` keep their colons.

### 5b. Markup we don't clean up yet (code)

- **HTML tags:** `Use <kbd>Ctrl</kbd>+<kbd>C</kbd>` gives "<kbd>Ctrl< slash kbd >+<kbd>C< slash kbd >". Strip real tags only; `Vec<String>` and `a < b` already pass and must keep passing. `<details><summary>` too.
- **HTML entities:** `AT&amp;T`, `a &lt; b` are spoken as written. Use `html.unescape` first.
- **ANSI escapes:** `\x1b[31mError\x1b[0m` reaches the voice.
- **Emoji:** `Done ✅ 🎉` reaches the voice. Drop Unicode category `So` and the variation selectors U+FE00–FE0F (cg, livekit).
- **Autolinks and footnotes:** `<https://example.com>` gives "<a link"; `Footnote[^1]` gives "Footnote[^one]".
- **Tables:** dropped silently today. Either say "Table omitted." like code blocks, or read rows as sentences ("a, b. 1, 2.", CareyScott). Make it a setting alongside the code-block idea in section 4.

Done: tables are read row by row ("a, b."), with the `|---|` row and empty cells skipped and `\|` kept as content. HTML tags go only when they're certainly HTML (a closing tag, `/>`, or a known tag name), so `<path>` and `Vec<String>` stay; `<br>`, `<p>`, `<summary>` and friends become sentence breaks. Then entities are unescaped. ANSI codes, emoji (Unicode "other symbols", except `°©®™`), skin tones and joiners, autolinks and footnote markers are removed. All of this skips `inline code`.

### 5c. Config and replacement features

- **Backreferences in `/regex/` rules:** let `\1` work in the replacement, so word order can be fixed in config: `/\$(\d[\d,.]*)/ => \1 dollars` for `Costs $5` (now "Costs $five"). Without this, currency needs code.
- **Rule order:** CareyScott applies overrides longest first, so `fancyapp-web` wins over `fancyapp`. Ours applies them in list order, which is predictable and lets you put specific rules first. Keep it, and document it in the README.
- **New default replacements to consider:** `#` before a number → "number"; comparison operators; `*` before `.ext` → "star". Short TLDs said as letters (`io` → "i o", `co.uk`, CareyScott) only work after `speak_paths` has run, which replacements can't see. Leave them to users.

### 5d. Bigger ideas (decide, then do or drop)

- **Summary mode for long or code-heavy replies** (claude-spoken-briefs, opencode-voice): ask Haiku for a 2–4 sentence spoken brief instead of reading the reply. spoken-briefs routes cheaply: replies of 280 characters or less with no code fence, table or path are read as written; everything else is summarised. Prompt points worth keeping: at most 60 words, no Markdown, paths or IDs, name things by role ("the server file"), order "what was done, what needs you, open questions", "you" for the developer and "I" for the assistant. Costs latency and an API call per reply; an optional setting, off by default.
- **Paths as file name only** (CharlesAdewumi2004, opencode-voice): `~/.claude/hooks/speak-last-message.py` → "speak last message". A `speak_paths` value of `full` / `name` / `off` instead of a boolean.
- **camelCase splitting** (opencode-voice): `parseConfig` → "parse config". A `split_camel_case` setting, off by default, since Kokoro often copes.
- **Dropped:** a "🔊 Speaker:" summary line that Claude writes itself (antonyjaen); an "auto" mode that speaks only when the prompt looks dictated (CharlesAdewumi2004).
