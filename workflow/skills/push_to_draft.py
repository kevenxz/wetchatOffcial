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
from workflow.utils.wechat_api import upload_cover_material, upload_article_image
from workflow.utils.markdown_to_wechat import markdown_to_wechat_html

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
        
    retry_count = 0
    max_retries = 3
    final_media_id = None
    error_msg = None
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        # 在此循环外预处理图片，无论重试几次，图片上传复用
        # 如果获取 token 出错或者需要获取，必须在这个阶段先拿到一次 token
        try:
            token = await _get_access_token(app_id, app_secret, client)
        except Exception as e:
            error_msg = str(e)
            logger.error("skill_failed", task_id=task_id, skill="push_to_draft", status="failed", duration_ms=round((time.monotonic() - start_time) * 1000), error=error_msg)
            return {"status": "failed", "current_skill": "push_to_draft", "error": error_msg}
            
        # 1. 上传封面图，获取 media_id
        thumb_media_id = ""
        if article.get("cover_image"):
            logger.info("uploading_cover_image", task_id=task_id, url=article["cover_image"])
            thumb_media_id = await upload_cover_material(client, article["cover_image"], token)
        
        # 2. 上传插图，把外部链接替换为微信的 qpic 图床链接
        illustrations = list(article.get("illustrations", []))
        wechat_illustrations = []
        for i, img_url in enumerate(illustrations):
            logger.info("uploading_illustration", task_id=task_id, index=i+1, url=img_url)
            wx_url = await upload_article_image(client, img_url, token)
            wechat_illustrations.append(wx_url)
            
        # 重构带真实微信图片的 html 内容
        html_content = markdown_to_wechat_html(
            md_text=article.get("content", ""), 
            illustrations=wechat_illustrations
        )
        
        # 3. 构建草稿 Payload
        draft_payload = {
            "articles": [
                {
                    "title": article.get("title", "自动生成的文章"),
                    "content": html_content,
                    "thumb_media_id": thumb_media_id,
                }
            ]
        }
        
        # 因为在测试或者没有好图源时，封面可能是必填的，但如果是自己测试可以模拟
        if not thumb_media_id:
            logger.warning("missing_thumb_media_id", task_id=task_id, message="封面图 media_id 为空，调用微信接口必定报错(40007)")
        while retry_count < max_retries:
            try:
                # 重新校验/刷新一次 token
                current_token = await _get_access_token(app_id, app_secret, client)
                url = f"https://api.weixin.qq.com/cgi-bin/draft/add?access_token={current_token}"
                
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
