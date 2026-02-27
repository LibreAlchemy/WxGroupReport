import json
import os
import sys
import argparse
import re
from datetime import datetime
from pathlib import Path
from bisect import bisect_right
from urllib.parse import urlparse

import jinja2


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def safe_text(value):
    return str(value).replace("\r", " ").replace("\n", " ").strip()


def ensure_table_safe(value):
    return safe_text(value).replace("|", "\\|")


def read_member_quality_score(member):
    return float(member.get("qualityScore", 0.0))


def sanitize_url(url):
    text = safe_text(url)
    normalized = text.strip("[]()").strip()
    if not normalized:
        return ""
    if normalized == "链接":
        return ""
    lowered = normalized.lower()
    if not (lowered.startswith("http://") or lowered.startswith("https://")):
        return ""
    return text


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


def normalize_min_max(value, min_value, max_value):
    if max_value <= min_value:
        return 0.5
    return (value - min_value) / (max_value - min_value)


def normalize_percentile(value, sorted_values):
    total = len(sorted_values)
    if total <= 1:
        return 0.5
    if sorted_values[0] == sorted_values[-1]:
        return 0.5
    index = bisect_right(sorted_values, value) - 1
    index = max(index, 0)
    return index / (total - 1)


def compute_activity_score_100(
    msg_count,
    avg_score,
    sorted_msg_counts,
    min_avg_score,
    max_avg_score,
    weight_count=0.6,
    weight_quality=0.4,
):
    norm_msg_count = normalize_percentile(msg_count, sorted_msg_counts)
    norm_avg_score = normalize_min_max(avg_score, min_avg_score, max_avg_score)
    weight_sum = weight_count + weight_quality
    if weight_sum <= 0:
        return 0.0
    return 100 * ((weight_count * norm_msg_count + weight_quality * norm_avg_score) / weight_sum)


def compute_low_quality_members(member_scores):
    severity_label = {
        "high": "高",
        "medium": "中",
        "low": "低",
    }
    weight_count = 0.6
    weight_quality = 0.4
    msg_counts = [m.get("messageCount", 0) for m in member_scores]
    sorted_msg_counts = sorted(msg_counts)
    avg_scores = [read_member_quality_score(m) for m in member_scores]
    min_avg_score = min(avg_scores, default=0.0)
    max_avg_score = max(avg_scores, default=0.0)

    low_quality = []
    for m in member_scores:
        msg_count = m.get("messageCount", 0)
        avg_score = read_member_quality_score(m)
        activity_score = compute_activity_score_100(
            msg_count,
            avg_score,
            sorted_msg_counts,
            min_avg_score,
            max_avg_score,
            weight_count,
            weight_quality,
        )

        status = None
        severity = None
        reason = ""
        if msg_count == 0:
            status = "zero_activity"
            severity = "high"
            reason = "无消息"
        elif 40 < activity_score < 60:
            status = "low_quality"
            severity = "medium"
            reason = f"综合分{activity_score:.1f}"
        elif activity_score <= 40:
            status = "low_frequency"
            severity = "low"
            reason = f"综合分{activity_score:.1f}"

        if status:
            low_quality.append(
                {
                    "name": safe_text(m.get("nickname") or m.get("wxid") or ""),
                    "msg_count": msg_count,
                    "avg_score": avg_score,
                    "activity_score": round(activity_score, 1),
                    "status": status,
                    "reason": reason,
                    "severity": severity,
                    "severity_label": severity_label.get(severity, ""),
                }
            )

    severity_order = {"high": 0, "medium": 1, "low": 2}
    low_quality.sort(key=lambda x: severity_order.get(x["severity"], 3))
    return low_quality


def build_low_quality_groups(low_quality_members):
    group_meta = [
        {"status": "zero_activity", "title": "零发言成员", "severity_label": "高"},
        {"status": "low_frequency", "title": "综合分 <=40", "severity_label": "低"},
        {"status": "low_quality", "title": "综合分 40~60", "severity_label": "中"},
    ]
    groups = []
    for meta in group_meta:
        members = [m for m in low_quality_members if m.get("status") == meta["status"]]
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

    weight_count = 0.6
    weight_quality = 0.4
    msg_counts = [m.get("messageCount", 0) for m in member_scores]
    sorted_msg_counts = sorted(msg_counts)
    avg_scores = [read_member_quality_score(m) for m in member_scores]
    min_avg_score = min(avg_scores, default=0.0)
    max_avg_score = max(avg_scores, default=0.0)

    enriched_members = []
    for m in member_scores:
        msg_count = m.get("messageCount", 0)
        avg_score = read_member_quality_score(m)
        activity_score = compute_activity_score_100(
            msg_count,
            avg_score,
            sorted_msg_counts,
            min_avg_score,
            max_avg_score,
            weight_count,
            weight_quality,
        )
        enriched_members.append(
            {
                "name": ensure_table_safe(m.get("nickname") or m.get("wxid") or ""),
                "sort_name": safe_text(m.get("nickname") or m.get("wxid") or "").lower(),
                "msg_count": msg_count,
                "avg_score": avg_score,
                "activity_score": activity_score,
            }
        )

    sorted_members = sorted(
        enriched_members,
        key=lambda m: (
            -m["activity_score"],
            -m["msg_count"],
            -m["avg_score"],
            m["sort_name"],
        ),
    )
    top_members = [
        {
            "name": m["name"],
            "msg_count": m["msg_count"],
            "avg_score": m["avg_score"],
            "activity_score": m["activity_score"],
        }
        for m in sorted_members[:10]
    ]

    articles = []
    github_items = []
    insights = []
    opportunities = []

    for item in highlights:
        item_type = item.get("type")
        if item_type not in {"article", "github", "insight", "opportunity"}:
            continue
        author = ensure_table_safe(item.get("author") or "")
        if item_type == "article":
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

    low_quality = compute_low_quality_members(member_scores)
    low_quality_groups = build_low_quality_groups(low_quality)

    period_start = "-"
    period_end = "-"
    if config.get("period"):
        period_start = config.get("period", {}).get("start") or "-"
        period_end = config.get("period", {}).get("end") or "-"

    # If period is not provided, try to extract from processed data
    if period_start == "-" or period_end == "-":
        all_timestamps = []
        members = processed.get("members", {})
        for m_data in members.values():
            for msg in m_data.get("messages", []):
                ts = msg.get("timestamp")
                if ts:
                    all_timestamps.append(ts)

        if all_timestamps:
            all_timestamps.sort()
            if period_start == "-":
                period_start = all_timestamps[0].split("T")[0]
            if period_end == "-":
                period_end = all_timestamps[-1].split("T")[0]

    group_name = (
        processed.get("group_info", {}).get("name")
        or processed.get("meta", {}).get("name")
        or ""
    )

    return {
        "group_name": safe_text(group_name),
        "period_start": safe_text(period_start),
        "period_end": safe_text(period_end),
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "report_number": config.get("report_number", 1),
        "total_members": members_total,
        "active_members": active_members,
        "low_quality_count": len(low_quality),
        "highlights_count": len(highlights),
        "top_members": top_members,
        "articles": articles,
        "github_items": github_items,
        "insights": insights,
        "opportunities": opportunities,
        "low_quality_members": low_quality,
        "low_quality_groups": low_quality_groups,
    }


def render_report(template_path: Path, context):
    with template_path.open("r", encoding="utf-8") as handle:
        template_text = handle.read()
    env = jinja2.Environment(autoescape=False)
    template = env.from_string(template_text)
    return template.render(**context)


def render_low_quality_report(template_path: Path, context):
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
    parser.add_argument("-o", "--output", help="输出目录 (OUTPUT_DIR)")
    parser.add_argument(
        "--low-quality-template", help="低质成员模板路径 (LOW_QUALITY_TEMPLATE_PATH)"
    )
    parser.add_argument(
        "--low-quality-output", help="低质成员报告输出路径 (LOW_QUALITY_OUTPUT_PATH)"
    )
    args = parser.parse_args()

    output_dir_env = args.output or os.getenv("OUTPUT_DIR", "output")
    default_low_quality_template = (
        Path(__file__).resolve().parent.parent / "references" / "low_quality_template.md"
    )
    low_quality_template_env = args.low_quality_template or os.getenv(
        "LOW_QUALITY_TEMPLATE_PATH", str(default_low_quality_template)
    )
    low_quality_output_env = args.low_quality_output or os.getenv(
        "LOW_QUALITY_OUTPUT_PATH"
    )

    assert output_dir_env is not None
    assert low_quality_template_env is not None

    skill_dir = Path(__file__).resolve().parent.parent
    output_dir = Path(output_dir_env)
    processed_path = select_imported_file(output_dir)
    analysis_path = output_dir / "analyze.json"
    template_path = skill_dir / "references" / "template.md"
    output_path = output_dir / "report.md"
    low_quality_template_path = Path(low_quality_template_env)
    low_quality_output_path = (
        Path(low_quality_output_env)
        if low_quality_output_env
        else output_dir / "low_quality_members.md"
    )

    config = {
        "period": {
            "start": os.getenv("PERIOD_START") or None,
            "end": os.getenv("PERIOD_END") or None,
        },
        "report_number": int(os.getenv("REPORT_NUMBER", "1")),
    }
    if not config["period"]["start"] and not config["period"]["end"]:
        config["period"] = None

    if not analysis_path.exists():
        raise SystemExit(f"missing analysis file: {analysis_path}")
    if not template_path.exists():
        raise SystemExit(f"missing template: {template_path}")
    if not low_quality_template_path.exists():
        raise SystemExit(f"missing low quality template: {low_quality_template_path}")

    processed = load_json(processed_path)
    analysis = load_json(analysis_path)

    context = to_report_context(processed, analysis, config)
    context["low_quality_report_file"] = low_quality_output_path.name

    rendered = render_report(template_path, context)
    low_quality_rendered = render_low_quality_report(low_quality_template_path, context)
    rendered = normalize_heading_spacing(rendered)
    low_quality_rendered = normalize_heading_spacing(low_quality_rendered)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        handle.write(rendered)
    low_quality_output_path.parent.mkdir(parents=True, exist_ok=True)
    with low_quality_output_path.open("w", encoding="utf-8") as handle:
        handle.write(low_quality_rendered)

    print("report generated")
    print("output:", output_path)
    print("low quality output:", low_quality_output_path)


if __name__ == "__main__":
    main()
