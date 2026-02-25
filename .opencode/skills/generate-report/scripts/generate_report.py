import json
import os
import importlib
import subprocess
import sys
from datetime import datetime
from pathlib import Path


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

    best_by_type = {}
    for item in highlights:
        item_type = item.get("type")
        if item_type in best_by_type:
            continue
        if item_type not in {"article", "github", "insight", "opportunity"}:
            continue
        best_by_type[item_type] = item

    articles = []
    github_items = []
    insights = []
    opportunities = []

    for item_type, item in best_by_type.items():
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


def ensure_jinja2(requirements_path: Path):
    try:
        return importlib.import_module("jinja2")
    except ImportError:
        if not requirements_path.exists():
            raise SystemExit(f"missing requirements file: {requirements_path}")
        command = [sys.executable, "-m", "pip", "install", "-r", str(requirements_path)]
        try:
            subprocess.check_call(command)
        except Exception as exc:
            raise SystemExit(
                "failed to install dependencies for generate-report"
            ) from exc
        try:
            return importlib.import_module("jinja2")
        except ImportError as exc:
            raise SystemExit("jinja2 is still missing after install") from exc


def render_report(template_path: Path, context, jinja2_module):
    with template_path.open("r", encoding="utf-8") as handle:
        template_text = handle.read()
    env = jinja2_module.Environment(autoescape=False)
    template = env.from_string(template_text)
    return template.render(**context)


def select_latest_processed(output_dir: Path) -> Path:
    candidates = list(output_dir.glob("*_processed.json"))
    if not candidates:
        raise SystemExit(f"missing processed file in {output_dir}")
    return max(candidates, key=lambda path: path.stat().st_mtime)


def main():
    output_dir_env = os.getenv("OUTPUT_DIR", "output")
    template_path_env = os.getenv(
        "TEMPLATE_PATH", ".opencode/skills/generate-report/template.md"
    )
    output_path_env = os.getenv("OUTPUT_PATH")
    requirements_path_env = os.getenv(
        "REQUIREMENTS_PATH", ".opencode/skills/generate-report/requirements.txt"
    )

    assert output_dir_env is not None
    assert template_path_env is not None
    assert requirements_path_env is not None

    output_dir = Path(output_dir_env)
    processed_path = select_latest_processed(output_dir)
    analysis_path = output_dir / "analyze-messages.json"
    template_path = Path(template_path_env)
    output_path = Path(output_path_env) if output_path_env else output_dir / "report.md"
    requirements_path = Path(requirements_path_env)

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

    processed = load_json(processed_path)
    analysis = load_json(analysis_path)

    context = to_report_context(processed, analysis, config)
    jinja2_module = ensure_jinja2(requirements_path)
    rendered = render_report(template_path, context, jinja2_module)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        handle.write(rendered)

    print("report generated")
    print("output:", output_path)


if __name__ == "__main__":
    main()
