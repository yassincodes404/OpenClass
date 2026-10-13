"""Token-bucket rate limiter unit tests."""

from openclass_server.rate_limit import RateLimiter, TokenBucket


def test_bucket_allows_up_to_capacity():
    bucket = TokenBucket(capacity=3, refill_per_minute=3, tokens=3, updated=0.0)
    assert bucket.take(now=0.0) is True
    assert bucket.take(now=0.1) is True
    assert bucket.take(now=0.2) is True
    assert bucket.take(now=0.3) is False


def test_bucket_refills_over_time():
    bucket = TokenBucket(capacity=2, refill_per_minute=60, tokens=0, updated=0.0)
    assert bucket.take(now=0.0) is False
    assert bucket.take(now=61.0) is True  # 1 token per second refill


def test_limiter_classifies_routes():
    limiter = RateLimiter(ingest_per_minute=60, classify_per_minute=300)
    assert limiter.route_class("/api/v1/projects/x/events") == "ingest"
    assert limiter.route_class("/api/v1/projects/x/events/batch") == "ingest"
    assert limiter.route_class("/api/v1/classifiers/x/classify") == "classify"
    assert limiter.route_class("/api/v1/projects/x/decision-services/s/runs") == "classify"
    assert limiter.route_class("/api/v1/projects") is None


def test_limiter_enforces_per_client_isolation():
    limiter = RateLimiter(ingest_per_minute=2, classify_per_minute=300)
    path = "/api/v1/projects/p/events"
    assert limiter.check("client-a", path, now=0.0)[0] is True
    assert limiter.check("client-a", path, now=0.1)[0] is True
    allowed, retry_after, limit, _ = limiter.check("client-a", path, now=0.2)
    assert allowed is False
    assert retry_after >= 1
    assert limit == 2
    # A different client is unaffected (per-key buckets).
    assert limiter.check("client-b", path, now=0.2)[0] is True


def test_limiter_disabled_allows_everything():
    limiter = RateLimiter(ingest_per_minute=1, classify_per_minute=1, enabled=False)
    for _ in range(5):
        assert limiter.check("c", "/api/v1/projects/p/events", now=0.0)[0] is True


def test_limiter_returns_headers_data():
    limiter = RateLimiter(ingest_per_minute=3, classify_per_minute=300)
    _, _, limit, remaining = limiter.check("c", "/api/v1/projects/p/events", now=0.0)
    assert limit == 3
    assert remaining == 2


def test_limiter_ignores_get_requests_and_limits_webhooks():
    limiter = RateLimiter(ingest_per_minute=1, classify_per_minute=1, max_buckets=2)
    assert limiter.route_class("/api/v1/projects/p/events", method="GET") is None
    assert limiter.route_class("/api/v1/projects/p/runs", method="GET") is None
    webhook_path = "/api/v1/projects/p/integrations/i/webhook"
    assert limiter.route_class(webhook_path, method="POST") == "ingest"
    # GET requests never consume tokens
    for _ in range(5):
        assert limiter.check("c", "/api/v1/projects/p/events", method="GET", now=0.0)[0] is True
    # Bounded bucket eviction keeps _buckets <= max_buckets
    limiter.check("c1", "/api/v1/projects/p/events", now=1.0)
    limiter.check("c2", "/api/v1/projects/p/events", now=2.0)
    limiter.check("c3", "/api/v1/projects/p/events", now=3.0)
    assert len(limiter._buckets) <= 2
