<div align="center">

# 🦜 Yap

### Stop typing. Start yapping.

**Real-time, 100% on-device dictation for Apple Silicon Macs.**
Speak anywhere — your words land where your cursor is. No button. No cloud.
**One command to install. No model to pick, no API keys, no settings — it just runs.**

[![License: MIT](https://img.shields.io/badge/License-MIT-black.svg)](LICENSE)
![Platform](https://img.shields.io/badge/platform-Apple%20Silicon-black)
![macOS](https://img.shields.io/badge/macOS-13%2B-black)
![Powered by MLX](https://img.shields.io/badge/powered%20by-MLX-black)

<!-- Demo GIF: drop the recording at docs/demo.gif and restore the line below.
<img src="docs/demo.gif" alt="Yap demo — talking into a text field, words appearing in real time" width="720">
-->

</div>

---

## The keyboard is the bottleneck

For fifty years, the way we get thoughts *into* a computer has barely changed: we type. But typing was never the fast path — it's the *slow* one we got used to.

A [Stanford study](https://engineering.stanford.edu/news/smartphone-speech-recognition-faster-and-more-accurate-typing) measured it directly: **speaking is ~3× faster than typing** (161 vs. 55 words per minute), with **20% fewer errors**. Average typing sits around 40 WPM; you *talk* at ~150.

And it matters more now than ever. If you spend your day **coding and talking to LLMs**, the keyboard is a tax on every prompt, every comment, every message. Your ideas are ready; your fingers are the throttle. Yap removes the throttle:

> **Think it → say it → it's text.** Everywhere on your Mac.

100% local. Nothing you say ever leaves your machine.

---

## What it does

- 🎙️ **Always-on, no button.** Sit in a quiet room and just talk — Yap detects speech automatically.
- ⚡ **Faster than real-time.** Powered by [NVIDIA Parakeet TDT 0.6B v2](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v2) running natively on Apple Silicon via [MLX](https://github.com/ml-explore/mlx). A sentence transcribes in a fraction of a second.
- 🖇️ **Lands where your cursor is.** Your words are typed straight in — editors, terminals, browsers, anywhere — and copied to your clipboard too.
- 🔒 **Private by design.** Fully on-device. No account, no network, no telemetry.
- 🦜 **Lives in your menu bar.** A parrot that flips to 💬 the instant it hears you and back to 🦜 when you pause. The last 15 phrases sit in the dropdown, one click to re-copy.
- 😴 **Pause anytime**, and **launch at login** with one toggle.

---

## Why Yap is different

Most dictation tools make *you* do the work first: pick a model, download gigabytes by hand, dig through settings — or paste in an API key and ship your voice off to someone else's cloud.

Yap has none of that.

```bash
curl -fsSL https://raw.githubusercontent.com/KhalidAlnujaidi/yap/main/install.sh | bash
```

**One command. No configuration. No API keys. No accounts.** It installs, pulls a state-of-the-art speech model once, and just runs — entirely on your device. That's the whole setup.

---

## Install

**One line** (Apple Silicon macOS, [Homebrew](https://brew.sh) required):

```bash
curl -fsSL https://raw.githubusercontent.com/KhalidAlnujaidi/yap/main/install.sh | bash
```

This installs `ffmpeg` + [`uv`](https://github.com/astral-sh/uv) if needed, grabs the speech model once (~1–2.5 GB), builds **Yap.app**, and drops it in `/Applications`.

Then launch **Yap** from Spotlight, grant **Microphone** + **Accessibility** on first run, and start talking.

<details>
<summary>Manual install</summary>

```bash
git clone https://github.com/KhalidAlnujaidi/yap.git
cd yap
brew install ffmpeg          # if you don't have it
uv sync                      # builds the env, downloads the model on first run
./scripts/build_app.sh       # builds Yap.app → /Applications
# or run from source without packaging:
uv run python -m yap
```
</details>

> **Why Accessibility?** It's what lets Yap paste transcribed text into whatever app you're focused on. It never reads your screen.

---

## Usage

| Action | What happens |
|---|---|
| **Speak, then pause** | The finished phrase is pasted at your cursor and copied to the clipboard. |
| **Auto-paste (⌘V)** | On by default; toggle off for clipboard-only mode. |
| **🦜 → 💬** | The menu-bar icon reacts live while you're talking. |
| **Click 🦜** | See your last 15 phrases — click any to re-copy it. |
| **Pause** (😴) | Stops listening until you resume. |
| **Start at Login** | Yap comes back automatically after a reboot. |

Nothing is written to disk — recent phrases live in memory only and vanish when you quit.

---

## How it works

```
  🎤 mic ──▶ Silero VAD ──▶ Parakeet-MLX ──▶ clipboard + ⌘V into focused field
  16 kHz     detects the      transcribes       your words, where you want them
  mono       spoken phrase    on-device
```

One small Python process: [`sounddevice`](https://python-sounddevice.readthedocs.io) captures the mic, [Silero VAD](https://github.com/snakers4/silero-vad) finds where a phrase starts and ends, [`parakeet-mlx`](https://github.com/senstella/parakeet-mlx) transcribes the finished phrase, and the result is delivered via the macOS clipboard + a synthesized ⌘V. A [`rumps`](https://github.com/jaredks/rumps) menu-bar shell ties it together. Transcribing *whole phrases* (rather than a live token stream) means full-context accuracy with no glitchy word-by-word rewrites — and on an M-series chip it's fast enough to feel instant.

### Tuning

The pause length and sensitivity live as constants on `Segmenter` in [`src/yap/vad.py`](src/yap/vad.py) — tweak `silence_ms` (default `600`) if it fires too eagerly or waits too long.

---

## Requirements

- **Apple Silicon** Mac (M1/M2/M3/M4). Intel is not supported yet.
- **macOS 13+**
- **Homebrew** (for `ffmpeg`)
- ~1–2.5 GB disk for the speech model (downloaded once, cached in `~/.cache/huggingface`)

---

## Roadmap & contributing

Yap is intentionally small and Apple-Silicon-first. It's **MIT-licensed** — fork it, ship it, extend it. Especially welcome:

- 🧠 **An optional tiny local LLM that polishes raw speech into clean, grammatical sentences** — still 100% on-device, no keys, opt-in for when you want prose instead of verbatim.
- 🪟 **Windows / 🐧 Linux** ports (swap the macOS clipboard/paste/menu-bar layer)
- 🌍 Multilingual models (Parakeet has multilingual variants)
- ⌨️ A push-to-talk / hotkey mode
- 🎛️ A settings UI for the VAD knobs

Open an issue or PR — the architecture is deliberately modular (mic / VAD / transcriber / output are independent, testable units).

---

## Credits

- [NVIDIA Parakeet TDT 0.6B v2](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v2) — the speech model
- [`parakeet-mlx`](https://github.com/senstella/parakeet-mlx) by senstella — Apple Silicon port
- [Silero VAD](https://github.com/snakers4/silero-vad) — voice activity detection
- [`rumps`](https://github.com/jaredks/rumps) — Python macOS menu-bar apps

## License

[MIT](LICENSE) © 2026 Khalid Alnujaidi — built for the community. Go yap.
