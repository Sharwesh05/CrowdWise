"""Lightweight background worker.

Four periodic jobs, all idempotent and safe to run repeatedly:

* classify feedback that is still pending
* close campaigns whose deadline has passed
* close governance rounds whose voting window has expired
* anchor contributions still waiting on the chain

Deliberately a thread rather than Celery: no broker to run, nothing extra in the
compose file, and every job is a plain function the test suite can call directly.
Swapping in Celery or RQ later means changing this file only.
"""

from __future__ import annotations

import threading
import time

from app.core.db import session_scope
from app.core.logging import get_logger
from app.services import blockchain_service, campaign_service, governance_service, sentiment_service

logger = get_logger("worker")

_stop = threading.Event()
_thread: threading.Thread | None = None


def run_once() -> dict[str, int]:
    """Run every periodic job once. Safe to call from a script or a test."""
    results = {"feedback": 0, "deadlines": 0, "governance": 0, "blockchain": 0}
    db = session_scope()
    try:
        results["feedback"] = sentiment_service.analyze_pending(db, limit=100)
    except Exception as exc:
        logger.error("worker_feedback_failed", error=str(exc))
        db.rollback()
    try:
        results["deadlines"] = campaign_service.process_due_deadlines(db)
    except Exception as exc:
        logger.error("worker_deadline_failed", error=str(exc))
        db.rollback()
    try:
        results["governance"] = governance_service.process_due_governance(db)
    except Exception as exc:
        logger.error("worker_governance_failed", error=str(exc))
        db.rollback()
    try:
        results["blockchain"] = blockchain_service.sync_pending_contributions(db)
    except Exception as exc:
        logger.error("worker_chain_failed", error=str(exc))
        db.rollback()
    finally:
        db.close()
    if any(results.values()):
        logger.info("worker_cycle", **results)
    return results


def _loop(interval: float) -> None:  # pragma: no cover - thread body
    while not _stop.wait(interval):
        try:
            run_once()
        except Exception as exc:
            logger.error("worker_cycle_failed", error=str(exc))


def start(interval: float = 30.0) -> None:  # pragma: no cover - thread mgmt
    global _thread
    if _thread and _thread.is_alive():
        return
    _stop.clear()
    _thread = threading.Thread(target=_loop, args=(interval,), name="crowdwise-worker", daemon=True)
    _thread.start()
    logger.info("worker_started", interval=interval)


def stop() -> None:  # pragma: no cover - thread mgmt
    _stop.set()


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    from app.core.config import settings
    from app.core.logging import configure_logging

    configure_logging(settings.log_level)
    logger.info("worker_process_started")
    while True:
        run_once()
        time.sleep(30)
