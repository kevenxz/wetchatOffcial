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
