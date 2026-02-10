import pytest
import json
from pathlib import Path
from scripts.preprocessor import (
    is_valid_message,
    build_member_mapping,
    extract_join_times,
    preprocess_chat_data,
    SYSTEM_MSG_TYPES,
    LOW_QUALITY_TYPES,
)

MOCK_JSON_PATH = "docs/测试/test/json解析器/mock_chat_data.json"


@pytest.fixture
def integration_result(tmp_path):
    output_dir = str(tmp_path / "output")
    result, output_files = preprocess_chat_data(
        MOCK_JSON_PATH, output_dir=output_dir, include_media=False, save_individual=True
    )
    return result, output_files


class TestGroupInfoParsing:
    """TC-PRE-001: 群组信息解析验证"""

    def test_group_name(self, integration_result):
        result, _ = integration_result
        assert result.group_info.name == "测试群聊"

    def test_group_id(self, integration_result):
        result, _ = integration_result
        assert result.group_info.group_id == "123456789@chatroom"

    def test_platform(self, integration_result):
        result, _ = integration_result
        assert result.group_info.platform == "wechat"


class TestMemberExtraction:
    """TC-PRE-002: 成员列表提取验证"""

    def test_member_count(self, integration_result):
        result, _ = integration_result
        assert len(result.members) == 2

    def test_member_keys(self, integration_result):
        result, _ = integration_result
        assert "user_01" in result.members
        assert "user_02" in result.members

    def test_member_nicknames(self, integration_result):
        result, _ = integration_result
        assert result.members["user_01"].nickname == "张三"
        assert result.members["user_02"].nickname == "李四"

    def test_build_member_mapping_excludes_group_id(self):
        members = [
            {"platformId": "u1", "accountName": "A", "avatar": "v1"},
            {"platformId": "u2", "accountName": "B", "avatar": "v2"},
            {"platformId": "group_id", "accountName": "Group", "avatar": "v3"},
        ]
        mapping = build_member_mapping(members, group_id="group_id")
        assert len(mapping) == 2
        assert "u1" in mapping
        assert mapping["u1"]["accountName"] == "A"
        assert "group_id" not in mapping


class TestMessageClassification:
    """TC-PRE-003: 成员消息正确归类验证"""

    def test_user01_messages_belong_to_user01(self, integration_result):
        result, _ = integration_result
        u1_msgs = result.members["user_01"].messages
        assert len(u1_msgs) == 1
        assert u1_msgs[0].content == "大家好，这是第一条有效消息"

    def test_message_has_required_fields(self, integration_result):
        result, _ = integration_result
        msg = result.members["user_01"].messages[0]
        assert hasattr(msg, "id")
        assert hasattr(msg, "timestamp")
        assert hasattr(msg, "msg_type")
        assert hasattr(msg, "content")


class TestSystemMessageFiltering:
    """TC-PRE-004: 系统消息(type=80)过滤验证"""

    def test_no_system_messages_in_output(self, integration_result):
        result, _ = integration_result
        for member in result.members.values():
            for msg in member.messages:
                assert msg.msg_type != 80

    def test_filtered_count_correct(self, integration_result):
        result, _ = integration_result
        assert result.statistics["totalMessages"] == 5
        assert result.statistics["filteredMessages"] == 3


class TestLowQualityFiltering:
    """TC-PRE-005: 水消息(type=5)过滤验证"""

    def test_no_animated_emoji_in_output(self, integration_result):
        result, _ = integration_result
        for member in result.members.values():
            for msg in member.messages:
                assert msg.msg_type != 5

    def test_is_valid_message_rejects_type5(self):
        assert is_valid_message(5) is False


class TestJoinTimeExtraction:
    """TC-PRE-006: 基于系统消息的入群时间提取"""

    def test_join_time_iso_format(self, integration_result):
        result, _ = integration_result
        assert result.members["user_02"].join_time is not None
        assert "2024-02-03T22:40:00Z" in result.members["user_02"].join_time

    def test_extract_join_times_from_raw_messages(self):
        messages = [
            {"type": 80, "timestamp": 1000, "content": '"张三"加入群聊'},
            {"type": 0, "timestamp": 1100, "content": "普通消息"},
            {"type": 80, "timestamp": 1200, "content": '"李四"加入群聊'},
        ]
        join_times = extract_join_times(messages)
        assert join_times["张三"] == 1000
        assert join_times["李四"] == 1200
        assert len(join_times) == 2


class TestMediaFiltering:
    """TC-PRE-007: 媒体消息(图片)过滤验证"""

    def test_image_filtered_with_include_media_true(self):
        assert is_valid_message(1, include_media=True) is False

    def test_image_filtered_with_include_media_false(self):
        assert is_valid_message(1, include_media=False) is False


class TestTimeRangeFiltering:
    """TC-PRE-008: 时间范围过滤功能验证"""

    @pytest.mark.xfail(reason="preprocessor.py 尚未实现时间范围过滤功能")
    def test_time_range_filtering(self):
        start_ts = 1707000002
        end_ts = 1707000004
        assert False, "时间范围过滤功能尚未实现"


class TestFileNotFound:
    """TC-PRE-009: 空文件/不存在文件异常处理"""

    def test_non_existent_file_raises(self, tmp_path):
        non_existent = tmp_path / "nothing.json"
        with pytest.raises(FileNotFoundError):
            preprocess_chat_data(str(non_existent))


class TestMalformedJson:
    """TC-PRE-010: 损坏的JSON格式异常处理"""

    def test_invalid_json_raises(self, tmp_path):
        bad_json = tmp_path / "bad.json"
        bad_json.write_text("{ 'invalid': json ", encoding="utf-8")
        with pytest.raises(json.JSONDecodeError):
            preprocess_chat_data(str(bad_json))


class TestSpecialCharacters:
    """TC-PRE-011: 特殊字符与Emoji解析验证"""

    def test_emoji_and_special_chars_preserved(self, tmp_path):
        special_json = tmp_path / "special.json"
        data = {
            "meta": {"name": "🌟Emoji群🌟"},
            "members": [
                {"platformId": "u1", "accountName": "李' OR 1=1 --", "avatar": ""}
            ],
            "messages": [
                {
                    "type": 0,
                    "timestamp": 1000,
                    "sender": "u1",
                    "content": "🔥\n换行符\t制表符",
                }
            ],
        }
        special_json.write_text(json.dumps(data), encoding="utf-8")

        result, _ = preprocess_chat_data(str(special_json), output_dir=str(tmp_path))
        assert result.group_info.name == "🌟Emoji群🌟"
        assert result.members["u1"].nickname == "李' OR 1=1 --"
        assert result.members["u1"].messages[0].content == "🔥\n换行符\t制表符"


class TestEdgeCases:
    """补充边界用例"""

    def test_missing_fields_minimal_json(self, tmp_path):
        minimal_json = tmp_path / "minimal.json"
        minimal_json.write_text(json.dumps({}), encoding="utf-8")

        result, _ = preprocess_chat_data(str(minimal_json), output_dir=str(tmp_path))
        assert result.group_info.name == ""
        assert len(result.members) == 0
        assert result.statistics["totalMessages"] == 0

    def test_is_valid_message_accepts_text(self):
        assert is_valid_message(0) is True

    def test_is_valid_message_rejects_system(self):
        assert is_valid_message(80) is False

    def test_output_files_generated(self, integration_result):
        _, output_files = integration_result
        assert Path(output_files["main"]).exists()
        assert len(output_files["members"]) == 2
