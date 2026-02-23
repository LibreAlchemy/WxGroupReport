"""
Google Gemini API 客户端
"""

import json
import os
import re
from dataclasses import dataclass
from typing import List, Dict, Any, Optional

try:
    import aiohttp
except ImportError:
    aiohttp = None

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None


GEMINI_API_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
)


@dataclass
class ScoreResult:
    summary: str
    scores: List[Dict[str, Any]]
    highlights: List[Dict[str, Any]]


class GeminiClient:
    def __init__(self, api_key: Optional[str] = None, model: str = "gemini-2.0-flash"):
        self.api_key = api_key or os.getenv("GOOGLE_API_KEY") or os.getenv("API_KEY")
        self.model = model
        self.api_url = GEMINI_API_URL.format(model=model)

    def _build_prompt(self, wxid: str, nickname: str, messages: List[Dict]) -> str:
        messages_text = "\n".join(
            [
                f"{i}. [{msg.get('timestamp', '')}] {msg.get('content', '')}"
                for i, msg in enumerate(messages)
            ]
        )

        return f"""## 任务
请分析以下群成员的消息，进行总结并评分。

## 成员信息
- wxid: {wxid}
- 昵称: {nickname}
- 消息数: {len(messages)}

## 消息列表
{messages_text}

## 输出格式 (JSON，严格返回)
{{
  "summary": "成员发言总结（50-200字）",
  "scores": [
    {{
      "message_index": 0,
      "technical_share": 3,
      "resource_share": 0,
      "answer_question": 0,
      "deep_discussion": 0,
      "original_viewpoint": 0,
      "opportunity_share": 0,
      "interactive_reply": 2,
      "total_score": 5
    }}
  ],
  "highlights": [
    {{
      "type": "article|github|insight|opportunity",
      "content": "内容摘要",
      "url": "链接（如果有）",
      "message_index": 0
    }}
  ]
}}
严格返回 JSON，不要包含其他内容。"""

    async def score_messages(
        self, wxid: str, nickname: str, messages: List[Dict]
    ) -> ScoreResult:
        """调用 Gemini API 评分消息"""
        if not messages:
            return ScoreResult(summary="无消息", scores=[], highlights=[])

        prompt = self._build_prompt(wxid, nickname, messages)

        if aiohttp is None:
            raise ImportError("aiohttp is required. Install: pip install aiohttp")

        url = f"{self.api_url}?key={self.api_key}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.3,
                "maxOutputTokens": 4096,
            },
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise RuntimeError(f"API error: {response.status} - {error_text}")

                result = await response.json()
                text = result["candidates"][0]["content"]["parts"][0]["text"]
                return self._parse_response(text)

    def _parse_response(self, text: str) -> ScoreResult:
        """解析 API 响应"""
        json_match = re.search(r"\{[\s\S]*\}", text)
        if not json_match:
            raise ValueError(f"Cannot parse JSON from response: {text[:200]}")

        data = json.loads(json_match.group())
        return ScoreResult(
            summary=data.get("summary", ""),
            scores=data.get("scores", []),
            highlights=data.get("highlights", []),
        )


def create_client() -> GeminiClient:
    """创建 Gemini 客户端"""
    return GeminiClient()
