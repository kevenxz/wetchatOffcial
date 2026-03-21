"""封装微信 API 素材上传相关的操作方法。"""
from __future__ import annotations

import mimetypes
from urllib.parse import urlparse

import httpx
import structlog

logger = structlog.get_logger(__name__)

# 正文插图允许的类型（微信 uploadimg 兼容性优先）
ARTICLE_ALLOWED_IMG_TYPES = {"image/jpeg", "image/png", "image/gif"}
# 封面素材允许的类型（永久素材接口更严格，禁用 webp/svg）
COVER_ALLOWED_IMG_TYPES = {"image/jpeg", "image/png", "image/gif"}


def _detect_image_mime(content: bytes, content_type_header: str, img_url: str) -> str:
    """根据响应头、URL 后缀和文件内容推断真实图片类型。"""
    content_type = content_type_header.lower().split(";")[0].strip()
    if content_type:
        return content_type

    guessed, _ = mimetypes.guess_type(urlparse(img_url).path)
    if guessed:
        return guessed

    head = content[:64]
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if head.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if head.startswith(b"RIFF") and b"WEBP" in content[:16]:
        return "image/webp"

    # camo/github/shields 等来源常见 svg，微信素材接口不支持
    text_head = content[:256].lstrip().lower()
    if text_head.startswith(b"<?xml") or text_head.startswith(b"<svg") or b"<svg" in text_head:
        return "image/svg+xml"

    return ""


async def _download_image(
    client: httpx.AsyncClient,
    img_url: str,
    allowed_types: set[str],
) -> tuple[bytes, str, str]:
    """下载远端图片，返回二进制内容、文件名和 MimeType。"""
    try:
        resp = await client.get(img_url, follow_redirects=True, timeout=15.0)
        resp.raise_for_status()
        
        content = resp.content
        content_type = _detect_image_mime(content, resp.headers.get("Content-Type", ""), img_url)

        if content_type == "image/svg+xml":
            logger.warning("skip_unsupported_svg_image", url=img_url)
            return b"", "", ""

        if content_type not in allowed_types:
            logger.warning("skip_unsupported_image_type", url=img_url, content_type=content_type or "unknown")
            return b"", "", ""

        # 生成一个模拟的文件名
        ext = "jpg" if content_type == "image/jpeg" else content_type.split("/")[-1]
        filename = f"upload_img.{ext}"
        
        return content, filename, content_type
    except Exception as e:
        logger.warning("download_image_failed", url=img_url, error=str(e))
        return b"", "", ""


async def upload_cover_material(client: httpx.AsyncClient, img_url: str, access_token: str) -> str:
    """上传封面图片为草稿箱需要的“永久素材 (media_id)”。
    微信要求：草稿的 thumb_media_id 必须是由新增永久图文素材或者新增实体图片素材生成的。
    
    Returns:
        media_id: 微信服务器返回的永久素材 media_id，上传失败则返回空字符串。
    """
    if not img_url:
        return ""
        
    img_data, filename, content_type = await _download_image(client, img_url, COVER_ALLOWED_IMG_TYPES)
    if not img_data:
        return ""
        
    url = f"https://api.weixin.qq.com/cgi-bin/material/add_material?access_token={access_token}&type=image"
    
    files = {
        "media": (filename, img_data, content_type)
    }
    
    try:
        resp = await client.post(url, files=files, timeout=20.0)
        data = resp.json()
        if "media_id" in data:
            return data["media_id"]
        else:
            logger.error("upload_material_failed", result=data, url=img_url)
            return ""
    except Exception as e:
        logger.error("upload_material_exception", url=img_url, error=str(e))
        return ""


async def upload_article_image(client: httpx.AsyncClient, img_url: str, access_token: str) -> str:
    """上传正文插图获取微信白名单图床 URL (不会产生 media_id，不占用永久素材库配额)。
    
    Returns:
        wechat_url: 微信图床 URL (`http://mmbiz.qpic.cn/...`)，失败则返回原 URL。
    """
    if not img_url:
        return ""
        
    img_data, filename, content_type = await _download_image(client, img_url, ARTICLE_ALLOWED_IMG_TYPES)
    if not img_data:
        return img_url # 如果下载失败就不强求了，兜底用外网连接
        
    url = f"https://api.weixin.qq.com/cgi-bin/media/uploadimg?access_token={access_token}"
    
    files = {
        "media": (filename, img_data, content_type)
    }
    
    try:
        resp = await client.post(url, files=files, timeout=20.0)
        data = resp.json()
        if "url" in data:
            return data["url"]
        else:
            logger.warning("uploadimg_failed", result=data, url=img_url)
            return img_url
    except Exception as e:
        logger.warning("uploadimg_exception", url=img_url, error=str(e))
        return img_url
