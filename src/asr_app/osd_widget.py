"""PyQt6 OSD bubble used by realtime ASR."""

from __future__ import annotations

import ctypes
import logging
import math
from dataclasses import dataclass

from PyQt6.QtCore import QEasingCurve, QPoint, QPointF, QRectF, QPropertyAnimation, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QGuiApplication, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QGraphicsOpacityEffect, QWidget

from .caret_locator import physical_to_logical_qt_point
from .i18n import t


logger = logging.getLogger("asr")

GWL_EXSTYLE = -20
WS_EX_NOACTIVATE = 0x08000000
WS_EX_TOOLWINDOW = 0x00000080

_user32 = ctypes.windll.user32
_GetWindowLong = _user32.GetWindowLongW
_SetWindowLong = _user32.SetWindowLongW


@dataclass(frozen=True)
class BubbleTextLayout:
    lines: list[str]
    text_width: int
    text_height: int
    text_box_width: int
    bubble_width: int
    bubble_body_height: int


class OsdBubble(QWidget):
    sig_show = pyqtSignal(int, int, int, str)
    sig_update_stash = pyqtSignal(str)
    sig_update_completed = pyqtSignal(str)
    sig_set_phase = pyqtSignal(str)
    sig_hide = pyqtSignal()

    RADIUS = 12
    ARROW_H = 8
    ARROW_HALF_W = 7
    DOT_RADIUS = 4
    DOT_X = 18
    MIN_W = 176
    MAX_W = 960
    MIN_BODY_H = 48
    MAX_SCREEN_WIDTH_RATIO = 0.55
    MAX_SCREEN_HEIGHT_RATIO = 0.42
    SCREEN_MARGIN = 12
    PADDING_TOP = 12
    PADDING_BOTTOM = 12
    PADDING_LEFT = 36
    PADDING_RIGHT = 18
    DEFAULT_CARET_GAP = 20
    BELOW_CARET_GAP = 12
    TEXT_WIDTH_STEP = 28
    STASH_REGRESSION_TOLERANCE = 10

    PHASE_RECORDING = "recording"
    PHASE_POLISHING = "polishing"
    BREAK_CHARS = " \t,.;:!?)]}\u3001\uff0c\u3002\uff1b\uff1a\uff01\uff1f\uff09\u3011\u300b"

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)

        self._font = QFont("Microsoft YaHei UI", 11)
        self._font.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
        self._fm = QFontMetrics(self._font)

        self._phase = self.PHASE_RECORDING
        self._text = self.listening_text
        self._confirmed_text = ""
        self._stash_text = ""
        self._display_stash_text = ""
        self._text_color = QColor(255, 255, 255, 230)
        self._wrapped_lines = [self._text]
        self._anchor_x = 0
        self._anchor_y = 0
        self._anchor_screen_name = ""
        self._caret_height = 0
        self._bubble_body_height = self.MIN_BODY_H
        self._text_rect = QRectF()
        self._arrow_center_x = self.MIN_W / 2.0
        self._arrow_points_down = True
        self._dot_scale = 1.0
        self._hiding = False
        self._text_box_width = max(72, self.MIN_W - self.PADDING_LEFT - self.PADDING_RIGHT)

        self.setFixedSize(self.MIN_W, self.MIN_BODY_H + self.ARROW_H)

        self._pulse_timer = QTimer(self)
        self._pulse_timer.setInterval(50)
        self._pulse_timer.timeout.connect(self._pulse_tick)
        self._pulse_phase = 0.0

        self._confirm_timer = QTimer(self)
        self._confirm_timer.setSingleShot(True)
        self._confirm_timer.timeout.connect(self._restore_text_color)

        self._opacity_effect = QGraphicsOpacityEffect(self)
        self._opacity_effect.setOpacity(1.0)
        self.setGraphicsEffect(self._opacity_effect)

        self._fade_anim = QPropertyAnimation(self._opacity_effect, b"opacity", self)
        self._fade_anim.setDuration(180)
        self._fade_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._fade_anim.finished.connect(self._on_fade_finished)

        self.sig_show.connect(self._show_bubble)
        self.sig_update_stash.connect(self._update_stash)
        self.sig_update_completed.connect(self._update_completed)
        self.sig_set_phase.connect(self._set_phase)
        self.sig_hide.connect(self._hide_bubble)

    def showEvent(self, event):
        super().showEvent(event)
        hwnd = int(self.winId())
        ex_style = _GetWindowLong(hwnd, GWL_EXSTYLE)
        _SetWindowLong(hwnd, GWL_EXSTYLE, ex_style | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW)


    @property
    def listening_text(self) -> str:
        return t("osd.listening")

    @property
    def polishing_text(self) -> str:
        return t("osd.polishing")

    def refresh_language(self) -> None:
        self._text = self._compose_display_text()
        self._apply_layout()
        self.update()

    def _show_bubble(self, x: int, y: int, caret_height: int, source: str):
        self._fade_anim.stop()
        self._confirmed_text = ""
        self._stash_text = ""
        self._display_stash_text = ""
        self._phase = self.PHASE_RECORDING
        self._text = self.listening_text
        self._text_color = QColor(255, 255, 255, 230)
        self._hiding = False

        logical_x, logical_y, screen, scale = physical_to_logical_qt_point(x, y)
        self._anchor_x = logical_x
        self._anchor_y = logical_y
        self._caret_height = max(0, round(caret_height / max(scale, 1.0)))
        self._anchor_screen_name = screen.name() if screen is not None else ""

        logger.info(
            "[OSD] bubble anchor source=%s physical=(%d,%d) logical=(%d,%d) caret_h=%d screen=%s scale=%.3f",
            source,
            x,
            y,
            logical_x,
            logical_y,
            self._caret_height,
            self._anchor_screen_name or "-",
            scale,
        )

        screen_text_width = self._screen_text_width_limits(screen)[0]
        self._text_box_width = screen_text_width
        self._apply_layout()
        self._opacity_effect.setOpacity(1.0)
        self.show()
        self._pulse_timer.start()
        self.update()

    def _update_stash(self, text: str):
        if not text or self._phase != self.PHASE_RECORDING:
            return
        self._stash_text = text
        self._display_stash_text = self._merge_stash_for_display(self._display_stash_text, text)
        self._text = self._compose_display_text()
        self._text_color = QColor(255, 255, 255, 230)
        self._apply_layout()
        self.update()

    def _update_completed(self, text: str):
        if not text:
            return
        self._confirmed_text = self._append_completed_text(self._confirmed_text, text)
        self._stash_text = ""
        self._display_stash_text = ""
        self._text = self._compose_display_text()
        self._text_color = QColor(74, 222, 128)
        self._apply_layout()
        self.update()
        self._confirm_timer.start(600)

    def _set_phase(self, phase: str):
        if phase not in {self.PHASE_RECORDING, self.PHASE_POLISHING}:
            return
        self._phase = phase
        self._stash_text = ""
        self._display_stash_text = ""
        self._text = self._compose_display_text()
        self._text_color = QColor(255, 255, 255, 230)
        self._apply_layout()
        self.update()

    def _hide_bubble(self):
        if self._hiding or not self.isVisible():
            return
        self._hiding = True
        self._pulse_timer.stop()
        self._fade_anim.stop()
        self._fade_anim.setStartValue(self._opacity_effect.opacity())
        self._fade_anim.setEndValue(0.0)
        self._fade_anim.start()

    def _on_fade_finished(self):
        if self._hiding:
            self.hide()
            self._hiding = False

    def _restore_text_color(self):
        self._text_color = QColor(255, 255, 255, 230)
        self.update()

    def _pulse_tick(self):
        self._pulse_phase += 0.12
        if self._pulse_phase > 2 * math.pi:
            self._pulse_phase -= 2 * math.pi
        self._dot_scale = 1.0 + 0.25 * (0.5 + 0.5 * math.sin(self._pulse_phase))
        self.update()

    def _compose_display_text(self) -> str:
        base_text = self.listening_text
        if self._confirmed_text and self._display_stash_text:
            base_text = f"{self._confirmed_text}{self._display_stash_text}"
        elif self._confirmed_text:
            base_text = self._confirmed_text
        elif self._display_stash_text:
            base_text = self._display_stash_text

        if self._phase == self.PHASE_POLISHING:
            if base_text:
                return f"{base_text}\n{self.polishing_text}"
            return self.polishing_text
        return base_text

    def _append_completed_text(self, existing: str, new_text: str) -> str:
        if not existing:
            return new_text
        if not new_text:
            return existing

        needs_space = (
            existing[-1].isascii()
            and existing[-1].isalnum()
            and new_text[0].isascii()
            and new_text[0].isalnum()
        )
        separator = " " if needs_space else ""
        return f"{existing}{separator}{new_text}"

    def _merge_stash_for_display(self, existing: str, new_text: str) -> str:
        if not existing:
            return new_text
        if len(new_text) >= len(existing):
            return new_text
        if existing.startswith(new_text):
            regression = len(existing) - len(new_text)
            if regression <= self.STASH_REGRESSION_TOLERANCE:
                return existing
        return new_text

    def _target_screen(self):
        if self._anchor_screen_name:
            for candidate in QGuiApplication.screens():
                if candidate.name() == self._anchor_screen_name:
                    return candidate
        return QGuiApplication.screenAt(QPoint(self._anchor_x, self._anchor_y)) or QGuiApplication.primaryScreen()

    def _apply_layout(self):
        screen = self._target_screen()
        layout = self._measure_text_layout(screen)
        self._wrapped_lines = layout.lines
        self._bubble_body_height = layout.bubble_body_height
        self._text_box_width = layout.text_box_width

        total_height = layout.bubble_body_height + self.ARROW_H
        self.setFixedSize(layout.bubble_width, total_height)
        self._text_rect = self._build_text_rect(layout)
        self._reposition(screen)

    def _measure_text_layout(self, screen) -> BubbleTextLayout:
        text_min_width, text_max_width, available_height = self._screen_text_width_limits(screen)
        target_text_width = self._natural_text_width(text_min_width, text_max_width)
        text_box_width = self._grow_text_box_width(target_text_width, text_min_width, text_max_width)
        lines = self._wrap_text(self._text, text_box_width)
        lines = self._truncate_lines(lines, text_box_width, available_height)

        text_width = max((self._fm.horizontalAdvance(line) for line in lines), default=0)
        text_height = max(self._fm.lineSpacing() * len(lines), self._fm.height())
        bubble_width = max(self.MIN_W, min(self.MAX_W, text_box_width + self.PADDING_LEFT + self.PADDING_RIGHT))
        bubble_body_height = max(
            self.MIN_BODY_H,
            min(
                available_height,
                self.PADDING_TOP + text_height + self.PADDING_BOTTOM,
            ),
        )

        return BubbleTextLayout(lines, text_width, text_height, text_box_width, bubble_width, bubble_body_height)

    def _screen_text_width_limits(self, screen) -> tuple[int, int, int]:
        available_width = self.MAX_W
        available_height = 720
        if screen is not None:
            geo = screen.availableGeometry()
            available_width = min(
                self.MAX_W,
                max(
                    self.MIN_W,
                    round(geo.width() * self.MAX_SCREEN_WIDTH_RATIO) - self.SCREEN_MARGIN * 2,
                ),
            )
            available_height = max(
                self.MIN_BODY_H,
                round(geo.height() * self.MAX_SCREEN_HEIGHT_RATIO) - self.ARROW_H - self.SCREEN_MARGIN * 2,
            )

        text_min_width = max(72, self.MIN_W - self.PADDING_LEFT - self.PADDING_RIGHT)
        text_max_width = max(text_min_width, available_width - self.PADDING_LEFT - self.PADDING_RIGHT)
        return text_min_width, text_max_width, available_height

    def _natural_text_width(self, min_text_width: int, max_text_width: int) -> int:
        natural_width = max(self._fm.horizontalAdvance(part) for part in self._text.splitlines() or [""])
        return max(min_text_width, min(max_text_width, natural_width))

    def _grow_text_box_width(self, target_width: int, min_text_width: int, max_text_width: int) -> int:
        current = max(min_text_width, min(self._text_box_width, max_text_width))
        if target_width <= current:
            return current

        growth = max(self.TEXT_WIDTH_STEP, target_width - current)
        next_width = current + min(growth, self.TEXT_WIDTH_STEP * 2)
        return max(min_text_width, min(max_text_width, next_width))

    def _truncate_lines(self, lines: list[str], text_width: int, max_body_height: int) -> list[str]:
        line_height = self._fm.lineSpacing()
        max_lines = max(2, (max_body_height - self.PADDING_TOP - self.PADDING_BOTTOM) // max(line_height, 1))
        if len(lines) <= max_lines:
            return lines

        visible = lines[:max_lines]
        overflow_text = "".join(lines[max_lines - 1 :])
        visible[-1] = self._elide_text(overflow_text, text_width)
        return visible

    def _elide_text(self, text: str, text_width: int) -> str:
        if self._fm.horizontalAdvance(text) <= text_width:
            return text

        ellipsis = "..."
        buffer = text.rstrip()
        while buffer and self._fm.horizontalAdvance(buffer + ellipsis) > text_width:
            buffer = buffer[:-1].rstrip()
        return (buffer + ellipsis) if buffer else ellipsis

    def _wrap_text(self, text: str, max_width: int) -> list[str]:
        paragraphs = text.splitlines() or [text]
        lines: list[str] = []
        for paragraph in paragraphs:
            if not paragraph:
                lines.append("")
                continue
            lines.extend(self._wrap_paragraph(paragraph, max_width))
        return lines or [""]

    def _wrap_paragraph(self, text: str, max_width: int) -> list[str]:
        lines: list[str] = []
        current = ""

        for char in text:
            tentative = current + char
            if not current or self._fm.horizontalAdvance(tentative) <= max_width:
                current = tentative
                continue

            split_index = self._last_break_index(current)
            if split_index > 0:
                line = current[:split_index].rstrip()
                remainder = current[split_index:].lstrip() + char
                lines.append(line if line else current)
                current = remainder
            else:
                lines.append(current)
                current = char

        if current:
            lines.append(current.rstrip())
        return lines or [text]

    def _last_break_index(self, text: str) -> int:
        for index in range(len(text) - 1, -1, -1):
            if text[index] in self.BREAK_CHARS:
                return index + 1
        return 0

    def _build_text_rect(self, layout: BubbleTextLayout) -> QRectF:
        body_top = 0 if self._arrow_points_down else self.ARROW_H
        return QRectF(
            self.PADDING_LEFT,
            body_top + self.PADDING_TOP,
            max(0, self.width() - self.PADDING_LEFT - self.PADDING_RIGHT),
            layout.text_height,
        )

    def _caret_gap(self) -> int:
        if self._caret_height <= 0:
            return self.DEFAULT_CARET_GAP
        return max(self.DEFAULT_CARET_GAP, min(32, self._caret_height + 8))

    def _reposition(self, screen):
        if screen is None:
            return

        geo = screen.availableGeometry()
        width = self.width()
        total_height = self.height()
        gap = self._caret_gap()

        preferred_x = self._anchor_x - width // 2
        preferred_y = self._anchor_y - total_height - gap

        bx = max(geo.left() + self.SCREEN_MARGIN, min(preferred_x, geo.right() - width - self.SCREEN_MARGIN))
        by = preferred_y
        self._arrow_points_down = True

        if by < geo.top() + self.SCREEN_MARGIN:
            by = self._anchor_y + max(self._caret_height, 0) + self.BELOW_CARET_GAP
            self._arrow_points_down = False

        max_y = geo.bottom() - total_height - self.SCREEN_MARGIN
        by = max(geo.top() + self.SCREEN_MARGIN, min(by, max_y))

        arrow_margin = self.RADIUS + self.ARROW_HALF_W + 6
        desired_arrow_x = self._anchor_x - bx
        self._arrow_center_x = max(arrow_margin, min(desired_arrow_x, width - arrow_margin))

        self._text_rect = self._build_text_rect(
            BubbleTextLayout(
                self._wrapped_lines,
                0,
                max(self._fm.lineSpacing() * len(self._wrapped_lines), self._fm.height()),
                self._text_box_width,
                width,
                self._bubble_body_height,
            )
        )
        self.move(bx, by)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        body_top = 0 if self._arrow_points_down else self.ARROW_H
        body_rect = QRectF(0, body_top, self.width(), self._bubble_body_height)

        bubble = QPainterPath()
        bubble.addRoundedRect(body_rect, self.RADIUS, self.RADIUS)

        arrow = QPainterPath()
        if self._arrow_points_down:
            arrow.moveTo(self._arrow_center_x - self.ARROW_HALF_W, body_rect.bottom())
            arrow.lineTo(self._arrow_center_x, body_rect.bottom() + self.ARROW_H)
            arrow.lineTo(self._arrow_center_x + self.ARROW_HALF_W, body_rect.bottom())
        else:
            arrow.moveTo(self._arrow_center_x - self.ARROW_HALF_W, body_rect.top())
            arrow.lineTo(self._arrow_center_x, body_rect.top() - self.ARROW_H)
            arrow.lineTo(self._arrow_center_x + self.ARROW_HALF_W, body_rect.top())
        arrow.closeSubpath()
        bubble = bubble.united(arrow)

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(30, 30, 30, 210))
        p.drawPath(bubble)

        p.setPen(QPen(QColor(255, 255, 255, 25), 1.0))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(bubble)

        dot_center_y = self._text_rect.top() + self._fm.ascent() / 2.0 + 2.0
        dot_r = self.DOT_RADIUS * self._dot_scale
        glow_alpha = int(60 * (0.5 + 0.5 * math.sin(self._pulse_phase)))

        if self._phase == self.PHASE_POLISHING:
            dot_color = QColor(245, 158, 11)
        else:
            dot_color = QColor(239, 68, 68)

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(dot_color.red(), dot_color.green(), dot_color.blue(), glow_alpha))
        p.drawEllipse(QPoint(self.DOT_X, round(dot_center_y)), round(dot_r + 3), round(dot_r + 3))
        p.setBrush(dot_color)
        p.drawEllipse(QPoint(self.DOT_X, round(dot_center_y)), round(dot_r), round(dot_r))

        p.setFont(self._font)
        p.setPen(QPen(self._text_color))
        line_height = self._fm.lineSpacing()
        text_top = self._text_rect.top() + self._fm.ascent()
        for index, line in enumerate(self._wrapped_lines):
            y = text_top + index * line_height
            p.drawText(QPointF(self._text_rect.left(), y), line)

        p.end()
