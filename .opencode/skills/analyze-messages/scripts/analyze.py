"""
消息分析主脚本
从 .env 读取配置
"""

import asyncio
import json
import os
from pathlib import Path
from typing import Dict, List, Any, Optional

from dotenv import load_dotenv

load_dotenv()

OUTPUT_DIR = os.getenv("OUTPUT_DIR", "./output")
MEMBERS_DIR = os.path.join(OUTPUT_DIR, "members")
SCORES_DIR = os.path.join(OUTPUT_DIR, "scores")

from api_client import GeminiClient
from batcher import balance_members, split_member_messages


def load_members(members_path: str) -> List[Dict[str, Any]]:
    """从目录加载成员消息"""
    members_dir = Path(members_path)
    if not members_dir.exists():
        raise FileNotFoundError(f"Members directory not found: {members_path}")

    members = []
    for file_path in members_dir.glob("*.json"):
        try:
            data = json.loads(file_path.read_text(encoding="utf-8"))
            if data.get("messages"):
                members.append(data)
        except (json.JSONDecodeError, KeyError) as e:
            print(f"Warning: Skip invalid file {file_path}: {e}")

    return members


async def analyze_member(
    client: GeminiClient, member: Dict[str, Any]
) -> Dict[str, Any]:
    """分析单个成员的消息"""
    wxid = member["wxid"]
    nickname = member.get("nickname", wxid)
    messages = member.get("messages", [])

    if not messages:
        return {
            "wxid": wxid,
            "nickname": nickname,
            "messageCount": 0,
            "totalScore": 0,
            "averageScore": 0,
            "summary": "无消息",
            "scores": [],
            "highlights": [],
            "status": "zero_activity",
        }

    result = await client.score_messages(wxid, nickname, messages)

    total_score = sum(s.get("total_score", 0) for s in result.scores)
    avg_score = total_score / len(result.scores) if result.scores else 0

    return {
        "wxid": wxid,
        "nickname": nickname,
        "messageCount": len(messages),
        "totalScore": total_score,
        "averageScore": round(avg_score, 2),
        "summary": result.summary,
        "scores": result.scores,
        "highlights": result.highlights,
        "status": "normal",
    }


async def analyze_parallel(
    members: List[Dict[str, Any]], config: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """并行分析成员消息"""
    max_workers = config.get("maxWorkers", 5)
    batch_size = config.get("batchSize", 100)

    client = GeminiClient(
        api_key=config.get("apiKey"), model=config.get("model", "gemini-2.0-flash")
    )

    member_batches = []

    for member in members:
        batches = split_member_messages(member, batch_size)
        member_batches.extend(batches)

    buckets = balance_members(member_batches, num_buckets=max_workers)

    async def process_bucket(bucket):
        results = []
        for batch in bucket:
            result = await analyze_member(client, batch)
            results.append(result)
        return results

    tasks = [process_bucket(bucket) for bucket in buckets]
    bucket_results = await asyncio.gather(*tasks)

    member_results = {}
    for bucket_result in bucket_results:
        for result in bucket_result:
            wxid = result["wxid"]
            if wxid not in member_results:
                member_results[wxid] = {
                    "wxid": result["wxid"],
                    "nickname": result["nickname"],
                    "messageCount": 0,
                    "totalScore": 0,
                    "summary": "",
                    "highlights": [],
                }
            member_results[wxid]["messageCount"] += result["messageCount"]
            member_results[wxid]["totalScore"] += result["totalScore"]
            member_results[wxid]["summary"] = result["summary"]
            member_results[wxid]["highlights"].extend(result.get("highlights", []))

    for wxid, data in member_results.items():
        if data["messageCount"] > 0:
            data["averageScore"] = round(data["totalScore"] / data["messageCount"], 2)
        else:
            data["averageScore"] = 0
            data["status"] = "zero_activity"

    return list(member_results.values())


def determine_low_quality(
    members: List[Dict[str, Any]], config: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """判定低质成员"""
    threshold = config.get("lowQualityThreshold", 60)
    min_count = config.get("minMessageCount", 5)

    low_quality = []

    for member in members:
        if member["messageCount"] == 0:
            low_quality.append(
                {
                    "wxid": member["wxid"],
                    "nickname": member["nickname"],
                    "messageCount": member["messageCount"],
                    "averageScore": member["averageScore"],
                    "status": "zero_activity",
                    "severity": "high",
                    "reason": "周期内无任何有效消息",
                }
            )
        elif member["averageScore"] < threshold:
            low_quality.append(
                {
                    "wxid": member["wxid"],
                    "nickname": member["nickname"],
                    "messageCount": member["messageCount"],
                    "averageScore": member["averageScore"],
                    "status": "low_quality",
                    "severity": "medium",
                    "reason": f"平均分 {member['averageScore']} < {threshold}",
                }
            )
        elif member["messageCount"] < min_count:
            low_quality.append(
                {
                    "wxid": member["wxid"],
                    "nickname": member["nickname"],
                    "messageCount": member["messageCount"],
                    "averageScore": member["averageScore"],
                    "status": "low_frequency",
                    "severity": "low",
                    "reason": f"发言数 {member['messageCount']} < {min_count}",
                }
            )

    severity_order = {"high": 0, "medium": 1, "low": 2}
    return sorted(low_quality, key=lambda x: severity_order[x["severity"]])


def run_analysis(config: Optional[Dict] = None) -> Dict:
    """运行分析主流程"""
    config = config or {}

    members = load_members(MEMBERS_DIR)

    results = asyncio.run(analyze_parallel(members, config))

    highlights = []
    for member in results:
        for hl in member.get("highlights", []):
            hl["author"] = member["nickname"]
            highlights.append(hl)

    low_quality = determine_low_quality(results, config)

    output = {
        "success": True,
        "data": {
            "memberScores": results,
            "highlights": highlights,
            "lowQualityMembers": low_quality,
            "summary": {
                "totalMembers": len(members),
                "analyzedMembers": len(results),
                "totalMessages": sum(m["messageCount"] for m in results),
                "highlightsCount": len(highlights),
                "lowQualityCount": len(low_quality),
            },
        },
    }

    Path(SCORES_DIR).mkdir(parents=True, exist_ok=True)
    output_file = os.path.join(SCORES_DIR, "analyze-messages.json")
    Path(output_file).write_text(
        json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    return output
