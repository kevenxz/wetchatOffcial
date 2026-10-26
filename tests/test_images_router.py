"""Tests for the generated-image listing API.

The 「图片管理」page was an eleven-line placeholder and there was no endpoint at all, so
~90 generated pictures sat on disk with no way to review them — the reason nobody could
tell that the images did not match their articles.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.models import TaskResponse
from api.store import task_store
from workflow.utils.image_styles import STYLE_IDS


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture()
def seeded_task() -> Any:
    """A task with one good asset and one failed (placeholder) asset."""
    task_id = "task-images-test"
    task = TaskResponse(
        task_id=task_id,
        keywords="GPT-6 免费开放",
        status="done",
        created_at=datetime(2026, 10, 9, 12, 0, tzinfo=timezone.utc),
        final_article={"title": "GPT-6 免费开放"},
        visual_state={
            "style_id": "editorial_photo",
            "image_briefs": [
                {"role": "cover", "visual_spec": {"subject": "A laptop on a desk", "section_link": "thesis"}},
                {"role": "data_scene", "visual_spec": {"subject": "Rack status lights"}},
            ],
            "assets": [
                {
                    "role": "cover",
                    "url": "",
                    "path": "artifacts/generated_images/task-images-test_cover_1.png",
                    "prompt": "Editorial photograph. A laptop on a desk. No text, letters, numbers, logos, or watermarks anywhere in the image.",
                },
                {
                    "role": "data_scene",
                    "url": "",
                    "path": "generated://data_scene",
                    "prompt": "Editorial photograph. Rack status lights. No text.",
                },
            ],
            "visual_review": {"check": "structural_only", "missing": ["data_scene"]},
        },
    )
    task_store[task_id] = task
    yield task_id
    task_store.pop(task_id, None)


def test_lists_style_presets_matching_the_backend_catalogue(client: TestClient) -> None:
    response = client.get("/api/images/styles")

    assert response.status_code == 200
    items = response.json()["items"]
    assert {item["style_id"] for item in items} == set(STYLE_IDS)
    assert all(item["name"] for item in items)


def test_lists_assets_with_their_prompt_and_visual_spec(client: TestClient, seeded_task: str) -> None:
    response = client.get(f"/api/images?task_id={seeded_task}")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2

    cover = next(item for item in body["items"] if item["role"] == "cover")
    assert cover["generated"] is True
    assert cover["degraded"] is False
    # The prompt is what makes the page an audit surface.
    assert "A laptop on a desk" in cover["prompt"]
    assert cover["visual_spec"]["subject"] == "A laptop on a desk"
    assert cover["style_id"] == "editorial_photo"
    assert cover["article_title"] == "GPT-6 免费开放"
    assert cover["created_at"].startswith("2026-10-09")


def test_local_artifact_path_becomes_a_browser_reachable_url(client: TestClient, seeded_task: str) -> None:
    """`artifacts/` is mounted at `/artifacts`, so the thumbnail needs the mounted form."""
    body = client.get(f"/api/images?task_id={seeded_task}").json()
    cover = next(item for item in body["items"] if item["role"] == "cover")

    assert cover["ref"] == "/artifacts/generated_images/task-images-test_cover_1.png"


def test_placeholder_assets_are_flagged_degraded_and_have_no_ref(client: TestClient, seeded_task: str) -> None:
    """The failed generation must be visible — the old review passed it silently."""
    body = client.get(f"/api/images?task_id={seeded_task}").json()
    failed = next(item for item in body["items"] if item["role"] == "data_scene")

    assert failed["generated"] is False
    assert failed["degraded"] is True
    assert failed["ref"] == ""


def test_degraded_only_filter_returns_just_the_failures(client: TestClient, seeded_task: str) -> None:
    body = client.get(f"/api/images?task_id={seeded_task}&degraded_only=true").json()

    assert body["total"] == 1
    assert body["items"][0]["role"] == "data_scene"


def test_pagination_reports_the_full_total(client: TestClient, seeded_task: str) -> None:
    body = client.get(f"/api/images?task_id={seeded_task}&limit=1&offset=0").json()

    assert body["total"] == 2
    assert len(body["items"]) == 1
    assert body["limit"] == 1


def test_unknown_task_returns_an_empty_list(client: TestClient) -> None:
    body = client.get("/api/images?task_id=does-not-exist").json()

    assert body["total"] == 0
    assert body["items"] == []


def test_tasks_without_visual_state_are_skipped(client: TestClient) -> None:
    task_id = "task-no-visuals"
    task_store[task_id] = TaskResponse(
        task_id=task_id,
        keywords="无配图任务",
        status="done",
        created_at=datetime(2026, 10, 9, 11, 0, tzinfo=timezone.utc),
    )
    try:
        body = client.get(f"/api/images?task_id={task_id}").json()
        assert body["total"] == 0
    finally:
        task_store.pop(task_id, None)
