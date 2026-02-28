"""
消息分析脚本
批量并行处理：从 output/members/ 读取，调用 AI SDK 评分，输出到 output/scores/
支持增量重试和错误记录 (errors.json)
支持通过环境变量配置不同模型厂商
"""

import asyncio
import json
import os
import sys
import glob
import argparse
import time
from pathlib import Path
from typing import List, Optional
from dotenv import load_dotenv
import litellm
from pydantic import BaseModel, Field

# 修复 Windows 控制台编码
if sys.platform == "win32":
    import codecs

    sys.stdout = codecs.getwriter("utf-8")(sys.stdout.buffer, "strict")
    sys.stderr = codecs.getwriter("utf-8")(sys.stderr.buffer, "strict")

load_dotenv()

litellm.drop_params = True

# 全局配置，将在 main 中更新
OUTPUT_DIR = "output"
MEMBERS_DIR = os.path.join(OUTPUT_DIR, "members")
SCORES_DIR = os.path.join(OUTPUT_DIR, "scores")
ERRORS_FILE = os.path.join(OUTPUT_DIR, "errors.json")

# AI 配置
AI_PROVIDER = os.getenv("AI_PROVIDER", "google")
AI_MODEL_NAME = os.getenv("AI_MODEL", "gemini-2.0-flash")
AI_API_KEY = os.getenv("AI_API_KEY")
AI_BASE_URL = os.getenv("AI_BASE_URL")

# 构造 litellm 模型名称
if "/" in AI_MODEL_NAME:
    LITELLM_MODEL = AI_MODEL_NAME
else:
    # 兼容旧配置，如果是 gemini/google 则统一为 gemini/
    provider = AI_PROVIDER.lower()
    if provider == "google":
        provider = "gemini"
    LITELLM_MODEL = f"{provider}/{AI_MODEL_NAME}"

# 默认并发数
DEFAULT_MAX_WORKERS = 10


def resolve_max_workers() -> int:
    raw = os.getenv("MAX_ANALYZE_WORKERS", str(DEFAULT_MAX_WORKERS))
    try:
        value = int(raw)
        return max(1, value)
    except ValueError:
        print(
            f"⚠️ 无效 MAX_ANALYZE_WORKERS={raw!r}，将使用默认值 {DEFAULT_MAX_WORKERS}",
            file=sys.stderr,
        )
        return DEFAULT_MAX_WORKERS


MAX_WORKERS = resolve_max_workers()
SLOW_API_SECONDS = float(os.getenv("ANALYZE_SLOW_API_SECONDS", "8"))
LOG_INFLIGHT = os.getenv("ANALYZE_LOG_INFLIGHT", "0") not in {"0", "false", "False"}

class Highlight(BaseModel):
    type: str = Field(description="文章|GitHub|见解|机会 (article|github|insight|opportunity)")
    content: str = Field(description="高亮内容的简短描述")
    url: str = Field(default="", description="相关的 URL 链接")


class Stats(BaseModel):
    resource: int = Field(default=0, description="资源分享")
    technical: int = Field(default=0, description="技术探讨")
    qa: int = Field(default=0, description="问答/求助")
    discussion: int = Field(default=0, description="一般讨论")
    insight: int = Field(default=0, description="深度见解")
    opportunity: int = Field(default=0, description="合作机会")
    reply: int = Field(default=0, description="回复他人")


class AnalysisResult(BaseModel):
    summary: str = Field(description="成员消息的总结（30-100字）")
    quality_score: int = Field(
        default=50, ge=0, le=100, description="成员整体内容质量分（0-100）"
    )
    stats: Stats = Field(description="各类型消息的数量统计")
    highlights: List[Highlight] = Field(default_factory=list, description="消息中的亮点内容")


def filter_effective_messages(messages: list) -> list:
    """过滤无效消息（当前规则：去掉以 '#接龙' 开头的消息）"""
    return [
        m for m in messages if not m.get("content", "").strip().startswith("#接龙")
    ]


def build_prompt(wxid: str, nickname: str, filtered_messages: list) -> str:
    """构建评分 prompt"""
    msgs_text = "\n".join(
        [f"{i}. {m.get('content', '')}" for i, m in enumerate(filtered_messages)]
    )

    return f"""## 任务
分析以下微信群成员的消息，给出总结和评分。

## 成员: {nickname} ({len(filtered_messages)}条消息)

## 消息内容
{msgs_text}

## 注意事项
1. 总结要客观准确，涵盖成员的主要言论特点。
2. stats 统计应基于消息内容进行合理分类。
3. highlights 仅记录高价值内容，且 type 必须严格使用以下定义：
   - article: 公众号/博客/新闻/技术文章。`content` 必须是文章原始标题；若无法确定原始标题，`content` 置为空字符串。
   - github: GitHub 仓库/代码项目。`content` 根据对话内容总结该仓库描述。
   - insight: 原创观点/经验总结/判断结论。`content` 填消息原文。
   - opportunity: 招聘/内推/合作招募/项目招募等机会信息。`content` 填机会摘要。
4. `highlights.url` 仅在消息中存在明确链接时填写，否则置为空字符串。
5. 必须输出 quality_score（0-100），用于评估成员整体内容质量，尽量拉开分布。

## quality_score 评分锚点
- 0~20: 几乎无信息量，纯表情/灌水/重复复读
- 21~40: 信息量较低，闲聊为主，偶有有效内容
- 41~60: 有一定信息量，包含问题、回复或一般观点
- 61~80: 持续输出有效内容，有较强技术/资源价值
- 81~100: 高密度高价值输出，具备深度见解或强资源贡献

## 输出格式 (JSON)
{{
  "summary": "总结（30-100字）",
  "quality_score": 0,
  "stats": {{"resource": 0, "technical": 0, "qa": 0, "discussion": 0, "insight": 0, "opportunity": 0, "reply": 0}},
  "highlights": [{{"type": "article|github|insight|opportunity", "content": "", "url": ""}}]
}}
"""


async def analyze_member(sem, wxid: str, nickname: str, messages: list, inflight_state) -> dict:
    """分析单个成员"""
    async with sem:
        async with inflight_state["lock"]:
            inflight_state["count"] += 1
            current_inflight = inflight_state["count"]
        if LOG_INFLIGHT:
            print(f"🚦 并发占用 {current_inflight}/{MAX_WORKERS} -> 开始: {nickname} ({wxid})")

        t0 = time.perf_counter()
        try:
            filtered_messages = filter_effective_messages(messages)
            effective_count = len(filtered_messages)

            if effective_count == 0:
                return {
                    "wxid": wxid,
                    "nickname": nickname,
                    "messageCount": 0,
                    "qualityScore": 0,
                    "summary": "无消息",
                    "stats": {},
                    "highlights": [],
                    "status": "zero_activity",
                    "apiDurationSec": round(time.perf_counter() - t0, 3),
                }

            try:
                prompt = build_prompt(wxid, nickname, filtered_messages)
                
                # 使用 litellm 进行结构化输出
                response = await litellm.acompletion(
                    model=LITELLM_MODEL,
                    messages=[{"role": "user", "content": prompt}],
                    response_format=AnalysisResult,
                    api_key=AI_API_KEY,
                    base_url=AI_BASE_URL,
                )
                
                # 解析结果
                content = response.choices[0].message.content
                
                # 处理可能的 markdown 代码块
                if content.startswith("```json"):
                    content = content.replace("```json", "", 1).rsplit("```", 1)[0].strip()
                elif content.startswith("```"):
                    content = content.replace("```", "", 1).rsplit("```", 1)[0].strip()
                
                result = AnalysisResult.model_validate_json(content)
                
                stats_dict = result.stats.model_dump()
                quality_score = max(0, min(100, int(result.quality_score)))

                return {
                    "wxid": wxid,
                    "nickname": nickname,
                    "messageCount": effective_count,
                    "qualityScore": round(float(quality_score), 1),
                    "summary": result.summary,
                    "stats": stats_dict,
                    "highlights": [h.model_dump() for h in result.highlights],
                    "status": "normal",
                    "apiDurationSec": round(time.perf_counter() - t0, 3),
                }
            except Exception as e:
                print(f"❌ 分析成员 {nickname} ({wxid}) 失败: {str(e)}", file=sys.stderr)
                return {
                    "wxid": wxid,
                    "nickname": nickname,
                    "messageCount": effective_count,
                    "qualityScore": 0,
                    "summary": "",
                    "stats": {},
                    "highlights": [],
                    "status": "error",
                    "error": str(e),
                    "apiDurationSec": round(time.perf_counter() - t0, 3),
                }
        finally:
            async with inflight_state["lock"]:
                inflight_state["count"] = max(0, inflight_state["count"] - 1)


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

    if not AI_API_KEY:
        print(f"❌ 错误: 未设置 AI API Key (Model: {LITELLM_MODEL})", file=sys.stderr)
        return

    Path(SCORES_DIR).mkdir(parents=True, exist_ok=True)

    print(f"🤖 使用模型: {LITELLM_MODEL}")
    print(f"⚙️ 并发配置: MAX_ANALYZE_WORKERS={MAX_WORKERS}, 慢请求阈值={SLOW_API_SECONDS:.1f}s")

    loop_round = 0

    while True:
        loop_round += 1
        round_t0 = time.perf_counter()
        # 1. 识别待处理成员
        pending_members = []
        errors_data = load_errors()
        scan_t0 = time.perf_counter()
        
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
                            if wxid in errors_data:
                                del errors_data[wxid]
                            continue
                    except:
                        pass

            pending_members.append((wxid, nickname, messages))

        scan_cost = time.perf_counter() - scan_t0
        print(f"🧭 第{loop_round}轮扫描完成: 待处理 {len(pending_members)} 人, 用时 {scan_cost:.2f}s")

        if not pending_members:
            save_errors(errors_data)
            print("✅ 所有成员已成功分析。")
            break

        print(f"🔄 发现 {len(pending_members)} 个待处理/重试成员...")
        
        # 统一并发处理
        sem = asyncio.Semaphore(MAX_WORKERS)
        inflight_state = {"count": 0, "lock": asyncio.Lock()}
        tasks = [
            analyze_member(sem, wxid, nick, msgs, inflight_state)
            for wxid, nick, msgs in pending_members
        ]
        
        batch_results = []
        completed = 0
        total = len(tasks)
        batch_t0 = time.perf_counter()
        
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
            api_cost = result.get("apiDurationSec", 0.0)
            print(f"[{completed}/{total}] {status_char} {nickname} ({msg_count}条, {api_cost:.2f}s)")

        # 2. 统计本轮结果
        success_count = sum(1 for r in batch_results if r["status"] != "error")
        error_count = len(batch_results) - success_count
        batch_cost = time.perf_counter() - batch_t0
        durations = sorted(r.get("apiDurationSec", 0.0) for r in batch_results)
        avg_cost = (sum(durations) / len(durations)) if durations else 0.0
        p95_cost = durations[int(len(durations) * 0.95) - 1] if durations else 0.0
        slow_count = sum(1 for d in durations if d >= SLOW_API_SECONDS)

        print(f"📈 本轮完成: 成功 {success_count}, 失败 {error_count}, 总耗时 {batch_cost:.2f}s")
        print(f"⏱️ API耗时统计: avg={avg_cost:.2f}s, p95={p95_cost:.2f}s, slow>={SLOW_API_SECONDS:.1f}s: {slow_count}/{len(durations)}")
        
        if error_count == 0:
            round_cost = time.perf_counter() - round_t0
            print(f"✅ 第{loop_round}轮已收敛, 总用时 {round_cost:.2f}s")
            break
        
        # 如果有错误，等待一段时间后重试
        wait_retry = 10
        print(f"⏳ 等待 {wait_retry} 秒后开始下一轮重试...")
        await asyncio.sleep(wait_retry)

    # 3. 最终汇总
    print("📊 正在生成最终汇总报告...")
    summary_t0 = time.perf_counter()
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

    analysis_data = {
        "success": True,
        "data": {
            "memberScores": results,
            "highlights": all_highlights,
        },
    }
    analysis_path = os.path.join(OUTPUT_DIR, "analyze.json")
    with open(analysis_path, "w", encoding="utf-8") as f:
        json.dump(analysis_data, f, ensure_ascii=False, indent=2)

    total_msgs = sum(r["messageCount"] for r in results)
    summary_cost = time.perf_counter() - summary_t0
    print(f"\n✨ 分析全部完成！")
    print(f"总成员: {len(results)}, 总消息: {total_msgs}, 总高亮: {len(all_highlights)}")
    print(f"🧾 汇总写盘耗时: {summary_cost:.2f}s")
    print(f"结果已汇总至: {analysis_path}")


if __name__ == "__main__":
    asyncio.run(main())
