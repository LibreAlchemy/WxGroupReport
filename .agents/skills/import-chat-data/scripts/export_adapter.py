#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Normalize supported WeChat group export formats for preprocessing."""

from typing import Any, Dict, List


CHATLAB_SCHEMA = "chatlab"
WECHAT_EXPORT_V1_SCHEMA = "wechat-export-v1"

BUSINESS_RENDER_TYPES = {
    "text",
    "image",
    "emoji",
    "file",
    "link",
    "quote",
    "video",
    "voice",
    "redPacket",
}

RENDER_TYPE_TO_MESSAGE_TYPE = {
    "text": 0,
    "quote": 25,
    **{render_type: 7 for render_type in BUSINESS_RENDER_TYPES - {"text", "quote"}},
    "system": 80,
    "chatHistory": 7,
}

EMPTY_CONTENT_PLACEHOLDERS = {
    "text": "[消息]",
    "image": "[图片]",
    "emoji": "[表情]",
    "file": "[文件]",
    "link": "[链接]",
    "quote": "[引用]",
    "video": "[视频]",
    "voice": "[语音]",
    "redPacket": "[红包]",
    "system": "[系统消息]",
    "chatHistory": "[聊天记录]",
}


class UnsupportedExportFormatError(ValueError):
    """Raised when the input does not match a supported export schema."""


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _timestamp(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if value < 0:
        return None
    return int(value)


def _require_message_list(raw_data: Dict[str, Any]) -> List[Any]:
    messages = raw_data.get("messages")
    if not isinstance(messages, list):
        raise UnsupportedExportFormatError("导出文件缺少 messages 数组")
    return messages


def _validate_legacy_schema(raw_data: Dict[str, Any]) -> None:
    if not isinstance(raw_data.get("meta"), dict):
        raise UnsupportedExportFormatError("ChatLab 导出缺少 meta 对象")
    if not isinstance(raw_data.get("members"), list):
        raise UnsupportedExportFormatError("ChatLab 导出缺少 members 数组")
    _require_message_list(raw_data)


def _validate_v1_schema(raw_data: Dict[str, Any]) -> None:
    version = raw_data.get("schemaVersion")
    if version != 1:
        raise UnsupportedExportFormatError(
            f"不支持的新版导出 schemaVersion={version!r}，当前仅支持 1"
        )

    conversation = raw_data.get("conversation")
    if not isinstance(conversation, dict):
        raise UnsupportedExportFormatError("新版导出缺少 conversation 对象")
    if not _text(conversation.get("username")):
        raise UnsupportedExportFormatError("新版导出缺少群 conversation.username")
    if not _text(conversation.get("displayName")):
        raise UnsupportedExportFormatError("新版导出缺少群 conversation.displayName")
    if conversation.get("isGroup") is not True:
        raise UnsupportedExportFormatError("新版导出不是群聊数据")

    _require_message_list(raw_data)


def detect_export_schema(raw_data: Dict[str, Any]) -> str:
    if not isinstance(raw_data, dict):
        raise UnsupportedExportFormatError("导出 JSON 顶层必须是对象")

    has_legacy_fields = "meta" in raw_data or "members" in raw_data
    has_v1_fields = "schemaVersion" in raw_data or "conversation" in raw_data

    if has_legacy_fields and has_v1_fields:
        raise UnsupportedExportFormatError("导出文件混用了 ChatLab 与新版字段")
    if has_v1_fields:
        _validate_v1_schema(raw_data)
        return WECHAT_EXPORT_V1_SCHEMA
    if has_legacy_fields:
        _validate_legacy_schema(raw_data)
        return CHATLAB_SCHEMA

    raise UnsupportedExportFormatError(
        "无法识别导出格式：未找到 ChatLab 字段或新版 schemaVersion/conversation"
    )


def _normalize_link_content(message: Dict[str, Any]) -> str:
    title = _text(message.get("title"))
    url = _text(message.get("url"))
    if title and url:
        return f"[{title}]({url})"

    content = _text(message.get("content"))
    if content:
        return content
    if title:
        return title
    if url:
        return url
    return EMPTY_CONTENT_PLACEHOLDERS["link"]


def _normalize_quote_content(message: Dict[str, Any]) -> str:
    content = _text(message.get("content"))
    quoted_content = _text(message.get("quoteContent"))
    if quoted_content:
        quote_author = _text(message.get("quoteTitle")) or "未知成员"
        quote_block = f"[引用 {quote_author}：{quoted_content}]"
        return f"{content}{quote_block}"
    return content or EMPTY_CONTENT_PLACEHOLDERS["quote"]


def _normalize_content(message: Dict[str, Any], render_type: str) -> str:
    if render_type == "link":
        return _normalize_link_content(message)
    if render_type == "quote":
        return _normalize_quote_content(message)
    if render_type == "voice":
        content = _text(message.get("content"))
        transcript = _text(message.get("voiceTranscript"))
        if transcript:
            return f"{content}\n{transcript}" if content else transcript

    content = _text(message.get("content"))
    if content:
        return content
    if render_type == "file":
        return _text(message.get("title")) or EMPTY_CONTENT_PLACEHOLDERS[render_type]
    return EMPTY_CONTENT_PLACEHOLDERS.get(render_type, "")


def _normalize_v1_messages(
    raw_messages: List[Any], group_id: str
) -> tuple[List[Dict[str, Any]], List[Dict[str, str]]]:
    messages: List[Dict[str, Any]] = []
    member_state: Dict[str, Dict[str, Any]] = {}

    for item in raw_messages:
        message = item if isinstance(item, dict) else {}
        render_type = _text(message.get("renderType"))
        sender = _text(message.get("senderUsername"))
        display_name = _text(message.get("senderDisplayName"))
        avatar = _text(message.get("senderAvatarPath"))
        timestamp = _timestamp(message.get("createTime"))

        if sender and sender != group_id:
            state = member_state.setdefault(
                sender,
                {
                    "platformId": sender,
                    "accountName": "",
                    "avatar": "",
                    "nameTimestamp": -1,
                    "avatarTimestamp": -1,
                    "order": len(member_state),
                },
            )
            effective_timestamp = timestamp if timestamp is not None else -1
            if display_name and effective_timestamp >= state["nameTimestamp"]:
                state["accountName"] = display_name
                state["nameTimestamp"] = effective_timestamp
            if avatar and effective_timestamp >= state["avatarTimestamp"]:
                state["avatar"] = avatar
                state["avatarTimestamp"] = effective_timestamp

        is_business_type = render_type in BUSINESS_RENDER_TYPES
        has_valid_sender = bool(sender) and sender != group_id
        if (
            timestamp is None
            or render_type not in RENDER_TYPE_TO_MESSAGE_TYPE
            or (is_business_type and not has_valid_sender)
        ):
            msg_type = -1
        else:
            msg_type = RENDER_TYPE_TO_MESSAGE_TYPE[render_type]

        normalized: Dict[str, Any] = {
            "sender": sender,
            "accountName": display_name,
            "timestamp": timestamp if timestamp is not None else 0,
            "type": msg_type,
            "content": _normalize_content(message, render_type),
        }
        if render_type == "quote":
            quote_content = _text(message.get("quoteContent"))
            if quote_content:
                normalized["quote"] = {
                    "author": _text(message.get("quoteTitle")) or "未知成员",
                    "content": quote_content,
                }
        source_id = _text(message.get("id"))
        if source_id:
            normalized["platformMessageId"] = source_id
        if render_type == "chatHistory":
            normalized["forwardedChatRecord"] = True
        messages.append(normalized)

    members = []
    for state in sorted(member_state.values(), key=lambda value: value["order"]):
        members.append(
            {
                "platformId": state["platformId"],
                "accountName": state["accountName"] or state["platformId"],
                "avatar": state["avatar"],
            }
        )
    return messages, members


def normalize_export(raw_data: Dict[str, Any], schema: str) -> Dict[str, Any]:
    if schema == CHATLAB_SCHEMA:
        _validate_legacy_schema(raw_data)
        return raw_data
    if schema != WECHAT_EXPORT_V1_SCHEMA:
        raise UnsupportedExportFormatError(f"未知导出 schema: {schema!r}")

    _validate_v1_schema(raw_data)
    conversation = raw_data["conversation"]
    messages, members = _normalize_v1_messages(
        raw_data["messages"], _text(conversation.get("username"))
    )
    return {
        "meta": {
            "name": _text(conversation.get("displayName")),
            "platform": "wechat",
            "type": "group",
            "groupId": _text(conversation.get("username")),
            "groupAvatar": _text(conversation.get("avatarPath")),
        },
        "members": members,
        "messages": messages,
    }
