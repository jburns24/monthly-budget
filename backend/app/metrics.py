"""Prometheus metrics for receipt processing."""

from prometheus_client import Counter, Histogram

receipts_processed_total = Counter(
    "receipts_processed_total",
    "Total number of receipt uploads processed",
    ["status"],
)

receipts_upload_errors_total = Counter(
    "receipts_upload_errors_total",
    "Total number of receipt upload errors by type",
    ["error_type"],
)

claude_api_latency_seconds = Histogram(
    "claude_api_latency_seconds",
    "Latency of Claude API calls in seconds",
    buckets=[0.5, 1, 2, 5, 10, 30],
)

receipt_image_bytes = Histogram(
    "receipt_image_bytes",
    "Size of receipt images in bytes",
    buckets=[102400, 262144, 524288, 1048576, 2097152, 5242880],
)
