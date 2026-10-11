"""Image validation and compression for event cover photos.

Nigerian mobile data is slow and expensive, so every upload is resized and
re-encoded to WebP before it ever reaches storage. Re-encoding also strips EXIF
metadata (including GPS coordinates) and neutralizes polyglot/malformed files.
"""
import io

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from PIL import Image, ImageOps, UnidentifiedImageError

ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}
MAX_WIDTH = 1280
MAX_HEIGHT = 1280
MAX_PIXELS = 40_000_000  # decompression-bomb guard


def process_cover_image(uploaded_file):
    """Validate an uploaded image and return a compressed WebP ContentFile."""
    if uploaded_file.size > settings.MAX_UPLOAD_BYTES:
        raise ValidationError("Image is too large. Maximum size is 8 MB.")

    Image.MAX_IMAGE_PIXELS = MAX_PIXELS
    try:
        uploaded_file.seek(0)
        img = Image.open(uploaded_file)
        if img.format not in ALLOWED_FORMATS:
            raise ValidationError("Upload a JPG, PNG or WebP image.")
        img.load()  # fully decode now so corrupt files fail here
    except ValidationError:
        raise
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, SyntaxError):
        raise ValidationError("That file isn't a valid image.")

    img = ImageOps.exif_transpose(img)  # respect phone camera orientation
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGB")
    img.thumbnail((MAX_WIDTH, MAX_HEIGHT), Image.LANCZOS)

    buffer = io.BytesIO()
    img.save(buffer, format="WEBP", quality=80, method=4)  # no exif passed -> metadata stripped
    return ContentFile(buffer.getvalue(), name="cover.webp")
