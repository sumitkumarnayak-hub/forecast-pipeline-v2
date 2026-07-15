import sys
import os
import time
import threading
import uuid
import concurrent.futures
import logging
logger = logging.getLogger("stress_test")
logging.basicConfig(level=logging.INFO)

# Add backend to sys path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import config
from core.database.engine import get_shared_database
from core.database.models import Base, QueueJob
from core.queue.driver import PostgresQueueDriver
from core.queue.worker import QueueWorker
from sqlalchemy.orm import sessionmaker

# 1. Setup DB
db = get_shared_database()
engine = db.engine
SessionLocal = sessionmaker(bind=engine)
Base.metadata.create_all(bind=engine)

# 2. Define Mock Handlers for Stress Test
def mock_email_handler(payload):
    time.sleep(0.1) # Simulate network delay

def mock_sheets_handler(payload):
    time.sleep(0.2) # Simulate Google Sheets delay

def mock_ph_sync_handler(payload):
    time.sleep(0.15) # Simulate master sync

# 3. Create a custom worker that uses mock handlers to prevent destroying real sheets
worker = QueueWorker(SessionLocal)
worker.register("npl.send_email", mock_email_handler)
worker.register("npl.sheets_sync", mock_sheets_handler)
worker.register("npl.delete_submission_rows", mock_sheets_handler)
worker.register("npl.ph_sync", mock_ph_sync_handler)
worker.register("npl.new_hub_sync", mock_ph_sync_handler)

def enqueue_job(task_name):
    with SessionLocal() as session:
        driver = PostgresQueueDriver(session)
        driver.enqueue(task_name, payload={"test": True, "id": str(uuid.uuid4())})

def run_stress_test():
    tasks = [
        "npl.send_email", 
        "npl.sheets_sync", 
        "npl.delete_submission_rows", 
        "npl.ph_sync", 
        "npl.new_hub_sync"
    ] * 20 # 100 jobs total

    logger.info("=== Enqueueing 100 jobs simultaneously ===")
    start_time = time.time()
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        executor.map(enqueue_job, tasks)
        
    logger.info(f"Enqueued 100 jobs in {time.time() - start_time:.2f} seconds")
    
    logger.info("=== Starting 3 concurrent queue workers ===")
    
    # Run 3 workers in parallel to test SKIP LOCKED
    def run_worker_loop():
        # process up to 40 jobs per worker
        for _ in range(40):
            with SessionLocal() as session:
                driver = PostgresQueueDriver(session)
                job = driver.dequeue(worker.worker_id)
                if job:
                    worker.process_job(driver, job)
                else:
                    time.sleep(0.1)
                
    threads = []
    for i in range(3):
        t = threading.Thread(target=run_worker_loop, name=f"Worker-{i}")
        t.start()
        threads.append(t)
        
    for t in threads:
        t.join()
        
    logger.info("=== Stress Test Completed ===")
    
    # Verify results
    with SessionLocal() as session:
        completed = session.query(QueueJob).filter_by(status='completed').count()
        failed = session.query(QueueJob).filter_by(status='failed').count()
        pending = session.query(QueueJob).filter_by(status='pending').count()
        logger.info(f"Final State -> Completed: {completed}, Failed: {failed}, Pending: {pending}")

if __name__ == "__main__":
    run_stress_test()
