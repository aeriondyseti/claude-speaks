#!/usr/bin/env python3
"""Keeps a Pocket TTS model loaded and speaks text sent over a unix socket.

Protocol: one JSON object per connection.
  {"text": "...", "voice": "alba"}  speak (interrupts anything playing)
  {"cmd": "stop"}                   stop playback
  {"cmd": "shutdown"}               exit
"""
import argparse
import json
import os
import socket
import subprocess
import threading
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

import numpy as np  # noqa: E402
from pocket_tts import TTSModel  # noqa: E402

STATE_DIR = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / "claude-speaks"
SOCKET = STATE_DIR / "daemon.sock"
DEFAULT_VOICE = os.environ.get("CLAUDE_SPEAKS_POCKET_VOICE", "alba")


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
        if self.player and self.player.poll() is None:
            self.player.kill()

    def say(self, text, voice=None):
        self.stop()
        with self.lock:  # wait for the previous job to unwind
            self.stop_event = stop = threading.Event()
            state = self.voice(voice or DEFAULT_VOICE)
            self.player = player = subprocess.Popen(
                ["paplay", "--raw", "--format=s16le", "--channels=1", f"--rate={self.model.sample_rate}"],
                stdin=subprocess.PIPE, stderr=subprocess.DEVNULL,
            )
            try:
                for chunk in self.model.generate_audio_stream(state, text, stop=stop):
                    if stop.is_set():
                        break
                    pcm = (np.clip(chunk.detach().cpu().numpy(), -1, 1) * 32767).astype("<i2")
                    player.stdin.write(pcm.tobytes())
                player.stdin.close()
            except (BrokenPipeError, OSError):
                pass


def serve(initial_text=None):
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    speaker = Speaker()
    SOCKET.unlink(missing_ok=True)
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.bind(str(SOCKET))
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
                threading.Thread(target=speaker.say, args=(req["text"], req.get("voice")), daemon=True).start()
    finally:
        SOCKET.unlink(missing_ok=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--say", help="text to speak once the model is loaded")
    serve(ap.parse_args().say)
