from __future__ import annotations

from pathlib import Path

from workflow.utils.markdown_to_wechat import markdown_to_wechat_html


def test_markdown_to_wechat_converts_artifact_paths_to_public_urls(tmp_path: Path) -> None:
    image_path = Path("artifacts/generated_images/task_inline.png").resolve()
    html = markdown_to_wechat_html(
        "正文\n\n[插图1]",
        [str(image_path)],
        style_config={"container": ""},
    )

    assert 'src="/artifacts/generated_images/task_inline.png"' in html


def test_markdown_to_wechat_keeps_remote_image_urls() -> None:
    html = markdown_to_wechat_html(
        "正文\n\n[插图1]",
        ["https://img.example.com/a.png"],
        style_config={"container": ""},
    )

    assert 'src="https://img.example.com/a.png"' in html
