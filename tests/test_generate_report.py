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
                    {"timestamp": "2026-02-28T16:00:00Z"},
                    {"timestamp": "2026-03-03T16:30:00Z"},
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
                    "score": 90,
                },
                {
                    "wxid": "wx2",
                    "nickname": "Bob",
                    "messageCount": 0,
                    "score": 20,
                },
            ],
            "highlights": [
                {"type": "news", "content": "产品发布新闻", "url": "https://example.com/news", "author": "Alice"},
                {"type": "news", "content": "无链接新闻", "url": "", "author": "Alice"},
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
    context = module.to_report_context(
        sample_processed(),
        sample_analysis(),
        {"report_number": 3},
    )

    assert context["group_name"] == "Test Group"
    assert context["period_start"] == "2026-03-01"
    assert context["period_end"] == "2026-03-04"
    assert context["report_number"] == 3
    assert context["total_members"] == 2
    assert context["score_flagged_count"] == 1
    assert context["highlights_count"] == 4
    assert context["top_members"][0]["name"] == "Alice"
    assert context["news_items"] == [
        {
            "title": "产品发布新闻",
            "url": "https://example.com/news",
            "author": "Alice",
        }
    ]
    assert context["articles"] == [
        {
            "title": "一篇文章",
            "url": "https://example.com",
            "author": "Alice",
        }
    ]
    assert context["github_items"] == [
        {
            "repo": "repo",
            "url": "https://github.com/org/repo",
            "author": "Alice",
        }
    ]
    assert context["insights"] == [
        {"content": "原话观点", "author": "Alice"}
    ]
    assert context["opportunities"] == [
        {"summary": "招聘机会", "author": "Alice"}
    ]


def test_canonicalize_analysis_highlights_uses_source_text_and_link_title():
    module = load_generate_report_module()
    processed = {
        "members": {
            "wx1": {
                "nickname": "Alice",
                "messages": [
                    {
                        "id": "m1",
                        "content": "这是成员原始观点，不应被摘要替代。",
                    },
                    {
                        "id": "m2",
                        "content": "【原始链接标题】 https://example.com/article",
                    },
                ],
            }
        }
    }
    highlights = [
        {
            "type": "insight",
            "content": "指出一个摘要观点",
            "messageId": "m1",
            "author": "Alice",
        },
        {
            "type": "article",
            "content": "分享一篇文章并给出摘要",
            "messageId": "m2",
            "author": "Alice",
        },
    ]

    canonical = module.canonicalize_analysis_highlights(highlights, processed)

    assert canonical == [
        {
            "type": "insight",
            "content": "这是成员原始观点，不应被摘要替代。",
            "messageId": "m1",
            "author": "Alice",
        },
        {
            "type": "article",
            "content": "原始链接标题",
            "messageId": "m2",
            "url": "https://example.com/article",
            "author": "Alice",
        },
    ]


def test_canonicalize_github_uses_model_project_description():
    module = load_generate_report_module()
    processed = {
        "members": {
            "wx1": {
                "nickname": "Alice",
                "messages": [
                    {
                        "id": "g1",
                        "content": "org/repo https://github.com/org/repo",
                    }
                ],
            }
        }
    }
    highlights = [
        {
            "type": "github",
            "content": "一个用于编排多智能体工作流的开源框架。",
            "messageId": "g1",
            "author": "Alice",
        }
    ]

    canonical = module.canonicalize_analysis_highlights(highlights, processed)

    assert canonical == [
        {
            "type": "github",
            "content": "一个用于编排多智能体工作流的开源框架。",
            "messageId": "g1",
            "url": "https://github.com/org/repo",
            "author": "Alice",
        }
    ]


def test_source_link_inventory_uses_model_type_and_github_description():
    module = load_generate_report_module()
    processed = {
        "members": {
            "wx1": {
                "nickname": "Alice",
                "messages": [
                    {"id": "g1", "content": "https://github.com/org/repo"},
                    {
                        "id": "g2",
                        "content": "【Repo title】 https://github.com/org/repo/releases/tag/v1",
                    },
                    {
                        "id": "n1",
                        "content": "【模型正式发布】 https://example.com/news",
                    },
                    {
                        "id": "a1",
                        "content": "【实战教程正式上线】 https://example.com/tutorial",
                    },
                ],
            }
        }
    }
    canonical = [
        {
            "type": "news",
            "content": "模型正式发布",
            "url": "https://example.com/news",
            "messageId": "n1",
        },
        {
            "type": "github",
            "content": "一个提供发布流程自动化的开源项目。",
            "url": "https://github.com/org/repo",
            "messageId": "g2",
        },
    ]

    links = module.build_source_link_highlights(processed, canonical)

    assert links == [
        {
            "type": "github",
            "content": "一个提供发布流程自动化的开源项目。",
            "url": "https://github.com/org/repo",
            "messageId": "g2",
            "author": "Alice",
        },
        {
            "type": "news",
            "content": "模型正式发布",
            "url": "https://example.com/news",
            "messageId": "n1",
            "author": "Alice",
        },
        {
            "type": "article",
            "content": "实战教程正式上线",
            "url": "https://example.com/tutorial",
            "messageId": "a1",
            "author": "Alice",
        },
    ]


def test_title_keywords_do_not_promote_unselected_link_to_news():
    module = load_generate_report_module()
    processed = {
        "members": {
            "wx1": {
                "nickname": "Alice",
                "messages": [
                    {
                        "id": "n1",
                        "content": "【模型正式发布】 https://example.com/news",
                    }
                ],
            }
        }
    }

    links = module.build_source_link_highlights(processed, [])

    assert links == [
        {
            "type": "article",
            "content": "模型正式发布",
            "url": "https://example.com/news",
            "messageId": "n1",
            "author": "Alice",
        }
    ]


def test_github_description_map_overrides_repo_name_fallback():
    module = load_generate_report_module()
    processed = {
        "members": {
            "wx1": {
                "nickname": "Alice",
                "messages": [
                    {
                        "id": "g1",
                        "content": "https://github.com/org/repo",
                    }
                ],
            }
        }
    }

    links = module.build_source_link_highlights(
        processed,
        [],
        {
            "https://github.com/org/repo": "一个用于自动化发布流程的开源工具。"
        },
    )

    assert links[0]["type"] == "github"
    assert links[0]["content"] == "一个用于自动化发布流程的开源工具。"


def test_scores_context_restores_target_alias_to_member_name():
    module = load_generate_report_module()
    processed = sample_processed()
    analysis = sample_analysis()
    nickname = analysis["data"]["memberScores"][0]["nickname"]
    analysis["data"]["memberScores"][0]["summary"] = "T在群内较活跃，持续分享技术内容。"

    context = module.to_report_context(
        processed,
        analysis,
        {"report_number": 1},
    )

    member = next(
        item for item in context["score_members"] if item["name"] == nickname
    )
    assert member["summary"].startswith(f"{nickname}在群内较活跃")
def test_sanitize_url_trims_wechat_mp_query_params():
    module = load_generate_report_module()

    cleaned = module.sanitize_url(
        "https://mp.weixin.qq.com/s?__biz=MzAwNjI5MTYyMw==&mid=2651508237&idx=1&sn=548cf42dd4d865ddb2839e68ce217077&chksm=8128f442491aea92d8cc2011205a5b650f10a4f30724bc84695fcc733582c588f4a14b0a69ad&mpshare=1&scene=1&srcid=0416PW3f8KUzukVodtNQxUjA&sharer_shareinfo=b80fcc17e7842ad93"
    )

    assert (
        cleaned
        == "https://mp.weixin.qq.com/s?__biz=MzAwNjI5MTYyMw%3D%3D&mid=2651508237&idx=1&sn=548cf42dd4d865ddb2839e68ce217077&chksm=8128f442491aea92d8cc2011205a5b650f10a4f30724bc84695fcc733582c588f4a14b0a69ad"
    )


def test_main_repairs_article_urls_from_imported_messages_without_writing_back(
    tmp_path, monkeypatch
):
    module = load_generate_report_module()
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    processed = sample_processed()
    processed["members"]["wx1"]["messages"].append(
        {
            "timestamp": "2026-03-02T10:00:00Z",
            "content": "[AGI Hunt的文字分享](https://mp.weixin.qq.com/s?scene=1&__biz=MzA4NzgzMjA4MQ==&mid=2453482212&idx=1&sn=48762a1e014431e3c22c38408e6b29f3&sharer_shareinfo_first=dc2fbfdc23aa15a4a1812fc09723f48b&sharer_shareinfo=dc2fbfdc23aa15a4a1812fc09723f48b#wechat_redirect)",
        }
    )
    analysis = sample_analysis()
    analysis["data"]["highlights"] = [
        {
            "type": "article",
            "content": "AGI Hunt的文字分享",
            "url": "https://mp.weixin.qq.com/s?scene=1&__biz=MzA4NzgzMjA4MQ==&mid=2453482212&idx=1&sn=48762a1e014431e3c22c38408e6b29f3&sharer_shareinfo=broken...",
            "author": "Alice",
        }
    ]
    (output_dir / "imported.json").write_text(
        json.dumps(processed, ensure_ascii=False), encoding="utf-8"
    )
    original_analysis_text = json.dumps(analysis, ensure_ascii=False)
    (output_dir / "analyze.json").write_text(
        original_analysis_text,
        encoding="utf-8",
    )

    monkeypatch.setenv("REPORT_NUMBER", "1")
    monkeypatch.setattr(sys, "argv", ["generate_report.py", "-o", str(output_dir)])
    module.main()

    report_text = (output_dir / "report.md").read_text(encoding="utf-8")
    assert (
        "[AGI Hunt的文字分享](https://mp.weixin.qq.com/s?__biz=MzA4NzgzMjA4MQ%3D%3D&mid=2453482212&idx=1&sn=48762a1e014431e3c22c38408e6b29f3) @Alice"
        in report_text
    )
    assert (
        output_dir / "analyze.json"
    ).read_text(encoding="utf-8") == original_analysis_text


def test_select_imported_file_raises_when_missing(tmp_path):
    module = load_generate_report_module()
    with pytest.raises(SystemExit, match="missing imported file"):
        module.select_imported_file(tmp_path)


def test_main_generates_report_and_scores_report(tmp_path, monkeypatch, capsys):
    module = load_generate_report_module()
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    (output_dir / "imported.json").write_text(
        json.dumps(sample_processed(), ensure_ascii=False), encoding="utf-8"
    )
    (output_dir / "analyze.json").write_text(
        json.dumps(sample_analysis(), ensure_ascii=False), encoding="utf-8"
    )

    monkeypatch.setenv("REPORT_NUMBER", "1")
    monkeypatch.setattr(sys, "argv", ["generate_report.py", "-o", str(output_dir)])
    module.main()

    report_path = output_dir / "report.md"
    scores_path = output_dir / "scores.md"
    assert report_path.exists()
    assert scores_path.exists()
    report_text = report_path.read_text(encoding="utf-8")
    scores_text = scores_path.read_text(encoding="utf-8")
    assert "第 1 期" in report_text
    assert report_text.index("## 🔥 新闻热点") < report_text.index("## 🤩 精选分享")
    assert "[产品发布新闻](https://example.com/news) @Alice" in report_text
    assert "无链接新闻" not in report_text
    assert "一篇文章" in report_text
    assert "## 🤩 精选分享" in report_text
    assert "## 💻 开源项目" in report_text
    assert "## 📚 公众号 & 文章" not in report_text
    assert "## 💻 Github 项目" not in report_text
    assert "[一篇文章](https://example.com) @Alice" in report_text
    assert "repo" in report_text
    assert "## 零发言成员（1人）" in scores_text
    assert "- Bob" in scores_text
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


def test_score_groups_use_50_point_low_score_boundary():
    module = load_generate_report_module()
    enriched = [
        {
            "member": {"nickname": "at-50", "messageCount": 1, "score": 50.0},
            "activity_score": 50.0,
        },
        {
            "member": {"nickname": "at-60", "messageCount": 1, "score": 60.0},
            "activity_score": 60.0,
        },
        {
            "member": {"nickname": "over-60", "messageCount": 1, "score": 60.1},
            "activity_score": 60.1,
        },
    ]
    members = module.compute_score_members(enriched)

    groups = module.build_score_groups(members)

    assert [(group["title"], group["count"]) for group in groups] == [
        ("综合分 <=50", 1),
        ("综合分 50~60", 1),
        ("综合分 >60", 1),
    ]


def test_composite_score_uses_adjusted_global_weights():
    module = load_generate_report_module()

    assert module.compute_activity_score_100(1, 5.6, 99) == pytest.approx(
        30.1, abs=0.1
    )
    assert module.compute_activity_score_100(100, 100, 100) == pytest.approx(
        100.0
    )
    assert module.compute_activity_score_100(0, 90, 100) == 0.0
