import json
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any

from openai import OpenAI

from .config import DEFAULT_BASE_URL, DEFAULT_OPTIMIZATION_LEVEL, DEFAULT_TEXT_POLISH_MODEL, DEFAULT_TEXT_POLISH_OUTPUT_KEY
from .i18n import t
from .polish_parser import JsonFieldStreamExtractor, PolishStreamResult, describe_stream_issue, extract_target_text

REQUEST_TIMEOUT_SECONDS = 30


class TextPolisherError(RuntimeError):
    pass


@dataclass(slots=True)
class PolishResult:
    text: str
    source: str
    stream: PolishStreamResult | None = None
    fallback_reason: str | None = None
    stream_error: str | None = None
    fallback_error: str | None = None


def lang_styles() -> dict[str, str]:
    return {
        "light": t("polish.style.light"),
        "normal": t("polish.style.normal"),
        "deep": t("polish.style.deep"),
        "professional": t("polish.style.professional"),
    }


def base_prompt() -> str:
    return t("polish.base_prompt")


def json_suffix(target_key: str) -> str:
    return t("polish.json_suffix", target_key=target_key)


def _build_client(api_key: str, base_url: str) -> OpenAI:
    return OpenAI(api_key=api_key, base_url=base_url, timeout=REQUEST_TIMEOUT_SECONDS)


def _build_system_prompt(target_key: str, optimization_level: str = DEFAULT_OPTIMIZATION_LEVEL, custom_prompt: str = "") -> str:
    if optimization_level == "custom" and custom_prompt:
        style_text = custom_prompt
    else:
        styles = lang_styles()
        style_text = styles.get(optimization_level, styles["normal"])
    return base_prompt() + style_text + json_suffix(target_key)


def _build_messages(raw_text: str, target_key: str, optimization_level: str = DEFAULT_OPTIMIZATION_LEVEL, custom_prompt: str = "") -> list[dict[str, str]]:
    return [
        {"role": "system", "content": _build_system_prompt(target_key, optimization_level, custom_prompt)},
        {"role": "user", "content": json.dumps({t("polish.input_text_key"): raw_text}, ensure_ascii=False)},
    ]


def _iter_delta_text(delta: Any) -> Iterator[str]:
    content = getattr(delta, "content", None)
    if isinstance(content, str):
        if content:
            yield content
        return
    if not isinstance(content, list):
        return
    for item in content:
        text = item.get("text", "") if isinstance(item, dict) else getattr(item, "text", "")
        if text:
            yield text


def _iter_message_text(content: Any) -> Iterator[str]:
    if isinstance(content, str):
        if content:
            yield content
        return
    if not isinstance(content, list):
        return
    for item in content:
        text = item.get("text", "") if isinstance(item, dict) else getattr(item, "text", "")
        if text:
            yield text


def stream_polished_text(raw_text: str, api_key: str, *, on_chunk: Callable[[str], None] | None = None, model_name: str = DEFAULT_TEXT_POLISH_MODEL, base_url: str = DEFAULT_BASE_URL, target_key: str = DEFAULT_TEXT_POLISH_OUTPUT_KEY, optimization_level: str = DEFAULT_OPTIMIZATION_LEVEL, custom_prompt: str = "") -> PolishStreamResult:
    if not raw_text:
        return PolishStreamResult(text="", emitted_any=False, target_started=False, target_completed=False, json_completed=False, first_chunk_latency_ms=None, elapsed_ms=0)
    client = _build_client(api_key, base_url)
    extractor = JsonFieldStreamExtractor(target_key=target_key)
    started_at = time.perf_counter()
    first_chunk_latency_ms = None
    emitted_chunks: list[str] = []
    raw_fragments: list[str] = []
    try:
        stream = client.chat.completions.create(
            model=model_name,
            messages=_build_messages(raw_text, target_key, optimization_level, custom_prompt),
            stream=True,
            extra_body={"enable_thinking": False},
        )
    except Exception as exc:
        raise TextPolisherError(str(exc)) from exc

    try:
        for chunk in stream:
            choices = getattr(chunk, "choices", None) or []
            if not choices:
                continue
            delta = getattr(choices[0], "delta", None)
            if delta is None:
                continue
            for text in _iter_delta_text(delta):
                raw_fragments.append(text)
                if first_chunk_latency_ms is None:
                    first_chunk_latency_ms = int((time.perf_counter() - started_at) * 1000)
                parsed = extractor.feed(text)
                if not parsed:
                    continue
                emitted_chunks.append(parsed)
                if on_chunk is not None:
                    on_chunk(parsed)
    except Exception as exc:
        raise TextPolisherError(str(exc)) from exc

    raw_response_text = "".join(raw_fragments)
    resolved_text = extract_target_text(raw_response_text, target_key)
    return PolishStreamResult(
        text="".join(emitted_chunks),
        emitted_any=bool(emitted_chunks),
        target_started=extractor.target_started,
        target_completed=extractor.target_completed,
        json_completed=extractor.json_completed,
        first_chunk_latency_ms=first_chunk_latency_ms,
        elapsed_ms=int((time.perf_counter() - started_at) * 1000),
        resolved_text=resolved_text,
    )


def collect_streamed_polish(raw_text: str, api_key: str, *, model_name: str = DEFAULT_TEXT_POLISH_MODEL, base_url: str = DEFAULT_BASE_URL, target_key: str = DEFAULT_TEXT_POLISH_OUTPUT_KEY, optimization_level: str = DEFAULT_OPTIMIZATION_LEVEL, custom_prompt: str = "") -> PolishStreamResult:
    return stream_polished_text(raw_text, api_key, model_name=model_name, base_url=base_url, target_key=target_key, optimization_level=optimization_level, custom_prompt=custom_prompt)


def request_polished_text(raw_text: str, api_key: str, *, model_name: str = DEFAULT_TEXT_POLISH_MODEL, base_url: str = DEFAULT_BASE_URL, target_key: str = DEFAULT_TEXT_POLISH_OUTPUT_KEY, optimization_level: str = DEFAULT_OPTIMIZATION_LEVEL, custom_prompt: str = "") -> str:
    if not raw_text:
        return ""
    client = _build_client(api_key, base_url)
    try:
        response = client.chat.completions.create(
            model=model_name,
            messages=_build_messages(raw_text, target_key, optimization_level, custom_prompt),
            extra_body={"enable_thinking": False},
        )
    except Exception as exc:
        raise TextPolisherError(str(exc)) from exc

    choices = getattr(response, "choices", None) or []
    if not choices:
        raise TextPolisherError(t("polish.error.no_choices"))
    message = getattr(choices[0], "message", None)
    content = getattr(message, "content", None)
    response_text = "".join(_iter_message_text(content)).strip()
    if not response_text:
        raise TextPolisherError(t("polish.error.empty_content"))
    polished_text = extract_target_text(response_text, target_key)
    if polished_text is None:
        raise TextPolisherError(t("polish.error.missing_json_key"))
    if not polished_text:
        raise TextPolisherError(t("polish.error.empty_polished_text"))
    return polished_text


def polish_text_with_fallback(raw_text: str, api_key: str, *, model_name: str = DEFAULT_TEXT_POLISH_MODEL, base_url: str = DEFAULT_BASE_URL, target_key: str = DEFAULT_TEXT_POLISH_OUTPUT_KEY, optimization_level: str = DEFAULT_OPTIMIZATION_LEVEL, custom_prompt: str = "") -> PolishResult:
    if not raw_text:
        return PolishResult(text="", source="raw")
    stream_result = None
    stream_error = None
    fallback_reason = None
    try:
        stream_result = collect_streamed_polish(raw_text, api_key, model_name=model_name, base_url=base_url, target_key=target_key, optimization_level=optimization_level, custom_prompt=custom_prompt)
    except TextPolisherError as exc:
        stream_error = str(exc)
        fallback_reason = t("polish.stream_request_failed")
    else:
        if stream_result.resolved_text is not None:
            return PolishResult(text=stream_result.resolved_text, source="stream", stream=stream_result)
        fallback_reason = describe_stream_issue(stream_result)
    try:
        polished_text = request_polished_text(raw_text, api_key, model_name=model_name, base_url=base_url, target_key=target_key, optimization_level=optimization_level, custom_prompt=custom_prompt)
    except TextPolisherError as exc:
        return PolishResult(text=raw_text, source="raw", stream=stream_result, fallback_reason=fallback_reason, stream_error=stream_error, fallback_error=str(exc))
    return PolishResult(text=polished_text, source="fallback", stream=stream_result, fallback_reason=fallback_reason, stream_error=stream_error)
