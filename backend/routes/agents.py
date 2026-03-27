"""
TravelSync Pro — Agent Registry & Health Routes
A2A agent discovery, health monitoring, and circuit breaker status.
"""
import logging
from flask import Blueprint, jsonify
from auth import get_current_user, admin_required
from agents.registry import registry
from extensions import limiter

logger = logging.getLogger(__name__)

agents_bp = Blueprint("agents", __name__, url_prefix="/api/agents")


@agents_bp.route("", methods=["GET"])
def list_agents():
    """GET /api/agents — list all registered A2A agents with metadata."""
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Authentication required"}), 401
    return jsonify({"success": True, "agents": registry.list_agents()}), 200


@agents_bp.route("/health", methods=["GET"])
@limiter.limit("30 per minute")
def agent_health():
    """GET /api/agents/health — real-time health dashboard for all agents."""
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Authentication required"}), 401
    return jsonify({"success": True, **registry.get_health()}), 200


@agents_bp.route("/<string:agent_name>", methods=["GET"])
def get_agent(agent_name):
    """GET /api/agents/:name — detailed info for a single agent."""
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Authentication required"}), 401

    agent = registry.get(agent_name)
    if not agent:
        return jsonify({"success": False, "error": f"Agent '{agent_name}' not found"}), 404
    return jsonify({"success": True, "agent": agent.to_dict()}), 200


@agents_bp.route("/<string:agent_name>/reset", methods=["POST"])
@limiter.limit("5 per minute")
@admin_required
def reset_agent_circuit(agent_name):
    """POST /api/agents/:name/reset — manually reset an agent's circuit breaker (admin only)."""
    agent = registry.get(agent_name)
    if not agent:
        return jsonify({"success": False, "error": f"Agent '{agent_name}' not found"}), 404
    if not agent.circuit_breaker:
        return jsonify({"success": False, "error": "Agent has no circuit breaker"}), 400

    agent.circuit_breaker._state = agent.circuit_breaker.CLOSED
    agent.circuit_breaker._failure_count = 0
    logger.info("[Agents] Circuit breaker for %s manually reset", agent_name)
    return jsonify({"success": True, "message": f"Circuit breaker for {agent_name} reset to CLOSED"}), 200
