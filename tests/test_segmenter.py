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


import subprocess
from parakeet_dictation.vad import SileroVad


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
