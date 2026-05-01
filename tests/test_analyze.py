import asyncio
import importlib.util
import json
import sys
import types
from pathlib import Path


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


def write_member(path: Path, wxid: str, nickname: str, messages):
    path.write_text(
        json.dumps(
            {"wxid": wxid, "nickname": nickname, "messages": messages},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def test_filter_effective_messages_excludes_jielong_and_exported_image_paths():
    analyze = load_analyze_module()
    messages = [
        {"content": "#接龙 明天中午吃什么"},
        {"content": "../images/20260328/abc123.png"},
        {"content": "[链接] 一篇文章"},
    ]

    filtered = analyze.filter_effective_messages(messages)

    assert filtered == [{"content": "[链接] 一篇文章"}]


def test_build_prompt_formats_messages_with_timestamp_sorted_and_truncated():
    analyze = load_analyze_module()
    long_content = "A" * 620
    filtered_messages = [
        {"timestamp": "2026-03-03T10:00:00Z", "content": "后发的消息"},
        {"timestamp": "2026-03-01T08:00:00Z", "content": long_content},
    ]

    prompt = analyze.build_prompt("wxid_alice", "Alice", filtered_messages)
    message_section = prompt.split("## 消息内容\n", 1)[1].split("\n\n## 注意事项", 1)[0]

    assert "[2026-03-01T08:00:00Z] " + ("A" * 500) + "..." in prompt
    assert "[2026-03-03T10:00:00Z] 后发的消息" in prompt
    assert prompt.index("2026-03-01T08:00:00Z") < prompt.index("2026-03-03T10:00:00Z")
    assert "0. " not in message_section
    assert "1. " not in message_section
    assert "需要结合消息发送时间理解上下文" in prompt
    assert "避免因为单次高质量发言或短时高频发言而高估整体质量" in prompt
    assert "score 主要衡量内容质量、信息密度和有效性" in prompt
    assert "quality_score" not in prompt
    assert "stats" not in prompt
    assert "highlights 总数不超过 10 条" in prompt
    assert "news|article|github|insight|opportunity" in prompt
    assert "news 类型必须有明确 URL" in prompt
    assert "非新闻型公众号/博客/技术文章/教程/资源文章" in prompt
    assert "必须优先填写成员消息中的原文片段" in prompt


def test_truncate_quoted_reply_blocks_preserves_quote_prefix():
    analyze = load_analyze_module()
    long_quote = "[引用 Alice：" + ("B" * 140) + "]"

    cleaned = analyze.truncate_quoted_reply_blocks(f"前文{long_quote}后文")

    assert cleaned.startswith("前文[引用 Alice：")
    assert cleaned.endswith("...后文")
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


def test_analyze_member_repairs_article_url_from_member_messages(monkeypatch):
    module = load_analyze_module()

    async def fake_completion(**kwargs):
        return FakeResponse(
            '{"summary":"总结","score":77,"highlights":[{"type":"article","content":"AGI Hunt的文字分享","url":"https://mp.weixin.qq.com/s?scene=1&__biz=MzA4NzgzMjA4MQ==&mid=2453482212&idx=1&sn=48762a1e014431e3c22c38408e6b29f3&sharer_shareinfo=broken..."}]}'
        )

    monkeypatch.setattr(module.litellm, "acompletion", fake_completion, raising=False)

    async def run():
        return await module.analyze_member(
            asyncio.Semaphore(1),
            "wx1",
            "Alice",
            [
                {
                    "content": "[AGI Hunt的文字分享](https://mp.weixin.qq.com/s?scene=1&__biz=MzA4NzgzMjA4MQ==&mid=2453482212&idx=1&sn=48762a1e014431e3c22c38408e6b29f3&sharer_shareinfo_first=dc2fbfdc23aa15a4a1812fc09723f48b&sharer_shareinfo=dc2fbfdc23aa15a4a1812fc09723f48b#wechat_redirect)",
                    "timestamp": "2026-04-01T00:00:00Z",
                }
            ],
            {"count": 0, "lock": asyncio.Lock()},
        )

    result = asyncio.run(run())
    assert result["highlights"] == [
        {
            "type": "article",
            "content": "AGI Hunt的文字分享",
            "url": "https://mp.weixin.qq.com/s?__biz=MzA4NzgzMjA4MQ%3D%3D&mid=2453482212&idx=1&sn=48762a1e014431e3c22c38408e6b29f3",
        }
    ]


def test_analyze_member_repairs_article_url_uses_last_matching_message(monkeypatch):
    module = load_analyze_module()

    async def fake_completion(**kwargs):
        return FakeResponse(
            '{"summary":"总结","score":77,"highlights":[{"type":"article","content":"重复标题","url":"https://mp.weixin.qq.com/s/short"}]}'
        )

    monkeypatch.setattr(module.litellm, "acompletion", fake_completion, raising=False)

    async def run():
        return await module.analyze_member(
            asyncio.Semaphore(1),
            "wx1",
            "Alice",
            [
                {
                    "content": "[重复标题](https://mp.weixin.qq.com/s?__biz=first==&mid=1&idx=1&sn=first&scene=1)",
                    "timestamp": "2026-04-01T00:00:00Z",
                },
                {
                    "content": "[重复标题](https://mp.weixin.qq.com/s?__biz=last==&mid=2&idx=1&sn=last&scene=1)",
                    "timestamp": "2026-04-01T00:01:00Z",
                },
            ],
            {"count": 0, "lock": asyncio.Lock()},
        )

    result = asyncio.run(run())
    assert result["highlights"][0]["url"] == "https://mp.weixin.qq.com/s?__biz=last%3D%3D&mid=2&idx=1&sn=last"


def test_build_output_paths_derives_all_runtime_paths():
    analyze = load_analyze_module()

    paths = analyze.build_output_paths("custom-output")

    assert paths == {
        "output_dir": "custom-output",
        "members_dir": "custom-output/members",
        "scores_dir": "custom-output/scores",
        "errors_file": "custom-output/errors.json",
        "analysis_path": "custom-output/analyze.json",
    }


def test_analyze_member_returns_zero_activity():
    module = load_analyze_module()

    async def run():
        return await module.analyze_member(
            asyncio.Semaphore(1),
            "wx1",
            "Alice",
            [{"content": "#接龙 test", "timestamp": "2026-03-01T00:00:00Z"}],
            {"count": 0, "lock": asyncio.Lock()},
        )

    result = asyncio.run(run())
    assert result["status"] == "zero_activity"
    assert result["messageCount"] == 0


def test_analyze_member_parses_fenced_json(monkeypatch):
    module = load_analyze_module()

    async def fake_completion(**kwargs):
        return FakeResponse(
            """```json
{"summary":"总结","score":88,"highlights":[{"type":"insight","content":"原文观点","url":""}]}
```"""
        )

    monkeypatch.setattr(module.litellm, "acompletion", fake_completion, raising=False)

    async def run():
        return await module.analyze_member(
            asyncio.Semaphore(1),
            "wx1",
            "Alice",
            [{"content": "有效消息", "timestamp": "2026-03-01T00:00:00Z"}],
            {"count": 0, "lock": asyncio.Lock()},
        )

    result = asyncio.run(run())
    assert result["status"] == "normal"
    assert result["score"] == 88.0
    assert "qualityScore" not in result
    assert "stats" not in result
    assert result["highlights"] == [{"type": "insight", "content": "原文观点"}]


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
            [{"content": "有效消息", "timestamp": "2026-03-01T00:00:00Z"}],
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


def test_main_generates_scores_and_analyze_json(monkeypatch, tmp_path):
    module = load_analyze_module()
    out = tmp_path / "out"
    members_dir = out / "members"
    members_dir.mkdir(parents=True)
    write_member(
        members_dir / "wx1.json",
        "wx1",
        "Alice",
        [{"content": "有效消息", "timestamp": "2026-03-01T00:00:00Z"}],
    )

    async def fake_completion(**kwargs):
        return FakeResponse(
            '{"summary":"总结","score":77,"highlights":[{"type":"article","content":"文章标题","url":"https://example.com"}]}'
        )

    monkeypatch.setattr(module.litellm, "acompletion", fake_completion, raising=False)
    monkeypatch.setattr(module, "AI_API_KEY", "test-key")
    monkeypatch.setattr(module, "MAX_WORKERS", 1)
    monkeypatch.setattr(sys, "argv", ["analyze.py", "-o", str(out)])

    asyncio.run(module.main())

    score = json.loads((out / "scores" / "wx1.json").read_text(encoding="utf-8"))
    analysis = json.loads((out / "analyze.json").read_text(encoding="utf-8"))
    assert score["status"] == "normal"
    assert score["score"] == 77.0
    assert "qualityScore" not in score
    assert "stats" not in score
    assert analysis["data"]["memberScores"][0]["nickname"] == "Alice"
    assert analysis["data"]["memberScores"][0]["score"] == 77.0
    assert analysis["data"]["highlights"][0]["author"] == "Alice"
