"""Tests for Agent Registry, Health Monitor, and Circuit Breaker."""
from agents.registry import registry, CircuitBreaker


def test_registry_has_agents():
    health = registry.get_health()
    assert health["summary"]["total_agents"] >= 15
    assert health["summary"]["overall"] in ("healthy", "degraded", "unhealthy")


def test_registry_agent_lookup():
    agent = registry.get("hotel_agent")
    assert agent is not None
    assert agent.version == "3.1.0"
    assert "hotel_search" in agent.capabilities
    assert agent.external_service == "amadeus"


def test_registry_record_success():
    registry.record_success("weather_agent", latency_ms=150)
    agent = registry.get("weather_agent")
    assert agent.successes >= 1
    assert agent.avg_latency_ms > 0
    assert agent.status in ("healthy", "idle")


def test_registry_record_failure():
    registry.record_failure("anomaly_agent", error="Test error")
    agent = registry.get("anomaly_agent")
    assert agent.failures >= 1
    assert agent.last_error == "Test error"


def test_registry_nonexistent():
    assert registry.get("nonexistent_agent") is None


def test_health_endpoint(auth_client):
    resp = auth_client.get("/api/agents/health")
    data = resp.get_json()
    assert data["success"] is True
    assert "summary" in data
    assert "agents" in data
    assert data["summary"]["total_agents"] >= 15


def test_list_agents_endpoint(auth_client):
    resp = auth_client.get("/api/agents")
    data = resp.get_json()
    assert data["success"] is True
    names = [a["name"] for a in data["agents"]]
    assert "orchestrator" in names
    assert "hotel_agent" in names


def test_single_agent_endpoint(auth_client):
    resp = auth_client.get("/api/agents/hotel_agent")
    data = resp.get_json()
    assert data["success"] is True
    assert data["agent"]["name"] == "hotel_agent"
    assert data["agent"]["circuit_breaker"] is not None


def test_agent_not_found(auth_client):
    resp = auth_client.get("/api/agents/fake_agent")
    assert resp.status_code == 404


# ── Circuit Breaker unit tests ────────────────────────────────────────────────

def test_circuit_breaker_starts_closed():
    cb = CircuitBreaker(failure_threshold=3, recovery_timeout=1)
    assert cb.state == CircuitBreaker.CLOSED
    assert cb.allow_request() is True


def test_circuit_breaker_opens_on_failures():
    cb = CircuitBreaker(failure_threshold=3, recovery_timeout=60)
    cb.record_failure()
    cb.record_failure()
    assert cb.state == CircuitBreaker.CLOSED  # Not yet
    cb.record_failure()
    assert cb.state == CircuitBreaker.OPEN
    assert cb.allow_request() is False


def test_circuit_breaker_half_open_after_timeout():
    import time
    cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.1)
    cb.record_failure()
    cb.record_failure()
    assert cb.state == CircuitBreaker.OPEN
    time.sleep(0.15)
    assert cb.state == CircuitBreaker.HALF_OPEN
    assert cb.allow_request() is True


def test_circuit_breaker_closes_on_success():
    import time
    cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.1)
    cb.record_failure()
    cb.record_failure()
    time.sleep(0.15)
    assert cb.state == CircuitBreaker.HALF_OPEN
    cb.record_success()
    assert cb.state == CircuitBreaker.CLOSED


def test_circuit_breaker_reopens_on_half_open_failure():
    import time
    cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.1)
    cb.record_failure()
    cb.record_failure()
    time.sleep(0.15)
    assert cb.state == CircuitBreaker.HALF_OPEN
    cb.record_failure()
    assert cb.state == CircuitBreaker.OPEN
