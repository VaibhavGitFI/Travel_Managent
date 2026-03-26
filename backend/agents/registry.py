"""
TravelSync Pro — Agent Registry, Health Monitor & Circuit Breaker
Centralized registry for all A2A agents with real-time health tracking.

Usage:
    from agents.registry import registry
    registry.record_success("hotel_agent", latency_ms=320)
    registry.record_failure("weather_agent", error="API timeout")
    health = registry.get_health()
"""
import time
import threading
import logging
from collections import defaultdict
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# ── Circuit Breaker ───────────────────────────────────────────────────────────

class CircuitBreaker:
    """
    Circuit breaker for external service calls.
    States: CLOSED (normal) -> OPEN (failing, reject calls) -> HALF_OPEN (test one call)
    """
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

    def __init__(self, failure_threshold: int = 5, recovery_timeout: float = 60.0,
                 half_open_max: int = 1):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max = half_open_max
        self._state = self.CLOSED
        self._failure_count = 0
        self._last_failure_time = 0.0
        self._half_open_calls = 0
        self._lock = threading.Lock()

    @property
    def state(self) -> str:
        with self._lock:
            if self._state == self.OPEN:
                if time.time() - self._last_failure_time >= self.recovery_timeout:
                    self._state = self.HALF_OPEN
                    self._half_open_calls = 0
            return self._state

    def allow_request(self) -> bool:
        """Check if a request should be allowed through."""
        state = self.state
        if state == self.CLOSED:
            return True
        if state == self.HALF_OPEN:
            with self._lock:
                if self._half_open_calls < self.half_open_max:
                    self._half_open_calls += 1
                    return True
            return False
        return False  # OPEN

    def record_success(self):
        """Record a successful call. Resets circuit if half-open."""
        with self._lock:
            if self._state == self.HALF_OPEN:
                self._state = self.CLOSED
                logger.info("[CircuitBreaker] Circuit CLOSED after successful test call")
            self._failure_count = 0

    def record_failure(self):
        """Record a failed call. May trip the circuit."""
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.time()
            if self._state == self.HALF_OPEN:
                self._state = self.OPEN
                logger.warning("[CircuitBreaker] Circuit re-OPENED after half-open failure")
            elif self._failure_count >= self.failure_threshold:
                if self._state != self.OPEN:
                    self._state = self.OPEN
                    logger.warning("[CircuitBreaker] Circuit OPENED after %d failures", self._failure_count)

    def to_dict(self) -> dict:
        return {
            "state": self.state,
            "failure_count": self._failure_count,
            "failure_threshold": self.failure_threshold,
            "recovery_timeout_s": self.recovery_timeout,
        }


# ── Agent Definition ──────────────────────────────────────────────────────────

class AgentInfo:
    """Metadata + health metrics for a single agent."""

    def __init__(self, name: str, version: str, description: str,
                 agent_type: str = "task", capabilities: list = None,
                 external_service: str = None, timeout_s: int = 25):
        self.name = name
        self.version = version
        self.description = description
        self.agent_type = agent_type  # "task" | "orchestrator" | "validator" | "crud"
        self.capabilities = capabilities or []
        self.external_service = external_service  # e.g. "amadeus", "openweather"
        self.timeout_s = timeout_s
        self.registered_at = datetime.now(timezone.utc).isoformat()

        # Health metrics
        self.invocations = 0
        self.successes = 0
        self.failures = 0
        self.total_latency_ms = 0.0
        self.last_invoked = None
        self.last_error = None
        self.last_error_time = None

        # Circuit breaker (only for agents with external services)
        self.circuit_breaker = CircuitBreaker() if external_service else None

    @property
    def avg_latency_ms(self) -> float:
        return round(self.total_latency_ms / self.successes, 1) if self.successes else 0.0

    @property
    def success_rate(self) -> float:
        return round(self.successes / self.invocations * 100, 1) if self.invocations else 100.0

    @property
    def status(self) -> str:
        if self.circuit_breaker and self.circuit_breaker.state == CircuitBreaker.OPEN:
            return "circuit_open"
        if self.invocations == 0:
            return "idle"
        if self.success_rate >= 95:
            return "healthy"
        if self.success_rate >= 80:
            return "degraded"
        return "unhealthy"

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "type": self.agent_type,
            "capabilities": self.capabilities,
            "external_service": self.external_service,
            "timeout_s": self.timeout_s,
            "status": self.status,
            "metrics": {
                "invocations": self.invocations,
                "successes": self.successes,
                "failures": self.failures,
                "success_rate": self.success_rate,
                "avg_latency_ms": self.avg_latency_ms,
                "last_invoked": self.last_invoked,
                "last_error": self.last_error,
                "last_error_time": self.last_error_time,
            },
            "circuit_breaker": self.circuit_breaker.to_dict() if self.circuit_breaker else None,
            "registered_at": self.registered_at,
        }


# ── Agent Registry ────────────────────────────────────────────────────────────

class AgentRegistry:
    """Singleton registry for all A2A agents."""

    def __init__(self):
        self._agents: dict[str, AgentInfo] = {}
        self._lock = threading.Lock()

    def register(self, name: str, version: str, description: str, **kwargs) -> AgentInfo:
        """Register an agent. Idempotent — updates if already registered."""
        with self._lock:
            if name in self._agents:
                agent = self._agents[name]
                agent.version = version
                agent.description = description
                for k, v in kwargs.items():
                    if hasattr(agent, k):
                        setattr(agent, k, v)
            else:
                agent = AgentInfo(name, version, description, **kwargs)
                self._agents[name] = agent
        return agent

    def get(self, name: str) -> AgentInfo | None:
        return self._agents.get(name)

    def record_success(self, name: str, latency_ms: float = 0) -> None:
        agent = self._agents.get(name)
        if not agent:
            return
        agent.invocations += 1
        agent.successes += 1
        agent.total_latency_ms += latency_ms
        agent.last_invoked = datetime.now(timezone.utc).isoformat()
        if agent.circuit_breaker:
            agent.circuit_breaker.record_success()

    def record_failure(self, name: str, error: str = "") -> None:
        agent = self._agents.get(name)
        if not agent:
            return
        agent.invocations += 1
        agent.failures += 1
        agent.last_invoked = datetime.now(timezone.utc).isoformat()
        agent.last_error = error[:200] if error else None
        agent.last_error_time = datetime.now(timezone.utc).isoformat()
        if agent.circuit_breaker:
            agent.circuit_breaker.record_failure()

    def allow_request(self, name: str) -> bool:
        """Check if agent's circuit breaker allows a request."""
        agent = self._agents.get(name)
        if not agent or not agent.circuit_breaker:
            return True
        return agent.circuit_breaker.allow_request()

    def get_health(self) -> dict:
        """Return health summary for all agents."""
        agents = [a.to_dict() for a in self._agents.values()]
        total = len(agents)
        healthy = sum(1 for a in agents if a["status"] == "healthy")
        degraded = sum(1 for a in agents if a["status"] == "degraded")
        unhealthy = sum(1 for a in agents if a["status"] in ("unhealthy", "circuit_open"))

        return {
            "summary": {
                "total_agents": total,
                "healthy": healthy,
                "degraded": degraded,
                "unhealthy": unhealthy,
                "overall": "healthy" if unhealthy == 0 and degraded == 0
                           else "degraded" if unhealthy == 0
                           else "unhealthy",
            },
            "agents": agents,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    def list_agents(self) -> list[dict]:
        return [a.to_dict() for a in self._agents.values()]


# ── Global singleton ──────────────────────────────────────────────────────────
registry = AgentRegistry()

# ── Register all known agents ─────────────────────────────────────────────────
def _register_all():
    registry.register("hotel_agent", "3.1.0",
        "Search hotels via Amadeus Hotels v3 + PG/long-stay suggestions",
        agent_type="task", external_service="amadeus",
        capabilities=["hotel_search", "pg_search", "price_comparison"],
        timeout_s=20)

    registry.register("travel_mode_agent", "3.1.0",
        "Recommend flights, trains, buses via Amadeus Flights v2 + Indian carriers",
        agent_type="task", external_service="amadeus",
        capabilities=["flight_search", "train_search", "bus_search", "carbon_estimate"],
        timeout_s=20)

    registry.register("weather_agent", "3.1.0",
        "Travel weather forecasts via OpenWeatherMap",
        agent_type="task", external_service="openweather",
        capabilities=["forecast", "current_weather", "travel_advisory"],
        timeout_s=8)

    registry.register("checklist_agent", "3.1.0",
        "AI-powered packing lists via Gemini",
        agent_type="task", external_service="gemini",
        capabilities=["packing_list", "document_checklist"],
        timeout_s=15)

    registry.register("guide_agent", "3.1.0",
        "Destination guides via Google Maps Places + Gemini",
        agent_type="task", external_service="google_maps",
        capabilities=["places", "restaurants", "attractions", "local_tips"],
        timeout_s=15)

    registry.register("meeting_agent", "3.1.0",
        "Client meeting CRUD + AI schedule optimization",
        agent_type="crud",
        capabilities=["meeting_crud", "schedule_optimize", "venue_search", "text_parse"],
        timeout_s=10)

    registry.register("expense_agent", "3.1.0",
        "Expense CRUD + 3-stage OCR verification",
        agent_type="crud", external_service="google_vision",
        capabilities=["expense_crud", "ocr_extract", "receipt_verify"],
        timeout_s=20)

    registry.register("chat_agent", "3.1.0",
        "AI conversational assistant via Gemini 2.0 Flash",
        agent_type="task", external_service="gemini",
        capabilities=["chat", "intent_detection", "trip_planning", "expense_help"],
        timeout_s=30)

    registry.register("analytics_agent", "3.1.0",
        "Dashboard KPIs, spend analysis, compliance scorecard from real DB",
        agent_type="task",
        capabilities=["dashboard_stats", "spend_analysis", "compliance_score", "carbon_analytics"],
        timeout_s=10)

    registry.register("policy_agent", "3.1.0",
        "Travel policy compliance validation",
        agent_type="validator",
        capabilities=["policy_check", "budget_validation", "class_validation"],
        timeout_s=5)

    registry.register("validator_agent", "3.1.0",
        "Post-plan validation: checks consistency across all agent results",
        agent_type="validator",
        capabilities=["cross_agent_validation", "data_consistency", "completeness_check"],
        timeout_s=10)

    registry.register("request_agent", "3.1.0",
        "Travel request workflow engine: CRUD + status transitions + approval routing",
        agent_type="crud",
        capabilities=["request_crud", "status_transition", "approval_routing", "auto_transition"],
        timeout_s=10)

    registry.register("anomaly_agent", "3.1.0",
        "AI-powered expense anomaly detection",
        agent_type="task", external_service="gemini",
        capabilities=["anomaly_detection", "duplicate_check", "outlier_detection"],
        timeout_s=15)

    registry.register("budget_forecast_agent", "3.1.0",
        "AI-powered trip budget forecasting",
        agent_type="task", external_service="gemini",
        capabilities=["budget_prediction", "cost_breakdown", "savings_tips"],
        timeout_s=15)

    registry.register("document_agent", "3.1.0",
        "Parse flight tickets, hotel vouchers, visa docs, train tickets",
        agent_type="task", external_service="gemini",
        capabilities=["ticket_parse", "voucher_parse", "visa_parse"],
        timeout_s=15)

    registry.register("sos_agent", "3.1.0",
        "Emergency SOS: geocoding, nearby hospitals/police, emergency contacts",
        agent_type="task", external_service="google_maps",
        capabilities=["reverse_geocode", "nearby_hospitals", "nearby_police", "emergency_contacts"],
        timeout_s=10)

    registry.register("recommendation_agent", "3.1.0",
        "AI trip recommendations based on travel history",
        agent_type="task", external_service="gemini",
        capabilities=["destination_recommend", "hotel_recommend", "activity_recommend"],
        timeout_s=15)

    registry.register("orchestrator", "3.1.0",
        "Master A2A orchestrator: parallel agent coordination",
        agent_type="orchestrator",
        capabilities=["parallel_execution", "result_assembly", "fallback_handling"],
        timeout_s=35)

_register_all()
