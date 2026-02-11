#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
微信群聊记录预处理工具

功能：
1. 读取微信群聊 JSON 导出文件
2. 过滤无效消息（系统消息、动画表情等）
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
LOW_QUALITY_TYPES = {5}  # 动画表情（水消息）
MEDIA_TYPES = {1}  # 图片
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


def is_valid_message(msg_type: int, include_media: bool = False) -> bool:
    """判断消息类型是否有效"""
    if msg_type in SYSTEM_MSG_TYPES or msg_type in LOW_QUALITY_TYPES:
        return True
    if msg_type in MEDIA_TYPES and not include_media:
        return False
    return msg_type in VALID_MSG_TYPES


def build_member_mapping(members: List[Dict], group_id: str = "") -> Dict[str, Dict]:
    """从成员列表构建 wxid → member_info 映射"""
    mapping = {}
    for member in members:
        wxid = member.get("platformId")
        if not wxid:
            continue
        if group_id and wxid == group_id:
            continue
        mapping[wxid] = {
            "accountName": member.get("accountName", ""),
            "avatar": member.get("avatar", ""),
        }
    return mapping


def extract_join_times(messages: List[Dict]) -> Dict[str, int]:
    """从系统消息提取入群时间（按昵称映射）"""
    result: Dict[str, int] = {}

    for msg in messages:
        msg_type = int(msg.get("type", -1))
        if msg_type not in SYSTEM_MSG_TYPES:
            continue

        content = clean_content(msg.get("content"))
        if "加入群聊" not in content:
            continue

        matches = re.findall(r"\"([^\"]+)\"", content)
        if not matches:
            continue

        joiner = matches[0].strip()
        if not joiner:
            continue

        timestamp = int(msg.get("timestamp", 0))
        if joiner not in result or timestamp < result[joiner]:
            result[joiner] = timestamp

    return result


def filter_and_parse_messages(
    messages: List[Dict],
    member_mapping: Dict[str, Dict],
    include_media: bool = False,
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

        if not is_valid_message(msg_type, include_media):
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
    return {
        "totalMessages": len(messages),
        "validMessages": len(messages) - filtered_count,
        "filteredMessages": filtered_count,
        "totalMembers": len(member_mapping),
    }


def save_processed_data(
    data: ProcessedData, output_dir: Path, group_name: str, save_individual: bool = True
) -> Dict[str, Any]:
    """
    保存处理后的数据

    Returns:
        {"main": Path, "members": List[Path]}
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    main_file = output_dir / f"{group_name}_processed.json"
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
    include_media: bool = False,
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

    member_mapping = build_member_mapping(members, group_info.group_id)
    join_times_by_nickname = extract_join_times(messages) if include_join_time else {}

    messages_by_member, filtered_count = filter_and_parse_messages(
        messages, member_mapping, include_media=include_media, show_progress=True
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
        result, Path(output_dir), group_info.name, save_individual=save_individual
    )

    return result, output_files


def parse_bool(value: Optional[str], default: bool = False) -> bool:
    """解析布尔环境变量"""
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def load_config_from_env() -> Dict[str, Any]:
    """从 .env 读取配置"""
    if load_dotenv is None:
        raise RuntimeError("缺少依赖 python-dotenv，请先安装")

    load_dotenv()

    input_path = os.getenv("INPUT_PATH") or os.getenv("DATA_PATH")
    if not input_path:
        raise ValueError("未在 .env 中配置 INPUT_PATH 或 DATA_PATH")

    output_dir = os.getenv("OUTPUT_DIR", "output")
    include_media = parse_bool(os.getenv("INCLUDE_MEDIA"), default=False)
    include_join_time = parse_bool(os.getenv("INCLUDE_JOIN_TIME"), default=True)
    save_individual = not parse_bool(os.getenv("NO_INDIVIDUAL"), default=False)

    return {
        "input_path": input_path,
        "output_dir": output_dir,
        "include_media": include_media,
        "include_join_time": include_join_time,
        "save_individual": save_individual,
    }


def main():
    """命令行入口"""
    config = load_config_from_env()

    try:
        input_path = Path(config["input_path"])
        validate_input_file(input_path)

        result, output_files = preprocess_chat_data(
            config["input_path"],
            config["output_dir"],
            config["include_media"],
            include_join_time=config["include_join_time"],
            save_individual=config["save_individual"],
        )

        print(f"\n✅ 处理完成！")
        print(f"📊 总成员数: {result.statistics['totalMembers']}")
        print(f"💬 有效消息: {result.statistics['validMessages']}")
        print(f"🗑️  过滤消息: {result.statistics['filteredMessages']}")
        print(f"📁 主文件: {output_files['main']}")
        if output_files["members"]:
            print(f"👥 成员文件: {len(output_files['members'])} 个 (output/members/)")

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
