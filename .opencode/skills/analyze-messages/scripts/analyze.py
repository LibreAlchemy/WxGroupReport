"""
消息分析脚本
批量并行处理：从 output/members/ 读取，调用 Gemini 评分，输出到 output/scores/
支持增量重试和错误记录 (errors.json)
"""

import asyncio
import json
import os
import sys
import glob
import argparse
from pathlib import Path
from dotenv import load_dotenv

# 修复 Windows 控制台编码
if sys.platform == "win32":
    import codecs

    sys.stdout = codecs.getwriter("utf-8")(sys.stdout.buffer, "strict")
    sys.stderr = codecs.getwriter("utf-8")(sys.stderr.buffer, "strict")

load_dotenv()

# 全局配置，将在 main 中更新
OUTPUT_DIR = "output"
MEMBERS_DIR = os.path.join(OUTPUT_DIR, "members")
SCORES_DIR = os.path.join(OUTPUT_DIR, "scores")
ERRORS_FILE = os.path.join(OUTPUT_DIR, "errors.json")
MODEL = os.getenv("MODEL", "gemini-2.0-flash")
API_KEY = os.getenv("GOOGLE_API_KEY")
MAX_WORKERS = 5  # 并发数
MAX_MESSAGES_PER_CALL = 100  # 单次调用最大消息数
MAX_TOTAL_LENGTH = 15000  # 单次调用最大字符数

GEMINI_API_URL = (
    f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"
)


async def call_gemini(prompt: str) -> dict:
    """调用 Gemini API"""
    import aiohttp
    import re

    url = f"{GEMINI_API_URL}?key={API_KEY}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.3},
    }

    proxy = os.getenv("HTTP_PROXY") or os.getenv("HTTPS_PROXY")

    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload, proxy=proxy) as response:
            if response.status != 200:
                if response.status == 429:
                    raise RuntimeError(f"API error: 429 (Rate Limit)")
                raise RuntimeError(f"API error: {response.status}")
            
            result = await response.json()
            if "candidates" not in result or not result["candidates"]:
                raise RuntimeError(f"API error: No candidates in response. {json.dumps(result)}")
                
            text = result["candidates"][0]["content"]["parts"][0]["text"]

            text = text.strip()
            if text.startswith("```"):
                text = re.sub(r"^```[a-z]*\n?", "", text)
                text = re.sub(r"\n?```$", "", text)

            match = re.search(r"\{[\s\S]*\}", text)
            if match:
                return json.loads(match.group())
            raise ValueError(f"Cannot parse JSON from text: {text[:100]}...")


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


def load_errors() -> dict:
    if os.path.exists(ERRORS_FILE):
        try:
            with open(ERRORS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {}
    return {}


def save_errors(errors: dict):
    if not errors:
        if os.path.exists(ERRORS_FILE):
            os.remove(ERRORS_FILE)
        return
    with open(ERRORS_FILE, "w", encoding="utf-8") as f:
        json.dump(errors, f, ensure_ascii=False, indent=2)


async def main():
    global OUTPUT_DIR, MEMBERS_DIR, SCORES_DIR, ERRORS_FILE

    parser = argparse.ArgumentParser(description="消息分析脚本")
    parser.add_argument("-o", "--output", help="输出目录 (OUTPUT_DIR)")
    args = parser.parse_args()

    OUTPUT_DIR = args.output or os.getenv("OUTPUT_DIR", "output")
    MEMBERS_DIR = os.path.join(OUTPUT_DIR, "members")
    SCORES_DIR = os.path.join(OUTPUT_DIR, "scores")
    ERRORS_FILE = os.path.join(OUTPUT_DIR, "errors.json")

    if not API_KEY:
        print("❌ 错误: 未设置 GOOGLE_API_KEY 环境变量", file=sys.stderr)
        return

    Path(SCORES_DIR).mkdir(parents=True, exist_ok=True)

    while True:
        # 1. 识别待处理成员
        pending_members = []
        errors_data = load_errors()
        
        # 扫描 members 目录
        for filepath in glob.glob(os.path.join(MEMBERS_DIR, "*.json")):
            with open(filepath, encoding="utf-8") as f:
                data = json.load(f)
            wxid = data.get("wxid")
            nickname = data.get("nickname", wxid)
            messages = data.get("messages", [])
            
            if not wxid:
                continue

            score_path = os.path.join(SCORES_DIR, f"{wxid}.json")
            
            # 如果已经存在成功的评分，跳过
            if os.path.exists(score_path):
                with open(score_path, encoding="utf-8") as f:
                    try:
                        score_data = json.load(f)
                        # 只要 status 不是 error，就说明已经处理过了（包括 normal, zero_activity, low_frequency 等）
                        if score_data.get("status") != "error":
                            continue
                    except:
                        pass

            pending_members.append((wxid, nickname, messages))

        if not pending_members:
            print("✅ 所有成员已成功分析。")
            break

        print(f"🔄 发现 {len(pending_members)} 个待处理/重试成员...")
        
        # 统一并发处理
        sem = asyncio.Semaphore(MAX_WORKERS)
        tasks = [analyze_member(sem, wxid, nick, msgs) for wxid, nick, msgs in pending_members]
        
        batch_results = []
        completed = 0
        total = len(tasks)
        
        for coro in asyncio.as_completed(tasks):
            result = await coro
            batch_results.append(result)
            completed += 1
            
            wxid = result["wxid"]
            nickname = result["nickname"]
            msg_count = result["messageCount"]
            
            if result["status"] == "error":
                status_char = "❌"
                errors_data[wxid] = {
                    "nickname": nickname,
                    "error": result["error"],
                    "messageCount": msg_count
                }
                # 确保 scores 下没有旧记录
                score_path = os.path.join(SCORES_DIR, f"{wxid}.json")
                if os.path.exists(score_path):
                    try:
                        os.remove(score_path)
                    except:
                        pass
            else:
                status_char = "✅"
                # 成功，写入 scores 目录
                output_file = os.path.join(SCORES_DIR, f"{wxid}.json")
                with open(output_file, "w", encoding="utf-8") as f:
                    json.dump(result, f, ensure_ascii=False, indent=2)
                
                # 从错误记录中移除
                if wxid in errors_data:
                    del errors_data[wxid]
            
            # 即时保存错误记录
            save_errors(errors_data)
            print(f"[{completed}/{total}] {status_char} {nickname} ({msg_count}条)")

        # 2. 统计本轮结果
        success_count = sum(1 for r in batch_results if r["status"] != "error")
        error_count = len(batch_results) - success_count
        
        print(f"📈 本轮完成: 成功 {success_count}, 失败 {error_count}")
        
        if error_count == 0:
            break
        
        # 如果有错误，等待一段时间后重试
        wait_retry = 10
        print(f"⏳ 等待 {wait_retry} 秒后开始下一轮重试...")
        await asyncio.sleep(wait_retry)

    # 3. 最终汇总
    print("📊 正在生成最终汇总报告...")
    results = []
    for filepath in glob.glob(os.path.join(SCORES_DIR, "*.json")):
        with open(filepath, encoding="utf-8") as f:
            try:
                data = json.load(f)
                if data.get("status") in ["normal", "zero_activity"]:
                    results.append(data)
            except:
                continue

    all_highlights = []
    for r in results:
        for h in r.get("highlights", []):
            h["author"] = r["nickname"]
            all_highlights.append(h)

    # 计算低质成员
    LOW_SCORE_THRESHOLD = 0.5
    LOW_MSG_THRESHOLD = 15

    low_quality_members = []
    for r in results:
        msg_count = r.get("messageCount", 0)
        avg_score = r.get("averageScore", 0)

        if msg_count == 0:
            low_quality_members.append({
                "wxid": r["wxid"], "nickname": r["nickname"],
                "messageCount": msg_count, "averageScore": avg_score,
                "status": "zero_activity", "severity": "high", "reason": "无消息"
            })
        elif avg_score < LOW_SCORE_THRESHOLD and msg_count < LOW_MSG_THRESHOLD:
            low_quality_members.append({
                "wxid": r["wxid"], "nickname": r["nickname"],
                "messageCount": msg_count, "averageScore": avg_score,
                "status": "low_quality", "severity": "medium", "reason": f"发言{msg_count}条且均分{avg_score:.1f}低"
            })
        elif msg_count < LOW_MSG_THRESHOLD:
            low_quality_members.append({
                "wxid": r["wxid"], "nickname": r["nickname"],
                "messageCount": msg_count, "averageScore": avg_score,
                "status": "low_frequency", "severity": "low", "reason": f"发言仅{msg_count}条"
            })

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

    total_msgs = sum(r["messageCount"] for r in results)
    print(f"\n✨ 分析全部完成！")
    print(f"总成员: {len(results)}, 总消息: {total_msgs}, 总高亮: {len(all_highlights)}")
    print(f"结果已汇总至: {analysis_path}")


if __name__ == "__main__":
    asyncio.run(main())
