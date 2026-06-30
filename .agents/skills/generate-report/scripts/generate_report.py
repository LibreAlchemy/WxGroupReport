import json
import os
import sys
import argparse
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlparse
from dotenv import load_dotenv

import jinja2

SHARED_SKILL_DIR = Path(__file__).resolve().parents[2] / "shared"
if str(SHARED_SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(SHARED_SKILL_DIR))

from highlight_url_repair import (
    build_title_url_index_from_processed,
    repair_highlights,
    sanitize_url,
)

load_dotenv()

ACTIVITY_SCORE_COUNT_WEIGHT = 0.3
ACTIVITY_SCORE_QUALITY_WEIGHT = 0.7
ACTIVITY_SCORE_COUNT_MIN_ACTIVE = 60.0
BEIJING_TZ = timezone(timedelta(hours=8))


def compute_p75_message_count(member_scores):
    """计算活跃成员（发言数 > 0）的发言数量 P75（第 75 百分位）。"""
    counts = [m.get("messageCount", 0) for m in member_scores if m.get("messageCount", 0) > 0]
    if not counts:
        return 1.0
    counts.sort()
    n = len(counts)
    pos = 0.75 * (n - 1)
    low = int(pos)
    high = min(low + 1, n - 1)
    frac = pos - low
    return counts[low] + frac * (counts[high] - counts[low])


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def safe_text(value):
    return str(value).replace("\r", " ").replace("\n", " ").strip()


def ensure_table_safe(value):
    return safe_text(value).replace("|", "\\|")


def read_member_score(member):
    return float(member.get("score", 0.0))


def timestamp_to_beijing_date(timestamp):
    text = safe_text(timestamp)
    if not text:
        return ""
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return ""
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(BEIJING_TZ).date().isoformat()


def sanitize_github_url(url):
    cleaned = sanitize_url(url)
    if not cleaned:
        return ""
    parsed = urlparse(cleaned)
    host = (parsed.netloc or "").lower()
    if host in {"github.com", "www.github.com"}:
        return cleaned
    return ""


def is_invalid_article_title(title: str) -> bool:
    text = safe_text(title)
    if not text:
        return True

    lowered = text.lower()
    invalid_titles = {
        "文章",
        "链接",
        "link",
        "article",
    }
    if lowered in invalid_titles:
        return True

    mini_program_keywords = (
        "小程序",
        "mini program",
        "miniprogram",
        "微信小程序",
        "wxapp",
    )
    if any(keyword in lowered for keyword in mini_program_keywords):
        return True

    return False


def compute_activity_score_100(
    msg_count,
    score,
    ref_msg_count,
    weight_count=ACTIVITY_SCORE_COUNT_WEIGHT,
    weight_quality=ACTIVITY_SCORE_QUALITY_WEIGHT,
):
    """综合分 = 加权(发言数量绝对分, 质量分绝对值)
    发言数量绝对分以活跃成员 P75 为基准（P75 = 100 分），封顶 100。
    """
    if ref_msg_count <= 0:
        ref_msg_count = 1.0
    msg_score = min(100.0, msg_count / ref_msg_count * 100.0)
    if msg_count > 0:
        msg_score = max(ACTIVITY_SCORE_COUNT_MIN_ACTIVE, msg_score)
    weight_sum = weight_count + weight_quality
    if weight_sum <= 0:
        return 0.0
    return (weight_count * msg_score + weight_quality * score) / weight_sum


def enrich_member_scores(member_scores, ref_msg_count):
    enriched = []
    for m in member_scores:
        activity_score = compute_activity_score_100(
            m.get("messageCount", 0),
            read_member_score(m),
            ref_msg_count,
            ACTIVITY_SCORE_COUNT_WEIGHT,
            ACTIVITY_SCORE_QUALITY_WEIGHT,
        )
        enriched.append(
            {
                "member": m,
                "activity_score": activity_score,
            }
        )
    return enriched


def compute_score_members(enriched_member_scores):
    severity_label = {
        "high": "高",
        "medium": "中",
        "low": "低",
    }

    score_members = []
    for item in enriched_member_scores:
        m = item["member"]
        msg_count = m.get("messageCount", 0)
        score = read_member_score(m)
        activity_score = item["activity_score"]

        status = None
        severity = None
        reason = ""
        if msg_count == 0:
            status = "zero_activity"
            severity = "high"
            reason = "无消息"
        elif 40 < activity_score <= 60:
            status = "score_middle"
            severity = "medium"
            reason = f"综合分{activity_score:.1f}"
        elif activity_score <= 40:
            status = "low_frequency"
            severity = "low"
            reason = f"综合分{activity_score:.1f}"
        elif activity_score > 60:
            status = "qualified"
            severity = "normal"
            reason = f"综合分{activity_score:.1f}"

        if status:
            score_members.append(
                {
                    "name": safe_text(m.get("nickname") or m.get("wxid") or ""),
                    "summary": safe_text(m.get("summary") or ""),
                    "msg_count": msg_count,
                    "score": score,
                    "activity_score": round(activity_score, 1),
                    "status": status,
                    "reason": reason,
                    "severity": severity,
                    "severity_label": severity_label.get(severity, ""),
                }
            )

    severity_order = {"high": 0, "medium": 1, "low": 2}
    score_members.sort(key=lambda x: severity_order.get(x["severity"], 3))
    return score_members


def build_score_groups(score_members):
    group_meta = [
        {"status": "zero_activity", "title": "零发言成员", "severity_label": "高"},
        {"status": "low_frequency", "title": "综合分 <=40", "severity_label": "低"},
        {"status": "score_middle", "title": "综合分 40~60", "severity_label": "中"},
        {"status": "qualified", "title": "综合分 >60", "severity_label": "正常"},
    ]
    groups = []
    for meta in group_meta:
        members = [m for m in score_members if m.get("status") == meta["status"]]
        if not members:
            continue
        members = sorted(
            members,
            key=lambda m: (
                m.get("activity_score", 0.0),
                m.get("msg_count", 0),
                m.get("name", ""),
            ),
        )
        groups.append(
            {
                "status": meta["status"],
                "title": meta["title"],
                "severity_label": meta["severity_label"],
                "count": len(members),
                "members": members,
            }
        )
    return groups


def to_report_context(processed, analysis, config):
    data = analysis.get("data", {})
    member_scores = data.get("memberScores", [])
    highlights = data.get("highlights", [])

    members_total = len(member_scores)
    active_members = len([m for m in member_scores if m.get("messageCount", 0) > 0])
    p75_msg_count = compute_p75_message_count(member_scores)
    enriched_member_scores = enrich_member_scores(
        member_scores,
        p75_msg_count,
    )

    enriched_members = []
    for item in enriched_member_scores:
        m = item["member"]
        msg_count = m.get("messageCount", 0)
        score = read_member_score(m)
        enriched_members.append(
            {
                "name": ensure_table_safe(m.get("nickname") or m.get("wxid") or ""),
                "sort_name": safe_text(m.get("nickname") or m.get("wxid") or "").lower(),
                "msg_count": msg_count,
                "score": score,
                "activity_score": item["activity_score"],
            }
        )

    sorted_members = sorted(
        enriched_members,
        key=lambda m: (
            -m["activity_score"],
            -m["msg_count"],
            -m["score"],
            m["sort_name"],
        ),
    )
    top_members = [
        {
            "name": m["name"],
            "msg_count": m["msg_count"],
            "score": m["score"],
            "activity_score": m["activity_score"],
        }
        for m in sorted_members[:10]
    ]

    news_items = []
    articles = []
    github_items = []
    insights = []
    opportunities = []

    for item in highlights:
        item_type = item.get("type")
        if item_type not in {"news", "article", "github", "insight", "opportunity"}:
            continue
        author = ensure_table_safe(item.get("author") or "")
        if item_type == "news":
            url = sanitize_url(item.get("url") or "")
            if not url:
                continue
            title = safe_text(item.get("content") or "")
            if is_invalid_article_title(title):
                continue
            news_items.append({"title": title, "url": url, "author": author})
        elif item_type == "article":
            url = sanitize_url(item.get("url") or "")
            title = safe_text(item.get("content") or "")
            if is_invalid_article_title(title):
                continue
            articles.append({"title": title, "url": url, "author": author})
        elif item_type == "github":
            url = sanitize_github_url(item.get("url") or "")
            if not url:
                continue
            repo = safe_text(item.get("content") or url or "GitHub")
            github_items.append({"repo": repo, "url": url, "author": author})
        elif item_type == "insight":
            content = safe_text(item.get("content") or "")
            if not content:
                continue
            insights.append({"content": content, "author": author})
        elif item_type == "opportunity":
            opportunities.append(
                {"summary": safe_text(item.get("content") or ""), "author": author}
            )

    score_members = compute_score_members(enriched_member_scores)
    score_groups = build_score_groups(score_members)
    score_flagged_count = len(
        [m for m in score_members if m.get("status") != "qualified"]
    )

    period_dates = []
    members = processed.get("members", {})
    for m_data in members.values():
        for msg in m_data.get("messages", []):
            ts = msg.get("timestamp")
            if ts:
                period_dates.append(timestamp_to_beijing_date(ts))
    period_dates = sorted(date for date in period_dates if date)
    period_start = period_dates[0] if period_dates else "-"
    period_end = period_dates[-1] if period_dates else "-"

    group_name = (
        processed.get("group_info", {}).get("name")
        or processed.get("meta", {}).get("name")
        or ""
    )

    displayed_highlights_count = (
        len(news_items) + len(articles) + len(github_items) + len(insights)
    )

    return {
        "group_name": safe_text(group_name),
        "period_start": safe_text(period_start),
        "period_end": safe_text(period_end),
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "report_number": config.get("report_number", 1),
        "activity_score_count_weight": ACTIVITY_SCORE_COUNT_WEIGHT,
        "activity_score_quality_weight": ACTIVITY_SCORE_QUALITY_WEIGHT,
        "activity_score_count_min_active": ACTIVITY_SCORE_COUNT_MIN_ACTIVE,
        "p75_msg_count": round(p75_msg_count, 1),
        "total_members": members_total,
        "active_members": active_members,
        "score_flagged_count": score_flagged_count,
        "highlights_count": displayed_highlights_count,
        "news_items": news_items,
        "top_members": top_members,
        "articles": articles,
        "github_items": github_items,
        "insights": insights,
        "opportunities": opportunities,
        "score_members": score_members,
        "score_groups": score_groups,
    }


def render_report(template_path: Path, context):
    with template_path.open("r", encoding="utf-8") as handle:
        template_text = handle.read()
    env = jinja2.Environment(autoescape=False)
    template = env.from_string(template_text)
    return template.render(**context)


def render_scores_report(template_path: Path, context):
    with template_path.open("r", encoding="utf-8") as handle:
        template_text = handle.read()
    env = jinja2.Environment(autoescape=False)
    template = env.from_string(template_text)
    return template.render(**context)


def normalize_heading_spacing(text):
    lines = text.splitlines()
    normalized = []
    for i, line in enumerate(lines):
        is_heading = line.startswith("#")
        if is_heading and normalized:
            if normalized[-1] != "":
                normalized.append("")
            elif len(normalized) >= 2 and normalized[-2] != "":
                normalized.append("")
        normalized.append(line.rstrip())
    out = "\n".join(normalized).rstrip() + "\n"
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out


def select_imported_file(output_dir: Path) -> Path:
    imported_path = output_dir / "imported.json"
    if not imported_path.exists():
        raise SystemExit(f"missing imported file: {imported_path}")
    return imported_path


def main():
    parser = argparse.ArgumentParser(description="生成报告脚本")
    parser.add_argument("-o", "--output", default="output", help="输出目录，默认 output")
    args = parser.parse_args()

    output_dir_env = args.output

    assert output_dir_env is not None

    skill_dir = Path(__file__).resolve().parent.parent
    output_dir = Path(output_dir_env)
    processed_path = select_imported_file(output_dir)
    analysis_path = output_dir / "analyze.json"
    template_path = skill_dir / "references" / "report_template.md"
    output_path = output_dir / "report.md"
    scores_template_path = skill_dir / "references" / "scores_template.md"
    scores_output_path = output_dir / "scores.md"

    config = {
        "report_number": int(os.getenv("REPORT_NUMBER", "1")),
    }

    if not analysis_path.exists():
        raise SystemExit(f"missing analysis file: {analysis_path}")
    if not template_path.exists():
        raise SystemExit(f"missing template: {template_path}")
    if not scores_template_path.exists():
        raise SystemExit(f"missing scores template: {scores_template_path}")

    processed = load_json(processed_path)
    analysis = load_json(analysis_path)
    analysis_data = analysis.get("data") or {}
    analysis_data["highlights"] = repair_highlights(
        analysis_data.get("highlights") or [],
        build_title_url_index_from_processed(processed),
    )
    analysis["data"] = analysis_data

    context = to_report_context(processed, analysis, config)
    context["scores_report_file"] = scores_output_path.name

    rendered = render_report(template_path, context)
    scores_rendered = render_scores_report(scores_template_path, context)
    rendered = normalize_heading_spacing(rendered)
    scores_rendered = normalize_heading_spacing(scores_rendered)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        handle.write(rendered)
    scores_output_path.parent.mkdir(parents=True, exist_ok=True)
    with scores_output_path.open("w", encoding="utf-8") as handle:
        handle.write(scores_rendered)

    print("report generated")
    print("output:", output_path)
    print("scores output:", scores_output_path)


if __name__ == "__main__":
    main()
