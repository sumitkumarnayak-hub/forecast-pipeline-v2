"""Final Plan engine — headless wrapper around ff_hub_automation_cluster_change.py."""
from __future__ import annotations

import os
import subprocess
import sys
import uuid
from datetime import datetime
from pathlib import Path

from app.config import PROJECT_ROOT
from core.database.engine import Database

from features.validation.output_validation import find_latest_file, validate_final_plan_output



def _generate_run_id() -> str:
    return f"FP-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}"


def run_final_plan_engine(*, user_id: int, db: Database | None = None) -> dict:
    """Run the final plan distribution script and record output in DB."""
    from core.shared.pipeline_state import is_baseline_approved


    if not is_baseline_approved():
        raise ValueError("Baseline must be approved before running Final Plan.")

    from features.final_plan.inputs import get_inputs_status


    inputs = get_inputs_status()
    if not inputs.get("ready"):
        missing = [
            c["label"]
            for c in inputs.get("checks", [])
            if c.get("required") and not c.get("exists")
        ]
        if not inputs.get("inv_logic_ok"):
            missing.append("Inv logic Excel files (sync inventory logic)")
        raise ValueError(f"Final Plan inputs not ready: {', '.join(missing)}")

    db = db or Database()

    run_id = _generate_run_id()
    run_name = f"Final Plan {datetime.now().strftime('%Y-%m-%d %H:%M')}"

    db.save_final_plan_run(
        {
            "run_id": run_id,
            "run_name": run_name,
            "user_id": user_id,
            "status": "running",
            "baseline_run_id": "",
            "output_file": "",
            "validation_status": "pending",
        }
    )

    script = PROJECT_ROOT / "backend" / "scripts" / "ff_hub_automation_cluster_change.py"
    if not script.is_file():
        script = PROJECT_ROOT / "scripts" / "ff_hub_automation_cluster_change.py"

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PROJECT_ROOT"] = str(PROJECT_ROOT)

    try:
        result = subprocess.run(
            [sys.executable, str(script)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=7200,
            cwd=str(PROJECT_ROOT),
            env=env,
        )
        stdout = result.stdout or ""
        stderr = result.stderr or ""

        if result.returncode != 0:
            db.update_final_plan_run(run_id, status="failed", summary_stats={"stderr": stderr[-2000:]})
            raise RuntimeError(stderr[-1500:] or stdout[-1500:] or f"Script exited {result.returncode}")

        latest = find_latest_file(PROJECT_ROOT, "Hub_Dist_Wk*.xlsx")
        output_path = str(latest) if latest else ""
        validation = validate_final_plan_output(latest) if latest else {"valid": False, "errors": ["No output file"]}

        db.update_final_plan_run(
            run_id,
            status="completed",
            output_file=output_path,
            validation_status="passed" if validation.get("valid") else "failed",
            summary_stats=validation.get("stats", {}),
        )
        preview_rows: list[dict] = []
        if latest and latest.is_file():
            import pandas as pd

            preview_rows = pd.read_excel(latest, nrows=50).fillna("").to_dict(orient="records")

        return {
            "run_id": run_id,
            "run_name": run_name,
            "output_file": output_path,
            "validation": validation,
            "preview_rows": preview_rows,
            "stdout_tail": stdout[-2000:],
        }
    except subprocess.TimeoutExpired:
        db.update_final_plan_run(run_id, status="failed")
        raise RuntimeError("Final plan script timed out after 2 hours") from None
    except Exception:
        if db:
            try:
                db.update_final_plan_run(run_id, status="failed")
            except Exception:
                pass
        raise


def get_latest_output_preview(*, limit: int = 100) -> dict:
    latest = find_latest_file(PROJECT_ROOT, "Hub_Dist_Wk*.xlsx")
    if not latest:
        return {"available": False, "message": "No Hub_Dist_Wk*.xlsx found in project root."}
    import pandas as pd

    df = pd.read_excel(latest)
    validation = validate_final_plan_output(latest)
    return {
        "available": True,
        "file": latest.name,
        "path": str(latest),
        "rows": len(df),
        "columns": df.columns.tolist(),
        "preview_rows": df.head(limit).fillna("").to_dict(orient="records"),
        "validation": validation,
    }


def load_hub_suggestions_preview(*, limit: int = 200) -> dict:
    from core.utils.dataframe import df_to_records


    cache = PROJECT_ROOT / "outputs" / "hub_suggestion_latest.parquet"
    if cache.is_file():
        import pandas as pd

        df = pd.read_parquet(cache)
        return {
            "source": "cache",
            "rows": df_to_records(df.head(limit)),
            "columns": df.columns.tolist(),
            "row_count": len(df),
        }
    return {"source": "none", "rows": [], "columns": [], "row_count": 0, "message": "Run baseline first."}
