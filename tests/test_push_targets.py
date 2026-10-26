"""Tests for account-bound draft pushing."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from api.models import AccountConfig, PlatformType
from workflow.tools.wechat_draft import push_to_draft_node


def _account(account_id: str = "acc-1", *, enabled: bool = True) -> AccountConfig:
    return AccountConfig(
        account_id=account_id,
        name=f"账号{account_id}",
        platform=PlatformType.wechat_mp,
        app_id=f"appid-{account_id}",
        app_secret=f"secret-{account_id}",
        enabled=enabled,
        created_at=datetime.now(tz=timezone.utc),
    )


def _state(**overrides) -> dict:
    base = {
        "task_id": "task-push",
        "generated_article": {
            "title": "标题",
            "content": "正文",
            "cover_image": "https://example.com/cover.png",
        },
        "visual_state": {},
        "config_snapshot": {"publish_policy": {"auto_publish": False}},
        "publish_targets": [{"account_id": "acc-1", "platform": "wechat_mp"}],
    }
    base.update(overrides)
    return base


@pytest.mark.asyncio
async def test_bound_account_is_used_instead_of_environment_credentials() -> None:
    with patch("workflow.tools.wechat_draft.get_account", return_value=_account()):
        with patch(
            "workflow.tools.wechat_draft.push_article_to_wechat_draft",
            new=AsyncMock(return_value={"media_id": "media-1", "publish_status": "draft_only"}),
        ) as mock_push:
            result = await push_to_draft_node(_state())

    kwargs = mock_push.await_args.kwargs
    assert kwargs["app_id"] == "appid-acc-1"
    assert kwargs["app_secret"] == "secret-acc-1"
    assert result["draft_info"]["media_id"] == "media-1"
    record = result["publish_records"][0]
    assert record["account_id"] == "acc-1"
    assert record["status"] == "success"
    assert record["publish_status"] == "draft_only"


@pytest.mark.asyncio
async def test_auto_publish_policy_is_forwarded_to_the_service() -> None:
    state = _state(
        config_snapshot={
            "publish_policy": {
                "auto_publish": True,
                "publish_poll_interval_seconds": 2,
                "publish_poll_max_attempts": 4,
            }
        }
    )

    with patch("workflow.tools.wechat_draft.get_account", return_value=_account()):
        with patch(
            "workflow.tools.wechat_draft.push_article_to_wechat_draft",
            new=AsyncMock(return_value={"media_id": "m", "publish_status": "published", "publish_id": "p-1"}),
        ) as mock_push:
            result = await push_to_draft_node(state)

    kwargs = mock_push.await_args.kwargs
    assert kwargs["auto_publish"] is True
    assert kwargs["publish_poll_interval_seconds"] == 2
    assert kwargs["publish_poll_max_attempts"] == 4
    assert result["publish_records"][0]["publish_status"] == "published"
    assert result["publish_records"][0]["publish_id"] == "p-1"


@pytest.mark.asyncio
async def test_disabled_account_is_skipped_and_falls_back_to_mock() -> None:
    with patch("workflow.tools.wechat_draft.get_account", return_value=_account(enabled=False)):
        with patch.dict("os.environ", {}, clear=True):
            result = await push_to_draft_node(_state())

    assert result["draft_info"]["mock"] is True
    assert result["publish_records"][0]["account_name"] == "env_fallback"


@pytest.mark.asyncio
async def test_mock_draft_is_explicitly_marked() -> None:
    state = _state(publish_targets=[])

    with patch.dict("os.environ", {}, clear=True):
        result = await push_to_draft_node(state)

    draft_info = result["draft_info"]
    assert draft_info["mock"] is True
    assert draft_info["source"] == "mock"
    # Operators must be able to tell a mock result apart from a real delivery.
    assert result["publish_records"][0]["draft_info"]["mock"] is True


@pytest.mark.asyncio
async def test_environment_fallback_is_marked_as_such() -> None:
    state = _state(publish_targets=[])
    env = {"WECHAT_APP_ID": "env-appid", "WECHAT_APP_SECRET": "env-secret"}

    with patch.dict("os.environ", env, clear=True):
        with patch(
            "workflow.tools.wechat_draft.push_article_to_wechat_draft",
            new=AsyncMock(return_value={"media_id": "env-media", "publish_status": "draft_only"}),
        ):
            result = await push_to_draft_node(state)

    assert result["draft_info"]["source"] == "env_fallback"
    assert result["publish_records"][0]["account_name"] == "env_fallback"


@pytest.mark.asyncio
async def test_one_failing_account_does_not_block_the_other() -> None:
    state = _state(
        publish_targets=[
            {"account_id": "acc-1", "platform": "wechat_mp"},
            {"account_id": "acc-2", "platform": "wechat_mp"},
        ]
    )

    async def fake_push(*, app_id: str, **kwargs):
        if app_id == "appid-acc-1":
            raise RuntimeError("wechat rejected the draft")
        return {"media_id": "media-2", "publish_status": "draft_only"}

    with patch("workflow.tools.wechat_draft.get_account", side_effect=lambda aid: _account(aid)):
        with patch("workflow.tools.wechat_draft.push_article_to_wechat_draft", side_effect=fake_push):
            result = await push_to_draft_node(state)

    statuses = {record["account_id"]: record["status"] for record in result["publish_records"]}
    assert statuses == {"acc-1": "failed", "acc-2": "success"}
    assert result["draft_info"]["media_id"] == "media-2"


@pytest.mark.asyncio
async def test_all_accounts_failing_marks_the_node_failed() -> None:
    state = _state(publish_targets=[{"account_id": "acc-1", "platform": "wechat_mp"}])

    with patch("workflow.tools.wechat_draft.get_account", return_value=_account()):
        with patch(
            "workflow.tools.wechat_draft.push_article_to_wechat_draft",
            new=AsyncMock(side_effect=RuntimeError("cover upload failed")),
        ):
            result = await push_to_draft_node(state)

    assert result["status"] == "failed"
    assert "failed" in result["error"]
    assert result["publish_records"][0]["status"] == "failed"
