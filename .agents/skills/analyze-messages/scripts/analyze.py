"""
消息分析脚本
批量并行处理：从 output/members/ 读取，调用 AI SDK 评分，输出到 output/scores/
支持增量重试和错误记录 (errors.json)
支持通过环境变量配置不同模型厂商
"""

import asyncio
import json
import os
import re
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


def build_output_paths(output_dir: str) -> dict[str, str]:
    return {
        "output_dir": output_dir,
        "members_dir": os.path.join(output_dir, "members"),
        "scores_dir": os.path.join(output_dir, "scores"),
        "errors_file": os.path.join(output_dir, "errors.json"),
        "analysis_path": os.path.join(output_dir, "analyze.json"),
    }


def sanitize_highlight_output(highlights: list[dict]) -> list[dict]:
    """清理 highlights 输出：空链接字段不写入最终结果"""
    cleaned = []
    for item in highlights:
        normalized = dict(item)
        if not normalized.get("url", "").strip():
            normalized.pop("url", None)
        cleaned.append(normalized)
    return cleaned


def extract_json_payload(content: str) -> str:
    """兼容模型返回的 markdown 代码块，只提取 JSON 主体。"""
    text = (content or "").strip()
    if text.startswith("```json"):
        return text.replace("```json", "", 1).rsplit("```", 1)[0].strip()
    if text.startswith("```"):
        return text.replace("```", "", 1).rsplit("```", 1)[0].strip()
    return text


def normalize_analysis_payload(payload: dict) -> AnalysisResult:
    """对模型原始 JSON 做兜底归一化，再交给 Pydantic 校验。"""
    normalized = {
        "summary": payload.get("summary", "") or "",
        "quality_score": payload.get("quality_score", 50),
        "stats": payload.get("stats") or {},
        "highlights": payload.get("highlights") or [],
    }
    return AnalysisResult.model_validate(normalized)


def filter_effective_messages(messages: list) -> list:
    """过滤无效消息"""
    return [
        m
        for m in messages
        if not m.get("content", "").strip().startswith("#接龙")
        and not m.get("content", "").strip().startswith("../images/")
    ]


def truncate_message_content(content: str, max_chars: int = 300) -> str:
    """截断单条消息内容，避免 prompt 被超长消息撑大"""
    text = str(content or "").strip()
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "..."


def strip_quoted_reply_blocks(content: str) -> str:
    """剥离消息中的内联引用块，避免把被引用内容算到当前成员头上。"""
    text = str(content or "")

    # 常见导出格式：正文[引用 昵称：被引用内容]
    prev = None
    while prev != text:
        prev = text
        text = re.sub(r"\[引用 [^\[\]]*?\]", "", text)

    # 清理剥离引用后留下的多余空白
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def format_messages_for_prompt(messages: list) -> str:
    """将消息按时间升序格式化为 prompt 文本"""
    sorted_messages = sorted(messages, key=lambda m: m.get("timestamp", ""))
    return "\n".join(
        f"[{m.get('timestamp', '')}] {truncate_message_content(strip_quoted_reply_blocks(m.get('content', '')))}"
        for m in sorted_messages
        if strip_quoted_reply_blocks(m.get("content", "")).strip()
    )


def build_prompt(wxid: str, nickname: str, filtered_messages: list) -> str:
    """构建评分 prompt"""
    msgs_text = format_messages_for_prompt(filtered_messages)

    return f"""## 任务
分析以下微信群成员的消息，给出总结和评分。

## 成员: {nickname} ({len(filtered_messages)}条消息)

## 消息内容
{msgs_text}

## 注意事项
1. 总结要客观准确，涵盖成员的主要言论特点。
2. stats 统计应基于消息内容进行合理分类。
3. 需要结合消息发送时间理解上下文，避免忽略先后顺序而误判消息语义或成员意图。
4. highlights 仅记录高价值内容，且 type 必须严格使用以下定义：
   - article: 公众号/博客/新闻/技术文章。`content` 必须是文章原始标题；若无法确定原始标题，`content` 置为空字符串。
   - github: GitHub 仓库/代码项目。`content` 根据对话内容总结该仓库描述。
   - insight: 原创观点/经验总结/判断结论。`content` 必须优先填写成员消息中的原文片段，尽量逐字摘录；只有原文过长或存在明显口语噪音时，才允许做最小必要整理，但不得改写原意。
   - opportunity: 招聘/内推/合作招募/项目招募等机会信息。`content` 填机会摘要。
5. `highlights.url` 仅在消息中存在明确链接时填写，否则置为空字符串。
6. 只提取当前成员自己新增的高价值内容；回复、引用、转述里的标题、链接、仓库和机会信息都不算当前成员的 highlights，除非该成员在引用之外提供了明确的新链接或实质性补充。
7. 必须输出 quality_score（0-100），用于评估成员整体内容质量，尽量拉开分布。
8. 需要关注成员在统计周期内的持续性与阶段性表现，避免因为单次高质量发言或短时高频发言而高估整体质量。
9. quality_score 主要衡量内容质量、信息密度和有效性，不应因消息数量多而直接提高，也不应因消息数量少而直接降低。
10. stats 中 resource/technical/qa/discussion/insight/opportunity 应按每条消息的主属性归类，尽量避免一条消息重复计入多个主类别；reply 可作为附加互动标签单独统计。
11. highlights 应少而精，只保留最有代表性的高价值内容；如果没有足够高价值的内容，可返回空数组。highlights 总数不超过 10 条。
12. summary 需要尽量同时覆盖：主要话题、发言特点、整体价值判断，避免只复述消息表面内容。

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

                # 避开部分 provider 对 Pydantic JsonSchema 的兼容性问题，
                # 直接要求模型输出 JSON，再由本地做严格校验。
                response = await litellm.acompletion(
                    model=LITELLM_MODEL,
                    messages=[{"role": "user", "content": prompt}],
                    api_key=AI_API_KEY,
                    base_url=AI_BASE_URL,
                )

                content = extract_json_payload(response.choices[0].message.content)
                result = normalize_analysis_payload(json.loads(content))
                
                stats_dict = result.stats.model_dump()
                quality_score = max(0, min(100, int(result.quality_score)))

                return {
                    "wxid": wxid,
                    "nickname": nickname,
                    "messageCount": effective_count,
                    "qualityScore": round(float(quality_score), 1),
                    "summary": result.summary,
                    "stats": stats_dict,
                    "highlights": sanitize_highlight_output(
                        [h.model_dump() for h in result.highlights]
                    ),
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


def load_errors(errors_file: str) -> dict:
    if os.path.exists(errors_file):
        try:
            with open(errors_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {}
    return {}


def save_errors(errors: dict, errors_file: str):
    if not errors:
        if os.path.exists(errors_file):
            os.remove(errors_file)
        return
    with open(errors_file, "w", encoding="utf-8") as f:
        json.dump(errors, f, ensure_ascii=False, indent=2)


async def main():
    parser = argparse.ArgumentParser(description="消息分析脚本")
    parser.add_argument("-o", "--output", default="output", help="输出目录，默认 output")
    args = parser.parse_args()

    paths = build_output_paths(args.output)

    if not AI_API_KEY:
        print(f"❌ 错误: 未设置 AI API Key (Model: {LITELLM_MODEL})", file=sys.stderr)
        return

    Path(paths["scores_dir"]).mkdir(parents=True, exist_ok=True)

    print(f"🤖 使用模型: {LITELLM_MODEL}")
    print(f"⚙️ 并发配置: MAX_ANALYZE_WORKERS={MAX_WORKERS}")

    loop_round = 0

    while True:
        loop_round += 1
        round_t0 = time.perf_counter()
        # 1. 识别待处理成员
        pending_members = []
        errors_data = load_errors(paths["errors_file"])
        scan_t0 = time.perf_counter()
        
        # 扫描 members 目录
        for filepath in glob.glob(os.path.join(paths["members_dir"], "*.json")):
            with open(filepath, encoding="utf-8") as f:
                data = json.load(f)
            wxid = data.get("wxid")
            nickname = data.get("nickname", wxid)
            messages = data.get("messages", [])
            
            if not wxid:
                continue

            score_path = os.path.join(paths["scores_dir"], f"{wxid}.json")
            
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
            save_errors(errors_data, paths["errors_file"])
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
                score_path = os.path.join(paths["scores_dir"], f"{wxid}.json")
                if os.path.exists(score_path):
                    try:
                        os.remove(score_path)
                    except:
                        pass
            else:
                status_char = "✅"
                # 成功，写入 scores 目录
                output_file = os.path.join(paths["scores_dir"], f"{wxid}.json")
                with open(output_file, "w", encoding="utf-8") as f:
                    json.dump(result, f, ensure_ascii=False, indent=2)
                
                # 从错误记录中移除
                if wxid in errors_data:
                    del errors_data[wxid]
            
            # 即时保存错误记录
            save_errors(errors_data, paths["errors_file"])
            api_cost = result.get("apiDurationSec", 0.0)
            print(f"[{completed}/{total}] {status_char} {nickname} ({msg_count}条, {api_cost:.2f}s)")

        # 2. 统计本轮结果
        success_count = sum(1 for r in batch_results if r["status"] != "error")
        error_count = len(batch_results) - success_count
        batch_cost = time.perf_counter() - batch_t0
        durations = sorted(r.get("apiDurationSec", 0.0) for r in batch_results)
        avg_cost = (sum(durations) / len(durations)) if durations else 0.0
        p95_cost = durations[int(len(durations) * 0.95) - 1] if durations else 0.0

        print(f"📈 本轮完成: 成功 {success_count}, 失败 {error_count}, 总耗时 {batch_cost:.2f}s")
        print(f"⏱️ API耗时统计: avg={avg_cost:.2f}s, p95={p95_cost:.2f}s")
        
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
    for filepath in glob.glob(os.path.join(paths["scores_dir"], "*.json")):
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
    with open(paths["analysis_path"], "w", encoding="utf-8") as f:
        json.dump(analysis_data, f, ensure_ascii=False, indent=2)

    total_msgs = sum(r["messageCount"] for r in results)
    summary_cost = time.perf_counter() - summary_t0
    print(f"\n✨ 分析全部完成！")
    print(f"总成员: {len(results)}, 总消息: {total_msgs}, 总高亮: {len(all_highlights)}")
    print(f"🧾 汇总写盘耗时: {summary_cost:.2f}s")
    print(f"结果已汇总至: {paths['analysis_path']}")


if __name__ == "__main__":
    asyncio.run(main())
