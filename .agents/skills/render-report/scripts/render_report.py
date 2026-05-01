#!/usr/bin/env python3
"""
将 output/report_refined.md 渲染为最终 HTML：
- 模板：template_v1.html（技能 references 目录）
- 输出：output/report_final.html
"""

from __future__ import annotations

import argparse
import math
import re
from pathlib import Path


def count_highlight_items(markdown_text: str) -> int:
    lines = markdown_text.splitlines()
    in_highlights = False
    current = None
    count = 0

    for line in lines:
        if line.startswith("# "):
            in_highlights = line.strip() == "# 本期看点"
            current = None
            continue
        if not in_highlights:
            continue
        if line.startswith("## "):
            current = "news_items" if "新闻热点" in line else "other"
            continue
        if in_highlights and line.startswith("- "):
            if current == "news_items" and not re.match(r"^-\s+\[.*?\]\(https?://.*?\)\s*@", line):
                continue
            count += 1

    return count


def sync_highlights_count(markdown_text: str) -> tuple[str, int]:
    actual_count = count_highlight_items(markdown_text)
    updated_text, replacements = re.subn(
        r"^(\*\*精彩内容数\*\*：)\s*\d+\s*$",
        rf"\g<1>{actual_count}",
        markdown_text,
        count=1,
        flags=re.M,
    )
    if replacements == 0:
        raise ValueError("missing highlights count field")
    return updated_text, actual_count


def compute_rank_bar_width(score: float, max_score: float, min_score: float, min_width: float = 68.0) -> float:
    """Spread close ranking scores with a log-scaled gap from the top score."""
    if max_score <= 0:
        return min_width

    span = max_score - min_score
    if span <= 0:
        return 100.0

    gap_from_top = max_score - score
    transformed = 1 - (math.log1p(gap_from_top) / math.log1p(span))
    return min_width + (transformed * (100 - min_width))


def parse_report(markdown_text: str) -> dict:
    lines = markdown_text.splitlines()

    m_title = re.search(r"^#\s*(.+)$", markdown_text, re.M)
    title_main = (m_title.group(1).strip() if m_title else "麦田精选").split("（")[0].strip()

    m_issue = re.search(r"^\*\*期号\*\*：\s*(.+)$", markdown_text, re.M)
    issue = m_issue.group(1).strip() if m_issue else "第 1 期"

    m_period = re.search(r"^\*\*统计周期\*\*：\s*(.+)$", markdown_text, re.M)
    period = m_period.group(1).strip() if m_period else "-"

    m_total = re.search(r"^\*\*总成员数\*\*：\s*(\d+)", markdown_text, re.M)
    total_members = m_total.group(1) if m_total else "0"

    m_active = re.search(r"^\*\*活跃成员数\*\*：\s*(\d+)", markdown_text, re.M)
    active_members = m_active.group(1) if m_active else "0"

    section_idx = {}
    for i, line in enumerate(lines):
        if line.startswith("# "):
            section_idx[line.strip()] = i

    rankings = []
    rank_key = "# 本期排行"
    if rank_key in section_idx:
        s = section_idx[rank_key]
        e = len(lines)
        for j in range(s + 1, len(lines)):
            if lines[j].startswith("# "):
                e = j
                break
        for ln in lines[s:e]:
            # | 1 | 李小麦 | 99.6 |
            m = re.match(r"^\|\s*(\d+)\s*\|\s*(.*?)\s*\|\s*(\d+(?:\.\d+)?)\s*\|\s*$", ln)
            if not m:
                continue
            rank = int(m.group(1))
            badge = {1: "🥇", 2: "🥈", 3: "🥉"}.get(rank, str(rank))
            rankings.append(
                {
                    "rank_badge": badge,
                    "name": m.group(2).strip(),
                    "score": m.group(3).strip(),
                    "score_num": float(m.group(3)),
                    "rank": rank,
                }
            )

    if rankings:
        max_score = max(r["score_num"] for r in rankings)
        min_score = min(r["score_num"] for r in rankings)
        min_width = 68.0
        fill_palette = {
            1: "#E39A73FF",
            2: "#E39A73BF",
            3: "#E39A738C",
            4: "#E39A7359",
            5: "#E39A7320",
        }
        for r in rankings:
            width = compute_rank_bar_width(
                score=r["score_num"],
                max_score=max_score,
                min_score=min_score,
                min_width=min_width,
            )
            r["bar_width"] = f"{width:.1f}"
            r["bar_color"] = fill_palette.get(r["rank"], "#E39A7320")

    items = {
        "news_items": [],
        "articles": [],
        "shares": [],
        "github_projects": [],
        "insights": [],
    }
    start = section_idx.get("# 本期看点")
    if start is not None:
        current = None
        for ln in lines[start + 1 :]:
            if ln.startswith("# "):
                break
            if ln.startswith("## "):
                h = ln.strip()
                if "新闻热点" in h:
                    current = "news_items"
                elif "公众号" in h:
                    current = "articles"
                elif "精选分享" in h:
                    current = "shares"
                elif "开源项目" in h or "Github 项目" in h or "GitHub 项目" in h:
                    current = "github_projects"
                elif "原创心得" in h:
                    current = "insights"
                else:
                    current = None
                continue
            if not current or not ln.startswith("- "):
                continue

            text = ln[2:].strip()
            m_link = re.match(r"^\[(.*?)\]\((.*?)\)\s*@(.+)$", text)
            m_article = re.match(r"^《(.*?)》\s*@(.+)$", text)
            m_insight = re.match(r'^"(.*)"\s*[—-]\s*@(.+)$', text)
            if m_link:
                title_v, url_v, author = m_link.groups()
                target = current
                if current == "shares" and "github.com" in url_v.lower():
                    target = "github_projects"
                items[target].append(
                    {"title": title_v.strip(), "author": author.strip(), "url": url_v.strip()}
                )
            elif m_article:
                title_v, author = m_article.groups()
                target = "articles" if current == "shares" else current
                if target != "news_items":
                    items[target].append({"title": f"《{title_v.strip()}》", "author": author.strip()})
            elif m_insight:
                title_v, author = m_insight.groups()
                items[current].append({"title": title_v.strip(), "author": author.strip()})
            else:
                m_plain = re.match(r"^(.*?)\s*@(.+)$", text)
                if m_plain:
                    items[current].append(
                        {
                            "title": m_plain.group(1).strip(),
                            "author": m_plain.group(2).strip(),
                        }
                    )

    highlights_count = sum(
        len(items[key])
        for key in ["news_items", "articles", "shares", "github_projects", "insights"]
    )

    return {
        "issue": issue,
        "title_main": title_main,
        "period": period,
        "total_members": total_members,
        "active_members": active_members,
        "highlights_count": str(highlights_count),
        "rankings": rankings[:10],
        "news_items": items["news_items"],
        "articles": items["articles"],
        "shares": items["shares"],
        "github_projects": items["github_projects"],
        "insights": items["insights"],
    }


def render_sections(template: str, key: str, arr: list[dict]) -> str:
    pattern = re.compile(r"\{\{#" + re.escape(key) + r"\}\}(.*?)\{\{/" + re.escape(key) + r"\}\}", re.S)

    def repl(match: re.Match) -> str:
        block = match.group(1)
        rendered = []
        for obj in arr:
            b = block
            for k, v in obj.items():
                b = b.replace("{{" + k + "}}", str(v))
            rendered.append(b)
        return "".join(rendered)

    return pattern.sub(repl, template)


def render_html(template_text: str, data: dict) -> str:
    html = template_text
    for k in ["issue", "title_main", "period", "total_members", "active_members", "highlights_count"]:
        html = html.replace("{{" + k + "}}", str(data[k]))

    html = render_sections(html, "rankings", data["rankings"])
    html = render_sections(html, "news_items", data["news_items"])
    html = render_sections(html, "articles", data["articles"])
    html = render_sections(html, "shares", data["shares"])
    html = render_sections(html, "github_projects", data["github_projects"])
    html = render_sections(html, "insights", data["insights"])
    return html


def main() -> None:
    default_template = Path(__file__).resolve().parent.parent / "references" / "template_v1.html"
    parser = argparse.ArgumentParser(description="将 report_refined.md 渲染为 report_final.html")
    parser.add_argument(
        "--template",
        default=str(default_template),
        help="HTML 模板路径（默认技能内 references/template_v1.html）",
    )
    parser.add_argument(
        "--input",
        default="output/report_refined.md",
        help="输入 Markdown 报告路径（默认 output/report_refined.md）",
    )
    parser.add_argument(
        "--output",
        default="output/report_final.html",
        help="输出 HTML 路径（默认 output/report_final.html）",
    )
    args = parser.parse_args()

    template_path = Path(args.template)
    input_path = Path(args.input)
    output_path = Path(args.output)

    if not template_path.exists():
        raise SystemExit(f"missing template: {template_path}")
    if not input_path.exists():
        raise SystemExit(f"missing input report: {input_path}")

    template_text = template_path.read_text(encoding="utf-8")
    markdown_text = input_path.read_text(encoding="utf-8")
    synced_markdown_text, synced_highlights_count = sync_highlights_count(markdown_text)
    if synced_markdown_text != markdown_text:
        input_path.write_text(synced_markdown_text, encoding="utf-8")
    markdown_text = synced_markdown_text
    data = parse_report(markdown_text)
    html = render_html(template_text, data)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    print(output_path)
    print(
        "counts",
        len(data["rankings"]),
        len(data["news_items"]),
        len(data["articles"]),
        len(data["shares"]),
        len(data["github_projects"]),
        len(data["insights"]),
        synced_highlights_count,
    )


if __name__ == "__main__":
    main()
