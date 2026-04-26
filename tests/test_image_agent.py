from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from workflow.skills.image_agent import image_agent_node


@pytest.mark.asyncio
async def test_image_agent_wraps_generate_visual_assets_node() -> None:
    with patch("workflow.skills.image_agent.generate_visual_assets_node", new_callable=AsyncMock) as mock_generate:
        mock_generate.return_value = {
            "status": "running",
            "current_skill": "generate_visual_assets",
            "progress": 74,
            "visual_state": {
                "image_briefs": [{"role": "cover"}],
                "assets": [{"role": "cover", "url": "https://img.example.com/cover.png"}],
            },
            "generated_article": {"title": "Title"},
        }

        result = await image_agent_node({"task_id": "task-image"})

    assert result["current_skill"] == "image_agent"
    assert result["visual_state"]["agent"]["name"] == "image_agent"
    assert result["visual_state"]["agent"]["brief_count"] == 1
    assert result["visual_state"]["agent"]["asset_count"] == 1
