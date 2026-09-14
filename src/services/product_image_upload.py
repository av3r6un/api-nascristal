from __future__ import annotations

import asyncio
import io
import re
import uuid
from pathlib import PurePosixPath

from minio import Minio
from PIL import Image, ImageOps, UnidentifiedImageError

from src.core.config import settings
from src.services.moysklad_client import MoySkladClient

IMAGE_CHARACTERISTIC = "ID Изображения"
MAX_IMAGE_SIZE = 10 * 1024 * 1024


class ProductImageUploadError(ValueError):
  pass


def _category_folder(name: str) -> str:
  transliteration = str.maketrans({
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "yo",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sch", "ъ": "",
    "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
  })
  value = name.lower().translate(transliteration)
  value = re.sub(r"[^a-z0-9.-]+", "-", value).strip(".-_")
  return value or "uncategorized"


class ProductImageUploadService:
  def __init__(self, *, s3_client: Minio | None = None) -> None:
    self.s3 = s3_client or Minio(
      settings.S3_ENDPOINT,
      access_key=settings.S3_ACCESS_KEY,
      secret_key=settings.S3_SECRET_KEY,
      secure=True,
    )

  async def upload_for_variant(self, *, client: MoySkladClient, variant_id: uuid.UUID,
                               category_name: str, content: bytes, content_type: str) -> dict[str, str]:
    if not content:
      raise ProductImageUploadError("Image is empty")
    if len(content) > MAX_IMAGE_SIZE:
      raise ProductImageUploadError("Image is too large")
    if content_type not in {"image/jpeg", "image/png", "image/webp", "image/gif"}:
      raise ProductImageUploadError("Unsupported image type")
    try:
      content = await asyncio.to_thread(self._convert_to_webp, content)
    except (UnidentifiedImageError, OSError, ValueError) as exc:
      raise ProductImageUploadError("Invalid image") from exc

    object_key = str(PurePosixPath("products", _category_folder(category_name)) / f"{uuid.uuid4()}.webp")
    await asyncio.to_thread(self.s3.put_object, settings.S3_BUCKET, object_key, io.BytesIO(content),
                            length=len(content), content_type="image/webp",
                            metadata={"Cache-Control": "public, max-age=31536000, immutable"})
    try:
      variant = await client.get(f"/entity/variant/{variant_id}")
      characteristics = variant.get("characteristics", []) if isinstance(variant, dict) else []
      if not isinstance(characteristics, list):
        characteristics = []
      image_characteristic = next((item for item in characteristics if isinstance(item, dict) and
        str(item.get("name", "")).strip().casefold() == IMAGE_CHARACTERISTIC.casefold()), None)
      if image_characteristic is None:
        metadata = await client.get("/entity/variant/metadata")
        definitions = metadata.get("characteristics", []) if isinstance(metadata, dict) else []
        definition = next((item for item in definitions if isinstance(item, dict) and
          str(item.get("name", "")).strip().casefold() == IMAGE_CHARACTERISTIC.casefold()), None)
        if not isinstance(definition, dict) or not definition.get("id"):
          raise ProductImageUploadError(f'MoySklad characteristic "{IMAGE_CHARACTERISTIC}" is not configured')
        image_characteristic = {
          "id": definition["id"],
          "name": definition.get("name") or IMAGE_CHARACTERISTIC,
          "value": object_key,
        }
        characteristics.append(image_characteristic)
      else:
        image_characteristic["value"] = object_key
      await client.update("variant", str(variant_id), {"characteristics": characteristics})
    except Exception:
      await asyncio.to_thread(self.s3.remove_object, settings.S3_BUCKET, object_key)
      raise
    return {"object_key": object_key, "url": f"{settings.S3_DOMAIN.rstrip('/')}/{object_key}"}

  @staticmethod
  def _convert_to_webp(source: bytes, quality: int = 82) -> bytes:
    with Image.open(io.BytesIO(source)) as image:
      image = ImageOps.exif_transpose(image)
      icc_profile = image.info.get("icc_profile")
      exif = image.info.get("exif")
      if image.mode not in ("RGB", "RGBA"):
        image = image.convert("RGB")
      output = io.BytesIO()
      save_options = {"format": "WEBP", "quality": quality, "method": 6, "optimize": True}
      if icc_profile:
        save_options["icc_profile"] = icc_profile
      if exif:
        save_options["exif"] = exif
      image.save(output, **save_options)
      return output.getvalue()
