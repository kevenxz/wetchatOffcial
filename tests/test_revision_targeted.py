"""Tests for targeted revision behaviour in the writing stage."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from workflow import runtime_settings
from workflow.agents.writer import compose_draft_node


def _valid_content(*, first_heading: str = "## 变化信号") -> str:
    """A draft body that already satisfies every quality rule."""
    return "\n\n".join(
        [
            "开头给出判断，先说明变化已经发生。" * 10,
            f"{first_heading}\n\n" + "第一段说明已确认的事实与数据。" * 10,
            "## 风险边界\n\n" + "第二段说明判断成立的条件与不确定处。" * 10,
            "## 接下来看什么\n\n" + "第三段给出后续观察指标。" * 10,
            "结尾回扣判断，不复述全文。" * 10,
        ]
    )


def _state(revision_brief: dict | None = None) -> dict:
    return {
        "task_id": "task-revision",
        "keywords": "机器人融资潮",
        "task_brief": {"topic": "机器人融资潮"},
        "planning_state": {"article_type": {"type_id": "trend_analysis"}, "article_blueprint": {}},
        "research_state": {"evidence_pack": {"confirmed_facts": [{"claim": "融资升温"}]}},
        "config_snapshot": {"content_template": {"article_length": "short"}},
        "writing_state": {
            "draft": {
                "title": "上一稿标题",
                "content": "上一稿正文内容，用于验证返工是否携带历史稿件。" * 6,
                "summary": "上一稿摘要",
                "alt_titles": ["备选一"],
            },
            **({"revision_brief": revision_brief} if revision_brief else {}),
        },
    }


def _mock_chain(result: dict) -> tuple[MagicMock, MagicMock]:
    chain = MagicMock()
    chain.ainvoke = AsyncMock(return_value=result)
    prompt = MagicMock()
    prompt.__or__ = MagicMock(return_value=chain)
    return prompt, chain


async def _run(state: dict, result: dict) -> tuple[MagicMock, MagicMock]:
    prompt, chain = _mock_chain(result)
    with patch("workflow.model_factory.build_chat_model") as mock_build:
        with patch("workflow.agents.writer.ChatPromptTemplate") as mock_prompt_class:
            mock_build.return_value = MagicMock()
            mock_prompt_class.from_messages.return_value = prompt
            await compose_draft_node(state)
    return mock_build, chain


@pytest.mark.asyncio
async def test_revision_sends_previous_draft_and_violations_to_the_model() -> None:
    _build, chain = await _run(
        _state(
            {
                "mode": "targeted_revision",
                "guidance": ["补充数据依据"],
                "findings": [{"type": "evidence", "message": "结论支撑不足"}],
            }
        ),
        {"title": "修订后的标题", "content": _valid_content(), "summary": "修订摘要", "alt_titles": []},
    )

    first_payload = chain.ainvoke.await_args_list[0].args[0]
    assert first_payload["previous_draft"]["title"] == "上一稿标题"
    assert first_payload["draft_violations"] == ["补充数据依据"]


@pytest.mark.asyncio
async def test_revision_uses_a_smaller_token_budget() -> None:
    mock_build, _chain = await _run(
        _state({"mode": "targeted_revision", "guidance": ["补充数据依据"]}),
        {"title": "t", "content": _valid_content(), "summary": "s", "alt_titles": []},
    )

    # A targeted revision edits an existing draft, so it gets its own (smaller) budget,
    # configured via LLM_MAX_TOKENS_DRAFT_REVISION. The budget is then widened for the
    # tier the stage actually runs on (see runtime_settings.budget_for_tier).
    assert mock_build.call_args.kwargs["max_tokens"] == runtime_settings.budget_for_tier(
        "compose_draft_revision", "strong"
    )


@pytest.mark.asyncio
async def test_first_pass_uses_the_full_token_budget_without_previous_draft() -> None:
    mock_build, chain = await _run(
        _state(),
        {"title": "t", "content": _valid_content(), "summary": "s", "alt_titles": []},
    )

    assert mock_build.call_args.kwargs["max_tokens"] == runtime_settings.budget_for_tier(
        "compose_draft", "strong"
    )
    first_payload = chain.ainvoke.await_args_list[0].args[0]
    assert first_payload["previous_draft"] == {}
    assert first_payload["draft_violations"] == []


@pytest.mark.asyncio
async def test_mechanical_violations_are_repaired_without_a_second_generation() -> None:
    """A leaked source heading must not cost a full extra LLM generation."""
    _build, chain = await _run(
        _state(),
        {
            "title": "标题",
            "content": _valid_content(first_heading="## https://example.com/raw-source-title"),
            "summary": "摘要",
            "alt_titles": [],
        },
    )

    assert chain.ainvoke.await_count == 1, "a mechanical defect triggered a second generation"


@pytest.mark.asyncio
async def test_content_level_violations_still_escalate_to_the_model() -> None:
    """A draft that is simply too thin still deserves a repair generation."""
    _build, chain = await _run(
        _state(),
        {"title": "标题", "content": "太短了。", "summary": "摘要", "alt_titles": []},
    )

    assert chain.ainvoke.await_count >= 2
