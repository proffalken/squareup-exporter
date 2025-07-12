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
SQUARE_TOKEN     = os.getenv("SQUARE_ACCESS_TOKEN")
LOCATION_ID      = os.getenv("SQUARE_LOCATION_ID")
EXPORTER_PORT    = int(os.getenv("EXPORTER_PORT", "8000"))
SCRAPE_WINDOW_H  = int(os.getenv("SCRAPE_WINDOW_H", "24"))
API_BASE         = "https://connect.squareup.com/v2"

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
    currency = loc.get("currency")
    if not currency:
        logger.warning("Could not determine currency from location data; defaulting to minor units")
    return currency

CURRENCY = get_account_currency()
logger.info(f"Detected account currency: %s", CURRENCY)

# Define Prometheus metrics
g_pay_count    = Gauge("square_payments_count_24h", "Number of payments in the last 24h")
g_pay_value    = Gauge("square_payments_value_24h", "Total value of payments in the last 24h (in minor currency units)")
g_avg_value    = Gauge("square_payments_avg_value_24h", "Average payment value in the last 24h (in minor currency units)")
g_refund_count = Gauge("square_refunds_count_24h", "Number of refunds in the last 24h")
g_refund_value = Gauge("square_refunds_value_24h", "Total value of refunds in the last 24h (in minor currency units)")

def list_payments(begin_time: str, end_time: str, cursor=None):
    """Fetch one page of payments from Square API."""
    params = {
        "begin_time": begin_time,
        "end_time": end_time,
        "location_id": LOCATION_ID,
        "sort_order": "ASC",
        "cursor": cursor,
        "limit": 100
    }
    response = requests.get(f"{API_BASE}/payments", headers=HEADERS, params=params)
    response.raise_for_status()
    return response.json()

def list_refunds(begin_time: str, end_time: str, cursor=None):
    """Fetch one page of refunds from Square API."""
    params = {
        "begin_time": begin_time,
        "end_time": end_time,
        "location_id": LOCATION_ID,
        "sort_order": "ASC",
        "cursor": cursor,
        "limit": 100
    }
    response = requests.get(f"{API_BASE}/refunds", headers=HEADERS, params=params)
    response.raise_for_status()
    return response.json()

def collect_metrics():
    """Collect payment and refund metrics over the configured time window."""
    end = datetime.utcnow()
    start = end - timedelta(hours=SCRAPE_WINDOW_H)
    begin_time = start.isoformat() + "Z"
    end_time   = end.isoformat() + "Z"

    logger.info("Collecting metrics from %s to %s", begin_time, end_time)

    # Payments
    total_count = 0
    total_value = 0
    cursor = None
    while True:
        data = list_payments(begin_time, end_time, cursor)
        payments = data.get("payments", [])
        total_count += len(payments)
        for p in payments:
            total_value += p["amount_money"]["amount"]
        cursor = data.get("cursor")
        if not cursor:
            break

    # Refunds
    refund_count = 0
    refund_value = 0
    cursor = None
    while True:
        data = list_refunds(begin_time, end_time, cursor)
        refunds = data.get("refunds", [])
        refund_count += len(refunds)
        for r in refunds:
            refund_value += r["amount_money"]["amount"]
        cursor = data.get("cursor")
        if not cursor:
            break

    # Update Prometheus metrics
    g_pay_count.set(total_count)
    g_pay_value.set(total_value)
    avg_value = total_value / total_count if total_count else 0
    g_avg_value.set(avg_value)
    g_refund_count.set(refund_count)
    g_refund_value.set(refund_value)

    # Log with currency code
    logger.info(
        "Metrics updated: payments=%d, total_value=%d minor units (%s), avg_value=%.2f minor units (%s), refunds=%d, refund_value=%d minor units (%s)",
        total_count, total_value, CURRENCY, avg_value, CURRENCY, refund_count, refund_value, CURRENCY
    )

if __name__ == "__main__":
    # Start the Prometheus metrics HTTP server
    start_http_server(EXPORTER_PORT)
    logger.info("Square exporter listening on port %d", EXPORTER_PORT)

    # Main loop: collect metrics periodically
    interval_seconds = max(60, int((SCRAPE_WINDOW_H * 3600) / 12))
    logger.info("Starting main loop, collecting every %d seconds", interval_seconds)
    while True:
        try:
            collect_metrics()
        except Exception:
            logger.exception("Error collecting metrics")
        time.sleep(interval_seconds)

