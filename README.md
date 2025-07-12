# Square Prometheus Exporter

A Prometheus exporter for Square Payments API metrics, exposing key payment and refund statistics for monitoring and alerting.

## Features

* **Payment Metrics**: Number of payments in the last 24 hours
* **Value Metrics**: Total and average payment value in minor currency units
* **Refund Metrics**: Number and total value of refunds in the last 24 hours
* **Automatic Currency Detection**: Logs and annotates metrics with your account currency code

## Prerequisites

* Python 3.10 or higher
* Docker & Docker Compose (optional, for containerized deployment)
* Square Developer account with an Access Token and Location ID

## Installation

1. **Clone the repository**

   ```bash
   git clone <repository_url>
   cd <repository_dir>
   ```

2. **Build with Docker Compose**

   ```bash
   docker-compose build
   ```

## Configuration

The exporter reads configuration from environment variables:

| Variable              | Description                               | Default |
| --------------------- | ----------------------------------------- | ------- |
| `SQUARE_ACCESS_TOKEN` | Your Square API Access Token              | —       |
| `SQUARE_LOCATION_ID`  | Your Square Location ID                   | —       |
| `EXPORTER_PORT`       | Port on which exporter listens            | `8000`  |
| `SCRAPE_WINDOW_H`     | Look-back window in hours for each scrape | `24`    |

Export environment variables before running:

```bash
export SQUARE_ACCESS_TOKEN="sq0atp-XXXXXXXXXXXXXXXXXXXXXXXXXXXX"
export SQUARE_LOCATION_ID="LOCATION_ID_HERE"
```

## Usage

### Using Docker Compose

```bash
# Start exporter in detached mode
docker-compose up -d

# View logs
docker-compose logs -f square-exporter

# Verify metrics endpoint
curl http://localhost:${EXPORTER_PORT:-8000}/metrics
```

### Using Plain Docker

```bash
# Build image
docker build -t square-prom-exporter .

# Run container
docker run -d \
  --name square-exporter \
  -e SQUARE_ACCESS_TOKEN="$SQUARE_ACCESS_TOKEN" \
  -e SQUARE_LOCATION_ID="$SQUARE_LOCATION_ID" \
  -p ${EXPORTER_PORT:-8000}:8000 \
  square-prom-exporter

# View logs
docker logs -f square-exporter

# Test metrics endpoint
curl http://localhost:8000/metrics
```

## Continuous Integration

A GitHub Actions workflow is provided at [`.github/workflows/docker-publish.yml`](.github/workflows/docker-publish.yml) to build and publish the Docker image to GitHub Container Registry on every push to `main`.

## Metrics Reference

| Metric Name                     | Description                                                |
| ------------------------------- | ---------------------------------------------------------- |
| `square_payments_count_24h`     | Number of payments processed in the last 24 hours          |
| `square_payments_value_24h`     | Total value of payments in the last 24 hours (minor units) |
| `square_payments_avg_value_24h` | Average payment value in the last 24 hours (minor units)   |
| `square_refunds_count_24h`      | Number of refunds in the last 24 hours                     |
| `square_refunds_value_24h`      | Total value of refunds in the last 24 hours (minor units)  |

Scrape the `/metrics` endpoint from your Prometheus server to integrate these into your dashboards.

## License

MIT License (c) 2025 Matthew Macdonald-Wallace

