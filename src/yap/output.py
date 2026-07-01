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
