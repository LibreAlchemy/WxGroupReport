import importlib.util
import json
import sys
from pathlib import Path

import pytest


def load_generate_report_module():
    script_path = (
        Path(__file__).resolve().parents[1]
        / ".agents"
        / "skills"
        / "generate-report"
        / "scripts"
        / "generate_report.py"
    )
    spec = importlib.util.spec_from_file_location("generate_report", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def sample_processed():
    return {
        "group_info": {"name": "Test Group"},
        "members": {
            "wx1": {
                "messages": [
                    {"timestamp": "2026-03-01T08:00:00Z"},
                    {"timestamp": "2026-03-03T09:00:00Z"},
                ]
            }
        },
    }


def sample_analysis():
    return {
        "data": {
            "memberScores": [
                {
                    "wxid": "wx1",
                    "nickname": "Alice",
                    "messageCount": 10,
                    "qualityScore": 90,
                },
                {
                    "wxid": "wx2",
                    "nickname": "Bob",
                    "messageCount": 0,
                    "qualityScore": 20,
                },
            ],
            "highlights": [
                {"type": "article", "content": "一篇文章", "url": "https://example.com", "author": "Alice"},
                {"type": "article", "content": "微信小程序开发", "url": "", "author": "Alice"},
                {"type": "github", "content": "repo", "url": "https://github.com/org/repo", "author": "Alice"},
                {"type": "github", "content": "bad", "url": "https://example.com/repo", "author": "Alice"},
                {"type": "insight", "content": "原话观点", "author": "Alice"},
                {"type": "opportunity", "content": "招聘机会", "author": "Alice"},
            ],
        }
    }


def test_to_report_context_filters_and_computes_sections():
    module = load_generate_report_module()
    context = module.to_report_context(sample_processed(), sample_analysis(), {"period": None, "report_number": 3})

    assert context["group_name"] == "Test Group"
    assert context["period_start"] == "2026-03-01"
    assert context["period_end"] == "2026-03-03"
    assert context["report_number"] == 3
    assert context["total_members"] == 2
    assert context["active_members"] == 1
    assert context["low_quality_count"] == 1
    assert context["highlights_count"] == 3
    assert context["top_members"][0]["name"] == "Alice"
    assert context["articles"] == [{"title": "一篇文章", "url": "https://example.com", "author": "Alice"}]
    assert context["github_items"] == [{"repo": "repo", "url": "https://github.com/org/repo", "author": "Alice"}]
    assert context["insights"] == [{"content": "原话观点", "author": "Alice"}]
    assert context["opportunities"] == [{"summary": "招聘机会", "author": "Alice"}]


def test_select_imported_file_raises_when_missing(tmp_path):
    module = load_generate_report_module()
    with pytest.raises(SystemExit, match="missing imported file"):
        module.select_imported_file(tmp_path)


def test_main_generates_report_and_low_quality_report(tmp_path, monkeypatch, capsys):
    module = load_generate_report_module()
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    (output_dir / "imported.json").write_text(
        json.dumps(sample_processed(), ensure_ascii=False), encoding="utf-8"
    )
    (output_dir / "analyze.json").write_text(
        json.dumps(sample_analysis(), ensure_ascii=False), encoding="utf-8"
    )

    monkeypatch.delenv("PERIOD_START", raising=False)
    monkeypatch.delenv("PERIOD_END", raising=False)
    monkeypatch.setenv("REPORT_NUMBER", "1")
    monkeypatch.setattr(sys, "argv", ["generate_report.py", "-o", str(output_dir)])
    module.main()

    report_path = output_dir / "report.md"
    low_quality_path = output_dir / "low_quality_members.md"
    assert report_path.exists()
    assert low_quality_path.exists()
    report_text = report_path.read_text(encoding="utf-8")
    low_quality_text = low_quality_path.read_text(encoding="utf-8")
    assert "第 1 期" in report_text
    assert "一篇文章" in report_text
    assert "repo" in report_text
    assert "## 零发言成员（1人）" in low_quality_text
    assert "- Bob" in low_quality_text
    out = capsys.readouterr().out
    assert "report generated" in out


def test_main_raises_when_analysis_missing(tmp_path, monkeypatch):
    module = load_generate_report_module()
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    (output_dir / "imported.json").write_text(
        json.dumps(sample_processed(), ensure_ascii=False), encoding="utf-8"
    )
    monkeypatch.setattr(sys, "argv", ["generate_report.py", "-o", str(output_dir)])

    with pytest.raises(SystemExit, match="missing analysis file"):
        module.main()
