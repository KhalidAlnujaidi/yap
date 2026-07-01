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
