from io import BytesIO

from PIL import Image

from app.core.imaging import transform


def _image_bytes(format: str, size: tuple[int, int] = (128, 96)) -> bytes:
    image = Image.new("RGB", size, color=(180, 80, 20))
    output = BytesIO()
    image.save(output, format=format)
    return output.getvalue()


def test_transform_passes_through_non_images() -> None:
    assert transform(b"plain", "text/plain", quality=40, max_dimension=None) == (
        b"plain",
        "text/plain",
    )


def test_transform_shrinks_jpeg_and_converts_png_to_webp() -> None:
    jpeg, jpeg_type = transform(_image_bytes("JPEG"), "image/jpeg", quality=40, max_dimension=64)
    png, png_type = transform(_image_bytes("PNG"), "image/png", quality=40, max_dimension=None)

    with Image.open(BytesIO(jpeg)) as image:
        assert max(image.size) <= 64
    assert jpeg_type == "image/jpeg"
    assert png_type == "image/webp"
    assert png
