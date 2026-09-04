"""Allowlisted articleSupplySource payloads. Dangerous shapes cannot be built.

Live discovery (scripts/discovery/out/): omitting version on PUT returns 200 and
overwrites blindly; ignoreMissingProperties=true is required; one unknown
property discards the whole body; articlePrices is a full-array replace;
nested price ids are valid only from the GET in this apply step.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

PUT_PARAMS: dict[str, str] = {"ignoreMissingProperties": "true"}

ALLOWED_PUT_FIELDS = frozenset(
    {
        "id",
        "version",
        "articleNumber",
        "name",
        "unitId",
        "taxRateType",
        "ean",
        "minimumPurchaseQuantity",
        "fixedPurchaseQuantity",
        "procurementLeadDays",
        "articlePrices",
        "supplierId",
    }
)
FORBIDDEN_FIELDS = frozenset({"articleId", "lastModifiedByUserId"})
PRICE_STRIP_KEYS = frozenset(
    {"createdDate", "lastModifiedDate", "lastModifiedByUserId", "version"}
)
REDUCTION_STRIP_KEYS = frozenset({"id", "version", "createdDate", "lastModifiedDate"})


class SupplySourcePayloadError(ValueError):
    pass


def _reject_forbidden(payload: Mapping[str, Any]) -> None:
    for key in payload:
        if key in FORBIDDEN_FIELDS:
            raise SupplySourcePayloadError(
                f"Forbidden articleSupplySource property {key!r}"
            )
        if key not in ALLOWED_PUT_FIELDS:
            raise SupplySourcePayloadError(
                f"Unknown articleSupplySource property {key!r}"
            )


def live_price_ids(live_get: Mapping[str, Any]) -> frozenset[str]:
    ids: set[str] = set()
    for row in live_get.get("articlePrices") or []:
        if not isinstance(row, dict):
            continue
        pid = str(row.get("id") or "").strip()
        if pid:
            ids.add(pid)
    return frozenset(ids)


def sanitize_price_row(
    row: Mapping[str, Any],
    *,
    allowed_ids: frozenset[str],
) -> dict[str, Any]:
    cleaned: dict[str, Any] = {}
    for key, value in row.items():
        if key in PRICE_STRIP_KEYS:
            continue
        if key == "id":
            pid = str(value or "").strip()
            if pid and pid in allowed_ids:
                cleaned["id"] = pid
            continue
        if key == "reductionAdditions" and isinstance(value, list):
            additions = []
            for item in value:
                if not isinstance(item, dict):
                    continue
                additions.append(
                    {
                        inner_k: inner_v
                        for inner_k, inner_v in item.items()
                        if inner_k not in REDUCTION_STRIP_KEYS
                    }
                )
            cleaned["reductionAdditions"] = additions
            continue
        cleaned[key] = value
    return cleaned


def build_supply_source_put(
    *,
    supply_source_id: str,
    version: str,
    article_number: str | None = None,
    name: str | None = None,
    unit_id: str | None = None,
    tax_rate_type: str | None = None,
    ean: str | None = None,
    minimum_purchase_quantity: Any = None,
    fixed_purchase_quantity: Any = None,
    procurement_lead_days: int | None = None,
    article_prices: list[Mapping[str, Any]] | None = None,
    live_get: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, str]]:
    """PUT body + query params. ``version`` is required; there is no default."""
    if not str(supply_source_id or "").strip():
        raise SupplySourcePayloadError("supply source id is required")
    if version is None or str(version).strip() == "":
        raise SupplySourcePayloadError(
            "version is required on every articleSupplySource PUT"
        )
    if article_prices is not None and len(article_prices) == 0:
        raise SupplySourcePayloadError(
            "articlePrices: [] deletes every price; there is no legitimate caller"
        )
    if article_prices is not None and live_get is None:
        raise SupplySourcePayloadError(
            "articlePrices requires the live GET from this apply step"
        )

    body: dict[str, Any] = {
        "id": str(supply_source_id).strip(),
        "version": str(version).strip(),
    }
    if article_number is not None:
        body["articleNumber"] = article_number
    if name is not None:
        body["name"] = name
    if unit_id is not None:
        body["unitId"] = unit_id
    if tax_rate_type is not None:
        body["taxRateType"] = tax_rate_type
    if ean is not None:
        body["ean"] = ean
    if minimum_purchase_quantity is not None:
        body["minimumPurchaseQuantity"] = minimum_purchase_quantity
    if fixed_purchase_quantity is not None:
        body["fixedPurchaseQuantity"] = fixed_purchase_quantity
    if procurement_lead_days is not None:
        body["procurementLeadDays"] = procurement_lead_days
    if article_prices is not None:
        allowed = live_price_ids(live_get or {})
        body["articlePrices"] = [
            sanitize_price_row(row, allowed_ids=allowed) for row in article_prices
        ]
    _reject_forbidden(body)
    return body, dict(PUT_PARAMS)


def build_supply_source_post(
    *,
    supplier_id: str,
    article_number: str,
    name: str,
    unit_id: str,
) -> dict[str, Any]:
    """Minimal create body (discovery B3: supplierId + articleNumber + name + unitId)."""
    if not str(unit_id or "").strip():
        raise SupplySourcePayloadError("unitId is required on create")
    body = {
        "supplierId": str(supplier_id).strip(),
        "articleNumber": str(article_number).strip(),
        "name": str(name).strip(),
        "unitId": str(unit_id).strip(),
    }
    _reject_forbidden(body)
    return body


def build_article_attach_put(
    *,
    article_id: str,
    version: str,
    supply_sources: list[Mapping[str, Any]],
    primary_supply_source_id: str,
) -> tuple[dict[str, Any], dict[str, str]]:
    if version is None or str(version).strip() == "":
        raise SupplySourcePayloadError("article version is required on attach PUT")
    if not str(primary_supply_source_id or "").strip():
        raise SupplySourcePayloadError("primarySupplySourceId is required on attach")
    cleaned_sources: list[dict[str, Any]] = []
    for item in supply_sources:
        ss_id = str(item.get("articleSupplySourceId") or "").strip()
        if not ss_id:
            continue
        entry: dict[str, Any] = {"articleSupplySourceId": ss_id}
        position = item.get("positionNumber")
        if position not in (None, ""):
            entry["positionNumber"] = int(position)
        cleaned_sources.append(entry)
    body = {
        "id": str(article_id).strip(),
        "version": str(version).strip(),
        "supplySources": cleaned_sources,
        "primarySupplySourceId": str(primary_supply_source_id).strip(),
    }
    return body, dict(PUT_PARAMS)
