import importlib.util
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError


ROOT = Path(__file__).resolve().parents[1]
ANALYZE_SCRIPTS = ROOT / ".agents" / "skills" / "analyze-messages" / "scripts"
SHARED_SCRIPTS = ROOT / ".agents" / "skills" / "shared"
for path in (ANALYZE_SCRIPTS, SHARED_SCRIPTS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


def load_module(name: str, filename: str):
    if filename.startswith("../shared/"):
        path = SHARED_SCRIPTS / Path(filename).name
    else:
        path = ANALYZE_SCRIPTS / filename
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def dialogue_message(message_id, timestamp, sender, nickname, content):
    return {
        "id": message_id,
        "timestamp": timestamp,
        "sender": sender,
        "nickname": nickname,
        "msg_type": 0,
        "content": content,
        "quote": None,
    }


def test_nested_inline_quote_is_split_without_losing_surrounding_text():
    context = load_module("test_message_context", "../shared/message_context.py")

    body, quote = context.parse_inline_quote("前文[引用 Alice：[链接] 内容]后文")

    assert body == "前文后文"
    assert quote == {"author": "Alice", "content": "[链接] 内容"}


def test_local_context_keeps_two_neighbors_each_side_and_merges_windows():
    context = load_module("test_analysis_context", "analysis_context.py")
    base = datetime(2026, 3, 1, 10, 0, tzinfo=timezone.utc)
    dialogue = [
        dialogue_message(
            f"m{i}",
            (base + timedelta(seconds=i * 30)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "other",
            "Other",
            f"ctx{i}",
        )
        for i in range(7)
    ]
    dialogue[3]["sender"] = "wx1"
    dialogue[3]["nickname"] = "Alice"
    dialogue[3]["content"] = "target"

    messages = [{"id": "m3", "content": "target", "timestamp": dialogue[3]["timestamp"]}]
    context_messages, target_ids, alias_to_id = context.build_context_messages(
        "wx1", "Alice", messages, dialogue
    )

    assert target_ids == {"m3"}
    assert [item["id"] for item in context_messages] == [
        "m1",
        "m2",
        "m3",
        "m4",
        "m5",
    ]
    assert [item["role"] for item in context_messages] == [
        "CTX",
        "CTX",
        "TARGET",
        "CTX",
        "CTX",
    ]
    assert alias_to_id == {"a1": "m1", "a2": "m2", "a3": "m3", "a4": "m4", "a5": "m5"}


def test_self_contained_target_only_keeps_one_previous_context_message():
    context = load_module("test_analysis_context_prune", "analysis_context.py")
    base = datetime(2026, 3, 1, 10, 0, tzinfo=timezone.utc)
    dialogue = [
        dialogue_message(
            f"m{i}",
            (base + timedelta(seconds=i * 30)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "other",
            "Other",
            f"上下文{i}",
        )
        for i in range(6)
    ]
    dialogue[3]["sender"] = "wx1"
    dialogue[3]["nickname"] = "Alice"
    dialogue[3]["content"] = "公网IP和动态域名解析的完整配置已经确认可用"

    context_messages, _, _ = context.build_context_messages(
        "wx1",
        "Alice",
        [
            {
                "id": "m3",
                "content": "公网IP和动态域名解析的完整配置已经确认可用",
                "timestamp": dialogue[3]["timestamp"],
            }
        ],
        dialogue,
    )

    assert [message["id"] for message in context_messages] == ["m2", "m3"]


def test_chunking_respects_character_budget_and_preserves_targets():
    context = load_module("test_analysis_context_chunk", "analysis_context.py")
    messages = [
        {
            "id": f"m{i}",
            "timestamp": f"2026-03-{1 + i // 10:02d}T10:00:{i % 60:02d}Z",
            "nickname": "Alice",
            "sender": "wx1",
            "role": "TARGET",
            "alias": f"a{i + 1}",
            "speaker_alias": "T",
            "content": "A" * 400,
            "quote": None,
        }
        for i in range(40)
    ]

    chunks = context.chunk_context_messages(messages, max_chars=3000)

    assert len(chunks) > 1
    assert all(len(chunk["text"]) <= 3240 for chunk in chunks)
    assert sum(chunk["own_count"] for chunk in chunks) == 40
    assert {message["id"] for chunk in chunks for message in chunk["messages"]} == {
        f"m{i}" for i in range(40)
    }


def test_input_package_counts_substantive_messages_and_full_period():
    context = load_module("test_analysis_context_stats", "analysis_context.py")
    messages = [
        {"id": "m1", "content": "[图片]", "timestamp": "2026-03-01T00:00:00Z"},
        {"id": "m2", "content": "有效观点", "timestamp": "2026-03-03T00:00:00Z"},
    ]
    dialogue = [
        dialogue_message("d1", "2026-03-01T00:00:00Z", "wx1", "Alice", "[图片]"),
        dialogue_message("d2", "2026-03-05T00:00:00Z", "wx2", "Bob", "其他消息"),
    ]

    package = context.build_input_package("wx1", "Alice", messages, dialogue)

    assert package["stats"] == {
        "rawMessageCount": 2,
        "substantiveCount": 1,
        "activeDays": 1,
        "periodDays": 5,
        "linkCount": 0,
        "mediaCount": 1,
    }
    assert package["alias_to_id"]


def test_compact_context_uses_short_alias_time_and_speaker():
    context = load_module("test_analysis_context_compact", "analysis_context.py")
    message = {
        "id": "message_2:Msg_very_long_identifier:10565",
        "alias": "a7",
        "timestamp": "2026-10-08T09:05:40Z",
        "nickname": "Zer_8",
        "sender": "wx2",
        "role": "CTX",
        "speaker_alias": "C1",
        "content": "magpie 都开始做 UI 优化了",
        "quote": None,
    }

    rendered = context.format_context_message(message)

    assert rendered == "17:05 a7 C1: magpie 都开始做 UI 优化了"
    assert "message_2" not in rendered
    assert "2026-" not in rendered


def test_scoring_weights_confidence_and_calibration_are_deterministic():
    scoring = load_module("test_analysis_scoring", "analysis_scoring.py")

    assert scoring.confidence_for(4) == "low"
    assert scoring.confidence_for(5) == "medium"
    assert scoring.confidence_for(20) == "high"
    assert scoring.continuity_score(5, 10) == 50.0
    assert scoring.raw_quality_score(
        {
            "informationDensity": 80,
            "originality": 70,
            "resourceValue": 60,
            "interactionValue": 50,
        },
        100,
    ) == 72.5

    results = [
        {
            "wxid": "a",
            "status": "normal",
            "confidence": "medium",
            "rawScore": 20,
            "dimensions": {"informationDensity": 20},
        },
        {
            "wxid": "b",
            "status": "normal",
            "confidence": "medium",
            "rawScore": 40,
            "dimensions": {"informationDensity": 40},
        },
        {
            "wxid": "c",
            "status": "normal",
            "confidence": "high",
            "rawScore": 60,
            "dimensions": {"informationDensity": 60},
        },
        {
            "wxid": "d",
            "status": "normal",
            "confidence": "high",
            "rawScore": 80,
            "dimensions": {"informationDensity": 80},
        },
        {
            "wxid": "e",
            "status": "normal",
            "confidence": "low",
            "rawScore": 90,
            "dimensions": {"informationDensity": 90},
        },
    ]
    calibration = scoring.calibrate_member_scores(results)

    assert calibration["applied"] is True
    assert [result["score"] for result in results] == [14.0, 38.0, 62.0, 86.0, 90.0]
    assert results[-1]["calibrated"] is False


def test_highlight_validation_rejects_invalid_types_and_cross_member_sources():
    scoring = load_module("test_analysis_scoring_validation", "analysis_scoring.py")

    with pytest.raises(ValidationError):
        scoring.Highlight(type="invalid", content="内容", messageId="m1")

    highlights = [
        scoring.Highlight(
            type="insight", content="冒领上下文", messageId="ctx1"
        ),
        scoring.Highlight(
            type="insight", content="本人观点", messageId="m1"
        ),
    ]
    own_messages = [
        {
            "id": "m1",
            "content": "本人观点",
            "timestamp": "2026-03-01T00:00:00Z",
        }
    ]
    context_messages = [
        {
            "id": "ctx1",
            "content": "其他人观点",
            "timestamp": "2026-03-01T00:00:01Z",
        }
    ]

    repaired = scoring.repair_highlights_with_sources(
        highlights, own_messages, context_messages
    )

    assert repaired == [
        {
            "type": "insight",
            "content": "本人观点",
            "messageId": "m1",
        }
    ]


def test_analysis_schema_enforces_summary_and_highlight_limits():
    scoring = load_module("test_analysis_scoring_limits", "analysis_scoring.py")
    base = {
        "summary": "太短",
        "dimensions": {
            "informationDensity": 50,
            "originality": 50,
            "resourceValue": 50,
            "interactionValue": 50,
        },
        "evidence": [],
        "highlights": [],
    }

    with pytest.raises(ValidationError):
        scoring.AnalysisResult.model_validate(base)

    highlights = [
        {"type": "insight", "content": f"观点{i}", "messageId": "m1"}
        for i in range(11)
    ]
    with pytest.raises(ValidationError):
        scoring.AnalysisResult.model_validate(
            {
                **base,
                "summary": "这是一段长度符合要求的成员总结内容。",
                "highlights": highlights,
            }
        )


def test_invalid_evidence_ids_are_removed():
    scoring = load_module("test_analysis_scoring_evidence", "analysis_scoring.py")
    evidence = [
        scoring.Evidence(messageId="m1", topic="有效", kind="claim"),
        scoring.Evidence(messageId="missing", topic="无来源", kind="claim"),
    ]

    filtered = scoring.filter_valid_evidence(evidence, {"m1"})

    assert filtered == [{"messageId": "m1", "topic": "有效", "kind": "claim"}]


def test_payload_normalization_tolerates_unknown_evidence_kind_and_long_summary():
    scoring = load_module("test_analysis_scoring_tolerant", "analysis_scoring.py")
    result = scoring.normalize_analysis_payload(
        {
            "summary": "长" * 200,
            "dimensions": {
                "informationDensity": 120,
                "originality": -5,
                "resource_value": "70",
                "interaction_value": 40,
            },
            "evidence": [
                {"messageId": "a1", "topic": "测试", "kind": "insight"}
            ],
            "highlights": [],
        }
    )

    assert len(result.summary) == 160
    assert result.dimensions.informationDensity == 100
    assert result.dimensions.originality == 0
    assert result.dimensions.resourceValue == 70
    assert result.evidence[0].kind == "claim"


def test_payload_normalization_maps_resource_highlight_type():
    scoring = load_module("test_analysis_scoring_resource", "analysis_scoring.py")
    result = scoring.normalize_analysis_payload(
        {
            "summary": "这是一段长度足够的成员质量总结。",
            "dimensions": {
                "informationDensity": 50,
                "originality": 50,
                "resourceValue": 50,
                "interactionValue": 50,
            },
            "evidence": [],
            "highlights": [
                {
                    "type": "resource",
                    "content": "无链接资源观点",
                    "messageId": "a1",
                },
                {
                    "type": "resource",
                    "content": "有链接资源",
                    "messageId": "a2",
                    "url": "https://example.com",
                },
            ],
        }
    )

    assert [item.type for item in result.highlights] == ["insight", "article"]


def test_news_requires_a_source_url_and_article_url_is_backfilled():
    scoring = load_module("test_analysis_scoring_urls", "analysis_scoring.py")
    own_messages = [
        {
            "id": "m1",
            "content": "[文章](https://example.com/article)",
            "timestamp": "2026-03-01T00:00:00Z",
        },
        {
            "id": "m2",
            "content": "没有链接的普通消息",
            "timestamp": "2026-03-01T00:01:00Z",
        },
    ]
    highlights = [
        scoring.Highlight(
            type="article",
            content="文章",
            messageId="m1",
            url="",
        ),
        scoring.Highlight(
            type="news",
            content="无来源新闻",
            messageId="m2",
            url="https://example.com/fake",
        ),
    ]

    repaired = scoring.repair_highlights_with_sources(highlights, own_messages, [])

    assert len(repaired) == 1
    assert repaired[0]["type"] == "article"
    assert repaired[0]["url"] == "https://example.com/article"


def test_highlights_are_replaced_with_source_titles_and_exact_quotes():
    scoring = load_module("test_analysis_scoring_exact", "analysis_scoring.py")
    own_messages = [
        {
            "id": "m1",
            "content": "我认为最关键的判断是不要把摘要当原文。",
            "timestamp": "2026-03-01T00:00:00Z",
        },
        {
            "id": "m2",
            "content": "【原始新闻标题】 https://example.com/news",
            "timestamp": "2026-03-01T00:01:00Z",
        },
        {
            "id": "m3",
            "content": "https://example.com/only-url",
            "timestamp": "2026-03-01T00:02:00Z",
        },
    ]
    highlights = [
        scoring.Highlight(
            type="insight",
            content="指出不要把摘要当原文",
            messageId="m1",
        ),
        scoring.Highlight(
            type="article",
            content="分享一条新闻并做了总结",
            messageId="m2",
        ),
        scoring.Highlight(
            type="article",
            content="分享一个没有标题的链接",
            messageId="m3",
        ),
    ]

    repaired = scoring.repair_highlights_with_sources(highlights, own_messages, [])

    assert repaired == [
        {
            "type": "insight",
            "content": "我认为最关键的判断是不要把摘要当原文。",
            "messageId": "m1",
        },
        {
            "type": "article",
            "content": "原始新闻标题",
            "messageId": "m2",
            "url": "https://example.com/news",
        },
    ]


def test_multiline_article_metadata_uses_only_article_name_as_title():
    scoring = load_module("test_analysis_scoring_multiline", "analysis_scoring.py")
    own_messages = [
        {
            "id": "m1",
            "content": (
                "文章名称：Rethinking skills and prompts for GPT-6 Astra\n"
                "摘要：重新审视技能描述、AGENTS.md 以及任务提示词。\n"
                "原文链接：https://developers.openai.com/blog/example"
            ),
            "timestamp": "2026-03-01T00:00:00Z",
        }
    ]
    highlights = [
        scoring.Highlight(
            type="article",
            content="分享一篇关于提示词的文章",
            messageId="m1",
        )
    ]

    repaired = scoring.repair_highlights_with_sources(highlights, own_messages, [])

    assert repaired == [
        {
            "type": "article",
            "content": "Rethinking skills and prompts for GPT-6 Astra",
            "messageId": "m1",
            "url": "https://developers.openai.com/blog/example",
        }
    ]


def test_insight_original_text_removes_wechat_and_unicode_emoji():
    scoring = load_module("test_analysis_scoring_emoji", "analysis_scoring.py")
    own_messages = [
        {
            "id": "m1",
            "content": "这个判断很重要[破涕为笑] 🚀 [旺柴]",
            "timestamp": "2026-03-01T00:00:00Z",
        }
    ]
    highlights = [
        scoring.Highlight(
            type="insight",
            content="另一个摘要",
            messageId="m1",
        )
    ]

    repaired = scoring.repair_highlights_with_sources(highlights, own_messages, [])

    assert repaired == [
        {
            "type": "insight",
            "content": "这个判断很重要",
            "messageId": "m1",
        }
    ]
