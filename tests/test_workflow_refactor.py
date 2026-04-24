import pytest

from workflow.config import build_config_snapshot
from workflow.skills.assemble_article import assemble_article_node


def test_build_config_snapshot_normalizes_workflow_policies():
    snapshot = build_config_snapshot(
        generation_config={
            "audience_roles": ["AI 产品经理"],
            "account_profile": {"positioning": "enterprise AI", "fit_tags": ["AI", "AI"]},
            "content_template": {"template_id": "deep-dive", "article_length": "long"},
            "review_policy": {"strictness": "strict", "max_revision_rounds": 8},
            "image_policy": {"inline_count": 9, "brand_colors": ["#000", "#000"]},
            "publish_policy": {"auto_publish_to_draft": True},
        },
        hotspot_capture_config={"enabled": True},
        skip_auto_push=True,
    )

    assert snapshot["mode"] == "auto_hotspot"
    assert snapshot["generation"]["audience_roles"] == ["AI 产品经理"]
    assert snapshot["account_profile"]["fit_tags"] == ["AI"]
    assert snapshot["content_template"]["template_id"] == "deep-dive"
    assert snapshot["review_policy"]["strictness"] == "strict"
    assert snapshot["review_policy"]["max_revision_rounds"] == 3
    assert snapshot["image_policy"]["inline_count"] == 4
    assert snapshot["image_policy"]["brand_colors"] == ["#000"]
    assert snapshot["publish_policy"]["auto_publish_to_draft"] is False


@pytest.mark.asyncio
async def test_assemble_article_merges_visual_assets_and_requires_review():
    result = await assemble_article_node(
        {
            "generated_article": {"title": "Title", "content": "Body"},
            "visual_state": {
                "assets": [
                    {"role": "cover", "url": "https://example.com/cover.png"},
                    {"role": "inline", "path": "/tmp/inline.png"},
                ]
            },
            "quality_state": {
                "next_action": "human_review",
                "quality_report": {"blocking_reasons": ["article_score_below_threshold"]},
            },
            "config_snapshot": {
                "review_policy": {"require_human_review": False},
                "publish_policy": {"auto_publish_to_draft": True},
            },
            "skip_auto_push": False,
            "selected_topic": {"title": "Selected topic"},
            "selected_hotspot": {"title": "Hotspot"},
        }
    )

    final_article = result["final_article"]
    assert final_article["cover_image"] == "https://example.com/cover.png"
    assert final_article["illustrations"] == ["/tmp/inline.png"]
    assert final_article["selected_topic"]["title"] == "Selected topic"
    assert result["human_review_required"] is True
    assert result["quality_state"]["publish_decision"]["next_step"] == "human_review"
