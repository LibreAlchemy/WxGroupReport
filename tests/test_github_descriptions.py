import asyncio
import importlib.util
import json
import sys
from pathlib import Path


def load_description_module():
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
    script_path = skill_scripts / "github_descriptions.py"
    spec = importlib.util.spec_from_file_location(
        "github_descriptions", script_path
    )
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
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


def test_build_github_projects_normalizes_and_deduplicates_repo_urls():
    module = load_description_module()
    dialogue = [
        {
            "content": "https://github.com/org/repo",
            "nickname": "Alice",
        },
        {
            "content": "项目 v2 https://github.com/org/repo/releases/tag/v2",
            "nickname": "Bob",
        },
    ]

    projects = module.build_github_projects(dialogue)

    assert len(projects) == 1
    assert projects[0]["url"] == "https://github.com/org/repo"
    assert projects[0]["repo"] == "org/repo"
    assert len(projects[0]["snippets"]) == 2


def test_parse_description_payload_accepts_known_ids_only():
    module = load_description_module()
    payload = json.dumps(
        {
            "projects": [
                {"id": "p1", "description": "一个用于自动化发布的开源工具。"},
                {"id": "p2", "description": "不应保留。"},
                {"id": "unknown", "description": "不应保留。"},
            ]
        },
        ensure_ascii=False,
    )

    descriptions = module.parse_description_payload(payload, {"p1"})

    assert descriptions == {"p1": "一个用于自动化发布的开源工具。"}


def test_enrich_github_projects_returns_description_map():
    module = load_description_module()
    dialogue = [
        {
            "content": "org/repo 是一个发布自动化工具 https://github.com/org/repo",
            "nickname": "Alice",
        }
    ]

    async def fake_completion(**kwargs):
        projects = json.loads(kwargs["messages"][1]["content"].split("\n", 1)[1])
        return FakeResponse(
            json.dumps(
                {
                    "projects": [
                        {
                            "id": projects[0]["id"],
                            "description": "一个用于自动化发布流程的开源工具。",
                        }
                    ]
                },
                ensure_ascii=False,
            )
        )

    descriptions, metadata = asyncio.run(
        module.enrich_github_projects(
            dialogue,
            model="test/model",
            api_key="key",
            base_url=None,
            completion_kwargs={"temperature": 0.1},
            completion=fake_completion,
        )
    )

    assert descriptions == {
        "https://github.com/org/repo": "一个用于自动化发布流程的开源工具。"
    }
    assert metadata == {
        "version": module.DESCRIPTION_VERSION,
        "projects": 1,
        "described": 1,
        "batches": 1,
    }
