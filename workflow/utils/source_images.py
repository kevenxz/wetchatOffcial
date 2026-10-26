"""Harvest real photographs from the reference articles the article is built on.

Why this exists
---------------
`workflow/tools/fetch_extract.py` has always collected up to five image URLs per page into
``extracted_contents[].images`` — and **nothing ever read them**. Meanwhile the illustration
slots were filled exclusively by the image model, so a task whose sources contained perfectly
good press photographs still shipped synthetic pictures. This module closes that loop.

Two things this is careful about
--------------------------------

1. **Provenance.** Every harvested image must be attributable to the page it came from. An
   image with neither a source title nor a source domain is *rejected* rather than used,
   because the approved policy is "record the origin and require human review" — an
   unattributable image cannot satisfy it.

2. **Real validation, not declared metadata.** The old ``fetch_extract._is_valid_image`` only
   looked at the URL extension and the ``width``/``height`` *attributes* on the ``<img>`` tag.
   Those attributes are usually absent, so logos, icons, ad banners and tracking pixels all
   passed. Everything here is checked against the decoded pixels.

The caller (``plan_visual_assets`` / ``image_generation``) treats a harvest failure as "no
photos available" and falls back to generation; this module never raises for an upstream
problem.
"""
from __future__ import annotations

import asyncio
import hashlib
import io
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlsplit

import httpx
import structlog
from PIL import Image, ImageStat, UnidentifiedImageError

logger = structlog.get_logger(__name__)

SOURCE_IMAGES_DIR = Path("artifacts/source_images")

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# Formats we can decode and the ones WeChat will accept.
DECODABLE_FORMATS = frozenset({"JPEG", "PNG", "WEBP", "BMP", "TIFF", "GIF"})
# `wechat_api.ARTICLE_ALLOWED_IMG_TYPES` is {jpeg, png, gif}. WebP is *not* accepted, yet the
# old extractor happily kept `.webp` URLs — those would only fail later, at upload time.
WECHAT_SAFE_FORMATS = frozenset({"JPEG", "PNG"})

ALLOWED_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp")

# Logos, icons, avatars, ad banners, spacers and analytics beacons. Matched against the URL
# path, since these are almost always named.
_SUSPICIOUS_NAME = re.compile(
    r"(?:^|[/_.-])(logo|icon|favicon|qr|qrcode|avatar|head|share|sprite|spacer|blank|"
    r"pixel|beacon|track|ad|ads|advert|banner|button|badge|watermark)(?:[/_.-]|$)",
    re.IGNORECASE,
)

# Minimum standard deviation of luminance. A near-uniform image is a blank placeholder or a
# solid colour block, not a photograph.
MIN_LUMINANCE_STDDEV = 8.0

# Aspect bounds. The upper bound sits just above the 2.35:1 cover ratio: it admits the cover
# and ordinary landscape photographs (16:9 is 1.78) while rejecting the very wide shapes that
# are almost always site banners rather than pictures.
MIN_ASPECT = 0.5
MAX_ASPECT = 2.8

MAX_WIDTH = 1600
DOWNLOAD_TIMEOUT_SECONDS = 15.0
DOWNLOAD_CONCURRENCY = 4


def _env_bool(name: str, default: bool) -> bool:
    raw = (os.getenv(name) or "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int, *, minimum: int = 1) -> int:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        return max(minimum, int(raw))
    except ValueError:
        return default


def _env_float(name: str, default: float, *, minimum: float = 0.0) -> float:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        return max(minimum, float(raw))
    except ValueError:
        return default


def harvesting_enabled() -> bool:
    return _env_bool("SOURCE_IMAGE_ENABLED", True)


def max_source_images() -> int:
    return _env_int("SOURCE_IMAGE_MAX", 3)


def min_width() -> int:
    return _env_int("SOURCE_IMAGE_MIN_WIDTH", 600)


def min_height() -> int:
    return _env_int("SOURCE_IMAGE_MIN_HEIGHT", 300)


def max_bytes() -> int:
    return _env_int("SOURCE_IMAGE_MAX_BYTES", 8 * 1024 * 1024)


def credit_enabled() -> bool:
    """Whether a visible credit line is rendered under harvested images.

    Off by default: the approved policy is to record provenance in metadata and force human
    review, not necessarily to print the source to readers. One flag flips it.
    """
    return _env_bool("SOURCE_IMAGE_CREDIT", False)


def cover_source_preferred() -> bool:
    return _env_bool("COVER_SOURCE_PREFERRED", True)


def crop_discard_warn_ratio() -> float:
    return _env_float("COVER_CROP_DISCARD_WARN", 0.25)


def allowed_domains() -> tuple[str, ...]:
    raw = (os.getenv("SOURCE_IMAGE_ALLOWED_DOMAINS") or "").strip()
    if not raw:
        return ()
    return tuple(part.strip().lower() for part in raw.split(",") if part.strip())


@dataclass
class SourceImageCandidate:
    """One image URL plus the page it was found on."""

    image_url: str
    source_url: str
    source_title: str
    source_domain: str
    declared_width: int = 0
    declared_height: int = 0


@dataclass
class HarvestedImage:
    """A validated, locally stored photograph ready to be an illustration."""

    image_url: str
    local_path: str
    source_url: str
    source_title: str
    source_domain: str
    width: int
    height: int
    byte_size: int
    content_type: str
    converted_from: str = ""
    notes: list[str] = field(default_factory=list)

    def to_asset(self, *, role: str, index: int, aspect_ratio: str, credit: bool = False) -> dict[str, Any]:
        """Shape used by the rest of the visual pipeline (`visual_state["assets"]`).

        Carries a real ``path`` so `visual_reviewer.is_generated_asset` accepts it, plus the
        attribution block the review UI and the publish gate read.
        """
        return {
            "asset_index": index,
            "role": role,
            "provider": "source",
            # Point every consumer at the file we already downloaded, not the remote origin:
            # the upload path would otherwise re-fetch the URL (without the Referer we needed
            # during harvest) and many CDNs answer that with 403. The remote origin stays in
            # `attribution.image_url` for provenance.
            "url": self.local_path,
            "path": self.local_path,
            "remote_url": self.image_url,
            "target_aspect_ratio": aspect_ratio,
            "source": "source_photo",
            "width": self.width,
            "height": self.height,
            "byte_size": self.byte_size,
            "content_type": self.content_type,
            "converted_from": self.converted_from,
            "credit": self.credit_line() if credit else "",
            "attribution": {
                "source_title": self.source_title,
                "source_domain": self.source_domain,
                "source_url": self.source_url,
                "image_url": self.image_url,
            },
            "notes": list(self.notes),
        }

    def credit_line(self) -> str:
        label = self.source_title or self.source_domain
        return f"图片来源：{label}" if label else ""


def _suspicious_name(url: str) -> bool:
    return bool(_SUSPICIOUS_NAME.search(urlsplit(url).path or ""))


def _domain_of(url: str) -> str:
    return (urlsplit(url).hostname or "").lower()


def _domain_allowed(url: str, allowed: tuple[str, ...]) -> bool:
    if not allowed:
        return True
    host = _domain_of(url)
    return any(host == domain or host.endswith("." + domain) for domain in allowed)


def collect_candidates(
    extracted_contents: list[dict[str, Any]],
    *,
    cited_urls: set[str] | None = None,
    allowed: tuple[str, ...] | None = None,
) -> tuple[list[SourceImageCandidate], dict[str, int]]:
    """Build de-duplicated image candidates from extracted pages.

    ``cited_urls`` restricts harvesting to pages the article actually references. Images from
    pages that merely turned up in search are both less relevant and harder to justify, so
    when the caller supplies a citation set, un-cited pages are skipped.
    """
    allowed_domains_value = allowed if allowed is not None else allowed_domains()
    candidates: list[SourceImageCandidate] = []
    seen_urls: set[str] = set()
    skipped: dict[str, int] = {}

    def skip(reason: str) -> None:
        skipped[reason] = skipped.get(reason, 0) + 1

    for page in extracted_contents:
        if not isinstance(page, dict):
            continue
        page_url = str(page.get("url") or "").strip()
        if cited_urls and page_url and page_url not in cited_urls:
            skip("not_cited")
            continue

        title = str(page.get("title") or "").strip()
        domain = str(page.get("domain") or "").strip() or _domain_of(page_url)

        # The approved policy is "record where it came from", so an image we cannot attribute
        # must not be used at all.
        if not page_url or not (title or domain):
            skip("no_attribution")
            continue

        for raw in list(page.get("images") or []):
            image_url = str(raw or "").strip()
            if not image_url:
                continue
            absolute = urljoin(page_url, image_url) if page_url else image_url
            parsed = urlsplit(absolute)
            if parsed.scheme != "https":
                skip("not_https")
                continue
            if not _domain_allowed(absolute, allowed_domains_value):
                skip("domain_not_allowed")
                continue
            path_lower = (parsed.path or "").lower()
            if not path_lower.endswith(ALLOWED_EXTENSIONS):
                skip("bad_extension")
                continue
            if _suspicious_name(absolute):
                skip("suspicious_name")
                continue
            if absolute in seen_urls:
                skip("duplicate_url")
                continue

            seen_urls.add(absolute)
            candidates.append(
                SourceImageCandidate(
                    image_url=absolute,
                    source_url=page_url,
                    source_title=title,
                    source_domain=domain,
                )
            )

    return candidates, skipped


def _decode(data: bytes) -> Image.Image | None:
    try:
        image = Image.open(io.BytesIO(data))
        image.load()
        return image
    except (UnidentifiedImageError, OSError, ValueError):
        return None


def validate_pixels(image: Image.Image) -> tuple[bool, str]:
    """Pixel-level checks. Returns ``(ok, reason)``.

    Everything here works on decoded pixels, which is the point: the previous check trusted
    ``<img width= height=>`` attributes that are usually missing.
    """
    fmt = str(image.format or "").upper()
    if fmt not in DECODABLE_FORMATS:
        return False, f"unsupported_format({fmt or 'unknown'})"

    # An animated image in an article looks broken and may not survive the upload.
    if int(getattr(image, "n_frames", 1) or 1) > 1:
        return False, "animated"

    width, height = image.size
    if width < min_width() or height < min_height():
        return False, f"too_small({width}x{height})"

    aspect = width / height if height else 0
    if aspect < MIN_ASPECT or aspect > MAX_ASPECT:
        return False, f"bad_aspect({aspect:.2f})"

    # A near-uniform image is a blank box, a solid divider or a placeholder.
    try:
        luminance = image.convert("L")
        stddev = max(ImageStat.Stat(luminance).stddev or [0.0])
    except (OSError, ValueError):
        stddev = 0.0
    if stddev < MIN_LUMINANCE_STDDEV:
        return False, f"low_variance({stddev:.1f})"

    return True, ""


def _prepare_for_wechat(image: Image.Image) -> tuple[bytes, str, str, str]:
    """Re-encode for WeChat. Returns ``(data, extension, content_type, converted_from)``."""
    fmt = str(image.format or "").upper()
    converted_from = ""

    working = image
    if working.width > MAX_WIDTH:
        ratio = MAX_WIDTH / working.width
        working = working.resize((MAX_WIDTH, max(1, int(working.height * ratio))), Image.LANCZOS)

    if fmt in WECHAT_SAFE_FORMATS:
        target_format, extension, content_type = ("PNG", ".png", "image/png") if fmt == "PNG" else ("JPEG", ".jpg", "image/jpeg")
    else:
        # WebP and everything else gets converted: WeChat rejects WebP outright, and WebP is
        # one of the most common formats on the modern web.
        target_format, extension, content_type = "JPEG", ".jpg", "image/jpeg"
        converted_from = fmt.lower()

    if target_format == "JPEG" and working.mode not in ("RGB", "L"):
        # Flatten transparency onto white rather than letting JPEG turn it black.
        if working.mode in ("RGBA", "LA", "P"):
            working = working.convert("RGBA")
            background = Image.new("RGB", working.size, (255, 255, 255))
            background.paste(working, mask=working.split()[-1])
            working = background
        else:
            working = working.convert("RGB")

    buffer = io.BytesIO()
    if target_format == "JPEG":
        working.save(buffer, format="JPEG", quality=86, optimize=True)
    else:
        working.save(buffer, format="PNG", optimize=True)

    return buffer.getvalue(), extension, content_type, converted_from


async def _download(
    client: httpx.AsyncClient,
    candidate: SourceImageCandidate,
) -> tuple[bytes | None, str]:
    """Download one image. Sets ``Referer`` because many CDNs 403 without it."""
    headers = {"User-Agent": USER_AGENT, "Accept": "image/avif,image/webp,image/*,*/*;q=0.8"}
    if candidate.source_url:
        headers["Referer"] = candidate.source_url
    try:
        response = await client.get(candidate.image_url, headers=headers)
        response.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        logger.debug(
            "source_image_download_failed",
            url=candidate.image_url[:120],
            error=f"{type(exc).__name__}: {exc}",
        )
        return None, f"download_failed({type(exc).__name__})"

    data = response.content
    if not data:
        return None, "empty_body"
    if len(data) > max_bytes():
        return None, f"too_large({len(data) // 1024}KB)"
    return data, ""


async def harvest_source_images(
    extracted_contents: list[dict[str, Any]],
    *,
    task_id: str = "",
    cited_urls: set[str] | None = None,
    limit: int | None = None,
) -> tuple[list[HarvestedImage], dict[str, Any]]:
    """Validate and store photographs from the referenced pages.

    Returns ``(images, report)``. The report always describes what was rejected and why, so an
    operator seeing no harvested photos can tell whether that is expected.
    """
    report: dict[str, Any] = {"enabled": harvesting_enabled(), "candidates": 0, "accepted": 0, "rejected": {}}
    if not harvesting_enabled():
        report["skipped"] = "disabled"
        return [], report

    candidates, skipped = collect_candidates(extracted_contents, cited_urls=cited_urls)
    report["candidates"] = len(candidates)
    report["rejected"].update(skipped)
    if not candidates:
        return [], report

    wanted = limit if limit is not None else max_source_images()
    # Over-fetch: some candidates will fail validation, and we want `wanted` survivors.
    attempt_limit = max(wanted * 3, wanted + 4)
    shortlist = candidates[:attempt_limit]

    accepted: list[HarvestedImage] = []
    seen_hashes: set[str] = set()
    rejected = report["rejected"]
    semaphore = asyncio.Semaphore(DOWNLOAD_CONCURRENCY)

    target_dir = SOURCE_IMAGES_DIR / (task_id or "shared")
    target_dir.mkdir(parents=True, exist_ok=True)

    async with httpx.AsyncClient(timeout=DOWNLOAD_TIMEOUT_SECONDS, follow_redirects=True) as client:
        async def process(candidate: SourceImageCandidate) -> HarvestedImage | None:
            async with semaphore:
                if len(accepted) >= wanted:
                    return None
                data, failure = await _download(client, candidate)
                if data is None:
                    rejected[failure] = rejected.get(failure, 0) + 1
                    return None

                digest = hashlib.sha256(data).hexdigest()
                if digest in seen_hashes:
                    rejected["duplicate_content"] = rejected.get("duplicate_content", 0) + 1
                    return None

                image = _decode(data)
                if image is None:
                    rejected["undecodable"] = rejected.get("undecodable", 0) + 1
                    return None

                ok, reason = validate_pixels(image)
                if not ok:
                    key = reason.split("(")[0]
                    rejected[key] = rejected.get(key, 0) + 1
                    return None

                try:
                    payload, extension, content_type, converted_from = _prepare_for_wechat(image)
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "source_image_encode_failed",
                        url=candidate.image_url[:120],
                        error=str(exc),
                        exc_info=True,
                    )
                    rejected["encode_failed"] = rejected.get("encode_failed", 0) + 1
                    return None

                seen_hashes.add(digest)
                path = target_dir / f"{digest[:16]}{extension}"
                try:
                    path.write_bytes(payload)
                except OSError as exc:
                    logger.warning(
                        "source_image_write_failed",
                        path=str(path),
                        error=str(exc),
                        exc_info=True,
                    )
                    rejected["write_failed"] = rejected.get("write_failed", 0) + 1
                    return None

                return HarvestedImage(
                    image_url=candidate.image_url,
                    local_path=str(path).replace("\\", "/"),
                    source_url=candidate.source_url,
                    source_title=candidate.source_title,
                    source_domain=candidate.source_domain,
                    width=image.width,
                    height=image.height,
                    byte_size=len(payload),
                    content_type=content_type,
                    converted_from=converted_from,
                )

        results = await asyncio.gather(*[process(item) for item in shortlist], return_exceptions=True)

    survivors: list[HarvestedImage] = []
    for result in results:
        if isinstance(result, Exception):
            logger.warning("source_image_harvest_unexpected", error=str(result), exc_info=True)
            rejected["unexpected_error"] = rejected.get("unexpected_error", 0) + 1
            continue
        if result is not None:
            survivors.append(result)

    # The cap must be applied here, not only inside the workers. The in-worker check reads a
    # shared counter before appending, so with DOWNLOAD_CONCURRENCY workers in flight they can
    # all pass it and overshoot — a probe with a cap of 2 returned 6. Over-fetching is
    # deliberate (some candidates always fail validation), so trimming the extras is expected.
    accepted = survivors[:wanted]
    if len(survivors) > wanted:
        rejected["over_cap"] = rejected.get("over_cap", 0) + (len(survivors) - wanted)

    report["accepted"] = len(accepted)
    logger.info(
        "source_images_harvested",
        task_id=task_id,
        candidates=report["candidates"],
        accepted=len(accepted),
        rejected=rejected,
    )
    return accepted, report


# --------------------------------------------------------------------------- #
# cropping
# --------------------------------------------------------------------------- #


def crop_to_aspect(
    source_path: str,
    *,
    aspect_ratio: str,
    output_path: str | None = None,
    anchor: str = "center",
) -> tuple[str, float]:
    """Crop an image to ``aspect_ratio`` (e.g. ``"2.35:1"``).

    Returns ``(path, discarded_fraction)`` — the fraction of the original frame thrown away.
    The caller surfaces a large discard ratio for human review, because this function cannot
    see *what* was cropped: without a vision model it cannot tell whether the subject survived.
    """
    try:
        width_ratio, height_ratio = (float(part) for part in str(aspect_ratio).split(":"))
        target = width_ratio / height_ratio
    except (ValueError, ZeroDivisionError):
        return source_path, 0.0

    with Image.open(source_path) as raw:
        image = raw.convert("RGB") if raw.mode not in ("RGB", "L") else raw.copy()

    width, height = image.size
    if not width or not height:
        return source_path, 0.0

    current = width / height
    if abs(current - target) < 0.01:
        return source_path, 0.0

    if current > target:
        # Too wide: trim the sides.
        new_width = max(1, int(round(height * target)))
        new_height = height
        left = (width - new_width) // 2
        top = 0
    else:
        # Too tall: trim top/bottom.
        new_width = width
        new_height = max(1, int(round(width / target)))
        left = 0
        if anchor == "top":
            top = 0
        elif anchor == "bottom":
            top = height - new_height
        else:
            top = (height - new_height) // 2

    discarded = 1.0 - (new_width * new_height) / (width * height)
    cropped = image.crop((left, top, left + new_width, top + new_height))

    destination = Path(output_path) if output_path else Path(source_path).with_name(
        f"{Path(source_path).stem}-{str(aspect_ratio).replace(':', 'x')}.jpg"
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    cropped.save(destination, format="JPEG", quality=90, optimize=True)
    return str(destination).replace("\\", "/"), round(max(0.0, discarded), 4)
