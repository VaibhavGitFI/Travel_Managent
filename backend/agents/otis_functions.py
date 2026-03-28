"""
OTIS Function Calling Framework
Defines all TravelSync functions that OTIS can execute via voice commands

This module provides:
    - Function registry (all available OTIS functions)
    - Parameter extraction from natural language
    - Permission checks (admin-only functions)
    - Safe function execution with error handling
    - Voice-friendly response formatting

Architecture:
    Voice Command → Extract Intent → Map to Function → Extract Params → Execute → Format Response

Aligned with TravelSync patterns:
    - Uses existing agent functions
    - Uses database patterns
    - Follows permission model
    - Integrates with notification service

Author: TravelSync Pro Team
Date: 2026-03-26
"""

import sys
import os
import logging
import re
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import get_db, table_columns

# Import existing TravelSync agents
from agents.request_agent import get_pending_approvals, process_approval, get_requests, get_request_detail
from agents.expense_agent import get_expenses
from agents.meeting_agent import get_all_meetings
from agents.analytics_agent import get_dashboard_stats, get_spend_analysis
from agents.policy_agent import get_active_policy

logger = logging.getLogger(__name__)


@dataclass
class FunctionDefinition:
    """Definition of a callable OTIS function."""
    name: str                          # Function name
    description: str                   # What it does (for LLM)
    function: Callable                 # Actual Python function
    parameters: Dict[str, str]         # Parameter descriptions
    required_params: List[str]         # Required parameters
    admin_only: bool = False           # Requires admin/manager role
    examples: List[str] = None         # Example voice commands

    def __post_init__(self):
        if self.examples is None:
            self.examples = []


class OtisFunctionRegistry:
    """
    Registry of all functions OTIS can execute.

    This is the central registry that maps voice commands to TravelSync functions.
    All functions are designed to be called safely with error handling.
    """

    def __init__(self):
        """Initialize function registry."""
        self._functions: Dict[str, FunctionDefinition] = {}
        self._register_all_functions()

        logger.info(
            f"[OTIS Functions] Initialized registry with {len(self._functions)} functions"
        )

    def _register_all_functions(self):
        """Register all available OTIS functions."""

        # ── Approvals (Admin/Manager Only) ────────────────────────────────────

        self.register(FunctionDefinition(
            name="get_pending_approvals",
            description="Get list of pending travel approval requests",
            function=self._get_pending_approvals_wrapper,
            parameters={},
            required_params=[],
            admin_only=True,
            examples=[
                "What pending approvals do I have?",
                "Show me pending requests",
                "Any approvals waiting for me?"
            ]
        ))

        self.register(FunctionDefinition(
            name="approve_trip",
            description="Approve a travel request",
            function=self._approve_trip_wrapper,
            parameters={
                "request_id": "Travel request ID (e.g., TR-2024-001)",
                "comments": "Optional approval comments"
            },
            required_params=["request_id"],
            admin_only=True,
            examples=[
                "Approve John's Mumbai trip",
                "Approve request TR-2024-001",
                "Approve the first one"
            ]
        ))

        self.register(FunctionDefinition(
            name="reject_trip",
            description="Reject a travel request",
            function=self._reject_trip_wrapper,
            parameters={
                "request_id": "Travel request ID",
                "reason": "Rejection reason (required)"
            },
            required_params=["request_id", "reason"],
            admin_only=True,
            examples=[
                "Reject John's trip because it's over budget",
                "Reject TR-2024-001 due to policy violation"
            ]
        ))

        # ── Travel Requests ────────────────────────────────────────────────────

        self.register(FunctionDefinition(
            name="get_my_trips",
            description="Get user's travel requests",
            function=self._get_my_trips_wrapper,
            parameters={
                "status": "Filter by status (pending, approved, completed, etc.)",
                "limit": "Maximum number of results (default: 10)"
            },
            required_params=[],
            admin_only=False,
            examples=[
                "Show me my trips",
                "What are my recent trips?",
                "Show me my pending trips"
            ]
        ))

        self.register(FunctionDefinition(
            name="get_trip_details",
            description="Get details of a specific trip",
            function=self._get_trip_details_wrapper,
            parameters={
                "request_id": "Travel request ID"
            },
            required_params=["request_id"],
            admin_only=False,
            examples=[
                "Tell me about my Mumbai trip",
                "Show details of TR-2024-001"
            ]
        ))

        # ── Expenses ───────────────────────────────────────────────────────────

        self.register(FunctionDefinition(
            name="get_my_expenses",
            description="Get user's expense reports",
            function=self._get_my_expenses_wrapper,
            parameters={
                "trip_id": "Filter by trip ID",
                "status": "Filter by verification status"
            },
            required_params=[],
            admin_only=False,
            examples=[
                "Show me my expenses",
                "What expenses do I have?",
                "Show expenses for my Mumbai trip"
            ]
        ))

        # ── Meetings ───────────────────────────────────────────────────────────

        self.register(FunctionDefinition(
            name="get_upcoming_meetings",
            description="Get upcoming client meetings",
            function=self._get_upcoming_meetings_wrapper,
            parameters={
                "days": "Number of days ahead (default: 7)",
                "destination": "Filter by destination city"
            },
            required_params=[],
            admin_only=False,
            examples=[
                "What meetings do I have?",
                "Show me my upcoming meetings",
                "Any meetings this week?"
            ]
        ))

        # ── Analytics (Admin/Manager) ──────────────────────────────────────────

        self.register(FunctionDefinition(
            name="get_travel_stats",
            description="Get travel statistics and KPIs",
            function=self._get_travel_stats_wrapper,
            parameters={},
            required_params=[],
            admin_only=True,
            examples=[
                "Show me travel statistics",
                "What are our travel KPIs?",
                "Give me a dashboard summary"
            ]
        ))

        self.register(FunctionDefinition(
            name="get_spend_report",
            description="Get travel spending analysis",
            function=self._get_spend_report_wrapper,
            parameters={
                "period": "Time period (this_month, last_month, this_year)"
            },
            required_params=[],
            admin_only=True,
            examples=[
                "How much have we spent on travel?",
                "Show me spending for this month",
                "What's our travel spend?"
            ]
        ))

        # ── Policy ─────────────────────────────────────────────────────────────

        self.register(FunctionDefinition(
            name="get_travel_policy",
            description="Get active travel policy details",
            function=self._get_travel_policy_wrapper,
            parameters={},
            required_params=[],
            admin_only=False,
            examples=[
                "What's our travel policy?",
                "Tell me about travel guidelines",
                "What's the hotel budget limit?"
            ]
        ))

        # ── Quick Actions ──────────────────────────────────────────────────────

        self.register(FunctionDefinition(
            name="get_my_schedule_today",
            description="Get today's schedule (meetings + trips)",
            function=self._get_schedule_today_wrapper,
            parameters={},
            required_params=[],
            admin_only=False,
            examples=[
                "What's my schedule today?",
                "What do I have today?",
                "Am I traveling today?"
            ]
        ))

    def register(self, func_def: FunctionDefinition):
        """Register a function in the registry."""
        self._functions[func_def.name] = func_def
        logger.debug(f"[OTIS Functions] Registered: {func_def.name}")

    def get_function(self, name: str) -> Optional[FunctionDefinition]:
        """Get function definition by name."""
        return self._functions.get(name)

    def list_functions(self, admin_only: bool = None) -> List[FunctionDefinition]:
        """
        List all available functions.

        Args:
            admin_only: If True, only admin functions. If False, only non-admin. If None, all.
        """
        if admin_only is None:
            return list(self._functions.values())
        return [f for f in self._functions.values() if f.admin_only == admin_only]

    def get_function_descriptions_for_llm(self, user_role: str = "employee") -> str:
        """
        Get formatted function descriptions for LLM prompt.

        This generates the function catalog that Gemini uses to understand
        what actions OTIS can perform.
        """
        is_admin = user_role in ("admin", "manager", "super_admin")

        descriptions = []
        descriptions.append("Available functions you can call:")
        descriptions.append("")

        for func in self._functions.values():
            # Skip admin functions for non-admin users
            if func.admin_only and not is_admin:
                continue

            desc = f"- **{func.name}**"
            if func.admin_only:
                desc += " (admin only)"
            desc += f": {func.description}"

            if func.parameters:
                params = ", ".join([f"{k}: {v}" for k, v in func.parameters.items()])
                desc += f"\n  Parameters: {params}"

            descriptions.append(desc)

        return "\n".join(descriptions)

    async def execute_function(
        self,
        function_name: str,
        parameters: Dict[str, Any],
        user_id: int,
        user_role: str = "employee",
        org_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Execute a function with given parameters.

        Args:
            function_name: Name of function to execute
            parameters: Function parameters extracted from voice
            user_id: Current user ID
            user_role: Current user role
            org_id: Current organization ID

        Returns:
            Result dict with success, data, and voice_response
        """
        # Get function definition
        func_def = self.get_function(function_name)
        if not func_def:
            logger.error(f"[OTIS Functions] Function not found: {function_name}")
            return {
                "success": False,
                "error": f"Function {function_name} not found",
                "voice_response": "I don't know how to do that yet."
            }

        # Check permissions
        if func_def.admin_only and user_role not in ("admin", "manager", "super_admin"):
            logger.warning(
                f"[OTIS Functions] Permission denied: {user_role} tried to call "
                f"{function_name} (admin only)"
            )
            return {
                "success": False,
                "error": "Permission denied - admin only function",
                "voice_response": "Sorry, only admins can do that."
            }

        # Check required parameters
        missing = [p for p in func_def.required_params if p not in parameters]
        if missing:
            logger.warning(f"[OTIS Functions] Missing parameters: {missing}")
            return {
                "success": False,
                "error": f"Missing required parameters: {', '.join(missing)}",
                "voice_response": f"I need more information. Please specify {', '.join(missing)}."
            }

        # Execute function
        try:
            logger.info(
                f"[OTIS Functions] Executing {function_name} for user {user_id} "
                f"with params: {parameters}"
            )

            # Add context to parameters
            context = {
                "user_id": user_id,
                "user_role": user_role,
                "org_id": org_id
            }

            result = await func_def.function(context, parameters)

            if result.get("success"):
                logger.info(f"[OTIS Functions] {function_name} succeeded")
            else:
                logger.warning(f"[OTIS Functions] {function_name} failed: {result.get('error')}")

            return result

        except Exception as e:
            logger.error(f"[OTIS Functions] Execution error in {function_name}: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "voice_response": "I encountered an error. Please try again."
            }

    # ── Function Wrappers (Async) ──────────────────────────────────────────────

    async def _get_pending_approvals_wrapper(self, context: Dict, params: Dict) -> Dict:
        """Get pending approvals for current user."""
        try:
            # Use existing request_agent function
            approvals = get_pending_approvals(
                approver_id=context["user_id"],
                org_id=context.get("org_id")
            )

            count = len(approvals)

            if count == 0:
                return {
                    "success": True,
                    "data": {"approvals": [], "count": 0},
                    "voice_response": "You have no pending approvals right now."
                }

            # Format for voice
            voice_parts = [f"You have {count} pending approval"]
            if count > 1:
                voice_parts[0] += "s"

            # List first 3
            for i, approval in enumerate(approvals[:3], 1):
                destination = approval.get("destination", "unknown")
                requester = approval.get("requester_name") or approval.get("full_name", "someone")
                voice_parts.append(f"{destination} trip for {requester}")

            if count > 3:
                voice_parts.append(f"and {count - 3} more")

            voice_response = voice_parts[0] + ". " + ", ".join(voice_parts[1:]) + "."

            return {
                "success": True,
                "data": {"approvals": approvals, "count": count},
                "voice_response": voice_response
            }

        except Exception as e:
            logger.error(f"[OTIS Functions] get_pending_approvals error: {e}")
            return {
                "success": False,
                "error": str(e),
                "voice_response": "I couldn't retrieve pending approvals."
            }

    async def _approve_trip_wrapper(self, context: Dict, params: Dict) -> Dict:
        """Approve a travel request."""
        try:
            request_id = params.get("request_id")
            comments = params.get("comments", "Approved via OTIS voice assistant")

            # Use existing request_agent function
            result = process_approval(
                request_id=request_id,
                approver_id=context["user_id"],
                decision="approved",
                comments=comments
            )

            if not result.get("success"):
                return {
                    "success": False,
                    "error": result.get("error", "Approval failed"),
                    "voice_response": f"I couldn't approve that trip. {result.get('error', '')}"
                }

            # Get trip details for voice response
            try:
                db = get_db()
                trip = db.execute(
                    "SELECT destination, user_id FROM travel_requests WHERE request_id = ?",
                    (request_id,)
                ).fetchone()
                user = db.execute(
                    "SELECT full_name FROM users WHERE id = ?",
                    (dict(trip)["user_id"],)
                ).fetchone() if trip else None
                db.close()

                if trip and user:
                    trip_dict = dict(trip)
                    user_dict = dict(user)
                    destination = trip_dict.get("destination", "")
                    name = user_dict.get("full_name", "")
                    voice_response = f"Done. I've approved the {destination} trip for {name}."
                else:
                    voice_response = f"Done. I've approved request {request_id}."
            except:
                voice_response = "Trip approved successfully."

            return {
                "success": True,
                "data": result,
                "voice_response": voice_response
            }

        except Exception as e:
            logger.error(f"[OTIS Functions] approve_trip error: {e}")
            return {
                "success": False,
                "error": str(e),
                "voice_response": "I couldn't approve that trip."
            }

    async def _reject_trip_wrapper(self, context: Dict, params: Dict) -> Dict:
        """Reject a travel request."""
        try:
            request_id = params.get("request_id")
            reason = params.get("reason", "Rejected")

            result = process_approval(
                request_id=request_id,
                approver_id=context["user_id"],
                decision="rejected",
                comments=reason
            )

            if not result.get("success"):
                return {
                    "success": False,
                    "error": result.get("error", "Rejection failed"),
                    "voice_response": f"I couldn't reject that trip. {result.get('error', '')}"
                }

            voice_response = f"Done. I've rejected request {request_id}."

            return {
                "success": True,
                "data": result,
                "voice_response": voice_response
            }

        except Exception as e:
            logger.error(f"[OTIS Functions] reject_trip error: {e}")
            return {
                "success": False,
                "error": str(e),
                "voice_response": "I couldn't reject that trip."
            }

    async def _get_my_trips_wrapper(self, context: Dict, params: Dict) -> Dict:
        """Get user's travel requests."""
        try:
            status = params.get("status")
            limit = int(params.get("limit", 10))

            trips = get_requests(
                user_id=context["user_id"],
                status=status,
                org_id=context.get("org_id")
            )

            # Limit results
            trips = trips[:limit] if trips else []
            count = len(trips)

            if count == 0:
                status_text = f" with status {status}" if status else ""
                return {
                    "success": True,
                    "data": {"trips": [], "count": 0},
                    "voice_response": f"You have no trips{status_text}."
                }

            # Format for voice
            voice_parts = [f"You have {count} trip"]
            if count > 1:
                voice_parts[0] += "s"

            # List first 3
            for trip in trips[:3]:
                destination = trip.get("destination", "unknown")
                status_str = trip.get("status", "")
                voice_parts.append(f"{destination} ({status_str})")

            if count > 3:
                voice_parts.append(f"and {count - 3} more")

            voice_response = voice_parts[0] + ". " + ", ".join(voice_parts[1:]) + "."

            return {
                "success": True,
                "data": {"trips": trips, "count": count},
                "voice_response": voice_response
            }

        except Exception as e:
            logger.error(f"[OTIS Functions] get_my_trips error: {e}")
            return {
                "success": False,
                "error": str(e),
                "voice_response": "I couldn't retrieve your trips."
            }

    async def _get_trip_details_wrapper(self, context: Dict, params: Dict) -> Dict:
        """Get details of a specific trip."""
        try:
            request_id = params.get("request_id")

            trip = get_request_detail(request_id)

            if not trip:
                return {
                    "success": False,
                    "error": "Trip not found",
                    "voice_response": f"I couldn't find trip {request_id}."
                }

            # Format for voice
            destination = trip.get("destination", "unknown")
            status = trip.get("status", "")
            start_date = trip.get("start_date", "")
            estimated = trip.get("estimated_total", 0)

            voice_response = f"Your {destination} trip is {status}."
            if start_date:
                voice_response += f" It starts on {start_date}."
            if estimated:
                voice_response += f" Estimated cost is {int(estimated)} rupees."

            return {
                "success": True,
                "data": trip,
                "voice_response": voice_response
            }

        except Exception as e:
            logger.error(f"[OTIS Functions] get_trip_details error: {e}")
            return {
                "success": False,
                "error": str(e),
                "voice_response": "I couldn't get trip details."
            }

    async def _get_my_expenses_wrapper(self, context: Dict, params: Dict) -> Dict:
        """Get user's expenses."""
        try:
            trip_id = params.get("trip_id")

            result = get_expenses(
                trip_id=trip_id,
                user_id=context["user_id"],
                org_id=context.get("org_id")
            )

            expenses = result.get("expenses", [])
            count = len(expenses)

            if count == 0:
                return {
                    "success": True,
                    "data": {"expenses": [], "count": 0},
                    "voice_response": "You have no expenses recorded."
                }

            # Calculate total
            total = sum(e.get("invoice_amount", 0) for e in expenses)

            voice_response = f"You have {count} expense"
            if count > 1:
                voice_response += "s"
            voice_response += f" totaling {int(total)} rupees."

            return {
                "success": True,
                "data": {"expenses": expenses, "count": count, "total": total},
                "voice_response": voice_response
            }

        except Exception as e:
            logger.error(f"[OTIS Functions] get_my_expenses error: {e}")
            return {
                "success": False,
                "error": str(e),
                "voice_response": "I couldn't retrieve your expenses."
            }

    async def _get_upcoming_meetings_wrapper(self, context: Dict, params: Dict) -> Dict:
        """Get upcoming meetings."""
        try:
            days = int(params.get("days", 7))
            destination = params.get("destination")

            meetings = get_all_meetings(
                user_id=context["user_id"],
                destination=destination,
                role=context.get("user_role", "employee")
            )

            # Filter to upcoming only
            today = datetime.now().date()
            future_date = today + timedelta(days=days)

            upcoming = []
            for meeting in meetings:
                meeting_date_str = meeting.get("meeting_date", "")
                if meeting_date_str:
                    try:
                        meeting_date = datetime.strptime(meeting_date_str, "%Y-%m-%d").date()
                        if today <= meeting_date <= future_date:
                            upcoming.append(meeting)
                    except:
                        pass

            count = len(upcoming)

            if count == 0:
                return {
                    "success": True,
                    "data": {"meetings": [], "count": 0},
                    "voice_response": f"You have no meetings in the next {days} days."
                }

            # Format for voice
            voice_parts = [f"You have {count} upcoming meeting"]
            if count > 1:
                voice_parts[0] += "s"

            # List first 3
            for mtg in upcoming[:3]:
                client = mtg.get("client_name", "")
                date = mtg.get("meeting_date", "")
                voice_parts.append(f"{client} on {date}")

            voice_response = voice_parts[0] + ". " + ", ".join(voice_parts[1:]) + "."

            return {
                "success": True,
                "data": {"meetings": upcoming, "count": count},
                "voice_response": voice_response
            }

        except Exception as e:
            logger.error(f"[OTIS Functions] get_upcoming_meetings error: {e}")
            return {
                "success": False,
                "error": str(e),
                "voice_response": "I couldn't retrieve your meetings."
            }

    async def _get_travel_stats_wrapper(self, context: Dict, params: Dict) -> Dict:
        """Get travel statistics."""
        try:
            stats = get_dashboard_stats(user_id=context["user_id"])

            # Format key stats for voice
            total_requests = stats.get("total_requests", 0)
            pending_count = stats.get("pending_approvals", 0)
            total_spend = stats.get("total_spend", 0)

            voice_response = f"You have {total_requests} total travel requests. "
            if pending_count > 0:
                voice_response += f"{pending_count} are pending approval. "
            voice_response += f"Total spend is {int(total_spend)} rupees."

            return {
                "success": True,
                "data": stats,
                "voice_response": voice_response
            }

        except Exception as e:
            logger.error(f"[OTIS Functions] get_travel_stats error: {e}")
            return {
                "success": False,
                "error": str(e),
                "voice_response": "I couldn't get travel statistics."
            }

    async def _get_spend_report_wrapper(self, context: Dict, params: Dict) -> Dict:
        """Get spending analysis."""
        try:
            spend_data = get_spend_analysis()

            monthly_spend = spend_data.get("monthly_spend", 0)
            budget = spend_data.get("monthly_budget", 0)
            utilization = spend_data.get("budget_utilization", 0)

            voice_response = f"This month's travel spend is {int(monthly_spend)} rupees."
            if budget:
                voice_response += f" That's {int(utilization)} percent of your {int(budget)} rupee budget."

            return {
                "success": True,
                "data": spend_data,
                "voice_response": voice_response
            }

        except Exception as e:
            logger.error(f"[OTIS Functions] get_spend_report error: {e}")
            return {
                "success": False,
                "error": str(e),
                "voice_response": "I couldn't get the spending report."
            }

    async def _get_travel_policy_wrapper(self, context: Dict, params: Dict) -> Dict:
        """Get travel policy."""
        try:
            policy = get_active_policy()

            if not policy:
                return {
                    "success": False,
                    "error": "No policy found",
                    "voice_response": "No travel policy is configured."
                }

            flight_class = policy.get("flight_class", "economy")
            hotel_budget = policy.get("hotel_budget_per_night", 0)
            per_diem = policy.get("per_diem_inr", 0)

            voice_response = f"Your travel policy allows {flight_class} class flights. "
            voice_response += f"Hotel budget is {int(hotel_budget)} rupees per night. "
            voice_response += f"Per diem is {int(per_diem)} rupees per day."

            return {
                "success": True,
                "data": policy,
                "voice_response": voice_response
            }

        except Exception as e:
            logger.error(f"[OTIS Functions] get_travel_policy error: {e}")
            return {
                "success": False,
                "error": str(e),
                "voice_response": "I couldn't get the travel policy."
            }

    async def _get_schedule_today_wrapper(self, context: Dict, params: Dict) -> Dict:
        """Get today's schedule."""
        try:
            today = datetime.now().strftime("%Y-%m-%d")

            # Get meetings today
            meetings = get_all_meetings(
                user_id=context["user_id"],
                meeting_date=today,
                role=context.get("user_role", "employee")
            )

            # Get trips today
            db = get_db()
            trips = db.execute(
                "SELECT * FROM travel_requests WHERE user_id = ? AND start_date = ?",
                (context["user_id"], today)
            ).fetchall()
            db.close()

            meeting_count = len(meetings)
            trip_count = len(trips)

            if meeting_count == 0 and trip_count == 0:
                return {
                    "success": True,
                    "data": {"meetings": [], "trips": [], "count": 0},
                    "voice_response": "You have nothing scheduled today."
                }

            voice_parts = []
            if trip_count > 0:
                voice_parts.append(f"{trip_count} trip")
                if trip_count > 1:
                    voice_parts[-1] += "s"

            if meeting_count > 0:
                voice_parts.append(f"{meeting_count} meeting")
                if meeting_count > 1:
                    voice_parts[-1] += "s"

            voice_response = f"Today you have {' and '.join(voice_parts)}."

            return {
                "success": True,
                "data": {"meetings": [dict(m) for m in meetings], "trips": [dict(t) for t in trips]},
                "voice_response": voice_response
            }

        except Exception as e:
            logger.error(f"[OTIS Functions] get_schedule_today error: {e}")
            return {
                "success": False,
                "error": str(e),
                "voice_response": "I couldn't get today's schedule."
            }


# ── Global Registry Instance ──────────────────────────────────────────────────

# Create global registry instance
otis_functions = OtisFunctionRegistry()


# ── Utility Functions ─────────────────────────────────────────────────────────

def get_function_catalog_for_llm(user_role: str = "employee") -> str:
    """
    Get function catalog for LLM prompt.

    This is used by OTIS agent to tell Gemini what functions are available.
    """
    return otis_functions.get_function_descriptions_for_llm(user_role)


async def execute_otis_function(
    function_name: str,
    parameters: Dict[str, Any],
    user_id: int,
    user_role: str = "employee",
    org_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    Execute an OTIS function.

    This is the main entry point for function execution.
    """
    return await otis_functions.execute_function(
        function_name=function_name,
        parameters=parameters,
        user_id=user_id,
        user_role=user_role,
        org_id=org_id
    )


if __name__ == "__main__":
    # Test function registry
    print("=" * 70)
    print("OTIS Function Registry")
    print("=" * 70)

    print(f"\nTotal functions: {len(otis_functions._functions)}")

    print("\n" + "=" * 70)
    print("Employee Functions:")
    print("=" * 70)
    catalog = get_function_catalog_for_llm("employee")
    print(catalog)

    print("\n" + "=" * 70)
    print("Admin Functions:")
    print("=" * 70)
    catalog = get_function_catalog_for_llm("admin")
    print(catalog)

    print("\n" + "=" * 70)
