"""Speaks text sent over a unix socket.

Uses an OpenAI-compatible /v1/audio/speech server when one is configured and
reachable (e.g. a GPU container), otherwise a Pocket TTS model kept loaded here.
Config is re-read on every request from ~/.config/claude-speaks/config.json:
  {"http_url": "http://127.0.0.1:18090/v1/audio/speech", "http_model": "...",
   "http_voice": "casual_female", "http_sample_rate": 24000, "pocket_voice": "alba",
   "volume_db": 6, "max_chars": 600,
   "http_extra": {"normalization_options": {"normalize": false}}}  # merged into the request body
Requests carry the raw reply; it is cleaned up and truncated here, the same for every engine.

Protocol: one JSON object per connection.
  {"text": "...", "voice": "alba"}  speak (interrupts anything playing)
  {"cmd": "stop"}                   stop playback
  {"cmd": "shutdown"}               exit
"""
import argparse
import queue
import re
import shutil
import base64
import json
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

import numpy as np  # noqa: E402

from speak import ENV_REF, code_fingerprint, max_chars, to_speech, truncate  # noqa: E402

FINGERPRINT = code_fingerprint(Path(__file__).resolve().parent)  # of the code this process loaded

STATE_DIR = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / "claude-speaks"
SOCKET = STATE_DIR / "daemon.sock"
CONFIG = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "claude-speaks/config.json"
DEFAULT_VOICE = os.environ.get("CLAUDE_SPEAKS_POCKET_VOICE", "alba")


def log(msg):
    print(time.strftime("%H:%M:%S"), msg, file=sys.stderr, flush=True)  # stderr is daemon.log


def load_config(options=None):
    """config.json, overridden by the plugin's options (an empty string there means unset)."""
    try:
        cfg = json.loads(CONFIG.read_text())
    except (OSError, json.JSONDecodeError):
        cfg = {}
    cfg.update({k: v for k, v in (options or {}).items() if v != ""})
    return cfg


def expand_env(value, env, key):
    """Expand ${VAR} / ${VAR:-default} in a setting; an unset VAR with no default is empty."""
    if isinstance(value, str):
        def sub(m):
            if m[1] in env:
                return env[m[1]]
            if m[2] is None:
                log(f"{key} names ${{{m[1]}}}, which is not set")
            return m[2] or ""
        return ENV_REF.sub(sub, value)
    if isinstance(value, list):
        return [expand_env(v, env, key) for v in value]
    if isinstance(value, dict):
        return {k: expand_env(v, env, key) for k, v in value.items()}
    return value


def split_sentences(text):
    parts = []
    for p in re.split(r"(?<=[.!?])\s+", text):
        # A wordless piece ("...") gets no audio from Kokoro, which reads as a failure; join it on
        if parts and not re.search(r"\w", parts[-1]):
            parts[-1] += " " + p
        elif p.strip():
            parts.append(p.strip())
    if len(parts) > 1 and not re.search(r"\w", parts[-1]):
        tail = parts.pop()
        parts[-1] += " " + tail
    return parts or [text]


def extra_body(cfg):
    extra = cfg.get("http_extra") or {}
    if isinstance(extra, str):  # the plugin option is a JSON string
        try:
            extra = json.loads(extra)
        except json.JSONDecodeError:
            log("http_extra is not valid JSON; ignoring it")
            return {}
    return extra if isinstance(extra, dict) else {}


def request_headers(cfg):
    headers = {"Content-Type": "application/json"}
    if cfg.get("http_api_key"):
        headers["Authorization"] = f"Bearer {cfg['http_api_key']}"
    for line in cfg.get("http_headers") or []:  # "Name: value"
        name, sep, value = line.partition(":")
        if sep and name.strip():
            headers[name.strip()] = value.strip()
    return headers


def audio_backend(choice="auto"):
    """paplay where it exists (PulseAudio/PipeWire, WSLg: the known-good path on Linux), else
    sounddevice, whose macOS and Windows wheels bundle PortAudio (Linux needs libportaudio2)."""
    if choice == "auto":
        return "paplay" if shutil.which("paplay") else "sounddevice"
    return choice


class Player:
    """Mono s16le out through paplay or sounddevice, with optional gain through a tanh soft limiter."""

    def __init__(self, rate, volume_db=0, backend="auto"):
        self.gain = 10 ** (volume_db / 20)
        self.leftover = b""
        self.proc = self.stream = None
        if audio_backend(backend) == "paplay":
            self.proc = subprocess.Popen(
                ["paplay", "--raw", "--format=s16le", "--channels=1", f"--rate={rate}"],
                stdin=subprocess.PIPE, stderr=subprocess.DEVNULL,
            )
        else:
            import sounddevice  # raises OSError when PortAudio is missing
            self.stream = sounddevice.RawOutputStream(samplerate=rate, channels=1, dtype="int16")
            self.stream.start()

    def write_float(self, samples):
        if self.gain != 1:
            samples = np.tanh(samples * self.gain)
        data = (np.clip(samples, -1, 1) * 32767).astype("<i2").tobytes()
        if self.proc:
            self.proc.stdin.write(data)
        elif self.stream:
            self.stream.write(data)  # blocks while PortAudio's buffer is full

    def write_pcm(self, data):
        data = self.leftover + data
        cut = len(data) - len(data) % 2  # chunks may split a sample
        self.leftover = data[cut:]
        self.write_float(np.frombuffer(data[:cut], "<i2").astype(np.float32) / 32768)

    def close(self):
        """Finish playing what was written (paplay drains on its own after EOF)."""
        if self.proc:
            self.proc.stdin.close()
        elif self.stream:
            try:
                self.stream.stop()  # waits for the buffered audio
                self.stream.close()
            except Exception:
                pass

    def kill(self):
        if self.proc and self.proc.poll() is None:
            self.proc.kill()
        elif self.stream:
            try:
                self.stream.abort()
            except Exception:
                pass


class Reporter:
    """Status lines back to the speak.py that asked ("loading-pocket", "pocket-ready"); closed once
    an engine has started, so the client doesn't wait out the speech."""

    def __init__(self, conn=None):
        self.conn = conn

    def event(self, name):
        if self.conn:
            try:
                self.conn.sendall(name.encode() + b"\n")
            except OSError:
                self.close()

    def close(self):
        if self.conn:
            self.conn.close()
            self.conn = None


class Speaker:
    def __init__(self):
        self.model = None  # Pocket TTS loads on the first reply that needs it
        self.model_lock = threading.Lock()
        self.voices = {}
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self.player = None

    def ensure_pocket(self, report):
        with self.model_lock:
            if self.model is None:
                report.event("loading-pocket")
                log("loading Pocket TTS")
                from pocket_tts import TTSModel
                self.model = TTSModel.load_model()
                report.event("pocket-ready")
                log("Pocket TTS ready")

    def voice(self, name):
        if name not in self.voices:
            self.voices[name] = self.model.get_state_for_audio_prompt(name)
        return self.voices[name]

    def stop(self):
        self.stop_event.set()
        if self.player:
            self.player.kill()

    def say(self, reply, voice=None, options=None, env=None, report=None):
        report = report or Reporter()
        try:
            self._say(reply, voice, options, env, report)
        finally:
            report.close()

    def _say(self, reply, voice, options, env, report):
        self.stop()
        with self.lock:  # wait for the previous job to unwind
            self.stop_event = stop = threading.Event()
            cfg = load_config(options)
            limit = int(cfg.get("max_chars", max_chars()))
            debug = bool(cfg.get("debug_log_text"))
            try:
                url_as_written = cfg.get("http_url")  # logged instead of the expansion, which may hold a key
                if url_as_written:
                    cfg = {k: expand_env(v, env or {}, k) if k.startswith("http_") else v for k, v in cfg.items()}
                text = pocket_text = truncate(to_speech(reply, cfg), limit)  # the same text for every engine
                if cfg.get("http_url"):
                    if debug:
                        log(f"text for {url_as_written}: {text}")
                    spoke, rest = self.say_http(cfg, text, stop, report) if text else (True, "")
                    if spoke and not rest:
                        log(f"spoke via {url_as_written}")
                        return
                    if spoke:  # a later sentence failed: Pocket says the rest
                        log("http engine failed partway; Pocket speaks the rest")
                        pocket_text = rest
                    else:
                        log("http engine failed; falling back to Pocket")
                if pocket_text:
                    if debug:
                        log(f"text for Pocket: {pocket_text}")
                    self.ensure_pocket(report)
                    report.close()
                    self.say_pocket(pocket_text, voice or cfg.get("pocket_voice") or DEFAULT_VOICE, stop,
                                    float(cfg.get("volume_db", 0)), cfg.get("audio_backend", "auto"))
            except BrokenPipeError:
                pass  # playback was cut off by stop()
            except OSError as e:
                log(f"playback failed: {e}")

    def say_http(self, cfg, text, stop, report):
        """Speak through the server, one request per sentence (http_split_sentences, on by default) so
        the first audio comes after one sentence's synthesis, not the whole reply's. A background
        thread fetches ahead while playback runs. Returns (spoke anything, text left unspoken)."""
        sentences = split_sentences(text) if cfg.get("http_split_sentences", True) else [text]
        chunks = queue.Queue(maxsize=256)
        progress = {"failed_at": None}
        t0 = time.time()

        def fetch():
            for i, sentence in enumerate(sentences):
                if stop.is_set():
                    break
                if not self.stream_sentence(cfg, sentence, stop, chunks):
                    progress["failed_at"] = i
                    break
            chunks.put(None)

        threading.Thread(target=fetch, daemon=True).start()
        player = None
        while (pcm := chunks.get()) is not None:
            if stop.is_set():
                continue  # drain until the fetcher notices
            if player is None:
                report.close()  # the server answered; nothing to report
                log(f"first audio after {int((time.time() - t0) * 1000)} ms")
                self.player = player = Player(int(cfg.get("http_sample_rate", 24000)), float(cfg.get("volume_db", 0)),
                                              cfg.get("audio_backend", "auto"))
            player.write_pcm(pcm)
        if player:
            player.close()
        failed = progress["failed_at"]
        if failed is None or stop.is_set():
            return True, ""
        return player is not None, " ".join(sentences[failed:])

    def stream_sentence(self, cfg, text, stop, chunks):
        """One request; queue its PCM. False when it failed before any audio (unreachable, an HTTP
        error, nothing returned)."""
        body = {"input": text, "stream": True, "response_format": "pcm",
                "model": cfg.get("http_model"), "voice": cfg.get("http_voice"), **extra_body(cfg)}
        req = urllib.request.Request(
            cfg["http_url"], data=json.dumps({k: v for k, v in body.items() if v}).encode(),
            headers=request_headers(cfg),
        )
        got_audio = False
        try:
            with urllib.request.urlopen(req, timeout=float(cfg.get("http_timeout", 10))) as resp:  # HTTPError is an OSError
                if resp.headers.get_content_type() == "text/event-stream":
                    # vLLM-Omni: speech.audio.delta events with base64 PCM, then speech.audio.done
                    # (the connection stays open for a while after done, so stop there).
                    for line in resp:
                        if stop.is_set():
                            break
                        if not line.startswith(b"data:"):
                            continue
                        event = json.loads(line[5:])
                        if event.get("audio"):
                            chunks.put(base64.b64decode(event["audio"]))
                            got_audio = True
                        if event.get("type", "").endswith(".done"):
                            break
                else:
                    while not stop.is_set() and (data := resp.read1(8192)):
                        chunks.put(data)
                        got_audio = True
        except OSError as e:
            log(f"http request failed: {e}")
        return got_audio or stop.is_set()

    def say_pocket(self, text, voice, stop, volume_db, backend):
        state = self.voice(voice)
        self.player = player = Player(self.model.sample_rate, volume_db, backend)
        for chunk in self.model.generate_audio_stream(state, text, stop=stop):
            if stop.is_set():
                break
            player.write_float(chunk.detach().cpu().numpy())
        player.close()


def serve(initial_text=None):
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    speaker = Speaker()
    SOCKET.unlink(missing_ok=True)
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    STATE_DIR.chmod(0o700)
    os.chdir(STATE_DIR)
    srv.bind(SOCKET.name)  # relative: AF_UNIX paths max out near 108 characters
    SOCKET.chmod(0o600)  # requests can carry an API key
    srv.listen()
    (STATE_DIR / "daemon.starting").unlink(missing_ok=True)
    log(f"daemon {FINGERPRINT} ready")
    if initial_text:
        threading.Thread(target=speaker.say, args=(initial_text,), daemon=True).start()
    try:
        while True:
            conn, _ = srv.accept()
            try:
                req = json.loads(conn.makefile().read() or "{}")  # the client shuts its side when done
            except (OSError, json.JSONDecodeError):
                conn.close()
                continue
            cmd = req.get("cmd")
            if cmd == "hello":
                try:
                    conn.sendall(f"daemon {FINGERPRINT}\n".encode())
                except OSError:
                    pass
            if cmd or not req.get("text"):
                conn.close()
            if cmd == "shutdown":
                log("shutting down")
                speaker.stop()
                break
            if cmd == "stop":
                speaker.stop()
            elif req.get("text"):
                args = (req["text"], req.get("voice"), req.get("options"), req.get("env"), Reporter(conn))
                threading.Thread(target=speaker.say, args=args, daemon=True).start()
    finally:
        SOCKET.unlink(missing_ok=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--say", help="text to speak once started")
    serve(ap.parse_args().say)
