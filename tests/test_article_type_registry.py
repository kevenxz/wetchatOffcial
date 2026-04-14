from workflow.utils.article_type_registry import get_article_type_registry


def test_article_type_registry_includes_multiple_formal_types() -> None:
    registry = get_article_type_registry()
    assert "hotspot_interpretation" in registry
    assert "trend_analysis" in registry
    assert registry["quick_news"]["title_style"] == "fast_and_clear"
