"""Pure image transformations used by the blob upload service."""

from __future__ import annotations

import warnings
from io import BytesIO

from PIL import Image, UnidentifiedImageError

from app.core.exceptions import UnsupportedMediaTypeError


def transform(
    data: bytes,
    content_type: str,
    *,
    quality: int | None,
    max_dimension: int | None,
) -> tuple[bytes, str]:
    """Resize/re-encode an image without retaining source EXIF metadata."""
    if not content_type.lower().startswith("image/") or (
        quality is None and max_dimension is None
    ):
        return data, content_type

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as source:
                source.load()
                image = source.copy()
                source_format = source.format
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise UnsupportedMediaTypeError("Image exceeds the supported pixel limit") from exc
    except UnidentifiedImageError as exc:
        raise UnsupportedMediaTypeError("Invalid image data") from exc

    if max_dimension is not None:
        image.thumbnail((max_dimension, max_dimension))

    output = BytesIO()
    is_jpeg = content_type.lower() in {"image/jpeg", "image/jpg"} or source_format == "JPEG"
    if is_jpeg:
        if image.mode not in {"RGB", "L"}:
            image = image.convert("RGB")
        image.save(output, format="JPEG", quality=quality, optimize=True)
        return output.getvalue(), "image/jpeg"

    if quality is not None:
        image.save(output, format="WEBP", quality=quality, method=6)
        return output.getvalue(), "image/webp"

    image.save(output, format=source_format or "PNG", optimize=True)
    return output.getvalue(), content_type
