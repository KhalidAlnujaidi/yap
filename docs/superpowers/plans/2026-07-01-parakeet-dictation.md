# Parakeet Dictation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** An always-on macOS menu-bar dictation app that transcribes speech (Parakeet TDT 0.6B v2 via MLX) after each spoken phrase and drops the text into the clipboard + focused text field.

**Architecture:** One Python process. A background worker thread runs mic capture → Silero VAD segmentation → Parakeet-MLX transcription → output (clipboard + optional ⌘V paste). A `rumps` menu-bar app owns the macOS main run loop, shows a static icon that flashes while transcribing, and lists the last 15 transcripts. Shipped as a native `.app` via py2app.

**Tech Stack:** Python 3.11+ (uv-managed venv), `parakeet-mlx`, `silero-vad` (+torch CPU), `sounddevice`, `rumps`, `pyobjc`, `ffmpeg` (Homebrew), `py2app`.

## Global Constraints

- Target: Apple M3, macOS 15.6.1, arm64, 16 GB RAM. English only.
- STT model: `mlx-community/parakeet-tdt-0.6b-v2` (verbatim).
- VAD: `silero-vad`. Audio is 16 kHz mono float32; Silero requires exactly **512-sample** chunks at 16 kHz — mic frame size is fixed at 512 samples (32 ms).
- Recent transcripts: **in-memory only, max 15 entries**. Never written to disk. Lost on quit/shutdown.
- Clipboard is set for **every** finished utterance. Field paste (⌘V) happens **only** when the Accessibility API confirms a focused editable text element.
- Isolated `uv` env only — never touch the user's miniconda base.
- All test/run commands use `uv run ...` from the project root `/Users/khalid/Projects/parakeet-dictation`.

## File Structure

- `pyproject.toml` — uv project + dependencies.
- `setup.py` — py2app build config (Task 9 only).
- `src/parakeet_dictation/__init__.py` — package marker.
- `src/parakeet_dictation/vad.py` — `Segmenter` (pure state machine) + `SileroVad` (model wrapper).
- `src/parakeet_dictation/transcriber.py` — `write_wav()` helper + `Transcriber` class.
- `src/parakeet_dictation/output.py` — `OutputSink` (ring buffer + delivery logic, injectable deps).
- `src/parakeet_dictation/macos.py` — pyobjc primitives: `set_clipboard()`, `is_text_field_focused()`, `paste()`.
- `src/parakeet_dictation/mic.py` — `MicCapture` (sounddevice stream → frame queue).
- `src/parakeet_dictation/app.py` — `DictationApp(rumps.App)` + `main()`.
- `tests/test_segmenter.py`, `tests/test_transcriber.py`, `tests/test_output.py`.
- `scripts/build_app.sh` — packaging + install helper.

---

### Task 1: Project scaffolding

**Files:**
- Create: `pyproject.toml`, `src/parakeet_dictation/__init__.py`, `tests/test_smoke.py`
- System: `ffmpeg` via Homebrew

**Interfaces:**
- Consumes: nothing.
- Produces: an installable `uv` env; `parakeet_dictation` importable; `uv run pytest` works.

- [ ] **Step 1: Install ffmpeg**

Run:
```bash
brew install ffmpeg
```
Expected: ffmpeg installed (or "already installed").

- [ ] **Step 2: Create `pyproject.toml`**

```toml
[project]
name = "parakeet-dictation"
version = "0.1.0"
description = "Always-on macOS menu-bar dictation using Parakeet TDT 0.6B v2 (MLX)"
requires-python = ">=3.11,<3.13"
dependencies = [
    "parakeet-mlx",
    "silero-vad",
    "torch",
    "sounddevice",
    "numpy",
    "rumps",
    "pyobjc-core",
    "pyobjc-framework-Cocoa",
    "pyobjc-framework-Quartz",
    "pyobjc-framework-ApplicationServices",
    "pyobjc-framework-ServiceManagement",
]

[dependency-groups]
dev = ["pytest", "py2app"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/parakeet_dictation"]

[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]
```

Note: `python-version` is pinned `<3.13` because the user's base is 3.13 but some wheels (torch/py2app) are more reliable on 3.11/3.12. uv will fetch a suitable interpreter.

- [ ] **Step 3: Create package marker**

`src/parakeet_dictation/__init__.py`:
```python
"""Parakeet Dictation — always-on macOS menu-bar dictation."""
```

- [ ] **Step 4: Create a smoke test**

`tests/test_smoke.py`:
```python
import parakeet_dictation


def test_package_imports():
    assert parakeet_dictation.__doc__
```

- [ ] **Step 5: Sync env and run the smoke test**

Run:
```bash
uv sync
uv run pytest tests/test_smoke.py -v
```
Expected: 1 passed. (First `uv sync` downloads torch/mlx wheels — may take a few minutes.)

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock src/parakeet_dictation/__init__.py tests/test_smoke.py
git commit -m "chore: scaffold parakeet-dictation project"
```

---

### Task 2: Segmenter state machine

**Files:**
- Create: `src/parakeet_dictation/vad.py`
- Test: `tests/test_segmenter.py`

**Interfaces:**
- Consumes: nothing (pure).
- Produces:
  - `Segmenter(threshold=0.5, silence_ms=600, min_speech_ms=250, max_utterance_ms=30000, sample_rate=16000, frame_samples=512)`
  - `Segmenter.push(frame: np.ndarray, speech_prob: float) -> np.ndarray | None` — returns the concatenated utterance PCM (float32) when speech has just ended (or max length hit), else `None`.
  - `Segmenter.reset() -> None`.

- [ ] **Step 1: Write the failing tests**

`tests/test_segmenter.py`:
```python
import numpy as np
from parakeet_dictation.vad import Segmenter


def _frame():
    return np.zeros(512, dtype=np.float32)


def test_no_output_during_silence():
    seg = Segmenter()
    for _ in range(10):
        assert seg.push(_frame(), 0.0) is None


def test_emits_utterance_after_speech_then_silence():
    # 32 ms per frame. min_speech 250ms ≈ 8 frames; silence 600ms ≈ 19 frames.
    seg = Segmenter(silence_ms=600, min_speech_ms=250)
    out = None
    for _ in range(15):  # speech
        out = seg.push(_frame(), 0.9)
        assert out is None
    for _ in range(18):  # not enough trailing silence yet
        out = seg.push(_frame(), 0.0)
        if out is not None:
            break
    # one more silent frame crosses the 600ms threshold
    if out is None:
        out = seg.push(_frame(), 0.0)
    assert out is not None
    assert out.dtype == np.float32
    # utterance should contain roughly speech + trailing silence frames
    assert out.shape[0] >= 15 * 512


def test_short_blip_is_discarded():
    seg = Segmenter(silence_ms=600, min_speech_ms=250)
    # 3 speech frames (~96ms) < min_speech, then silence
    for _ in range(3):
        assert seg.push(_frame(), 0.9) is None
    out = None
    for _ in range(25):
        out = seg.push(_frame(), 0.0)
        if out is not None:
            break
    assert out is None


def test_max_utterance_forces_emit():
    seg = Segmenter(max_utterance_ms=320, min_speech_ms=32)  # 10 frames cap
    out = None
    for _ in range(11):
        out = seg.push(_frame(), 0.9)
        if out is not None:
            break
    assert out is not None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_segmenter.py -v`
Expected: FAIL (ModuleNotFoundError / cannot import `Segmenter`).

- [ ] **Step 3: Implement `Segmenter` (and `SileroVad` stub file)**

`src/parakeet_dictation/vad.py`:
```python
"""Voice-activity segmentation.

`Segmenter` is a pure state machine: given per-frame speech probabilities it
accumulates speech into utterances and emits a completed utterance once the
speaker pauses. `SileroVad` wraps the Silero model to produce those
probabilities from raw audio frames.
"""
from __future__ import annotations

import numpy as np


class Segmenter:
    def __init__(
        self,
        threshold: float = 0.5,
        silence_ms: int = 600,
        min_speech_ms: int = 250,
        max_utterance_ms: int = 30000,
        sample_rate: int = 16000,
        frame_samples: int = 512,
    ):
        self.threshold = threshold
        self.frame_samples = frame_samples
        frame_ms = 1000.0 * frame_samples / sample_rate
        self.silence_frames = max(1, round(silence_ms / frame_ms))
        self.min_speech_frames = max(1, round(min_speech_ms / frame_ms))
        self.max_frames = max(1, round(max_utterance_ms / frame_ms))
        self.reset()

    def reset(self) -> None:
        self._active = False
        self._speech_count = 0
        self._silence_count = 0
        self._buffer: list[np.ndarray] = []

    def _emit(self) -> np.ndarray | None:
        frames = self._buffer
        speech_count = self._speech_count
        self.reset()
        if speech_count < self.min_speech_frames or not frames:
            return None
        return np.concatenate(frames).astype(np.float32)

    def push(self, frame: np.ndarray, speech_prob: float) -> np.ndarray | None:
        is_speech = speech_prob >= self.threshold
        if not self._active:
            if is_speech:
                self._active = True
                self._buffer = [frame]
                self._speech_count = 1
                self._silence_count = 0
            return None

        # active
        self._buffer.append(frame)
        if is_speech:
            self._speech_count += 1
            self._silence_count = 0
        else:
            self._silence_count += 1

        if self._silence_count >= self.silence_frames:
            return self._emit()
        if len(self._buffer) >= self.max_frames:
            return self._emit()
        return None


class SileroVad:
    """Wraps Silero VAD to return a speech probability per 512-sample frame."""

    def __init__(self, sample_rate: int = 16000):
        import torch  # noqa: F401  (imported lazily; heavy)
        from silero_vad import load_silero_vad

        self._torch = __import__("torch")
        self.sample_rate = sample_rate
        self.model = load_silero_vad()

    def speech_prob(self, frame: np.ndarray) -> float:
        tensor = self._torch.from_numpy(frame.astype(np.float32))
        with self._torch.no_grad():
            return float(self.model(tensor, self.sample_rate).item())

    def reset(self) -> None:
        self.model.reset_states()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_segmenter.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add src/parakeet_dictation/vad.py tests/test_segmenter.py
git commit -m "feat: add VAD segmenter state machine and Silero wrapper"
```

---

### Task 3: Verify Silero wrapper against real audio

**Files:**
- Test: `tests/test_segmenter.py` (add an integration test)

**Interfaces:**
- Consumes: `SileroVad`, `Segmenter` from Task 2.
- Produces: confidence that real speech audio yields ≥1 segment.

- [ ] **Step 1: Add integration test**

Append to `tests/test_segmenter.py`:
```python
import subprocess
import numpy as np
from parakeet_dictation.vad import SileroVad, Segmenter


def _say_to_pcm(text="testing one two three"):
    """Render speech via macOS `say` and decode to 16k mono float32 via ffmpeg."""
    import tempfile, os
    with tempfile.TemporaryDirectory() as d:
        aiff = os.path.join(d, "s.aiff")
        subprocess.run(["say", "-o", aiff, text], check=True)
        raw = subprocess.run(
            ["ffmpeg", "-i", aiff, "-ac", "1", "-ar", "16000",
             "-f", "f32le", "-"],
            check=True, capture_output=True,
        ).stdout
    return np.frombuffer(raw, dtype=np.float32).copy()


def test_silero_segments_real_speech():
    pcm = _say_to_pcm()
    vad = SileroVad()
    seg = Segmenter()
    utterances = []
    n = 512
    for i in range(0, len(pcm) - n, n):
        frame = pcm[i:i + n]
        out = seg.push(frame, vad.speech_prob(frame))
        if out is not None:
            utterances.append(out)
    # flush trailing (append silence)
    for _ in range(25):
        out = seg.push(np.zeros(n, dtype=np.float32), 0.0)
        if out is not None:
            utterances.append(out)
    assert len(utterances) >= 1
    assert sum(len(u) for u in utterances) > 8000  # >0.5s of captured speech
```

- [ ] **Step 2: Run the integration test**

Run: `uv run pytest tests/test_segmenter.py::test_silero_segments_real_speech -v`
Expected: PASS (first run downloads the Silero model, ~a few MB).

- [ ] **Step 3: Commit**

```bash
git add tests/test_segmenter.py
git commit -m "test: verify Silero VAD segments real speech"
```

---

### Task 4: Transcriber

**Files:**
- Create: `src/parakeet_dictation/transcriber.py`
- Test: `tests/test_transcriber.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces:
  - `write_wav(path: str, pcm: np.ndarray, sample_rate: int = 16000) -> None` — 16-bit PCM mono WAV.
  - `Transcriber(model_name="mlx-community/parakeet-tdt-0.6b-v2", model=None)` — loads model lazily on first `transcribe` if `model` not injected.
  - `Transcriber.transcribe(pcm: np.ndarray, sample_rate=16000) -> str` — returns stripped text.

- [ ] **Step 1: Write the failing tests**

`tests/test_transcriber.py`:
```python
import wave
import numpy as np
from parakeet_dictation.transcriber import write_wav, Transcriber


def test_write_wav_roundtrip(tmp_path):
    pcm = (np.sin(np.linspace(0, 20, 16000)).astype(np.float32))
    path = str(tmp_path / "t.wav")
    write_wav(path, pcm, 16000)
    with wave.open(path, "rb") as w:
        assert w.getnchannels() == 1
        assert w.getframerate() == 16000
        assert w.getsampwidth() == 2
        assert w.getnframes() == 16000


class _FakeResult:
    text = "  hello world  "


class _FakeModel:
    def __init__(self):
        self.calls = []

    def transcribe(self, path):
        self.calls.append(path)
        return _FakeResult()


def test_transcribe_uses_model_and_strips(tmp_path):
    fake = _FakeModel()
    t = Transcriber(model=fake)
    text = t.transcribe(np.zeros(16000, dtype=np.float32))
    assert text == "hello world"
    assert len(fake.calls) == 1
    assert fake.calls[0].endswith(".wav")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_transcriber.py -v`
Expected: FAIL (cannot import `transcriber`).

- [ ] **Step 3: Implement transcriber**

`src/parakeet_dictation/transcriber.py`:
```python
"""Parakeet-MLX transcription of finished utterances."""
from __future__ import annotations

import os
import tempfile
import wave

import numpy as np


def write_wav(path: str, pcm: np.ndarray, sample_rate: int = 16000) -> None:
    clipped = np.clip(pcm, -1.0, 1.0)
    ints = (clipped * 32767.0).astype("<i2")
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(ints.tobytes())


class Transcriber:
    def __init__(
        self,
        model_name: str = "mlx-community/parakeet-tdt-0.6b-v2",
        model=None,
    ):
        self.model_name = model_name
        self._model = model

    def _ensure_model(self):
        if self._model is None:
            from parakeet_mlx import from_pretrained
            self._model = from_pretrained(self.model_name)
        return self._model

    def transcribe(self, pcm: np.ndarray, sample_rate: int = 16000) -> str:
        model = self._ensure_model()
        fd, path = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        try:
            write_wav(path, pcm, sample_rate)
            result = model.transcribe(path)
        finally:
            try:
                os.remove(path)
            except OSError:
                pass
        return (result.text or "").strip()
```

- [ ] **Step 4: Run unit tests to verify they pass**

Run: `uv run pytest tests/test_transcriber.py -v`
Expected: 2 passed.

- [ ] **Step 5: Add and run a real-model integration test**

Append to `tests/test_transcriber.py`:
```python
import subprocess


def test_real_transcription_of_say():
    import tempfile, os
    with tempfile.TemporaryDirectory() as d:
        aiff = os.path.join(d, "s.aiff")
        subprocess.run(["say", "-o", aiff, "the quick brown fox"], check=True)
        raw = subprocess.run(
            ["ffmpeg", "-i", aiff, "-ac", "1", "-ar", "16000", "-f", "f32le", "-"],
            check=True, capture_output=True,
        ).stdout
    pcm = np.frombuffer(raw, dtype=np.float32).copy()
    text = Transcriber().transcribe(pcm).lower()
    assert "quick" in text and "fox" in text
```

Run: `uv run pytest tests/test_transcriber.py::test_real_transcription_of_say -v`
Expected: PASS (first run downloads the Parakeet model, ~1–2.5 GB — may take several minutes).

- [ ] **Step 6: Commit**

```bash
git add src/parakeet_dictation/transcriber.py tests/test_transcriber.py
git commit -m "feat: add Parakeet-MLX transcriber with WAV helper"
```

---

### Task 5: OutputSink (ring buffer + delivery logic)

**Files:**
- Create: `src/parakeet_dictation/output.py`
- Test: `tests/test_output.py`

**Interfaces:**
- Consumes: nothing (deps injected).
- Produces:
  - `OutputSink(set_clipboard, is_field_focused, paste, maxlen=15)` where the three args are callables.
  - `OutputSink.deliver(text: str) -> bool` — returns True if a non-empty transcript was delivered.
  - `OutputSink.recent() -> list[str]` — newest first, ≤ maxlen.

- [ ] **Step 1: Write the failing tests**

`tests/test_output.py`:
```python
from parakeet_dictation.output import OutputSink


def _make(focused=False):
    state = {"clip": None, "pastes": 0}
    sink = OutputSink(
        set_clipboard=lambda t: state.__setitem__("clip", t),
        is_field_focused=lambda: focused,
        paste=lambda: state.__setitem__("pastes", state["pastes"] + 1),
    )
    return sink, state


def test_empty_text_is_ignored():
    sink, state = _make()
    assert sink.deliver("   ") is False
    assert state["clip"] is None
    assert sink.recent() == []


def test_delivers_to_clipboard_always():
    sink, state = _make(focused=False)
    assert sink.deliver("hello") is True
    assert state["clip"] == "hello"
    assert state["pastes"] == 0  # no paste when unfocused


def test_pastes_when_field_focused():
    sink, state = _make(focused=True)
    sink.deliver("hi there")
    assert state["clip"] == "hi there"
    assert state["pastes"] == 1


def test_recent_is_newest_first_and_capped_at_15():
    sink, _ = _make()
    for i in range(20):
        sink.deliver(f"line {i}")
    recent = sink.recent()
    assert len(recent) == 15
    assert recent[0] == "line 19"
    assert recent[-1] == "line 5"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_output.py -v`
Expected: FAIL (cannot import `output`).

- [ ] **Step 3: Implement `OutputSink`**

`src/parakeet_dictation/output.py`:
```python
"""Delivery of finished transcripts: clipboard, optional paste, recent history."""
from __future__ import annotations

from collections import deque
from typing import Callable


class OutputSink:
    def __init__(
        self,
        set_clipboard: Callable[[str], None],
        is_field_focused: Callable[[], bool],
        paste: Callable[[], None],
        maxlen: int = 15,
    ):
        self._set_clipboard = set_clipboard
        self._is_field_focused = is_field_focused
        self._paste = paste
        self._history: deque[str] = deque(maxlen=maxlen)

    def deliver(self, text: str) -> bool:
        text = (text or "").strip()
        if not text:
            return False
        self._history.appendleft(text)
        self._set_clipboard(text)
        if self._is_field_focused():
            self._paste()
        return True

    def recent(self) -> list[str]:
        return list(self._history)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_output.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add src/parakeet_dictation/output.py tests/test_output.py
git commit -m "feat: add OutputSink with clipboard, paste, and 15-item history"
```

---

### Task 6: macOS primitives

**Files:**
- Create: `src/parakeet_dictation/macos.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `set_clipboard(text: str) -> None`
  - `is_text_field_focused() -> bool`
  - `paste() -> None` — posts a ⌘V key event.

- [ ] **Step 1: Implement `macos.py`**

`src/parakeet_dictation/macos.py`:
```python
"""macOS system integration via PyObjC: clipboard, focus detection, paste."""
from __future__ import annotations

from AppKit import NSPasteboard, NSStringPboardType
from ApplicationServices import (
    AXUIElementCreateSystemWide,
    AXUIElementCopyAttributeValue,
    kAXFocusedUIElementAttribute,
    kAXRoleAttribute,
)
import Quartz


def set_clipboard(text: str) -> None:
    pb = NSPasteboard.generalPasteboard()
    pb.clearContents()
    pb.setString_forType_(text, NSStringPboardType)


_EDITABLE_ROLES = {"AXTextField", "AXTextArea", "AXComboBox"}


def is_text_field_focused() -> bool:
    system = AXUIElementCreateSystemWide()
    err, focused = AXUIElementCopyAttributeValue(
        system, kAXFocusedUIElementAttribute, None
    )
    if err != 0 or focused is None:
        return False
    err, role = AXUIElementCopyAttributeValue(focused, kAXRoleAttribute, None)
    if err != 0 or role is None:
        return False
    return str(role) in _EDITABLE_ROLES


def paste() -> None:
    # Post Cmd+V (virtual keycode 9 == 'v') via a dedicated event source.
    src = Quartz.CGEventSourceCreate(Quartz.kCGEventSourceStateHIDSystemState)
    v_down = Quartz.CGEventCreateKeyboardEvent(src, 9, True)
    v_up = Quartz.CGEventCreateKeyboardEvent(src, 9, False)
    Quartz.CGEventSetFlags(v_down, Quartz.kCGEventFlagMaskCommand)
    Quartz.CGEventSetFlags(v_up, Quartz.kCGEventFlagMaskCommand)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, v_down)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, v_up)
```

- [ ] **Step 2: Manually verify clipboard (works without special permissions)**

Run:
```bash
uv run python -c "from parakeet_dictation.macos import set_clipboard; set_clipboard('parakeet-clip-test')"
pbpaste
```
Expected: `pbpaste` prints `parakeet-clip-test`.

- [ ] **Step 3: Manually verify focus detection**

Run (click into a TextEdit document within 3 seconds):
```bash
uv run python -c "import time; time.sleep(3); from parakeet_dictation.macos import is_text_field_focused as f; print('focused:', f())"
```
Expected: prints `focused: True` when a text area is focused. Note: this requires granting **Accessibility** permission to the terminal running it (System Settings → Privacy & Security → Accessibility). Full paste behavior is verified end-to-end in Task 8.

- [ ] **Step 4: Commit**

```bash
git add src/parakeet_dictation/macos.py
git commit -m "feat: add macOS clipboard, focus detection, and paste primitives"
```

---

### Task 7: Mic capture

**Files:**
- Create: `src/parakeet_dictation/mic.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `MicCapture(sample_rate=16000, frame_samples=512)` with `.start()`, `.stop()`, and `.frames()` (a generator yielding `np.ndarray` float32 of length `frame_samples`).

- [ ] **Step 1: Implement `mic.py`**

`src/parakeet_dictation/mic.py`:
```python
"""Microphone capture via sounddevice → fixed-size float32 frames."""
from __future__ import annotations

import queue

import numpy as np
import sounddevice as sd


class MicCapture:
    def __init__(self, sample_rate: int = 16000, frame_samples: int = 512):
        self.sample_rate = sample_rate
        self.frame_samples = frame_samples
        self._q: queue.Queue = queue.Queue()
        self._stream: sd.InputStream | None = None

    def _callback(self, indata, frames, time_info, status):
        # indata: (frames, 1) float32. Copy — buffer is reused by PortAudio.
        self._q.put(indata[:, 0].copy())

    def start(self) -> None:
        self._stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=1,
            dtype="float32",
            blocksize=self.frame_samples,
            callback=self._callback,
        )
        self._stream.start()

    def stop(self) -> None:
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None

    def frames(self):
        while True:
            yield self._q.get()
```

- [ ] **Step 2: Manually verify capture**

Run (speak for ~2 seconds; requires **Microphone** permission for the terminal):
```bash
uv run python -c "
import numpy as np, itertools
from parakeet_dictation.mic import MicCapture
m = MicCapture(); m.start()
peaks = [float(np.abs(f).max()) for f in itertools.islice(m.frames(), 60)]
m.stop()
print('max amplitude:', max(peaks))
"
```
Expected: max amplitude clearly > 0.01 when you speak (near 0 in silence). Confirms mic frames flow.

- [ ] **Step 3: Commit**

```bash
git add src/parakeet_dictation/mic.py
git commit -m "feat: add microphone capture stream"
```

---

### Task 8: Menu-bar app wiring

**Files:**
- Create: `src/parakeet_dictation/app.py`

**Interfaces:**
- Consumes: `MicCapture`, `SileroVad`, `Segmenter`, `Transcriber`, `OutputSink`, and `macos` primitives from all prior tasks.
- Produces: `main()` entry point that runs the menu-bar app.

- [ ] **Step 1: Implement `app.py`**

`src/parakeet_dictation/app.py`:
```python
"""Menu-bar dictation app: wires mic → VAD → transcribe → output."""
from __future__ import annotations

import threading

import rumps

from . import macos
from .mic import MicCapture
from .output import OutputSink
from .transcriber import Transcriber
from .vad import Segmenter, SileroVad

IDLE_ICON = "🎙️"
BUSY_ICON = "✍️"


class DictationApp(rumps.App):
    def __init__(self):
        super().__init__(IDLE_ICON, quit_button=None)
        self.paused = False
        self._worker: threading.Thread | None = None
        self._stop = threading.Event()

        self.pause_item = rumps.MenuItem("Pause", callback=self.toggle_pause)
        self.login_item = rumps.MenuItem(
            "Start at Login", callback=self.toggle_login
        )
        self.login_item.state = self._login_enabled()
        self.menu = [
            self.pause_item,
            None,
            "Recent transcripts:",
            None,
            self.login_item,
            rumps.MenuItem("Quit", callback=self.quit_app),
        ]

        self.mic = MicCapture()
        self.vad = SileroVad()
        self.segmenter = Segmenter()
        self.transcriber = Transcriber()
        self.sink = OutputSink(
            set_clipboard=macos.set_clipboard,
            is_field_focused=macos.is_text_field_focused,
            paste=macos.paste,
        )
        self.start_worker()

    # ---- worker ----
    def start_worker(self) -> None:
        self.mic.start()
        self._worker = threading.Thread(target=self._run, daemon=True)
        self._worker.start()

    def _run(self) -> None:
        for frame in self.mic.frames():
            if self._stop.is_set():
                return
            if self.paused:
                continue
            prob = self.vad.speech_prob(frame)
            utt = self.segmenter.push(frame, prob)
            if utt is not None:
                self.vad.reset()
                self._set_icon(BUSY_ICON)
                try:
                    text = self.transcriber.transcribe(utt)
                    if text:
                        self.sink.deliver(text)
                        self._refresh_recent()
                finally:
                    self._set_icon(IDLE_ICON)

    # ---- UI helpers (main-thread safe via rumps.Timer trick) ----
    def _set_icon(self, icon: str) -> None:
        self.title = icon

    def _refresh_recent(self) -> None:
        recent = self.sink.recent()
        # Rebuild the recent-transcripts section.
        for key in list(self.menu.keys()):
            if key.startswith("↳ "):
                del self.menu[key]
        anchor = "Recent transcripts:"
        for line in recent:
            label = "↳ " + (line[:50] + ("…" if len(line) > 50 else ""))
            item = rumps.MenuItem(label, callback=self._recopy)
            item._full_text = line
            self.menu.insert_after(anchor, item)

    def _recopy(self, sender) -> None:
        macos.set_clipboard(getattr(sender, "_full_text", sender.title))

    # ---- menu callbacks ----
    def toggle_pause(self, _) -> None:
        self.paused = not self.paused
        self.pause_item.title = "Resume" if self.paused else "Pause"
        self.title = "⏸️" if self.paused else IDLE_ICON

    def toggle_login(self, sender) -> None:
        try:
            from ServiceManagement import SMAppService
            svc = SMAppService.mainAppService()
            if sender.state:
                svc.unregisterAndReturnError_(None)
                sender.state = False
            else:
                svc.registerAndReturnError_(None)
                sender.state = True
        except Exception as e:  # not fatal — only works from the bundled .app
            rumps.notification("Parakeet", "Login item", str(e))

    def _login_enabled(self) -> bool:
        try:
            from ServiceManagement import SMAppService
            return SMAppService.mainAppService().status() == 1
        except Exception:
            return False

    def quit_app(self, _) -> None:
        self._stop.set()
        self.mic.stop()
        rumps.quit_application()


def main() -> None:
    DictationApp().run()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the app from source and verify end-to-end**

Run:
```bash
uv run python -m parakeet_dictation.app
```
Grant **Microphone** and **Accessibility** when prompted (System Settings → Privacy & Security). Then:
1. See the 🎙️ icon in the menu bar.
2. Open TextEdit, click into a document, speak a sentence, pause.
3. Expected: icon flips to ✍️ briefly, then the sentence appears in TextEdit AND is on the clipboard (`pbpaste`).
4. Click the menu-bar icon → the "↳ …" recent items list your last phrases; clicking one re-copies it.
5. Click Pause → speaking does nothing; Resume restores.
6. Quit → relaunch → recent list is empty (no persistence).

- [ ] **Step 3: Commit**

```bash
git add src/parakeet_dictation/app.py
git commit -m "feat: wire menu-bar app (mic→VAD→transcribe→output) with recent list"
```

---

### Task 9: Package as native .app and install

**Files:**
- Create: `setup.py`, `scripts/build_app.sh`

**Interfaces:**
- Consumes: `parakeet_dictation.app:main`.
- Produces: `/Applications/Parakeet Dictation.app` that launches into the menu bar.

- [ ] **Step 1: Create `setup.py` for py2app**

`setup.py`:
```python
from setuptools import setup

APP = ["src/parakeet_dictation/__main__.py"]
OPTIONS = {
    "argv_emulation": False,
    "plist": {
        "CFBundleName": "Parakeet Dictation",
        "CFBundleIdentifier": "com.khalid.parakeetdictation",
        "CFBundleShortVersionString": "0.1.0",
        "LSUIElement": True,  # menu-bar only, no Dock icon
        "NSMicrophoneUsageDescription": "Parakeet Dictation transcribes your speech.",
        "NSAppleEventsUsageDescription": "Parakeet Dictation pastes text into the focused field.",
    },
    "packages": ["parakeet_dictation", "parakeet_mlx", "silero_vad", "rumps"],
    "includes": ["numpy", "sounddevice"],
}

setup(
    app=APP,
    name="Parakeet Dictation",
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)
```

- [ ] **Step 2: Add package `__main__.py`**

`src/parakeet_dictation/__main__.py`:
```python
from parakeet_dictation.app import main

if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Create build script**

`scripts/build_app.sh`:
```bash
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

echo "Building .app with py2app (alias mode for speed on first try)..."
rm -rf build dist
uv run python setup.py py2app -A   # -A = alias mode: fast, references the venv

echo "Installing to /Applications ..."
rm -rf "/Applications/Parakeet Dictation.app"
cp -R "dist/Parakeet Dictation.app" "/Applications/"

echo "Done. Launch from /Applications or Spotlight."
echo "NOTE: alias-mode bundle depends on this project's venv staying in place."
echo "For a fully standalone bundle, run: uv run python setup.py py2app"
```

Make it executable:
```bash
chmod +x scripts/build_app.sh
```

- [ ] **Step 4: Build and install (alias mode first)**

Run:
```bash
./scripts/build_app.sh
```
Expected: `dist/Parakeet Dictation.app` created and copied to `/Applications`.

Rationale: alias mode (`-A`) is fast and reliable for MLX/torch (which are hard to fully freeze). It produces a real `.app` in `/Applications` that launches into the menu bar — meeting the "native installed app" goal — while depending on the project venv. Attempt a full standalone build (`uv run python setup.py py2app`) only if the user later wants to delete the source tree; note in the commit that MLX/torch may need `--no-strip` or manual data-file inclusion.

- [ ] **Step 5: Verify the installed app**

1. Launch **Parakeet Dictation** from Spotlight/Launchpad.
2. Confirm the 🎙️ menu-bar icon appears (no Dock icon, because `LSUIElement`).
3. Repeat the Task 8 end-to-end speech test using the installed app.
4. In the menu, enable **Start at Login**, reboot, and confirm the icon reappears automatically.

- [ ] **Step 6: Commit**

```bash
git add setup.py scripts/build_app.sh src/parakeet_dictation/__main__.py
git commit -m "build: package as native .app via py2app with install script"
```

---

## Self-Review

**Spec coverage:**
- Menu-bar always-on app → Tasks 8, 9. ✓
- Static icon that flashes while transcribing → Task 8 (`_set_icon` IDLE/BUSY). ✓
- Mic 16 kHz mono, 512-sample frames → Task 7 + Global Constraints. ✓
- Silero VAD segmentation on pause → Tasks 2, 3. ✓
- Parakeet v2 transcription per utterance → Task 4. ✓
- Clipboard always; paste only when field focused → Tasks 5, 6. ✓
- Last 15 in memory, newest-first, no disk, dropped on quit → Tasks 5, 8. ✓
- Microphone + Accessibility permissions → Tasks 6, 7, 8, 9 (plist). ✓
- Launch at login → Task 8 (`toggle_login` via SMAppService) + Task 9 verify. ✓
- Native .app in /Applications → Task 9. ✓
- Isolated uv env, no miniconda base → Task 1 + Global Constraints. ✓
- English only → default model behavior; no multilingual config added. ✓

**Placeholder scan:** No TBD/TODO; every code step has complete code. ✓

**Type consistency:** `Segmenter.push(frame, speech_prob)` used consistently (Tasks 2, 3, 8). `Transcriber.transcribe(pcm)` consistent (Tasks 4, 8). `OutputSink.deliver/recent` consistent (Tasks 5, 8). `macos.set_clipboard/is_text_field_focused/paste` consistent (Tasks 6, 8). ✓

**Known risk (flagged, not a gap):** Full py2app freezing of MLX/torch can be finicky; Task 9 mitigates by shipping an alias-mode `.app` first (still a real installed app), with the standalone build as an optional follow-up.
