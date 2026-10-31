import re
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from message_context import message_body_and_quote


MARKDOWN_LINK_RE = re.compile(r"^\[([^\]]+)\]\((https?://[^)]+)\)$")
URL_RE = re.compile(r"https?://[^\s<>\"'）)]+")
MARKDOWN_LINK_ANY_RE = re.compile(r"\[([^\]]+)\]\((https?://[^)]+)\)")
EMOJI_TOKEN_RE = re.compile(r"\[[^\[\]]{1,12}\](?!\()")
UNICODE_EMOJI_RE = re.compile(
    "[\U0001F000-\U0001FAFF\U0001F3FB-\U0001F3FF\u2600-\u27BF\uFE0F\u200D\u20E3]"
)
COMMENTARY_PREFIXES = (
    "分享",
    "转发",
    "推荐",
    "指出",
    "认为",
    "提出",
    "整理",
    "看到",
    "这篇文章",
    "这篇文章",
    "一个",
)


def safe_text(value):
    return str(value).replace("\r", " ").replace("\n", " ").strip()


def sanitize_url(url):
    text = safe_text(url)
    normalized = text.strip("[]()").strip()
    if not normalized:
        return ""
    if normalized == "链接":
        return ""
    lowered = normalized.lower()
    if not (lowered.startswith("http://") or lowered.startswith("https://")):
        return ""
    parsed = urlparse(normalized)
    host = (parsed.netloc or "").lower()
    if host == "mp.weixin.qq.com":
        params = parse_qsl(parsed.query, keep_blank_values=True)
        param_map = {key: value for key, value in params}
        if "__biz" in param_map:
            kept_params = [
                (key, param_map[key])
                for key in ("__biz", "mid", "idx", "sn", "chksm")
                if key in param_map
            ]
            parsed = parsed._replace(query=urlencode(kept_params), fragment="")
            return urlunparse(parsed)
    return normalized


def normalize_github_repo_url(url):
    cleaned = sanitize_url(url)
    parsed = urlparse(cleaned)
    if (parsed.netloc or "").lower() not in {"github.com", "www.github.com"}:
        return ""
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 2:
        return cleaned
    repo = parts[1][:-4] if parts[1].endswith(".git") else parts[1]
    return f"https://github.com/{parts[0]}/{repo}"


def _clean_url(url: str) -> str:
    return sanitize_url(re.sub(r"[.,，。;；]+$", "", safe_text(url)))


def extract_markdown_link(message_content: str):
    match = MARKDOWN_LINK_RE.match(safe_text(message_content))
    if not match:
        return None
    title = safe_text(match.group(1))
    url = safe_text(match.group(2))
    if not title or not url:
        return None
    return title, url


def extract_source_title_and_url(message_content: str) -> dict[str, str]:
    """Extract the original link title and URL from a chat message."""
    body, _ = message_body_and_quote({"content": message_content})
    body = str(body or "").replace("\r", "").strip()
    parsed = extract_markdown_link(body)
    if parsed:
        title, url = parsed
        return {"title": safe_text(title), "url": _clean_url(url)}

    urls = URL_RE.findall(body)
    url = _clean_url(urls[0]) if urls else ""
    title = ""

    bracket_match = re.search(r"【([^】]{2,120})】", body)
    if bracket_match:
        title = safe_text(bracket_match.group(1))

    if not title:
        for prefix in ("文章名称", "文章标题", "标题"):
            match = re.search(
                rf"{prefix}\s*[：:]\s*(.+)", body, flags=re.IGNORECASE
            )
            if match:
                title = safe_text(match.group(1).splitlines()[0])
                break

    if not title:
        for line in body.splitlines():
            candidate = safe_text(line)
            if not candidate or "http://" in candidate or "https://" in candidate:
                continue
            if candidate.endswith(("：", ":")):
                continue
            if candidate.startswith(COMMENTARY_PREFIXES):
                continue
            if len(candidate) > 120 or candidate.endswith(("？", "?")):
                continue
            title = candidate
            break

    return {"title": title, "url": url}


def _truncate_original(text: str, max_chars: int = 300) -> str:
    text = safe_text(text)
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3].rstrip() + "..."


def clean_insight_text(text: str) -> str:
    """Remove WeChat emoji tokens and Unicode emoji while preserving links."""
    cleaned = EMOJI_TOKEN_RE.sub("", str(text or ""))
    cleaned = UNICODE_EMOJI_RE.sub("", cleaned)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r"\s+([，。！？；：,.!?;:])", r"\1", cleaned)
    return cleaned.strip()


def restore_target_name(text: str, nickname: str) -> str:
    """Replace the prompt-only target alias T with the member nickname."""
    cleaned = safe_text(text)
    member = safe_text(nickname)
    if not cleaned or not member or member == "T":
        return cleaned
    return re.sub(r"(?<![A-Za-z0-9_])T(?![A-Za-z0-9_])", member, cleaned)


def extract_source_links(message_content: str) -> list[dict[str, str]]:
    """Extract all Markdown or bare links with the best available title."""
    body, _ = message_body_and_quote({"content": message_content})
    body = str(body or "").replace("\r", "").strip()
    if not body:
        return []

    markdown_titles = {
        _clean_url(url): safe_text(title)
        for title, url in MARKDOWN_LINK_ANY_RE.findall(body)
    }
    urls = []
    for url in URL_RE.findall(body):
        cleaned = _clean_url(url)
        if cleaned and cleaned not in urls:
            urls.append(cleaned)

    message_link = extract_source_title_and_url(body)
    entries = []
    for url in urls:
        title = markdown_titles.get(url, "")
        if not title and len(urls) == 1:
            title = message_link["title"]
        entries.append({"title": title, "url": url})
    return entries


def canonicalize_highlight_from_message(
    highlight: dict, message: dict | None
) -> dict | None:
    """Ground links in the source while preserving model-written GitHub summaries."""
    if not isinstance(message, dict):
        return None

    item = dict(highlight)
    item_type = safe_text(item.get("type")).lower()
    body, _ = message_body_and_quote(message)
    body = str(body or "").replace("\r", "").strip()
    link = extract_source_title_and_url(body)

    if item_type == "insight":
        original = _truncate_original(clean_insight_text(body))
        if not original:
            return None
        return {
            "type": "insight",
            "content": original,
            "messageId": safe_text(message.get("id")),
        }

    if item_type in {"article", "news"}:
        title = link["title"]
        url = link["url"]

        if url:
            if not title:
                return None
            return {
                "type": item_type,
                "content": _truncate_original(title),
                "messageId": safe_text(message.get("id")),
                "url": url,
            }

        if item_type != "article":
            return None

        no_link_title = body
        if no_link_title.startswith("[文件]"):
            no_link_title = safe_text(no_link_title[len("[文件]") :])
        if (
            not no_link_title
            or len(no_link_title) > 120
            or no_link_title.startswith(COMMENTARY_PREFIXES)
            or no_link_title.endswith(("？", "?"))
        ):
            return None
        return {
            "type": "article",
            "content": _truncate_original(no_link_title),
            "messageId": safe_text(message.get("id")),
        }

    if item_type == "github":
        url = link["url"]
        host = (urlparse(url).netloc or "").lower()
        if host not in {"github.com", "www.github.com"}:
            title = link["title"]
            if not url or not title:
                return None
            return {
                "type": "article",
                "content": _truncate_original(title),
                "messageId": safe_text(message.get("id")),
                "url": url,
            }
        content = _truncate_original(item.get("content") or "")
        if not content:
            return None
        return {
            "type": "github",
            "content": content,
            "messageId": safe_text(message.get("id")),
            "url": url,
        }

    if item_type == "opportunity":
        opportunity = _truncate_original(body) or _truncate_original(
            item.get("content") or ""
        )
        if not opportunity:
            return None
        return {
            "type": "opportunity",
            "content": opportunity,
            "messageId": safe_text(message.get("id")),
        }

    return None


def build_title_url_index_from_messages(messages: list[dict]) -> dict[str, str]:
    title_to_url: dict[str, str] = {}
    for message in messages:
        parsed = extract_markdown_link(message.get("content", ""))
        if not parsed:
            continue
        title, url = parsed
        title_to_url[title] = url
    return title_to_url


def build_title_url_index_from_processed(processed: dict) -> dict[str, str]:
    title_to_url: dict[str, str] = {}
    for member in (processed.get("members") or {}).values():
        title_to_url.update(
            build_title_url_index_from_messages(member.get("messages") or [])
        )
    return title_to_url


def repair_highlights(
    highlights: list[dict], title_to_url: dict[str, str]
) -> list[dict]:
    repaired = []
    for item in highlights:
        normalized = dict(item)
        if normalized.get("type") == "article":
            title = safe_text(normalized.get("content") or "")
            original_url = title_to_url.get(title)
            if original_url:
                normalized["url"] = original_url
        sanitized = sanitize_url(normalized.get("url") or "")
        if sanitized:
            normalized["url"] = sanitized
        else:
            normalized.pop("url", None)
        repaired.append(normalized)
    return repaired
