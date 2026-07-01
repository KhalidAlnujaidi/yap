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
