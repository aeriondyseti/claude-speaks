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
    ("**Bold with * star** inside.", "Bold with star inside."),
    ("A **bold** and **another** on one line.", "A bold and another on one line."),
    ("Math 2 * 3 stays.", "Math two times three stays."),
    ("Before.\n\n* * *\n\nAfter.", "Before. After."),
    ("Before.\n\n- - -\n\nAfter.", "Before. After."),
    ("Before.\n\n___\n\nAfter.", "Before. After."),
    ("Glob `*.py` and a footnote*", "Glob star dot py and a footnote."),
    ("Run `ls *.test.ts` here.", "Run ls star dot test dot ts here."),
    ("Keep `a_b_c` and `x * y`.", "Keep a underscore bee underscore see and x y."),
    ("x**2 + y**2", "x two + y two."),
    ("cost = a *** b", "cost = a b."),
    ("**bold***italic*", "bold italic."),
    ("see ***** here", "see here."),
    (">= 3 holds", ">= three holds."),
    ("> quoted >= 3", "quoted >= three."),
    ("A snake_case_word and _emphasis_.", "A snake underscore case underscore word and emphasis."),
])
def test_markdown(md, spoken):
    assert to_speech(md) == spoken
