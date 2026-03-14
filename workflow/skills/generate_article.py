"""Skill 3: generate_article 节点实现。
调用 LLM 将多源内容综合成微信公众号风格文章。
"""
from __future__ import annotations

import os
import time

import structlog
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from workflow.state import WorkflowState

logger = structlog.get_logger(__name__)


class ArticleOutput(BaseModel):
    """生成的文章数据模型。"""
    title: str = Field(description="主标题，吸引眼球，≤20字")
    alt_titles: list[str] = Field(description="2个备选标题，≤20字")
    content: str = Field(
        description="正文内容（包含引言、3-5个分点论述、1-2个案例、结尾升华，总共1500-2500字。在适合配图的段落后插入 [插图N] 标记，N为数字序号）"
    )


def _format_extracted_texts(extracted_contents: list[dict]) -> str:
    """将提取到的网页内容格式化为 LLM 的输入。"""
    texts = []
    for i, content in enumerate(extracted_contents, 1):
        texts.append(f"【来源 {i}】\n标题：{content.get('title', '无题')}\n链接：{content.get('url', '')}\n内容：\n{content.get('text', '')}")
    return "\n\n".join(texts)


async def generate_article_node(state: WorkflowState) -> dict:
    """综合网页内容生成微信公众号文章。"""
    task_id = state["task_id"]
    extracted_contents = state.get("extracted_contents", [])
    
    start_time = time.monotonic()
    
    logger.info(
        "skill_start",
        task_id=task_id,
        skill="generate_article",
        status="running",
        source_count=len(extracted_contents),
    )
    
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        duration_ms = round((time.monotonic() - start_time) * 1000)
        error_msg = "未配置 OPENAI_API_KEY"
        logger.error("skill_failed", task_id=task_id, skill="generate_article", status="failed", duration_ms=duration_ms, error=error_msg)
        return {
            "status": "failed",
            "current_skill": "generate_article",
            "error": error_msg,
        }
        
    if not extracted_contents:
        duration_ms = round((time.monotonic() - start_time) * 1000)
        error_msg = "无提取内容，无法生成文章"
        logger.error("skill_failed", task_id=task_id, skill="generate_article", status="failed", duration_ms=duration_ms, error=error_msg)
        return {
            "status": "failed",
            "current_skill": "generate_article",
            "error": error_msg,
        }

    formatted_texts = _format_extracted_texts(extracted_contents)
    
    system_prompt = """你是一位资深新媒体编辑。请根据以下多个网页内容，综合成一篇微信公众号风格的文章。
要求：
- 给出 1 个主标题和 2 个备选标题，标题需吸引眼球（≤20字）
- 正文包含：引言、3-5个分点论述（含小标题）、1-2个案例、结尾升华
- 语言生动活泼，符合公众号读者喜好，字数 1500-2500 字
- 在适合配图的段落后插入 [插图N] 标记（N 为序号）
"""
    human_prompt = "内容来源：\n{extracted_texts}"
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        ("human", human_prompt),
    ])
    
    model_name = os.getenv("OPENAI_MODEL", "gpt-4o")
    base_url = os.getenv("OPENAI_API_BASE", None)
    
    llm = ChatOpenAI(
        model=model_name,
        api_key=api_key,
        base_url=base_url if base_url else None,
        max_tokens=4000,
        temperature=0.7,
    ).with_structured_output(ArticleOutput)
    
    chain = prompt | llm
    
    retry_count = 0
    max_retries = 3
    final_article: ArticleOutput | None = None
    error_msg = None
    
    while retry_count < max_retries:
        try:
            logger.info("generate_article_attempt", task_id=task_id, attempt=retry_count + 1)
            # ainvoke 返回 ArticleOutput 实例
            result = await chain.ainvoke({"extracted_texts": formatted_texts})
            if result and len(result.content) >= 500:
                final_article = result
                break
            else:
                error_msg = "生成的文章过短（< 500字）"
        except Exception as e:
            error_msg = str(e)
            logger.warning(
                "generate_article_failed_attempt",
                task_id=task_id,
                attempt=retry_count + 1,
                error=error_msg
            )
        
        retry_count += 1
    
    duration_ms = round((time.monotonic() - start_time) * 1000)
    
    if not final_article:
        final_error = error_msg or "文章生成失败"
        logger.error(
            "skill_failed",
            task_id=task_id,
            skill="generate_article",
            status="failed",
            duration_ms=duration_ms,
            error=final_error,
        )
        return {
            "status": "failed",
            "current_skill": "generate_article",
            "error": final_error,
        }
    
    logger.info(
        "skill_done",
        task_id=task_id,
        skill="generate_article",
        status="done",
        duration_ms=duration_ms,
        content_length=len(final_article.content),
    )
    
    return {
        "status": "running",
        "current_skill": "generate_article",
        "progress": 75,
        "generated_article": {
            "title": final_article.title,
            "alt_titles": final_article.alt_titles,
            "content": final_article.content,
            "cover_image": "",
            "illustrations": []
        },
    }
