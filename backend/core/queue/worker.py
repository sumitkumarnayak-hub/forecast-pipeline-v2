import time
import json
import uuid
import logging
import traceback
import threading
from typing import Callable, Dict
from sqlalchemy.orm import Session
from sqlalchemy.engine import Engine
from sqlalchemy import text
from .driver import PostgresQueueDriver

logger = logging.getLogger(__name__)

class QueueWorker:
    def __init__(self, engine: Engine, sleep_interval: float = 5.0):
        self.engine = engine
        self.sleep_interval = sleep_interval
        self.worker_id = f"worker-{uuid.uuid4().hex[:8]}"
        self.registry: Dict[str, Callable] = {}
        self.stop_event = threading.Event()
        self._last_cleanup = 0.0

    def register(self, task_name: str, handler: Callable):
        """Registers a function to handle a specific task_name."""
        self.registry[task_name] = handler

    def process_job(self, driver: PostgresQueueDriver, job):
        logger.info(f"[{self.worker_id}] Picked up job {job.id} (task: {job.task_name})")
        
        handler = self.registry.get(job.task_name)
        if not handler:
            error_msg = f"No handler registered for task '{job.task_name}'"
            logger.error(error_msg)
            driver.mark_failed(job.id, error_msg)
            return

        try:
            payload = json.loads(job.payload) if job.payload else {}
            # Execute the handler synchronously in this worker thread
            handler(payload)
            driver.mark_completed(job.id)
            logger.info(f"[{self.worker_id}] Successfully completed job {job.id}")
            
        except Exception as e:
            error_trace = traceback.format_exc()
            logger.error(f"[{self.worker_id}] Job {job.id} failed: {error_trace}")
            driver.mark_failed(job.id, error_trace)

    def _cleanup_old_jobs(self):
        """Periodically deletes completed/permanently-failed jobs older than 7 days."""
        now = time.time()
        # Run cleanup at most once per hour
        if now - self._last_cleanup < 3600:
            return
            
        self._last_cleanup = now
        try:
            with Session(self.engine) as db:
                is_postgres = db.bind.dialect.name == "postgresql" if db.bind else False
                if is_postgres:
                    result = db.execute(text(
                        "DELETE FROM queue_jobs WHERE "
                        "(status = 'completed' OR (status = 'failed' AND retries >= max_retries)) "
                        "AND updated_at < NOW() - INTERVAL '7 days'"
                    ))
                else:
                    result = db.execute(text(
                        "DELETE FROM queue_jobs WHERE "
                        "(status = 'completed' OR (status = 'failed' AND retries >= max_retries)) "
                        "AND updated_at < datetime('now', '-7 days')"
                    ))
                db.commit()
                logger.info(f"[{self.worker_id}] Cleaned up {result.rowcount} old queue jobs.")
        except Exception as e:
            logger.warning(f"[{self.worker_id}] Failed to clean up old queue jobs: {e}")

    def run(self, stop_event: threading.Event = None):
        """Continually polls for jobs until stop_event is set."""
        if stop_event:
            self.stop_event = stop_event
            
        logger.info(f"Starting Queue Worker {self.worker_id} polling every {self.sleep_interval}s...")
        while not self.stop_event.is_set():
            job_processed = False
            try:
                # Run cleanup periodically
                self._cleanup_old_jobs()
                
                # We use a fresh DB session for each poll/process cycle to ensure we don't hold long transactions
                with Session(self.engine) as db:
                    driver = PostgresQueueDriver(db)
                    job = driver.dequeue(self.worker_id)
                    
                    if job:
                        self.process_job(driver, job)
                        job_processed = True
                        
            except Exception as e:
                logger.error(f"[{self.worker_id}] Worker loop error: {e}")
                
            # If we didn't process a job, sleep. If we did, loop immediately to pick up the next one.
            if not job_processed and not self.stop_event.is_set():
                # Sleep in small chunks so we can respond to stop_event quickly
                sleep_time = 0.0
                while sleep_time < self.sleep_interval and not self.stop_event.is_set():
                    time.sleep(0.5)
                    sleep_time += 0.5
