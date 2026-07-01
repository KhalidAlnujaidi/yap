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
