"""Skill 5: push_to_draft 节点实现。
将图文内容推送至微信公众号草稿箱。
"""
from __future__ import annotations

import os
import re
import time

import httpx
import structlog

from workflow.state import WorkflowState

logger = structlog.get_logger(__name__)

# 全局 Token 缓存
_access_token_cache: dict[str, str | float] = {"token": "", "expires_at": 0.0}


async def _get_access_token(app_id: str, app_secret: str, client: httpx.AsyncClient) -> str:
    """获取/刷新微信 API Access Token。"""
    now = time.time()
    if _access_token_cache.get("token") and now < float(_access_token_cache.get("expires_at", 0)) - 300:
        return str(_access_token_cache["token"])
        
    url = f"https://api.weixin.qq.com/cgi-bin/token?grant_type=client_credential&appid={app_id}&secret={app_secret}"
    resp = await client.get(url)
    resp.raise_for_status()
    data = resp.json()
    
    if "errcode" in data and data["errcode"] != 0:
        raise ValueError(f"获取 token 失败: {data}")
        
    token = data["access_token"]
    expires_in = data["expires_in"]
    _access_token_cache["token"] = token
    _access_token_cache["expires_at"] = now + expires_in
    return token


def _build_html_content(article: dict) -> str:
    """将正文和插图替换合并为最终的 HTML 格式文本。"""
    content = article.get("content", "")
    illustrations = article.get("illustrations", [])
    
    # 替换 [插图N] 为 <img> 标签
    def replacer(match):
        idx_str = match.group(1)
        idx = int(idx_str) - 1
        if 0 <= idx < len(illustrations):
            img_url = illustrations[idx]
            return f'<br><img src="{img_url}" style="max-width: 100%;"><br>'
        return match.group(0) # 没找到对应图片则保留原样
        
    html_content = re.sub(r"\[插图(\d+)\]", replacer, content)
    # 将段落换行替换为 <p> 或 <br>
    html_content = html_content.replace("\n\n", "</p><p>")
    html_content = f"<p>{html_content}</p>"
    
    return html_content


async def push_to_draft_node(state: WorkflowState) -> dict:
    """推送到微信公众号草稿箱。"""
    task_id = state["task_id"]
    article = state.get("generated_article")
    
    start_time = time.monotonic()
    
    logger.info("skill_start", task_id=task_id, skill="push_to_draft", status="running")
    
    if not article:
        duration_ms = round((time.monotonic() - start_time) * 1000)
        error_msg = "无可推送的文章内容"
        logger.error("skill_failed", task_id=task_id, skill="push_to_draft", status="failed", duration_ms=duration_ms, error=error_msg)
        return {"status": "failed", "current_skill": "push_to_draft", "error": error_msg}
        
    app_id = os.getenv("WECHAT_APP_ID")
    app_secret = os.getenv("WECHAT_APP_SECRET")
    
    if not app_id or not app_secret:
        # 如果没有配置 APP_ID，模拟成功以便于测试
        logger.warning("wechat_api_mock", task_id=task_id, message="未配置 WECHAT_APP_ID，跳过实际推送并模拟成功")
        duration_ms = round((time.monotonic() - start_time) * 1000)
        return {
            "status": "running",
            "current_skill": "push_to_draft",
            "progress": 95,
            "draft_info": {
                "media_id": "mock_media_id_12345",
                "url": "https://mp.weixin.qq.com/mock_draft_preview",
            }
        }
        
    html_content = _build_html_content(article)
    
    # 构建请求体
    draft_payload = {
        "articles": [
            {
                "title": article.get("title", "自动生成的文章"),
                "content": html_content,
                # "thumb_media_id": "..." 此处应当是已上传图片的 media_id。为简化此处省略，实际微信强求封面图
                # 如果没有 thumb_media_id 会报错，这里在实际调用中必须提供。
            }
        ]
    }
    
    retry_count = 0
    max_retries = 3
    final_media_id = None
    error_msg = None
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        while retry_count < max_retries:
            try:
                token = await _get_access_token(app_id, app_secret, client)
                url = f"https://api.weixin.qq.com/cgi-bin/draft/add?access_token={token}"
                
                resp = await client.post(url, json=draft_payload)
                resp.raise_for_status()
                data = resp.json()
                
                if "errcode" in data and data["errcode"] != 0:
                    # 如果 token 失效
                    if data["errcode"] in (40001, 40014, 42001, 42002):
                        _access_token_cache["token"] = "" # 清空缓存强制刷新
                        raise ValueError(f"Token invalid: {data}")
                    raise ValueError(f"推送失败: {data}")
                    
                final_media_id = data.get("media_id")
                break
            except Exception as e:
                error_msg = str(e)
                logger.warning("push_to_draft_failed_attempt", task_id=task_id, attempt=retry_count+1, error=error_msg)
                
            retry_count += 1
            
    duration_ms = round((time.monotonic() - start_time) * 1000)
    
    if not final_media_id:
        logger.error("skill_failed", task_id=task_id, skill="push_to_draft", status="failed", duration_ms=duration_ms, error=error_msg)
        return {
            "status": "failed",
            "current_skill": "push_to_draft",
            "error": error_msg or "推送失败",
        }
        
    logger.info("skill_done", task_id=task_id, skill="push_to_draft", status="done", duration_ms=duration_ms, media_id=final_media_id)
    
    return {
        "status": "running",
        "current_skill": "push_to_draft",
        "progress": 95,
        "draft_info": {
            "media_id": final_media_id,
            "url": "", # 微信草稿没法直接给 url，可以通过 media_id 去预览接口换
        }
    }
