#!/usr/bin/env python3
"""Speaks text sent over a unix socket.

Uses an OpenAI-compatible /v1/audio/speech server when one is configured and
reachable (e.g. a GPU container), otherwise a Pocket TTS model kept loaded here.
Config is re-read on every request from ~/.config/claude-speaks/config.json:
  {"http_url": "http://127.0.0.1:18090/v1/audio/speech", "http_model": "...",
   "http_voice": "casual_female", "http_sample_rate": 24000, "pocket_voice": "alba",
   "volume_db": 6, "max_chars": 600,
   "http_text_profile": "kokoro",          # text rules for the server; Pocket always gets "pocket"
   "http_extra": {"normalization_options": {"normalize": false}}}  # merged into the request body
Requests carry the raw reply; it is cleaned up and truncated here, per engine.

Protocol: one JSON object per connection.
  {"text": "...", "voice": "alba"}  speak (interrupts anything playing)
  {"cmd": "stop"}                   stop playback
  {"cmd": "shutdown"}               exit
"""
import argparse
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
from pocket_tts import TTSModel  # noqa: E402

from speak import DEFAULT_REPLACEMENTS, ENV_REF, max_chars, to_speech, truncate  # noqa: E402

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


class Player:
    """paplay fed mono s16le, with optional gain through a tanh soft limiter."""

    def __init__(self, rate, volume_db=0):
        self.gain = 10 ** (volume_db / 20)
        self.leftover = b""
        self.proc = subprocess.Popen(
            ["paplay", "--raw", "--format=s16le", "--channels=1", f"--rate={rate}"],
            stdin=subprocess.PIPE, stderr=subprocess.DEVNULL,
        )

    def write_float(self, samples):
        if self.gain != 1:
            samples = np.tanh(samples * self.gain)
        self.proc.stdin.write((np.clip(samples, -1, 1) * 32767).astype("<i2").tobytes())

    def write_pcm(self, data):
        data = self.leftover + data
        cut = len(data) - len(data) % 2  # chunks may split a sample
        self.leftover = data[cut:]
        self.write_float(np.frombuffer(data[:cut], "<i2").astype(np.float32) / 32768)

    def close(self):
        self.proc.stdin.close()

    def kill(self):
        if self.proc.poll() is None:
            self.proc.kill()


class Speaker:
    def __init__(self):
        self.model = TTSModel.load_model()
        self.voices = {}
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self.player = None
        self.voice(DEFAULT_VOICE)

    def voice(self, name):
        if name not in self.voices:
            self.voices[name] = self.model.get_state_for_audio_prompt(name)
        return self.voices[name]

    def stop(self):
        self.stop_event.set()
        if self.player:
            self.player.kill()

    def say(self, reply, voice=None, options=None, env=None):
        self.stop()
        with self.lock:  # wait for the previous job to unwind
            self.stop_event = stop = threading.Event()
            cfg = load_config(options)
            limit = int(cfg.get("max_chars", max_chars()))
            rules = cfg.get("replacements", DEFAULT_REPLACEMENTS)
            try:
                url_as_written = cfg.get("http_url")  # logged instead of the expansion, which may hold a key
                if url_as_written:
                    cfg = {k: expand_env(v, env or {}, k) if k.startswith("http_") else v for k, v in cfg.items()}
                if cfg.get("http_url"):
                    text = truncate(to_speech(reply, cfg.get("http_text_profile", "kokoro"), rules), limit)
                    if not text or self.say_http(cfg, text, stop):
                        log(f"spoke via {url_as_written}")
                        return
                    log("http engine failed; falling back to Pocket")
                text = truncate(to_speech(reply, "pocket", rules), limit)
                if text:
                    self.say_pocket(text, voice or cfg.get("pocket_voice") or DEFAULT_VOICE, stop, float(cfg.get("volume_db", 0)))
            except (BrokenPipeError, OSError):
                pass

    def say_http(self, cfg, text, stop):
        """Stream PCM from the server. False (unreachable, an error, no audio) falls back to Pocket."""
        body = {"input": text, "stream": True, "response_format": "pcm",
                "model": cfg.get("http_model"), "voice": cfg.get("http_voice"), **extra_body(cfg)}
        req = urllib.request.Request(
            cfg["http_url"], data=json.dumps({k: v for k, v in body.items() if v}).encode(),
            headers=request_headers(cfg),
        )
        try:
            resp = urllib.request.urlopen(req, timeout=float(cfg.get("http_timeout", 10)))  # HTTPError is an OSError
        except OSError as e:
            log(f"http request failed: {e}")
            return False
        got_audio = False
        with resp:
            self.player = player = Player(int(cfg.get("http_sample_rate", 24000)), float(cfg.get("volume_db", 0)))
            if resp.headers.get_content_type() == "text/event-stream":
                # vLLM-Omni: speech.audio.delta events with base64 PCM, then speech.audio.done
                # (the connection stays open for a while after done, so stop there).
                for line in resp:
                    if stop.is_set() or not line.startswith(b"data:"):
                        continue
                    event = json.loads(line[5:])
                    if event.get("audio"):
                        player.write_pcm(base64.b64decode(event["audio"]))
                        got_audio = True
                    if event.get("type", "").endswith(".done"):
                        break
            else:
                while not stop.is_set() and (data := resp.read1(8192)):
                    player.write_pcm(data)
                    got_audio = True
            player.close()
        return got_audio or stop.is_set()

    def say_pocket(self, text, voice, stop, volume_db):
        state = self.voice(voice)
        self.player = player = Player(self.model.sample_rate, volume_db)
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
    srv.bind(str(SOCKET))
    SOCKET.chmod(0o600)  # requests can carry an API key
    srv.listen()
    (STATE_DIR / "daemon.starting").unlink(missing_ok=True)
    if initial_text:
        threading.Thread(target=speaker.say, args=(initial_text,), daemon=True).start()
    try:
        while True:
            conn, _ = srv.accept()
            with conn:
                try:
                    req = json.loads(conn.makefile().read() or "{}")
                except json.JSONDecodeError:
                    continue
            cmd = req.get("cmd")
            if cmd == "shutdown":
                speaker.stop()
                break
            if cmd == "stop":
                speaker.stop()
            elif req.get("text"):
                threading.Thread(target=speaker.say, args=(req["text"], req.get("voice"), req.get("options"), req.get("env")), daemon=True).start()
    finally:
        SOCKET.unlink(missing_ok=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--say", help="text to speak once the model is loaded")
    serve(ap.parse_args().say)
