# Parakeet Dictation — Design Spec

**Date:** 2026-07-01
**Target machine:** Apple M3, macOS 15.6.1, 16 GB RAM (arm64)
**Status:** Approved design — pending user spec review

## Goal

An always-on macOS **menu-bar dictation app**. The user speaks in a quiet room;
when they pause, the finished phrase is copied to the clipboard and, if a text
field is focused, pasted into it. No buttons, no hotkeys, no visible window. The
primary interest is testing the real-time feel and transcription speed of the
NVIDIA Parakeet TDT 0.6B v2 model on Apple Silicon.

## Non-goals

- Multiple languages (English only).
- Live token-by-token captioning / word revisions.
- Persisting transcripts to disk or any transcript history across restarts.
- A floating caption window (dropped as YAGNI; clipboard + field insertion is the feedback).
- Speaker diarization, punctuation tuning, or model fine-tuning.

## Model choice

- **Speech-to-text:** `mlx-community/parakeet-tdt-0.6b-v2` via the `parakeet-mlx`
  package. This is the same NVIDIA Parakeet TDT 0.6B v2 model, ported to run
  natively on Apple Silicon through MLX. It transcribes far faster than
  real-time on an M3.
  - Rejected alternative: NVIDIA's official NeMo weights. NeMo is CUDA-oriented
    and painful to run on macOS.
- **Voice activity detection:** `silero-vad`. Industry-standard, ~few MB, runs
  in <1 ms per chunk on CPU, supports 16 kHz.
  - Rejected alternative: `monishmal0204/nova-vad`. Obscure single-author repo
    with no track record; Silero delivers identical behavior with zero risk.

Note: model weights are a one-time ~1–2.5 GB download cached in
`~/.cache/huggingface`. This does not grow over time. Transcript data itself is
kept only in memory.

## Architecture

Single Python process with four cooperating parts. The `rumps` menu-bar app owns
the macOS main run loop; audio capture, VAD, and transcription run on a
background worker thread. UI updates (icon state, menu items) are marshaled back
to the main thread.

```
 mic ──> [Mic capture]         sounddevice, 16 kHz mono, small frames (~32 ms)
             │  audio frames
             v
        [VAD gate]             silero-vad: detect speech start; on ~0.6 s of
             │                 trailing silence, close the segment
             │  finished utterance (numpy PCM)
             v
        [Transcriber]          parakeet-mlx transcribes the whole segment
             │  text           (batch, full context — no live revisions)
             v
        [Output]               1. push text to in-memory ring buffer (last 15)
             │                 2. set system clipboard
             │                 3. if a text field is focused (AX API), send Cmd+V
             v
        [Menu bar]             rumps: static icon (flashes while transcribing),
                               dropdown lists last 15 (click = re-copy),
                               Pause / Quit
```

### Components and responsibilities

- **`mic.py` — Mic capture.** Opens a `sounddevice` input stream at 16 kHz mono
  and pushes fixed-size frames onto a thread-safe queue. Knows nothing about
  speech or the model. Depends on: `sounddevice`, `numpy`.
- **`vad.py` — Speech segmenter.** Consumes frames, runs Silero VAD, emits a
  complete utterance (concatenated PCM) once speech ends (trailing-silence
  threshold, configurable, default ~0.6 s). Also enforces a max-utterance length
  safety cap. Depends on: `silero-vad`, `numpy`.
- **`transcriber.py` — ASR.** Loads `parakeet-mlx` once at startup; given an
  utterance's PCM, returns text. Writes the segment to a short-lived temp WAV and
  calls `model.transcribe()` (simplest robust path; segments are short and
  transcription is fast, so temp-file overhead is negligible). Depends on:
  `parakeet-mlx`, `ffmpeg` (system).
- **`output.py` — Delivery.** Maintains an in-memory ring buffer of the last 15
  transcripts. For each new transcript: append to buffer, set clipboard, and —
  if the macOS Accessibility API reports a focused editable text element — post a
  Cmd+V key event. Depends on: `pyobjc` (AppKit, ApplicationServices).
- **`app.py` — Menu-bar shell.** `rumps.App` with a static icon that briefly
  changes while transcribing, a dropdown showing the last 15 transcripts (click
  to re-copy), and Pause / Quit items. Starts the background worker thread that
  wires mic → VAD → transcriber → output. Owns lifecycle.

### Data flow / threading

- One background worker thread runs the mic→VAD→transcribe→output loop.
- The main thread runs the rumps/AppKit event loop only.
- Cross-thread UI updates use `rumps`'s main-thread scheduling (e.g.
  `rumps.Timer` or `pyobjc performSelectorOnMainThread`).
- **Pause** stops feeding frames to the VAD (mic stream may stay open or be
  closed; simplest is to drop frames while paused).

## State & persistence

- **Recent transcripts:** in-memory ring buffer, max 15 entries. Never written to
  disk. Cleared on quit and lost on shutdown (as required).
- **No config file needed for v1**; thresholds are constants in code
  (documented so they're easy to tweak).

## Output behavior detail

- Clipboard is **always** set for every finished utterance.
- Field insertion (Cmd+V) happens **only** when the AX API confirms a focused
  editable text element, to avoid pasting into random apps or triggering
  shortcuts when no field is focused.

## Permissions

One-time macOS grants, prompted on first run:
- **Microphone** — for audio capture.
- **Accessibility** — required to read focused-element role and to post the
  Cmd+V key event into other apps.

## Launch at login

Registered as a macOS **Login Item** so the app starts automatically after boot
and appears in the menu bar. (Implementation: add the packaged `.app` to Login
Items, via `SMAppService`/`osascript` during install, or documented manual step.)

## Packaging & delivery

- Development in an **isolated `uv` environment** so nothing touches the user's
  miniconda base.
- Dependencies: `parakeet-mlx`, `silero-vad`, `sounddevice`, `rumps`, `pyobjc`;
  plus `ffmpeg` via Homebrew.
- Final artifact: a native **`.app` bundle** built with **`py2app`**, installed
  to `/Applications`. The user double-clicks it or it launches at login; Python
  is never visible.

## Testing / verification

- **Unit-testable in isolation:**
  - `vad.py`: feed a pre-recorded WAV with known speech/silence; assert it emits
    the expected number of segments with sane boundaries.
  - `transcriber.py`: feed a known short WAV clip; assert the text roughly
    matches expected words.
  - `output.py`: ring buffer keeps exactly the last 15; clipboard set correctly
    (mock AX focus to test paste/no-paste branch).
- **Manual end-to-end:** launch app → speak a sentence → confirm it lands in
  clipboard, and in a focused TextEdit window; confirm dropdown shows recent 15;
  confirm nothing persists after quit.
- **Speed check (the point of the project):** log wall-clock transcription time
  per utterance vs. utterance duration to confirm faster-than-real-time.

## Open items to resolve during planning

- Exact VAD trailing-silence and min-speech thresholds (start with ~0.6 s /
  ~0.25 s, tune by feel).
- Whether transcribing a numpy array directly (via `parakeet-mlx` mel helpers) is
  cleaner than the temp-WAV path; temp WAV is the safe default.
- Login Item registration method for a py2app bundle (`SMAppService` vs.
  scripted).
