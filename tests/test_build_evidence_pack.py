from workflow.utils.evidence_pack import build_evidence_pack


def test_build_evidence_pack_groups_items_by_usage() -> None:
    items = [
        {"angle": "fact", "claim": "A", "source_type": "official"},
        {"angle": "data", "claim": "B", "source_type": "dataset"},
        {"angle": "case", "claim": "C", "source_type": "news"},
    ]

    pack = build_evidence_pack(items)

    assert pack["confirmed_facts"]
    assert pack["usable_data_points"]
    assert pack["usable_cases"]


def test_build_evidence_pack_includes_quality_summary_and_research_gaps() -> None:
    items = [
        {"angle": "fact", "claim": "A", "source_type": "official", "evidence_score": 0.91},
        {"angle": "opinion", "claim": "B", "source_type": "community", "evidence_score": 0.42, "needs_caution": True},
    ]

    pack = build_evidence_pack(items)

    assert pack["quality_summary"]["total_items"] == 2
    assert pack["quality_summary"]["high_confidence_items"] == 1
    assert pack["quality_summary"]["caution_items"] == 1
    assert "missing_data_evidence" in pack["research_gaps"]
