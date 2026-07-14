"""Validation router — input, master, output validation and history."""

from __future__ import annotations



import io



from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query

from pathlib import Path



from app.dependencies import get_current_user, require_write

from app.config import BASELINE_OUTPUTS_FOLDER, PROJECT_ROOT



router = APIRouter()





def _record_run(

    *,

    current_user: dict,

    run_id: str,

    validation_type: str,

    passed: bool,

    errors_found: list[str] | None = None,

    filename: str | None = None,

    stats: dict | None = None,

) -> None:

    from features.validation.history import append_validation_run




    append_validation_run(

        user_id=int(current_user["sub"]),

        username=str(current_user.get("username") or current_user.get("full_name") or "user"),

        run_id=run_id,

        validation_type=validation_type,

        passed=passed,

        errors_found=errors_found,

        filename=filename,

        stats=stats,

    )





@router.get("/bootstrap")

def validation_bootstrap(current_user: dict = Depends(get_current_user)):

    """Single payload — logics, latest output files, history count."""

    from features.validation.service import get_validation_bootstrap




    return get_validation_bootstrap(user_id=int(current_user["sub"]))





@router.get("/logics")

def validation_logics(current_user: dict = Depends(get_current_user)):

    from features.validation.service import get_validation_logics




    return get_validation_logics()





@router.post("/validate-input")

async def validate_input_upload(

    data_type: str = Query(..., description="raw_data | hub_changes | outlier | percentile"),

    file: UploadFile = File(...),

    current_user: dict = Depends(require_write),

):

    if not file.filename:

        raise HTTPException(status_code=400, detail="No file provided")

    if not file.filename.lower().endswith((".csv", ".xlsx", ".xls")):

        raise HTTPException(status_code=400, detail="Only CSV or Excel files accepted")



    content = await file.read()

    try:

        from features.validation.input import read_uploaded_table, validate_input_dataframe




        df = read_uploaded_table(content, file.filename)

        result = validate_input_dataframe(df, data_type)

        _record_run(

            current_user=current_user,

            run_id="INPUT_VALIDATION",

            validation_type=data_type,

            passed=result["valid"],

            errors_found=result.get("errors", []) + result.get("warnings", []),

            filename=file.filename,

            stats={"rows": result.get("rows"), "columns": result.get("columns")},

        )

        return {"filename": file.filename, **result}

    except Exception as exc:

        raise HTTPException(status_code=422, detail=str(exc)) from exc





@router.post("/validate-master")

def validate_master(

    master_id: str = Query(..., description="product_hub_master | product_master | hub_mapping | hub_changes"),

    current_user: dict = Depends(require_write),

):

    try:

        from features.validation.service import validate_master_by_id




        result = validate_master_by_id(master_id)

        _record_run(

            current_user=current_user,

            run_id=f"MASTER_{master_id.upper()}",

            validation_type=f"master_{master_id}",

            passed=result["valid"],

            errors_found=result.get("errors", []) + result.get("warnings", []),

            stats=result.get("stats"),

        )

        return result

    except ValueError as exc:

        raise HTTPException(status_code=400, detail=str(exc)) from exc

    except Exception as exc:

        raise HTTPException(status_code=500, detail=str(exc)) from exc





@router.post("/validate-baseline-output")

async def validate_baseline_output(

    file: UploadFile = File(...),

    current_user: dict = Depends(require_write),

):

    if not file.filename or not file.filename.endswith((".xlsx", ".xls")):

        raise HTTPException(status_code=400, detail="Only Excel files accepted")



    contents = await file.read()

    try:

        import pandas as pd

        from features.validation.output_validation import validate_baseline_summary_df




        df = pd.read_excel(io.BytesIO(contents))

        result = validate_baseline_summary_df(df)

        _record_run(

            current_user=current_user,

            run_id=file.filename,

            validation_type="baseline_output_upload",

            passed=result["valid"],

            errors_found=result.get("errors", []) + result.get("warnings", []),

            filename=file.filename,

            stats=result.get("stats"),

        )

        return {

            "filename": file.filename,

            "rows": len(df),

            "columns": list(df.columns),

            "validation": result,

        }

    except Exception as exc:

        raise HTTPException(status_code=422, detail=str(exc)) from exc





@router.get("/validate-latest/baseline")

def validate_latest_baseline(current_user: dict = Depends(get_current_user)):

    from features.validation.output_validation import find_latest_file, validate_baseline_output




    latest = find_latest_file(Path(BASELINE_OUTPUTS_FOLDER), "Summary_*.xlsx")

    if not latest:

        raise HTTPException(status_code=404, detail="No Summary_*.xlsx on disk")

    result = validate_baseline_output(latest)

    _record_run(

        current_user=current_user,

        run_id=latest.stem,

        validation_type="baseline_output",

        passed=result["valid"],

        errors_found=result.get("errors", []) + result.get("warnings", []),

        filename=latest.name,

        stats=result.get("stats"),

    )

    return {"file": latest.name, "path": str(latest), "validation": result}





@router.get("/validate-latest/final-plan")

def validate_latest_final_plan(current_user: dict = Depends(get_current_user)):

    from features.validation.output_validation import find_latest_file, validate_final_plan_output




    latest = find_latest_file(Path(PROJECT_ROOT), "Hub_Dist_Wk*.xlsx")

    if not latest:

        raise HTTPException(status_code=404, detail="No Hub_Dist_Wk*.xlsx on disk")

    result = validate_final_plan_output(latest)

    _record_run(

        current_user=current_user,

        run_id=latest.stem,

        validation_type="final_plan_output",

        passed=result["valid"],

        errors_found=result.get("errors", []) + result.get("warnings", []),

        filename=latest.name,

        stats=result.get("stats"),

    )

    return {"file": latest.name, "path": str(latest), "validation": result}





@router.get("/history")

def validation_history(

    limit: int = 50,

    current_user: dict = Depends(get_current_user),

):

    from features.validation.history import get_validation_history




    return {"rows": get_validation_history(user_id=int(current_user["sub"]), limit=limit)}





@router.delete("/history")

def clear_validation_history(current_user: dict = Depends(require_write)):

    from features.validation.history import clear_validation_history




    clear_validation_history(user_id=int(current_user["sub"]))

    return {"detail": "Validation history cleared for this session"}





@router.get("/validation-logs")

def get_validation_logs(

    limit: int = 20,

    current_user: dict = Depends(get_current_user),

):

    """Legacy master sync failures — kept for ops visibility."""

    try:

        from core.database.engine import Database




        db = Database()

        with db.engine.connect() as conn:

            from sqlalchemy import text



            rows = conn.execute(

                text("""

                    SELECT id, sync_date, master_type, status, error_message, records_synced

                    FROM master_sync_log

                    WHERE status IN ('failed', 'warning') OR master_type LIKE '%validation%'

                    ORDER BY sync_date DESC

                    LIMIT :limit

                """),

                {"limit": limit},

            ).fetchall()

        return [dict(r._mapping) for r in rows]

    except Exception:

        return []


