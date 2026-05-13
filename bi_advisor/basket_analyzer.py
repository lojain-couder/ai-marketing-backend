"""
Basket Analysis — finds products frequently bought together in the same order.
Suggests bundle content ideas for the merchant.
"""

from __future__ import annotations
from collections import defaultdict
from itertools import combinations


def find_product_bundles(sales_rows: list[dict], min_support: int = 2) -> dict:
    """
    Find product pairs that appear together in the same order.
    Returns top bundles sorted by co-occurrence count.
    """
    if not sales_rows:
        return {"available": False, "reason": "no_sales_data"}

    # Group products by order_id
    order_products: dict[str, set] = defaultdict(set)
    for row in sales_rows:
        order_id = (row.get("order_id") or "").strip()
        product  = (row.get("product_name") or "").strip()
        if order_id and product:
            order_products[order_id].add(product)

    multi_product_orders = {oid: prods for oid, prods in order_products.items() if len(prods) >= 2}

    if not multi_product_orders:
        return {
            "available": False,
            "reason":    "no_multi_product_orders",
            "note_ar":   "لا توجد طلبات تحتوي على أكثر من منتج واحد — يحتاج البيانات order_id",
        }

    # Count pair co-occurrences
    pair_count: dict[tuple, int] = defaultdict(int)
    for products in multi_product_orders.values():
        for pair in combinations(sorted(products), 2):
            pair_count[pair] += 1

    bundles = [
        {
            "product_a":  pair[0],
            "product_b":  pair[1],
            "co_orders":  count,
            "bundle_tip_ar": (
                f"ينصح بعمل محتوى يجمع «{pair[0]}» و«{pair[1]}» — "
                f"اشتُريا معاً في {count} طلب"
            ),
        }
        for pair, count in pair_count.items()
        if count >= min_support
    ]
    bundles.sort(key=lambda x: x["co_orders"], reverse=True)
    top = bundles[:8]

    total_multi = len(multi_product_orders)
    total_orders = len(order_products)

    return {
        "available":            True,
        "multi_product_orders": total_multi,
        "total_orders":         total_orders,
        "multi_order_pct":      round(total_multi / total_orders * 100, 1) if total_orders > 0 else 0.0,
        "bundles":              top,
        "summary_ar":           _bundle_summary_ar(top, total_multi),
    }


def _bundle_summary_ar(bundles: list[dict], multi_orders: int) -> str:
    if not bundles:
        return "لا توجد أنماط شراء مشتركة واضحة بعد."
    top = bundles[0]
    return (
        f"أكثر منتجَين يُشتريان معاً: «{top['product_a']}» و«{top['product_b']}» "
        f"في {top['co_orders']} طلب — اعملي محتوى bundle لهما لرفع متوسط قيمة الطلب."
    )
