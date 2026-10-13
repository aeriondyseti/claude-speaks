#!/usr/bin/env -S uv run --no-project --quiet
"""Claude Code Stop hook: read Claude's last reply aloud (WSL).

Engines: "pocket" (default) sends text to daemon.py, which keeps a Pocket TTS
model loaded and is started on demand; "sapi" uses the Windows voices.

As a settings Stop hook, input arrives as JSON on stdin; the plugin passes
`--stdin-text` with the reply itself. The reply text comes from
`last_assistant_message` when present, otherwise from the transcript.

Env:
  CLAUDE_SPEAKS_MAX_CHARS  truncate spoken text (default 600, 0 = no limit)
  CLAUDE_SPEAKS_ENGINE     pocket | sapi
  CLAUDE_SPEAKS_POCKET_VOICE  Pocket TTS voice (default alba; read by the daemon)
  CLAUDE_SPEAKS_VOICE      SAPI voice name, e.g. "Microsoft Zira Desktop"
  CLAUDE_SPEAKS_RATE       -10..10 (default 1)
"""
import hashlib
import html
import json
import os
import re
import signal
import socket
import subprocess
import sys
import time
import unicodedata
from pathlib import Path

STATE_DIR = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / "claude-speaks"
MUTE_FILE = STATE_DIR / "muted"
PID_FILE = STATE_DIR / "speaker.pid"
SOCKET = STATE_DIR / "daemon.sock"
STARTING = STATE_DIR / "daemon.starting"
RETIRING = STATE_DIR / "daemon.retiring"  # pid of a replaced daemon finishing its last reply
HERE = Path(__file__).resolve().parent
PS1 = HERE / "say.ps1"
# Kept outside the plugin folder so plugin updates don't throw away the ~1 GB install.
VENV = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "claude-speaks/venv"
UV_ENV = {**os.environ, "UV_PROJECT_ENVIRONMENT": str(VENV)}


def code_fingerprint(root=HERE):
    """Short hash of this copy's speak.py and daemon.py: a daemon started from other code (an
    older plugin version, or files edited since) answers a different one and gets replaced."""
    digest = hashlib.sha256()
    for name in ("speak.py", "daemon.py"):
        digest.update((root / name).read_bytes())
    return digest.hexdigest()[:12]


def plugin_version(root=HERE):
    try:
        return json.loads((root / ".claude-plugin/plugin.json").read_text())["version"]
    except (OSError, ValueError, KeyError):
        return ""


def version_key(version):
    """Sortable plugin version. Releases up to 0.5.2 used three parts; from 0.1.5.2 on, versions
    are 0.MAJOR.MINOR.PATCH, so any four-part version is newer than any three-part one."""
    parts = tuple(int(n) for n in re.findall(r"\d+", version or ""))
    return (len(parts) >= 4, parts)


def installed():
    """True once uv has finished installing (it creates the venv folder before that)."""
    return any(VENV.glob("lib/python*/site-packages/pocket_tts"))


def last_reply_from_transcript(path):
    # The transcript may lag the Stop event slightly; retry briefly.
    for _ in range(5):
        try:
            lines = Path(path).read_text(encoding="utf-8").splitlines()
        except OSError:
            return ""
        for line in reversed(lines):
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if entry.get("type") == "user" and not _is_tool_result(entry):
                break  # reached the prompt without finding text yet
            if entry.get("type") != "assistant":
                continue
            content = entry.get("message", {}).get("content", [])
            texts = [c.get("text", "") for c in content if isinstance(c, dict) and c.get("type") == "text"]
            if any(t.strip() for t in texts):
                return "\n".join(texts)
        time.sleep(0.2)
    return ""


def _is_tool_result(entry):
    content = entry.get("message", {}).get("content")
    return isinstance(content, list) and any(
        isinstance(c, dict) and c.get("type") == "tool_result" for c in content
    )


HEX_HASH = re.compile(r"\b(?=[0-9a-f]*\d)(?=[0-9a-f]*[a-f])[0-9a-f]{12,}\b", re.I)
UUID = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I)
SEPARATORS = {"/": " slash ", ".": " dot ", "-": " dash ", "_": " underscore "}
# Anchored paths (~/, $HOME/, /, ./, ../) or relative ones with 2+ slashes or a file extension.
PATH = re.compile(
    r"(?<![\w/])(?:(?:~|\$HOME|\.{1,2})?(?:/[\w.@+-]+)+/?(?<!\.)"
    r"|[\w@+-][\w.@+-]*(?:/[\w.@+-]+){2,}/?(?<!\.)"
    r"|[\w@+-][\w.@+-]*(?:/[\w.@+-]+)*/[\w@+-]+\.[A-Za-z]\w*"
    r"|(?<!\w)[\w-]{2,}(?:\.[\w-]+)*\.[A-Za-z][A-Za-z0-9]+\b"  # bare file.ext
    r"|(?<![\w./])\.[A-Za-z][\w-]*(?:\.[A-Za-z][\w-]*)*\b)"  # dotfile: .env, .env.local
)


def spell(chars):
    return " ".join(LETTERS.get(c.lower(), c) for c in chars)


def parse_replacements(lines):
    rules = []
    for line in lines:
        find, sep, repl = line.partition("=>")
        find, repl = find.strip(), repl.strip()
        if not sep or not find:
            continue
        if len(find) > 2 and find.startswith("/") and find.endswith("/"):
            try:
                rules.append((re.compile(find[1:-1]), repl, True))
            except re.error:
                continue
        else:
            flags = re.I if find == find.lower() else 0
            rules.append((re.compile(r"(?<![\w-])" + re.escape(find) + r"(?![\w-])", flags), repl, False))
    return rules


def apply_replacements(text, lines):
    for pattern, repl, is_regex in parse_replacements(lines):
        if is_regex:
            text = pattern.sub(lambda m, r=repl: padded(m, m.expand(r)), text)
        else:  # a whole word keeps its neighbours as they are: daemon.py stays a file name
            text = pattern.sub(lambda m, r=repl: r, text)
    return text


def padded(m, out):
    """A regex replacement, kept apart from a neighbour it would otherwise glue onto: 9–12 ->
    "9 to 12", but helpers.ts:42 -> "helpers.ts, line 42" (no space before the comma)."""
    text, found = m.string, m[0]
    # A space where the match ate one, or where the neighbour would run on; not "( ey" or "ey *b".
    before = m.start() > 0 and (found[:1].isspace() or text[m.start() - 1].isalnum() or text[m.start() - 1] in "/_)]}")
    after = m.end() < len(text) and (found[-1:].isspace() or text[m.end()].isalnum() or text[m.end()] in "/_([{")
    if out and out[0].isalnum() and before:
        out = " " + out
    if out and out[-1].isalnum() and after:
        out += " "
    return out


def speak_identifier(m):
    """snake_case -> words joined by "underscore"; vowelless bits like db/sm are spelled out."""
    parts = m.group().split("_")
    return " underscore ".join(
        spell(p) if len(p) <= 4 and p.isalpha() and not re.search(r"[aeiouy]", p, re.I)
        else p.lower() if p.isupper() else p  # MAX_CHARS: words, not letters (Kokoro spells all caps)
        for p in parts
    )


def speak_hash(m):
    return "hash ending with " + spell(m.group()[-4:])


def speak_path(m, hashes=True):
    path = m.group()
    if hashes:
        path = UUID.sub(lambda h: f"\0{speak_hash(h)}\0", path)
        path = HEX_HASH.sub(lambda h: f"\0{speak_hash(h)}\0", path)  # protect from separator words
    parts = re.split(r"(\0[^\0]*\0)", path)
    out = "".join(
        part.strip("\0") if part.startswith("\0") else re.sub(r"[/._-]", lambda c: SEPARATORS[c.group()], part)
        for part in parts
    )
    return " " + re.sub(r"\s+", " ", out).strip() + " "


# "oh", not "zero": v0.3 is "vee oh dot three". A decimal says "zero" and "point": 0.05 is
# "zero point zero five". Versions say "dot".
ONES = "oh one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen".split()
TENS = "_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()
SCALES = [(10**12, "trillion"), (10**9, "billion"), (10**6, "million"), (1000, "thousand"), (100, "hundred")]
UNITS = {"GB": "gigabytes", "GiB": "gigabytes", "MB": "megabytes", "MiB": "megabytes", "KB": "kilobytes",
         "TB": "terabytes", "ms": "milliseconds", "s": "seconds", "GHz": "gigahertz", "MHz": "megahertz",
         "Hz": "hertz", "kHz": "kilohertz", "dB": "decibels", "%": "percent"}
# Spellings checked against Kokoro's phonemizer (/dev/phonemize): "ay" and "ey" both come out "eye".
LETTERS = dict(zip("abcdefghijklmnopqrstuvwxyz", (
    "eigh bee see dee ee eff gee aitch eye jay kay el em en oh pee cue ar ess tee you vee "
    "double-you ex why zee").split()))
# User-editable "find => replace" rules, applied first (once Markdown structure is gone). A plain word matches whole
# words (any case when written in lowercase); /regex/ is a pattern. Every word-level fix lives here,
# never in code; these defaults are the light set that suits Kokoro.
DEFAULT_REPLACEMENTS = [
    "Ti => tee eye",
    # The letter a, not the article: alone in `code`, or beside a math operator (a >= b, x + a)
    r"/(?<![\w'])(?:(?<=`)[aA](?=`)|[aA](?=\s?(?:[<>=+*%^]|!=))|(?:(?<=[<>=+*%^])|(?<=[<>=+*%^]\s))[aA])(?![\w'])/ => eigh",
    r"/(?<![\w/])(?:~|\$HOME)(?=/)/ => home",
    r"/\$HOME\b/ => home",
    r"/~(?=\d)/ => about",
    r"/(?<=\d)\s?[–—-]\s?(?=\d)/ => to",
    r"/(?<=\w)\(\)/ => ",
    r"/(?<=[\w)])(?:\*\*|\s+\*\*\s+)(?=[\w(])/ => to the power of",
    r"/(?<=[\w)])(?:\*|\s+\*\s+)(?=[\w(])/ => times",
    r"/(?<![\w*])\*\.(?=[\w{])/ => star dot",
    r"/(\.[A-Za-z]\w*):(\d+)(?::\d+)?\b/ => \1, line \2",
    r"/(?<![\d:])(?!(?:[01]?\d|2[0-3]):[0-5]\d(?!\d))(\d+):(\d+)(?![\d:])/ => \1 to \2",
    r"/(?<=\w)@(?=[\w-]+\.[A-Za-z])/ => at",
    r"/(?<![\w&])#(?=\d)/ => number",
    r"/\$(?=\d)([\d,]*\d(?:\.\d+)?)/ => \1 dollars",
    ">= => greater than or equal to",
    "<= => less than or equal to",
    "!= => not equal to",
    "== => equals",
    r"/__(\w+?)__/ => dunder \1",
    r"/(?m)^\[[xX]\]/ => done,",
    r"/(?m)^\[ \]/ => to do,",
]
# The rules that need code rather than a find-and-replace, each a setting of its own (default shown).
TEXT_RULES = {
    "speak_hashes": True,         # 77522be1a2b3c, UUIDs -> "hash ending with two bee three see"
    "speak_paths": True,          # ~/dev/a.py -> "slash dev slash a dot py"
    "speak_snake_case": True,     # debug_log_text -> "debug underscore log underscore text"
    "speak_versions": True,       # v0.3.2 -> "vee oh dot three dot two"
    "speak_numbers": True,        # 1,234 / 8 GB / -5 dB / 2x -> words
    "spell_letter_digits": False, # p99, x86 -> "pee 99", "ex 86"
    "spell_abbreviations": False, # vowelless db, cfg, RTX, TTY -> "dee bee", ...
}
UNIT_RE = r"%|[KMGT]i?B|ms|s|[kMG]?Hz|dB"
NUMBER = re.compile(
    r"(?<![\w.])(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d+))?"
    rf"(?:\s?([×x])(?!\w)|\s?({UNIT_RE})(?!\w)|(?![\w.]*[A-Za-z_]))"  # skip ids like sm_120, 4B
)
VERSION = re.compile(r"(?<![\w.])(v?)(\d+(?:\.\d+){2,}|(?<=v)\d+\.\d+)(?![\d.]*\d)")


def int_words(n):
    if n < 20:
        return ONES[n]
    if n < 100:
        return TENS[n // 10] + ("" if n % 10 == 0 else " " + ONES[n % 10])
    for value, name in SCALES:
        if n >= value:
            rest = n % value
            return f"{int_words(n // value)} {name}" + (f" {int_words(rest)}" if rest else "")


def say_whole(digits):
    n = int(digits.replace(",", ""))
    # Four-digit model numbers and years read in pairs: 5060 -> fifty sixty, 2026 -> twenty twenty six
    if len(digits) == 4 and n % 1000 >= 10 and n % 100 != 0:
        low = n % 100
        return f"{int_words(n // 100)} {'oh ' if low < 10 else ''}{int_words(low)}"
    return int_words(n)


def speak_version(m):
    return ("vee " if m.group(1) else "") + " dot ".join(int_words(int(p)) for p in m.group(2).split("."))


# A clock time (other number:number pairs are ratios, a default replacement): 9:05, 14:00, 7:30 pm
TIME = re.compile(r"(?<![\w:.])([01]?\d|2[0-3]):([0-5]\d)(?::([0-5]\d))?(?:\s?([AaPp])(?:\.[Mm]\.|[Mm])(?!\w))?(?![\w:])")


def speak_time(m):
    hour, minute, second, half = int(m[1]), int(m[2]), m[3], m[4]
    words = int_words(hour)
    if minute:
        words += f" {'oh ' if minute < 10 else ''}{int_words(minute)}"
    elif not half:
        words += " hundred" if hour > 12 or len(m[1]) == 2 and hour < 10 else " o'clock"
    if second:
        words += f" and {int_words(int(second))} seconds"
    if half:
        words += " " + spell(half + "m")  # "a m" would be read as the article
    return words


def speak_number(m):
    whole, frac, times, unit = m.groups()
    words = say_whole(whole)
    if frac:  # a decimal says "zero" (0.5, 2.05); everything else says "oh"
        digit = lambda d: "zero" if d == "0" else ONES[int(d)]  # noqa: E731
        words = ("zero" if whole == "0" else words) + " point " + " ".join(digit(d) for d in frac)
    if times:
        words += " times"
    elif unit:
        words += " " + UNITS[unit]
    return words


def text_rule(cfg, name):
    value = cfg.get(name, TEXT_RULES[name])
    return value.lower() not in ("false", "0", "off", "no") if isinstance(value, str) else bool(value)


# Emphasis never starts or ends inside a word (snake_case, x**2), in runs of one to three.
EMPHASIS = [re.compile(r"(?<![\w*])(\*{1,3}|~~)(?=[^\s*])(.+?)(?<=[^\s*])\1(?![\w*])"),
            # not a dunder: __init__ is a name, not bold "init"
            re.compile(r"(?<![\w_])(_{1,3})(?!(?<=(?<!_)__)[A-Za-z0-9]\w*?(?<!_)__(?![\w_]))(?=[^\s_])(.+?)(?<=[^\s_])\1(?![\w_])")]


def outside_code(text, fn):
    """Apply fn to the text outside `inline code`, which is spoken as written."""
    parts = re.split(r"(`[^`\n]*`)", text)
    return "".join(p if i % 2 else fn(p) for i, p in enumerate(parts))


def strip_emphasis(text):
    for _ in range(3):  # nested: **a *b* c**
        before = text
        for pattern in EMPHASIS:
            text = pattern.sub(r"\2", text)
        if text == before:
            break
    return text


# Unicode "other symbols" are emoji, dingbats and box drawing; a few are worth saying.
KEEP_SYMBOLS = set("°©®™")


def is_emoji(c):
    return (unicodedata.category(c) == "So" and c not in KEEP_SYMBOLS
            or "\ufe00" <= c <= "\ufe0f" or c == "\u200d" or "\U0001f3fb" <= c <= "\U0001f3ff")


def table_row(line):
    """| a | b | -> "a, b.": each cell a pause, each row a sentence; the |---| row goes."""
    cells = [c.strip().replace("\\|", "|") for c in re.split(r"(?<!\\)\|", line.strip().strip("|"))]
    if all(re.fullmatch(r":?-+:?", c) for c in cells if c):
        return ""
    return ", ".join(c for c in cells if c) + "."


# HTML that turns up in replies. Opening tags only when they're certainly HTML, so a placeholder
# like <path> or a type like Vec<String> survives.
HTML_BREAK = "br|p|div|li|ul|ol|details|summary|hr|tr|table|h[1-6]"
HTML_INLINE = "kbd|code|b|i|em|strong|span|sup|sub|u|s|mark|small|a|img|wbr|td|th"


def strip_tags(text):
    closed = {m.lower() for m in re.findall(r"</([A-Za-z][\w-]*)\s*>", text)}
    def tag(m):
        name = m[2].lower()
        if not (m[1] or m[0].endswith("/>") or name in closed
                or re.fullmatch(f"{HTML_BREAK}|{HTML_INLINE}", name)):
            return m[0]
        return "\n" if re.fullmatch(HTML_BREAK, name) else ""
    return re.sub(r"<(/?)([A-Za-z][\w-]*)(?:\s[^<>]*)?/?>", tag, text)


def strip_markup(md):
    """Markdown structure out, first, so no rule mistakes it for content ("1. first" is not a number)."""
    text = re.sub(r"\x1b\[[0-9;?]*[ -/]*[@-~]", "", md)  # ANSI colours
    text = "".join(c for c in text if not is_emoji(c))
    text = re.sub(r"```.*?(```|$)", "\nCode block omitted.\n", text, flags=re.S)
    text = "\n".join(table_row(l) if l.lstrip().startswith("|") else l for l in text.splitlines())
    text = re.sub(r"^[ \t]*([-*_])(?:[ \t]*\1){2,}[ \t]*$", "", text, flags=re.M)  # rules: ---, * * *
    text = re.sub(r"^[ \t]*=+[ \t]*$", "", text, flags=re.M)  # setext underline (---- went with the rules)
    text = re.sub(r"^\s{0,3}#{1,6}(?:[ \t]+(.*?)(?:[ \t]+#+)?[ \t]*|[ \t]*)$", r"\1", text, flags=re.M)  # headings; #1 isn't one
    text = re.sub(r"^\s*([-*+]|\d+[.)])\s+", "", text, flags=re.M)  # list markers
    text = re.sub(r"^\s*>(?!=)\s?", "", text, flags=re.M)  # quotes, not >=
    text = re.sub(r"(?m)^\[\^[^\]]+\]:\s*", "", text)  # footnote: its text stays
    text = re.sub(r"\[\^[^\]]+\]", "", text)  # footnote reference
    text = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", text)  # links/images -> label
    text = re.sub(r"<(?:https?|mailto):[^>\s]+>", "a link", text)  # autolinks
    text = re.sub(r"https?://[^\s)]*[^\s).,!?;:]", "a link", text)  # not the punctuation after it
    text = outside_code(text, strip_tags)
    text = outside_code(text, lambda t: re.sub(r"(?<=[a-z])\.(?=[A-Z][a-z])", ". ", t))  # now.Then: a sentence
    text = outside_code(text, html.unescape)  # after tags: &lt;b&gt; is text, not a tag
    return outside_code(text, strip_emphasis)


def to_speech(md, cfg=None):
    """Markdown -> speakable text. Markdown structure goes first; everything after that comes
    from cfg: its `replacements` ("find => replace" lines, DEFAULT_REPLACEMENTS when unset),
    then each TEXT_RULES setting that is on."""
    cfg = cfg or {}
    on = lambda name: text_rule(cfg, name)  # noqa: E731
    text = strip_markup(md)
    if on("speak_hashes"):  # before replacements, whose 9–12 rule would split it at its dashes
        text = UUID.sub(speak_hash, text)
    text = apply_replacements(text, cfg.get("replacements", DEFAULT_REPLACEMENTS))
    if on("speak_hashes"):
        text = HEX_HASH.sub(speak_hash, text)
    if on("speak_paths"):
        text = PATH.sub(lambda m: speak_path(m, on("speak_hashes")), text)
    if on("speak_snake_case"):
        text = re.sub(r"\b[A-Za-z0-9]+(?:_[A-Za-z0-9]+)+\b", speak_identifier, text)
    if on("speak_versions"):
        text = VERSION.sub(speak_version, text)
    if on("spell_letter_digits"):
        text = re.sub(r"\b([A-Za-z])(\d+)\b", lambda m: f"{LETTERS[m[1].lower()]} {m[2]}", text)
    if on("speak_numbers"):
        text = re.sub(r"(?<![\w.-])-(?=\d)", "minus ", text)
        text = TIME.sub(speak_time, text)
        text = NUMBER.sub(speak_number, text)
    if on("spell_abbreviations"):
        # Vowelless 2-5 letter words, and all-caps ones whose only vowel is Y (TTY, NYC)
        text = re.sub(r"(?<![\w-])[b-df-hj-np-tv-xzB-DF-HJ-NP-TV-XZ]{2,5}(?![\w-])", lambda m: spell(m[0]), text)
        text = re.sub(r"(?<![\w-])(?=[A-Z]*Y)[B-DF-HJ-NP-TV-Z]{2,5}(?![\w-])", lambda m: spell(m[0]), text)
    text = re.sub(r"`([^`]*)`", r"\1", text)
    # A star still here is markup the emphasis rules couldn't pair (or bold across a line
    # break), never something to say: drop it, keeping words it sat between apart.
    text = re.sub(r"(?<=\w)\*+(?=\w)", " ", text)
    text = text.replace("*", "")
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    text = " ".join(l if l[-1] in ".!?:;," else l + "." for l in lines)  # pause between lines
    text = re.sub(r"\s+([.,;:!?])(?=\s|$)", r"\1", text)  # padding left by speak_path; not .env or !=
    return re.sub(r"\s+", " ", text).strip()


def truncate(text, limit):
    if limit <= 0 or len(text) <= limit:
        return text
    cut = text[:limit]
    end = max(cut.rfind(". "), cut.rfind("? "), cut.rfind("! "))
    return (cut[: end + 1] if end > limit // 3 else cut) + " ... and more on screen."


# A period after these doesn't end a sentence ("Mr. Smith", "e.g. this"); splitting there would
# send each half as its own request and break the intonation.
NOT_SENTENCE_END = re.compile(r"(?:^|\s)(?:e\.g|i\.e|mr|mrs|ms|dr|vs|etc|cf|approx)\.$", re.I)
FIRST_CLAUSES = 100  # characters: a longer first sentence is sent in clause-sized pieces


def split_clauses(sentence, size=FIRST_CLAUSES):
    """Pieces of about `size` characters, split after , ; : or a dash; joined, they give back
    the sentence. Short sentences come back whole."""
    if len(sentence) <= size:
        return [sentence]
    pieces = []
    for clause in re.split(r"(?<=[,;:—–])\s+", sentence):
        if pieces and len(pieces[-1]) + 1 + len(clause) <= size:
            pieces[-1] += " " + clause
        else:
            pieces.append(clause)
    return pieces


def split_sentences(text):
    """Requests for the TTS server: one per sentence, so the first audio waits for one
    sentence's synthesis, and a long first sentence in clauses, so it waits for less."""
    parts = []
    for p in re.split(r"(?<=[.!?])\s+", text):
        # A wordless piece ("...") gets no audio from Kokoro, which reads as a failure; join it on
        if parts and (not re.search(r"\w", parts[-1]) or NOT_SENTENCE_END.search(parts[-1])):
            parts[-1] += " " + p
        elif p.strip():
            parts.append(p.strip())
    if len(parts) > 1 and not re.search(r"\w", parts[-1]):
        tail = parts.pop()
        parts[-1] += " " + tail
    if not parts:
        return [text]
    # Later sentences are fetched while earlier ones play, so only the first one's length is heard
    return [p for p in split_clauses(parts[0]) if p] + parts[1:]


def stop_current():
    try:
        pid = int(PID_FILE.read_text())
        os.killpg(pid, signal.SIGTERM)
    except (OSError, ValueError):
        pass
    PID_FILE.unlink(missing_ok=True)


def send_to_daemon(req, on_line=lambda line: print(line, flush=True)):
    """Send one request; hand each line the daemon writes back to on_line (for speech, status lines
    relayed to stdout, which the plugin toasts) until it closes the connection."""
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
        try:
            s.settimeout(2)
            s.connect(SOCKET.name)  # relative to STATE_DIR (main() moves there): AF_UNIX paths max out near 108
            s.sendall(json.dumps(req).encode("utf-8"))
            s.shutdown(socket.SHUT_WR)
        except OSError:
            return False
        try:  # sent: from here on a failure only means we stop relaying
            s.settimeout(180)  # a first Pocket load can take a while
            with s.makefile() as events:
                for line in events:
                    on_line(line.strip())
        except OSError:
            pass
        return True


# ${VAR} / ${VAR:-default} in settings, as in Claude Code's .mcp.json. Expanded by the daemon at
# the moment it builds a request; only the variables a setting names are sent with each reply.
ENV_REF = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}")
CONFIG = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "claude-speaks/config.json"


def referenced_env(options):
    try:
        config_text = CONFIG.read_text()
    except OSError:
        config_text = ""
    names = {m[1] for m in ENV_REF.finditer(json.dumps(options) + config_text)}
    return {n: os.environ[n] for n in names if n in os.environ}


def plugin_options():
    """The plugin's userConfig values, handed over by the hook in CLAUDE_SPEAKS_OPTIONS."""
    try:
        return json.loads(os.environ.get("CLAUDE_SPEAKS_OPTIONS", "{}"))
    except json.JSONDecodeError:
        return {}


def daemon_hello():
    """(fingerprint, plugin version) of the running daemon, None when none is running. A daemon
    from before 0.3.1 answers neither ("", ""); one from before 0.5.3, no version."""
    lines = []
    if not send_to_daemon({"cmd": "hello"}, lines.append):
        return None
    words = next((l.split()[1:] for l in lines if l.startswith("daemon ")), [])
    return (words + ["", ""])[0], (words + ["", ""])[1]


def daemon_fingerprint():
    hello = daemon_hello()
    return hello and hello[0]


def ensure_daemon(wait=True, when_idle=False):
    """Have a daemon from this copy's code running, replacing an older one. A newer daemon (another
    session updated first) is left alone: it serves this client too, and replacing it would start a
    tug-of-war that cuts speech off. With when_idle, the old daemon finishes what it's saying first;
    without, it stops at once (a reply is waiting, and a new reply interrupts anyway). With wait,
    block until the new one answers (minutes on the very first run, while uv installs)."""
    mine = code_fingerprint()
    hello = daemon_hello()
    if hello and hello[0] == mine:
        return True
    if hello:
        if version_key(hello[1]) > version_key(plugin_version()):
            return True
        # older, or the same version with other code (edited in development): replace it
        send_to_daemon({"cmd": "shutdown", "when_idle": when_idle}, lambda line: None)
        deadline = time.time() + 5
        while SOCKET.exists() and time.time() < deadline:
            time.sleep(0.1)
        STARTING.unlink(missing_ok=True)
    start_daemon()
    if not wait:
        return False
    installing = not installed()
    if installing:
        print("installing-pocket", flush=True)
    deadline = time.time() + (900 if installing else 45)
    while time.time() < deadline:
        time.sleep(0.5)
        if daemon_fingerprint() == mine:
            return True
    return False


def speak_pocket(reply):
    # The plugin doesn't wait on this process, and the request never touches disk or argv.
    options = plugin_options()
    if ensure_daemon():
        send_to_daemon({"text": reply, "options": options, "env": referenced_env(options)})


def open_private_log():
    """daemon.log, readable only by the user: with debug_log_text on it holds reply text."""
    path = STATE_DIR / "daemon.log"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    os.chmod(path, 0o600)  # tighten a log created before this
    return os.fdopen(fd, "ab")


def start_daemon(text=None):
    """`uv run` installs the dependencies itself on first use (~1 GB), so that start can take minutes."""
    window = 60 if installed() else 900
    if STARTING.exists() and time.time() - STARTING.stat().st_mtime < window:
        return  # already starting
    STARTING.touch()
    subprocess.Popen(
        ["uv", "run", "--quiet", "--frozen", "--project", str(HERE), "python", str(HERE / "daemon.py")]
        + (["--say", text] if text else []),
        env=UV_ENV, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
        stderr=open_private_log(), start_new_session=True,
    )


def warm():
    """Session start: have a current daemon up (installing on first use) before the first reply.
    Pocket TTS itself loads only when a reply needs it."""
    ensure_daemon(wait=False, when_idle=True)  # don't cut off another session's reply


def max_chars():
    return int(os.environ.get("CLAUDE_SPEAKS_MAX_CHARS", "600"))


def speak(reply):
    """Hand the raw reply to the daemon, which cleans it up per engine; SAPI cleans it here."""
    stop_current()
    if os.environ.get("CLAUDE_SPEAKS_ENGINE", "pocket") == "pocket":
        speak_pocket(reply)
        return
    proc = subprocess.Popen(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
         "-File", subprocess.check_output(["wslpath", "-w", str(PS1)], text=True).strip()],
        stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    PID_FILE.write_text(str(proc.pid))
    proc.stdin.write(truncate(to_speech(reply, plugin_options()), max_chars()).encode("utf-8"))
    proc.stdin.close()  # don't wait; let speech run after the hook exits


def main():
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    os.chdir(STATE_DIR)  # the daemon's socket is addressed relative to here
    args = sys.argv[1:]
    if args == ["--stop"]:
        stop_current()
        send_to_daemon({"cmd": "stop"})
    elif args == ["--shutdown"]:
        send_to_daemon({"cmd": "shutdown"})
    elif args == ["--warm"]:
        warm()
    elif args == ["--stdin-text"]:  # plugin hook: the reply as plain text
        reply = sys.stdin.read()
        if not MUTE_FILE.exists() and reply.strip():
            speak(reply)
    elif args:  # direct use: speak.py "some text"
        speak(" ".join(args))
    elif not MUTE_FILE.exists():  # classic Stop hook: JSON on stdin
        try:
            data = json.load(sys.stdin)
        except json.JSONDecodeError:
            return
        if data.get("stop_hook_active"):
            return
        reply = data.get("last_assistant_message") or last_reply_from_transcript(data.get("transcript_path", ""))
        if reply and reply.strip():
            speak(reply)


if __name__ == "__main__":
    main()
