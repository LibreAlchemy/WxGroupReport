import asyncio
import importlib.util
import json
import shutil
import sys
import types
from pathlib import Path

import pytest


def load_analyze_module():
    script_path = (
        Path(__file__).resolve().parents[1]
        / ".agents"
        / "skills"
        / "analyze-messages"
        / "scripts"
        / "analyze.py"
    )
    spec = importlib.util.spec_from_file_location("test_analyze_module", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    sys.modules.setdefault(
        "litellm",
        types.SimpleNamespace(
            drop_params=False,
            acompletion=None,
        ),
    )
    spec.loader.exec_module(module)
    return module


class FakeMessage:
    def __init__(self, content):
        self.content = content


class FakeChoice:
    def __init__(self, content):
        self.message = FakeMessage(content)


class FakeResponse:
    def __init__(self, content):
        self.choices = [FakeChoice(content)]


def analysis_json(
    message_id="m1",
    summary="成员持续分享了有信息量的技术观点和资源。",
    dimensions=None,
    highlights=None,
    evidence=None,
):
    dimensions = dimensions or {
        "informationDensity": 80,
        "originality": 70,
        "resourceValue": 60,
        "interactionValue": 50,
    }
    return json.dumps(
        {
            "summary": summary,
            "dimensions": dimensions,
            "evidence": evidence
            if evidence is not None
            else [{"messageId": message_id, "topic": "技术讨论", "kind": "claim"}],
            "highlights": highlights
            if highlights is not None
            else [
                {
                    "type": "insight",
                    "content": "有代表性的原创观点",
                    "messageId": message_id,
                    "url": "",
                }
            ],
        },
        ensure_ascii=False,
    )


def write_member(path: Path, wxid: str, nickname: str, messages):
    path.write_text(
        json.dumps(
            {"wxid": wxid, "nickname": nickname, "messages": messages},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def test_filter_effective_messages_excludes_placeholders_and_image_paths():
    analyze = load_analyze_module()
    messages = [
        {"content": "#接龙 明天中午吃什么"},
        {"content": "../images/20260328/abc123.png"},
        {"content": "[图片]"},
        {"content": "[表情]"},
        {"content": "[链接] 一篇文章"},
    ]

    filtered = analyze.filter_effective_messages(messages)

    assert filtered == [{"content": "[链接] 一篇文章"}]


def test_build_prompt_separates_rules_from_untrusted_chat_data():
    analyze = load_analyze_module()
    prompt = analyze.build_prompt(
        "wxid_alice",
        "Alice",
        [
            {
                "id": "m1",
                "timestamp": "2026-03-01T08:00:00Z",
                "content": "有效消息",
            }
        ],
    )

    assert "不可信数据" in prompt
    assert "<BEGIN_UNTRUSTED_CHAT>" in prompt
    assert "<END_UNTRUSTED_CHAT>" in prompt
    assert "informationDensity" in prompt
    assert "消息别名" in prompt
    assert "只评估 T 消息" in prompt
    assert "github：content 用简洁中文说明项目用途" in prompt
    assert "禁止把消息别名 T 当作成员名称" in prompt
    assert "可脱离上下文理解、对他人有复用价值" in prompt
    assert "没有手写过代码了" in prompt
    assert "宁缺毋滥" in prompt


def test_truncate_quoted_reply_blocks_handles_nested_brackets():
    analyze = load_analyze_module()
    long_quote = "[引用 Alice：" + ("B" * 140) + "[脸红]]"

    cleaned = analyze.truncate_quoted_reply_blocks(f"前文{long_quote}后文")

    assert cleaned.startswith("前文后文[引用 Alice：")
    assert cleaned.endswith("...")
    assert "B" * 110 not in cleaned


def test_sanitize_highlight_output_removes_empty_url():
    analyze = load_analyze_module()

    highlights = [
        {"type": "insight", "content": "一个观点", "url": ""},
        {"type": "article", "content": "一篇文章", "url": "https://example.com"},
    ]

    cleaned = analyze.sanitize_highlight_output(highlights)

    assert cleaned == [
        {"type": "insight", "content": "一个观点"},
        {"type": "article", "content": "一篇文章", "url": "https://example.com"},
    ]


def test_analyze_member_repairs_article_url_from_evidence_message(monkeypatch):
    module = load_analyze_module()
    url = (
        "https://mp.weixin.qq.com/s?scene=1&__biz=MzA4NzgzMjA4MQ==&mid=2453482212"
        "&idx=1&sn=48762a1e014431e3c22c38408e6b29f3&sharer_shareinfo=broken"
    )

    async def fake_completion(**kwargs):
        return FakeResponse(
            analysis_json(
                message_id="m1",
                highlights=[
                    {
                        "type": "article",
                        "content": "AGI Hunt的文字分享",
                        "messageId": "m1",
                        "url": "https://example.com/wrong",
                    }
                ],
            )
        )

    monkeypatch.setattr(module.litellm, "acompletion", fake_completion, raising=False)

    async def run():
        return await module.analyze_member(
            asyncio.Semaphore(1),
            "wx1",
            "Alice",
            [
                {
                    "id": "m1",
                    "content": f"[AGI Hunt的文字分享]({url})",
                    "timestamp": "2026-04-01T00:00:00Z",
                }
            ],
            {"count": 0, "lock": asyncio.Lock()},
        )

    result = asyncio.run(run())
    assert result["highlights"][0]["messageId"] == "m1"
    assert result["highlights"][0]["url"].startswith(
        "https://mp.weixin.qq.com/s?__biz="
    )


def test_analyze_member_uses_specific_evidence_message_for_duplicate_titles(
    monkeypatch,
):
    module = load_analyze_module()

    async def fake_completion(**kwargs):
        return FakeResponse(
            analysis_json(
                message_id="m2",
                highlights=[
                    {
                        "type": "article",
                        "content": "重复标题",
                        "messageId": "m2",
                        "url": "",
                    }
                ],
            )
        )

    monkeypatch.setattr(module.litellm, "acompletion", fake_completion, raising=False)

    async def run():
        return await module.analyze_member(
            asyncio.Semaphore(1),
            "wx1",
            "Alice",
            [
                {
                    "id": "m1",
                    "content": "[重复标题](https://mp.weixin.qq.com/s?__biz=first==&mid=1)",
                    "timestamp": "2026-04-01T00:00:00Z",
                },
                {
                    "id": "m2",
                    "content": "[重复标题](https://mp.weixin.qq.com/s?__biz=last==&mid=2)",
                    "timestamp": "2026-04-01T00:01:00Z",
                },
            ],
            {"count": 0, "lock": asyncio.Lock()},
        )

    result = asyncio.run(run())
    assert "mid=2" in result["highlights"][0]["url"]


def test_build_output_paths_derives_all_runtime_paths():
    analyze = load_analyze_module()

    paths = analyze.build_output_paths("custom-output")

    assert paths == {
        "output_dir": "custom-output",
        "members_dir": "custom-output/members",
        "scores_dir": "custom-output/scores",
        "errors_file": "custom-output/errors.json",
        "analysis_path": "custom-output/analyze.json",
        "dialogue_path": "custom-output/dialogue.json",
    }


def test_analyze_member_returns_zero_activity_for_media_only():
    module = load_analyze_module()

    async def run():
        return await module.analyze_member(
            asyncio.Semaphore(1),
            "wx1",
            "Alice",
            [
                {"content": "[图片]", "timestamp": "2026-03-01T00:00:00Z"},
                {"content": "[表情]", "timestamp": "2026-03-01T00:01:00Z"},
            ],
            {"count": 0, "lock": asyncio.Lock()},
        )

    result = asyncio.run(run())
    assert result["status"] == "zero_activity"
    assert result["messageCount"] == 0
    assert result["rawMessageCount"] == 2
    assert result["confidence"] == "low"


def test_analyze_member_parses_fenced_json(monkeypatch):
    module = load_analyze_module()

    async def fake_completion(**kwargs):
        return FakeResponse("```json\n" + analysis_json(message_id="m1") + "\n```")

    monkeypatch.setattr(module.litellm, "acompletion", fake_completion, raising=False)

    async def run():
        return await module.analyze_member(
            asyncio.Semaphore(1),
            "wx1",
            "Alice",
            [
                {
                    "id": "m1",
                    "content": "有效消息",
                    "timestamp": "2026-03-01T00:00:00Z",
                }
            ],
            {"count": 0, "lock": asyncio.Lock()},
        )

    result = asyncio.run(run())
    assert result["status"] == "normal"
    assert result["dimensions"]["informationDensity"] == 80
    assert result["evidence"] == [
        {"messageId": "m1", "topic": "技术讨论", "kind": "claim"}
    ]


def test_analyze_member_resolves_compact_aliases_to_source_ids(monkeypatch):
    module = load_analyze_module()

    async def fake_completion(**kwargs):
        return FakeResponse(
            analysis_json(
                message_id="a1",
                highlights=[
                    {
                        "type": "insight",
                        "content": "别名观点",
                        "messageId": "a1",
                        "url": "",
                    }
                ],
                evidence=[
                    {"messageId": "a1", "topic": "别名", "kind": "claim"}
                ],
            )
        )

    monkeypatch.setattr(module.litellm, "acompletion", fake_completion, raising=False)

    async def run():
        return await module.analyze_member(
            asyncio.Semaphore(1),
            "wx1",
            "Alice",
            [
                {
                    "id": "source-message-1",
                    "content": "有效观点",
                    "timestamp": "2026-03-01T00:00:00Z",
                }
            ],
            {"count": 0, "lock": asyncio.Lock()},
        )

    result = asyncio.run(run())
    assert result["evidence"][0]["messageId"] == "source-message-1"
    assert result["highlights"][0]["messageId"] == "source-message-1"


def test_analyze_member_splits_large_context_and_runs_synthesis(monkeypatch):
    module = load_analyze_module()
    calls = []

    async def fake_completion(**kwargs):
        user_prompt = kwargs["messages"][1]["content"]
        calls.append(user_prompt)
        return FakeResponse(analysis_json(message_id="", highlights=[], evidence=[]))

    monkeypatch.setattr(module.litellm, "acompletion", fake_completion, raising=False)
    messages = [
        {
            "id": f"m{index}",
            "content": "A" * 400,
            "timestamp": f"2026-03-01T{index % 24:02d}:{index % 60:02d}:00Z",
        }
        for index in range(40)
    ]

    async def run():
        return await module.analyze_member(
            asyncio.Semaphore(1),
            "wx1",
            "Alice",
            messages,
            {"count": 0, "lock": asyncio.Lock()},
        )

    result = asyncio.run(run())
    assert result["status"] == "normal"
    assert result["chunkCount"] > 1
    assert len(calls) == result["chunkCount"] + 1
    assert "汇总任务" in calls[-1]


def test_analyze_member_returns_error_when_completion_fails(monkeypatch):
    module = load_analyze_module()

    async def fake_completion(**kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(module.litellm, "acompletion", fake_completion, raising=False)

    async def run():
        return await module.analyze_member(
            asyncio.Semaphore(1),
            "wx1",
            "Alice",
            [
                {
                    "id": "m1",
                    "content": "有效消息",
                    "timestamp": "2026-03-01T00:00:00Z",
                }
            ],
            {"count": 0, "lock": asyncio.Lock()},
        )

    result = asyncio.run(run())
    assert result["status"] == "error"
    assert result["error"] == "boom"


def test_main_returns_early_without_api_key(monkeypatch, tmp_path, capsys):
    module = load_analyze_module()
    monkeypatch.setattr(module, "AI_API_KEY", None)
    monkeypatch.setattr(sys, "argv", ["analyze.py", "-o", str(tmp_path / "out")])

    asyncio.run(module.main())

    assert "未设置 AI API Key" in capsys.readouterr().err


def test_main_generates_scores_analysis_and_cache_metadata(monkeypatch, tmp_path):
    module = load_analyze_module()
    out = tmp_path / "out"
    members_dir = out / "members"
    members_dir.mkdir(parents=True)
    write_member(
        members_dir / "wx1.json",
        "wx1",
        "Alice",
        [
            {
                "id": "m1",
                "content": "有信息量的有效消息",
                "timestamp": "2026-03-01T00:00:00Z",
            }
        ],
    )

    async def fake_completion(**kwargs):
        system_prompt = kwargs["messages"][0]["content"]
        if "原创心得编辑" in system_prompt:
            user_prompt = kwargs["messages"][1]["content"]
            candidates = json.loads(user_prompt.split("\n", 1)[1])
            return FakeResponse(
                json.dumps(
                    {
                        "decisions": [
                            {"id": item["id"], "keep": True}
                            for item in candidates
                        ]
                    },
                    ensure_ascii=False,
                )
            )
        return FakeResponse(analysis_json(message_id="m1"))

    monkeypatch.setattr(module.litellm, "acompletion", fake_completion, raising=False)
    monkeypatch.setattr(module, "AI_API_KEY", "test-key")
    monkeypatch.setattr(module, "MAX_WORKERS", 1)
    monkeypatch.setattr(sys, "argv", ["analyze.py", "-o", str(out)])

    asyncio.run(module.main())

    score = json.loads((out / "scores" / "wx1.json").read_text(encoding="utf-8"))
    analysis = json.loads((out / "analyze.json").read_text(encoding="utf-8"))
    assert score["status"] == "normal"
    assert score["rawScore"] == score["score"]
    assert score["promptVersion"] == module.PROMPT_VERSION
    assert score["scoringVersion"] == module.SCORING_VERSION
    assert score["inputHash"]
    assert analysis["data"]["metadata"]["calibration"]["applied"] is False
    assert analysis["data"]["metadata"]["insightCuration"]["kept"] == 1
    assert analysis["data"]["highlights"][0]["author"] == "Alice"


def test_score_cache_requires_version_model_and_input_hash():
    module = load_analyze_module()
    current = {
        "status": "normal",
        "promptVersion": module.PROMPT_VERSION,
        "scoringVersion": module.SCORING_VERSION,
        "model": module.LITELLM_MODEL,
        "temperature": module.AI_TEMPERATURE,
        "reasoningEffort": module.REASONING_EFFORT,
        "inputHash": "abc",
    }

    assert module.score_cache_is_current(current, "abc") is True
    assert (
        module.score_cache_is_current({**current, "promptVersion": "old"}, "abc")
        is False
    )
    assert (
        module.score_cache_is_current({**current, "model": "old/model"}, "abc")
        is False
    )
    assert module.score_cache_is_current(current, "new") is False


def test_provided_archive_runs_full_mocked_analysis(monkeypatch, tmp_path):
    module = load_analyze_module()
    source = Path(__file__).resolve().parents[1] / "output"
    members_dir = source / "members"
    dialogue_path = source / "dialogue.json"
    imported_path = source / "imported.json"
    if not members_dir.exists() or not dialogue_path.exists() or not imported_path.exists():
        pytest.skip("current processed archive is not available")

    out = tmp_path / "out"
    shutil.copytree(members_dir, out / "members")
    shutil.copy2(dialogue_path, out / "dialogue.json")
    shutil.copy2(imported_path, out / "imported.json")

    async def fake_completion(**kwargs):
        return FakeResponse(
            analysis_json(message_id="", highlights=[], evidence=[])
        )

    monkeypatch.setattr(module.litellm, "acompletion", fake_completion, raising=False)
    monkeypatch.setattr(module, "AI_API_KEY", "test-key")
    monkeypatch.setattr(module, "MAX_WORKERS", 8)
    monkeypatch.setattr(sys, "argv", ["analyze.py", "-o", str(out)])

    asyncio.run(module.main())

    analysis = json.loads((out / "analyze.json").read_text(encoding="utf-8"))
    scores = analysis["data"]["memberScores"]
    assert len(scores) == 57
    assert sum(score["messageCount"] for score in scores) == 4523
    assert any(score["chunkCount"] > 1 for score in scores)
    assert analysis["data"]["metadata"]["calibration"]["applied"] is True


def test_analyze_member_forwards_inference_params(monkeypatch):
    module = load_analyze_module()
    captured = {}

    async def fake_completion(**kwargs):
        captured.update(kwargs)
        return FakeResponse(
            analysis_json(message_id="m1", highlights=[], evidence=[])
        )

    monkeypatch.setattr(module.litellm, "acompletion", fake_completion, raising=False)
    monkeypatch.setattr(module, "REASONING_EFFORT", "medium")

    async def run():
        return await module.analyze_member(
            asyncio.Semaphore(1),
            "wx1",
            "Alice",
            [
                {
                    "id": "m1",
                    "content": "有效消息",
                    "timestamp": "2026-03-01T00:00:00Z",
                }
            ],
            {"count": 0, "lock": asyncio.Lock()},
        )

    result = asyncio.run(run())
    assert result["status"] == "normal"
    assert captured["temperature"] == module.AI_TEMPERATURE
    assert captured["reasoning_effort"] == "medium"
    assert captured["messages"][0]["role"] == "system"
    assert captured["messages"][1]["role"] == "user"


def test_completion_kwargs_always_include_fixed_temperature(monkeypatch):
    module = load_analyze_module()
    monkeypatch.delenv("REASONING_EFFORT", raising=False)

    monkeypatch.setattr(module, "REASONING_EFFORT", "")
    assert module.build_completion_kwargs() == {"temperature": 0.1}


def test_completion_kwargs_include_reasoning_effort_when_set(monkeypatch):
    module = load_analyze_module()

    monkeypatch.setattr(module, "REASONING_EFFORT", "high")
    assert module.build_completion_kwargs() == {
        "temperature": 0.1,
        "reasoning_effort": "high",
    }


def test_resolve_reasoning_effort_normalizes_and_warns(monkeypatch, capsys):
    module = load_analyze_module()

    monkeypatch.setenv("REASONING_EFFORT", "  HIGH ")
    assert module.resolve_reasoning_effort() == "high"
    assert "非常见" not in capsys.readouterr().err

    monkeypatch.setenv("REASONING_EFFORT", "ultra")
    assert module.resolve_reasoning_effort() == "ultra"
    assert "非常见 REASONING_EFFORT='ultra'" in capsys.readouterr().err

    monkeypatch.setenv("REASONING_EFFORT", "   ")
    assert module.resolve_reasoning_effort() == ""


def test_resolve_temperature_uses_env_default_and_fallbacks(monkeypatch, capsys):
    module = load_analyze_module()

    monkeypatch.setenv("AI_TEMPERATURE", "0.8")
    assert module.resolve_temperature() == 0.8

    monkeypatch.setenv("AI_TEMPERATURE", "0")
    assert module.resolve_temperature() == 0.0
    assert "无效" not in capsys.readouterr().err

    monkeypatch.delenv("AI_TEMPERATURE", raising=False)
    assert module.resolve_temperature() == module.DEFAULT_TEMPERATURE

    monkeypatch.setenv("AI_TEMPERATURE", "abc")
    assert module.resolve_temperature() == module.DEFAULT_TEMPERATURE
    assert "无效 AI_TEMPERATURE='abc'" in capsys.readouterr().err

    monkeypatch.setenv("AI_TEMPERATURE", "5")
    assert module.resolve_temperature() == module.DEFAULT_TEMPERATURE
    assert "超出 0.0-2.0 范围" in capsys.readouterr().err
