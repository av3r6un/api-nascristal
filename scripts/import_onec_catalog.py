from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from sqlalchemy import select


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
  sys.path.insert(0, str(REPO_ROOT))

from src.core.database import session_maker
from src.models.onec_catalog import Property
from src.services.onec_import import import_catalog, parse_catalog


def _build_parser() -> argparse.ArgumentParser:
  parser = argparse.ArgumentParser(description="Import CommerceML catalog data into the configured database.")
  parser.add_argument(
    "--import-path",
    default=str(REPO_ROOT / "1c_exchange" / "import.xml"),
    help="Path to CommerceML import.xml",
  )
  parser.add_argument(
    "--offers-path",
    default=str(REPO_ROOT / "1c_exchange" / "offers.xml"),
    help="Path to CommerceML offers.xml",
  )
  parser.add_argument(
    "--exchange-type",
    default="catalog",
    help="Import run exchange type",
  )
  return parser


async def _run(import_path: Path, offers_path: Path, exchange_type: str) -> None:
  if not import_path.exists():
    raise FileNotFoundError(f"import.xml not found: {import_path}")
  if not offers_path.exists():
    raise FileNotFoundError(f"offers.xml not found: {offers_path}")

  async with session_maker() as session:
    parsed = parse_catalog(import_path, offers_path)
    summary = await import_catalog(
      session,
      import_path=import_path,
      offers_path=offers_path,
      exchange_type=exchange_type,
    )
    imported_properties = (await session.execute(select(Property))).scalars().all()

  source_property_ids = {item["id"] for item in parsed.get("properties", []) if item.get("id")}
  source_properties_without_options = {
    item["id"]
    for item in parsed.get("properties", [])
    if item.get("id") and not item.get("options")
  }
  imported_property_ids = {item.eid for item in imported_properties}
  imported_properties_without_options = {
    item.eid
    for item in imported_properties
    if item.eid in source_properties_without_options
  }
  missing_property_ids = sorted(source_property_ids - imported_property_ids)
  properties_with_parent_category = sum(1 for item in imported_properties if item.parent_category_id is not None)

  print(f"import_run_id={summary.import_run_id}")
  print(f"categories={summary.categories}")
  print(f"properties={summary.properties}")
  print(f"property_options={summary.property_options}")
  print(f"products={summary.products}")
  print(f"product_images={summary.product_images}")
  print(f"product_attributes={summary.product_attributes}")
  print(f"offers={summary.offers}")
  print(f"source_properties={len(source_property_ids)}")
  print(f"source_properties_without_options={len(source_properties_without_options)}")
  print(f"imported_properties_without_options={len(imported_properties_without_options)}")
  print(f"properties_with_parent_category={properties_with_parent_category}")
  print(f"missing_properties={len(missing_property_ids)}")
  if missing_property_ids:
    print(f"missing_property_ids={','.join(missing_property_ids)}")


def main() -> None:
  args = _build_parser().parse_args()
  asyncio.run(
    _run(
      import_path=Path(args.import_path),
      offers_path=Path(args.offers_path),
      exchange_type=args.exchange_type,
    )
  )


if __name__ == "__main__":
  main()
