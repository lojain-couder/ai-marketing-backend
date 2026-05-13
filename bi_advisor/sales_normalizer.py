from __future__ import annotations

import csv
import io
from datetime import datetime, timezone
from typing import Any


# ── Field aliases (CSV column name mapping) ───────────────────────────────────

SALES_FIELD_ALIASES: dict[str, list[str]] = {
    # Core
    "order_id":       ["order_id", "order", "invoice", "order_number", "invoice_number",
                       "order_code", "رقم الطلب", "كود الطلب", "معرف الطلب"],
    "order_date":     ["date", "order_date", "created_at", "timestamp", "issue_date",
                       "تاريخ الطلب", "التاريخ", "تاريخ"],
    "order_status":   ["order_status", "status", "الحالة", "حالة الطلب"],
    "payment_status": ["payment_status", "حالة الدفع"],
    "payment_method": ["payment_method", "payment", "طريقة الدفع"],
    # Product
    "product_id":     ["product_id", "variant_id"],
    "product_name":   ["product_name", "product", "item_name", "item", "title",
                       "المنتج", "اسم المنتج", "البضاعة"],
    "sku":            ["sku", "barcode", "product_sku", "product_code",
                       "الرمز", "SKU", "كود المنتج"],
    "quantity":       ["quantity", "qty", "items", "units",
                       "الكمية", "عدد", "الوحدات"],
    "unit_price":     ["unit_price", "price", "item_price",
                       "السعر", "سعر الوحدة"],
    "cost_price":     ["cost_price", "cost", "cogs",
                       "التكلفة", "سعر التكلفة", "تكلفة المنتج"],
    # Revenue
    "revenue":        ["revenue", "total", "sales", "amount", "net_sales",
                       "order_total", "grand_total", "line_total",
                       "الإيراد", "المبلغ", "إجمالي الطلب", "قيمة الطلب", "الإجمالي"],
    # Customer
    "customer_id":    ["customer_id", "customer", "client_id", "buyer_id",
                       "معرف العميل", "رقم العميل"],
    "customer_type":  ["customer_type", "segment", "client_type",
                       "نوع العميل"],
    "customer_city":  ["customer_city", "city", "shipping_city",
                       "المدينة", "مدينة العميل"],
    # Attribution
    "channel":        ["channel", "القناة"],
    "source":         ["source", "utm_source", "order_source",
                       "المصدر"],
    "medium":         ["medium", "utm_medium"],
    "campaign_name":  ["campaign_name", "campaign", "utm_campaign",
                       "اسم الحملة", "الحملة"],
    "platform":       ["platform", "المنصة"],
    "discount_code":  ["discount_code", "coupon", "promo_code", "كوبون"],
    "ad_spend":       ["ad_spend", "spend", "cost_per_order",
                       "الإنفاق الإعلاني", "إنفاق إعلاني"],
}

_CANCELLED = {"cancelled", "canceled", "ملغي", "ملغاة", "returned", "مرتجع", "refunded"}


# ── Zid API normalizer ────────────────────────────────────────────────────────

def normalize_zid_orders(orders: list[dict]) -> list[dict]:
    """
    Expand Zid API orders into one row per product line item.
    Skips cancelled and fraudulent orders.
    """
    rows = []
    for order in orders:
        if not isinstance(order, dict):
            continue

        status_raw   = order.get("order_status") or {}
        order_status = _s(
            status_raw.get("code") if isinstance(status_raw, dict) else status_raw
        ).lower()

        if order_status in _CANCELLED or order.get("is_potential_fraud"):
            continue

        payment_raw = order.get("payment") or {}
        shipping    = order.get("shipping") or {}
        address     = shipping.get("address") or {}
        city_raw    = address.get("city") or {}
        customer    = order.get("customer") or {}

        base = {
            "order_id":       _s(order.get("id") or order.get("code")),
            "order_date":     _parse_date(_s(order.get("created_at") or order.get("issue_date"))),
            "order_status":   order_status,
            "payment_status": _s(order.get("payment_status")).lower(),
            "payment_method": _s(
                payment_raw.get("method") if isinstance(payment_raw, dict)
                else order.get("payment_method")
            ),
            "customer_id":    _s(customer.get("id")),
            "customer_type":  _s(customer.get("type")),
            "customer_city":  _s(city_raw.get("name") if isinstance(city_raw, dict) else city_raw),
            "source":         _s(order.get("source_code") or order.get("source")),
            "channel":        _s(order.get("source_code") or order.get("source")),
            "platform":       "zid",
            "campaign_name":  "",
            "ad_spend":       0.0,
            "product_views":  0,
            "product_rating": 0.0,
        }

        products = order.get("products") or []
        if products:
            for p in products:
                if not isinstance(p, dict):
                    continue
                row = dict(base)
                row.update({
                    "product_name":  _s(p.get("name")),
                    "sku":           _s(p.get("sku") or p.get("barcode")),
                    "quantity":      _to_float(p.get("quantity")) or 1.0,
                    "unit_price":    _to_float(p.get("price")),
                    "revenue":       _to_float(p.get("total") or p.get("discounted_total")),
                    "cost_price":    0.0,
                    "is_discounted": bool(p.get("is_discounted")),
                    "discount_pct":  _to_float(p.get("discount_percentage")),
                })
                rows.append(row)
        else:
            base.update({
                "product_name":  "",
                "sku":           "",
                "quantity":      1.0,
                "unit_price":    _to_float(order.get("order_total")),
                "revenue":       _to_float(order.get("order_total")),
                "cost_price":    0.0,
                "is_discounted": False,
                "discount_pct":  0.0,
            })
            rows.append(base)

    return rows


# ── Salla API normalizer ──────────────────────────────────────────────────────

def normalize_salla_orders(orders: list[dict]) -> list[dict]:
    """
    Expand Salla API orders into one row per item.
    Skips cancelled and draft orders.
    """
    rows = []
    for order in orders:
        if not isinstance(order, dict):
            continue

        status_raw   = order.get("status") or {}
        order_status = _s(
            status_raw.get("slug") if isinstance(status_raw, dict) else status_raw
        ).lower()

        if order_status in _CANCELLED or order.get("draft"):
            continue

        payment_status = "pending" if order.get("is_pending_payment") else "paid"
        total_raw      = order.get("total") or {}
        total_amt      = _to_float(
            total_raw.get("amount") if isinstance(total_raw, dict) else total_raw
        )
        date_raw   = order.get("date") or {}
        order_date = _parse_date(
            _s(date_raw.get("date") if isinstance(date_raw, dict) else date_raw)
        )
        customer = order.get("customer") or {}
        city_raw = customer.get("city") or {}

        base = {
            "order_id":       _s(order.get("id") or order.get("reference_id")),
            "order_date":     order_date,
            "order_status":   order_status,
            "payment_status": payment_status,
            "payment_method": _s(order.get("payment_method")),
            "customer_id":    _s(customer.get("id")),
            "customer_type":  "",
            "customer_city":  _s(city_raw.get("name") if isinstance(city_raw, dict) else city_raw),
            "source":         "salla",
            "channel":        "salla",
            "platform":       "salla",
            "campaign_name":  "",
            "ad_spend":       0.0,
            "product_views":  0,
            "product_rating": 0.0,
        }

        items = order.get("items") or []
        if items:
            per_item_rev = total_amt / len(items)
            for item in items:
                if not isinstance(item, dict):
                    continue
                price_raw = item.get("price") or {}
                row = dict(base)
                row.update({
                    "product_name":  _s(item.get("name")),
                    "sku":           _s(item.get("sku") or ""),
                    "quantity":      _to_float(item.get("quantity")) or 1.0,
                    "unit_price":    _to_float(
                        price_raw.get("amount") if isinstance(price_raw, dict) else price_raw
                    ),
                    "revenue":       per_item_rev,
                    "cost_price":    0.0,
                    "is_discounted": False,
                    "discount_pct":  0.0,
                })
                rows.append(row)
        else:
            base.update({
                "product_name":  "",
                "sku":           "",
                "quantity":      1.0,
                "unit_price":    total_amt,
                "revenue":       total_amt,
                "cost_price":    0.0,
                "is_discounted": False,
                "discount_pct":  0.0,
            })
            rows.append(base)

    return rows


# ── CSV normalizer ────────────────────────────────────────────────────────────

def normalize_sales_rows(
    raw_sales_data: list[dict[str, Any]] | str | None,
) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    """Main entry point for CSV / list data. Returns (rows, warnings, missing_fields)."""
    raw = _coerce_sales_rows(raw_sales_data)
    warnings: list[str] = []
    normalized: list[dict[str, Any]] = []

    col_map = _build_column_map(list(raw[0].keys())) if raw else {}

    for index, row in enumerate(raw):
        if not isinstance(row, dict):
            warnings.append(f"Skipped sales row {index + 1} because it is not an object.")
            continue
        normalized.append(_normalize_single_sales_row(row, col_map))

    missing_important = _missing_sales_fields(normalized)
    if not normalized:
        warnings.append("No usable sales rows were provided.")

    return normalized, warnings, missing_important


def _coerce_sales_rows(raw: list[dict[str, Any]] | str | None) -> list[dict[str, Any]]:
    if raw is None:
        return []
    if isinstance(raw, list):
        return raw
    if isinstance(raw, str):
        reader = csv.DictReader(io.StringIO(raw))
        return list(reader)
    return []


def _build_column_map(csv_cols: list[str]) -> dict[str, str]:
    lower = {c.lower().strip(): c for c in csv_cols}
    mapping: dict[str, str] = {}
    for internal, aliases in SALES_FIELD_ALIASES.items():
        for alias in aliases:
            hit = lower.get(alias.lower().strip())
            if hit:
                mapping[internal] = hit
                break
    return mapping


def _normalize_single_sales_row(row: dict[str, Any], col_map: dict[str, str] | None = None) -> dict[str, Any]:
    def get(key: str) -> str | None:
        if col_map:
            csv_col = col_map.get(key)
            if csv_col:
                val = row.get(csv_col)
                if val not in (None, ""):
                    return str(val)
        # Fallback: original alias scan
        return _find_value(row, key)

    revenue = _to_float(get("revenue"))
    quantity = _to_float(get("quantity")) or 1.0
    unit_price = _to_float(get("unit_price"))

    # Derive revenue from qty × price if not present
    if not revenue and unit_price:
        revenue = quantity * unit_price

    return {
        "order_id":       get("order_id"),
        "order_date":     _parse_date(get("order_date")),
        "order_status":   _s(get("order_status")).lower(),
        "payment_status": _s(get("payment_status")).lower(),
        "payment_method": _s(get("payment_method")),
        "product_id":     get("product_id"),
        "product_name":   _s(get("product_name")),
        "sku":            _s(get("sku")),
        "quantity":       quantity,
        "unit_price":     unit_price,
        "cost_price":     _to_float(get("cost_price")),
        "revenue":        revenue,
        "is_discounted":  False,
        "discount_pct":   0.0,
        "customer_id":    get("customer_id"),
        "customer_type":  _s(get("customer_type")),
        "customer_city":  _s(get("customer_city")),
        "channel":        _s(get("channel")),
        "source":         _s(get("source")),
        "medium":         _s(get("medium")),
        "platform":       _s(get("platform")),
        "campaign_name":  _s(get("campaign_name")),
        "discount_code":  _s(get("discount_code")),
        "ad_spend":       _to_float(get("ad_spend")),
        "product_views":  0,
        "product_rating": 0.0,
    }


def filter_valid_rows(rows: list[dict]) -> list[dict]:
    """Remove cancelled orders from analysis."""
    return [r for r in rows if _s(r.get("order_status")).lower() not in _CANCELLED]


def enrich_with_product_catalog(
    sales_rows: list[dict],
    catalog: list[dict],
) -> list[dict]:
    """
    Attach cost_price, product_views, and product_rating from a product catalog.
    Matches by SKU first, then by product name.
    """
    sku_map  = {_s(p.get("sku")):         p for p in catalog if p.get("sku")}
    name_map = {_s(p.get("name")).lower(): p for p in catalog if p.get("name")}

    for row in sales_rows:
        match = (
            sku_map.get(_s(row.get("sku")))
            or name_map.get(_s(row.get("product_name")).lower())
        )
        if match:
            if not row.get("cost_price"):
                row["cost_price"] = _to_float(match.get("cost_price"))
            rating = match.get("rating") or {}
            row["product_views"]  = int(match.get("views") or 0)
            row["product_rating"] = float(
                rating.get("rate") if isinstance(rating, dict) else (rating or 0)
            )

    return sales_rows


# ── Shared helpers ────────────────────────────────────────────────────────────

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
    aliases = SALES_FIELD_ALIASES.get(field_name, [])
    for alias in aliases:
        for key, value in row.items():
            if key and alias.lower() in str(key).lower() and value not in (None, ""):
                return str(value)
    return None


def _parse_date(value: Any) -> str | None:
    if value in (None, ""):
        return None
    raw = str(value).strip()
    for candidate in [raw, raw.replace("Z", "+00:00")]:
        try:
            parsed = datetime.fromisoformat(candidate)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.isoformat()
        except ValueError:
            continue
    for pattern in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%m/%d/%Y", "%d/%m/%Y",
                    "%d-%m-%Y", "%Y/%m/%d"):
        try:
            parsed = datetime.strptime(raw, pattern).replace(tzinfo=timezone.utc)
            return parsed.isoformat()
        except ValueError:
            continue
    return None


def _to_float(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    try:
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return 0.0


def _s(v: Any) -> str:
    return "" if v is None else str(v).strip()
