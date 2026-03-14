"""工作流状态定义。"""
from __future__ import annotations

from typing import Optional
from typing_extensions import TypedDict


class WorkflowState(TypedDict):
    """LangGraph 工作流全局状态。"""

    task_id: str
    """任务唯一 ID。"""

    keywords: str
    """用户输入的关键词。"""

    search_results: list[str]
    """搜索到的 URL 列表（最多 10 条）。"""

    extracted_contents: list[dict]
    """每个 URL 提取的内容：{url, title, text, images}。"""

    generated_article: dict
    """生成的文章：{title, alt_titles, content, cover_image, illustrations}。"""

    draft_info: Optional[dict]
    """草稿推送结果：{media_id, url, err_msg}。"""

    retry_count: int
    """当前重试次数。"""

    error: Optional[str]
    """错误信息。"""

    status: str
    """任务状态：pending | running | done | failed。"""

    current_skill: str
    """当前正在执行的 Skill 节点名称。"""

    progress: int
    """任务进度百分比（0-100）。"""
