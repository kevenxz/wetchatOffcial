from __future__ import annotations

import pytest

from workflow.nodes.run_research import run_research_node


def _long_body(topic: str, marker: str) -> str:
    """Topic-relevant extracted body that survives source filtering.

    ``marker`` is woven into every sentence so two bodies are genuinely different
    text; otherwise the near-duplicate gate would (correctly) collapse them. Real
    extractions are long and on-topic, unlike the single unrelated sentence these
    fixtures used before relevance and quality filtering existed.
    """
    sentences = [
        f"{marker}显示，{topic}的参与方在最近一个季度出现了调整，投入规模与落地场景同时变化。",
        f"根据{marker}披露的口径，{topic}的推进节奏明显快于去年同期，但统计标准尚未统一。",
        f"{marker}确认，{topic}的影响首先出现在供给端，随后才会传导到需求端与价格端。",
        f"从{marker}列举的案例看，{topic}正在从试点走向规模化，验证周期仍然偏长。",
        f"{marker}指出，{topic}的成本结构在过去半年发生调整，直接改变了下游的采购决策。",
        f"{marker}记录的反向信号表明，{topic}的商业化节奏仍存在分歧，风险集中在中游环节。",
        f"按照{marker}的表述，{topic}相关的政策口径趋严，不确定性因此有所上升。",
        f"{marker}强调，判断{topic}需要区分已经落地的交付结果与仍停留在预期的规划。",
        f"{marker}提供的对比数据显示，{topic}在不同区域的进展差异明显，不能一概而论。",
        f"结合{marker}与其它来源，{topic}的结论需要保留边界，避免把单点信息当成趋势。",
        f"{marker}提醒，{topic}接下来要观察的指标包括交付结果、成本变化与政策口径。",
        f"如果{marker}之外的来源出现相反证据，关于{topic}的判断就需要及时修正。",
    ]
    return "".join(sentences)


@pytest.mark.asyncio
async def test_run_research_builds_evidence_items_from_search_and_extract(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_search_web_node(state: dict) -> dict:
        assert state["search_queries"][0]["intent"] == "fact"
        return {
            "status": "running",
            "search_results": [
                {
                    "url": "https://example.com/report",
                    "title": "Example Report",
                    "snippet": "Robotics funding accelerated in 2026.",
                    "query": state["search_queries"][0]["query"],
                    "query_intent": "fact",
                    "domain": "example.com",
                    "source_type": "official",
                    "provider": "duckduckgo",
                    "authority_score": 0.95,
                    "final_score": 0.91,
                }
            ],
        }

    async def fake_fetch_extract_node(state: dict) -> dict:
        assert state["search_results"][0]["url"] == "https://example.com/report"
        return {
            "status": "running",
            "extracted_contents": [
                {
                    "url": "https://example.com/report",
                    "title": "Example Report",
                    "text": _long_body("机器人融资潮", "官方公告"),
                    "source_meta": {
                        "query": state["search_results"][0]["query"],
                        "query_intent": "fact",
                        "domain": "example.com",
                        "source_type": "official",
                        "provider": "duckduckgo",
                        "final_score": 0.91,
                    },
                }
            ],
        }

    monkeypatch.setattr("workflow.nodes.run_research.search_web_node", fake_search_web_node)
    monkeypatch.setattr("workflow.nodes.run_research.fetch_extract_node", fake_fetch_extract_node)

    state = {
        "task_id": "task-1",
        "task_brief": {"topic": "机器人融资潮"},
        "planning_state": {
            "search_plan": {
                "queries": [
                    {"angle": "fact", "query": "机器人融资潮 official announcement"},
                ]
            }
        },
        "research_state": {},
    }

    result = await run_research_node(state)
    evidence_items = result["research_state"]["evidence_items"]

    assert result["current_skill"] == "run_research"
    assert result["research_state"]["search_results"]
    assert result["research_state"]["extracted_contents"]
    assert evidence_items[0]["angle"] == "fact"
    assert evidence_items[0]["source_type"] == "official"
    assert evidence_items[0]["claim"]


@pytest.mark.asyncio
async def test_run_research_marks_low_authority_sources_for_caution(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_search_web_node(state: dict) -> dict:
        return {
            "status": "running",
            "search_results": [
                {
                    "url": "https://community.example.com/post",
                    "title": "Forum Post",
                    "snippet": "People are debating the robotics market.",
                    "query": state["search_queries"][0]["query"],
                    "query_intent": "opinion",
                    "domain": "community.example.com",
                    "source_type": "community",
                    "provider": "duckduckgo",
                    "authority_score": 0.41,
                    "final_score": 0.46,
                }
            ],
        }

    async def fake_fetch_extract_node(state: dict) -> dict:
        return {
            "status": "running",
            "extracted_contents": [
                {
                    "url": "https://community.example.com/post",
                    "title": "Forum Post",
                    "text": _long_body("机器人商业化", "社区讨论"),
                    "source_meta": {
                        "query": state["search_results"][0]["query"],
                        "query_intent": "opinion",
                        "domain": "community.example.com",
                        "source_type": "community",
                        "provider": "duckduckgo",
                        "authority_score": 0.41,
                        "final_score": 0.46,
                    },
                }
            ],
        }

    monkeypatch.setattr("workflow.nodes.run_research.search_web_node", fake_search_web_node)
    monkeypatch.setattr("workflow.nodes.run_research.fetch_extract_node", fake_fetch_extract_node)

    state = {
        "task_id": "task-2",
        "task_brief": {"topic": "机器人商业化"},
        "planning_state": {"search_plan": {"queries": [{"angle": "opinion", "query": "机器人商业化 expert opinion"}]}},
        "research_state": {},
    }

    result = await run_research_node(state)
    evidence_item = result["research_state"]["evidence_items"][0]

    assert evidence_item["needs_caution"] is True
    assert evidence_item["evidence_score"] < 0.6


@pytest.mark.asyncio
async def test_run_research_batches_queries_and_aggregates_results(monkeypatch: pytest.MonkeyPatch) -> None:
    search_calls: list[list[dict]] = []
    extract_calls: list[list[dict]] = []

    async def fake_search_web_node(state: dict) -> dict:
        search_calls.append(list(state["search_queries"]))
        query = state["search_queries"][0]["query"]
        intent = state["search_queries"][0]["intent"]
        suffix = "fact" if intent == "fact" else "data"
        return {
            "status": "running",
            "search_results": [
                {
                    "url": f"https://example.com/{suffix}",
                    "title": f"{suffix.title()} Source",
                    "snippet": f"{suffix} evidence for robotics market.",
                    "query": query,
                    "query_intent": intent,
                    "domain": "example.com",
                    "source_type": "official" if intent == "fact" else "dataset",
                    "provider": "duckduckgo",
                    "authority_score": 0.92,
                    "final_score": 0.88,
                }
            ],
        }

    async def fake_fetch_extract_node(state: dict) -> dict:
        extract_calls.append(list(state["search_results"]))
        extracted_contents = []
        for item in state["search_results"]:
            extracted_contents.append(
                {
                    "url": item["url"],
                    "title": item["title"],
                    "text": _long_body("机器人市场", f"{item['query_intent']} {item['title']}"),
                    "source_meta": {
                        "query": item["query"],
                        "query_intent": item["query_intent"],
                        "domain": item["domain"],
                        "source_type": item["source_type"],
                        "provider": item["provider"],
                        "authority_score": item["authority_score"],
                        "final_score": item["final_score"],
                    },
                }
            )
        return {
            "status": "running",
            "extracted_contents": extracted_contents,
        }

    monkeypatch.setattr("workflow.nodes.run_research.search_web_node", fake_search_web_node)
    monkeypatch.setattr("workflow.nodes.run_research.fetch_extract_node", fake_fetch_extract_node)

    state = {
        "task_id": "task-3",
        "task_brief": {"topic": "机器人市场"},
        "planning_state": {
            "search_plan": {
                "queries": [
                    {"angle": "fact", "query": "机器人市场 official announcement"},
                    {"angle": "data", "query": "机器人市场 statistics benchmark"},
                ]
            }
        },
        "research_state": {},
    }

    result = await run_research_node(state)

    assert len(search_calls) == 2
    assert len(extract_calls) == 2
    assert len(result["research_state"]["search_results"]) == 2
    assert len(result["research_state"]["extracted_contents"]) == 2
    evidence_items = result["research_state"]["evidence_items"]
    assert {item["angle"] for item in evidence_items} == {"fact", "data"}
    assert {item["query"] for item in evidence_items} == {
        "机器人市场 official announcement",
        "机器人市场 statistics benchmark",
    }


@pytest.mark.asyncio
async def test_run_research_continues_with_evaluator_next_queries(monkeypatch: pytest.MonkeyPatch) -> None:
    search_calls: list[str] = []

    async def fake_search_web_node(state: dict) -> dict:
        query = state["search_queries"][0]["query"]
        search_calls.append(query)
        source_type = "official" if "官方" in query else "media"
        return {
            "status": "running",
            "search_results": [
                {
                    "url": f"https://example.com/{len(search_calls)}",
                    "title": f"Source {len(search_calls)}",
                    "snippet": "AI 模型在 2026 发布，存在成本和隐私风险。",
                    "query": query,
                    "query_intent": state["search_queries"][0]["intent"],
                    "domain": f"example{len(search_calls)}.com",
                    "source_type": source_type,
                    "provider": "duckduckgo",
                    "authority_score": 0.92,
                    "final_score": 0.88,
                }
            ],
        }

    async def fake_fetch_extract_node(state: dict) -> dict:
        item = state["search_results"][0]
        return {
            "status": "running",
            "extracted_contents": [
                {
                    "url": item["url"],
                    "title": item["title"],
                    "text": f"{item['snippet']} Expanded evidence.",
                    "source_meta": {
                        "query": item["query"],
                        "query_intent": item["query_intent"],
                        "domain": item["domain"],
                        "source_type": item["source_type"],
                        "provider": item["provider"],
                        "authority_score": item["authority_score"],
                        "final_score": item["final_score"],
                    },
                }
            ],
        }

    monkeypatch.setattr("workflow.nodes.run_research.search_web_node", fake_search_web_node)
    monkeypatch.setattr("workflow.nodes.run_research.fetch_extract_node", fake_fetch_extract_node)

    state = {
        "task_id": "task-multi-round",
        "task_brief": {"topic": "AI 新模型发布"},
        "planning_state": {
            "search_contract": {
                "topic": "AI 新模型发布",
                "search_depth": "standard",
                "query_plan": [{"query": "AI 新模型 解读", "source_type": "media", "priority": 1}],
                "min_source_count": 2,
                "min_authoritative_source_count": 1,
                "min_cross_source_count": 2,
                "require_opposing_view": True,
            },
            "search_plan": {"queries": [{"angle": "media", "query": "AI 新模型 解读"}]},
        },
        "research_state": {},
    }

    result = await run_research_node(state)

    assert len(result["research_state"]["search_runs"]) >= 2
    assert any("官方" in query for query in search_calls)
    assert result["research_state"]["search_evaluation"]["decision"] in {"enough", "manual_review_required"}
