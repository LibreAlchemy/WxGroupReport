#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
微信群聊记录预处理工具

功能：
1. 读取微信群聊 JSON 导出文件
2. 过滤非成员业务消息（系统消息等）
3. 按成员拆分消息
4. 生成主文件和成员单独文件
5. 可选提取系统消息中的入群时间
"""

import dataclasses
import json
import re
import os
import sys
import uuid
import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from tqdm import tqdm

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - 仅在依赖缺失时触发
    load_dotenv = None

# 消息类型常量
SYSTEM_MSG_TYPES = {80}  # 系统消息
VALID_MSG_TYPES = {0, 7, 24, 25, 27}  # 有效消息


@dataclass
class ParsedMessage:
    """解析后的消息"""

    id: str
    timestamp: str
    msg_type: int
    content: str


@dataclass
class ProcessedMember:
    """处理后的成员数据"""

    wxid: str
    nickname: str
    avatar: str
    join_time: Optional[str]
    message_count: int
    messages: List[ParsedMessage]


@dataclass
class GroupInfo:
    """群组信息"""

    name: str
    platform: str
    group_id: str
    avatar: str


@dataclass
class ProcessedData:
    """处理后的完整数据"""

    group_info: GroupInfo
    members: Dict[str, ProcessedMember]
    statistics: Dict[str, int]


def parse_timestamp(unix_ts: int) -> str:
    """转换 Unix 时间戳为 ISO 8601 格式"""
    dt = datetime.fromtimestamp(unix_ts, tz=timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def generate_message_id(wxid: str, timestamp: int) -> str:
    """生成唯一消息 ID"""
    short_uuid = str(uuid.uuid4()).split("-")[0]
    return f"{wxid}_{timestamp}_{short_uuid}"


def clean_content(content: Optional[str]) -> str:
    """清理消息内容"""
    if content is None:
        return ""
    return str(content).strip()


def is_placeholder_name(value: str) -> bool:
    """判断是否为系统占位符，例如 $names$、$adder$、$revoke$"""
    return bool(re.fullmatch(r"\$[^$]+\$", value.strip()))


def is_valid_message(msg_type: int) -> bool:
    """判断消息类型是否有效"""
    if msg_type in SYSTEM_MSG_TYPES:
        return False
    return msg_type in VALID_MSG_TYPES


def is_forwarded_chat_record_message(msg: Dict[str, Any]) -> bool:
    """判断是否为转发聊天记录消息"""
    return int(msg.get("type", -1)) == 7 and "chatRecords" in msg


def collect_chat_record_participants(messages: List[Dict]) -> set[str]:
    """收集转发聊天记录中的参与者名称"""
    participants: set[str] = set()
    for msg in messages:
        if not is_forwarded_chat_record_message(msg):
            continue
        chat_records = msg.get("chatRecords")
        if not isinstance(chat_records, list):
            continue
        for record in chat_records:
            sender = clean_content(record.get("sender"))
            account_name = clean_content(record.get("accountName"))
            if sender:
                participants.add(sender)
            if account_name:
                participants.add(account_name)
    return participants


def build_member_mapping(
    members: List[Dict],
    root_message_senders: set[str],
    chat_record_participants: set[str],
    group_id: str = "",
) -> Dict[str, Dict]:
    """从成员列表构建 wxid → member_info 映射"""
    mapping = {}
    for member in members:
        wxid = member.get("platformId")
        if not wxid:
            continue
        if group_id and wxid == group_id:
            continue
        # 原始导出会把转发聊天记录中的参与者也塞进 members。
        # 这类伪成员的 platformId 往往直接等于聊天记录里的昵称，
        # 且不会作为当前群的顶层消息 sender 出现。
        if wxid in chat_record_participants and wxid not in root_message_senders:
            continue
        mapping[wxid] = {
            "accountName": member.get("accountName", ""),
            "avatar": member.get("avatar", ""),
        }
    return mapping


def extract_join_times(messages: List[Dict]) -> Dict[str, int]:
    """从系统消息提取入群时间（按昵称映射）"""
    result: Dict[str, int] = {}

    for index, msg in enumerate(messages):
        msg_type = int(msg.get("type", -1))
        if msg_type not in SYSTEM_MSG_TYPES:
            continue

        content = clean_content(msg.get("content"))
        if "加入群聊" not in content and "加入了群聊" not in content:
            continue

        timestamp = int(msg.get("timestamp", 0))
        joiner = ""

        # 微信导出中常见两段式入群提示：
        # 1. 邀请"$names$"加入了群聊
        # 2. "Dongmay"与群里其他人都不是朋友关系，请注意隐私安全
        # 实际入群成员名称通常出现在下一条系统消息中。
        if index + 1 < len(messages):
            next_msg = messages[index + 1]
            if int(next_msg.get("type", -1)) in SYSTEM_MSG_TYPES:
                next_content = clean_content(next_msg.get("content"))
                next_matches = re.findall(r"\"([^\"]+)\"", next_content)
                for candidate in next_matches:
                    candidate = candidate.strip()
                    if candidate and not is_placeholder_name(candidate):
                        joiner = candidate
                        break

        # 兼容直接在当前系统消息中带出成员名的格式
        if not joiner:
            matches = re.findall(r"\"([^\"]+)\"", content)
            for candidate in matches:
                candidate = candidate.strip()
                if candidate and not is_placeholder_name(candidate):
                    joiner = candidate
                    break

        if not joiner:
            continue

        if joiner not in result or timestamp < result[joiner]:
            result[joiner] = timestamp

    return result


def filter_and_parse_messages(
    messages: List[Dict],
    member_mapping: Dict[str, Dict],
    show_progress: bool = True,
) -> Tuple[Dict[str, List[ParsedMessage]], int]:
    """
    过滤和解析消息

    Returns:
        (messages_by_member, filtered_count)
    """
    result = {}
    filtered_count = 0

    iterator = messages
    if show_progress:
        iterator = tqdm(messages, desc="处理消息", file=sys.stderr)

    for msg in iterator:
        msg_type = int(msg.get("type", -1))

        if (
            not is_valid_message(msg_type)
            or is_forwarded_chat_record_message(msg)
        ):
            filtered_count += 1
            continue

        sender_id = msg.get("sender")
        if sender_id not in member_mapping:
            continue

        parsed_msg = ParsedMessage(
            id=generate_message_id(sender_id, msg.get("timestamp", 0)),
            timestamp=parse_timestamp(msg.get("timestamp", 0)),
            msg_type=msg_type,
            content=clean_content(msg.get("content")),
        )

        if sender_id not in result:
            result[sender_id] = []
        result[sender_id].append(parsed_msg)

    return result, filtered_count


def aggregate_member_data(
    member_mapping: Dict[str, Dict],
    messages_by_member: Dict[str, List[ParsedMessage]],
    join_times_by_nickname: Dict[str, int],
    show_progress: bool = True,
) -> Dict[str, ProcessedMember]:
    """聚合成员数据"""
    result = {}

    iterator = member_mapping.items()
    if show_progress:
        iterator = tqdm(member_mapping.items(), desc="聚合成员数据", file=sys.stderr)

    for wxid, member_info in iterator:
        messages = messages_by_member.get(wxid, [])
        sorted_messages = sorted(messages, key=lambda m: m.timestamp)
        join_timestamp = join_times_by_nickname.get(member_info["accountName"])

        result[wxid] = ProcessedMember(
            wxid=wxid,
            nickname=member_info["accountName"],
            avatar=member_info["avatar"],
            join_time=parse_timestamp(join_timestamp) if join_timestamp else None,
            message_count=len(messages),
            messages=sorted_messages,
        )

    return result


def calculate_statistics(
    messages: List[Dict], member_mapping: Dict[str, Dict], filtered_count: int
) -> Dict[str, int]:
    """计算统计信息"""
    system_messages = sum(
        1 for msg in messages if int(msg.get("type", -1)) in SYSTEM_MSG_TYPES
    )
    member_messages = len(messages) - filtered_count
    return {
        "totalMessages": len(messages),
        "validMessages": member_messages,
        "memberMessages": member_messages,
        "filteredMessages": filtered_count,
        "systemMessages": system_messages,
        "totalMembers": len(member_mapping),
    }


def save_processed_data(
    data: ProcessedData, output_dir: Path, save_individual: bool = True
) -> Dict[str, Any]:
    """
    保存处理后的数据

    Returns:
        {"main": Path, "members": List[Path]}
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    main_file = output_dir / "imported.json"
    with open(main_file, "w", encoding="utf-8") as f:
        json.dump(dataclasses.asdict(data), f, ensure_ascii=False, indent=2)

    result = {"main": main_file, "members": []}

    if save_individual:
        members_dir = output_dir / "members"
        members_dir.mkdir(exist_ok=True)

        for wxid, member in tqdm(
            data.members.items(), desc="保存成员文件", file=sys.stderr
        ):
            member_file = members_dir / f"{wxid}.json"
            member_data = dataclasses.asdict(member)

            with open(member_file, "w", encoding="utf-8") as f:
                json.dump(member_data, f, ensure_ascii=False, indent=2)

            result["members"].append(member_file)

    return result


def validate_input_file(input_path: Path) -> None:
    """验证输入文件"""
    if not input_path.exists():
        raise FileNotFoundError(f"输入文件不存在: {input_path}")
    if not input_path.is_file():
        raise ValueError(f"输入路径不是文件: {input_path}")
    if not input_path.suffix == ".json":
        raise ValueError("输入文件必须是 JSON 格式")


def preprocess_chat_data(
    input_path: str,
    output_dir: str = "output",
    include_join_time: bool = True,
    save_individual: bool = True,
) -> Tuple[ProcessedData, Dict[str, Any]]:
    """
    主函数：协调整个预处理流程

    Returns:
        (ProcessedData, output_files)
    """
    with open(input_path, "r", encoding="utf-8") as f:
        raw_data = json.load(f)

    meta = raw_data.get("meta", {})
    members = raw_data.get("members", [])
    messages = raw_data.get("messages", [])

    group_info = GroupInfo(
        name=meta.get("name", ""),
        platform=meta.get("platform", ""),
        group_id=meta.get("groupId", ""),
        avatar=meta.get("groupAvatar", ""),
    )

    root_message_senders = {
        msg.get("sender")
        for msg in messages
        if msg.get("sender") and not is_forwarded_chat_record_message(msg)
    }
    chat_record_participants = collect_chat_record_participants(messages)
    member_mapping = build_member_mapping(
        members,
        root_message_senders,
        chat_record_participants,
        group_info.group_id,
    )
    join_times_by_nickname = extract_join_times(messages) if include_join_time else {}

    messages_by_member, filtered_count = filter_and_parse_messages(
        messages, member_mapping, show_progress=True
    )

    processed_members = aggregate_member_data(
        member_mapping,
        messages_by_member,
        join_times_by_nickname,
        show_progress=True,
    )

    statistics = calculate_statistics(messages, member_mapping, filtered_count)

    result = ProcessedData(
        group_info=group_info, members=processed_members, statistics=statistics
    )

    output_files = save_processed_data(
        result, Path(output_dir), save_individual=save_individual
    )

    return result, output_files


def parse_bool(value: Optional[str], default: bool = False) -> bool:
    """解析布尔环境变量"""
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def load_config() -> Dict[str, Any]:
    """从命令行参数读取配置"""
    parser = argparse.ArgumentParser(description="微信群聊记录预处理工具")
    parser.add_argument("-i", "--input", help="输入 JSON 文件路径")
    parser.add_argument("-o", "--output", default="output", help="输出目录，默认 output")
    parser.add_argument("--no-extract-join-time", action="store_true", help="不提取入群时间")
    parser.add_argument("--no-save-individual", action="store_true", help="不保存成员单独文件")
    
    args = parser.parse_args()

    if load_dotenv:
        load_dotenv()

    output_dir = args.output
    include_join_time = not args.no_extract_join_time
    save_individual = not args.no_save_individual

    return {
        "input_path": args.input,
        "output_dir": output_dir,
        "include_join_time": include_join_time,
        "save_individual": save_individual,
    }


def main():
    """命令行入口"""
    config = load_config()

    if not config["input_path"]:
        print("❌ 错误: 未指定输入文件。请通过 -i/--input 参数指定。", file=sys.stderr)
        return 1

    try:
        input_path = Path(config["input_path"])
        validate_input_file(input_path)

        result, output_files = preprocess_chat_data(
            config["input_path"],
            config["output_dir"],
            include_join_time=config["include_join_time"],
            save_individual=config["save_individual"],
        )

        print("\n处理完成")
        print(f"总成员数: {result.statistics['totalMembers']}")
        print(f"有效消息: {result.statistics['validMessages']}")
        print(f"过滤消息: {result.statistics['filteredMessages']}")
        print(f"主文件: {output_files['main']}")
        if output_files["members"]:
            print(f"成员文件: {len(output_files['members'])} 个 (output/members/)")

        return 0
    except FileNotFoundError as e:
        print(f"\n❌ 文件错误: {e}", file=sys.stderr)
        return 1
    except json.JSONDecodeError as e:
        print(f"\n❌ JSON 格式错误: {e}", file=sys.stderr)
        return 1
    except ValueError as e:
        print(f"\n❌ 参数错误: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"\n❌ 处理失败: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
