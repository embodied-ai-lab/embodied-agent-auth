"""Image validity checks that deliberately do not classify scene semantics."""

from __future__ import annotations

import io
from dataclasses import dataclass

from PIL import Image, UnidentifiedImageError


class ImageValidationError(ValueError):
    pass


@dataclass(frozen=True)
class ImageInfo:
    format: str
    width: int
    height: int


def validate_image(image_bytes: bytes) -> ImageInfo:
    if not image_bytes:
        raise ImageValidationError("image payload is empty")
    try:
        with Image.open(io.BytesIO(image_bytes)) as image:
            image_format = str(image.format or "").upper()
            width, height = image.size
            image.verify()
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ImageValidationError(f"image is not decodable: {exc}") from exc
    if image_format not in {"PNG", "JPEG"}:
        raise ImageValidationError(f"unsupported image format: {image_format or 'unknown'}")
    if width < 128 or height < 128:
        raise ImageValidationError(f"image is too small for the VLM: {width}x{height}")
    return ImageInfo(format=image_format, width=width, height=height)
