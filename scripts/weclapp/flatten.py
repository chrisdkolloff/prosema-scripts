"""Flatten weclapp API records for tabular export."""

from __future__ import annotations

import json
from typing import Any


def _custom_attribute_value(entry: dict[str, Any]) -> str:
    for key in (
        "stringValue",
        "numberValue",
        "booleanValue",
        "dateValue",
        "selectedValueId",
        "entityId",
        "entityReferences",
    ):
        if key not in entry:
            continue
        value = entry[key]
        if value is None:
            continue
        if isinstance(value, (list, dict)):
            return json.dumps(value, ensure_ascii=False)
        return str(value)
    return ""


def flatten_article(
    article: dict[str, Any],
    *,
    attribute_labels: dict[str, str],
) -> dict[str, str]:
    row: dict[str, str] = {}

    for key, value in article.items():
        if key == "customAttributes":
            continue
        if isinstance(value, (list, dict)):
            row[key] = json.dumps(value, ensure_ascii=False) if value else ""
        elif value is None:
            row[key] = ""
        elif isinstance(value, bool):
            row[key] = "true" if value else "false"
        else:
            row[key] = str(value)

    for entry in article.get("customAttributes") or []:
        if not isinstance(entry, dict):
            continue
        attr_id = str(entry.get("attributeDefinitionId", "")).strip()
        if not attr_id:
            continue
        label = attribute_labels.get(attr_id, f"attr_{attr_id}")
        row[f"attr_{label}"] = _custom_attribute_value(entry)

    return row


def build_column_order(rows: list[dict[str, str]]) -> list[str]:
    preferred = (
        "id",
        "articleNumber",
        "name",
        "active",
        "articleType",
        "matchCode",
        "ean",
        "shortDescription1",
        "longText",
        "unitId",
        "articleCategoryId",
        "primarySupplySourceId",
        "createdDate",
        "lastModifiedDate",
        "articleNetWeight",
        "articleLength",
        "articleHeight",
        "availableInSale",
        "taxRateType",
    )
    all_keys = {key for row in rows for key in row}
    attr_columns = sorted(key for key in all_keys if key.startswith("attr_"))
    other_columns = sorted(
        key for key in all_keys if key not in preferred and not key.startswith("attr_")
    )
    return [key for key in preferred if key in all_keys] + other_columns + attr_columns
