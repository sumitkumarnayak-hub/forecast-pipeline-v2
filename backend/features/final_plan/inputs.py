"""Final Plan input files — status, city mapping, manual uploads (Streamlit parity)."""
from __future__ import annotations

import io
from datetime import datetime
from pathlib import Path
from typing import Any

from app.config import FF_INPUTS_FOLDER, FF_INV_LOGIC_FOLDER, PROJECT_ROOT
from core.utils.dataframe import clean_sheet_df, df_to_records, sanitize_for_json

from core.shared.pipeline_flow import FESTIVE_PATH, INV_BUFFER_PATH



def _file_meta(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"exists": False, "path": str(path)}
    stat = path.stat()
    return {
        "exists": True,
        "path": str(path),
        "size_bytes": stat.st_size,
        "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
    }


def get_inputs_status() -> dict[str, Any]:
    """Check required Final Plan input files on disk (matches pipeline_flow._check_ff_inputs)."""
    ff = Path(FF_INPUTS_FOLDER)
    inv_dir = Path(FF_INV_LOGIC_FOLDER)

    checks = [
        {
            "id": "festive",
            "label": "Festive.xlsx (Hub Festive sheet)",
            "group": "ff_inputs",
            "required": True,
            "sync_action": "festive",
            **_file_meta(FESTIVE_PATH),
        },
        {
            "id": "adhoc",
            "label": "Adhoc_Adjustment.xlsx",
            "group": "ff_inputs",
            "required": True,
            "sync_action": "adhoc",
            **_file_meta(ff / "Adhoc_Adjustment.xlsx"),
        },
        {
            "id": "adhoc_city_product",
            "label": "Adhoc_Adjustment_City_Product.xlsx",
            "group": "ff_inputs",
            "required": False,
            "sync_action": "adhoc",
            **_file_meta(ff / "Adhoc_Adjustment_City_Product.xlsx"),
        },
        {
            "id": "adhoc_hub",
            "label": "Adhoc_Adjustment_Hub.xlsx",
            "group": "ff_inputs",
            "required": False,
            "sync_action": "adhoc",
            **_file_meta(ff / "Adhoc_Adjustment_Hub.xlsx"),
        },
        {
            "id": "inv_buffer",
            "label": "Inv_buffer.xlsx",
            "group": "inventory",
            "required": True,
            "sync_action": "inv-buffer",
            **_file_meta(INV_BUFFER_PATH),
        },
    ]

    inv_files = sorted(inv_dir.glob("*.xlsx")) if inv_dir.is_dir() else []
    required_ok = all(c["exists"] for c in checks if c["required"])
    inv_ok = len(inv_files) > 0

    return sanitize_for_json(
        {
            "ready": required_ok and inv_ok,
            "required_ok": required_ok,
            "inv_logic_ok": inv_ok,
            "inv_logic_count": len(inv_files),
            "inv_logic_files": [f.name for f in inv_files[:20]],
            "checks": checks,
            "ff_inputs_folder": str(ff),
            "inv_logic_folder": str(inv_dir),
        }
    )


def load_city_mapping_preview(*, limit: int = 200) -> dict[str, Any]:
    """Preview City_Mapping tab from Demand Planning Masters."""
    try:
        from core.shared.sheets_session import get_sheets_manager


        gsm = get_sheets_manager()
        df = gsm.read_worksheet_to_df("demand_planning_masters", "city_mapping", "A:Z")
        if df is None or df.empty:
            local = Path(FF_INPUTS_FOLDER) / "City_Mapping.xlsx"
            if local.is_file():
                import pandas as pd

                df = pd.read_excel(local)
            else:
                return {"available": False, "message": "City_Mapping worksheet is empty.", "rows": [], "columns": []}
        clean_sheet_df(df)
        return sanitize_for_json(
            {
                "available": True,
                "source": "demand_planning_masters",
                "rows": df_to_records(df.head(limit)),
                "columns": df.columns.tolist(),
                "row_count": len(df),
            }
        )
    except Exception as exc:
        return {"available": False, "message": str(exc), "rows": [], "columns": []}


def sync_city_mapping_to_folder() -> dict[str, Any]:
    """Export City_Mapping worksheet → FF_INPUTS_FOLDER/City_Mapping.xlsx."""
    import pandas as pd
    from core.shared.sheets_session import get_sheets_manager


    gsm = get_sheets_manager()
    df = gsm.read_worksheet_to_df("demand_planning_masters", "city_mapping", "A:Z")
    if df is None or df.empty:
        raise ValueError("City_Mapping worksheet is empty or unreadable.")
    clean_sheet_df(df)
    out_dir = Path(FF_INPUTS_FOLDER)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "City_Mapping.xlsx"
    df.to_excel(out_path, index=False)
    return {"detail": f"Saved {len(df)} rows to {out_path.name}", "path": str(out_path), "rows": len(df)}


def sync_festive_placeholder_from_sheet() -> dict[str, Any]:
    """
    Ensure Festive.xlsx exists under FF_INPUTS_FOLDER.
    If missing, create a minimal template so operators know the expected layout.
    """
    out_path = Path(FESTIVE_PATH)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.is_file():
        return {"detail": "Festive.xlsx already on disk", "path": str(out_path), "created": False}

    import pandas as pd

    template = pd.DataFrame(
        columns=["city_name", "hub_name", "Cut class", "date", "Hub level Festive Factor"]
    )
    with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
        template.to_excel(writer, sheet_name="Hub Festive", index=False)
    return {
        "detail": "Created Festive.xlsx template — upload or paste Hub Festive data before running.",
        "path": str(out_path),
        "created": True,
    }


UPLOAD_TARGETS = {
    "festive": ("Festive.xlsx", "Hub Festive"),
    "adhoc": ("Adhoc_Adjustment.xlsx", None),
    "adhoc_city_product": ("Adhoc_Adjustment_City_Product.xlsx", None),
    "adhoc_hub": ("Adhoc_Adjustment_Hub.xlsx", None),
    "city_mapping": ("City_Mapping.xlsx", None),
}


def save_uploaded_input(*, kind: str, content: bytes, filename: str) -> dict[str, Any]:
    """Save manual Excel override into FF_INPUTS_FOLDER."""
    if kind not in UPLOAD_TARGETS:
        raise ValueError(f"Unknown upload kind: {kind}")
    if not filename.lower().endswith((".xlsx", ".xls")):
        raise ValueError("Only Excel files (.xlsx) are accepted.")

    import pandas as pd

    target_name, sheet_name = UPLOAD_TARGETS[kind]
    out_dir = Path(FF_INPUTS_FOLDER)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / target_name

    df = pd.read_excel(io.BytesIO(content))
    if sheet_name:
        with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
            df.to_excel(writer, sheet_name=sheet_name, index=False)
    else:
        df.to_excel(out_path, index=False)

    return {
        "detail": f"Saved {target_name} ({len(df)} rows)",
        "path": str(out_path),
        "rows": len(df),
        "columns": df.columns.tolist(),
    }
