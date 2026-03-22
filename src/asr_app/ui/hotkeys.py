from __future__ import annotations

from PyQt6.QtCore import Qt

from ..i18n import t


MODIFIER_KEYS = {
    int(Qt.Key.Key_Control),
    int(Qt.Key.Key_Shift),
    int(Qt.Key.Key_Alt),
    int(Qt.Key.Key_Meta),
}

SPECIAL_HOTKEY_NAMES = {
    int(Qt.Key.Key_CapsLock): "caps lock",
    int(Qt.Key.Key_Space): "space",
    int(Qt.Key.Key_Return): "enter",
    int(Qt.Key.Key_Enter): "enter",
    int(Qt.Key.Key_Tab): "tab",
    int(Qt.Key.Key_Backtab): "tab",
    int(Qt.Key.Key_Backspace): "backspace",
    int(Qt.Key.Key_Escape): "esc",
    int(Qt.Key.Key_Insert): "insert",
    int(Qt.Key.Key_Delete): "delete",
    int(Qt.Key.Key_Home): "home",
    int(Qt.Key.Key_End): "end",
    int(Qt.Key.Key_PageUp): "page up",
    int(Qt.Key.Key_PageDown): "page down",
    int(Qt.Key.Key_Left): "left",
    int(Qt.Key.Key_Right): "right",
    int(Qt.Key.Key_Up): "up",
    int(Qt.Key.Key_Down): "down",
}


def qt_key_to_hotkey_name(key: int, text: str) -> str:
    if key in SPECIAL_HOTKEY_NAMES:
        return SPECIAL_HOTKEY_NAMES[key]
    if int(Qt.Key.Key_F1) <= key <= int(Qt.Key.Key_F35):
        return f"f{key - int(Qt.Key.Key_F1) + 1}"
    raw = (text or "").strip().lower()
    return raw


def build_hotkey_from_key_event(key: int, text: str, modifiers: int) -> str:
    if key in MODIFIER_KEYS:
        return ""

    parts: list[str] = []
    modifier_flags = Qt.KeyboardModifier(modifiers)
    if modifier_flags & Qt.KeyboardModifier.ControlModifier:
        parts.append("ctrl")
    if modifier_flags & Qt.KeyboardModifier.AltModifier:
        parts.append("alt")
    if modifier_flags & Qt.KeyboardModifier.ShiftModifier:
        parts.append("shift")
    if modifier_flags & Qt.KeyboardModifier.MetaModifier:
        parts.append("windows")

    key_name = qt_key_to_hotkey_name(key, text)
    if not key_name:
        return ""
    if key_name not in parts:
        parts.append(key_name)
    return "+".join(parts)


def format_hotkey_label(hotkey: str | None) -> str:
    if not hotkey:
        return t("common.not_configured")
    parts = []
    for chunk in str(hotkey).split("+"):
        item = chunk.strip()
        lowered = item.lower()
        if lowered == "caps lock":
            parts.append("Caps Lock")
        elif lowered == "page up":
            parts.append("Page Up")
        elif lowered == "page down":
            parts.append("Page Down")
        elif lowered.startswith("f") and lowered[1:].isdigit():
            parts.append(lowered.upper())
        elif len(item) == 1:
            parts.append(item.upper())
        else:
            parts.append(item.title())
    return " + ".join(parts)
