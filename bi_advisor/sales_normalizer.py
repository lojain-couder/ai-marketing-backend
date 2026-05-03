from __future__ import annotations

import csv
import io
from datetime import datetime, timezone
from typing import Any


SALES_FIELD_ALIASES = {
    "order_id": ["order_id", "order", "invoice"],
    "order_date": ["date", "order_date", "created_at", "timestamp"],
    "product_id": ["product_id", "sku", "variant_id"],
    "product_name": ["product_name", "product", "item_name", "title"],
    "quantity": ["quantity", "qty", "items"],
    "revenue": ["revenue", "total", "sales", "amount", "net_sales"],
    "customer_id": ["customer_id", "customer"],
    "customer_type": ["customer_type", "segment"],
    "channel": ["channel"],
    "discount_code": ["discount_code", "coupon", "promo_code"],
    "campaign_name": ["campaign_name", "campaign"],
    "platform": ["platform"],
    "source": ["source", "utm_source"],
    "medium": ["medium", "utm_medium"],
}


def normalize_sales_rows(
    raw_sales_data: list[dict[str, Any]] | str | None,
) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    rows = _coerce_sales_rows(raw_sales_data)
    warnings: list[str] = []
    normalized: list[dict[str, Any]] = []

    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            warnings.append(f"Skipped sales row {index + 1} because it is not an object.")
            continue
        normalized.append(_normalize_single_sales_row(row))

    missing_important = _missing_sales_fields(normalized)
    if not normalized:
        warnings.append("No usable sales rows were provided.")

    return normalized, warnings, missing_important


def _coerce_sales_rows(raw_sales_data: list[dict[str, Any]] | str | None) -> list[dict[str, Any]]:
    if raw_sales_data is None:
        return []
    if isinstance(raw_sales_data, list):
        return raw_sales_data
    if isinstance(raw_sales_data, str):
        reader = csv.DictReader(io.StringIO(raw_sales_data))
        return list(reader)
    return []


def _normalize_single_sales_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "order_id": _find_value(row, "order_id"),
        "order_date": _parse_date(_find_value(row, "order_date")),
        "product_id": _find_value(row, "product_id"),
        "product_name": _find_value(row, "product_name"),
        "quantity": _to_int(_find_value(row, "quantity")),
        "revenue": _to_float(_find_value(row, "revenue")),
        "customer_id": _find_value(row, "customer_id"),
        "customer_type": _find_value(row, "customer_type"),
        "channel": _find_value(row, "channel"),
        "discount_code": _find_value(row, "discount_code"),
        "campaign_name": _find_value(row, "campaign_name"),
        "platform": _find_value(row, "platform"),
        "source": _find_value(row, "source"),
        "medium": _find_value(row, "medium"),
    }


def _missing_sales_fields(rows: list[dict[str, Any]]) -> list[str]:
    if not rows:
        return ["date", "revenue", "order_id or quantity"]

    missing: list[str] = []
    if not any(row.get("order_date") for row in rows):
        missing.append("date")
    if not any((row.get("revenue") or 0) > 0 for row in rows):
        missing.append("revenue")
    if not any(row.get("order_id") or (row.get("quantity") or 0) > 0 for row in rows):
        missing.append("order_id or quantity")
    if not any(row.get("product_name") for row in rows):
        missing.append("product_name")
    return missing


def _find_value(row: dict[str, Any], field_name: str) -> str | None:
    aliases = SALES_FIELD_ALIASES[field_name]
    for alias in aliases:
        for key, value in row.items():
            if key and alias in str(key).lower() and value not in (None, ""):
                return str(value)
    return None


def _parse_date(value: Any) -> str | None:
    if value in (None, ""):
        return None
    raw = str(value).strip()
    candidates = [raw, raw.replace("Z", "+00:00")]
    for candidate in candidates:
        try:
            parsed = datetime.fromisoformat(candidate)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.isoformat()
        except ValueError:
            continue
    for pattern in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%m/%d/%Y", "%d/%m/%Y"):
        try:
            parsed = datetime.strptime(raw, pattern)
            parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.isoformat()
        except ValueError:
            continue
    return None


def _to_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _to_float(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
