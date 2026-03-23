"""
TravelSync Pro — Background Task Queue
Thread-pool based async task runner with SocketIO progress events.
No external dependencies (no Redis/Celery required).

Usage:
    from services.task_queue import task_queue

    task_id = task_queue.submit(
        fn=plan_trip,
        args=(trip_input,),
        user_id=user["id"],
        task_type="plan_trip",
    )

    task_queue.get_status(task_id)  # → {status, progress, result, error}
"""
import uuid
import logging
import threading
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from cachetools import TTLCache

logger = logging.getLogger(__name__)


class TaskQueue:
    """In-process background task runner with progress tracking."""

    def __init__(self, max_workers: int = 4):
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="task")
        self._tasks = TTLCache(maxsize=200, ttl=3600)  # Tasks expire after 1 hour
        self._lock = threading.Lock()

    def submit(self, fn, args=(), kwargs=None, user_id=None, task_type="generic") -> str:
        """Submit a function for background execution. Returns task_id."""
        task_id = str(uuid.uuid4())[:12]
        kwargs = kwargs or {}

        with self._lock:
            self._tasks[task_id] = {
                "id": task_id,
                "type": task_type,
                "status": "pending",
                "progress": 0,
                "user_id": user_id,
                "created_at": datetime.now().isoformat(),
                "result": None,
                "error": None,
            }

        def _run():
            self._update(task_id, status="running", progress=10)
            self._emit_progress(task_id, user_id, "running", 10)
            try:
                result = fn(*args, **kwargs)
                self._update(task_id, status="completed", progress=100, result=result)
                self._emit_progress(task_id, user_id, "completed", 100)
            except Exception as e:
                logger.exception("[TaskQueue] Task %s failed", task_id)
                self._update(task_id, status="failed", error=str(e))
                self._emit_progress(task_id, user_id, "failed", 0)

        self._executor.submit(_run)
        return task_id

    def get_status(self, task_id: str) -> dict:
        """Get current status of a task."""
        with self._lock:
            task = self._tasks.get(task_id)
        if not task:
            return {"id": task_id, "status": "not_found"}
        return dict(task)

    def get_result(self, task_id: str) -> dict:
        """Get the result of a completed task."""
        status = self.get_status(task_id)
        if status["status"] == "completed":
            return {"success": True, "result": status.get("result")}
        elif status["status"] == "failed":
            return {"success": False, "error": status.get("error")}
        return {"success": False, "status": status["status"], "progress": status.get("progress", 0)}

    def list_tasks(self, user_id: int = None) -> list:
        """List recent tasks, optionally filtered by user."""
        with self._lock:
            tasks = list(self._tasks.values())
        if user_id is not None:
            tasks = [t for t in tasks if t.get("user_id") == user_id]
        return sorted(tasks, key=lambda t: t.get("created_at", ""), reverse=True)

    def _update(self, task_id: str, **fields):
        with self._lock:
            if task_id in self._tasks:
                self._tasks[task_id].update(fields)
                if fields.get("status") in ("completed", "failed"):
                    self._tasks[task_id]["completed_at"] = datetime.now().isoformat()

    def _emit_progress(self, task_id: str, user_id, status: str, progress: int):
        """Emit task progress via SocketIO."""
        try:
            from extensions import socketio
            event_data = {
                "task_id": task_id,
                "status": status,
                "progress": progress,
                "timestamp": datetime.now().isoformat(),
            }
            if user_id:
                socketio.emit("task_progress", event_data, to=f"user_{user_id}", namespace="/")
            else:
                socketio.emit("task_progress", event_data, namespace="/")
        except Exception:
            pass


# Singleton instance
task_queue = TaskQueue(max_workers=4)
