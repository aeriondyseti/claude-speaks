#!/usr/bin/env python3
"""Claude Code Stop hook: read Claude's last reply aloud (WSL).

Engines: "pocket" (default) sends text to daemon.py, which keeps a Pocket TTS
model loaded and is started on demand; "sapi" uses the Windows voices.

Hook input arrives as JSON on stdin. The reply text comes from
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


def load_lexicon():
    lex = dict(LEXICON)
    path = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "claude-speaks/lexicon.json"
    try:
        lex.update(json.loads(path.read_text()))
    except (OSError, json.JSONDecodeError):
        pass
    return lex


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
LEXICON = {"Ti": "tee eye", "GPU": "gee pee you", "CPU": "see pee you", "VRAM": "vee ram",
           "WSL": "double-you ess el", "TTS": "tee tee ess", "CLI": "see el eye", "UUID": "you you eye dee"}
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


def to_speech(md):
    text = re.sub(r"```.*?(```|$)", "\nCode block omitted.\n", md, flags=re.S)
    text = "\n".join(l for l in text.splitlines() if not l.lstrip().startswith("|"))  # tables
    text = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", text)  # links/images -> label
    text = re.sub(r"https?://\S+", "a link", text)
    text = PATH.sub(speak_path, text)
    text = UUID.sub(speak_hash, text)
    text = HEX_HASH.sub(speak_hash, text)
    text = re.sub(r"\$HOME\b", "home", text)
    text = re.sub(r"~(?=\d)", "about ", text)
    text = re.sub(r"(?<=\d)\s?[–—-]\s?(?=\d)", " to ", text)  # ranges: 9–12
    text = VERSION.sub(speak_version, text)
    text = re.sub(r"\b([A-Za-z])(\d+)\b", lambda m: f"{LETTERS[m[1].lower()]} {m[2]}", text)  # p99, x86
    text = re.sub(r"(?<![\w.-])-(?=\d)", "minus ", text)
    text = NUMBER.sub(speak_number, text)
    lexicon = load_lexicon()
    if lexicon:
        words = re.compile(r"(?<![\w-])(" + "|".join(map(re.escape, sorted(lexicon, key=len, reverse=True))) + r")(?![\w-])")
        text = words.sub(lambda m: lexicon[m[1]], text)
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
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.settimeout(2)
            s.connect(str(SOCKET))
            s.sendall(json.dumps(req).encode("utf-8"))
        return True
    except OSError:
        return False


def speak_pocket(text):
    if send_to_daemon({"text": text}):
        return
    # Not running: start it with this text queued (model load takes ~10s).
    if STARTING.exists() and time.time() - STARTING.stat().st_mtime < 60:
        return
    STARTING.touch()
    subprocess.Popen(
        [str(HERE / ".venv/bin/python"), str(HERE / "daemon.py"), "--say", text],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
        stderr=open(STATE_DIR / "daemon.log", "ab"), start_new_session=True,
    )


def speak(text):
    stop_current()
    if os.environ.get("CLAUDE_SPEAKS_ENGINE", "pocket") == "pocket":
        speak_pocket(text)
        return
    proc = subprocess.Popen(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
         "-File", subprocess.check_output(["wslpath", "-w", str(PS1)], text=True).strip()],
        stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    PID_FILE.write_text(str(proc.pid))
    proc.stdin.write(text.encode("utf-8"))
    proc.stdin.close()  # don't wait; let speech run after the hook exits


def main():
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    if sys.argv[1:] == ["--stop"]:
        stop_current()
        send_to_daemon({"cmd": "stop"})
        return
    if sys.argv[1:] == ["--shutdown"]:
        send_to_daemon({"cmd": "shutdown"})
        return
    if len(sys.argv) > 1:  # direct use: speak.py "some text"
        speak(to_speech(" ".join(sys.argv[1:])))
        return
    if MUTE_FILE.exists():
        return
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError:
        return
    if data.get("stop_hook_active"):
        return
    reply = data.get("last_assistant_message") or last_reply_from_transcript(data.get("transcript_path", ""))
    text = truncate(to_speech(reply or ""), int(os.environ.get("CLAUDE_SPEAKS_MAX_CHARS", "600")))
    if text:
        speak(text)


if __name__ == "__main__":
    main()
