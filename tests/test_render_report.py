import importlib.util
import sys
from pathlib import Path

import pytest


def load_render_report_module():
    script_path = (
        Path(__file__).resolve().parents[1]
        / ".agents"
        / "skills"
        / "render-report"
        / "scripts"
        / "render_report.py"
    )
    spec = importlib.util.spec_from_file_location("render_report", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def sample_markdown():
    return """# 麦田精选（第 3 期）

**期号**：第 3 期
**统计周期**：2026-03-01 ~ 2026-03-28
**总成员数**：89
**活跃成员数**：60
**精彩内容数**：4

# 本期排行
| 排名 | 成员 | 综合分 |
| --- | --- | --- |
| 1 | Alice | 98.5 |
| 2 | Bob | 80.0 |

# 本期看点
## 公众号文章
- 《一篇文章》 @Alice
## 精选分享
- [分享链接](https://example.com/share) @Bob
## GitHub 项目
- [repo](https://github.com/org/repo) @Alice
## 原创心得
- "原文观点" - @Bob
"""


def test_parse_report_extracts_sections():
    module = load_render_report_module()
    data = module.parse_report(sample_markdown())

    assert data["issue"] == "第 3 期"
    assert data["title_main"] == "麦田精选"
    assert data["period"] == "2026-03-01 ~ 2026-03-28"
    assert data["total_members"] == "89"
    assert data["active_members"] == "60"
    assert data["highlights_count"] == "4"
    assert data["rankings"][0]["name"] == "Alice"
    assert data["rankings"][0]["bar_width"]
    assert data["articles"] == [{"title": "《一篇文章》", "author": "Alice"}]
    assert data["shares"] == [{"title": "分享链接", "author": "Bob", "url": "https://example.com/share"}]
    assert data["github_projects"] == [{"title": "repo", "author": "Alice", "url": "https://github.com/org/repo"}]
    assert data["insights"] == [{"title": "原文观点", "author": "Bob"}]


def test_render_html_replaces_sections():
    module = load_render_report_module()
    html = module.render_html(
        "<h1>{{title_main}}</h1>{{#articles}}<p>{{title}}-{{author}}</p>{{/articles}}",
        {"title_main": "麦田精选", "issue": "1", "period": "-", "total_members": "1", "active_members": "1", "highlights_count": "1", "rankings": [], "articles": [{"title": "文章", "author": "Alice"}], "shares": [], "github_projects": [], "insights": []},
    )
    assert "<h1>麦田精选</h1>" in html
    assert "<p>文章-Alice</p>" in html


def test_main_renders_html_output(tmp_path, monkeypatch, capsys):
    module = load_render_report_module()
    template = tmp_path / "template.html"
    markdown = tmp_path / "report_refined.md"
    output = tmp_path / "report_final.html"
    template.write_text(
        "<title>{{title_main}}</title>{{#rankings}}<div>{{name}}:{{score}}</div>{{/rankings}}{{#articles}}<article>{{title}}</article>{{/articles}}",
        encoding="utf-8",
    )
    markdown.write_text(sample_markdown(), encoding="utf-8")

    monkeypatch.setattr(
        sys,
        "argv",
        ["render_report.py", "--template", str(template), "--input", str(markdown), "--output", str(output)],
    )

    module.main()

    html = output.read_text(encoding="utf-8")
    assert "麦田精选" in html
    assert "Alice:98.5" in html
    assert "《一篇文章》" in html
    out = capsys.readouterr().out
    assert str(output) in out


def test_main_raises_when_template_missing(tmp_path, monkeypatch):
    module = load_render_report_module()
    markdown = tmp_path / "report_refined.md"
    markdown.write_text(sample_markdown(), encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        ["render_report.py", "--template", str(tmp_path / "missing.html"), "--input", str(markdown)],
    )
    with pytest.raises(SystemExit, match="missing template"):
        module.main()

