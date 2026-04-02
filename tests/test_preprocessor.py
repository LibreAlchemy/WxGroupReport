import importlib.util
import json
from pathlib import Path


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

    for msg_type in [0, 7, 24, 25, 27]:
        assert preprocessor.is_valid_message(msg_type) is True

    for msg_type in [80, 1, 5, 999]:
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
    assert imported_path == output_files["main"]
    assert imported_path.exists()
    assert member_path.exists()
