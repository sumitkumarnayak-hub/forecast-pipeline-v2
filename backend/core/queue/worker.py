import time
import json
import uuid
import logging
import traceback
from typing import Callable, Dict
from sqlalchemy.orm import Session
from .driver import PostgresQueueDriver
from core.database.engine import Database

logger = logging.getLogger(__name__)

class QueueWorker:
    def __init__(self, db_factory: Callable[[], Session], sleep_interval: int = 5):
        self.db_factory = db_factory
        self.sleep_interval = sleep_interval
        self.worker_id = f"worker-{uuid.uuid4().hex[:8]}"
        self.registry: Dict[str, Callable] = {}

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

    def run(self):
        """Continually polls for jobs."""
        logger.info(f"Starting Queue Worker {self.worker_id} polling every {self.sleep_interval}s...")
        while True:
            try:
                # We use a fresh DB session for each poll/process cycle to ensure we don't hold long transactions
                with self.db_factory() as db:
                    driver = PostgresQueueDriver(db)
                    job = driver.dequeue(self.worker_id)
                    
                    if job:
                        self.process_job(driver, job)
                    else:
                        # Sleep if no jobs were found
                        time.sleep(self.sleep_interval)
            except Exception as e:
                logger.error(f"[{self.worker_id}] Worker loop error: {e}")
                time.sleep(self.sleep_interval)
