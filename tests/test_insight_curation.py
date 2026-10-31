import asyncio
import importlib.util
import json
import sys
from pathlib import Path


def load_curation_module():
    skill_scripts = (
        Path(__file__).resolve().parents[1]
        / ".agents"
        / "skills"
        / "analyze-messages"
        / "scripts"
    )
    shared_scripts = skill_scripts.parents[1] / "shared"
    for path in (skill_scripts, shared_scripts):
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))
    script_path = skill_scripts / "insight_curation.py"
    spec = importlib.util.spec_from_file_location("insight_curation", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def sample_results():
    return [
        {
            "nickname": "Alice",
            "highlights": [
                {
                    "type": "insight",
                    "content": "没有手写过代码了",
                    "messageId": "m1",
                },
                {
                    "type": "insight",
                    "content": "更强模型能提升效果，但工程方案优化带来的提升有限。",
                    "messageId": "m2",
                },
                {
                    "type": "insight",
                    "content": "买个工控机算了",
                    "messageId": "m3",
                },
                {
                    "type": "news",
                    "content": "产品正式发布",
                    "messageId": "m4",
                    "url": "https://example.com/news",
                },
            ],
        }
    ]


class FakeMessage:
    def __init__(self, content):
        self.content = content


class FakeChoice:
    def __init__(self, content):
        self.message = FakeMessage(content)


class FakeResponse:
    def __init__(self, content):
        self.choices = [FakeChoice(content)]


def test_curation_prompt_defines_negative_daily_chat_examples():
    module = load_curation_module()

    assert "可复用价值" in module.CURATION_SYSTEM_PROMPT
    assert "没有手写过代码了" in module.CURATION_SYSTEM_PROMPT
    assert "买个工控机算了" in module.CURATION_SYSTEM_PROMPT
    assert "宁缺毋滥" in module.CURATION_SYSTEM_PROMPT


def test_curation_batches_respect_character_budget():
    module = load_curation_module()
    candidates = [
        {"id": f"c{index}", "author": "Alice", "content": "x" * 80}
        for index in range(1, 6)
    ]

    batches = module.build_curation_batches(candidates, max_chars=300)

    assert [len(batch) for batch in batches] == [2, 2, 1]


def test_parse_curation_payload_ignores_unknown_ids_and_missing_is_rejected():
    module = load_curation_module()
    payload = json.dumps(
        {
            "decisions": [
                {"id": "c1", "keep": True},
                {"id": "c2", "keep": False},
                {"id": "unknown", "keep": True},
            ]
        }
    )

    kept = module.parse_curation_payload(payload, {"c1", "c2", "c3"})

    assert kept == {"c1"}


def test_curate_insights_filters_model_rejected_daily_chat():
    module = load_curation_module()
    results = sample_results()
    requests = []

    async def fake_completion(**kwargs):
        user_prompt = kwargs["messages"][1]["content"]
        candidates = json.loads(user_prompt.split("\n", 1)[1])
        requests.append(candidates)
        return FakeResponse(
            json.dumps(
                {
                    "decisions": [
                        {"id": candidates[0]["id"], "keep": False},
                        {"id": candidates[1]["id"], "keep": True},
                        {"id": candidates[2]["id"], "keep": False},
                    ]
                },
                ensure_ascii=False,
            )
        )

    curated, metadata = asyncio.run(
        module.curate_insights(
            results,
            model="test/model",
            api_key="key",
            base_url=None,
            completion_kwargs={"temperature": 0.1},
            completion=fake_completion,
        )
    )

    assert len(requests) == 1
    assert metadata == {
        "version": module.CURATION_VERSION,
        "candidates": 3,
        "kept": 1,
        "dropped": 2,
        "batches": 1,
    }
    assert len(results[0]["highlights"]) == 4
    assert [item["type"] for item in curated[0]["highlights"]] == [
        "insight",
        "news",
    ]
    assert curated[0]["highlights"][0]["content"].startswith("更强模型")
