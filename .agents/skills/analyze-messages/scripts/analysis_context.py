import hashlib
import json
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from message_context import (
    PLACEHOLDER_CONTENTS,
    is_substantive_message,
    message_body_and_quote,
    safe_text,
)


CONTEXT_WINDOW_SECONDS = 120
MAX_CONTEXT_NEIGHBORS = 2
MAX_CHUNK_CHARS = 12_000
MARKDOWN_LINK_RE = re.compile(r"^\[([^\]]+)\]\((https?://[^)]+)\)$")
BEIJING_TIMEZONE = timezone(timedelta(hours=8))
CONTEXT_CUES = (
    "这",
    "那",
    "它",
    "上面",
    "前面",
    "刚才",
    "然后",
    "所以",
    "但是",
    "不过",
    "也",
    "还是",
    "确实",
    "同意",
    "+1",
    "？",
    "?",
)


def parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(
        timezone.utc
    )


def local_date_key(value: str) -> str:
    try:
        return parse_timestamp(value).astimezone(BEIJING_TIMEZONE).date().isoformat()
    except ValueError:
        return safe_text(value)[:10] or "unknown"


def local_time_text(value: str) -> str:
    try:
        return parse_timestamp(value).astimezone(BEIJING_TIMEZONE).strftime("%H:%M")
    except ValueError:
        return safe_text(value)[11:16] or "--:--"


def ensure_message_ids(messages: list[dict], wxid: str) -> list[dict]:
    normalized = []
    used = set()
    for index, message in enumerate(messages):
        item = dict(message)
        message_id = safe_text(item.get("id"))
        if not message_id:
            timestamp = safe_text(item.get("timestamp")) or "unknown"
            message_id = f"{wxid}_{timestamp}_{index}"
        candidate = message_id
        suffix = 1
        while candidate in used:
            candidate = f"{message_id}_{suffix}"
            suffix += 1
        item["id"] = candidate
        used.add(candidate)
        normalized.append(item)
    return normalized


def load_dialogue(output_dir: str) -> list[dict]:
    path = Path(output_dir) / "dialogue.json"
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)
    messages = payload.get("messages", [])
    return messages if isinstance(messages, list) else []


def load_group_info(output_dir: str) -> dict:
    path = Path(output_dir) / "imported.json"
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)
    group_info = payload.get("group_info")
    return group_info if isinstance(group_info, dict) else {}


def _dialogue_for_member(wxid: str, nickname: str, messages: list[dict]) -> list[dict]:
    return [
        {
            **message,
            "sender": wxid,
            "nickname": nickname,
        }
        for message in messages
    ]


def _collect_window_indices(
    dialogue: list[dict], target_ids: set[str], wxid: str
) -> set[int]:
    selected: set[int] = set()
    for index, message in enumerate(dialogue):
        if safe_text(message.get("id")) not in target_ids:
            continue

        selected.add(index)
        target_time = parse_timestamp(safe_text(message.get("timestamp")))
        body, quote = message_body_and_quote(message)
        needs_context = bool(quote) or len(body) <= 16 or any(
            cue in body for cue in CONTEXT_CUES
        )

        for direction in (-1, 1):
            other_count = 0
            cursor = index + direction
            limit = (
                MAX_CONTEXT_NEIGHBORS
                if needs_context
                else (1 if direction < 0 else 0)
            )
            while 0 <= cursor < len(dialogue) and other_count < limit:
                candidate = dialogue[cursor]
                if safe_text(candidate.get("sender")) == wxid:
                    cursor += direction
                    continue
                if not is_substantive_message(candidate):
                    cursor += direction
                    continue
                try:
                    candidate_time = parse_timestamp(safe_text(candidate.get("timestamp")))
                except ValueError:
                    break
                if abs((candidate_time - target_time).total_seconds()) > CONTEXT_WINDOW_SECONDS:
                    break
                selected.add(cursor)
                if safe_text(candidate.get("sender")) != wxid:
                    other_count += 1
                cursor += direction
    return selected


def build_context_messages(
    wxid: str, nickname: str, substantive_messages: list[dict], dialogue: list[dict]
) -> tuple[list[dict], set[str], dict[str, str]]:
    normalized_messages = ensure_message_ids(substantive_messages, wxid)
    target_ids = {message["id"] for message in normalized_messages}
    source_dialogue = dialogue or _dialogue_for_member(wxid, nickname, normalized_messages)
    source_dialogue = ensure_message_ids(source_dialogue, wxid)

    dialogue_ids = {safe_text(message.get("id")) for message in source_dialogue}
    missing_targets = [
        message for message in normalized_messages if message["id"] not in dialogue_ids
    ]
    if missing_targets:
        source_dialogue.extend(_dialogue_for_member(wxid, nickname, missing_targets))
        source_dialogue.sort(key=lambda item: safe_text(item.get("timestamp")))

    indices = _collect_window_indices(source_dialogue, target_ids, wxid)
    context_messages = []
    alias_to_id = {}
    speaker_aliases = {}
    for alias_index, index in enumerate(sorted(indices), start=1):
        message = dict(source_dialogue[index])
        message_id = safe_text(message.get("id"))
        sender = safe_text(message.get("sender")) or wxid
        is_target = message_id in target_ids
        if is_target:
            role = "TARGET"
        elif sender == wxid:
            role = "SELF"
        else:
            role = "CTX"
        alias = f"a{alias_index}"
        alias_to_id[alias] = message_id
        if role == "TARGET":
            speaker_alias = "T"
        else:
            speaker_alias = speaker_aliases.setdefault(
                sender, f"C{len(speaker_aliases) + 1}"
            )
        body, quote = message_body_and_quote(message)
        context_messages.append(
            {
                "id": message_id,
                "alias": alias,
                "timestamp": safe_text(message.get("timestamp")),
                "nickname": safe_text(message.get("nickname")) or sender,
                "sender": sender,
                "role": role,
                "speaker_alias": speaker_alias,
                "content": body,
                "quote": quote,
            }
        )
    return context_messages, target_ids, alias_to_id


def format_context_message(message: dict) -> str:
    content = safe_text(message.get("content"))
    line = (
        f"{local_time_text(message['timestamp'])} {message['alias']} "
        f"{message['speaker_alias']}: {content}"
    )
    quote = message.get("quote")
    if isinstance(quote, dict) and safe_text(quote.get("content")):
        line += (
            f"\n  引用 {safe_text(quote.get('author')) or '未知成员'}："
            f"{safe_text(quote.get('content'))}"
        )
    return line


def chunk_context_messages(
    context_messages: list[dict], max_chars: int = MAX_CHUNK_CHARS
) -> list[dict]:
    day_groups: dict[str, list[dict]] = defaultdict(list)
    for message in context_messages:
        date = local_date_key(safe_text(message.get("timestamp")))
        day_groups[date].append(message)

    chunk_groups: list[list[dict]] = []
    current: list[dict] = []
    current_chars = 0
    current_date = None
    for date in sorted(day_groups):
        for message in day_groups[date]:
            line = format_context_message(message)
            header_size = len(date) + 4 if date != current_date else 0
            line_size = len(line) + 1 + header_size
            if current and current_chars + line_size > max_chars:
                chunk_groups.append(current)
                current = []
                current_chars = 0
                current_date = None
                line_size = len(line) + 1 + len(date) + 4
            current.append(message)
            current_chars += line_size
            current_date = date
    if current:
        chunk_groups.append(current)

    chunks = []
    for group in chunk_groups:
        legend = []
        seen_speakers = set()
        for message in group:
            speaker_alias = message["speaker_alias"]
            if speaker_alias == "T" or speaker_alias in seen_speakers:
                continue
            seen_speakers.add(speaker_alias)
            legend.append(f"{speaker_alias}={message['nickname']}")

        rendered_lines = []
        current_date = None
        for message in group:
            date = local_date_key(message["timestamp"])
            if date != current_date:
                rendered_lines.append(f"## {date}")
                current_date = date
            rendered_lines.append(format_context_message(message))
        chunks.append(
            {
                "messages": group,
                "text": "\n".join(rendered_lines),
                "own_count": sum(1 for message in group if message["role"] == "TARGET"),
                "legend": ", ".join(legend),
            }
        )
    return chunks


def _message_stats(
    raw_messages: list[dict], substantive_messages: list[dict], dialogue: list[dict]
) -> dict[str, int | float]:
    active_days = {
        local_date_key(safe_text(message.get("timestamp")))
        for message in substantive_messages
        if safe_text(message.get("timestamp"))
    }
    dialogue_days = {
        local_date_key(safe_text(message.get("timestamp")))
        for message in dialogue
        if safe_text(message.get("timestamp"))
    }
    if dialogue_days:
        first_day = datetime.fromisoformat(min(dialogue_days)).date()
        last_day = datetime.fromisoformat(max(dialogue_days)).date()
        period_days = (last_day - first_day).days + 1
    else:
        period_days = len(active_days) or 1
    link_count = sum(
        1
        for message in substantive_messages
        if MARKDOWN_LINK_RE.match(safe_text(message.get("content")))
    )
    media_count = sum(
        1
        for message in raw_messages
        if safe_text(message.get("content")) in PLACEHOLDER_CONTENTS
    )
    return {
        "rawMessageCount": len(raw_messages),
        "substantiveCount": len(substantive_messages),
        "activeDays": len(active_days),
        "periodDays": period_days,
        "linkCount": link_count,
        "mediaCount": media_count,
    }


def build_input_package(
    wxid: str,
    nickname: str,
    messages: list[dict],
    dialogue: list[dict] | None = None,
) -> dict[str, Any]:
    raw_messages = ensure_message_ids(messages, wxid)
    substantive_messages = [
        message for message in raw_messages if is_substantive_message(message)
    ]
    dialogue_messages = dialogue or _dialogue_for_member(wxid, nickname, raw_messages)
    context_messages, target_ids, alias_to_id = build_context_messages(
        wxid, nickname, substantive_messages, dialogue_messages
    )
    chunks = chunk_context_messages(context_messages)
    stats = _message_stats(raw_messages, substantive_messages, dialogue_messages)
    return {
        "stats": stats,
        "chunks": chunks,
        "target_ids": target_ids,
        "allowed_context_ids": {
            safe_text(message.get("id")) for message in context_messages
        },
        "alias_to_id": alias_to_id,
    }


def build_input_hash(
    package: dict[str, Any], prompt_version: str, model: str, temperature: float
) -> str:
    payload = {
        "promptVersion": prompt_version,
        "model": model,
        "temperature": temperature,
        "stats": package["stats"],
        "chunks": package["chunks"],
    }
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
