"""Helpers for multi-angle research query planning."""
from __future__ import annotations


def build_research_queries(topic: str, angles: list[str]) -> list[dict[str, str]]:
    """Build one query per supported research angle."""
    mapping = {
        "fact": f"{topic} official announcement OR official blog OR documentation",
        "news": f"{topic} latest news analysis",
        "opinion": f"{topic} expert opinion controversy",
        "case": f"{topic} company case study use case",
        "data": f"{topic} statistics benchmark trend data",
    }
    return [{"angle": angle, "query": mapping[angle]} for angle in angles if angle in mapping]
