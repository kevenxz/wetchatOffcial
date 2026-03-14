"""Skill 4: generate_images 节点实现。
为文章生成封面图与插图。当前默认从网页提取图片中随机/顺序挑选。
"""
from __future__ import annotations

import re
import time

import structlog

from workflow.state import WorkflowState

logger = structlog.get_logger(__name__)


async def generate_images_node(state: WorkflowState) -> dict:
    """处理文章配图与封面图。"""
    task_id = state["task_id"]
    extracted_contents = state.get("extracted_contents", [])
    generated_article = state.get("generated_article", {})
    
    start_time = time.monotonic()
    
    logger.info(
        "skill_start",
        task_id=task_id,
        skill="generate_images",
        status="running",
    )
    
    if not generated_article:
        duration_ms = round((time.monotonic() - start_time) * 1000)
        error_msg = "缺少 generated_article，无法生成配图"
        logger.error(
            "skill_failed",
            task_id=task_id,
            skill="generate_images",
            status="failed",
            duration_ms=duration_ms,
            error=error_msg,
        )
        return {
            "status": "failed",
            "current_skill": "generate_images",
            "error": error_msg,
        }

    # 1. 收集所有可用图片
    all_images = []
    for content in extracted_contents:
        for img in content.get("images", []):
            if img not in all_images:
                all_images.append(img)
                
    # 2. 从文中查找有多少个插图标记
    content_text = generated_article.get("content", "")
    # 查找 [插图1], [插图2] ...
    matches = re.findall(r"\[插图\d+\]", content_text)
    required_illustrations_count = len(matches)
    
    # 分配封面和插图
    cover_image = ""
    illustrations = []
    
    if all_images:
        cover_image = all_images.pop(0)  # 第一张作为封面图
        
    for _ in range(required_illustrations_count):
        if all_images:
            illustrations.append(all_images.pop(0))
        else:
            # 图片用完了，用占位符或者保留空
            break
            
    # 更新 generated_article
    new_article = dict(generated_article)
    new_article["cover_image"] = cover_image
    new_article["illustrations"] = illustrations
    
    duration_ms = round((time.monotonic() - start_time) * 1000)
    logger.info(
        "skill_done",
        task_id=task_id,
        skill="generate_images",
        status="done",
        duration_ms=duration_ms,
        cover_image_set=bool(cover_image),
        illustrations_count=len(illustrations),
    )
    
    return {
        "status": "running",
        "current_skill": "generate_images",
        "progress": 85,
        "generated_article": new_article,
    }
