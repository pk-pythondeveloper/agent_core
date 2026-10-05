import asyncio
import os
from app.celery_app import celery_app

_worker_loop = None
_worker_pid = None


def _get_worker_loop():
    """Keep async DB/Redis clients on one event loop for this Celery process."""
    global _worker_loop, _worker_pid
    pid = os.getpid()
    # Celery's prefork workers inherit imported modules from the parent. Create
    # the loop lazily in each child so no loop is shared across forked processes.
    if _worker_loop is None or _worker_pid != pid or _worker_loop.is_closed():
        _worker_loop = asyncio.new_event_loop()
        _worker_pid = pid
    return _worker_loop


@celery_app.task(name="execute_agent_run", bind=True, acks_late=True)
def execute_agent_run_task(self, run_id: str):
    from app.agent.runner import execute_agent_run_safe
    # asyncio.run() closes its loop after every task. The async SQLAlchemy and
    # Redis pools then retain connections bound to that closed loop. Reuse the
    # worker process's loop across tasks instead.
    return _get_worker_loop().run_until_complete(execute_agent_run_safe(run_id))
