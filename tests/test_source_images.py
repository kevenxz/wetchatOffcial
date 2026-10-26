"""Tests for harvesting real photographs from the reference articles.

The gap this closes: `fetch_extract` has always collected up to five image URLs per page into
``extracted_contents[].images``, and **nothing ever read them**. Illustration slots were filled
only by the image model, so a task whose sources contained real press photographs still shipped
synthetic pictures.

Two behaviours matter most here and are easy to get wrong:

* the old validator trusted ``<img width= height=>`` *attributes*, which are usually absent —
  so logos, icons, ad banners and tracking pixels all passed. Everything is now checked against
  the decoded pixels.
* WeChat accepts only jpeg/png/gif (`ARTICLE_ALLOWED_IMG_TYPES`), while the old extractor
  happily kept ``.webp`` URLs — those would fail only later, at upload time.
"""
from __future__ import annotations

import io

import pytest
from PIL import Image

import workflow.utils.source_images as source_images
from workflow.utils.source_images import (
    HarvestedImage,
    collect_candidates,
    crop_to_aspect,
    harvest_source_images,
    validate_pixels,
)


_PHOTO_CACHE: dict[tuple[int, int, str], bytes] = {}


def _photo_bytes(width: int = 1200, height: int = 800, fmt: str = "PNG") -> bytes:
    """Encoded photo-like image. Cached: a megapixel of noise per call is needlessly slow."""
    key = (width, height, fmt)
    if key not in _PHOTO_CACHE:
        image = Image.new("RGB", (width, height))
        # Deterministic high-frequency pattern: plenty of luminance variation for the variance
        # gate, without a million random() calls.
        rows = bytearray()
        for y in range(height):
            rows.extend(
                b
                for x in range(width)
                for b in ((x * 7 + y * 13) % 256, (x * 3 + y * 29) % 256, (x * 17 + y * 5) % 256)
            )
        image.frombytes(bytes(rows))
        buffer = io.BytesIO()
        image.save(buffer, format=fmt)
        _PHOTO_CACHE[key] = buffer.getvalue()
    return _PHOTO_CACHE[key]


def _photo(width: int = 1200, height: int = 800, fmt: str = "PNG") -> Image.Image:
    """A photo-like image: real luminance variation, so it passes the variance gate."""
    buffer = io.BytesIO(_photo_bytes(width, height, fmt))
    loaded = Image.open(buffer)
    loaded.load()
    return loaded


def _flat(width: int = 1200, height: int = 800, fmt: str = "PNG") -> Image.Image:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), (255, 255, 255)).save(buffer, format=fmt)
    buffer.seek(0)
    loaded = Image.open(buffer)
    loaded.load()
    return loaded


def _animated_gif() -> Image.Image:
    frames = [Image.new("RGB", (800, 600), (10 + index * 40, 40, 90)) for index in range(3)]
    buffer = io.BytesIO()
    frames[0].save(buffer, format="GIF", save_all=True, append_images=frames[1:], duration=120, loop=0)
    buffer.seek(0)
    loaded = Image.open(buffer)
    loaded.load()
    return loaded


@pytest.fixture(autouse=True)
def isolated_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(source_images, "SOURCE_IMAGES_DIR", tmp_path)
    yield


def _page(url: str = "https://news.example.com/a", **overrides) -> dict:
    page = {
        "url": url,
        "title": "示例新闻标题",
        "domain": "news.example.com",
        "images": ["https://img.example.com/photo-1.jpg"],
    }
    page.update(overrides)
    return page


# --------------------------------------------------------------------------- #
# pixel-level validation
# --------------------------------------------------------------------------- #


def test_photo_passes() -> None:
    ok, reason = validate_pixels(_photo())
    assert ok, reason


def test_blank_image_is_rejected() -> None:
    """A solid colour is a divider, a placeholder or an empty box — not a photograph."""
    ok, reason = validate_pixels(_flat())
    assert not ok
    assert reason.startswith("low_variance")


def test_tiny_image_is_rejected() -> None:
    """This is what the old attribute-based check missed: logos and icons."""
    ok, reason = validate_pixels(_photo(200, 150))
    assert not ok
    assert reason.startswith("too_small")


def test_short_banner_is_rejected() -> None:
    ok, reason = validate_pixels(_photo(2000, 200))
    assert not ok
    assert reason.startswith("too_small")


def test_extreme_aspect_is_rejected() -> None:
    ok, reason = validate_pixels(_photo(2400, 700))
    assert not ok
    assert reason.startswith("bad_aspect")


def test_animated_image_is_rejected() -> None:
    """An animation looks broken in an article and may not survive the upload."""
    ok, reason = validate_pixels(_animated_gif())
    assert not ok
    assert reason == "animated"


def test_webp_decodes_and_is_then_converted(monkeypatch) -> None:
    """WebP is common on the web and accepted by the old extractor, but WeChat rejects it."""
    image = _photo(fmt="WEBP")
    ok, reason = validate_pixels(image)
    assert ok, reason

    payload, extension, content_type, converted_from = source_images._prepare_for_wechat(image)
    assert extension == ".jpg"
    assert content_type == "image/jpeg"
    assert converted_from == "webp"
    assert payload


def test_png_is_kept_as_png() -> None:
    payload, extension, content_type, converted_from = source_images._prepare_for_wechat(_photo(fmt="PNG"))
    assert extension == ".png"
    assert content_type == "image/png"
    assert converted_from == ""


def test_oversized_image_is_downscaled() -> None:
    payload, _, _, _ = source_images._prepare_for_wechat(_photo(4000, 2200))
    with Image.open(io.BytesIO(payload)) as result:
        assert result.width <= source_images.MAX_WIDTH


# --------------------------------------------------------------------------- #
# candidate collection (no network)
# --------------------------------------------------------------------------- #


def test_only_https_is_kept() -> None:
    page = _page(images=["https://img.example.com/ok.jpg", "http://img.example.com/no.jpg"])
    candidates, skipped = collect_candidates([page])
    assert [item.image_url for item in candidates] == ["https://img.example.com/ok.jpg"]
    assert skipped["not_https"] == 1


@pytest.mark.parametrize(
    "hostile",
    [
        "https://img.example.com/logo.png",
        "https://img.example.com/icon-32.png",
        "https://img.example.com/avatar/user.jpg",
        "https://img.example.com/qrcode.png",
        "https://img.example.com/ad/banner.jpg",
        "https://img.example.com/pixel.gif",
        "https://img.example.com/spacer.png",
    ],
)
def test_logos_icons_and_trackers_are_filtered_by_name(hostile: str) -> None:
    candidates, skipped = collect_candidates([_page(images=[hostile])])
    assert candidates == []
    assert skipped.get("suspicious_name") == 1 or skipped.get("bad_extension") == 1


def test_non_image_extensions_are_filtered() -> None:
    page = _page(images=["https://img.example.com/a.svg", "https://img.example.com/b.gif", "https://img.example.com/c"])
    candidates, skipped = collect_candidates([page])
    assert candidates == []
    assert skipped["bad_extension"] == 3


def test_data_uri_is_filtered() -> None:
    page = _page(images=["images/real.jpg", "data:image/png;base64,AAAA"])
    candidates, skipped = collect_candidates([page])
    # A relative URL is resolved against the page; the data URI has no https scheme.
    assert [item.image_url for item in candidates] == ["https://news.example.com/images/real.jpg"]
    assert skipped["not_https"] == 1


def test_duplicate_urls_are_collapsed() -> None:
    page = _page(images=["https://img.example.com/a.jpg", "https://img.example.com/a.jpg"])
    candidates, skipped = collect_candidates([page])
    assert len(candidates) == 1
    assert skipped["duplicate_url"] == 1


def test_unattributable_page_is_skipped() -> None:
    """No title and no domain means we cannot record an origin, so the policy forbids use."""
    page = {"url": "", "title": "", "domain": "", "images": ["https://img.example.com/a.jpg"]}
    candidates, skipped = collect_candidates([page])
    assert candidates == []
    assert skipped["no_attribution"] == 1


def test_uncited_pages_are_skipped_when_a_citation_set_is_given() -> None:
    cited = _page("https://news.example.com/cited", images=["https://img.example.com/a.jpg"])
    other = _page("https://news.example.com/other", images=["https://img.example.com/b.jpg"])

    candidates, skipped = collect_candidates([cited, other], cited_urls={"https://news.example.com/cited"})

    assert [item.image_url for item in candidates] == ["https://img.example.com/a.jpg"]
    assert skipped["not_cited"] == 1


def test_allowed_domains_are_enforced() -> None:
    page = _page(images=["https://img.example.com/a.jpg", "https://cdn.trusted.com/b.jpg"])
    candidates, skipped = collect_candidates([page], allowed=("trusted.com",))
    assert [item.image_url for item in candidates] == ["https://cdn.trusted.com/b.jpg"]
    assert skipped["domain_not_allowed"] == 1


def test_relative_image_urls_are_resolved() -> None:
    page = _page(images=["/static/pic.jpg"])
    candidates, _ = collect_candidates([page])
    assert candidates[0].image_url == "https://news.example.com/static/pic.jpg"


# --------------------------------------------------------------------------- #
# harvesting
# --------------------------------------------------------------------------- #


class _FakeResponse:
    def __init__(self, content: bytes) -> None:
        self.content = content
        self.status_code = 200

    def raise_for_status(self) -> None:
        return None


def _client(payload_by_url: dict[str, bytes]):
    """A minimal async client stub that serves bytes per URL."""
    import httpx

    class _Client:
        def __init__(self, **kwargs) -> None:
            self.headers_seen: list[dict] = []

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, url, headers=None):
            self.headers_seen.append(dict(headers or {}))
            if url not in payload_by_url:
                raise httpx.HTTPStatusError("403", request=None, response=None)  # type: ignore[arg-type]
            return _FakeResponse(payload_by_url[url])

    return _Client


def _encode(image: Image.Image, fmt: str = "PNG") -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format=fmt)
    return buffer.getvalue()


@pytest.mark.asyncio
async def test_harvest_accepts_a_valid_photo(monkeypatch) -> None:
    url = "https://img.example.com/photo-1.jpg"
    monkeypatch.setattr(source_images.httpx, "AsyncClient", _client({url: _encode(_photo())}))

    harvested, report = await harvest_source_images([_page(images=[url])], task_id="t1")

    assert len(harvested) == 1
    assert report["accepted"] == 1
    stored = harvested[0]
    assert stored.source_domain == "news.example.com"
    assert stored.source_title == "示例新闻标题"
    assert stored.credit_line().startswith("图片来源：")
    assert (source_images.SOURCE_IMAGES_DIR / "t1").exists()


@pytest.mark.asyncio
async def test_harvest_sends_a_referer(monkeypatch) -> None:
    """Many CDNs 403 without one, which would silently cost us every image."""
    url = "https://img.example.com/photo-1.jpg"
    factory = _client({url: _encode(_photo())})
    monkeypatch.setattr(source_images.httpx, "AsyncClient", factory)

    await harvest_source_images([_page(images=[url])], task_id="t1")
    # The stub records headers on the instance; re-run via a capture list instead.
    captured: list[dict] = []
    original = source_images._download

    async def spy(client, candidate):
        captured.append({"referer": candidate.source_url})
        return await original(client, candidate)

    monkeypatch.setattr(source_images, "_download", spy)
    await harvest_source_images([_page(images=[url])], task_id="t1")
    assert captured and captured[0]["referer"] == "https://news.example.com/a"


@pytest.mark.asyncio
async def test_download_failure_is_tolerated(monkeypatch) -> None:
    """A 403 from a hotlink-protected CDN must not fail the task."""
    url = "https://img.example.com/locked.jpg"
    monkeypatch.setattr(source_images.httpx, "AsyncClient", _client({}))

    harvested, report = await harvest_source_images([_page(images=[url])], task_id="t1")

    assert harvested == []
    assert report["accepted"] == 0
    assert any(key.startswith("download_failed") for key in report["rejected"])


@pytest.mark.asyncio
async def test_garbage_body_is_rejected(monkeypatch) -> None:
    url = "https://img.example.com/not-an-image.jpg"
    monkeypatch.setattr(source_images.httpx, "AsyncClient", _client({url: b"this is not an image"}))

    harvested, report = await harvest_source_images([_page(images=[url])], task_id="t1")

    assert harvested == []
    assert report["rejected"].get("undecodable") == 1


@pytest.mark.asyncio
async def test_identical_images_from_two_pages_count_once(monkeypatch) -> None:
    """The same photo is often re-served under different URLs."""
    data = _encode(_photo())
    monkeypatch.setattr(
        source_images.httpx,
        "AsyncClient",
        _client({"https://img.example.com/a.jpg": data, "https://img.example.com/b.jpg": data}),
    )
    pages = [
        _page("https://news.example.com/1", images=["https://img.example.com/a.jpg"]),
        _page("https://news.example.com/2", images=["https://img.example.com/b.jpg"]),
    ]

    harvested, report = await harvest_source_images(pages, task_id="t1")

    assert len(harvested) == 1
    assert report["rejected"].get("duplicate_content") == 1


@pytest.mark.asyncio
async def test_result_count_is_capped(monkeypatch) -> None:
    monkeypatch.setenv("SOURCE_IMAGE_MAX", "2")
    payload = {
        f"https://img.example.com/{index}.jpg": _encode(_photo(1000 + index, 700))
        for index in range(6)
    }
    monkeypatch.setattr(source_images.httpx, "AsyncClient", _client(payload))
    page = _page(images=list(payload))

    harvested, _ = await harvest_source_images([page], task_id="t1")

    assert len(harvested) == 2


@pytest.mark.asyncio
async def test_harvesting_can_be_disabled(monkeypatch) -> None:
    monkeypatch.setenv("SOURCE_IMAGE_ENABLED", "false")
    harvested, report = await harvest_source_images([_page()], task_id="t1")
    assert harvested == []
    assert report["skipped"] == "disabled"


@pytest.mark.asyncio
async def test_no_candidate_urls_returns_empty_without_network(monkeypatch) -> None:
    harvested, report = await harvest_source_images([{"url": "https://x/1", "title": "t", "images": []}], task_id="t1")
    assert harvested == []
    assert report["candidates"] == 0


# --------------------------------------------------------------------------- #
# asset shaping + cover crop
# --------------------------------------------------------------------------- #


def test_asset_shape_satisfies_the_pipeline() -> None:
    """The reviewer accepts an asset with a real path; attribution drives the review gate."""
    item = HarvestedImage(
        image_url="https://img.example.com/a.png",
        local_path="artifacts/source_images/t1/abc.png",
        source_url="https://news.example.com/a",
        source_title="示例新闻",
        source_domain="news.example.com",
        width=1200,
        height=800,
        byte_size=1234,
        content_type="image/png",
    )

    asset = item.to_asset(role="cover", index=1, aspect_ratio="2.35:1", credit=True)

    assert asset["provider"] == "source"
    assert asset["path"].endswith(".png")
    assert asset["attribution"]["source_domain"] == "news.example.com"
    assert asset["credit"]

    from workflow.agents.visual_reviewer import has_real_image, is_generated_asset, is_source_asset

    assert has_real_image(asset)
    assert is_source_asset(asset)
    assert not is_generated_asset(asset), "a harvested photo is not a generated image"


def test_credit_line_can_be_withheld() -> None:
    item = HarvestedImage(
        image_url="https://img/a.png",
        local_path="p.png",
        source_url="https://news/a",
        source_title="示例",
        source_domain="news.example.com",
        width=1000,
        height=700,
        byte_size=1,
        content_type="image/png",
    )
    assert item.to_asset(role="cover", index=1, aspect_ratio="2.35:1", credit=False)["credit"] == ""


def test_cover_crop_hits_the_wechat_ratio(tmp_path) -> None:
    """WeChat's cover is 2.35:1; a 4:3 press photo must not be sent as-is."""
    source = tmp_path / "wide.png"
    _photo(1500, 1000).save(source)

    path, discarded = crop_to_aspect(str(source), aspect_ratio="2.35:1", output_path=str(tmp_path / "c.png"))

    with Image.open(path) as cropped:
        assert abs(cropped.width / cropped.height - 2.35) < 0.02
    assert 0 < discarded < 1


def test_crop_reports_the_discarded_fraction(tmp_path) -> None:
    """A big discard must be visible, because this code cannot see what it cut off."""
    source = tmp_path / "tall.png"
    _photo(1000, 1000).save(source)

    _, discarded = crop_to_aspect(str(source), aspect_ratio="2.35:1", output_path=str(tmp_path / "c.png"))

    assert discarded > 0.25, "a square cropped to 2.35:1 loses well over a quarter"


def test_crop_is_a_noop_for_the_right_ratio(tmp_path) -> None:
    source = tmp_path / "ok.png"
    _photo(1410, 600).save(source)

    path, discarded = crop_to_aspect(str(source), aspect_ratio="2.35:1", output_path=str(tmp_path / "c.png"))

    assert path == str(source)
    assert discarded == 0.0


def test_invalid_ratio_returns_the_original(tmp_path) -> None:
    source = tmp_path / "ok.png"
    _photo(1200, 800).save(source)
    path, discarded = crop_to_aspect(str(source), aspect_ratio="not-a-ratio")
    assert path == str(source)
    assert discarded == 0.0
