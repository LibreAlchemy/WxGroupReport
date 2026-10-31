import json
from collections.abc import Awaitable, Callable

import litellm

from highlight_url_repair import (
    extract_source_links,
    normalize_github_repo_url,
    sanitize_url,
)
from message_context import safe_text


DESCRIPTION_VERSION = "2026-10-30-v1"
MAX_DESCRIPTION_CHARS = 12_000
DESCRIPTION_SYSTEM_PROMPT = """你是开源项目编辑。输入是微信群消息中出现的 GitHub 仓库及原始上下文。

为每个仓库写一句面向群外读者的中文推荐说明，说明：
- 项目主要做什么；
- 适合什么场景或用户；
- 有明确依据时可以补充关键特点。

要求：
- 只根据仓库名称、原始上下文和可靠的公开认知描述，不得编造功能、数据或评价；
- 不写“某人在群里推荐”“值得一看”“非常强大”等空话；
- 不依赖聊天上下文才能理解；
- 20-100 字，保持客观；
- 无法判断项目用途时，description 返回空字符串。

## 输出 JSON
{"projects":[{"id":"p1","description":"项目说明"}]}
必须为输入中的每个 id 返回一次，不得新增 id。
"""


def _extract_json_payload(content: str) -> str:
    text = (content or "").strip()
    if text.startswith("```json"):
        return text.replace("```json", "", 1).rsplit("```", 1)[0].strip()
    if text.startswith("```"):
        return text.replace("```", "", 1).rsplit("```", 1)[0].strip()
    return text


def build_github_projects(dialogue: list[dict]) -> list[dict]:
    projects = {}
    for message in dialogue:
        for link in extract_source_links(message.get("content") or ""):
            url = normalize_github_repo_url(link.get("url") or "")
            if not url:
                continue
            project = projects.setdefault(
                url,
                {
                    "url": url,
                    "repo": url.removeprefix("https://github.com/"),
                    "snippets": [],
                },
            )
            snippet = safe_text(message.get("content"))[:500]
            if snippet and snippet not in project["snippets"]:
                project["snippets"].append(snippet)

    result = []
    for index, project in enumerate(projects.values(), start=1):
        result.append(
            {
                "id": f"p{index}",
                "url": project["url"],
                "repo": project["repo"],
                "snippets": project["snippets"][:2],
            }
        )
    return result


def build_description_batches(
    projects: list[dict], max_chars: int = MAX_DESCRIPTION_CHARS
) -> list[list[dict]]:
    batches = []
    current = []
    current_chars = 0
    for project in projects:
        item = {
            "id": project["id"],
            "repo": project["repo"],
            "context": project["snippets"],
        }
        item_chars = len(json.dumps(item, ensure_ascii=False))
        if current and current_chars + item_chars > max_chars:
            batches.append(current)
            current = []
            current_chars = 0
        current.append(project)
        current_chars += item_chars
    if current:
        batches.append(current)
    return batches


def parse_description_payload(
    content: str, allowed_ids: set[str]
) -> dict[str, str]:
    payload = json.loads(_extract_json_payload(content))
    descriptions = {}
    for item in payload.get("projects") or []:
        if not isinstance(item, dict):
            continue
        project_id = safe_text(item.get("id"))
        description = safe_text(item.get("description"))
        if project_id in allowed_ids and description:
            descriptions[project_id] = description[:300]
    return descriptions


async def enrich_github_projects(
    dialogue: list[dict],
    *,
    model: str,
    api_key: str,
    base_url: str | None,
    completion_kwargs: dict,
    completion: Callable[..., Awaitable] | None = None,
) -> tuple[dict[str, str], dict]:
    completion = completion or litellm.acompletion
    projects = build_github_projects(dialogue)
    if not projects:
        return {}, {
            "version": DESCRIPTION_VERSION,
            "projects": 0,
            "described": 0,
            "batches": 0,
        }

    descriptions_by_id = {}
    batches = build_description_batches(projects)
    for batch in batches:
        request_items = [
            {
                "id": project["id"],
                "repo": project["repo"],
                "context": project["snippets"],
            }
            for project in batch
        ]
        response = await completion(
            model=model,
            messages=[
                {"role": "system", "content": DESCRIPTION_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        "为以下 GitHub 项目生成说明，只返回 JSON：\n"
                        + json.dumps(request_items, ensure_ascii=False)
                    ),
                },
            ],
            api_key=api_key,
            base_url=base_url,
            **completion_kwargs,
        )
        content = response.choices[0].message.content
        descriptions_by_id.update(
            parse_description_payload(
                content, {project["id"] for project in batch}
            )
        )

    descriptions_by_url = {}
    for project in projects:
        description = descriptions_by_id.get(project["id"], "")
        if description:
            descriptions_by_url[sanitize_url(project["url"])] = description

    return descriptions_by_url, {
        "version": DESCRIPTION_VERSION,
        "projects": len(projects),
        "described": len(descriptions_by_url),
        "batches": len(batches),
    }
