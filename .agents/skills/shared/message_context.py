import re
from typing import Any


PLACEHOLDER_CONTENTS = {
    "[图片]",
    "[表情]",
    "[视频]",
    "[消息]",
    "[语音]",
    "[链接]",
    "[红包]",
}


def safe_text(value: Any) -> str:
    return str(value or "").strip()


def parse_inline_quote(content: str) -> tuple[str, dict[str, str] | None]:
    """Split the last balanced inline quote block from message content."""
    text = safe_text(content)
    start = text.rfind("[引用 ")
    if start < 0:
        return text, None

    depth = 0
    end = -1
    for index in range(start, len(text)):
        if text[index] == "[":
            depth += 1
        elif text[index] == "]":
            depth -= 1
            if depth == 0:
                end = index
                break
    if end < 0:
        return text, None

    block = text[start + 1 : end]
    payload = block[len("引用 ") :]
    separator = "：" if "：" in payload else ":"
    if separator not in payload:
        return text, None
    author, quoted_content = payload.split(separator, 1)
    author = safe_text(author)
    quoted_content = safe_text(quoted_content)
    if not quoted_content:
        return text, None

    body = safe_text(f"{text[:start]}{text[end + 1:]}")
    return body, {"author": author or "未知成员", "content": quoted_content}


def message_body_and_quote(message: dict) -> tuple[str, dict[str, str] | None]:
    body, inline_quote = parse_inline_quote(safe_text(message.get("content")))
    structured_quote = message.get("quote")
    if isinstance(structured_quote, dict):
        author = safe_text(structured_quote.get("author"))
        content = safe_text(structured_quote.get("content"))
        if content:
            return body, {"author": author or "未知成员", "content": content}
    return body, inline_quote


def is_substantive_message(message: dict) -> bool:
    body, _ = message_body_and_quote(message)
    if not body:
        return False
    if body.startswith("#接龙") or body.startswith("../images/"):
        return False
    if body in PLACEHOLDER_CONTENTS:
        return False
    return bool(re.search(r"[A-Za-z0-9\u4e00-\u9fff]", body))
