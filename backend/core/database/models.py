from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey, LargeBinary, Text
from sqlalchemy.orm import declarative_base
from sqlalchemy.sql import func

Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    password_hash = Column(String, nullable=False)
    full_name = Column(String)
    email = Column(String, unique=True, nullable=False)
    role = Column(String, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_login = Column(DateTime(timezone=True))


class UserPreference(Base):
    __tablename__ = "user_preferences"

    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    email_notifications = Column(Boolean, default=True)
    auto_sync_masters = Column(Boolean, default=False)
    preview_rows = Column(Integer, default=100)
    updated_at = Column(DateTime(timezone=True))


class BaselineRun(Base):
    __tablename__ = "baseline_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(String, unique=True, nullable=False)
    run_name = Column(String)
    run_date = Column(DateTime(timezone=True), server_default=func.now())
    user_id = Column(Integer, ForeignKey("users.id"))
    status = Column(String)
    raw_data_file = Column(String)
    output_file = Column(String)
    summary_stats = Column(String)
    parameters = Column(String)
    validation_status = Column(String)
    approved_by = Column(Integer)
    approved_at = Column(DateTime(timezone=True))
    session_id = Column(String)
    approval_session_id = Column(String)


class FinalPlanRun(Base):
    __tablename__ = "final_plan_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(String, unique=True, nullable=False)
    run_name = Column(String)
    run_date = Column(DateTime(timezone=True), server_default=func.now())
    user_id = Column(Integer, ForeignKey("users.id"))
    baseline_run_id = Column(String, ForeignKey("baseline_runs.run_id"))
    status = Column(String)
    output_file = Column(String)
    summary_stats = Column(String)
    festive_inputs = Column(String)
    adhoc_inputs = Column(String)
    validation_status = Column(String)
    approved_by = Column(Integer)
    approved_at = Column(DateTime(timezone=True))
    session_id = Column(String)


class PipelineRun(Base):
    __tablename__ = "pipeline_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(String, unique=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"))
    status = Column(String)
    current_step = Column(String)
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True))
    summary_stats = Column(String)
    session_id = Column(String)


class PipelineStepLog(Base):
    __tablename__ = "pipeline_step_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(String, ForeignKey("pipeline_runs.run_id"), nullable=False)
    step_key = Column(String, nullable=False)
    step_name = Column(String)
    step_order = Column(Integer)
    status = Column(String)
    message = Column(String)
    error_detail = Column(String)
    logged_at = Column(DateTime(timezone=True), server_default=func.now())
    session_id = Column(String)


class AuthSession(Base):
    __tablename__ = "auth_sessions"

    session_id = Column(String, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    system_details = Column(String)


class MasterSyncLog(Base):
    __tablename__ = "master_sync_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    sync_date = Column(DateTime(timezone=True), server_default=func.now())
    master_type = Column(String)
    user_id = Column(Integer, ForeignKey("users.id"))
    records_synced = Column(Integer)
    status = Column(String)
    error_message = Column(String)
    session_id = Column(String)


class PipelineRunLogLine(Base):
    __tablename__ = "pipeline_run_log_lines"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(String, ForeignKey("pipeline_runs.run_id"), nullable=False)
    level = Column(String)
    message = Column(String, nullable=False)
    logged_at = Column(DateTime(timezone=True), server_default=func.now())


class EmailNotificationRecipient(Base):
    __tablename__ = "email_notification_recipients"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String, nullable=False)
    display_name = Column(String)
    category = Column(String, nullable=False)
    enabled = Column(Boolean, default=True)
    created_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True))


class EmailLog(Base):
    __tablename__ = "email_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    sent_at = Column(DateTime(timezone=True), server_default=func.now())
    email_type = Column(String)
    subject = Column(String)
    recipients = Column(String)
    status = Column(String)
    error_message = Column(String)
    body_preview = Column(String)
    triggered_by_user_id = Column(Integer, ForeignKey("users.id"))
    session_id = Column(String)
    metadata_ = Column("metadata", String)


class SyncRun(Base):
    __tablename__ = "sync_run"

    id = Column(String, primary_key=True)
    started_at = Column(DateTime(timezone=True), nullable=False)
    finished_at = Column(DateTime(timezone=True))
    triggered_by = Column(String(64))
    step_name = Column(String(64))
    status = Column(String(16), default="running")
    error_msg = Column(Text)


class SyncSnapshot(Base):
    __tablename__ = "sync_snapshot"

    id = Column(String, primary_key=True)
    sync_run_id = Column(String, nullable=False)
    sheet_name = Column(String(128), nullable=False)
    snapshot_parquet = Column(LargeBinary, nullable=False)
    row_count = Column(Integer)
    created_at = Column(DateTime(timezone=True), nullable=False)
    user_id = Column(String(64))


class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(String, primary_key=True)
    sync_run_id = Column(String)
    action = Column(String(64))
    user_id = Column(String(64))
    sheet_name = Column(String(128))
    rows_affected = Column(Integer)
    status = Column(String(16))
    ts = Column(DateTime(timezone=True), nullable=False)


class WriteQueue(Base):
    __tablename__ = "write_queue"

    id = Column(String, primary_key=True)
    sheet_name = Column(String(128))
    payload = Column(Text)
    status = Column(String(16), default="pending")
    created_at = Column(DateTime(timezone=True))
    flushed_at = Column(DateTime(timezone=True))


class NplSubmission(Base):
    """Mirror of Google Sheets Submission_Log for fast DB-side queries."""
    __tablename__ = "npl_submissions"

    id               = Column(Integer, primary_key=True, autoincrement=True)
    submission_id    = Column(String, unique=True, nullable=False, index=True)
    sub_type         = Column(String)          # New Launch | Expansion | Replacement
    product_id       = Column(String)
    product_name     = Column(String)
    category         = Column(String)
    cities           = Column(String)          # comma-separated city list
    hub_count        = Column(Integer, default=0)
    city_count       = Column(Integer, default=0)
    start_date       = Column(String)
    status           = Column(String, default="Pending")
    rejection_reason = Column(String)
    submitted_by     = Column(String)
    user_id          = Column(Integer, ForeignKey("users.id"), nullable=True)
    step_log         = Column(Text)            # JSON — per-wizard-step timing/errors
    timestamp        = Column(DateTime(timezone=True), server_default=func.now())
    notes            = Column(Text)            # Notes from submissions

class QueueJob(Base):
    __tablename__ = "queue_jobs"

    id = Column(String, primary_key=True)
    task_name = Column(String, nullable=False, index=True)
    payload = Column(Text, nullable=False)
    status = Column(String, default="pending", index=True)
    retries = Column(Integer, default=0)
    max_retries = Column(Integer, default=3)
    error_message = Column(Text)
    locked_by = Column(String, index=True)
    locked_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
