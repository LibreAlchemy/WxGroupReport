import json
import os
from datetime import datetime
from pathlib import Path

import jinja2


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def safe_text(value):
    return str(value).replace("\r", " ").replace("\n", " ").strip()


def ensure_table_safe(value):
    return safe_text(value).replace("|", "\\|")


def to_report_context(processed, analysis, config):
    data = analysis.get("data", {})
    member_scores = data.get("memberScores", [])
    highlights = data.get("highlights", [])
    low_quality_members = data.get("lowQualityMembers", [])

    members_total = len(member_scores)
    active_members = len([m for m in member_scores if m.get("messageCount", 0) > 0])

    sorted_members = sorted(
        member_scores, key=lambda m: m.get("messageCount", 0), reverse=True
    )
    top_members = [
        {
            "name": ensure_table_safe(m.get("nickname") or m.get("wxid") or ""),
            "msg_count": m.get("messageCount", 0),
            "avg_score": m.get("averageScore", 0.0),
        }
        for m in sorted_members[:10]
    ]

    articles = []
    github_items = []
    insights = []
    opportunities = []

    for item in highlights:
        item_type = item.get("type")
        author = ensure_table_safe(item.get("author") or "")
        if item_type == "article":
            url = item.get("url") or ""
            title = safe_text(item.get("content") or url or "文章")
            articles.append({"title": title, "url": url, "author": author})
        elif item_type == "github":
            url = item.get("url") or ""
            repo = safe_text(item.get("content") or url or "GitHub")
            github_items.append({"repo": repo, "url": url, "author": author})
        elif item_type == "insight":
            insights.append(
                {"content": safe_text(item.get("content") or ""), "author": author}
            )
        elif item_type == "opportunity":
            opportunities.append(
                {"summary": safe_text(item.get("content") or ""), "author": author}
            )

    severity_label = {
        "high": "高",
        "medium": "中",
        "low": "低",
    }

    low_quality = [
        {
            "name": safe_text(m.get("nickname") or m.get("wxid") or ""),
            "msg_count": m.get("messageCount", 0),
            "avg_score": m.get("averageScore", 0.0),
            "reason": safe_text(m.get("reason") or ""),
            "severity_label": severity_label.get(
                m.get("severity"), safe_text(m.get("severity") or "")
            ),
        }
        for m in low_quality_members
    ]

    period_start = "-"
    period_end = "-"
    if config.get("period"):
        period_start = config.get("period", {}).get("start") or "-"
        period_end = config.get("period", {}).get("end") or "-"

    group_name = (
        processed.get("group_info", {}).get("name")
        or processed.get("meta", {}).get("name")
        or ""
    )

    return {
        "group_name": safe_text(group_name),
        "period_start": safe_text(period_start),
        "period_end": safe_text(period_end),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "report_number": config.get("report_number", 1),
        "total_members": members_total,
        "active_members": active_members,
        "low_quality_count": len(low_quality_members),
        "highlights_count": len(highlights),
        "top_members": top_members,
        "articles": articles,
        "github_items": github_items,
        "insights": insights,
        "opportunities": opportunities,
        "low_quality_members": low_quality,
    }


def render_report(template_path: Path, context):
    with template_path.open("r", encoding="utf-8") as handle:
        template_text = handle.read()
    env = jinja2.Environment(autoescape=False)
    template = env.from_string(template_text)
    return template.render(**context)


def main():
    processed_path = Path(os.getenv("PROCESSED_PATH", "output/麦田怪圈_processed.json"))
    analysis_path = Path(os.getenv("ANALYSIS_PATH", "output/analyze-messages.json"))
    template_path = Path(
        os.getenv("TEMPLATE_PATH", ".opencode/skills/generate-report/template.md")
    )
    output_path = Path(os.getenv("OUTPUT_PATH", "output/report.md"))

    config = {
        "period": {
            "start": os.getenv("PERIOD_START") or None,
            "end": os.getenv("PERIOD_END") or None,
        },
        "report_number": int(os.getenv("REPORT_NUMBER", "1")),
    }
    if not config["period"]["start"] and not config["period"]["end"]:
        config["period"] = None

    if not processed_path.exists():
        raise SystemExit(f"missing processed file: {processed_path}")
    if not analysis_path.exists():
        raise SystemExit(f"missing analysis file: {analysis_path}")
    if not template_path.exists():
        raise SystemExit(f"missing template: {template_path}")

    processed = load_json(processed_path)
    analysis = load_json(analysis_path)

    context = to_report_context(processed, analysis, config)
    rendered = render_report(template_path, context)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        handle.write(rendered)

    print("report generated")
    print("output:", output_path)


if __name__ == "__main__":
    main()
