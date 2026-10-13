"""to_speech: Markdown in, the exact text an engine is given out. Run with
uv run --no-project --with pytest pytest"""
from pathlib import Path

import pytest

from speak import DEFAULT_REPLACEMENTS, split_sentences, to_speech, truncate

# The two spelling settings on, as suits Pocket TTS on its own.
POCKET = {"spell_letter_digits": True, "spell_abbreviations": True}

SAMPLE = (Path(__file__).parent / "sample.md").read_text()


def test_sample_default():
    assert to_speech(SAMPLE) == (
        "I read your rules in home slash dot claude slash settings dot json (Kokoro profile, with debug "
        "underscore log underscore text on). The daemon is up; stop gets called. Startup takes about three "
        "point seven seconds, first audio in zero point three seconds. Files: home slash dev slash claude "
        "dash speaks slash daemon dot py, home slash dot config slash claude dash speaks slash config dot "
        "json, and home alone. Plugin at home slash dot claude slash plugins slash cache slash aeriondyseti "
        "dash plugins slash speaks slash zero dot three dot two slash, so vee zero point three point two. "
        "Commit hash ending with two bee three see and 3cb8f78. The RTX fifty sixty tee eye has eight "
        "gigabytes of VRAM; nine to twelve sentences keep p99 under four hundred milliseconds at minus five "
        "decibels. Use x86 db cfg HTML TTY. See src slash components slash App dot tsx and README dot md, "
        "max underscore chars too. one million two hundred thirty four thousand five hundred sixty seven "
        "items, two times faster, forty five percent. Bold item with a link and a link. Code block omitted."
    )


def test_sample_pocket_with_word_rules():
    """The two spelling settings plus a few replacements reproduce 0.3's Pocket profile."""
    cfg = {**POCKET, "replacements": DEFAULT_REPLACEMENTS + [
        "py => pie", "json => jay sohn", "tsx => tee ess ex", "md => markdown", "src => source", "vram => vee ram"]}
    out = to_speech(SAMPLE, cfg)
    for spoken in ("daemon dot pie", "settings dot jay sohn", "The ar tee ex fifty sixty", "of vee ram",
                   "keep pee ninety nine", "Use ex eighty six dee bee see eff gee aitch tee em el tee tee why",
                   "See source slash components slash App dot tee ess ex and README dot markdown"):
        assert spoken in out


@pytest.mark.parametrize("md,spoken", [
    ("Edit `daemon.py` now.", "Edit daemon dot py now."),
    ("See ~/dev/x/y.txt and $HOME alone.", "See home slash dev slash x slash y dot txt and home alone."),
    ("Commit 77522be1a2b3c landed.", "Commit hash ending with two bee three see landed."),
    ("Set debug_log_text and MAX_CHARS.", "Set debug underscore log underscore text and max underscore chars."),
    ("Upgrade to v0.3.2 or 1.2.3.", "Upgrade to vee zero point three point two or one point two point three."),
    ("It takes ~3.7s and 9–12 runs.", "It takes about three point seven seconds and nine to twelve runs."),
    ("8 GB, 400 ms, -5 dB, 2x, 45%, 1,234,567.",
     "eight gigabytes, four hundred milliseconds, minus five decibels, two times, forty five percent, "
     "one million two hundred thirty four thousand five hundred sixty seven."),
    ("In 2026 the 5060 Ti shipped.", "In twenty twenty six the fifty sixty tee eye shipped."),
    ("Call stop() then run.", "Call stop then run."),
    ("## Heading\n\n- item one\n- item two\n\n> quoted", "Heading. item one. item two. quoted."),
    ("**bold**, *italic*, ~~gone~~, _under_.", "bold, italic, gone, under."),
    ("See [the docs](https://x.y) or https://example.com/a", "See the docs or a link."),
    ("Before.\n```py\nprint(1)\n```\nAfter.", "Before. Code block omitted. After."),
    ("Use p99 on x86 with db and TTY.", "Use p99 on x86 with db and TTY."),
])
def test_default(md, spoken):
    assert to_speech(md) == spoken


def test_pocket_spelling():
    assert to_speech("Use p99 on x86 with db and TTY.", POCKET) == \
        "Use pee ninety nine on ex eighty six with dee bee and tee tee why."


@pytest.mark.parametrize("setting,md,spoken", [
    ("speak_hashes", "Commit 77522be1a2b3c.", "Commit 77522be1a2b3c."),
    ("speak_paths", "See a/b/c.py now.", "See a/b/c.py now."),
    ("speak_snake_case", "Set debug_log_text.", "Set debug_log_text."),
    ("speak_versions", "On v1.2.3 now.", "On v1.2.3 now."),
    ("speak_numbers", "Got 8 GB.", "Got 8 GB."),
])
def test_each_rule_can_be_turned_off(setting, md, spoken):
    assert to_speech(md, {setting: False}) == spoken


@pytest.mark.parametrize("value", [False, "false", "off", "0", "no"])
def test_settings_accept_strings(value):
    assert to_speech("Got 8 GB.", {"speak_numbers": value}) == "Got 8 GB."


@pytest.mark.parametrize("rules,md,spoken", [
    (["daemon => daymen"], "The daemon and daemon.py and Daemon.", "The daymen and daymen dot py and daymen."),
    (["daemon => daymen"], "Keep daemon_pid and daemon-mode.", "Keep daemon underscore pid and daemon-mode."),
    (["Ti => tee eye"], "TI and Ti.", "TI and tee eye."),  # written with capitals: exact case only
    (["/(?<=\\d)x(?=\\d)/ => by"], "A 4x4 grid.", "A four by four grid."),
    (["/[/ => x", "no arrow", " => empty find"], "Left alone.", "Left alone."),  # bad rules are skipped
])
def test_replacements(rules, md, spoken):
    assert to_speech(md, {"replacements": rules}) == spoken


def test_no_replacements_at_all():
    assert to_speech("See ~/a/b.py", {"replacements": []}) == "See ~ slash a slash b dot py."


@pytest.mark.parametrize("text,sentences", [
    ("One. Two! Three?", ["One.", "Two!", "Three?"]),
    ("x. ... and more on screen.", ["x.", "... and more on screen."]),  # Kokoro gives "..." no audio
    ("Hi. ...", ["Hi. ..."]),
    ("...", ["..."]),
])
def test_split_sentences(text, sentences):
    assert split_sentences(text) == sentences


@pytest.mark.parametrize("text,limit,out", [
    ("Short.", 600, "Short."),
    ("A" * 10 + ". " + "B" * 30 + ".", 25, "A" * 10 + ". ... and more on screen."),
    ("A" * 50, 0, "A" * 50),
])
def test_truncate(text, limit, out):
    assert truncate(text, limit) == out


def test_plugin_defaults_match_speak_py():
    import json
    manifest = json.loads((Path(__file__).parent.parent / ".claude-plugin/plugin.json").read_text())
    assert manifest["userConfig"]["replacements"]["default"] == DEFAULT_REPLACEMENTS


# Markdown structure is removed before any rule sees it (from berga-a/claude-speak's suite).
@pytest.mark.parametrize("md,spoken", [
    ("1. first\n2. second", "first. second."),
    ("1) first\n2) second", "first. second."),
    ("***Both*** here.", "Both here."),
    ("___Totally___ here.", "Totally here."),
    ("**a *nested* one** here.", "a nested one here."),
    ("**Bold spanning\ntwo lines** here.", "Bold spanning. two lines here."),
    ("**Bold with * star** inside.", "Bold with times star inside."),  # a spaced * between words is multiplication
    ("A **bold** and **another** on one line.", "A bold and another on one line."),
    ("Math 2 * 3 stays.", "Math two times three stays."),
    ("Before.\n\n* * *\n\nAfter.", "Before. After."),
    ("Before.\n\n- - -\n\nAfter.", "Before. After."),
    ("Before.\n\n___\n\nAfter.", "Before. After."),
    ("Glob `*.py` and a footnote*", "Glob star dot py and a footnote."),
    ("Run `ls *.test.ts` here.", "Run ls star dot test dot ts here."),
    ("Use `*.{js,ts}` globs.", "Use star dot {js,ts} globs."),
    ("Keep `a_b_c` and `x * y`.", "Keep a underscore bee underscore see and x times y."),
    ("x**2 + y**2", "x to the power of two + y to the power of two."),
    ("x ** 2 and 2*3 and (a + b) * c", "x to the power of two and two times three and (ey + b) times c."),
    ("cost = a *** b", "cost = ey b."),
    ("**bold***italic*", "bold italic."),
    ("see ***** here", "see here."),
    (">= 3 holds", "greater than or equal to three holds."),
    ("> quoted >= 3", "quoted greater than or equal to three."),
    ("A snake_case_word and _emphasis_.", "A snake underscore case underscore word and emphasis."),
])
def test_markdown(md, spoken):
    assert to_speech(md) == spoken


@pytest.mark.parametrize("text,sentences", [
    ("Mr. Smith arrived. He sat.", ["Mr. Smith arrived.", "He sat."]),
    ("Use a flag, e.g. this one. Done.", ["Use a flag, e.g. this one.", "Done."]),
    ("Tabs vs. spaces, i.e. war. Next.", ["Tabs vs. spaces, i.e. war.", "Next."]),
    ("Is it? No. Then go.", ["Is it?", "No.", "Then go."]),
])
def test_split_sentences_keeps_abbreviations(text, sentences):
    assert split_sentences(text) == sentences


def test_long_first_sentence_is_sent_in_clauses():
    first = ("I read your rules in the settings file, with the debug log on, and here is a passage "
             "that hits each one; it covers paths, numbers and hashes, plus some edge cases.")
    later = ("This second sentence is long as well, with several commas in it, but it is fetched "
             "while the first one plays, so it stays whole.")
    parts = split_sentences(f"{first} {later}")
    assert parts[-1] == later
    assert len(parts) > 2 and all(len(p) <= 100 for p in parts[:-1])
    assert " ".join(parts[:-1]) == first
    assert all(p.rstrip().endswith((",", ";")) for p in parts[:-2])  # split at clause ends only


def test_long_first_sentence_without_clauses_stays_whole():
    first = "A" * 150 + "."
    assert split_sentences(first + " Next.") == [first, "Next."]


# From the survey of other readers (plan section 5a/5c).
@pytest.mark.parametrize("md,spoken", [
    ("Saved to /tmp/out.txt.", "Saved to slash tmp slash out dot txt."),
    ("Look in /tmp.", "Look in slash tmp."),
    ("See ~/dev/x.", "See home slash dev slash x."),
    ("Visit https://x.com, then go.", "Visit a link, then go."),
    ("Docs (see https://x.com/a).", "Docs (see a link)."),
    ("Edit the .env file and .gitignore.", "Edit the dot env file and dot gitignore."),
    ("Check x != y now.", "Check x not equal to y now."),
    ("Contact kevin@example.com today.", "Contact kevin at example dot com today."),
    ("Mail first_last@example.com.", "Mail first underscore last at example dot com."),
    ("#1 priority", "number one priority."),
    ("Fixed in PR #45.", "Fixed in PR number forty five."),
    ("- [x] write tests\n- [ ] ship it", "done, write tests. to do, ship it."),
    ("Setext\n======\nbody", "Setext. body."),
    ("Other\n------\nbody", "Other. body."),
    ("# Title #", "Title."),
    ("a >= 3 and b <= 4 and c == 5", "ey greater than or equal to three and b less than or equal to four and c equals five."),
    ("Call `__init__` or __dunder_method__ here.", "Call dunder init or dunder dunder underscore method here."),
    ("See helpers.ts:42 now.", "See helpers dot ts, line forty two now."),
    ("See src/app.py:10:4 now.", "See src slash app dot py, line ten now."),
    ("Meet at 10:30 or 9:05 or 14:00.", "Meet at ten thirty or nine oh five or fourteen hundred."),
    ("At 7:00 pm, then 11:15am, or 10:00.", "At seven p m, then eleven fifteen a m, or ten o'clock."),
    ("A 3:1 ratio, 16:9 screens, 25:00 is no time.", "A three to one ratio, sixteen to nine screens, twenty five to zero is no time."),
    ("Run make.Then test.", "Run make. Then test."),
    ("Use Node.js and 3.14 and `java.lang.String`.", "Use Node dot js and three point one four and java dot lang dot String."),
    ("id 123e4567-e89b-12d3-a456-426614174000 ok", "id hash ending with four zero zero zero ok."),
    ("Costs $5 and $1,200.", "Costs five dollars and one thousand two hundred dollars."),
])
def test_survey(md, spoken):
    assert to_speech(md) == spoken


@pytest.mark.parametrize("rules,md,spoken", [
    (["/(\\w+)@(\\w+)/ => \\2 from \\1"], "x a@b y", "x b from a y"),  # backreferences
    (["/(?<=\\d)x(?=\\d)/ => by"], "4x4", "four by four."),  # padded only where it would glue on
    (["/:(?=\\d)/ => , line "], "fx.py:3", "fx dot py, line three."),
])
def test_regex_replacements(rules, md, spoken):
    assert to_speech(md, {"replacements": rules}).rstrip(".") == spoken.rstrip(".")


# Markup other readers clean up (plan section 5b).
@pytest.mark.parametrize("md,spoken", [
    ("Before.\n\n| Setting | Default |\n|---|:---:|\n| `max_chars` | 600 |\n| volume | 6 dB |\n\nAfter.",
     "Before. Setting, Default. max underscore chars, six hundred. volume, six decibels. After."),
    ("| a | b |\n| - | - |\n| 1 |  |", "a, b. one."),  # empty cells skipped
    ("| x \\| y | z |", "x | y, z."),  # an escaped pipe is content
    ("Use <kbd>Ctrl</kbd>+<kbd>C</kbd> to stop.", "Use Ctrl+C to stop."),
    ("Line one<br>Line two", "Line one. Line two."),
    ("<details><summary>More</summary>Hidden text</details>", "More. Hidden text."),
    ("Keep Vec<String> and a < b and `<path>` here.", "Keep Vec<String> and ey < b and <path> here."),
    ("AT&amp;T and a &lt; b", "AT&T and ey < b."),
    ("\x1b[31mError\x1b[0m happened", "Error happened."),
    ("Done ✅ 🎉 all good ⚠️ and 👍🏽 too", "Done all good and too."),
    ("It was 25°C.", "It was twenty five°C."),  # ° is a symbol worth keeping
    ("Link: <https://example.com>.", "Link: a link."),
    ("Footnote[^1] here.\n\n[^1]: The note.", "Footnote here. The note."),
])
def test_markup(md, spoken):
    assert to_speech(md) == spoken


@pytest.mark.parametrize("md,spoken", [
    ("If a >= b then x + a.", "If ey greater than or equal to b then x + ey."),
    ("Use `a` and `b`, or a*b and a ** 2.", "Use ey and b, or ey times b and ey to the power of two."),
    ("A + B and a != b and x = a.", "ey + B and ey not equal to b and x = ey."),
    ("A long sentence with a few words, a lot.", "A long sentence with a few words, a lot."),
    ("Wow! a thing (a note) - a dash, 50% a day.", "Wow! a thing (a note) - a dash, fifty percent ey day."),
])
def test_letter_a(md, spoken):
    assert to_speech(md) == spoken
