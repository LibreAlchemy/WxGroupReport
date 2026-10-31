import importlib.util
import json
import re
from pathlib import Path

import pytest


def load_preprocessor_module():
    script_path = (
        Path(__file__).resolve().parents[1]
        / ".agents"
        / "skills"
        / "import-chat-data"
        / "scripts"
        / "preprocessor.py"
    )
    spec = importlib.util.spec_from_file_location("preprocessor", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_is_valid_message_only_allows_business_message_types():
    preprocessor = load_preprocessor_module()

    for msg_type in [0, 7, 24, 25]:
        assert preprocessor.is_valid_message(msg_type) is True

    # 27 = 名片，不参与内容分析；1/5 = 图片/动画表情等水消息
    for msg_type in [80, 1, 5, 27, 999]:
        assert preprocessor.is_valid_message(msg_type) is False


def test_extract_join_times_uses_next_system_message_for_joiner_name():
    preprocessor = load_preprocessor_module()

    messages = [
        {
            "type": 80,
            "timestamp": 1710000000,
            "content": '邀请"$names$"加入了群聊',
        },
        {
            "type": 80,
            "timestamp": 1710000001,
            "content": '"Dongmay"与群里其他人都不是朋友关系，请注意隐私安全',
        },
    ]

    result = preprocessor.extract_join_times(messages)

    assert result == {"Dongmay": 1710000000}


def test_extract_join_times_falls_back_to_current_system_message():
    preprocessor = load_preprocessor_module()

    messages = [
        {
            "type": 80,
            "timestamp": 1710001000,
            "content": '"Alice"加入群聊',
        },
    ]

    result = preprocessor.extract_join_times(messages)

    assert result == {"Alice": 1710001000}


def test_extract_join_times_ignores_placeholder_names_in_qr_join_message():
    preprocessor = load_preprocessor_module()

    messages = [
        {
            "type": 80,
            "timestamp": 1710001500,
            "content": '"$adder$"通过扫描你分享的二维码加入群聊  $revoke$',
        },
    ]

    result = preprocessor.extract_join_times(messages)

    assert result == {}


def test_filter_and_parse_messages_excludes_system_messages():
    preprocessor = load_preprocessor_module()
    member_mapping = {"wxid_alice": {"accountName": "Alice", "avatar": ""}}
    messages = [
        {
            "type": 0,
            "sender": "wxid_alice",
            "timestamp": 1710002000,
            "content": "hello",
        },
        {
            "type": 80,
            "sender": "wxid_alice",
            "timestamp": 1710002001,
            "content": '"Alice"撤回了一条消息',
        },
        {
            "type": 7,
            "sender": "wxid_alice",
            "timestamp": 1710002002,
            "content": "[链接] 一篇文章",
        },
    ]

    result, filtered_count = preprocessor.filter_and_parse_messages(
        messages, member_mapping, show_progress=False
    )

    assert filtered_count == 1
    assert len(result["wxid_alice"]) == 2
    assert [msg.msg_type for msg in result["wxid_alice"]] == [0, 7]


def test_filter_and_parse_messages_excludes_forwarded_chat_records():
    preprocessor = load_preprocessor_module()
    member_mapping = {"wxid_alice": {"accountName": "Alice", "avatar": ""}}
    messages = [
        {
            "type": 7,
            "sender": "wxid_alice",
            "timestamp": 1710002500,
            "content": "[转发的聊天记录]Alice与Bob的聊天记录",
            "chatRecords": [
                {
                    "sender": "Alice",
                    "accountName": "Alice",
                    "timestamp": 1710002400,
                    "type": 0,
                    "content": "hello",
                }
            ],
        },
        {
            "type": 0,
            "sender": "wxid_alice",
            "timestamp": 1710002600,
            "content": "正常发言",
        },
    ]

    result, filtered_count = preprocessor.filter_and_parse_messages(
        messages, member_mapping, show_progress=False
    )

    assert filtered_count == 1
    assert len(result["wxid_alice"]) == 1
    assert result["wxid_alice"][0].content == "正常发言"


def test_filter_and_parse_messages_keeps_exported_image_path_messages():
    preprocessor = load_preprocessor_module()
    member_mapping = {"wxid_alice": {"accountName": "Alice", "avatar": ""}}
    messages = [
        {
            "type": 7,
            "sender": "wxid_alice",
            "timestamp": 1710002550,
            "content": "../images/20260328/abc123.png",
        },
        {
            "type": 7,
            "sender": "wxid_alice",
            "timestamp": 1710002600,
            "content": "[链接] 一篇文章",
        },
    ]

    result, filtered_count = preprocessor.filter_and_parse_messages(
        messages, member_mapping, show_progress=False
    )

    assert filtered_count == 0
    assert len(result["wxid_alice"]) == 2
    assert result["wxid_alice"][0].content == "../images/20260328/abc123.png"


def test_build_member_mapping_excludes_chat_record_only_members():
    preprocessor = load_preprocessor_module()
    members = [
        {"platformId": "group_1", "accountName": "群聊", "avatar": ""},
        {"platformId": "wxid_alice", "accountName": "Alice", "avatar": ""},
        {"platformId": "小七", "accountName": "小七", "avatar": ""},
    ]

    mapping = preprocessor.build_member_mapping(
        members,
        root_message_senders={"wxid_alice"},
        chat_record_participants={"小七"},
        group_id="group_1",
    )

    assert "group_1" not in mapping
    assert "wxid_alice" in mapping
    assert "小七" not in mapping


def test_preprocess_chat_data_extracts_join_time_and_writes_member_files(tmp_path):
    preprocessor = load_preprocessor_module()
    input_path = tmp_path / "chat.json"
    output_dir = tmp_path / "output"
    raw_data = {
        "meta": {
            "name": "Test Group",
            "platform": "wechat",
            "groupId": "group_1",
            "groupAvatar": "",
        },
        "members": [
            {"platformId": "group_1", "accountName": "群聊", "avatar": ""},
            {"platformId": "wxid_dongmay", "accountName": "Dongmay", "avatar": ""},
            {"platformId": "wxid_alice", "accountName": "Alice", "avatar": ""},
            {"platformId": "小七", "accountName": "小七", "avatar": ""},
        ],
        "messages": [
            {
                "type": 80,
                "sender": "group_1",
                "timestamp": 1710000000,
                "content": '邀请"$names$"加入了群聊',
            },
            {
                "type": 80,
                "sender": "group_1",
                "timestamp": 1710000001,
                "content": '"Dongmay"与群里其他人都不是朋友关系，请注意隐私安全',
            },
            {
                "type": 0,
                "sender": "wxid_dongmay",
                "timestamp": 1710000100,
                "content": "大家好",
            },
            {
                "type": 25,
                "sender": "wxid_alice",
                "timestamp": 1710000200,
                "content": '欢迎[引用 Dongmay：大家好]',
            },
            {
                "type": 7,
                "sender": "wxid_alice",
                "timestamp": 1710000300,
                "content": "[转发的聊天记录]小七与文件传输助手的聊天记录",
                "chatRecords": [
                    {
                        "sender": "小七",
                        "accountName": "小七",
                        "timestamp": 1710000290,
                        "type": 0,
                        "content": "转发内容",
                    }
                ],
            },
        ],
    }
    input_path.write_text(json.dumps(raw_data, ensure_ascii=False), encoding="utf-8")

    processed, output_files = preprocessor.preprocess_chat_data(
        str(input_path),
        output_dir=str(output_dir),
    )

    assert processed.statistics["totalMessages"] == 5
    assert processed.statistics["systemMessages"] == 2
    assert processed.statistics["memberMessages"] == 2
    assert processed.statistics["filteredMessages"] == 3
    assert processed.members["wxid_dongmay"].join_time == "2024-03-09T16:00:00Z"
    assert processed.members["wxid_dongmay"].message_count == 1
    assert processed.members["wxid_alice"].message_count == 1
    assert "小七" not in processed.members

    imported_path = output_dir / "imported.json"
    member_path = output_dir / "members" / "wxid_dongmay.json"
    dialogue_path = output_dir / "dialogue.json"
    assert imported_path == output_files["main"]
    assert imported_path.exists()
    assert member_path.exists()
    assert dialogue_path == output_files["dialogue"]
    assert dialogue_path.exists()
    member_payload = json.loads(member_path.read_text(encoding="utf-8"))
    assert set(member_payload) == {
        "wxid",
        "nickname",
        "avatar",
        "join_time",
        "message_count",
        "messages",
    }

    imported = json.loads(imported_path.read_text(encoding="utf-8"))
    alice_message = imported["members"]["wxid_alice"]["messages"][0]
    assert alice_message["id"].startswith("wxid_alice_")
    assert alice_message["quote"] == {
        "author": "Dongmay",
        "content": "大家好",
    }
    dialogue = json.loads(dialogue_path.read_text(encoding="utf-8"))
    assert len(dialogue["messages"]) == 2


def build_v1_export(messages):
    return {
        "schemaVersion": 1,
        "exportedAt": "2026-10-29T22:58:04",
        "account": "wxid_me",
        "conversation": {
            "username": "group_1",
            "displayName": "Test Group",
            "avatarPath": "media/avatars/group_1.jpg",
            "isGroup": True,
        },
        "messages": messages,
    }


def test_detect_export_schema_supports_legacy_and_v1():
    preprocessor = load_preprocessor_module()

    legacy = {"meta": {}, "members": [], "messages": []}
    assert preprocessor.detect_export_schema(legacy) == "chatlab"
    assert (
        preprocessor.detect_export_schema(build_v1_export([]))
        == "wechat-export-v1"
    )


def test_detect_export_schema_rejects_unknown_mixed_and_future_schemas():
    preprocessor = load_preprocessor_module()

    invalid_documents = [
        {},
        {"meta": {}, "members": [], "messages": [], "conversation": {}},
        {**build_v1_export([]), "schemaVersion": 2},
        {
            "schemaVersion": 1,
            "conversation": {"username": "group_1", "isGroup": True},
            "messages": [],
        },
    ]

    for document in invalid_documents:
        with pytest.raises(preprocessor.UnsupportedExportFormatError):
            preprocessor.detect_export_schema(document)


def test_normalize_v1_export_maps_links_quotes_types_and_latest_member_metadata():
    preprocessor = load_preprocessor_module()
    raw_data = build_v1_export(
        [
            {
                "id": "m1",
                "renderType": "text",
                "createTime": 1710000001,
                "senderUsername": "wxid_alice",
                "senderDisplayName": "Alice",
                "senderAvatarPath": "avatar-1.jpg",
                "content": "第一条",
            },
            {
                "id": "m2",
                "renderType": "link",
                "createTime": 1710000002,
                "senderUsername": "wxid_alice",
                "senderDisplayName": "Alice New",
                "senderAvatarPath": "avatar-2.jpg",
                "content": "链接摘要",
                "title": "文章标题",
                "url": "https://example.com/article",
            },
            {
                "id": "m3",
                "renderType": "quote",
                "createTime": 1710000003,
                "senderUsername": "wxid_bob",
                "senderDisplayName": "Bob",
                "senderAvatarPath": "bob.jpg",
                "content": "我同意",
                "quoteTitle": "Alice",
                "quoteContent": "原始观点",
            },
            {
                "id": "m4",
                "renderType": "image",
                "createTime": 1710000004,
                "senderUsername": "wxid_bob",
                "senderDisplayName": "Bob",
                "senderAvatarPath": "bob.jpg",
                "content": "",
            },
            {
                "id": "m5",
                "renderType": "system",
                "createTime": 1710000005,
                "senderUsername": "group_1",
                "senderDisplayName": "Test Group",
                "content": "系统消息",
            },
            {
                "id": "m6",
                "renderType": "chatHistory",
                "createTime": 1710000006,
                "senderUsername": "wxid_alice",
                "senderDisplayName": "Alice New",
                "senderAvatarPath": "avatar-2.jpg",
                "content": "转发的聊天记录",
            },
            {
                "id": "m7",
                "renderType": "unsupported",
                "createTime": 1710000007,
                "senderUsername": "wxid_bob",
                "senderDisplayName": "Bob",
                "senderAvatarPath": "bob.jpg",
                "content": "未知类型",
            },
        ]
    )

    normalized = preprocessor.normalize_export(
        raw_data, preprocessor.detect_export_schema(raw_data)
    )
    messages_by_content = {
        message["content"]: message for message in normalized["messages"]
    }

    assert normalized["meta"] == {
        "name": "Test Group",
        "platform": "wechat",
        "type": "group",
        "groupId": "group_1",
        "groupAvatar": "media/avatars/group_1.jpg",
    }
    assert [message["type"] for message in normalized["messages"]] == [
        0,
        7,
        25,
        7,
        80,
        7,
        -1,
    ]
    assert messages_by_content["[文章标题](https://example.com/article)"]["type"] == 7
    assert messages_by_content["我同意[引用 Alice：原始观点]"]["type"] == 25
    assert messages_by_content["我同意[引用 Alice：原始观点]"]["quote"] == {
        "author": "Alice",
        "content": "原始观点",
    }
    assert messages_by_content["[图片]"]["type"] == 7
    assert messages_by_content["转发的聊天记录"]["forwardedChatRecord"] is True
    assert normalized["members"] == [
        {
            "platformId": "wxid_alice",
            "accountName": "Alice New",
            "avatar": "avatar-2.jpg",
        },
        {
            "platformId": "wxid_bob",
            "accountName": "Bob",
            "avatar": "bob.jpg",
        },
    ]


def test_preprocess_v1_export_filters_non_business_and_malformed_messages(tmp_path):
    preprocessor = load_preprocessor_module()
    input_path = tmp_path / "v1.json"
    output_dir = tmp_path / "output"
    raw_data = build_v1_export(
        [
            {
                "renderType": "system",
                "createTime": 1710000000,
                "senderUsername": "group_1",
                "senderDisplayName": "Test Group",
                "content": '邀请"$names$"加入了群聊',
            },
            {
                "renderType": "system",
                "createTime": 1710000001,
                "senderUsername": "",
                "senderDisplayName": "",
                "content": '"Alice"与群里其他人都不是朋友关系，请注意隐私安全',
            },
            {
                "renderType": "text",
                "createTime": 1710000100,
                "senderUsername": "wxid_alice",
                "senderDisplayName": "Alice",
                "senderAvatarPath": "alice.jpg",
                "content": "有效文本",
            },
            {
                "renderType": "quote",
                "createTime": 1710000200,
                "senderUsername": "wxid_bob",
                "senderDisplayName": "Bob",
                "senderAvatarPath": "bob.jpg",
                "content": "回复",
                "quoteTitle": "Alice",
                "quoteContent": "有效文本",
            },
            {
                "renderType": "link",
                "createTime": 1710000300,
                "senderUsername": "wxid_alice",
                "senderDisplayName": "Alice",
                "senderAvatarPath": "alice.jpg",
                "title": "文章",
                "url": "https://example.com/a",
            },
            {
                "renderType": "image",
                "createTime": 1710000400,
                "senderUsername": "wxid_bob",
                "senderDisplayName": "Bob",
                "senderAvatarPath": "bob.jpg",
                "content": "[图片]",
            },
            {
                "renderType": "chatHistory",
                "createTime": 1710000500,
                "senderUsername": "wxid_alice",
                "senderDisplayName": "Alice",
                "senderAvatarPath": "alice.jpg",
                "content": "转发的聊天记录",
            },
            {
                "renderType": "unsupported",
                "createTime": 1710000600,
                "senderUsername": "wxid_bob",
                "senderDisplayName": "Bob",
                "senderAvatarPath": "bob.jpg",
                "content": "未知消息",
            },
            {
                "renderType": "text",
                "senderUsername": "wxid_alice",
                "senderDisplayName": "Alice",
                "senderAvatarPath": "alice.jpg",
                "content": "缺少时间戳",
            },
        ]
    )
    input_path.write_text(json.dumps(raw_data, ensure_ascii=False), encoding="utf-8")

    processed, output_files = preprocessor.preprocess_chat_data(
        str(input_path),
        output_dir=str(output_dir),
    )

    assert processed.statistics == {
        "totalMessages": 9,
        "validMessages": 4,
        "memberMessages": 4,
        "filteredMessages": 5,
        "systemMessages": 2,
        "totalMembers": 2,
    }
    assert processed.members["wxid_alice"].join_time == "2024-03-09T16:00:00Z"
    assert processed.members["wxid_alice"].message_count == 2
    assert processed.members["wxid_bob"].message_count == 2
    assert output_files["main"].exists()
    assert len(output_files["members"]) == 2
    expected_member_fields = {
        "wxid",
        "nickname",
        "avatar",
        "join_time",
        "message_count",
        "messages",
    }
    for member_file in output_files["members"]:
        member_payload = json.loads(member_file.read_text(encoding="utf-8"))
        assert set(member_payload) == expected_member_fields

    imported = json.loads(output_files["main"].read_text(encoding="utf-8"))
    alice_messages = imported["members"]["wxid_alice"]["messages"]
    assert [message["content"] for message in alice_messages] == [
        "有效文本",
        "[文章](https://example.com/a)",
    ]


def test_preprocess_v1_export_accepts_empty_messages(tmp_path):
    preprocessor = load_preprocessor_module()
    input_path = tmp_path / "empty.json"
    output_dir = tmp_path / "output"
    input_path.write_text(
        json.dumps(build_v1_export([]), ensure_ascii=False), encoding="utf-8"
    )

    processed, output_files = preprocessor.preprocess_chat_data(
        str(input_path),
        output_dir=str(output_dir),
    )

    assert processed.members == {}
    assert processed.statistics == {
        "totalMessages": 0,
        "validMessages": 0,
        "memberMessages": 0,
        "filteredMessages": 0,
        "systemMessages": 0,
        "totalMembers": 0,
    }
    assert output_files["main"].exists()


def test_normalize_v1_maps_media_types_and_link_fallbacks():
    preprocessor = load_preprocessor_module()
    raw_data = build_v1_export(
        [
            {
                "renderType": "emoji",
                "createTime": 1710000001,
                "senderUsername": "wxid_alice",
                "content": "[表情]",
            },
            {
                "renderType": "file",
                "createTime": 1710000002,
                "senderUsername": "wxid_alice",
                "content": "",
                "title": "report.pdf",
            },
            {
                "renderType": "video",
                "createTime": 1710000003,
                "senderUsername": "wxid_alice",
                "content": "[视频]",
            },
            {
                "renderType": "voice",
                "createTime": 1710000004,
                "senderUsername": "wxid_alice",
                "content": "[语音]",
                "voiceTranscript": "语音转写",
            },
            {
                "renderType": "redPacket",
                "createTime": 1710000005,
                "senderUsername": "wxid_alice",
                "content": "恭喜发财",
            },
            {
                "renderType": "link",
                "createTime": 1710000006,
                "senderUsername": "wxid_alice",
                "content": "仅有摘要",
            },
            {
                "renderType": "link",
                "createTime": 1710000007,
                "senderUsername": "wxid_alice",
            },
            {
                "renderType": "text",
                "createTime": 1710000008,
                "senderUsername": "",
                "content": "缺少发送者",
            },
        ]
    )

    normalized = preprocessor.normalize_export(
        raw_data, preprocessor.detect_export_schema(raw_data)
    )
    normalized_messages = normalized["messages"]

    assert [message["type"] for message in normalized_messages] == [
        7,
        7,
        7,
        7,
        7,
        7,
        7,
        -1,
    ]
    assert normalized_messages[1]["content"] == "report.pdf"
    assert normalized_messages[3]["content"] == "[语音]\n语音转写"
    assert normalized_messages[5]["content"] == "仅有摘要"
    assert normalized_messages[6]["content"] == "[链接]"


def test_provided_v1_archive_matches_expected_statistics(tmp_path):
    preprocessor = load_preprocessor_module()
    archive_path = (
        Path(__file__).resolve().parents[1]
        / "data"
        / "archives"
        / "2026-10"
        / "mt-20261001-20261029.json"
    )
    if not archive_path.exists():
        pytest.skip("provided October v1 archive is not available")

    processed, output_files = preprocessor.preprocess_chat_data(
        str(archive_path),
        output_dir=str(tmp_path / "output"),
        save_individual=False,
    )

    assert processed.statistics == {
        "totalMessages": 5259,
        "validMessages": 5198,
        "memberMessages": 5198,
        "filteredMessages": 61,
        "systemMessages": 55,
        "totalMembers": 57,
    }
    assert sum(
        member.message_count for member in processed.members.values()
    ) == 5198
    dialogue = json.loads(
        output_files["dialogue"].read_text(encoding="utf-8")
    )
    assert len(dialogue["messages"]) == 5198

    all_messages = [
        message
        for member in processed.members.values()
        for message in member.messages
    ]
    markdown_link_pattern = r"^\[[^\]]+\]\(https?://[^)]+\)$"
    assert sum(
        1 for message in all_messages if re.match(markdown_link_pattern, message.content)
    ) == 138
    assert sum(1 for message in all_messages if "[引用 " in message.content) == 719
