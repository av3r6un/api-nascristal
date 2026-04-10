from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path


class CommerceMLParser:
  ID = "Ид"
  NAME = "Наименование"
  CODE = "Код"
  VALUE = "Значение"
  CATEGORY = "Категория"
  CATEGORIES = "Категории"
  PROPERTIES = "Свойства"
  PROPERTY = "Свойство"
  PROPERTY_VALUES = "ЗначенияСвойств"
  PROPERTY_VALUE = "ЗначенияСвойства"
  VALUE_TYPE = "ТипЗначений"
  VALUE_OPTIONS = "ВариантыЗначений"
  VALUE_OPTION = "Справочник"
  VALUE_ID = "ИдЗначения"
  CLASSIFIER = "Классификатор"
  CATALOG = "Каталог"
  GOODS = "Товары"
  PRODUCT = "Товар"
  DESCRIPTION = "Описание"
  IMAGE = "Картинка"
  SKU = "Артикул"
  OFFERS_PACKAGE = "ПакетПредложений"
  OFFERS = "Предложения"
  OFFER = "Предложение"
  PRICE_TYPES = "ТипыЦен"
  PRICE_TYPE = "ТипЦены"
  PRICE_TYPE_ID = "ИдТипаЦены"
  AMOUNT = "ЦенаЗаЕдиницу"
  CURRENCY = "Валюта"
  UNIT = "Единица"
  COEFFICIENT = "Коэффициент"
  QUANTITY = "Количество"

  def __init__(self, import_path: str | Path, offers_path: str | Path) -> None:
    self.import_path = Path(import_path)
    self.offers_path = Path(offers_path)
    self.import_root = ET.parse(self.import_path).getroot()
    self.offers_root = ET.parse(self.offers_path).getroot()

  def _text(self, node: ET.Element | None, default: str = "") -> str:
    if node is None or node.text is None:
      return default
    return node.text.strip()

  def _child(self, parent: ET.Element | None, tag: str) -> ET.Element | None:
    if parent is None:
      return None
    for node in parent:
      if node.tag.rsplit("}", 1)[-1] == tag:
        return node
    return None

  def _children(self, parent: ET.Element | None, tag: str) -> list[ET.Element]:
    if parent is None:
      return []
    return [node for node in parent if node.tag.rsplit("}", 1)[-1] == tag]

  def _properties(self, node: ET.Element | None) -> dict[str, dict]:
    properties: dict[str, dict] = {}
    for prop in self._children(node, self.PROPERTY):
      property_id = self._text(self._child(prop, self.ID))
      option_map: dict[str, str] = {}
      for option in self._children(self._child(prop, self.VALUE_OPTIONS), self.VALUE_OPTION):
        option_map[self._text(self._child(option, self.VALUE_ID))] = self._text(self._child(option, self.VALUE))
      properties[property_id] = {
        "id": property_id,
        "name": self._text(self._child(prop, self.NAME)),
        "value_type": self._text(self._child(prop, self.VALUE_TYPE)),
        "options": [{"id": option_id, "value": option_value} for option_id, option_value in option_map.items()],
        "option_map": option_map,
      }
    return properties

  def parse(self) -> dict:
    import_classifier = self._child(self.import_root, self.CLASSIFIER)
    import_catalog = self._child(self.import_root, self.CATALOG)
    offer_classifier = self._child(self.offers_root, self.CLASSIFIER)
    offers_package = self._child(self.offers_root, self.OFFERS_PACKAGE)

    properties = self._properties(self._child(import_classifier, self.PROPERTIES))
    properties.update(self._properties(self._child(offer_classifier, self.PROPERTIES)))

    categories = []
    for category in self._children(self._child(import_classifier, self.CATEGORIES), self.CATEGORY):
      categories.append(
        {
          "id": self._text(self._child(category, self.ID)),
          "name": self._text(self._child(category, self.NAME)),
          "property_ids": [self._text(item) for item in self._children(self._child(category, self.PROPERTIES), self.ID) if self._text(item)],
        }
      )

    price_type_names = {
      self._text(self._child(price_type, self.ID)): self._text(self._child(price_type, self.NAME))
      for price_type in self._children(self._child(offers_package, self.PRICE_TYPES), self.PRICE_TYPE)
    }

    offers: dict[str, dict] = {}
    for offer in self._children(self._child(offers_package, self.OFFERS), self.OFFER):
      offer_id = self._text(self._child(offer, self.ID))
      prices = []
      for price in self._children(self._child(offer, "Цены"), "Цена"):
        price_type_id = self._text(self._child(price, self.PRICE_TYPE_ID))
        amount_text = self._text(self._child(price, self.AMOUNT), "0").replace(",", ".")
        coefficient_text = self._text(self._child(price, self.COEFFICIENT), "1").replace(",", ".")
        prices.append(
          {
            "price_type_id": price_type_id,
            "price_type_name": price_type_names.get(price_type_id, ""),
            "amount": float(amount_text) if "." in amount_text else int(amount_text),
            "currency": self._text(self._child(price, self.CURRENCY)),
            "unit": self._text(self._child(price, self.UNIT)),
            "coefficient": float(coefficient_text) if "." in coefficient_text else int(coefficient_text),
          }
        )
      quantity_text = self._text(self._child(offer, self.QUANTITY), "0").replace(",", ".")
      offers[offer_id] = {
        "quantity": float(quantity_text) if "." in quantity_text else int(quantity_text),
        "price": next((price for price in prices if price["price_type_name"] == "Розничная цена"), prices[0] if prices else {
          "amount": 0,
          "currency": "",
          "unit": "",
          "coefficient": 1,
          "price_type_id": "",
          "price_type_name": "",
        }),
      }

    products = []
    for product in self._children(self._child(import_catalog, self.GOODS), self.PRODUCT):
      product_id = self._text(self._child(product, self.ID))
      category_id = self._text(self._child(product, self.CATEGORY))
      requisites = {
        self._text(self._child(requisite, self.NAME)): self._text(self._child(requisite, self.VALUE))
        for requisite in self._children(self._child(product, "ЗначенияРеквизитов"), "ЗначениеРеквизита")
        if self._text(self._child(requisite, self.NAME))
      }
      attributes = []
      for property_value in self._children(self._child(product, self.PROPERTY_VALUES), self.PROPERTY_VALUE):
        property_id = self._text(self._child(property_value, self.ID))
        raw_value = self._text(self._child(property_value, self.VALUE))
        resolved_value = properties.get(property_id, {}).get("option_map", {}).get(raw_value, raw_value)
        attributes.append({"property_id": property_id, "value": resolved_value})

      offer = offers.get(product_id, {"quantity": 0, "price": {"amount": 0, "currency": "", "unit": "", "coefficient": 1}})
      products.append(
        {
          "id": product_id,
          "sku": self._text(self._child(product, self.SKU)),
          "code": self._text(self._child(product, self.CODE)),
          "name": self._text(self._child(product, self.NAME)),
          "description": self._text(self._child(product, self.DESCRIPTION)),
          "image": self._text(self._child(product, self.IMAGE)) or requisites.get("ОписаниеФайла", "").split("#", 1)[0],
          "category_id": category_id,
          "attributes": attributes,
          "quantity": offer["quantity"],
          "price": {
            "amount": offer["price"]["amount"],
            "currency": offer["price"]["currency"],
            "unit": offer["price"]["unit"],
            "coefficient": offer["price"]["coefficient"],
          },
        }
      )

    return {
      "classifier_id": self._text(self._child(import_classifier, self.ID)),
      "catalog_name": self._text(self._child(import_catalog, self.NAME)),
      "properties": [
        {
          "id": prop["id"],
          "name": prop["name"],
          "options": prop["options"],
        }
        for prop in sorted(properties.values(), key=lambda item: (item["name"], item["id"]))
      ],
      "categories": sorted(categories, key=lambda item: item["name"]),
      "products": products,
    }
