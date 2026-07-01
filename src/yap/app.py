"""Yap menu-bar app: wires mic → VAD → transcribe → output."""
from __future__ import annotations

import threading

import rumps

from . import macos
from .mic import MicCapture
from .output import OutputSink
from .transcriber import Transcriber
from .vad import Segmenter, SileroVad

IDLE_ICON = "🦜"       # waiting / silent
BUSY_ICON = "💬"       # actively hearing speech
PAUSED_ICON = "😴"     # paused


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
        speaking = False
        for frame in self.mic.frames():
            if self._stop.is_set():
                return
            if self.paused:
                continue
            prob = self.vad.speech_prob(frame)

            # Live reaction: flip the icon on speech-state changes only.
            is_speech = prob >= self.segmenter.threshold
            if is_speech != speaking:
                speaking = is_speech
                self._set_icon(BUSY_ICON if speaking else IDLE_ICON)

            utt = self.segmenter.push(frame, prob)
            if utt is not None:
                self.vad.reset()
                speaking = False
                self._set_icon(IDLE_ICON)
                try:
                    text = self.transcriber.transcribe(utt)
                    if text:
                        self.sink.deliver(text)
                        self._refresh_recent()
                except Exception:
                    pass

    # ---- UI helpers ----
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
        self.title = PAUSED_ICON if self.paused else IDLE_ICON

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
            rumps.notification("Yap", "Login item", str(e))

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
    # Force menu-bar-only (no Dock icon) regardless of how the bundle's
    # Info.plist is resolved when launched via the venv-python launcher.
    try:
        from AppKit import (
            NSApplication,
            NSApplicationActivationPolicyAccessory,
        )
        NSApplication.sharedApplication().setActivationPolicy_(
            NSApplicationActivationPolicyAccessory
        )
    except Exception:
        pass
    DictationApp().run()


if __name__ == "__main__":
    main()
