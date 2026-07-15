import sys
import os
import time
import json
import threading

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app import config # This loads the .env
from core.database.engine import get_shared_database
from core.database.models import Base, QueueJob
from core.queue.driver import PostgresQueueDriver
from core.queue.worker import QueueWorker

db = get_shared_database()
engine = db.engine
SessionLocal = sessionmaker(bind=engine)

# Create the tables (QueueJob specifically)
Base.metadata.create_all(bind=engine)

print("--- Testing Queue System ---")

def dummy_task(payload):
    print(f"[TASK] Executing dummy task with payload: {payload}")
    if payload.get("should_fail"):
        raise ValueError("Intentional failure!")

# 1. Enqueue tasks
def test_enqueue():
    db = SessionLocal()
    driver = PostgresQueueDriver(db)
    
    id1 = driver.enqueue("test.dummy", {"data": "task 1"})
    id2 = driver.enqueue("test.dummy", {"data": "task 2", "should_fail": True})
    
    print(f"Enqueued tasks: {id1}, {id2}")
    db.close()
    return id1, id2

def run_worker():
    worker = QueueWorker(db_factory=SessionLocal, sleep_interval=1)
    worker.register("test.dummy", dummy_task)
    print("[WORKER] Starting...")
    
    # Run a few poll cycles manually instead of while True
    for _ in range(5):
        try:
            with SessionLocal() as db:
                driver = PostgresQueueDriver(db)
                job = driver.dequeue(worker.worker_id)
                if job:
                    worker.process_job(driver, job)
                else:
                    time.sleep(0.5)
        except Exception as e:
            print("Worker error:", e)

if __name__ == "__main__":
    job1, job2 = test_enqueue()
    
    worker_thread = threading.Thread(target=run_worker)
    worker_thread.start()
    worker_thread.join()
    
    # 3. Verify status
    db = SessionLocal()
    j1 = db.query(QueueJob).filter_by(id=job1).first()
    j2 = db.query(QueueJob).filter_by(id=job2).first()
    
    print(f"Job 1 Status: {j1.status} (retries: {j1.retries})")
    print(f"Job 2 Status: {j2.status} (retries: {j2.retries}) - Error: {j2.error_message[:20] if j2.error_message else None}...")
    
    db.close()
