import re
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse


MARKDOWN_LINK_RE = re.compile(r"^\[([^\]]+)\]\((https?://[^)]+)\)$")


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


def extract_markdown_link(message_content: str):
    match = MARKDOWN_LINK_RE.match(safe_text(message_content))
    if not match:
        return None
    title = safe_text(match.group(1))
    url = safe_text(match.group(2))
    if not title or not url:
        return None
    return title, url


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
