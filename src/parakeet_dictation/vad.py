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
