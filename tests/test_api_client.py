# tests/test_api_client.py
import pytest
import sys
import os
from unittest.mock import patch, MagicMock, AsyncMock

sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(__file__), "..", ".opencode/skills/analyze-messages/scripts"
    ),
)


def test_gemini_client_initialization():
    from api_client import GeminiClient

    client = GeminiClient(api_key="test_key", model="gemini-2.0-flash")
    assert client.model == "gemini-2.0-flash"


@pytest.mark.asyncio
async def test_score_messages_returns_structured_result():
    import aiohttp
    from api_client import GeminiClient

    client = GeminiClient(api_key="test_key")
    messages = [{"content": "分享一个Python教程", "timestamp": "2026-02-01T00:00:00Z"}]

    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.json = AsyncMock(
        return_value={
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "text": '{"summary": "test", "scores": [{"message_index": 0, "technical_share": 3, "resource_share": 0, "answer_question": 0, "deep_discussion": 0, "original_viewpoint": 0, "opportunity_share": 0, "interactive_reply": 0, "total_score": 3}], "highlights": []}'
                            }
                        ]
                    }
                }
            ]
        }
    )

    class MockResponse:
        async def __aenter__(self):
            return mock_response

        async def __aexit__(self, *args):
            pass

    class MockSession:
        def post(self, *args, **kwargs):
            return MockResponse()

    with patch.object(aiohttp.ClientSession, "post", return_value=MockResponse()):
        with patch.object(
            aiohttp.ClientSession, "__aenter__", AsyncMock(return_value=MockSession())
        ):
            with patch.object(
                aiohttp.ClientSession, "__aexit__", AsyncMock(return_value=None)
            ):
                result = await client.score_messages("wxid", "nickname", messages)
                assert result.summary == "test"
