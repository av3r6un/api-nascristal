from minio.datatypes import Object
from PIL import Image, ImageOps
from dotenv import load_dotenv
from minio import Minio
from io import BytesIO
from itertools import islice
from pathlib import Path
import logging
import os
import io


def create_logger(max_objects: int | None) -> logging.Logger:
  """Log limited runs to console and full runs to optimization.log."""
  logger = logging.getLogger("s3_storage_optimizer")
  logger.setLevel(logging.INFO)
  logger.propagate = False

  for handler in logger.handlers[:]:
    handler.close()
    logger.removeHandler(handler)

  if max_objects is not None:
    handler: logging.Handler = logging.StreamHandler()
  else:
    log_path = Path(__file__).resolve().with_name("optimization.log")
    handler = logging.FileHandler(log_path, encoding="utf-8")

  handler.setFormatter(logging.Formatter(
    fmt="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
  ))
  logger.addHandler(handler)
  return logger


def format_size(size: int) -> str:
  value = float(size)
  for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
    if abs(value) < 1024 or unit == "TiB":
      return f"{value:.2f} {unit}"
    value /= 1024



class S3Optimizer:
  client: Minio | None = None
  logger: logging.Logger | None = None
  
  def __init__(self, env_path) -> None:
    if not env_path or not os.path.exists(env_path):
      raise FileNotFoundError('ENV FILE NOT FOUND!')
    load_dotenv(env_path)
    self.create_client()
  
  def create_client(self, region='ru-1'):
    self.client = Minio(
      endpoint='s3.twcstorage.ru',
      access_key=os.getenv('S3_ACCESS_KEY'),
      secret_key=os.getenv('S3_SECRET_KEY'),
      region=region,
      secure=True
    )
    if self.logger:
      self.logger.info("S3 client created: endpoint=s3.twcstorage.ru region=%s", region)

  def _get_bucket_objects(self, prefix: str = '', recursive: bool = True) -> list[Object]:
    self.logger.info("Listing objects: prefix=%r recursive=%s", prefix, recursive)
    return self.client.list_objects(
      bucket_name=os.getenv('S3_BUCKET'),
      prefix=prefix,
      recursive=recursive,
    )
    
  def _convert_jpg_to_webp(self, source: bytes, quality: int = 82) -> bytes:
    self.logger.info("Converting JPEG to WebP: source_size=%d quality=%d", len(source), quality)
    with Image.open(io.BytesIO(source)) as image:
      if image.format != "JPEG":
        raise ValueError("Object has .jpg extension but is not JPEG")

      image = ImageOps.exif_transpose(image)

      icc_profile = image.info.get("icc_profile")
      exif = image.info.get("exif")

      if image.mode not in ("RGB", "RGBA"):
        image = image.convert("RGB")

      output = io.BytesIO()
      image.save(
        output,
        format="WEBP",
        quality=quality,
        method=6,
        optimize=True,
        icc_profile=icc_profile,
        exif=exif,
      )
      result = output.getvalue()
      self.logger.info("Conversion completed: target_size=%d", len(result))
      return result
  
  def _download_object(self, object_name: str) -> bytes:
    self.logger.info("Downloading object: %s", object_name)
    response = self.client.get_object(os.getenv('S3_BUCKET'), object_name)
    try:
      content = response.read()
      self.logger.info("Object downloaded: %s size=%d", object_name, len(content))
      return content
    finally:
      response.close()
      response.release_conn()

  def _upload_webp(self, object_name: str, content: bytes) -> bool:
    self.logger.info("Uploading WebP: %s size=%d", object_name, len(content))
    self.client.put_object(
      bucket_name=os.getenv('S3_BUCKET'),
      object_name=object_name,
      data=BytesIO(content),
      length=len(content),
      content_type="image/webp",
      metadata={
        "Cache-Control": "public, max-age=31536000, immutable",
      },
    )
    self.logger.info("WebP uploaded: %s", object_name)
    return True
  
  def _check_existence(self, object_name) -> bool:
    self.logger.info("Checking uploaded object: %s", object_name)
    stat = self.client.stat_object(bucket_name=os.getenv('S3_BUCKET'), object_name=object_name)
    valid = stat.size > 0 and stat.content_type == 'image/webp'
    self.logger.info(
      "Object check completed: %s size=%d content_type=%s valid=%s",
      object_name, stat.size, stat.content_type, valid,
    )
    return valid

  def _remove_old(self, object_name) -> bool:
    self.logger.info("Removing source object: %s", object_name)
    self.client.remove_object(bucket_name=os.getenv('S3_BUCKET'), object_name=object_name)
    self.logger.info("Source object removed: %s", object_name)
    return True

  def run(self, max_objects: int | None = 10) -> None:
    self.logger = create_logger(max_objects)
    self.logger.info("Optimization started: max_objects=%s", max_objects)

    objects = self._get_bucket_objects()
    cut = islice(objects, max_objects) if max_objects is not None else objects
    processed = 0
    skipped = 0
    failed = 0
    source_bytes = 0
    optimized_bytes = 0

    for obj in cut:
      skey = obj.object_name
      if not skey.lower().endswith(('.jpg', '.jpeg')):
        self.logger.info("Skipping non-JPEG object: %s", skey)
        skipped += 1
        continue

      try:
        target_key = skey.rsplit(".", 1)[0] + ".webp"
        self.logger.info("Processing object: source=%s target=%s", skey, target_key)
        jpg = self._download_object(skey)
        webp = self._convert_jpg_to_webp(jpg)
        self._upload_webp(target_key, webp)

        if self._check_existence(target_key):
          self._remove_old(skey)
          processed += 1
          source_size = len(jpg)
          optimized_size = len(webp)
          saved = source_size - optimized_size
          saved_percent = (saved / source_size * 100) if source_size else 0
          source_bytes += source_size
          optimized_bytes += optimized_size
          self.logger.info(
            "Space result: object=%s source=%s webp=%s saved=%s (%.2f%%)",
            skey,
            format_size(source_size),
            format_size(optimized_size),
            format_size(saved),
            saved_percent,
          )
        else:
          failed += 1
          self.logger.error("Uploaded object failed validation; source preserved: %s", skey)
      except Exception:
        failed += 1
        self.logger.exception("Object processing failed; source preserved: %s", skey)

    saved_bytes = source_bytes - optimized_bytes
    saved_percent = (saved_bytes / source_bytes * 100) if source_bytes else 0
    self.logger.info(
      "Optimization finished: processed=%d skipped=%d failed=%d "
      "source=%s webp=%s saved=%s (%.2f%%)",
      processed,
      skipped,
      failed,
      format_size(source_bytes),
      format_size(optimized_bytes),
      format_size(saved_bytes),
      saved_percent,
    )
    

if __name__ == '__main__':
  s3 = S3Optimizer('../src/.env')
  s3.run(None)
