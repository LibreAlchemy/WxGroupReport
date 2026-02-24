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

OUTPUT_DIR = os.getenv("OUTPUT_DIR", "./output")
MEMBERS_DIR = os.path.join(OUTPUT_DIR, "members")
SCORES_DIR = os.path.join(OUTPUT_DIR, "scores")
MODEL = os.getenv("MODEL", "gemini-2.0-flash")
API_KEY = os.getenv("GOOGLE_API_KEY")
MAX_WORKERS = 10  # 并发数

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
        "generationConfig": {"temperature": 0.3, "maxOutputTokens": 8192},
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
  "stats": {{", "resource": 0, "technical": 0qa": 0, "discussion": 0, "insight": 0, "opportunity": 0, "reply": 0}},
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
    """主流程 - 并行处理"""
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

    print(f"找到 {len(members)} 个成员，并行处理...")

    # 并行分析
    sem = asyncio.Semaphore(MAX_WORKERS)
    tasks = [analyze_member(sem, wxid, nick, msgs) for wxid, nick, msgs in members]
    results = await asyncio.gather(*tasks)

    # 保存结果
    for result in results:
        output_file = os.path.join(SCORES_DIR, f"{result['wxid']}.json")
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

    # 统计
    total_msgs = sum(r["messageCount"] for r in results)
    total_hl = sum(len(r.get("highlights", [])) for r in results)

    print(f"\n完成！")
    print(f"成员: {len(results)}, 消息: {total_msgs}, 高亮: {total_hl}")
    print(f"输出: {SCORES_DIR}")


if __name__ == "__main__":
    asyncio.run(main())
