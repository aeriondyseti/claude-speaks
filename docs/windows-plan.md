# Native Windows support: plan

Status: not started. `speaks` 0.2.0 runs on Linux, WSL2 and macOS. On native Windows it fails at the first daemon call. This document is the handoff for that work, which is meant to be done in a Claude Code session running natively on Windows, against a clone of this repo on the Windows side.

## What's been verified (2026-10-13, from WSL via `powershell.exe`)

- **The daemon can't be reached.** Windows Python (3.13) has no `socket.AF_UNIX`. `uv run --no-project speak.py --warm` and `--stdin-text` both fail in `send_to_daemon` with `AttributeError: module 'socket' has no attribute 'AF_UNIX'`.
- **Audio playback already works.** `sounddevice` plays through its bundled PortAudio (`PortAudio V19.7.0-devel`). A 24 kHz int16 `RawOutputStream` tone played on the default output, with no system install. `paplay` doesn't exist there, so `audio_backend: auto` already picks `sounddevice`.
- **`uv` is installed**, via mise shims (`C:\Users\…\AppData\Local\mise\shims\uv.exe`). In a folder that mise sees, calling `uv` can make mise auto-install the tools in its config. Expect that on a first run.

## What has to change

### 1. Daemon transport (blocker)

`speak.py` (`send_to_daemon`) and `daemon.py` (`serve`) use an AF_UNIX socket in the state dir, chmod 600.

- **On Windows, use TCP on `127.0.0.1`, port 0.** The daemon binds, then writes `{"port": N, "token": "<random 32 bytes hex>"}` to `daemon.json` in the state dir. That file must be readable by the current user only. The token matters: requests can carry the TTS API key, and on Windows any local process can reach a loopback port.
- **Every request carries the token.** The daemon rejects a missing or wrong token and closes the connection.
- **The protocol stays the same:** one JSON request, the client shuts its write side, and the daemon streams `installing-pocket` / `loading-pocket` / `pocket-ready` lines, then closes. `socket.SHUT_WR` exists on Windows.
- **Keep the `hello` handshake** (0.3.1): `{"cmd": "hello"}` gets back `daemon <fingerprint>`, and `ensure_daemon()` replaces a daemon whose fingerprint differs from the client's. It must work unchanged over TCP, so a plugin update on Windows also replaces the running daemon.
- **Hide the choice behind a small `transport` module** that both files use, so POSIX keeps AF_UNIX unchanged. The `os.chdir(STATE_DIR)` plus relative-name trick only exists for AF_UNIX's ~108-character path limit; don't apply it on Windows.
- **File permissions need Windows handling.** `STATE_DIR.chmod(0o700)` and `SOCKET.chmod(0o600)` don't restrict access on Windows. Either rely on `%LOCALAPPDATA%` being per-user (it is, by ACL), or set an explicit ACL with `icacls`. Pick one and say which in the README.

### 2. Paths

These are XDG-style everywhere: `STATE_DIR`, `VENV`, `CONFIG` in `speak.py` and `daemon.py`.

- **On Windows, default under `%LOCALAPPDATA%\claude-speaks\`:**
  - `state\` for the log, the starting marker and `daemon.json`
  - `venv\`
  - `config.json`
- **Keep XDG overrides working when the variables are set.** One `paths()` helper should serve both files. Right now `speak.py` and `daemon.py` each define these constants.
- **`installed()` won't find a Windows install.** It globs `lib/python*/site-packages/pocket_tts`, but a Windows venv uses `Lib/site-packages`. Check both layouts.

### 3. Process handling

- **Launching the daemon** (`start_daemon`): it uses `start_new_session=True`, which is POSIX only. On Windows, use `creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW`, and check that the daemon survives the hook's `uv run` process exiting.
- **Stopping the Windows voice** (`stop_current`): it uses `os.killpg`, and only the SAPI engine needs it. On Windows, use `proc.terminate()`, or `taskkill /PID <pid> /T /F` to also end PowerShell's children.
- **`/speaks` runs `bin/claude-speaks`**, a bash script, from `hooks/register.ts`. Native Windows has no bash. Move `on`, `off`, `stop` and `status` into `speak.py` (`--mute` / `--unmute` / `--stop` / `--status`). Then the mod runs `speakPy(root, …)` for `/speaks` too, and `bin/claude-speaks` becomes a thin POSIX wrapper around it.

### 4. Engines

- **Pocket TTS** should work unchanged. `pyproject.toml` pulls torch from the PyTorch CPU index, and `uv.lock` is universal. Verify that `uv run --frozen` resolves Windows wheels: the first run downloads ~1 GB into `%LOCALAPPDATA%\claude-speaks\venv`.
- **The Windows SAPI engine** (`CLAUDE_SPEAKS_ENGINE=sapi`, `say.ps1`) currently runs `wslpath -w`, which doesn't exist natively. Pass `PS1` straight to `powershell.exe -File`, and only use `wslpath` under WSL.
- **The HTTP engine** (`urllib`) should need no change.

### 5. Not in scope

- `install.sh`, the classic Stop hook path: Windows users install the plugin instead.
- `deploy/voxtral` (Docker/GPU).

## Test plan (in the Windows session)

1. **Tests and checks:** `claude plugin test .`, `claude plugin validate .` and `npx -y @aeriondyseti/plugin-kit doctor .` pass, plus any new tests for the transport and paths.
2. **Transport:** `uv run --no-project speak.py --warm` starts the daemon. `daemon.json` appears under `%LOCALAPPDATA%\claude-speaks\state\`, and a second `--warm` sees it running.
3. **A raw reply:** `"Edit ~/.config/x.json on the 5060 Ti." | uv run --no-project speak.py --stdin-text` prints `loading-pocket`, then `pocket-ready`, and you hear it. A second reply prints nothing and plays at once.
4. **Token check:** a request with a wrong token is refused. Use a short script that connects without it.
5. **Fresh install:** with a temp `LOCALAPPDATA` override (or a clean user), the first reply prints `installing-pocket` and still gets spoken.
6. **HTTP fallback:** run a stand-in server on 127.0.0.1. A good response plays, while a 500 or a response with no audio falls back to Pocket TTS, and `daemon.log` says which engine spoke.
7. **The plugin in Windows Claude Code:** install from a local marketplace or with `--plugin-dir`.
   - Replies are spoken.
   - Toasts show while Pocket TTS loads.
   - `/speaks off` / `/speaks on` / `/speaks stop` work.
   - An `http_api_key` of `${SOME_VAR}` gets expanded.
   - The daemon outlives the hook processes, and a new session reuses it.
8. **Paths with spaces:** a user profile with a space in it, if available. Every subprocess call passes an argv list, never a shell string; keep it that way.
