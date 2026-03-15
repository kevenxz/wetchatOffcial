"""Markdown 转微信内联样式 HTML 工具。"""
from __future__ import annotations

import re

import markdown
from bs4 import BeautifulSoup

from api.store import get_style_config


def markdown_to_wechat_html(md_text: str, illustrations: list[str]) -> str:
    """
    将 Markdown 文本转换为带有内联 CSS 样式的适用于微信公众号的 HTML 代码。
    并将 [插图1], [插图2] 转换为居中的 img 标签。
    
    Args:
        md_text: 大模型生成的附带 Markdown 格式的长文。
        illustrations: 已上传完毕的图床/外网图片链接列表。
    """
    if not md_text:
        return ""
        
    # 1. 第一步：先将 [插图N] 替换为特殊占位符以免破坏 Markdown 解析
    # 我们用一个能明确识别的 HTML 标签或者特定字符序列替换
    def replacer(match):
        idx_str = match.group(1)
        idx = int(idx_str) - 1
        if 0 <= idx < len(illustrations):
            img_url = illustrations[idx]
            # 微信公众号图片推荐全宽或限制大小，添加居中容器
            return (
                f'<figure class="wx-illustration-container" style="text-align: center; margin: 16px 0;">'
                f'<img src="{img_url}" style="max-width: 100%; height: auto; border-radius: 8px; box-shadow: 0 4px 8px rgba(0,0,0,0.1);">'
                f'</figure>'
            )
        return match.group(0)

    md_text = re.sub(r"\[插图(\d+)\]", replacer, md_text)
    
    # 将一些连续的换行确保被正确渲染成多个段落
    # markdown 库默认会把换行转为 <br> 或者 <p>
    
    # 2. 第二步：将 Markdown 转换为基础 HTML
    html_content = markdown.markdown(
        md_text,
        extensions=['tables', 'fenced_code', 'nl2br', 'sane_lists']
    )
    
    # 3. 第三步：注入内联 CSS
    style_config = get_style_config()
    
    soup = BeautifulSoup(html_content, "html.parser")
    
    # 遍历所有配置的标签字典
    for tag_name, style_str in style_config.items():
        if not style_str:
            continue
            
        elements = soup.find_all(tag_name)
        for el in elements:
            # 获取原有的 style
            existing_style = el.get("style", "")
            # 为了防止冲突，我们可以将自己的样式拼接到原有样式之后，或者覆盖
            # 这里统一应用配置的样式
            new_style = existing_style + (" " if existing_style and not existing_style.endswith(";") else "") + style_str if existing_style else style_str
            el["style"] = new_style

    # 我们可以在最外层包裹一个 div，设定一下基础边距
    final_html = f'<div class="wx-article-container" style="padding: 0 15px;">{str(soup)}</div>'
    
    return final_html
