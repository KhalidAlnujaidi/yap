"""Delivery of finished transcripts: clipboard, optional auto-paste, history."""
from __future__ import annotations

from collections import deque
from typing import Callable


class OutputSink:
    def __init__(
        self,
        set_clipboard: Callable[[str], None],
        paste: Callable[[], None],
        auto_paste: bool = True,
        maxlen: int = 15,
    ):
        self._set_clipboard = set_clipboard
        self._paste = paste
        self.auto_paste = auto_paste
        self._history: deque[str] = deque(maxlen=maxlen)

    def deliver(self, text: str) -> bool:
        text = (text or "").strip()
        if not text:
            return False
        self._history.appendleft(text)
        self._set_clipboard(text)
        # Always set the clipboard; synthesize ⌘V to drop it at the cursor when
        # auto-paste is on. We paste unconditionally rather than guessing at the
        # focused element's Accessibility role, because code editors (Sublime,
        # VS Code, terminals) don't report a standard text-field role.
        if self.auto_paste:
            self._paste()
        return True

    def recent(self) -> list[str]:
        return list(self._history)
