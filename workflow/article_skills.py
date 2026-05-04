"""Article skill registry used by planner and drafting agents."""
from __future__ import annotations

from typing import Any


ARTICLE_SKILLS: dict[str, dict[str, Any]] = {
    "general_tech_explainer": {
        "skill_id": "general_tech_explainer",
        "name": "\u901a\u7528\u79d1\u6280\u89e3\u8bfb",
        "description": "General technology explainer for public-account articles.",
        "activation_keywords": [
            "\u79d1\u6280",
            "AI",
            "\u5927\u6a21\u578b",
            "\u82af\u7247",
            "\u673a\u5668\u4eba",
            "\u4ea7\u54c1",
            "\u6280\u672f",
        ],
        "decision_rule": "Use when no more specific vertical article skill matches.",
        "framework": "Define why the event matters, then explain drivers, evidence, scenes, and risk boundaries.",
        "tone": "Professional, restrained, clear, and non-promotional.",
        "title_guidance": "Highlight the core change, technical boundary, or reader-facing judgment.",
        "opening_guidance": "Explain why the topic matters now, then provide the article's core judgment.",
        "section_guidance": [
            "Clarify the core event or technical change first.",
            "Use evidence, drivers, and cases to support the judgment.",
            "Keep a risk-boundary or next-observation section.",
        ],
        "evidence_policy": "Prefer official materials, papers, technical docs, industry data, and verifiable cases.",
        "writing_constraints": [
            "Do not stack jargon without explanation.",
            "Do not turn a single source into a firm conclusion.",
            "Every major judgment needs evidence or an explicit evidence boundary.",
        ],
        "visual_style": "Modern technology style, clear diagrams first, avoid exaggerated sci-fi posters.",
    },
    "quantum_tech_explainer": {
        "skill_id": "quantum_tech_explainer",
        "name": "\u91cf\u5b50\u79d1\u6280\u6df1\u5ea6\u89e3\u8bfb",
        "description": "Specialized skill for quantum computing, communication, chips, error correction, algorithms, and commercialization.",
        "activation_keywords": [
            "\u91cf\u5b50",
            "quantum",
            "qubit",
            "\u91cf\u5b50\u8ba1\u7b97",
            "\u91cf\u5b50\u901a\u4fe1",
            "\u91cf\u5b50\u82af\u7247",
            "\u91cf\u5b50\u7ea0\u9519",
            "\u91cf\u5b50\u7b97\u6cd5",
            "\u91cf\u5b50\u79d1\u6280",
            "\u91cf\u5b50\u7ea0\u7f20",
        ],
        "decision_rule": "Use when the topic, hotspot, source material, or style hint mentions quantum technology.",
        "framework": "Explain the scientific concept, then cover engineering progress, industrial value, verification metrics, and risk boundaries.",
        "tone": "Calm, rational, future-facing, and evidence-bounded; never turn a research result into immediate commercialization.",
        "title_guidance": "Highlight real progress, capability boundaries, industrial signals, or common misunderstandings in quantum technology.",
        "opening_guidance": "Start by correcting one common misunderstanding, then state the metric that actually matters.",
        "section_guidance": [
            "Explain the core quantum concept with an accurate analogy.",
            "Describe the real change in hardware, algorithms, error correction, communication links, or engineering metrics.",
            "Connect the progress to security communication, drug simulation, material computing, optimization, or compute infrastructure.",
            "State the evidence boundary: lab metrics, scalability, cost, stability, and commercialization cycle.",
        ],
        "evidence_policy": "Prefer papers, official releases, experimental metrics, technical roadmaps, and authoritative institutions; cross-check media reports.",
        "writing_constraints": [
            "Distinguish scientific principle, engineering prototype, and commercial product.",
            "Explain terms such as qubit, error correction, coherence time, and fidelity with a Chinese explanation and analogy.",
            "Avoid quantum mysticism, 'disrupt everything', or 'immediately replaces classical computing' claims.",
            "Keep uncertainty and validation conditions in the conclusion.",
        ],
        "visual_style": "Dark technology background, blue-purple cold light, quantum circuits, chip texture, and wave-function motifs.",
    },
}


DEFAULT_ARTICLE_SKILL_ID = "general_tech_explainer"


def list_article_skills() -> list[dict[str, Any]]:
    """Return the skill catalog as planner-visible metadata."""
    return [dict(skill) for skill in ARTICLE_SKILLS.values()]


def get_article_skill(skill_id: str | None) -> dict[str, Any]:
    """Return one article skill with a safe fallback."""
    return dict(ARTICLE_SKILLS.get(str(skill_id or ""), ARTICLE_SKILLS[DEFAULT_ARTICLE_SKILL_ID]))


def _skill_score(skill: dict[str, Any], text: str) -> int:
    lowered = text.lower()
    score = 0
    for keyword in list(skill.get("activation_keywords") or []):
        token = str(keyword).strip()
        if token and token.lower() in lowered:
            score += 3 if len(token) > 2 else 1
    return score


def select_article_skill(context: dict[str, Any]) -> dict[str, Any]:
    """Select the best article skill from planner context."""
    text_parts = [
        context.get("topic"),
        context.get("article_goal"),
        context.get("style_hint"),
        " ".join(str(item) for item in list(context.get("audience_roles") or [])),
        " ".join(str(item) for item in list(context.get("hotspot_titles") or [])),
    ]
    text = " ".join(str(item or "") for item in text_parts)
    scored = sorted(
        ((_skill_score(skill, text), skill) for skill in ARTICLE_SKILLS.values()),
        key=lambda item: item[0],
        reverse=True,
    )
    if not scored or scored[0][0] <= 0:
        selected = get_article_skill(DEFAULT_ARTICLE_SKILL_ID)
        selected["selection_reason"] = "no_specific_skill_matched"
        return selected
    selected = dict(scored[0][1])
    selected["selection_reason"] = "keyword_match"
    selected["selection_score"] = scored[0][0]
    return selected
