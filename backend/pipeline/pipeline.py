import os
import sys
import subprocess
import logging
import datetime
import uuid

# Make sure backend/ is in sys.path
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] [PIPELINE] %(message)s',
    handlers=[sys.stdout]
)

def run_pipeline(triggered_by: str = "Manual CLI", run_id: str | None = None) -> dict:
    """Run 3-step pipeline with DB logging."""
    if not run_id:
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        run_id = f"PIPE_{timestamp}_{uuid.uuid4().hex[:6]}"

    working_dir = backend_dir

    # Try saving initial DB log
    db = None
    try:
        from core.database.engine import Database
        db = Database()
        db.save_pipeline_execution_log(run_id=run_id, triggered_by=triggered_by, status="running")
    except Exception as exc:
        logging.warning("Could not initialize DB log for pipeline run: %s", exc)

    log_lines = []

    def log(msg: str):
        logging.info(msg)
        log_lines.append(f"{datetime.datetime.now().isoformat()} {msg}")

    steps = [
        ("step1_status", "pipeline/raw_data_6w.py", "Step 1: Raw Data Extraction"),
        ("step2_status", "pipeline/baseline_parquet.py", "Step 2: Baseline Parquet Creation"),
        ("step3_status", "pipeline/ff_hub_automation.py", "Step 3: FF Hub Automation"),
    ]

    log(f"Starting forecasting pipeline run ({run_id}) triggered by: {triggered_by}")
    overall_status = "completed"

    for step_key, script_relpath, step_title in steps:
        script_path = os.path.join(working_dir, script_relpath)
        log("=" * 60)
        log(f"STARTING {step_title} ({script_relpath})")
        log("=" * 60)

        if not os.path.exists(script_path):
            log(f"ERROR: Script file not found at {script_path}")
            if db:
                db.update_pipeline_execution_log(run_id, **{step_key: "failed", "status": "failed"})
            overall_status = "failed"
            break

        if db:
            db.update_pipeline_execution_log(run_id, **{step_key: "running"})

        try:
            res = subprocess.run(
                [sys.executable, script_path],
                cwd=working_dir,
                capture_output=True,
                text=True,
                check=True,
            )
            if res.stdout:
                log_lines.append(res.stdout)
            log(f"SUCCESS: Completed {step_title}")
            if db:
                db.update_pipeline_execution_log(run_id, **{step_key: "completed"})
        except subprocess.CalledProcessError as exc:
            if exc.stdout:
                log_lines.append(exc.stdout)
            if exc.stderr:
                log_lines.append(f"STDERR: {exc.stderr}")
            log(f"FAILURE in {step_title} (Exit code {exc.returncode})")
            if db:
                db.update_pipeline_execution_log(run_id, **{step_key: "failed"})
            overall_status = "failed"
            break

    completed_time = datetime.datetime.now()
    log("=" * 60)
    log(f"Pipeline run {run_id} finished with status: {overall_status.upper()}")
    log("=" * 60)

    if db:
        try:
            db.update_pipeline_execution_log(
                run_id,
                status=overall_status,
                completed_at=completed_time,
                console_log="\n".join(log_lines),
            )
        except Exception as exc:
            logging.warning("Failed updating final DB log entry: %s", exc)

    return {
        "run_id": run_id,
        "status": overall_status,
        "triggered_by": triggered_by,
        "completed_at": completed_time.isoformat(),
        "log": "\n".join(log_lines[-200:]),
    }

def main():
    triggered_by = os.getenv("PIPELINE_TRIGGERED_BY", "GitHub Actions / Airflow / CLI")
    res = run_pipeline(triggered_by=triggered_by)
    if res["status"] != "completed":
        sys.exit(1)

if __name__ == "__main__":
    main()

