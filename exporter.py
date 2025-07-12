import os
import time
import logging
from datetime import datetime, timedelta
import requests
from prometheus_client import start_http_server, Gauge

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)

# Read configuration from environment variables
SQUARE_TOKEN    = os.getenv("SQUARE_ACCESS_TOKEN")
LOCATION_ID     = os.getenv("SQUARE_LOCATION_ID")
EXPORTER_PORT   = int(os.getenv("EXPORTER_PORT", "8000"))
SCRAPE_WINDOW_H = int(os.getenv("SCRAPE_WINDOW_H", "24"))
API_BASE        = "https://connect.squareup.com/v2"

if not SQUARE_TOKEN or not LOCATION_ID:
    logger.error("Environment variables SQUARE_ACCESS_TOKEN and SQUARE_LOCATION_ID must be set.")
    raise RuntimeError("Please set SQUARE_ACCESS_TOKEN and SQUARE_LOCATION_ID")

# HTTP headers for Square API
HEADERS = {
    "Square-Version": "2023-07-20",
    "Authorization": f"Bearer {SQUARE_TOKEN}",
    "Content-Type": "application/json"
}

# Fetch account currency automatically via Locations API
def get_account_currency():
    """Retrieve the currency code for the configured location."""
    url = f"{API_BASE}/locations/{LOCATION_ID}"
    response = requests.get(url, headers=HEADERS)
    response.raise_for_status()
    loc = response.json().get("location", {})
    return loc.get("currency", "")

CURRENCY = get_account_currency()
logger.info("Detected account currency: %s", CURRENCY)

# Define Prometheus metrics
# 24h window metrics
g_pay_count       = Gauge("square_payments_count_24h", "Number of payments in the last 24h")
g_pay_value       = Gauge("square_payments_value_24h", "Total value of payments in the last 24h (in minor currency units)")
g_avg_value       = Gauge("square_payments_avg_value_24h", "Average payment value in the last 24h (in minor currency units)")
g_refund_count    = Gauge("square_refunds_count_24h", "Number of refunds in the last 24h")
g_refund_value    = Gauge("square_refunds_value_24h", "Total value of refunds in the last 24h (in minor currency units)")
# Product breakdown metrics for 24h
product_count_24h = Gauge("square_payments_count_24h_by_product", "Number of items sold in the last 24h", ["product_name"])
product_value_24h = Gauge("square_payments_value_24h_by_product", "Value of items sold in the last 24h (in minor currency units)", ["product_name"])
# Month-to-date metrics
g_pay_count_mtd   = Gauge("square_payments_count_mtd", "Number of payments in the month to date")
g_pay_value_mtd   = Gauge("square_payments_value_mtd", "Total value of payments in the month to date (in minor currency units)")
g_avg_value_mtd   = Gauge("square_payments_avg_value_mtd", "Average payment value in the month to date (in minor currency units)")

# Cache for orders
def get_order(order_id: str, cache={}):
    """Retrieve order details (with simple caching)."""
    if order_id in cache:
        return cache[order_id]
    url = f"{API_BASE}/orders/{order_id}"
    resp = requests.get(url, headers=HEADERS)
    resp.raise_for_status()
    order = resp.json().get("order", {})
    cache[order_id] = order
    return order

# Pagination helpers
def list_payments(begin_time: str, end_time: str, cursor=None) -> dict:
    params = {"begin_time": begin_time, "end_time": end_time, "location_id": LOCATION_ID, "sort_order": "ASC", "cursor": cursor, "limit": 100}
    resp = requests.get(f"{API_BASE}/payments", headers=HEADERS, params=params)
    resp.raise_for_status()
    return resp.json()

def list_refunds(begin_time: str, end_time: str, cursor=None) -> dict:
    params = {"begin_time": begin_time, "end_time": end_time, "location_id": LOCATION_ID, "sort_order": "ASC", "cursor": cursor, "limit": 100}
    resp = requests.get(f"{API_BASE}/refunds", headers=HEADERS, params=params)
    resp.raise_for_status()
    return resp.json()

# Core collection logic
def collect_metrics():
    now = datetime.utcnow()
    # ========== 24h WINDOW ==========
    end_time = now
    start_time = end_time - timedelta(hours=SCRAPE_WINDOW_H)
    bt = start_time.isoformat() + "Z"
    et = end_time.isoformat() + "Z"

    logger.info("Collecting 24h metrics from %s to %s", bt, et)

    # Initialize accumulators
    total_count = total_value = 0
    refund_count = refund_value = 0
    product_counts = {}
    product_values = {}

    # Fetch payments
    cursor = None
    while True:
        data = list_payments(bt, et, cursor)
        for p in data.get("payments", []):
            total_count += 1
            amount = p["amount_money"]["amount"]
            total_value += amount
            order_id = p.get("order_id")
            if order_id:
                order = get_order(order_id)
                for item in order.get("line_items", []):
                    name = item.get("name", "<unknown>")
                    qty = int(item.get("quantity", "1"))
                    unit_price = item.get("base_price_money", {}).get("amount", 0)
                    product_counts[name] = product_counts.get(name, 0) + qty
                    product_values[name] = product_values.get(name, 0) + unit_price * qty
        cursor = data.get("cursor")
        if not cursor:
            break

    # Fetch refunds
    cursor = None
    while True:
        data = list_refunds(bt, et, cursor)
        for r in data.get("refunds", []):
            refund_count += 1
            refund_value += r.get("amount_money", {}).get("amount", 0)
        cursor = data.get("cursor")
        if not cursor:
            break

    # Update 24h metrics
    g_pay_count.set(total_count)
    g_pay_value.set(total_value)
    g_avg_value.set(total_value / total_count if total_count else 0)
    g_refund_count.set(refund_count)
    g_refund_value.set(refund_value)
    for prod, cnt in product_counts.items():
        product_count_24h.labels(product_name=prod).set(cnt)
        product_value_24h.labels(product_name=prod).set(product_values[prod])

    logger.info(
        "24h metrics: payments=%d total=%d (%s), products=%s",
        total_count, total_value, CURRENCY, list(product_counts.keys())
    )

    # ========== MTD WINDOW ==========
    mtd_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    mb = mtd_start.isoformat() + "Z"
    me = et
    logger.info("Collecting MTD metrics from %s to %s", mb, me)

    mtd_count = mtd_value = 0
    cursor = None
    while True:
        data = list_payments(mb, me, cursor)
        for p in data.get("payments", []):
            mtd_count += 1
            mtd_value += p["amount_money"]["amount"]
        cursor = data.get("cursor")
        if not cursor:
            break

    # Update MTD metrics
    g_pay_count_mtd.set(mtd_count)
    g_pay_value_mtd.set(mtd_value)
    g_avg_value_mtd.set(mtd_value / mtd_count if mtd_count else 0)

    logger.info(
        "MTD metrics: payments=%d total=%d (%s)",
        mtd_count, mtd_value, CURRENCY
    )


if __name__ == "__main__":
    # Start the Prometheus metrics HTTP server
    start_http_server(EXPORTER_PORT)
    logger.info("Exporter running on port %d", EXPORTER_PORT)

    interval = max(60, int((SCRAPE_WINDOW_H * 3600) / 12))
    logger.info("Collecting every %d seconds", interval)
    while True:
        try:
            collect_metrics()
        except Exception:
            logger.exception("Error collecting metrics")
        time.sleep(interval)

