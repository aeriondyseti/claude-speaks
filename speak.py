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
import json
import os
import re
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

STATE_DIR = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / "claude-speaks"
MUTE_FILE = STATE_DIR / "muted"
PID_FILE = STATE_DIR / "speaker.pid"
SOCKET = STATE_DIR / "daemon.sock"
STARTING = STATE_DIR / "daemon.starting"
HERE = Path(__file__).resolve().parent
PS1 = HERE / "say.ps1"
# Kept outside the plugin folder so plugin updates don't throw away the ~1 GB install.
VENV = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "claude-speaks/venv"
UV_ENV = {**os.environ, "UV_PROJECT_ENVIRONMENT": str(VENV)}


def installed():
    """True once uv has finished installing (it creates the venv folder before that)."""
    return any(VENV.glob("lib/python*/site-packages/pocket_tts"))
# Kept outside the plugin folder so plugin updates don't throw away the ~1 GB install.
VENV = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "claude-speaks/venv"


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
    r"(?<![\w/])(?:(?:~|\$HOME|\.{1,2})?(?:/[\w.@+-]+)+/?"
    r"|[\w@+-][\w.@+-]*(?:/[\w.@+-]+){2,}/?"
    r"|[\w@+-][\w.@+-]*(?:/[\w.@+-]+)*/[\w@+-]+\.[A-Za-z]\w*"
    r"|(?<!\w)[\w-]{2,}(?:\.[\w-]+)*\.[A-Za-z][A-Za-z0-9]+\b)"  # bare file.ext
)


def spell(chars):
    return " ".join(LETTERS.get(c.lower(), c) for c in chars)


def load_lexicon(base=None):
    lex = dict(LEXICON if base is None else base)
    path = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "claude-speaks/lexicon.json"
    try:
        lex.update(json.loads(path.read_text()))
    except (OSError, json.JSONDecodeError):
        pass
    return lex


def parse_replacements(lines):
    rules = []
    for line in lines:
        find, sep, repl = line.partition("=>")
        find, repl = find.strip(), repl.strip()
        if not sep or not find:
            continue
        if len(find) > 2 and find.startswith("/") and find.endswith("/"):
            try:
                rules.append((re.compile(find[1:-1]), repl))
            except re.error:
                continue
        else:
            flags = re.I if find == find.lower() else 0
            rules.append((re.compile(r"(?<![\w-])" + re.escape(find) + r"(?![\w-])", flags), repl))
    return rules


def apply_replacements(text, lines):
    for pattern, repl in parse_replacements(lines):
        text = pattern.sub(lambda m, r=repl: f" {r} " if r else "", text)  # padded; spaces collapse later
    return text


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


def speak_path(m):
    path = m.group()
    path = re.sub(r"^(~|\$HOME)(?=/|$)", "home", path)
    path = UUID.sub(lambda h: f"\0{speak_hash(h)}\0", path)
    path = HEX_HASH.sub(lambda h: f"\0{speak_hash(h)}\0", path)  # protect from separator words
    parts = re.split(r"(\0[^\0]*\0)", path)
    out = "".join(
        part.strip("\0") if part.startswith("\0") else re.sub(r"[/._-]", lambda c: SEPARATORS[c.group()], part)
        for part in parts
    )
    return " " + re.sub(r"\s+", " ", out).strip() + " "


ONES = "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen".split()
TENS = "_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()
SCALES = [(10**12, "trillion"), (10**9, "billion"), (10**6, "million"), (1000, "thousand"), (100, "hundred")]
UNITS = {"GB": "gigabytes", "GiB": "gigabytes", "MB": "megabytes", "MiB": "megabytes", "KB": "kilobytes",
         "TB": "terabytes", "ms": "milliseconds", "s": "seconds", "GHz": "gigahertz", "MHz": "megahertz",
         "Hz": "hertz", "kHz": "kilohertz", "dB": "decibels", "%": "percent"}
LETTERS = dict(zip("abcdefghijklmnopqrstuvwxyz", (
    "ay bee see dee ee eff gee aitch eye jay kay el em en oh pee cue ar ess tee you vee "
    "double-you ex why zee").split()))
# Whole-word pronunciation fixes; extend with ~/.config/claude-speaks/lexicon.json ({"word": "spoken"}).
# Lowercase keys match any case (JSON, json); others match exactly.
LEXICON = {"Ti": "tee eye", "gpu": "gee pee you", "cpu": "see pee you", "vram": "vee ram",
           "wsl": "double-you ess el", "tts": "tee tee ess", "cli": "see el eye", "uuid": "you you eye dee",
           # file types
           "json": "jay sohn", "yaml": "yah-mull", "yml": "yah-mull", "png": "ping", "gif": "giff",
           "jpg": "jay peg", "jpeg": "jay peg", "toml": "tom-ull", "py": "pie", "exe": "ex ee",
           "wav": "wave", "md": "markdown", "ini": "in ee", "tsx": "tee ess ex", "jsx": "jay ess ex",
           # path words
           "src": "source", "tmp": "temp", "usr": "user", "mnt": "mount", "vs": "versus",
           # words Pocket can't sound out
           "gym": "jim", "hmm": "hum", "shh": "shush", "nth": "enth", "brr": "burr",
           "mr": "mister", "mrs": "missus", "dr": "doctor"}
# User-editable "find => replace" rules, applied first under every profile. A plain word matches
# whole words (any case when written in lowercase); /regex/ is a pattern. These defaults are the
# light ("kokoro") rules that fit this form; the rest (numbers, hashes, path separators,
# underscores) need code and stay built in.
DEFAULT_REPLACEMENTS = [
    "Ti => tee eye",
    r"/(?<![\w/])(?:~|\$HOME)(?=/)/ => home",
    r"/\$HOME\b/ => home",
    r"/~(?=\d)/ => about",
    r"/(?<=\d)\s?[–—-]\s?(?=\d)/ => to",
    r"/(?<=\w)\(\)/ => ",
]
# Vowelless words to leave alone rather than spell (ambiguous: St = street/saint, Ms = miz/milliseconds).
SAY_AS_WORD = {"st", "ms", "psst", "pfft"}
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
    return ("vee " if m.group(1) else "") + " point ".join(int_words(int(p)) for p in m.group(2).split("."))


def speak_number(m):
    whole, frac, times, unit = m.groups()
    words = say_whole(whole)
    if frac:
        words += " point " + " ".join(ONES[int(d)] for d in frac)
    if times:
        words += " times"
    elif unit:
        words += " " + UNITS[unit]
    return words


def to_speech(md, profile="pocket", replacements=None):
    """profile "pocket": spell everything out; "kokoro": only what Kokoro's own G2P gets wrong.
    `replacements` ("find => replace" lines, DEFAULT_REPLACEMENTS when None) run first under both."""
    full = profile != "kokoro"
    text = re.sub(r"```.*?(```|$)", "\nCode block omitted.\n", md, flags=re.S)
    text = "\n".join(l for l in text.splitlines() if not l.lstrip().startswith("|"))  # tables
    text = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", text)  # links/images -> label
    text = re.sub(r"https?://\S+", "a link", text)
    text = apply_replacements(text, DEFAULT_REPLACEMENTS if replacements is None else replacements)
    text = UUID.sub(speak_hash, text)
    text = HEX_HASH.sub(speak_hash, text)
    if full:
        text = PATH.sub(speak_path, text)
    else:
        # Kokoro drops dots, dashes and (after "home") slashes inside paths
        text = PATH.sub(lambda m: " " + re.sub(r"[./-]", lambda c: {".": " dot ", "/": " slash ", "-": " dash "}[c[0]], m[0]) + " ", text)
    if full:  # the light profile takes these from the (editable) replacements
        text = re.sub(r"\$HOME\b", "home", text)
        text = re.sub(r"(?<=\w)\(\)", "", text)  # stop() -> stop; a bare ")" reads as a sentence end
        text = re.sub(r"~(?=\d)", "about ", text)
        text = re.sub(r"(?<=\d)\s?[–—-]\s?(?=\d)", " to ", text)  # ranges: 9–12
    text = re.sub(r"\b[A-Za-z0-9]+(?:_[A-Za-z0-9]+)+\b", speak_identifier, text)
    text = VERSION.sub(speak_version, text)
    if full:
        text = re.sub(r"\b([A-Za-z])(\d+)\b", lambda m: f"{LETTERS[m[1].lower()]} {m[2]}", text)  # p99, x86
    text = re.sub(r"(?<![\w.-])-(?=\d)", "minus ", text)
    text = NUMBER.sub(speak_number, text)
    lexicon = load_lexicon(LEXICON if full else {})
    folded = {k: v for k, v in lexicon.items() if k == k.lower()}
    for keys, flags, look in ((lexicon.keys() - folded.keys(), 0, lexicon), (folded.keys(), re.I, folded)):
        if keys:
            words = re.compile(r"(?<![\w-])(" + "|".join(map(re.escape, sorted(keys, key=len, reverse=True))) + r")(?![\w-])", flags)
            text = words.sub(lambda m, look=look, flags=flags: look[m[1].lower() if flags else m[1]], text)
    if full:
        # Vowelless 2-5 letter words are abbreviations: db, cfg, RTX, HTML -> spelled out
        text = re.sub(r"(?<![\w-])[b-df-hj-np-tv-xzB-DF-HJ-NP-TV-XZ]{2,5}(?![\w-])",
                      lambda m: m[0] if m[0].lower() in SAY_AS_WORD else spell(m[0]), text)
        text = re.sub(r"(?<![\w-])(?=[A-Z]*Y)[B-DF-HJ-NP-TV-Z]{2,5}(?![\w-])", lambda m: spell(m[0]), text)  # TTY, NYC
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"^\s{0,3}#{1,6}\s*", "", text, flags=re.M)  # headings
    text = re.sub(r"^\s*([-*+]|\d+\.)\s+", "", text, flags=re.M)  # list markers
    text = re.sub(r"^\s*>\s?", "", text, flags=re.M)  # quotes
    text = re.sub(r"(\*\*|\*|~~)(?=\S)(.+?)(?<=\S)\1", r"\2", text)  # emphasis
    text = re.sub(r"(?<!\w)(__|_)(?=\S)(.+?)(?<=\S)\1(?!\w)", r"\2", text)  # not snake_case
    text = re.sub(r"[-*_]{3,}", " ", text)  # rules
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    text = " ".join(l if l[-1] in ".!?:;," else l + "." for l in lines)  # pause between lines
    text = re.sub(r"\s+([.,;:!?])", r"\1", text)  # padding left by speak_path
    return re.sub(r"\s+", " ", text).strip()


def truncate(text, limit):
    if limit <= 0 or len(text) <= limit:
        return text
    cut = text[:limit]
    end = max(cut.rfind(". "), cut.rfind("? "), cut.rfind("! "))
    return (cut[: end + 1] if end > limit // 3 else cut) + " ... and more on screen."


def stop_current():
    try:
        pid = int(PID_FILE.read_text())
        os.killpg(pid, signal.SIGTERM)
    except (OSError, ValueError):
        pass
    PID_FILE.unlink(missing_ok=True)


def send_to_daemon(req):
    """Send one request; for speech, relay the daemon's status lines to stdout (the plugin
    toasts "loading-pocket") until it closes the connection."""
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
                    print(line.strip(), flush=True)
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


def speak_pocket(reply):
    options = plugin_options()
    request = {"text": reply, "options": options, "env": referenced_env(options)}
    if send_to_daemon(request):
        return
    # Not running (the session-start warm-up normally has it up): start it and wait, then send.
    # The plugin doesn't wait on this process, and the request never touches disk or argv.
    installing = not installed()
    if installing:
        print("installing-pocket", flush=True)
    start_daemon()
    deadline = time.time() + (900 if installing else 45)
    while time.time() < deadline:
        time.sleep(0.5)
        if send_to_daemon(request):
            return


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
        stderr=open(STATE_DIR / "daemon.log", "ab"), start_new_session=True,
    )


def warm():
    """Session start: have the daemon up (installing on first use) before the first reply.
    Pocket TTS itself loads only when a reply needs it."""
    if not send_to_daemon({"cmd": "ping"}):
        start_daemon()


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
    proc.stdin.write(truncate(to_speech(reply), max_chars()).encode("utf-8"))
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
