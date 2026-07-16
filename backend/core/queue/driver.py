import json
import uuid
import logging
from typing import Any, Dict, Optional
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session
from sqlalchemy.sql import text

from core.database.models import QueueJob

logger = logging.getLogger(__name__)

class PostgresQueueDriver:
    """
    A robust queue driver backed by PostgreSQL using SKIP LOCKED for concurrent worker safety.
    """
    
    def __init__(self, session: Session):
        self.db = session

    def enqueue(self, task_name: str, payload: Dict[str, Any], max_retries: int = 3) -> str:
        """Adds a new job to the queue."""
        job_id = str(uuid.uuid4())
        job = QueueJob(
            id=job_id,
            task_name=task_name,
            payload=json.dumps(payload),
            status="pending",
            max_retries=max_retries
        )
        self.db.add(job)
        self.db.commit()
        return job_id

    def dequeue(self, worker_id: str) -> Optional[QueueJob]:
        """
        Pulls the next pending job from the queue safely.
        """
        # Determine dialect to conditionally use SKIP LOCKED
        is_postgres = self.db.bind.dialect.name == "postgresql" if self.db.bind else False
        
        if is_postgres:
            sql = text("""
                UPDATE queue_jobs
                SET status = 'processing',
                    locked_by = :worker_id,
                    locked_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = (
                    SELECT id
                    FROM queue_jobs
                    WHERE status = 'pending'
                       OR (status = 'failed' AND retries < max_retries)
                    ORDER BY created_at ASC
                    FOR UPDATE SKIP LOCKED
                    LIMIT 1
                )
                RETURNING id;
            """)
            result = self.db.execute(sql, {"worker_id": worker_id}).fetchone()
            self.db.commit()
            if not result:
                return None
            job_id = result[0]
        else:
            # Fallback for SQLite (no SKIP LOCKED support)
            # Not fully safe for concurrent workers, but works for local testing
            job = self.db.query(QueueJob).filter(
                (QueueJob.status == 'pending') | 
                ((QueueJob.status == 'failed') & (QueueJob.retries < QueueJob.max_retries))
            ).order_by(QueueJob.created_at.asc()).first()
            
            if not job:
                return None
                
            job.status = 'processing'
            job.locked_by = worker_id
            job.locked_at = datetime.now(timezone.utc)
            self.db.commit()
            job_id = job.id
            
        return self.db.query(QueueJob).filter_by(id=job_id).first()

    def mark_completed(self, job_id: str):
        """Marks a job as completed and clears the lock."""
        job = self.db.query(QueueJob).filter_by(id=job_id).first()
        if job:
            job.status = "completed"
            job.completed_at = datetime.now(timezone.utc)
            job.locked_by = None
            job.locked_at = None
            self.db.commit()

    def mark_failed(self, job_id: str, error_message: str):
        """
        Marks a job as failed, increments the retry counter.
        If retries >= max_retries, it stays failed permanently (dead letter).
        """
        job = self.db.query(QueueJob).filter_by(id=job_id).first()
        if job:
            job.retries += 1
            job.error_message = error_message
            job.locked_by = None
            job.locked_at = None
            # Leave as failed. Dequeue will pick it up again if retries < max_retries
            job.status = "failed"
            self.db.commit()
