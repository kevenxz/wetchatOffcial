from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from workflow.skills.push_to_draft import push_to_draft_node


@pytest.mark.asyncio
async def test_push_to_draft_uses_generated_article_with_visual_assets() -> None:
    state = {
        "task_id": "task-push-1",
        "generated_article": {
            "title": "机器人商业化进入验证期",
            "content": "正文",
        },
        "visual_state": {
            "assets": [
                {"role": "cover", "url": "https://img.example.com/cover.png"},
                {"role": "infographic", "url": "https://img.example.com/info.png"},
            ]
        },
    }

    with patch("workflow.skills.push_to_draft.os.getenv", side_effect=lambda key: {"WECHAT_APP_ID": "appid", "WECHAT_APP_SECRET": "secret"}.get(key)):
        with patch("workflow.skills.push_to_draft.push_article_to_wechat_draft", new=AsyncMock(return_value={"media_id": "media-1", "url": ""})) as mock_push:
            result = await push_to_draft_node(state)

    article = mock_push.await_args.kwargs["article"]
    assert article["cover_image"] == "https://img.example.com/cover.png"
    assert article["illustrations"] == ["https://img.example.com/info.png"]
    assert article["visual_assets"][0]["url"] == "https://img.example.com/cover.png"
    assert result["draft_info"]["media_id"] == "media-1"
