import sys
import os
import logging

# Ensure the backend directory is in the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.database.engine import get_db, SessionLocal
from core.queue.worker import QueueWorker

# Setup basic logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("QueueWorkerDaemon")

def db_factory():
    """Provides a fresh database session for the worker."""
    return SessionLocal()

def start_worker():
    worker = QueueWorker(db_factory=db_factory, sleep_interval=5)
    
    # Register handlers here. We will import them lazily or directly.
    from features.product_launch.tasks import register_npl_tasks
    register_npl_tasks(worker)
    
    logger.info("Starting up the queue worker daemon...")
    worker.run()

if __name__ == "__main__":
    start_worker()
