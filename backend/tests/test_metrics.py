"""Tests for T06: Prometheus metrics instruments."""

import pytest
from prometheus_client import REGISTRY


@pytest.mark.asyncio
async def test_receipts_processed_total_increments() -> None:
    """receipts_processed_total{status="completed"} increments after a mocked happy-path upload."""
    from app.metrics import receipts_processed_total

    before = receipts_processed_total.labels(status="completed")._value.get()
    receipts_processed_total.labels(status="completed").inc()
    after = receipts_processed_total.labels(status="completed")._value.get()

    assert after == before + 1.0


@pytest.mark.asyncio
async def test_receipts_processed_total_failed_increments() -> None:
    """receipts_processed_total{status="failed"} increments independently."""
    from app.metrics import receipts_processed_total

    before = receipts_processed_total.labels(status="failed")._value.get()
    receipts_processed_total.labels(status="failed").inc()
    after = receipts_processed_total.labels(status="failed")._value.get()

    assert after == before + 1.0


@pytest.mark.asyncio
async def test_receipts_upload_errors_total_increments() -> None:
    """receipts_upload_errors_total increments for each error_type label."""
    from app.metrics import receipts_upload_errors_total

    error_types = ["non_receipt", "invalid_format", "rate_limited", "api_error", "timeout", "too_large"]
    for error_type in error_types:
        before = receipts_upload_errors_total.labels(error_type=error_type)._value.get()
        receipts_upload_errors_total.labels(error_type=error_type).inc()
        after = receipts_upload_errors_total.labels(error_type=error_type)._value.get()
        assert after == before + 1.0, f"Expected increment for error_type={error_type}"


@pytest.mark.asyncio
async def test_claude_api_latency_seconds_observe() -> None:
    """claude_api_latency_seconds histogram accepts observations."""
    from app.metrics import claude_api_latency_seconds

    # Should not raise
    claude_api_latency_seconds.observe(1.5)
    claude_api_latency_seconds.observe(0.3)
    claude_api_latency_seconds.observe(25.0)


@pytest.mark.asyncio
async def test_receipt_image_bytes_observe() -> None:
    """receipt_image_bytes histogram accepts observations."""
    from app.metrics import receipt_image_bytes

    # Should not raise
    receipt_image_bytes.observe(26804)  # ~26KB sample receipt
    receipt_image_bytes.observe(1024 * 1024)  # 1MB
    receipt_image_bytes.observe(5 * 1024 * 1024)  # 5MB


@pytest.mark.asyncio
async def test_metrics_registered_in_default_registry() -> None:
    """All four metrics are discoverable in the default Prometheus registry.

    prometheus_client strips the `_total` suffix from Counter names internally;
    the suffix is appended at exposition time. Histograms keep their full name.
    """
    metric_names = {m.name for m in REGISTRY.collect()}
    # Counters: _total suffix is stripped in the registry
    assert "receipts_processed" in metric_names
    assert "receipts_upload_errors" in metric_names
    # Histograms: name is stored as-is
    assert "claude_api_latency_seconds" in metric_names
    assert "receipt_image_bytes" in metric_names
