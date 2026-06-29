"""
Database models and operations for Planning & Forecasting Tool.

Uses Supabase (PostgreSQL) when DATABASE_URL is set in .env, otherwise local SQLite.
"""
import json
import secrets
from contextlib import contextmanager
from datetime import datetime, timedelta

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from planning_suite.config import (
    DATABASE_PATH,
    IS_PRODUCTION,
    get_database_backend,
    get_database_host_label,
    get_database_url,
    get_supabase_project_ref,
)



def _order_by_desc_nulls_last(column: str, backend: str) -> str:
    """SQLite-compatible replacement for ``ORDER BY col DESC NULLS LAST``."""
    if backend == "postgresql":
        return f"{column} DESC NULLS LAST"
    return f"({column} IS NULL), {column} DESC"


class Database:
    """Database handler for storing run history and user data."""

    def __init__(self, db_url=None, db_path=DATABASE_PATH, *, require_postgresql=False):
        resolved_url = db_url or get_database_url()
        if require_postgresql and not resolved_url:
            raise ValueError(
                "DATABASE_URL is required but not set in .env. "
                "Add your Supabase connection string and restart Streamlit."
            )
        self.require_postgresql = require_postgresql
        self.database_url = resolved_url
        self.backend = get_database_backend(resolved_url)
        self.db_path = db_path
        self.engine: Engine = self._create_engine(resolved_url, db_path)
        try:
            self.init_database()
        except Exception as e:
            if not self.require_postgresql and self.backend == "postgresql":
                import sys
                print("⚠️ Connection to PostgreSQL failed. Falling back to local SQLite...", file=sys.stderr)
                print(f"Error: {e}", file=sys.stderr)
                self.database_url = None
                self.backend = "sqlite"
                self.engine = self._create_engine(None, db_path)
                self.init_database()
            else:
                raise

    @classmethod
    def for_supabase(cls) -> "Database":
        """Open a Supabase-only connection (never falls back to SQLite)."""
        return cls(require_postgresql=True)

    def connection_label(self) -> str:
        """Human-readable target for UI (no secrets)."""
        if self.backend != "postgresql":
            return "local SQLite (`forecasting_db.sqlite`)"
        project_ref = get_supabase_project_ref(self.database_url)
        host = get_database_host_label(self.database_url)
        parts = ["Supabase PostgreSQL"]
        if project_ref:
            parts.append(f"project `{project_ref}`")
        if host:
            parts.append(f"host `{host}`")
        return " · ".join(parts)

    def _create_engine(self, db_url, db_path) -> Engine:
        if self.backend == "postgresql":
            url = db_url
            if url.startswith("postgres://"):
                url = url.replace("postgres://", "postgresql://", 1)
            return create_engine(url, pool_pre_ping=True)
        sqlite_path = db_path.as_posix() if hasattr(db_path, "as_posix") else str(db_path)
        return create_engine(
            f"sqlite:///{sqlite_path}",
            connect_args={"check_same_thread": False},
        )

    @contextmanager
    def get_connection(self):
        """Yield a SQLAlchemy connection (compatible with pandas read_sql)."""
        with self.engine.connect() as conn:
            yield conn

    def init_database(self):
        """Initialize database tables."""
        statements = (
            _POSTGRES_SCHEMA if self.backend == "postgresql" else _SQLITE_SCHEMA
        )
        with self.engine.begin() as conn:
            for statement in statements:
                conn.execute(text(statement))
            self._migrate_auth_sessions(conn)
            self._migrate_session_id_columns(conn)
            self._migrate_pipeline_run_log_lines(conn)
        if not IS_PRODUCTION:
            self.create_default_users()

    def _migrate_auth_sessions(self, conn) -> None:
        """Add columns introduced after initial auth_sessions schema."""
        if self.backend == "postgresql":
            conn.execute(
                text(
                    "ALTER TABLE auth_sessions "
                    "ADD COLUMN IF NOT EXISTS system_details TEXT"
                )
            )
            return

        columns = conn.execute(text("PRAGMA table_info(auth_sessions)")).fetchall()
        existing = {row[1] for row in columns}
        if "system_details" not in existing:
            conn.execute(
                text("ALTER TABLE auth_sessions ADD COLUMN system_details TEXT")
            )

    _SESSION_ID_COLUMNS: tuple[tuple[str, str], ...] = (
        ("baseline_runs", "session_id"),
        ("baseline_runs", "approval_session_id"),
        ("final_plan_runs", "session_id"),
        ("master_sync_log", "session_id"),
        ("pipeline_runs", "session_id"),
        ("pipeline_step_logs", "session_id"),
    )

    def _migrate_session_id_columns(self, conn) -> None:
        """Add session_id audit columns linked to auth_sessions."""
        if self.backend == "postgresql":
            for table, column in self._SESSION_ID_COLUMNS:
                conn.execute(
                    text(
                        f"ALTER TABLE {table} "
                        f"ADD COLUMN IF NOT EXISTS {column} TEXT"
                    )
                )
            return

        for table, column in self._SESSION_ID_COLUMNS:
            rows = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
            existing = {row[1] for row in rows}
            if column not in existing:
                conn.execute(
                    text(f"ALTER TABLE {table} ADD COLUMN {column} TEXT")
                )

    def _migrate_pipeline_run_log_lines(self, conn) -> None:
        """Ensure append-only pipeline run log table exists (autopilot + CLI)."""
        if self.backend == "postgresql":
            conn.execute(
                text("""
                    CREATE TABLE IF NOT EXISTS pipeline_run_log_lines (
                        id BIGSERIAL PRIMARY KEY,
                        run_id TEXT NOT NULL,
                        level TEXT,
                        message TEXT NOT NULL,
                        logged_at TIMESTAMPTZ DEFAULT NOW(),
                        FOREIGN KEY (run_id) REFERENCES pipeline_runs (run_id)
                    )
                """)
            )
            return

        conn.execute(
            text("""
                CREATE TABLE IF NOT EXISTS pipeline_run_log_lines (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    level TEXT,
                    message TEXT NOT NULL,
                    logged_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (run_id) REFERENCES pipeline_runs (run_id)
                )
            """)
        )

    @staticmethod
    def _resolve_session_id(explicit: str | None = None) -> str | None:
        if explicit:
            return explicit
        try:
            from planning_suite.services.audit_context import get_audit_session_id

            return get_audit_session_id()
        except Exception:
            return None

    def create_default_users(self):
        """Create default dev users when the database is first initialized (non-production only)."""
        import bcrypt
        from sqlalchemy.exc import IntegrityError

        with self.engine.begin() as conn:
            defaults = [
                ("admin", "admin123", "Administrator", "admin@company.com", "admin"),
                ("planner", "planner123", "Planner User", "planner@company.com", "planner"),
                ("viewer", "viewer123", "Viewer User", "viewer@company.com", "viewer"),
            ]
            for username, password, full_name, email, role in defaults:
                # Check if this specific user already exists
                count = conn.execute(
                    text("SELECT COUNT(*) FROM users WHERE username = :username"),
                    {"username": username}
                ).scalar()
                if count == 0:
                    password_hash = bcrypt.hashpw(
                        password.encode("utf-8"), bcrypt.gensalt()
                    ).decode("utf-8")
                    try:
                        conn.execute(
                            text("""
                                INSERT INTO users (username, password_hash, full_name, email, role)
                                VALUES (:username, :password_hash, :full_name, :email, :role)
                            """),
                            {
                                "username": username,
                                "password_hash": password_hash,
                                "full_name": full_name,
                                "email": email,
                                "role": role,
                            },
                        )
                    except IntegrityError:
                        # Handle race condition where another thread/process inserted the user concurrently
                        pass


    def authenticate_user(self, username, password):
        """Authenticate user and return user data."""
        import bcrypt
        from sqlalchemy.orm import Session
        from planning_suite.db.models import User

        with Session(self.engine) as session:
            user = session.query(User).filter_by(username=username).first()

        if user and bcrypt.checkpw(password.encode("utf-8"), user.password_hash.encode("utf-8")):
            return {
                "id": user.id,
                "username": user.username,
                "full_name": user.full_name,
                "email": user.email,
                "role": user.role,
            }
        return None

    def get_user_by_username(self, username: str) -> dict | None:
        """Fetch active user profile by username (for session restore)."""
        if not username:
            return None
        from sqlalchemy.orm import Session
        from planning_suite.db.models import User

        with Session(self.engine) as session:
            user = session.query(User).filter_by(username=username).first()

        if not user:
            return None
        return {
            "id": user.id,
            "username": user.username,
            "full_name": user.full_name,
            "email": user.email,
            "role": user.role,
        }

    def get_user_by_id(self, user_id: int) -> dict | None:
        """Fetch active user profile by id."""
        if not user_id:
            return None
        from sqlalchemy.orm import Session
        from planning_suite.db.models import User

        with Session(self.engine) as session:
            user = session.query(User).filter_by(id=user_id).first()
        if not user:
            return None
        return self._row_to_user(user)

    @staticmethod
    def _row_to_user(row) -> dict:
        return {
            "id": row.id if hasattr(row, 'id') else row[0],
            "username": row.username if hasattr(row, 'username') else row[1],
            "full_name": row.full_name if hasattr(row, 'full_name') else row[2],
            "email": row.email if hasattr(row, 'email') else row[3],
            "role": row.role if hasattr(row, 'role') else row[4],
        }

    def create_auth_session(
        self,
        user_id: int,
        days: float = 7,
        *,
        system_details: str | None = None,
    ) -> str:
        """Create a persistent login session and return its opaque id."""
        session_id = secrets.token_urlsafe(32)
        expires_at = datetime.now() + timedelta(days=days)
        if not system_details:
            print(
                f"[auth_sessions] WARNING: creating session for user_id={user_id} "
                "with empty system_details",
                flush=True,
            )
        else:
            print(
                f"[auth_sessions] user_id={user_id} system_details_chars={len(system_details)}",
                flush=True,
            )
        
        from sqlalchemy.orm import Session
        from planning_suite.db.models import AuthSession

        with Session(self.engine) as session:
            new_session = AuthSession(
                session_id=session_id,
                user_id=user_id,
                expires_at=expires_at,
                system_details=system_details
            )
            session.add(new_session)
            session.commit()
        return session_id

    def get_auth_session(self, session_id: str) -> dict | None:
        """Return auth_sessions row metadata for audit/debug."""
        if not session_id:
            return None
        
        from sqlalchemy.orm import Session
        from planning_suite.db.models import AuthSession

        with Session(self.engine) as session:
            row = session.query(AuthSession).filter_by(session_id=session_id).first()
            if not row:
                return None
            return {
                "session_id": row.session_id,
                "user_id": row.user_id,
                "created_at": row.created_at,
                "expires_at": row.expires_at,
                "system_details": row.system_details,
            }

    def update_auth_session_system_details(self, session_id: str, system_details: str) -> bool:
        """Update system_details on an existing auth session row."""
        if not session_id or not system_details:
            return False
        
        from sqlalchemy.orm import Session
        from planning_suite.db.models import AuthSession

        with Session(self.engine) as session:
            row = session.query(AuthSession).filter_by(session_id=session_id).first()
            if not row:
                return False
            row.system_details = system_details
            session.commit()
            return True

    def get_user_by_session(self, session_id: str) -> dict | None:
        """Resolve a browser session cookie to a user profile."""
        if not session_id:
            return None
        
        from sqlalchemy.orm import Session
        from planning_suite.db.models import AuthSession, User

        with Session(self.engine) as session:
            res = (
                session.query(User)
                .join(AuthSession, User.id == AuthSession.user_id)
                .filter(AuthSession.session_id == session_id)
                .filter(AuthSession.expires_at > datetime.now())
                .first()
            )
            if not res:
                return None
            return self._row_to_user(res)

    def delete_auth_session(self, session_id: str) -> None:
        """Invalidate a single auth session."""
        if not session_id:
            return
        
        from sqlalchemy.orm import Session
        from planning_suite.db.models import AuthSession

        with Session(self.engine) as session:
            session.query(AuthSession).filter_by(session_id=session_id).delete()
            session.commit()

    def update_last_login(self, user_id):
        """Update user's last login timestamp."""
        with self.engine.begin() as conn:
            conn.execute(
                text("UPDATE users SET last_login = :last_login WHERE id = :user_id"),
                {"last_login": datetime.now(), "user_id": user_id},
            )

    def save_baseline_run(self, run_data):
        """Save baseline run to database."""
        from sqlalchemy.orm import Session
        from planning_suite.db.models import BaselineRun

        with Session(self.engine) as session:
            br = BaselineRun(
                run_id=run_data["run_id"],
                run_name=run_data["run_name"],
                user_id=run_data["user_id"],
                status=run_data["status"],
                raw_data_file=run_data.get("raw_data_file", ""),
                output_file=run_data.get("output_file", ""),
                summary_stats=json.dumps(run_data.get("summary_stats", {})),
                parameters=json.dumps(run_data.get("parameters", {})),
                validation_status=run_data.get("validation_status", "pending"),
                session_id=self._resolve_session_id(run_data.get("session_id"))
            )
            session.add(br)
            session.commit()

    def update_baseline_run(self, run_id, **fields):
        """Update fields on an existing baseline run."""
        allowed = {
            "status", "output_file", "summary_stats", "parameters",
            "validation_status", "run_name",
        }
        updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
        if not updates:
            return
        if "summary_stats" in updates and not isinstance(updates["summary_stats"], str):
            updates["summary_stats"] = json.dumps(updates["summary_stats"])
        if "parameters" in updates and not isinstance(updates["parameters"], str):
            updates["parameters"] = json.dumps(updates["parameters"])
        set_clause = ", ".join(f"{col} = :{col}" for col in updates)
        updates["run_id"] = run_id
        with self.engine.begin() as conn:
            conn.execute(
                text(f"UPDATE baseline_runs SET {set_clause} WHERE run_id = :run_id"),
                updates,
            )

    def get_baseline_runs(self, limit=50):
        """Get all baseline runs."""
        with self.engine.connect() as conn:
            return pd.read_sql_query(
                text("""
                    SELECT br.*, u.username, u.full_name
                    FROM baseline_runs br
                    LEFT JOIN users u ON br.user_id = u.id
                    ORDER BY br.run_date DESC
                    LIMIT :limit
                """),
                conn,
                params={"limit": limit},
            )

    def get_baseline_run(self, run_id):
        """Get specific baseline run."""
        with self.engine.connect() as conn:
            return conn.execute(
                text("SELECT * FROM baseline_runs WHERE run_id = :run_id"),
                {"run_id": run_id},
            ).fetchone()

    def approve_baseline_run(self, run_id, approver_id, session_id: str | None = None):
        """Approve baseline run."""
        if not run_id:
            return
        approval_session_id = self._resolve_session_id(session_id)
        with self.engine.begin() as conn:
            conn.execute(
                text("""
                    UPDATE baseline_runs
                    SET validation_status = 'approved',
                        approved_by = :approved_by,
                        approved_at = :approved_at,
                        approval_session_id = :approval_session_id
                    WHERE run_id = :run_id
                """),
                {
                    "approved_by": approver_id,
                    "approved_at": datetime.now(),
                    "approval_session_id": approval_session_id,
                    "run_id": run_id,
                },
            )

    def revoke_baseline_approvals(self, run_id: str | None = None) -> None:
        """Reset baseline approval in DB (single run or all approved runs)."""
        with self.engine.begin() as conn:
            if run_id:
                conn.execute(
                    text("""
                        UPDATE baseline_runs
                        SET validation_status = 'pending',
                            approved_by = NULL,
                            approved_at = NULL,
                            approval_session_id = NULL
                        WHERE run_id = :run_id
                          AND validation_status = 'approved'
                    """),
                    {"run_id": run_id},
                )
            else:
                conn.execute(
                    text("""
                        UPDATE baseline_runs
                        SET validation_status = 'pending',
                            approved_by = NULL,
                            approved_at = NULL,
                            approval_session_id = NULL
                        WHERE validation_status = 'approved'
                    """)
                )

    def get_latest_completed_baseline_run_id(self) -> str | None:
        """Return the most recent completed baseline run_id."""
        with self.engine.connect() as conn:
            row = conn.execute(
                text("""
                    SELECT run_id FROM baseline_runs
                    WHERE status = 'completed'
                    ORDER BY run_date DESC
                    LIMIT 1
                """)
            ).fetchone()
        return row[0] if row else None

    def resolve_baseline_run_id_for_approval(self, session_run_id: str | None) -> str | None:
        """Use session run_id when valid, otherwise latest completed run from DB."""
        if session_run_id and session_run_id not in ("N/A", ""):
            if self.get_baseline_run(session_run_id):
                return session_run_id
        return self.get_latest_completed_baseline_run_id()

    def get_user_preferences(self, user_id: int) -> dict:
        """Load user preferences with defaults."""
        from planning_suite.core.permissions import DEFAULT_PREFERENCES

        defaults = dict(DEFAULT_PREFERENCES)
        with self.engine.connect() as conn:
            row = conn.execute(
                text("""
                    SELECT email_notifications, auto_sync_masters, preview_rows
                    FROM user_preferences
                    WHERE user_id = :user_id
                """),
                {"user_id": user_id},
            ).fetchone()
        if not row:
            return defaults
        return {
            "email_notifications": bool(row[0]),
            "auto_sync_masters": bool(row[1]),
            "preview_rows": int(row[2]) if row[2] is not None else defaults["preview_rows"],
        }

    def save_user_preferences(self, user_id: int, prefs: dict) -> None:
        """Upsert user preferences."""
        with self.engine.begin() as conn:
            existing = conn.execute(
                text("SELECT 1 FROM user_preferences WHERE user_id = :user_id"),
                {"user_id": user_id},
            ).scalar()
            params = {
                "user_id": user_id,
                "email_notifications": bool(prefs.get("email_notifications", True)),
                "auto_sync_masters": bool(prefs.get("auto_sync_masters", False)),
                "preview_rows": int(prefs.get("preview_rows", 100)),
                "updated_at": datetime.now(),
            }
            if existing:
                conn.execute(
                    text("""
                        UPDATE user_preferences
                        SET email_notifications = :email_notifications,
                            auto_sync_masters = :auto_sync_masters,
                            preview_rows = :preview_rows,
                            updated_at = :updated_at
                        WHERE user_id = :user_id
                    """),
                    params,
                )
            else:
                conn.execute(
                    text("""
                        INSERT INTO user_preferences
                        (user_id, email_notifications, auto_sync_masters, preview_rows, updated_at)
                        VALUES (:user_id, :email_notifications, :auto_sync_masters, :preview_rows, :updated_at)
                    """),
                    params,
                )

    def save_final_plan_run(self, run_data):
        """Save final plan run to database."""
        session_id = self._resolve_session_id(run_data.get("session_id"))
        with self.engine.begin() as conn:
            conn.execute(
                text("""
                    INSERT INTO final_plan_runs
                    (run_id, run_name, user_id, baseline_run_id, status, output_file,
                     summary_stats, festive_inputs, adhoc_inputs, validation_status, session_id)
                    VALUES (:run_id, :run_name, :user_id, :baseline_run_id, :status, :output_file,
                            :summary_stats, :festive_inputs, :adhoc_inputs, :validation_status,
                            :session_id)
                """),
                {
                    "run_id": run_data["run_id"],
                    "run_name": run_data["run_name"],
                    "user_id": run_data["user_id"],
                    "baseline_run_id": run_data.get("baseline_run_id", ""),
                    "status": run_data["status"],
                    "output_file": run_data.get("output_file", ""),
                    "summary_stats": json.dumps(run_data.get("summary_stats", {})),
                    "festive_inputs": json.dumps(run_data.get("festive_inputs", {})),
                    "adhoc_inputs": json.dumps(run_data.get("adhoc_inputs", {})),
                    "validation_status": run_data.get("validation_status", "pending"),
                    "session_id": session_id,
                },
            )

    def update_final_plan_run(self, run_id, **fields):
        """Update fields on an existing final plan run."""
        allowed = {
            "status", "output_file", "summary_stats", "festive_inputs",
            "adhoc_inputs", "validation_status", "run_name", "baseline_run_id",
        }
        updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
        if not updates:
            return
        for key in ("summary_stats", "festive_inputs", "adhoc_inputs"):
            if key in updates and not isinstance(updates[key], str):
                updates[key] = json.dumps(updates[key])
        set_clause = ", ".join(f"{col} = :{col}" for col in updates)
        updates["run_id"] = run_id
        with self.engine.begin() as conn:
            conn.execute(
                text(f"UPDATE final_plan_runs SET {set_clause} WHERE run_id = :run_id"),
                updates,
            )

    def get_final_plan_runs(self, limit=50):
        """Get all final plan runs."""
        with self.engine.connect() as conn:
            return pd.read_sql_query(
                text("""
                    SELECT fp.*, u.username, u.full_name
                    FROM final_plan_runs fp
                    LEFT JOIN users u ON fp.user_id = u.id
                    ORDER BY fp.run_date DESC
                    LIMIT :limit
                """),
                conn,
                params={"limit": limit},
            )

    # ── Pipeline flow runs ────────────────────────────────────────────────────

    def create_pipeline_run(self, run_id: str, user_id: int, session_id: str | None = None) -> None:
        resolved = self._resolve_session_id(session_id)
        with self.engine.begin() as conn:
            conn.execute(
                text("""
                    INSERT INTO pipeline_runs (run_id, user_id, status, started_at, session_id)
                    VALUES (:run_id, :user_id, 'running', :started_at, :session_id)
                """),
                {
                    "run_id": run_id,
                    "user_id": user_id,
                    "started_at": datetime.now(),
                    "session_id": resolved,
                },
            )

    def update_pipeline_run(self, run_id: str, **fields) -> None:
        allowed = {"status", "current_step", "summary_stats", "completed_at"}
        updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
        if not updates:
            return
        if "summary_stats" in updates and not isinstance(updates["summary_stats"], str):
            updates["summary_stats"] = json.dumps(updates["summary_stats"])
        set_clause = ", ".join(f"{col} = :{col}" for col in updates)
        updates["run_id"] = run_id
        with self.engine.begin() as conn:
            conn.execute(
                text(f"UPDATE pipeline_runs SET {set_clause} WHERE run_id = :run_id"),
                updates,
            )

    def complete_pipeline_run(self, run_id: str, *, status: str, summary_stats: dict) -> None:
        self.update_pipeline_run(
            run_id,
            status=status,
            summary_stats=summary_stats,
            completed_at=datetime.now(),
        )

    def log_pipeline_step(
        self,
        *,
        run_id: str,
        step_key: str,
        step_name: str,
        step_order: int,
        status: str,
        message: str = "",
        error_detail: str = "",
        session_id: str | None = None,
    ) -> None:
        resolved = self._resolve_session_id(session_id)
        step_session_id = resolved if status == "manual" else None
        with self.engine.begin() as conn:
            conn.execute(
                text("""
                    INSERT INTO pipeline_step_logs
                        (run_id, step_key, step_name, step_order, status, message,
                         error_detail, logged_at, session_id)
                    VALUES
                        (:run_id, :step_key, :step_name, :step_order, :status, :message,
                         :error_detail, :logged_at, :session_id)
                """),
                {
                    "run_id": run_id,
                    "step_key": step_key,
                    "step_name": step_name,
                    "step_order": step_order,
                    "status": status,
                    "message": message,
                    "error_detail": error_detail,
                    "logged_at": datetime.now(),
                    "session_id": step_session_id,
                },
            )

    def get_latest_pipeline_run(self) -> dict | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                text("""
                    SELECT pr.run_id, pr.user_id, pr.status, pr.current_step,
                           pr.started_at, pr.completed_at, pr.summary_stats,
                           pr.session_id, u.username, u.full_name
                    FROM pipeline_runs pr
                    LEFT JOIN users u ON u.id = pr.user_id
                    ORDER BY pr.started_at DESC
                    LIMIT 1
                """)
            ).fetchone()
        if not row:
            return None
        summary = row[6]
        if summary and isinstance(summary, str):
            try:
                summary = json.loads(summary)
            except Exception:
                pass
        return {
            "run_id": row[0],
            "user_id": row[1],
            "status": row[2],
            "current_step": row[3],
            "started_at": row[4],
            "completed_at": row[5],
            "summary_stats": summary,
            "session_id": row[7],
            "username": row[8],
            "full_name": row[9],
        }

    def get_pipeline_steps(self, run_id: str) -> list[dict]:
        with self.engine.connect() as conn:
            rows = conn.execute(
                text("""
                    SELECT step_key, step_name, step_order, status, message, error_detail,
                           logged_at, session_id
                    FROM pipeline_step_logs
                    WHERE run_id = :run_id
                    ORDER BY step_order ASC, logged_at ASC
                """),
                {"run_id": run_id},
            ).fetchall()
        return [
            {
                "step_key": r[0],
                "step_name": r[1],
                "step_order": r[2],
                "status": r[3],
                "message": r[4],
                "error_detail": r[5],
                "logged_at": r[6],
                "session_id": r[7],
            }
            for r in rows
        ]

    def get_pipeline_runs(self, limit: int = 20) -> pd.DataFrame:
        limit = max(1, int(limit))
        with self.engine.connect() as conn:
            return pd.read_sql_query(
                text("""
                    SELECT pr.run_id, pr.status, pr.current_step, pr.started_at,
                           pr.completed_at, pr.summary_stats, pr.session_id, u.username
                    FROM pipeline_runs pr
                    LEFT JOIN users u ON u.id = pr.user_id
                    ORDER BY pr.started_at DESC
                    LIMIT :limit
                """),
                conn,
                params={"limit": limit},
            )

    # ── Auto-Pilot runs (pipeline_runs + pipeline_step_logs + pipeline_run_log_lines) ──

    @staticmethod
    def _autopilot_run_filter_sql() -> str:
        return "pr.run_id LIKE 'AUTOPILOT%'"

    def ensure_autopilot_run(
        self,
        run_id: str,
        user_id: int,
        *,
        run_name: str,
        source: str = "ui",
    ) -> None:
        """Create pipeline_runs row on first start if missing."""
        with self.engine.connect() as conn:
            exists = conn.execute(
                text("SELECT 1 FROM pipeline_runs WHERE run_id = :run_id"),
                {"run_id": run_id},
            ).fetchone()
        if exists:
            return
        self.create_pipeline_run(run_id, user_id)
        self.update_pipeline_run(
            run_id,
            status="running",
            current_step="0",
            summary_stats={
                "run_type": "autopilot",
                "run_name": run_name,
                "source": source,
                "success": False,
                "completed_steps": [],
                "failed_step": None,
                "error": "",
                "logs": {},
            },
        )

    def save_autopilot_snapshot(
        self,
        *,
        run_id: str,
        user_id: int,
        run_name: str,
        source: str,
        success: bool,
        completed_steps: list[int],
        failed_step: int | None = None,
        error: str = "",
        logs: dict | None = None,
    ) -> None:
        """Persist autopilot progress to pipeline_runs.summary_stats."""
        self.ensure_autopilot_run(run_id, user_id, run_name=run_name, source=source)
        logs = logs or {}
        status = "completed" if success else (
            "failed" if failed_step is not None else "running"
        )
        summary = {
            "run_type": "autopilot",
            "run_name": run_name,
            "source": source,
            "success": success,
            "completed_steps": completed_steps,
            "failed_step": failed_step,
            "error": error,
            "logs": {str(k): v for k, v in logs.items()},
        }
        fields: dict = {
            "status": status,
            "current_step": str(failed_step if failed_step is not None else len(completed_steps)),
            "summary_stats": summary,
        }
        if success or failed_step is not None:
            fields["completed_at"] = datetime.now()
        self.update_pipeline_run(run_id, **fields)

    def append_pipeline_run_log(
        self,
        run_id: str,
        message: str,
        *,
        level: str = "INFO",
    ) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                text("""
                    INSERT INTO pipeline_run_log_lines (run_id, level, message, logged_at)
                    VALUES (:run_id, :level, :message, :logged_at)
                """),
                {
                    "run_id": run_id,
                    "level": level,
                    "message": message,
                    "logged_at": datetime.now(),
                },
            )

    def get_pipeline_run_log_text(self, run_id: str, *, max_lines: int = 400) -> str:
        limit = max(1, int(max_lines))
        with self.engine.connect() as conn:
            rows = conn.execute(
                text("""
                    SELECT level, message, logged_at
                    FROM pipeline_run_log_lines
                    WHERE run_id = :run_id
                    ORDER BY logged_at ASC, id ASC
                """),
                {"run_id": run_id},
            ).fetchall()
        if not rows:
            return ""
        tail = rows[-limit:]
        lines = []
        for level, message, logged_at in tail:
            ts = logged_at.strftime("%Y-%m-%d %H:%M:%S") if logged_at else ""
            lines.append(f"{ts} [{level}] {message}")
        return "\n".join(lines)

    def _row_to_autopilot_state(self, row) -> dict:
        summary = row[6]
        if summary and isinstance(summary, str):
            try:
                summary = json.loads(summary)
            except Exception:
                summary = {}
        if not isinstance(summary, dict):
            summary = {}
        updated = row[5] or row[4]
        if hasattr(updated, "isoformat"):
            updated_at = updated.isoformat(timespec="seconds")
        else:
            updated_at = str(updated) if updated else ""
        return {
            "updated_at": updated_at,
            "source": summary.get("source", "ui"),
            "run_id": row[0],
            "run_name": summary.get("run_name", "Auto-Pilot"),
            "success": bool(summary.get("success")),
            "completed_steps": summary.get("completed_steps") or [],
            "failed_step": summary.get("failed_step"),
            "error": summary.get("error", ""),
            "logs": summary.get("logs") or {},
            "status": row[2],
            "started_at": row[4],
            "completed_at": row[5],
            "username": row[8],
        }

    def get_latest_autopilot_run(self) -> dict | None:
        filt = self._autopilot_run_filter_sql()
        with self.engine.connect() as conn:
            row = conn.execute(
                text(f"""
                    SELECT pr.run_id, pr.user_id, pr.status, pr.current_step,
                           pr.started_at, pr.completed_at, pr.summary_stats,
                           pr.session_id, u.username
                    FROM pipeline_runs pr
                    LEFT JOIN users u ON u.id = pr.user_id
                    WHERE {filt}
                    ORDER BY pr.started_at DESC
                    LIMIT 1
                """)
            ).fetchone()
        if not row:
            return None
        return self._row_to_autopilot_state(row)

    def get_autopilot_run(self, run_id: str) -> dict | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                text("""
                    SELECT pr.run_id, pr.user_id, pr.status, pr.current_step,
                           pr.started_at, pr.completed_at, pr.summary_stats,
                           pr.session_id, u.username
                    FROM pipeline_runs pr
                    LEFT JOIN users u ON u.id = pr.user_id
                    WHERE pr.run_id = :run_id
                """),
                {"run_id": run_id},
            ).fetchone()
        if not row:
            return None
        state = self._row_to_autopilot_state(row)
        state["step_logs"] = self.get_pipeline_steps(run_id)
        state["log_text"] = self.get_pipeline_run_log_text(run_id)
        return state

    def get_autopilot_run_history(self, limit: int = 25) -> pd.DataFrame:
        limit = max(1, int(limit))
        filt = self._autopilot_run_filter_sql()
        with self.engine.connect() as conn:
            df = pd.read_sql_query(
                text(f"""
                    SELECT pr.run_id, pr.status, pr.started_at, pr.completed_at,
                           pr.summary_stats, u.username
                    FROM pipeline_runs pr
                    LEFT JOIN users u ON u.id = pr.user_id
                    WHERE {filt}
                    ORDER BY pr.started_at DESC
                    LIMIT :limit
                """),
                conn,
                params={"limit": limit},
            )
        if df.empty:
            return df
        run_names = []
        sources = []
        steps_done = []
        for raw in df["summary_stats"].fillna(""):
            try:
                s = json.loads(raw) if isinstance(raw, str) and raw else {}
            except Exception:
                s = {}
            run_names.append(s.get("run_name", "Auto-Pilot"))
            sources.append(s.get("source", "—"))
            steps_done.append(len(s.get("completed_steps") or []))
        df = df.drop(columns=["summary_stats"])
        df.insert(1, "run_name", run_names)
        df.insert(2, "source", sources)
        df["steps_done"] = steps_done
        return df

    def log_master_sync(self, sync_data):
        """Log master data sync."""
        session_id = self._resolve_session_id(sync_data.get("session_id"))
        
        from sqlalchemy.orm import Session
        from planning_suite.db.models import MasterSyncLog

        with Session(self.engine) as session:
            log_entry = MasterSyncLog(
                master_type=sync_data["master_type"],
                user_id=sync_data["user_id"],
                records_synced=sync_data.get("records_synced", 0),
                status=sync_data["status"],
                error_message=sync_data.get("error_message", ""),
                session_id=session_id
            )
            session.add(log_entry)
            session.commit()

    def get_master_sync_history(self, master_type=None, limit=50):
        """Get master sync history."""
        from sqlalchemy.orm import Session
        from planning_suite.db.models import MasterSyncLog, User

        with Session(self.engine) as session:
            query = (
                session.query(
                    MasterSyncLog.id,
                    MasterSyncLog.sync_date,
                    MasterSyncLog.master_type,
                    MasterSyncLog.user_id,
                    MasterSyncLog.records_synced,
                    MasterSyncLog.status,
                    MasterSyncLog.error_message,
                    MasterSyncLog.session_id,
                    User.username
                )
                .outerjoin(User, MasterSyncLog.user_id == User.id)
            )
            if master_type:
                query = query.filter(MasterSyncLog.master_type == master_type)
            query = query.order_by(MasterSyncLog.sync_date.desc()).limit(limit)
            
            rows = query.all()
            data = []
            for r in rows:
                data.append({
                    "id": r[0],
                    "sync_date": r[1],
                    "master_type": r[2],
                    "user_id": r[3],
                    "records_synced": r[4],
                    "status": r[5],
                    "error_message": r[6],
                    "session_id": r[7],
                    "username": r[8]
                })
            return pd.DataFrame(data)

    # ── Email notifications ─────────────────────────────────────────────────────

    def get_email_recipients(
        self,
        *,
        category: str | None = None,
        enabled_only: bool = False,
    ) -> list[dict]:
        query = """
            SELECT id, email, display_name, category, enabled, created_by, created_at, updated_at
            FROM email_notification_recipients
        """
        params: dict = {}
        clauses: list[str] = []
        if category:
            clauses.append("category = :category")
            params["category"] = category
        if enabled_only:
            clauses.append("enabled = :enabled")
            params["enabled"] = True if self.backend == "postgresql" else 1
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY category ASC, email ASC"

        with self.engine.connect() as conn:
            rows = conn.execute(text(query), params).fetchall()
        return [
            {
                "id": r[0],
                "email": r[1],
                "display_name": r[2] or "",
                "category": r[3],
                "enabled": bool(r[4]),
                "created_by": r[5],
                "created_at": r[6],
                "updated_at": r[7],
            }
            for r in rows
        ]

    def create_email_recipient(
        self,
        *,
        email: str,
        display_name: str,
        category: str,
        created_by: int,
        enabled: bool = True,
    ) -> int | None:
        now = datetime.now()
        with self.engine.begin() as conn:
            if self.backend == "postgresql":
                row = conn.execute(
                    text("""
                        INSERT INTO email_notification_recipients
                            (email, display_name, category, enabled, created_by, created_at, updated_at)
                        VALUES
                            (:email, :display_name, :category, :enabled, :created_by, :created_at, :updated_at)
                        RETURNING id
                    """),
                    {
                        "email": email.strip().lower(),
                        "display_name": display_name.strip(),
                        "category": category,
                        "enabled": enabled,
                        "created_by": created_by,
                        "created_at": now,
                        "updated_at": now,
                    },
                ).fetchone()
                return int(row[0]) if row else None

            conn.execute(
                text("""
                    INSERT INTO email_notification_recipients
                        (email, display_name, category, enabled, created_by, created_at, updated_at)
                    VALUES
                        (:email, :display_name, :category, :enabled, :created_by, :created_at, :updated_at)
                """),
                {
                    "email": email.strip().lower(),
                    "display_name": display_name.strip(),
                    "category": category,
                    "enabled": 1 if enabled else 0,
                    "created_by": created_by,
                    "created_at": now,
                    "updated_at": now,
                },
            )
            return conn.execute(text("SELECT last_insert_rowid()")).scalar()

    def update_email_recipient(self, recipient_id: int, **fields) -> None:
        allowed = {"email", "display_name", "category", "enabled"}
        updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
        if not updates:
            return
        if "email" in updates:
            updates["email"] = str(updates["email"]).strip().lower()
        if "display_name" in updates:
            updates["display_name"] = str(updates["display_name"]).strip()
        if "enabled" in updates and self.backend != "postgresql":
            updates["enabled"] = 1 if updates["enabled"] else 0
        updates["updated_at"] = datetime.now()
        updates["id"] = recipient_id
        set_clause = ", ".join(f"{col} = :{col}" for col in updates if col != "id")
        with self.engine.begin() as conn:
            conn.execute(
                text(f"UPDATE email_notification_recipients SET {set_clause} WHERE id = :id"),
                updates,
            )

    def delete_email_recipient(self, recipient_id: int) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                text("DELETE FROM email_notification_recipients WHERE id = :id"),
                {"id": recipient_id},
            )

    def log_email(self, data: dict) -> int | None:
        recipients = data.get("recipients") or []
        if not isinstance(recipients, str):
            recipients_json = json.dumps(recipients)
        else:
            recipients_json = recipients
        metadata = data.get("metadata") or {}
        if not isinstance(metadata, str):
            metadata_json = json.dumps(metadata)
        else:
            metadata_json = metadata

        params = {
            "email_type": data.get("email_type", "general"),
            "subject": data.get("subject", ""),
            "recipients": recipients_json,
            "status": data.get("status", "skipped"),
            "error_message": data.get("error_message", ""),
            "body_preview": data.get("body_preview", ""),
            "triggered_by_user_id": data.get("triggered_by_user_id"),
            "session_id": data.get("session_id"),
            "metadata": metadata_json,
            "sent_at": datetime.now(),
        }

        with self.engine.begin() as conn:
            if self.backend == "postgresql":
                row = conn.execute(
                    text("""
                        INSERT INTO email_log
                            (sent_at, email_type, subject, recipients, status, error_message,
                             body_preview, triggered_by_user_id, session_id, metadata)
                        VALUES
                            (:sent_at, :email_type, :subject, :recipients, :status, :error_message,
                             :body_preview, :triggered_by_user_id, :session_id, :metadata)
                        RETURNING id
                    """),
                    params,
                ).fetchone()
                return int(row[0]) if row else None

            conn.execute(
                text("""
                    INSERT INTO email_log
                        (sent_at, email_type, subject, recipients, status, error_message,
                         body_preview, triggered_by_user_id, session_id, metadata)
                    VALUES
                        (:sent_at, :email_type, :subject, :recipients, :status, :error_message,
                         :body_preview, :triggered_by_user_id, :session_id, :metadata)
                """),
                params,
            )
            return conn.execute(text("SELECT last_insert_rowid()")).scalar()

    def get_email_log(self, limit: int = 50) -> pd.DataFrame:
        limit = max(1, int(limit))
        order_clause = _order_by_desc_nulls_last("el.sent_at", self.backend)
        with self.engine.connect() as conn:
            return pd.read_sql_query(
                text(f"""
                    SELECT
                        el.id,
                        el.sent_at,
                        el.email_type,
                        el.subject,
                        el.recipients,
                        el.status,
                        el.error_message,
                        el.triggered_by_user_id,
                        el.session_id,
                        u.username AS triggered_by
                    FROM email_log el
                    LEFT JOIN users u ON u.id = el.triggered_by_user_id
                    ORDER BY {order_clause}
                    LIMIT :limit
                """),
                conn,
                params={"limit": limit},
            )

    def ping(self) -> bool:
        """Return True if the database accepts a simple query."""
        with self.engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True

    def check_connection(self) -> dict:
        """Return connection status for UI diagnostics."""
        info = {
            "backend": self.backend,
            "ok": False,
            "message": "",
            "connection_label": self.connection_label(),
            "project_ref": get_supabase_project_ref(self.database_url),
        }
        if self.backend != "postgresql":
            info["message"] = (
                "DATABASE_URL is not set in .env — app fell back to local SQLite. "
                "Set DATABASE_URL to your Supabase connection string and restart Streamlit."
            )
            return info
        try:
            self.ping()
            info["ok"] = True
            info["message"] = "Connected to Supabase (PostgreSQL)."
        except Exception as exc:
            info["message"] = f"Supabase connection failed: {exc}"
        return info

_SQLITE_SCHEMA = [
    """
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        full_name TEXT,
        email TEXT,
        role TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        last_login TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS baseline_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id TEXT UNIQUE NOT NULL,
        run_name TEXT,
        run_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        user_id INTEGER,
        status TEXT,
        raw_data_file TEXT,
        output_file TEXT,
        summary_stats TEXT,
        parameters TEXT,
        validation_status TEXT,
        approved_by INTEGER,
        approved_at TIMESTAMP,
        session_id TEXT,
        approval_session_id TEXT,
        FOREIGN KEY (user_id) REFERENCES users (id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS final_plan_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id TEXT UNIQUE NOT NULL,
        run_name TEXT,
        run_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        user_id INTEGER,
        baseline_run_id TEXT,
        status TEXT,
        output_file TEXT,
        summary_stats TEXT,
        festive_inputs TEXT,
        adhoc_inputs TEXT,
        validation_status TEXT,
        approved_by INTEGER,
        approved_at TIMESTAMP,
        session_id TEXT,
        FOREIGN KEY (user_id) REFERENCES users (id),
        FOREIGN KEY (baseline_run_id) REFERENCES baseline_runs (run_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS master_sync_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sync_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        master_type TEXT,
        user_id INTEGER,
        records_synced INTEGER,
        status TEXT,
        error_message TEXT,
        session_id TEXT,
        FOREIGN KEY (user_id) REFERENCES users (id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS auth_sessions (
        session_id TEXT PRIMARY KEY,
        user_id INTEGER NOT NULL,
        expires_at TIMESTAMP NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        system_details TEXT,
        FOREIGN KEY (user_id) REFERENCES users (id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS user_preferences (
        user_id INTEGER PRIMARY KEY,
        email_notifications INTEGER DEFAULT 1,
        auto_sync_masters INTEGER DEFAULT 0,
        preview_rows INTEGER DEFAULT 100,
        updated_at TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS pipeline_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id TEXT UNIQUE NOT NULL,
        user_id INTEGER,
        status TEXT,
        current_step TEXT,
        started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        completed_at TIMESTAMP,
        summary_stats TEXT,
        session_id TEXT,
        FOREIGN KEY (user_id) REFERENCES users (id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS pipeline_step_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id TEXT NOT NULL,
        step_key TEXT NOT NULL,
        step_name TEXT,
        step_order INTEGER,
        status TEXT,
        message TEXT,
        error_detail TEXT,
        logged_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        session_id TEXT,
        FOREIGN KEY (run_id) REFERENCES pipeline_runs (run_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS pipeline_run_log_lines (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id TEXT NOT NULL,
        level TEXT,
        message TEXT NOT NULL,
        logged_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (run_id) REFERENCES pipeline_runs (run_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS email_notification_recipients (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT NOT NULL,
        display_name TEXT,
        category TEXT NOT NULL,
        enabled INTEGER DEFAULT 1,
        created_by INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP,
        FOREIGN KEY (created_by) REFERENCES users (id),
        UNIQUE (email, category)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS email_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        email_type TEXT,
        subject TEXT,
        recipients TEXT,
        status TEXT,
        error_message TEXT,
        body_preview TEXT,
        triggered_by_user_id INTEGER,
        session_id TEXT,
        metadata TEXT,
        FOREIGN KEY (triggered_by_user_id) REFERENCES users (id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS sync_run (
        id TEXT PRIMARY KEY,
        started_at TIMESTAMP NOT NULL,
        finished_at TIMESTAMP,
        triggered_by TEXT,
        step_name TEXT,
        status TEXT DEFAULT 'running',
        error_msg TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS sync_snapshot (
        id TEXT PRIMARY KEY,
        sync_run_id TEXT NOT NULL,
        sheet_name TEXT NOT NULL,
        snapshot_parquet BLOB NOT NULL,
        row_count INTEGER,
        created_at TIMESTAMP NOT NULL,
        user_id TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS audit_log (
        id TEXT PRIMARY KEY,
        sync_run_id TEXT,
        action TEXT,
        user_id TEXT,
        sheet_name TEXT,
        rows_affected INTEGER,
        status TEXT,
        ts TIMESTAMP NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS write_queue (
        id TEXT PRIMARY KEY,
        sheet_name TEXT,
        payload TEXT,
        status TEXT DEFAULT 'pending',
        created_at TIMESTAMP,
        flushed_at TIMESTAMP
    )
    """,
]

_POSTGRES_SCHEMA = [
    """
    CREATE TABLE IF NOT EXISTS users (
        id BIGSERIAL PRIMARY KEY,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        full_name TEXT,
        email TEXT,
        role TEXT NOT NULL,
        created_at TIMESTAMPTZ DEFAULT NOW(),
        last_login TIMESTAMPTZ
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS baseline_runs (
        id BIGSERIAL PRIMARY KEY,
        run_id TEXT UNIQUE NOT NULL,
        run_name TEXT,
        run_date TIMESTAMPTZ DEFAULT NOW(),
        user_id BIGINT,
        status TEXT,
        raw_data_file TEXT,
        output_file TEXT,
        summary_stats TEXT,
        parameters TEXT,
        validation_status TEXT,
        approved_by BIGINT,
        approved_at TIMESTAMPTZ,
        session_id TEXT,
        approval_session_id TEXT,
        FOREIGN KEY (user_id) REFERENCES users (id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS final_plan_runs (
        id BIGSERIAL PRIMARY KEY,
        run_id TEXT UNIQUE NOT NULL,
        run_name TEXT,
        run_date TIMESTAMPTZ DEFAULT NOW(),
        user_id BIGINT,
        baseline_run_id TEXT,
        status TEXT,
        output_file TEXT,
        summary_stats TEXT,
        festive_inputs TEXT,
        adhoc_inputs TEXT,
        validation_status TEXT,
        approved_by BIGINT,
        approved_at TIMESTAMPTZ,
        session_id TEXT,
        FOREIGN KEY (user_id) REFERENCES users (id),
        FOREIGN KEY (baseline_run_id) REFERENCES baseline_runs (run_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS master_sync_log (
        id BIGSERIAL PRIMARY KEY,
        sync_date TIMESTAMPTZ DEFAULT NOW(),
        master_type TEXT,
        user_id BIGINT,
        records_synced INTEGER,
        status TEXT,
        error_message TEXT,
        session_id TEXT,
        FOREIGN KEY (user_id) REFERENCES users (id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS auth_sessions (
        session_id TEXT PRIMARY KEY,
        user_id BIGINT NOT NULL,
        expires_at TIMESTAMPTZ NOT NULL,
        created_at TIMESTAMPTZ DEFAULT NOW(),
        system_details TEXT,
        FOREIGN KEY (user_id) REFERENCES users (id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS user_preferences (
        user_id BIGINT PRIMARY KEY,
        email_notifications BOOLEAN DEFAULT TRUE,
        auto_sync_masters BOOLEAN DEFAULT FALSE,
        preview_rows INTEGER DEFAULT 100,
        updated_at TIMESTAMPTZ,
        FOREIGN KEY (user_id) REFERENCES users (id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS pipeline_runs (
        id BIGSERIAL PRIMARY KEY,
        run_id TEXT UNIQUE NOT NULL,
        user_id BIGINT,
        status TEXT,
        current_step TEXT,
        started_at TIMESTAMPTZ DEFAULT NOW(),
        completed_at TIMESTAMPTZ,
        summary_stats TEXT,
        session_id TEXT,
        FOREIGN KEY (user_id) REFERENCES users (id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS pipeline_step_logs (
        id BIGSERIAL PRIMARY KEY,
        run_id TEXT NOT NULL,
        step_key TEXT NOT NULL,
        step_name TEXT,
        step_order INTEGER,
        status TEXT,
        message TEXT,
        error_detail TEXT,
        logged_at TIMESTAMPTZ DEFAULT NOW(),
        session_id TEXT,
        FOREIGN KEY (run_id) REFERENCES pipeline_runs (run_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS pipeline_run_log_lines (
        id BIGSERIAL PRIMARY KEY,
        run_id TEXT NOT NULL,
        level TEXT,
        message TEXT NOT NULL,
        logged_at TIMESTAMPTZ DEFAULT NOW(),
        FOREIGN KEY (run_id) REFERENCES pipeline_runs (run_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS email_notification_recipients (
        id BIGSERIAL PRIMARY KEY,
        email TEXT NOT NULL,
        display_name TEXT,
        category TEXT NOT NULL,
        enabled BOOLEAN DEFAULT TRUE,
        created_by BIGINT,
        created_at TIMESTAMPTZ DEFAULT NOW(),
        updated_at TIMESTAMPTZ,
        FOREIGN KEY (created_by) REFERENCES users (id),
        UNIQUE (email, category)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS email_log (
        id BIGSERIAL PRIMARY KEY,
        sent_at TIMESTAMPTZ DEFAULT NOW(),
        email_type TEXT,
        subject TEXT,
        recipients TEXT,
        status TEXT,
        error_message TEXT,
        body_preview TEXT,
        triggered_by_user_id BIGINT,
        session_id TEXT,
        metadata TEXT,
        FOREIGN KEY (triggered_by_user_id) REFERENCES users (id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS sync_run (
        id TEXT PRIMARY KEY,
        started_at TIMESTAMPTZ NOT NULL,
        finished_at TIMESTAMPTZ,
        triggered_by TEXT,
        step_name TEXT,
        status TEXT DEFAULT 'running',
        error_msg TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS sync_snapshot (
        id TEXT PRIMARY KEY,
        sync_run_id TEXT NOT NULL,
        sheet_name TEXT NOT NULL,
        snapshot_parquet BYTEA NOT NULL,
        row_count INTEGER,
        created_at TIMESTAMPTZ NOT NULL,
        user_id TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS audit_log (
        id TEXT PRIMARY KEY,
        sync_run_id TEXT,
        action TEXT,
        user_id TEXT,
        sheet_name TEXT,
        rows_affected INTEGER,
        status TEXT,
        ts TIMESTAMPTZ NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS write_queue (
        id TEXT PRIMARY KEY,
        sheet_name TEXT,
        payload TEXT,
        status TEXT DEFAULT 'pending',
        created_at TIMESTAMPTZ,
        flushed_at TIMESTAMPTZ
    )
    """,
]
