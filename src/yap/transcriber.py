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
