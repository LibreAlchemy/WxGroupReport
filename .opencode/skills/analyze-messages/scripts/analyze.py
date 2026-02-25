"""
消息分析脚本
批量并行处理：从 output/members/ 读取，调用 Gemini 评分，输出到 output/scores/
"""

import asyncio
import json
import os
import sys
import glob
from pathlib import Path
from dotenv import load_dotenv

# 修复 Windows 控制台编码
if sys.platform == "win32":
    import codecs

    sys.stdout = codecs.getwriter("utf-8")(sys.stdout.buffer, "strict")
    sys.stderr = codecs.getwriter("utf-8")(sys.stderr.buffer, "strict")

load_dotenv()

SCRIPT_DIR = Path(__file__).parent
PROJECT_DIR = SCRIPT_DIR.parent.parent.parent.parent
OUTPUT_DIR = os.path.join(PROJECT_DIR, "output")
MEMBERS_DIR = os.path.join(OUTPUT_DIR, "members")
SCORES_DIR = os.path.join(OUTPUT_DIR, "scores")
MODEL = os.getenv("MODEL", "gemini-2.0-flash")
API_KEY = os.getenv("GOOGLE_API_KEY")
MAX_WORKERS = 10  # 并发数
MAX_MESSAGES_PER_CALL = 100  # 单次调用最大消息数
MAX_TOTAL_LENGTH = 15000  # 单次调用最大字符数

GEMINI_API_URL = (
    f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"
)


async def call_gemini(prompt: str, retries=3) -> dict:
    """调用 Gemini API"""
    import aiohttp
    import re

    url = f"{GEMINI_API_URL}?key={API_KEY}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.3},
    }

    proxy = os.getenv("HTTP_PROXY") or os.getenv("HTTPS_PROXY")

    for attempt in range(retries):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, proxy=proxy) as response:
                    if response.status != 200:
                        error = await response.text()
                        raise RuntimeError(f"API error: {response.status}")
                    result = await response.json()
                    text = result["candidates"][0]["content"]["parts"][0]["text"]

                    text = text.strip()
                    if text.startswith("```"):
                        text = re.sub(r"^```[a-z]*\n?", "", text)
                        text = re.sub(r"\n?```$", "", text)

                    match = re.search(r"\{[\s\S]*\}", text)
                    if match:
                        return json.loads(match.group())
                    raise ValueError(f"Cannot parse JSON")
        except Exception as e:
            if attempt < retries - 1:
                await asyncio.sleep(1)
                continue
            raise


def estimate_content_length(messages: list) -> int:
    """估算消息总长度（字符数）"""
    total = 0
    for m in messages:
        content = m.get("content", "")
        total += len(content)
        total += len(str(m.get("timestamp", "")))
    return total


def needs_separate_processing(messages: list) -> bool:
    """判断是否需要单独处理（消息数过多或总长度过长）"""
    return (
        len(messages) > MAX_MESSAGES_PER_CALL
        or estimate_content_length(messages) > MAX_TOTAL_LENGTH
    )


def build_prompt(wxid: str, nickname: str, messages: list) -> str:
    """构建评分 prompt"""
    msgs_text = "\n".join(
        [f"{i}. {m.get('content', '')}" for i, m in enumerate(messages)]
    )

    return f"""## 任务
分析以下群成员的消息，给出总结和评分。

## 成员: {nickname} ({len(messages)}条消息)

## 消息
{msgs_text}

## 输出格式 (JSON)
{{
  "summary": "总结（30-100字）",
  "stats": {{"resource": 0, "technical": 0, "qa": 0, "discussion": 0, "insight": 0, "opportunity": 0, "reply": 0}},
  "highlights": [{{"type": "article|github|insight|opportunity", "content": "", "url": ""}}]
}}
只返回JSON。"""


async def analyze_member(sem, wxid: str, nickname: str, messages: list) -> dict:
    """分析单个成员"""
    async with sem:
        if not messages:
            return {
                "wxid": wxid,
                "nickname": nickname,
                "messageCount": 0,
                "totalScore": 0,
                "averageScore": 0,
                "summary": "无消息",
                "stats": {},
                "highlights": [],
                "status": "zero_activity",
            }

        try:
            prompt = build_prompt(wxid, nickname, messages)
            result = await call_gemini(prompt)
            stats = result.get("stats", {})
            total = sum(stats.values()) if stats else 0
            avg = total / len(messages) if messages else 0

            return {
                "wxid": wxid,
                "nickname": nickname,
                "messageCount": len(messages),
                "totalScore": total,
                "averageScore": round(avg, 2),
                "summary": result.get("summary", ""),
                "stats": stats,
                "highlights": result.get("highlights", []),
                "status": "normal",
            }
        except Exception as e:
            return {
                "wxid": wxid,
                "nickname": nickname,
                "messageCount": len(messages),
                "totalScore": 0,
                "averageScore": 0,
                "summary": "",
                "stats": {},
                "highlights": [],
                "status": "error",
                "error": str(e),
            }


async def main():
    """主流程 - 分组处理：超长成员单独处理，其他并行处理"""
    Path(SCORES_DIR).mkdir(parents=True, exist_ok=True)

    # 加载所有成员
    members = []
    for filepath in glob.glob(os.path.join(MEMBERS_DIR, "*.json")):
        with open(filepath, encoding="utf-8") as f:
            data = json.load(f)
        wxid = data.get("wxid", Path(filepath).stem)
        nickname = data.get("nickname", wxid)
        messages = data.get("messages", [])
        members.append((wxid, nickname, messages))

    # 分离：超长成员单独处理，其他并行处理
    separate_members = []
    normal_members = []
    for wxid, nickname, messages in members:
        if needs_separate_processing(messages):
            separate_members.append((wxid, nickname, messages))
        else:
            normal_members.append((wxid, nickname, messages))

    # 统一并发处理（超长成员会占用更多时间，但与其他成员并行）
    sem = asyncio.Semaphore(MAX_WORKERS)
    all_members = normal_members + separate_members

    print(f"正在并行处理 {len(all_members)} 个成员 (并发={MAX_WORKERS})...")
    tasks = [analyze_member(sem, wxid, nick, msgs) for wxid, nick, msgs in all_members]
    results = await asyncio.gather(*tasks)

    # 输出超长成员处理结果
    for r in results:
        if needs_separate_processing([{"content": ""}] * r["messageCount"]):
            print(f"  - {r['nickname']}: {r['messageCount']}条")

    # 保存结果
    for result in results:
        output_file = os.path.join(SCORES_DIR, f"{result['wxid']}.json")
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

    # 生成合并的 analyze-messages.json（供报告生成使用）
    all_highlights = []
    for r in results:
        for h in r.get("highlights", []):
            h["author"] = r["nickname"]
            all_highlights.append(h)

    # 计算低质成员（根据当前评分系统调整阈值）
    LOW_SCORE_THRESHOLD = 0.5  # 均分低于0.5
    LOW_MSG_THRESHOLD = 15  # 发言少于15条

    low_quality_members = []
    for r in results:
        msg_count = r.get("messageCount", 0)
        avg_score = r.get("averageScore", 0)

        if msg_count == 0:
            low_quality_members.append(
                {
                    "wxid": r["wxid"],
                    "nickname": r["nickname"],
                    "messageCount": msg_count,
                    "averageScore": avg_score,
                    "status": "zero_activity",
                    "severity": "high",
                    "reason": "无消息",
                }
            )
        elif avg_score < LOW_SCORE_THRESHOLD and msg_count < LOW_MSG_THRESHOLD:
            low_quality_members.append(
                {
                    "wxid": r["wxid"],
                    "nickname": r["nickname"],
                    "messageCount": msg_count,
                    "averageScore": avg_score,
                    "status": "low_quality",
                    "severity": "medium",
                    "reason": f"发言{msg_count}条且均分{avg_score:.1f}低",
                }
            )
        elif msg_count < LOW_MSG_THRESHOLD:
            low_quality_members.append(
                {
                    "wxid": r["wxid"],
                    "nickname": r["nickname"],
                    "messageCount": msg_count,
                    "averageScore": avg_score,
                    "status": "low_frequency",
                    "severity": "low",
                    "reason": f"发言仅{msg_count}条",
                }
            )

    # 按严重程度排序：high > medium > low
    severity_order = {"high": 0, "medium": 1, "low": 2}
    low_quality_members.sort(key=lambda x: severity_order.get(x["severity"], 3))

    analysis_data = {
        "success": True,
        "data": {
            "memberScores": results,
            "highlights": all_highlights,
            "lowQualityMembers": low_quality_members,
        },
    }
    analysis_path = os.path.join(OUTPUT_DIR, "analyze-messages.json")
    with open(analysis_path, "w", encoding="utf-8") as f:
        json.dump(analysis_data, f, ensure_ascii=False, indent=2)

    # 统计
    total_msgs = sum(r["messageCount"] for r in results)
    total_hl = sum(len(r.get("highlights", [])) for r in results)
    errors = sum(1 for r in results if r.get("status") == "error")

    print(f"\n完成！")
    print(f"成员: {len(results)}, 消息: {total_msgs}, 高亮: {total_hl}")
    if errors > 0:
        print(f"错误: {errors}")
    print(f"输出: {SCORES_DIR}")


if __name__ == "__main__":
    asyncio.run(main())
