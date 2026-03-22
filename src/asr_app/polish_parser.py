import json
from dataclasses import dataclass


@dataclass(slots=True)
class PolishStreamResult:
    text: str
    emitted_any: bool
    target_started: bool
    target_completed: bool
    json_completed: bool
    first_chunk_latency_ms: int | None
    elapsed_ms: int
    resolved_text: str | None = None

    @property
    def is_complete(self) -> bool:
        return self.target_completed and self.json_completed


class JsonFieldStreamExtractor:
    _STATE_SEEK_OBJECT = "seek_object"
    _STATE_EXPECT_KEY_OR_END = "expect_key_or_end"
    _STATE_READ_STRING = "read_string"
    _STATE_EXPECT_COLON = "expect_colon"
    _STATE_EXPECT_VALUE = "expect_value"
    _STATE_SKIP_LITERAL = "skip_literal"
    _STATE_SKIP_COMPOSITE = "skip_composite"
    _STATE_AFTER_VALUE = "after_value"
    _STATE_DONE = "done"

    _STRING_CONTEXT_KEY = "key"
    _STRING_CONTEXT_SKIP = "skip"
    _STRING_CONTEXT_TARGET = "target"

    def __init__(self, target_key: str):
        self.target_key = target_key
        self.state = self._STATE_SEEK_OBJECT
        self.string_context = None
        self.key_buffer = []
        self.pending_key = None
        self.escape_pending = False
        self.unicode_pending = False
        self.unicode_buffer = []
        self.composite_depth = 0
        self.composite_in_string = False
        self.composite_escape_pending = False
        self.target_started = False
        self.target_completed = False
        self.json_completed = False

    def feed(self, text: str) -> str:
        emitted = []
        for char in text:
            self._consume(char, emitted)
        return "".join(emitted)

    def _consume(self, char: str, emitted: list[str]) -> None:
        if self.state == self._STATE_DONE:
            return

        if self.state == self._STATE_SEEK_OBJECT:
            if char == "{":
                self.state = self._STATE_EXPECT_KEY_OR_END
            return

        if self.state == self._STATE_EXPECT_KEY_OR_END:
            if char.isspace():
                return
            if char == '"':
                self.string_context = self._STRING_CONTEXT_KEY
                self.key_buffer = []
                self.escape_pending = False
                self.unicode_pending = False
                self.unicode_buffer = []
                self.state = self._STATE_READ_STRING
                return
            if char == "}":
                self.json_completed = True
                self.state = self._STATE_DONE
            return

        if self.state == self._STATE_EXPECT_COLON:
            if char.isspace():
                return
            if char == ":":
                self.state = self._STATE_EXPECT_VALUE
            return

        if self.state == self._STATE_EXPECT_VALUE:
            if char.isspace():
                return
            if char == '"':
                if self.pending_key == self.target_key and not self.target_completed:
                    self.string_context = self._STRING_CONTEXT_TARGET
                    self.target_started = True
                else:
                    self.string_context = self._STRING_CONTEXT_SKIP
                self.escape_pending = False
                self.unicode_pending = False
                self.unicode_buffer = []
                self.state = self._STATE_READ_STRING
                return
            if char in "{[":
                self.composite_depth = 1
                self.composite_in_string = False
                self.composite_escape_pending = False
                self.state = self._STATE_SKIP_COMPOSITE
                return
            self.state = self._STATE_SKIP_LITERAL
            self._consume(char, emitted)
            return

        if self.state == self._STATE_READ_STRING:
            self._consume_string_char(char, emitted)
            return

        if self.state == self._STATE_SKIP_LITERAL:
            if char == ",":
                self.pending_key = None
                self.state = self._STATE_EXPECT_KEY_OR_END
                return
            if char == "}":
                self.pending_key = None
                self.json_completed = True
                self.state = self._STATE_DONE
            return

        if self.state == self._STATE_SKIP_COMPOSITE:
            self._consume_composite_char(char)
            return

        if self.state == self._STATE_AFTER_VALUE:
            if char.isspace():
                return
            if char == ",":
                self.pending_key = None
                self.state = self._STATE_EXPECT_KEY_OR_END
                return
            if char == "}":
                self.pending_key = None
                self.json_completed = True
                self.state = self._STATE_DONE
            return

    def _consume_string_char(self, char: str, emitted: list[str]) -> None:
        if self.unicode_pending:
            if char.lower() in "0123456789abcdef":
                self.unicode_buffer.append(char)
                if len(self.unicode_buffer) == 4:
                    decoded = chr(int("".join(self.unicode_buffer), 16))
                    self.unicode_pending = False
                    self.unicode_buffer = []
                    self._route_string_char(decoded, emitted)
                return
            self.unicode_pending = False
            self.unicode_buffer = []
            self._route_string_char(char, emitted)
            return

        if self.escape_pending:
            self.escape_pending = False
            if char == "u":
                self.unicode_pending = True
                self.unicode_buffer = []
                return
            self._route_string_char(self._decode_escape(char), emitted)
            return

        if char == "\\":
            self.escape_pending = True
            return

        if char == '"':
            if self.string_context == self._STRING_CONTEXT_KEY:
                self.pending_key = "".join(self.key_buffer)
                self.key_buffer = []
                self.state = self._STATE_EXPECT_COLON
            elif self.string_context == self._STRING_CONTEXT_TARGET:
                self.target_completed = True
                self.state = self._STATE_AFTER_VALUE
            else:
                self.state = self._STATE_AFTER_VALUE
            self.string_context = None
            return

        self._route_string_char(char, emitted)

    def _route_string_char(self, char: str, emitted: list[str]) -> None:
        if self.string_context == self._STRING_CONTEXT_KEY:
            self.key_buffer.append(char)
        elif self.string_context == self._STRING_CONTEXT_TARGET:
            emitted.append(char)

    def _consume_composite_char(self, char: str) -> None:
        if self.composite_in_string:
            if self.composite_escape_pending:
                self.composite_escape_pending = False
                return
            if char == "\\":
                self.composite_escape_pending = True
                return
            if char == '"':
                self.composite_in_string = False
            return

        if char == '"':
            self.composite_in_string = True
            return
        if char in "{[":
            self.composite_depth += 1
            return
        if char in "}]":
            self.composite_depth -= 1
            if self.composite_depth <= 0:
                self.state = self._STATE_AFTER_VALUE

    @staticmethod
    def _decode_escape(char: str) -> str:
        escape_map = {
            '"': '"',
            "\\": "\\",
            "/": "/",
            "b": "\b",
            "f": "\f",
            "n": "\n",
            "r": "\r",
            "t": "\t",
        }
        return escape_map.get(char, char)


def extract_target_text(response_text: str, target_key: str) -> str | None:
    decoder = json.JSONDecoder()
    for index, char in enumerate(response_text):
        if char != "{":
            continue
        try:
            payload, _ = decoder.raw_decode(response_text[index:])
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict) or target_key not in payload:
            continue
        value = payload[target_key]
        if value is None:
            return ""
        if isinstance(value, str):
            return value
        return json.dumps(value, ensure_ascii=False)
    return None


def describe_stream_issue(result: PolishStreamResult | None) -> str:
    if result is None:
        return "\u6d41\u5f0f\u7ed3\u679c\u4e0d\u53ef\u7528"

    reasons = []
    if not result.emitted_any:
        reasons.append("\u6a21\u578b\u672a\u8fd4\u56de\u53ef\u89e3\u6790\u5185\u5bb9")
    if not result.target_started:
        reasons.append("\u672a\u627e\u5230\u76ee\u6807\u5b57\u6bb5")
    elif not result.target_completed:
        reasons.append("\u76ee\u6807\u5b57\u6bb5\u672a\u5b8c\u6574\u7ed3\u675f")
    if not result.json_completed:
        reasons.append("JSON \u8f93\u51fa\u672a\u5b8c\u6574\u7ed3\u675f")
    if result.resolved_text is None:
        reasons.append("\u672a\u80fd\u4ece\u5b8c\u6574\u54cd\u5e94\u4e2d\u89e3\u6790\u51fa\u76ee\u6807\u5b57\u6bb5")
    return "\uff0c".join(reasons) or "\u6d41\u5f0f\u7ed3\u679c\u4e0d\u5b8c\u6574"
